"""SQLite persistence for prices and exchange rates."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterator

from .models import PriceStatus, RegionalPriceResult, StorePrice


@dataclass(frozen=True)
class PriceCacheEntry:
    result: RegionalPriceResult
    fetched_at: float


@dataclass(frozen=True)
class ExchangeRateCacheEntry:
    currency: str
    rate: float
    fetched_at: float
    effective_date: str | None = None


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
            table = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                ("regional_prices",),
            ).fetchone()
            if table is not None and "'missing'" in table["sql"]:
                self._migrate_legacy_price_table(connection)
            self._create_price_table(connection)
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS exchange_rates (
                    currency TEXT PRIMARY KEY,
                    rate_to_pln REAL NOT NULL,
                    fetched_at REAL NOT NULL
                )
                """
            )
            columns = {row["name"] for row in connection.execute("PRAGMA table_info(exchange_rates)")}
            if "effective_date" not in columns:
                connection.execute("ALTER TABLE exchange_rates ADD COLUMN effective_date TEXT")
            price_columns = {row["name"] for row in connection.execute("PRAGMA table_info(regional_prices)")}
            for name, kind in (("base_amount", "REAL"), ("discount_percent", "INTEGER"), ("is_free", "INTEGER"), ("developers", "TEXT"), ("publishers", "TEXT")):
                if name not in price_columns:
                    connection.execute(f"ALTER TABLE regional_prices ADD COLUMN {name} {kind}")
            connection.execute("PRAGMA user_version = 6")

    @staticmethod
    def _create_price_table(connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS regional_prices (
                app_id TEXT NOT NULL,
                region TEXT NOT NULL,
                currency TEXT NOT NULL,
                amount REAL,
                game_name TEXT,
                status TEXT NOT NULL CHECK(status IN (
                    'available', 'no_regional_price', 'app_unavailable'
                )),
                detail TEXT,
                fetched_at REAL NOT NULL,
                PRIMARY KEY (app_id, region)
            )
            """
        )

    def _migrate_legacy_price_table(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            "ALTER TABLE regional_prices RENAME TO regional_prices_legacy"
        )
        self._create_price_table(connection)
        connection.execute(
            """
            INSERT INTO regional_prices (
                app_id, region, currency, amount, game_name, status, detail, fetched_at
            )
            SELECT
                app_id,
                region,
                currency,
                amount,
                game_name,
                CASE status
                    WHEN 'available' THEN 'available'
                    ELSE 'no_regional_price'
                END,
                NULL,
                fetched_at
            FROM regional_prices_legacy
            """
        )
        connection.execute("DROP TABLE regional_prices_legacy")

    def get_price(
        self,
        app_id: str,
        region: str,
        expected_currency: str,
    ) -> PriceCacheEntry | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT currency, amount, game_name, status, detail, fetched_at, base_amount, discount_percent, is_free, developers, publishers
                FROM regional_prices
                WHERE app_id = ? AND region = ?
                """,
                (str(app_id), region.lower()),
            ).fetchone()
        if row is None or row["currency"] != expected_currency.upper():
            return None

        try:
            status = PriceStatus(row["status"])
        except ValueError:
            return None
        if status is PriceStatus.AVAILABLE:
            if row["amount"] is None:
                return None
            result = RegionalPriceResult.available(
                StorePrice(region.lower(), row["currency"], float(row["amount"]),
                           row["base_amount"], row["discount_percent"]),
                row["game_name"],
            )
        elif status is PriceStatus.NO_REGIONAL_PRICE:
            result = RegionalPriceResult.no_regional_price(
                row["game_name"],
                row["detail"],
            )
        else:
            result = RegionalPriceResult.app_unavailable(row["detail"])
        return PriceCacheEntry(
            replace(result, is_free=None if row["is_free"] is None else bool(row["is_free"]),
                    developers=None if row["developers"] is None else tuple(json.loads(row["developers"])),
                    publishers=None if row["publishers"] is None else tuple(json.loads(row["publishers"]))),
            float(row["fetched_at"]),
        )

    def put_price(
        self,
        app_id: str,
        region: str,
        expected_currency: str,
        result: RegionalPriceResult,
    ) -> None:
        currency = (
            result.price.currency if result.price is not None else expected_currency.upper()
        )
        amount = result.price.amount if result.price is not None else None
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO regional_prices (
                    app_id, region, currency, amount, game_name, status, detail, fetched_at, base_amount, discount_percent, is_free, developers, publishers
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id, region) DO UPDATE SET
                    currency = excluded.currency,
                    amount = excluded.amount,
                    base_amount = excluded.base_amount,
                    discount_percent = excluded.discount_percent,
                    is_free = excluded.is_free,
                    developers = excluded.developers,
                    publishers = excluded.publishers,
                    game_name = excluded.game_name,
                    status = excluded.status,
                    detail = excluded.detail,
                    fetched_at = excluded.fetched_at
                """,
                (
                    str(app_id),
                    region.lower(),
                    currency.upper(),
                    amount,
                    result.game_name,
                    result.status.value,
                    result.detail,
                    self._clock(),
                    result.price.base_amount if result.price else None,
                    result.price.discount_percent if result.price else None,
                    result.is_free,
                    None if result.developers is None else json.dumps(result.developers),
                    None if result.publishers is None else json.dumps(result.publishers),
                ),
            )

    def get_exchange_rate(self, currency: str) -> ExchangeRateCacheEntry | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT rate_to_pln, fetched_at, effective_date
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
            row["effective_date"],
        )

    def put_exchange_rate(self, currency: str, rate: float, effective_date: str | None = None) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO exchange_rates (currency, rate_to_pln, fetched_at, effective_date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(currency) DO UPDATE SET
                    rate_to_pln = excluded.rate_to_pln,
                    effective_date = excluded.effective_date,
                    fetched_at = excluded.fetched_at
                """,
                (currency.upper(), rate, self._clock(), effective_date),
            )
