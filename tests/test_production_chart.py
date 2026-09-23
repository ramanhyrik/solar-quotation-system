import unittest
from unittest.mock import patch

from chart_generator import generate_monthly_production_chart, plt, reshape_text_for_chart


class ProductionChartTests(unittest.TestCase):
    def test_chart_tracks_annual_production(self):
        # Include a changed quote, fractional production, and zero production.
        for annual_production, expected_label in (
            (36000, "36,000"),
            (72000, "72,000"),
            (12345.67, "12,345.67"),
            (0, "0"),
        ):
            with self.subTest(annual_production=annual_production):
                fig, ax = plt.subplots()
                try:
                    with patch("chart_generator.plt.subplots", return_value=(fig, ax)):
                        png = generate_monthly_production_chart(22.5, annual_production)
                    heights = [bar.get_height() for bar in ax.containers[0]]
                    self.assertEqual(len(heights), 12)
                    self.assertAlmostEqual(sum(heights), annual_production)
                    self.assertTrue(all(height >= 0 for height in heights))
                    if annual_production:
                        self.assertGreater(heights[5], heights[0])
                    self.assertIn(
                        reshape_text_for_chart(f"סה״כ: {expected_label} קוט״ש/שנה"),
                        [text.get_text() for text in ax.texts],
                    )
                    self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
                finally:
                    plt.close(fig)


if __name__ == "__main__":
    unittest.main()
