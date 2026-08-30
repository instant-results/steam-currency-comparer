import io
import unittest

from steam_price_polisher.comparison import compare_game
from steam_price_polisher.models import AnalysisResult, StorePrice
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
        self.assertNotIn("\033[", rendered)


if __name__ == "__main__":
    unittest.main()
