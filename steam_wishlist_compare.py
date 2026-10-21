#!/usr/bin/env python3
"""Command-line entry point for the Steam regional-price comparison tool."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Sequence

from steam_price_polisher.analysis import (
    AnalysisRunner,
    deduplicate_wishlist,
)
from steam_price_polisher.cache import SQLiteCache
from steam_price_polisher.configuration import ComparisonConfig, MAX_COMPARISONS
from steam_price_polisher.exchange_rates import (
    CachedExchangeRateProvider,
    ExchangeRateError,
    NbpExchangeRateProvider,
)
from steam_price_polisher.http_client import UrllibJsonHttpClient
from steam_price_polisher.models import AnalysisResult, ComparisonMethodology, GameComparison, SkippedGame
from steam_price_polisher.presentation import ConsolePresenter
from steam_price_polisher.price_service import CachedPriceService
from steam_price_polisher.request_policy import (
    RequestGate,
    RetryPolicy,
    RetryingJsonHttpClient,
)
from steam_price_polisher.steam_access import SteamClient


LIMIT_GAMES: int | None = None
STEAM_API_DELAY = 1.5


def _read_identifier(arguments: Sequence[str]) -> str:
    if arguments:
        return arguments[0].strip()
    try:
        return input(
            "Enter Steam ID (64-bit community ID or custom URL name): "
        ).strip()
    except KeyboardInterrupt:
        return ""


def main(arguments: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if arguments is None else arguments)
    parser = argparse.ArgumentParser(
        description="Compare Steam wishlist prices against Poland (PLN)."
    )
    parser.add_argument("identifier", nargs="?", help="SteamID64 or Steam profile URL")
    parser.add_argument(
        "--regions", nargs="+", metavar="REGION",
        help=f"Choose any supported storefronts (up to {MAX_COMPARISONS}), e.g. us de no gb jp. Default: us de. Put the identifier first.",
    )
    try:
        options = parser.parse_args(args)
    except SystemExit as exc:
        return int(exc.code)
    presenter = ConsolePresenter()
    try:
        config = (
            ComparisonConfig() if options.regions is None
            else ComparisonConfig.from_regions(options.regions)
        )
    except ValueError as exc:
        presenter.error(str(exc))
        return 1
    presenter.banner()
    presenter.info(
        "Storefronts: home pl (PLN); compare "
        + ", ".join(f"{region.region} ({region.currency})" for region in config.alternatives)
    )

    nbp_raw_http_client = UrllibJsonHttpClient()
    steam_raw_http_client = UrllibJsonHttpClient(
        cookie_string=os.environ.get("STEAM_COOKIE", "")
    )
    data_directory = Path(
        os.environ.get(
            "STEAM_PRICE_POLISHER_DATA_DIR",
            Path(__file__).with_name(".steam-price-polisher"),
        )
    )
    try:
        cache = SQLiteCache(data_directory / "cache.sqlite3")
    except Exception as exc:
        presenter.error(f"Could not initialize the local cache: {exc}")
        return 1

    nbp_http_client = RetryingJsonHttpClient(
        nbp_raw_http_client,
        policy=RetryPolicy(max_attempts=3, base_delay=1.0),
    )
    rate_provider = CachedExchangeRateProvider(
        NbpExchangeRateProvider(nbp_http_client),
        cache,
    )
    try:
        rate_details = rate_provider.get_rate_details(config.currencies)
        rates = {currency: rate.rate_to_pln for currency, rate in rate_details.items()}
    except ExchangeRateError as exc:
        presenter.error(str(exc))
        return 1
    presenter.show_exchange_rates(rate_details, config.home.currency)
    presenter.line()

    identifier = _read_identifier([options.identifier] if options.identifier is not None else [])
    if not identifier:
        presenter.error("Steam ID cannot be empty.")
        return 1

    steam_http_client = RetryingJsonHttpClient(
        steam_raw_http_client,
        gate=RequestGate(STEAM_API_DELAY),
    )
    steam_client = SteamClient(
        steam_http_client,
        request_delay=0,
        wishlist_file=Path(__file__).with_name("wishlist.txt"),
        web_api_key=os.environ.get("STEAM_WEB_API_KEY", ""),
    )
    wishlist_result = steam_client.get_wishlist(identifier)
    for warning in wishlist_result.warnings:
        presenter.warning(warning)

    if wishlist_result.failure is not None:
        presenter.error("Wishlist retrieval failed; this does not establish that the wishlist is empty or private.")
        return 1

    wishlist = deduplicate_wishlist(wishlist_result.items)
    if not wishlist:
        presenter.error("No games to process. The wishlist may be empty or private.")
        return 0

    duplicates_removed = len(wishlist_result.items) - len(wishlist)
    if duplicates_removed:
        presenter.warning(f"Removed {duplicates_removed} duplicate wishlist entries.")

    if LIMIT_GAMES is not None:
        wishlist = wishlist[:LIMIT_GAMES]
        presenter.warning(
            f"Limiting analysis to the first {len(wishlist)} games."
        )

    total_games = len(wishlist)
    presenter.show_wishlist_info(total_games, wishlist_result.source)
    calls_per_game = 1 + len(config.alternatives)
    presenter.show_estimate(total_games * calls_per_game * STEAM_API_DELAY)

    price_service = CachedPriceService(steam_client, cache)
    runner = AnalysisRunner(
        price_service,
        home=config.home,
        alternatives=config.alternatives,
    )

    comparisons: list[GameComparison] = []
    skipped: list[SkippedGame] = []

    for progress in runner.run(wishlist, rates):
        if progress.comparison is not None:
            comparisons.append(progress.comparison)
        if progress.skipped is not None:
            skipped.append(progress.skipped)
        presenter.show_game_status(
            progress.index,
            progress.total,
            progress.app_id,
            progress.name,
            progress.status,
            progress.source_summary,
        )

    result = AnalysisResult(
        tuple(comparisons), tuple(skipped), tuple(rate_details.values()), ComparisonMethodology()
    )
    presenter.show_results(result)
    return 2 if result.is_partial else 0


if __name__ == "__main__":
    raise SystemExit(main())
