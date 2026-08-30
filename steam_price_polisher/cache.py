"""SQLite persistence for prices and exchange rates."""

from __future__ import annotations

import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from .models import RegionalPriceResult, StorePrice


@dataclass(frozen=True)
class PriceCacheEntry:
    result: RegionalPriceResult
    fetched_at: float


@dataclass(frozen=True)
class ExchangeRateCacheEntry:
    currency: str
    rate: float
    fetched_at: float


class SQLiteCache:
    """Small atomic cache that also serves as an analysis checkpoint."""

    def __init__(
        self,
        database_path: Path,
        *,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._database_path = database_path
        self._clock = clock
        database_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._database_path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS regional_prices (
                    app_id TEXT NOT NULL,
                    region TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    amount REAL,
                    game_name TEXT,
                    status TEXT NOT NULL CHECK(status IN ('available', 'missing')),
                    fetched_at REAL NOT NULL,
                    PRIMARY KEY (app_id, region)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS exchange_rates (
                    currency TEXT PRIMARY KEY,
                    rate_to_pln REAL NOT NULL,
                    fetched_at REAL NOT NULL
                )
                """
            )

    def get_price(
        self,
        app_id: str,
        region: str,
        expected_currency: str,
    ) -> PriceCacheEntry | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT currency, amount, game_name, status, fetched_at
                FROM regional_prices
                WHERE app_id = ? AND region = ?
                """,
                (str(app_id), region.lower()),
            ).fetchone()
        if row is None or row["currency"] != expected_currency.upper():
            return None

        price = None
        if row["status"] == "available":
            price = StorePrice(region.lower(), row["currency"], float(row["amount"]))
        return PriceCacheEntry(
            RegionalPriceResult(price, row["game_name"]),
            float(row["fetched_at"]),
        )

    def put_price(
        self,
        app_id: str,
        region: str,
        expected_currency: str,
        result: RegionalPriceResult,
    ) -> None:
        status = "available" if result.price is not None else "missing"
        currency = (
            result.price.currency if result.price is not None else expected_currency.upper()
        )
        amount = result.price.amount if result.price is not None else None
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO regional_prices (
                    app_id, region, currency, amount, game_name, status, fetched_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id, region) DO UPDATE SET
                    currency = excluded.currency,
                    amount = excluded.amount,
                    game_name = excluded.game_name,
                    status = excluded.status,
                    fetched_at = excluded.fetched_at
                """,
                (
                    str(app_id),
                    region.lower(),
                    currency.upper(),
                    amount,
                    result.game_name,
                    status,
                    self._clock(),
                ),
            )

    def get_exchange_rate(self, currency: str) -> ExchangeRateCacheEntry | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT rate_to_pln, fetched_at
                FROM exchange_rates
                WHERE currency = ?
                """,
                (currency.upper(),),
            ).fetchone()
        if row is None:
            return None
        return ExchangeRateCacheEntry(
            currency.upper(),
            float(row["rate_to_pln"]),
            float(row["fetched_at"]),
        )

    def put_exchange_rate(self, currency: str, rate: float) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO exchange_rates (currency, rate_to_pln, fetched_at)
                VALUES (?, ?, ?)
                ON CONFLICT(currency) DO UPDATE SET
                    rate_to_pln = excluded.rate_to_pln,
                    fetched_at = excluded.fetched_at
                """,
                (currency.upper(), rate, self._clock()),
            )
