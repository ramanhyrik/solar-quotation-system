import ast
import asyncio
import inspect
import json
import math
import re
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from fastapi import Depends, Form, HTTPException

from metrics_catalog import AVAILABLE_CALCULATIONS, get_metrics_config, parse_metrics_config, build_metric_context
from quote_defaults import (
    LARGE_SYSTEM_TARIFF_RATE, LARGE_SYSTEM_THRESHOLD_KW,
    calculate_tiered_annual_revenue, get_effective_tariff_rate,
    get_first_tier_limit, get_first_tier_rate, get_legacy_quote_text_defaults,
)


class UrbanPremiumTests(unittest.TestCase):
    def test_custom_rate_and_limit_across_tiers(self):
        for size, expected in ((10, 9600), (30, 28800), (60, 47040)):
            with self.subTest(size=size):
                revenue = calculate_tiered_annual_revenue(size, 1600, True, .48, .60, 30)
                self.assertAlmostEqual(revenue, expected)
                self.assertAlmostEqual(get_effective_tariff_rate(size, .48, True, .60, 30), revenue / (size * 1600))

    def test_defaults_standard_and_zero_settings(self):
        self.assertEqual(calculate_tiered_annual_revenue(60, 1600, True), 41520)
        self.assertEqual(calculate_tiered_annual_revenue(60, 1600, True, .48, None, None), 41520)
        self.assertEqual(calculate_tiered_annual_revenue(60, 1600, False, .48, .60, 30), 40080)
        self.assertEqual(calculate_tiered_annual_revenue(60, 1600, True, .48, 0, 30), 18240)
        self.assertEqual(calculate_tiered_annual_revenue(60, 1600, True, .48, .60, 0), 36480)


class UrbanPremiumRouteTests(unittest.TestCase):
    """Execute real route functions with an in-memory pricing-store double.

    main.py imports the production database at module load; extracting the
    routes avoids needing credentials or running production startup migrations.
    """

    def setUp(self):
        self.pricing = dict(price_per_kwp=4500, production_per_kwp=1600,
                            tariff_rate=.48, trees_multiplier=.05,
                            urban_premium_tariff_rate=.52, urban_premium_threshold_kw=22.5)
        owner = self

        class Cursor:
            def execute(self, sql, args=None):
                if 'UPDATE pricing_parameters SET' in sql:
                    columns = re.findall(r'(\w+)\s*=\s*%s', sql)
                    assert len(columns) == len(args)
                    owner.pricing.update(zip(columns, args))

            def fetchone(self):
                return dict(owner.pricing)

        class Connection:
            def commit(self):
                pass

        @contextmanager
        def get_db():
            yield Connection()

        ns = dict(globals(), get_db=get_db, get_cursor=lambda _: Cursor(),
                  get_current_user=lambda: {'user_id': 1},
                  get_latest_pricing=lambda _: dict(self.pricing),
                  convert_decimals_in_dict=lambda value: value,
                  LEGACY_QUOTE_DEFAULTS=get_legacy_quote_text_defaults())
        tree = ast.parse((Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf8'))
        names = {'update_pricing', 'calculate_quote', 'get_pricing', 'build_quote_render_context', 'format_template_number'}
        nodes = [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in names]
        for node in nodes:
            node.decorator_list = []
        exec(compile(ast.Module(body=nodes, type_ignores=[]), 'main.py', 'exec'), ns)
        self.routes = ns

    def save(self, **values):
        route = self.routes['update_pricing']
        args = {name: param.default.default for name, param in inspect.signature(route).parameters.items() if name != 'user'}
        args.update(values, user={'user_id': 1})
        return asyncio.run(route(**args))

    def test_save_reload_calculation_and_quote_text(self):
        self.save(urban_premium_tariff_rate=.60, urban_premium_threshold_kw=30)
        loaded = asyncio.run(self.routes['get_pricing']())
        self.assertEqual(loaded['urban_premium_tariff_rate'], .60)
        self.assertEqual(loaded['urban_premium_threshold_kw'], 30)
        result = asyncio.run(self.routes['calculate_quote'](60, True))
        self.assertEqual(result['annual_revenue'], 47040)
        self.assertEqual(result['tariff_rate'], .49)
        self.assertEqual(asyncio.run(self.routes['calculate_quote'](60, False))['annual_revenue'], 40080)
        rendered = self.routes['build_quote_render_context'](
            dict(result, system_size=60, urban_premium=True), self.pricing
        )
        self.assertEqual(rendered['tariff_first_agorot'], '60')
        self.assertEqual(rendered['tariff_threshold_kw'], '30')
        self.assertEqual(rendered['tariff_rate'], '0.6')
        self.save(trees_multiplier=.07)  # Other settings saves retain premium settings.
        self.assertEqual(self.pricing['urban_premium_tariff_rate'], .60)
        self.assertEqual(self.pricing['urban_premium_threshold_kw'], 30)

    def test_invalid_values_rejected_and_zero_allowed(self):
        for key in ('urban_premium_tariff_rate', 'urban_premium_threshold_kw'):
            for value in (-1, float('inf'), float('nan')):
                with self.subTest(key=key, value=value), self.assertRaises(HTTPException) as error:
                    self.save(**{key: value})
                self.assertEqual(error.exception.status_code, 422)
        self.save(urban_premium_tariff_rate=0, urban_premium_threshold_kw=0)
        self.assertEqual(self.pricing['urban_premium_tariff_rate'], 0)
        self.assertEqual(self.pricing['urban_premium_threshold_kw'], 0)


if __name__ == '__main__':
    unittest.main()
