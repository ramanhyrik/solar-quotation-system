"""Configurable financial-metric cubes.

Single source of truth for the "מדדים פיננסיים" cubes shown in the quote
editor, the PDF and the sign page. The admin panel stores an ordered list of
cube definitions (label + calculation) in ``pricing_parameters
.financial_metrics_config``; every render surface resolves its cubes from that
list plus the calculation catalog below, so the numbers can never drift apart.

Kept dependency-free (no reportlab / DB imports) so it is safe to import from
main.py, pdf_generator.py and the migration.
"""

import json
import math


# --- Calculation catalog ---------------------------------------------------
# key -> default Hebrew label shown in the admin dropdown. Every key must be
# produced by build_metric_context().
AVAILABLE_CALCULATIONS = [
    ("annual_income", "הכנסה שנתית"),
    ("quarterly_value", "ערך רבעוני משוער"),
    ("cumulative_25", "תזרים מצטבר ל-25 שנה"),
    ("cumulative_18", "תזרים מצטבר ל-18 שנה"),
    ("system_value", "שווי מערכת לאחר 25 שנה"),
    ("total_income", "סך הכנסה"),
    ("gross_annual_revenue", "הכנסה שנתית ברוטו"),
    ("monthly_income", "הכנסה חודשית"),
    ("quarterly_income", "הכנסה רבעונית"),
]

CALCULATION_LABELS = dict(AVAILABLE_CALCULATIONS)
CALCULATION_KEYS = set(CALCULATION_LABELS)

AMORTIZATION_YEARS = 25

# The five cubes shipped today. Used to seed the config so existing quotes are
# unchanged until the admin edits anything.
DEFAULT_METRICS_CONFIG = [
    {"label": "הכנסה שנתית", "calculation": "annual_income", "enabled": True},
    {"label": "ערך רבעוני משוער", "calculation": "quarterly_value", "enabled": True},
    {"label": "תזרים מצטבר ל-25 שנה", "calculation": "cumulative_25", "enabled": True},
    {"label": "שווי מערכת לאחר 25 שנה", "calculation": "system_value", "enabled": True},
    {"label": "סך הכנסה", "calculation": "total_income", "enabled": True},
]


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _assumption(quote_data, pricing, key, default):
    for src in (quote_data, pricing):
        if src and src.get(key) not in (None, ""):
            return _num(src.get(key), default)
    return float(default)


def _effective_metric_value(calculation, computed, overrides):
    """Use a numeric override when deriving a total from a displayed amount."""
    raw = overrides.get(calculation, {}).get("value")
    if raw in (None, ""):
        return computed
    cleaned = "".join(str(raw).replace("₪", "").replace(",", "").split())
    try:
        value = float(cleaned)
    except (TypeError, ValueError):
        return computed
    return value if math.isfinite(value) else computed


def build_metric_context(quote_data, pricing=None, overrides=None):
    """Compute every base figure the cubes can reference.

    All quotes are presented leasing-style (income = leasing revenue share, no
    client investment), matching enrich_quote_render_data.
    """
    quote_data = quote_data or {}
    pricing = pricing or {}
    overrides = normalize_overrides(
        quote_data.get("financial_metrics_overrides") if overrides is None else overrides
    )

    annual_revenue = _num(quote_data.get("annual_revenue"))
    total_price = _num(quote_data.get("total_price"))
    leasing_ratio = _assumption(quote_data, pricing, "leasing_payment_ratio", 0.25)

    # Cumulative customer share = annual revenue × years × leasing share.
    # Flat, with no production degradation, per the agreed tariff model.
    cumulative_25 = round(annual_revenue * AMORTIZATION_YEARS * leasing_ratio)
    # Match JavaScript Math.round so half-shekel values agree with the editor.
    cumulative_18 = math.floor(annual_revenue * 18 * leasing_ratio + 0.5)

    stored_system_value = quote_data.get("system_value_after_25_years")
    system_value = (
        _num(stored_system_value)
        if stored_system_value not in (None, "")
        else total_price
    )

    annual_income = annual_revenue * leasing_ratio
    # Total income follows the first enabled cumulative metric in display order.
    # Without a cumulative cube, retain the established 25-year default.
    config_source = pricing if "financial_metrics_config" in pricing else quote_data
    cumulative_key = next(
        (cube["calculation"] for cube in get_metrics_config(config_source)
         if cube.get("enabled", True) and cube["calculation"] in ("cumulative_18", "cumulative_25")),
        "cumulative_25",
    )
    cumulative_value = cumulative_18 if cumulative_key == "cumulative_18" else cumulative_25
    total_income = (
        _effective_metric_value("system_value", system_value, overrides)
        + _effective_metric_value(cumulative_key, cumulative_value, overrides)
    )

    return {
        "gross_annual_revenue": annual_revenue,
        "annual_income": annual_income,
        "monthly_income": annual_income / 12,
        "quarterly_income": annual_income / 4,
        "cumulative_25": cumulative_25,
        "cumulative_18": cumulative_18,
        "system_value": system_value,
        "total_income": total_income,
        "quarterly_value": total_income / AMORTIZATION_YEARS / 4,
    }


def compute_cube_value(calculation, context):
    return _num(context.get(calculation, 0.0))


def parse_metrics_config(raw):
    """Validate/normalize a stored config list; return None if unusable."""
    if not raw:
        return None
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except (ValueError, TypeError):
            return None
    if not isinstance(raw, list):
        return None

    cleaned = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        calc = str(item.get("calculation") or "").strip()
        if calc not in CALCULATION_KEYS:
            continue
        label = str(item.get("label") or "").strip() or CALCULATION_LABELS[calc]
        enabled = item.get("enabled", True)
        cleaned.append(
            {"label": label, "calculation": calc, "enabled": bool(enabled)}
        )
    return cleaned or None


def get_metrics_config(pricing):
    """Return the effective cube list (stored config or the default five)."""
    config = parse_metrics_config((pricing or {}).get("financial_metrics_config"))
    if config:
        return config
    return [dict(cube) for cube in DEFAULT_METRICS_CONFIG]


# The fixed cube order used before cubes became configurable. Legacy per-quote
# overrides were saved as a positional list in this order; we map them onto the
# calculation keys so old customizations survive reordering.
LEGACY_OVERRIDE_ORDER = [
    "annual_income",
    "cumulative_25",
    "system_value",
    "total_income",
]


def normalize_overrides(overrides):
    """Return per-quote overrides as a dict keyed by calculation.

    Accepts the new keyed dict as-is, or migrates the legacy positional list
    ([annual_income, cumulative_25, system_value, total_income]).
    """
    if isinstance(overrides, str):
        try:
            overrides = json.loads(overrides)
        except (ValueError, TypeError):
            return {}
    if isinstance(overrides, dict):
        return {
            key: value
            for key, value in overrides.items()
            if isinstance(value, dict)
        }
    if isinstance(overrides, list):
        result = {}
        for index, item in enumerate(overrides):
            if index >= len(LEGACY_OVERRIDE_ORDER):
                break
            if not isinstance(item, dict):
                continue
            if item.get("label") or item.get("value") not in (None, ""):
                result[LEGACY_OVERRIDE_ORDER[index]] = item
        return result
    return {}


def resolve_metrics(quote_data, pricing=None, overrides=None):
    """Resolve the ordered cubes for one quote.

    Returns a list of dicts: ``{label, value, override_value, calculation}``.
    Overrides are keyed by calculation: a non-empty override value wins over the
    computed value, an override label wins over the configured label. Disabled
    cubes are skipped.
    """
    config = get_metrics_config(pricing)
    overrides = normalize_overrides(
        (quote_data or {}).get("financial_metrics_overrides") if overrides is None else overrides
    )
    context = build_metric_context(quote_data, pricing, overrides)

    result = []
    for cube in config:
        if not cube.get("enabled", True):
            continue
        calc = cube["calculation"]
        label = cube["label"]
        override_value = None
        override = overrides.get(calc)
        if isinstance(override, dict):
            if override.get("label"):
                label = str(override["label"])
            raw_value = override.get("value")
            if raw_value not in (None, ""):
                override_value = str(raw_value)
        result.append(
            {
                "label": label,
                "value": compute_cube_value(calc, context),
                "override_value": override_value,
                "calculation": calc,
            }
        )
    return result
