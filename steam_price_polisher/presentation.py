"""Console presentation for wishlist comparison results."""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping, Sequence
from typing import TextIO

from .models import AnalysisResult, GameComparison, SkipCategory


GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def supports_color(stream: TextIO) -> bool:
    if not getattr(stream, "isatty", lambda: False)():
        return False
    if os.name != "nt":
        return True
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        return True
    except Exception:
        return "ANSICON" in os.environ or "WT_SESSION" in os.environ


class ConsolePresenter:
    def __init__(
        self,
        stream: TextIO = sys.stdout,
        *,
        use_colors: bool | None = None,
    ) -> None:
        self._stream = stream
        self._use_colors = supports_color(stream) if use_colors is None else use_colors

    def styled(self, text: str, *styles: str) -> str:
        if not self._use_colors:
            return text
        return f"{''.join(styles)}{text}{RESET}"

    def line(self, text: str = "") -> None:
        print(text, file=self._stream, flush=True)

    def banner(self) -> None:
        border = "==============================================="
        self.line(self.styled(border, CYAN))
        self.line(self.styled("      STEAM WISHLIST PRICE COMPARER (PLN)     ", BOLD, CYAN))
        self.line(self.styled(border, CYAN))

    def info(self, text: str) -> None:
        self.line(self.styled(text, CYAN))

    def warning(self, text: str) -> None:
        self.line(self.styled(f"[!] {text}", YELLOW))

    def error(self, text: str) -> None:
        self.line(self.styled(text, RED))

    def show_exchange_rates(self, rates: Mapping[str, float], home_currency: str) -> None:
        self.info("Fetching exchange rates from Narodowy Bank Polski...")
        for currency, rate in rates.items():
            self.line(
                f"  {currency} to {home_currency} Rate: "
                f"{self.styled(f'{rate:.4f}', GREEN)} {home_currency}"
            )

    def show_wishlist_info(self, count: int, source: str) -> None:
        self.line(
            f"Found {self.styled(str(count), GREEN)} games on your wishlist "
            f"using {source}."
        )

    def show_estimate(self, seconds: float) -> None:
        minutes = seconds / 60
        self.line(
            "Cold-cache request delay estimate: up to "
            f"{self.styled(f'{seconds:.1f} seconds', YELLOW)} "
            f"({self.styled(f'{minutes:.1f} minutes', YELLOW)})"
        )
        self.info("Please wait, querying Steam API...")
        self.line()

    def show_game_status(
        self,
        index: int,
        total: int,
        app_id: str,
        name: str,
        status: str,
        source_summary: str = "",
    ) -> None:
        if status == "fair":
            label = self.styled("FAIR PRICE! [OK]", GREEN, BOLD)
        elif status == "expensive":
            label = self.styled("EXPENSIVE! [X]", RED)
        else:
            label = self.styled(f"SKIPPED ({status})", YELLOW)
        source = f" [{source_summary}]" if source_summary else ""
        self.line(
            f"[{index}/{total}] {app_id}: {self.styled(name, BOLD)} {label}{source}"
        )

    def show_results(self, result: AnalysisResult) -> None:
        border = "==============================================="
        self.line()
        self.line(self.styled(border, CYAN))
        self.line(self.styled("                    RESULTS                    ", BOLD, CYAN))
        self.line(self.styled(border, CYAN))

        if result.fair_games:
            self._show_group(
                "[FAIR] FAIR PRICE GAMES (home price is cheaper/equal):",
                result.fair_games,
                is_fair=True,
            )
        else:
            self.warning(
                "No games have a cheaper/equal home price than every comparison region."
            )

        if result.expensive_games:
            self._show_group(
                "[EXPENSIVE] EXPENSIVE GAMES (home price is more expensive):",
                result.expensive_games,
                is_fair=False,
            )

        self.line()
        self.line(self.styled(border, CYAN))
        self.line(f"Total Wishlist Checked: {result.total_checked}")
        self.line(f"Fair Games: {self.styled(str(len(result.fair_games)), GREEN)}")
        self.line(
            f"Expensive Games: {self.styled(str(len(result.expensive_games)), RED)}"
        )
        self.line(
            "No Regional Price: "
            f"{result.skipped_count(SkipCategory.NO_REGIONAL_PRICE)}"
        )
        self.line(
            "Apps Unavailable: "
            f"{result.skipped_count(SkipCategory.APP_UNAVAILABLE)}"
        )
        self.line(f"Technical Failures: {len(result.technical_failures)}")
        for category in (
            SkipCategory.TEMPORARY_FAILURE,
            SkipCategory.INVALID_RESPONSE,
            SkipCategory.REGION_MISMATCH,
            SkipCategory.REQUEST_FAILURE,
        ):
            count = result.skipped_count(category)
            if count:
                self.line(f"  {category.label}: {count}")
        if result.is_partial:
            self.line(f"Run Status: {self.styled('PARTIAL', YELLOW, BOLD)}")
        else:
            self.line(f"Run Status: {self.styled('COMPLETE', GREEN, BOLD)}")
        self.line(self.styled(border, CYAN))

    def _show_group(
        self,
        title: str,
        games: Sequence[GameComparison],
        *,
        is_fair: bool,
    ) -> None:
        title_color = GREEN if is_fair else RED
        self.line()
        self.line(self.styled(title, title_color))

        first = games[0]
        home_currency = first.home_price.currency
        alternative_currencies = [price.currency for price in first.alternatives]
        headers = ["Game Name", f"{home_currency} Price"]
        headers.extend(
            f"{currency} (in {home_currency})" for currency in alternative_currencies
        )
        headers.append("Savings" if is_fair else "Loss/Overpay")
        widths = [35, 14] + [17] * len(alternative_currencies) + [20]

        header = " | ".join(
            f"{label:<{width}}" for label, width in zip(headers, widths, strict=True)
        )
        self.line(header)
        self.line("-" * len(header))

        for game in games:
            values = [
                game.name[:34],
                f"{game.home_price.amount:.2f} {game.home_price.currency}",
            ]
            values.extend(
                f"{price.amount_in_home:.2f} {game.home_price.currency}"
                for price in game.alternatives
            )
            if is_fair:
                metric = f"{game.savings:.2f} {game.home_price.currency}"
                metric = self.styled(metric, GREEN)
            else:
                cheapest = game.cheapest_alternative.currency
                metric = (
                    f"+{game.overpayment:.2f} {game.home_price.currency} ({cheapest})"
                )
                metric = self.styled(metric, RED)
            values.append(metric)
            self.line(
                " | ".join(
                    f"{value:<{width}}"
                    for value, width in zip(values, widths, strict=True)
                )
            )
