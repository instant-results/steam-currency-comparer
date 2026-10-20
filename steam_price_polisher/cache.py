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

from .models import ExchangeRate, PriceStatus, RegionalPriceResult, StorePrice


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
    source: str = "NBP table A (mid)"


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
            if "source" not in columns:
                connection.execute("ALTER TABLE exchange_rates ADD COLUMN source TEXT NOT NULL DEFAULT 'NBP table A (mid)'")
            connection.execute("""CREATE TABLE IF NOT EXISTS exchange_rate_tables (
                table_name TEXT PRIMARY KEY CHECK(table_name IN ('A', 'B')),
                fetched_at REAL NOT NULL)""")
            price_columns = {row["name"] for row in connection.execute("PRAGMA table_info(regional_prices)")}
            for name, kind in (("base_amount", "REAL"), ("discount_percent", "INTEGER"), ("is_free", "INTEGER"), ("developers", "TEXT"), ("publishers", "TEXT"), ("discount_calculated", "INTEGER")):
                if name not in price_columns:
                    connection.execute(f"ALTER TABLE regional_prices ADD COLUMN {name} {kind}")
            connection.execute("""CREATE TABLE IF NOT EXISTS batch_observations (
                kind TEXT NOT NULL, app_id TEXT NOT NULL, region TEXT NOT NULL,
                payload TEXT NOT NULL, fetched_at REAL NOT NULL,
                PRIMARY KEY(kind, app_id, region))""")
            connection.execute("PRAGMA user_version = 9")

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
                SELECT currency, amount, game_name, status, detail, fetched_at, base_amount, discount_percent, is_free, developers, publishers, discount_calculated
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
                           row["base_amount"], row["discount_percent"],
                           discount_calculated=bool(row["discount_calculated"]) or (row["discount_calculated"] is None and row["discount_percent"] is not None and not float(row["discount_percent"]).is_integer())),
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
                    app_id, region, currency, amount, game_name, status, detail, fetched_at, base_amount, discount_percent, is_free, developers, publishers, discount_calculated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(app_id, region) DO UPDATE SET
                    currency = excluded.currency,
                    amount = excluded.amount,
                    base_amount = excluded.base_amount,
                    discount_percent = excluded.discount_percent,
                    discount_calculated = excluded.discount_calculated,
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
                    result.price.discount_calculated if result.price else None,
                ),
            )

    def get_exchange_rate(self, currency: str) -> ExchangeRateCacheEntry | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT rate_to_pln, fetched_at, effective_date, source
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
            row["source"],
        )

    def put_exchange_rate(self, currency: str, rate: float, effective_date: str | None = None,
                          *, source: str = "NBP table A (mid)") -> None:
        with self._connection() as connection:
            self._put_exchange_rate(connection, currency, rate, effective_date, source, self._clock())

    @staticmethod
    def _put_exchange_rate(connection, currency, rate, effective_date, source, fetched_at):
        connection.execute("""
            INSERT INTO exchange_rates (currency, rate_to_pln, fetched_at, effective_date, source)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(currency) DO UPDATE SET
                rate_to_pln = excluded.rate_to_pln,
                effective_date = excluded.effective_date,
                fetched_at = excluded.fetched_at,
                source = excluded.source
            """, (currency.upper(), rate, fetched_at, effective_date, source))

    def get_exchange_rate_table_fetched_at(self, table: str) -> float | None:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT fetched_at FROM exchange_rate_tables WHERE table_name = ?", (table,)
            ).fetchone()
        return float(row["fetched_at"]) if row else None

    def put_exchange_rate_table(self, table: str, rates: dict[str, ExchangeRate]) -> None:
        """Commit a validated complete table and its freshness marker atomically."""
        if table not in {"A", "B"} or not rates or any(
            key != rate.currency or rate.source != f"NBP table {table} (mid)"
            or rate.effective_date is None or rate.cache_status != "live"
            for key, rate in rates.items()
        ):
            raise ValueError("Expected a complete live NBP table")
        fetched_at = self._clock()
        with self._connection() as connection:
            for rate in rates.values():
                self._put_exchange_rate(connection, rate.currency, rate.rate_to_pln,
                                        rate.effective_date, rate.source, fetched_at)
            connection.execute("""
                INSERT INTO exchange_rate_tables (table_name, fetched_at) VALUES (?, ?)
                ON CONFLICT(table_name) DO UPDATE SET fetched_at = excluded.fetched_at
                """, (table, fetched_at))

    def get_observation(self, kind, app_id, region):
        """Metadata (English, regional context) and offers have independent ages."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT payload, fetched_at FROM batch_observations WHERE kind=? AND app_id=? AND region=?",
                (kind, str(app_id), region.lower())).fetchone()
        return (json.loads(row["payload"]), row["fetched_at"]) if row else None

    def put_observation(self, kind, app_id, region, payload):
        with self._connection() as connection:
            connection.execute("""INSERT INTO batch_observations VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(kind, app_id, region) DO UPDATE SET
                payload=excluded.payload, fetched_at=excluded.fetched_at""",
                (kind, str(app_id), region.lower(), json.dumps(payload, allow_nan=False), self._clock()))
