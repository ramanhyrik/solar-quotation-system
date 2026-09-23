import json
import unittest
from pathlib import Path
from types import SimpleNamespace

from jinja2 import Environment, FileSystemLoader

from metrics_catalog import CALCULATION_LABELS, build_metric_context, parse_metrics_config, resolve_metrics
from pdf_generator import build_leasing_metrics_rows, build_specs_rows, reshape_hebrew


class QuoteMetricTests(unittest.TestCase):
    def test_eighteen_year_metric_and_existing_totals(self):
        for revenue, ratio, expected in (
            (13680, 0.25, 61560),
            (20000, 0.4, 144000),
            (10001, 0.25, 45005),  # Half-shekel: same rounding as the browser.
            (0, 0.25, 0),
            (15000, 0, 0),
        ):
            with self.subTest(revenue=revenue, ratio=ratio):
                context = build_metric_context(
                    {"annual_revenue": revenue, "total_price": 101250},
                    {"leasing_payment_ratio": ratio},
                )
                self.assertEqual(context["cumulative_18"], expected)
                self.assertEqual(context["cumulative_25"], round(revenue * 25 * ratio))
                self.assertEqual(context["total_income"], 101250 + context["cumulative_25"])

    def test_metric_config_roundtrip_pdf_and_overrides(self):
        config = [{"calculation": "cumulative_18", "label": "", "enabled": True}]
        saved = json.dumps(parse_metrics_config(config))
        label = CALCULATION_LABELS["cumulative_18"]
        quote = {"annual_revenue": 13680, "financial_metrics_config": saved}
        self.assertEqual(parse_metrics_config(saved)[0]["label"], label)
        for model in ("purchase", "leasing"):
            with self.subTest(model=model):
                rows = build_leasing_metrics_rows(quote, model)
                self.assertEqual(rows[1], [reshape_hebrew("₪61,560"), reshape_hebrew(label)])
        result = resolve_metrics(quote, quote, {"cumulative_18": {"value": "12345"}})
        self.assertEqual(result[0]["override_value"], "12345")
        disabled = [{"calculation": "cumulative_18", "enabled": False}]
        self.assertEqual(resolve_metrics(quote, {"financial_metrics_config": disabled}), [])


class MaintenanceTests(unittest.TestCase):
    def test_empty_maintenance_is_omitted_and_text_is_retained(self):
        label = reshape_hebrew("תחזוקה:")
        for model in ("purchase", "leasing"):
            for value in (None, "", "   ", "\t\n"):
                with self.subTest(model=model, value=value):
                    rows = build_specs_rows({"maintenance": value}, "Not specified", model)
                    self.assertNotIn(label, [row[1] for row in rows])
            rows = build_specs_rows({"maintenance": "Annual maintenance"}, "Not specified", model)
            self.assertIn([reshape_hebrew("Annual maintenance"), label], rows)
        self.assertNotIn(label, [row[1] for row in build_specs_rows({}, "Not specified")])

    def test_signing_page_omits_empty_maintenance(self):
        templates = Path(__file__).resolve().parents[1] / "templates"
        template = Environment(loader=FileSystemLoader(templates)).get_template("sign_quote.html")
        for value in (None, "", "   ", "Annual maintenance"):
            with self.subTest(value=value):
                html = template.render(
                    maintenance=value,
                    request=SimpleNamespace(url=SimpleNamespace(path="/sign/test")),
                )
                self.assertEqual(
                    '<span class="detail-label">תחזוקה:</span>' in html,
                    bool(value and value.strip()),
                )


if __name__ == "__main__":
    unittest.main()
