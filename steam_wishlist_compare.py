#!/usr/bin/env python3
"""Command-line entry point for the Steam regional-price comparison tool."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Sequence

from steam_price_polisher.comparison import compare_game
from steam_price_polisher.exchange_rates import ExchangeRateError, NbpExchangeRateProvider
from steam_price_polisher.http_client import UrllibJsonHttpClient
from steam_price_polisher.models import AnalysisResult, GameComparison, SkippedGame, StorePrice
from steam_price_polisher.presentation import ConsolePresenter
from steam_price_polisher.steam_access import SteamAccessError, SteamClient


# Keep the original defaults while making the processing layers independent.
HOME_REGION = "pl"
HOME_CURRENCY = "PLN"
COMPARISON_REGIONS = (("us", "USD"), ("de", "EUR"))
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
    presenter = ConsolePresenter()
    presenter.banner()

    http_client = UrllibJsonHttpClient(
        cookie_string=os.environ.get("STEAM_COOKIE", "")
    )
    rate_provider = NbpExchangeRateProvider(http_client)
    try:
        rates = rate_provider.get_rates_to_pln(
            currency for _, currency in COMPARISON_REGIONS
        )
    except ExchangeRateError as exc:
        presenter.error(str(exc))
        return 1
    presenter.show_exchange_rates(rates, HOME_CURRENCY)
    presenter.line()

    identifier = _read_identifier(args)
    if not identifier:
        presenter.error("Steam ID cannot be empty.")
        return 1

    steam_client = SteamClient(
        http_client,
        request_delay=STEAM_API_DELAY,
        wishlist_file=Path(__file__).with_name("wishlist.txt"),
    )
    wishlist_result = steam_client.get_wishlist(identifier)
    for warning in wishlist_result.warnings:
        presenter.warning(warning)

    wishlist = wishlist_result.items
    if not wishlist:
        presenter.error("No games to process. The wishlist may be empty or private.")
        return 0

    if LIMIT_GAMES is not None:
        wishlist = wishlist[:LIMIT_GAMES]
        presenter.warning(
            f"Limiting analysis to the first {len(wishlist)} games."
        )

    total_games = len(wishlist)
    presenter.show_wishlist_info(total_games, wishlist_result.source)
    calls_per_game = 1 + len(COMPARISON_REGIONS)
    presenter.show_estimate(total_games * calls_per_game * STEAM_API_DELAY)

    comparisons: list[GameComparison] = []
    skipped: list[SkippedGame] = []

    for index, item in enumerate(wishlist, start=1):
        display_name = item.name or f"App {item.app_id}"
        try:
            home_result = steam_client.get_regional_price(
                item.app_id,
                HOME_REGION,
                HOME_CURRENCY,
            )
        except SteamAccessError as exc:
            reason = str(exc)
            skipped.append(SkippedGame(item.app_id, display_name, reason))
            presenter.show_game_status(
                index, total_games, item.app_id, display_name, reason
            )
            continue

        if home_result.game_name:
            display_name = home_result.game_name
        if home_result.price is None:
            reason = f"No {HOME_CURRENCY} price/Free/Unreleased"
            skipped.append(SkippedGame(item.app_id, display_name, reason))
            presenter.show_game_status(
                index, total_games, item.app_id, display_name, reason
            )
            continue

        alternative_prices: list[StorePrice] = []
        skip_reason: str | None = None
        for region, currency in COMPARISON_REGIONS:
            try:
                regional_result = steam_client.get_regional_price(
                    item.app_id,
                    region,
                    currency,
                )
            except SteamAccessError as exc:
                skip_reason = str(exc)
                break
            if regional_result.price is None:
                skip_reason = f"{currency} price missing"
                break
            alternative_prices.append(regional_result.price)

        if skip_reason:
            skipped.append(SkippedGame(item.app_id, display_name, skip_reason))
            presenter.show_game_status(
                index, total_games, item.app_id, display_name, skip_reason
            )
            continue

        comparison = compare_game(
            item.app_id,
            display_name,
            home_result.price,
            alternative_prices,
            rates,
        )
        comparisons.append(comparison)
        presenter.show_game_status(
            index,
            total_games,
            item.app_id,
            display_name,
            "fair" if comparison.is_fair else "expensive",
        )

    result = AnalysisResult(tuple(comparisons), tuple(skipped))
    presenter.show_results(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
