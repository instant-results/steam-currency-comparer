import io
import unittest

from steam_price_polisher.comparison import compare_game
from steam_price_polisher.models import (
    AnalysisResult,
    SkipCategory,
    SkippedGame,
    StorePrice,
)
from steam_price_polisher.presentation import ConsolePresenter


class PresentationTests(unittest.TestCase):
    def test_results_can_be_rendered_without_terminal_or_network(self):
        game = compare_game(
            "10",
            "Test Game",
            StorePrice("pl", "PLN", 40.0),
            (StorePrice("us", "USD", 10.0), StorePrice("de", "EUR", 12.0)),
            {"USD": 4.0, "EUR": 4.5},
        )
        stream = io.StringIO()

        ConsolePresenter(stream, use_colors=False).show_results(
            AnalysisResult((game,), ())
        )

        rendered = stream.getvalue()
        self.assertIn("Test Game", rendered)
        self.assertIn("Fair Games: 1", rendered)
        self.assertIn("Run Status: COMPLETE", rendered)
        self.assertNotIn("\033[", rendered)

    def test_technical_failures_mark_the_run_partial(self):
        stream = io.StringIO()
        skipped = SkippedGame(
            "10",
            "Broken Game",
            "Steam returned malformed data",
            SkipCategory.INVALID_RESPONSE,
            "pl",
            False,
        )

        ConsolePresenter(stream, use_colors=False).show_results(
            AnalysisResult((), (skipped,))
        )

        rendered = stream.getvalue()
        self.assertIn("Invalid Steam responses: 1", rendered)
        self.assertIn("Run Status: PARTIAL", rendered)


if __name__ == "__main__":
    unittest.main()
