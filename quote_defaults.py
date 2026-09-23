import re


LARGE_SYSTEM_THRESHOLD_KW = 22.5
STANDARD_TARIFF_RATE = 0.48
URBAN_PREMIUM_TARIFF_RATE = 0.52
LARGE_SYSTEM_TARIFF_RATE = 0.38
SYSTEM_VALUE_AMORTIZATION_YEARS = 25


QUOTE_BACKGROUND = "#14181F"
QUOTE_SURFACE = "#1A1D22"
QUOTE_ACCENT = "#3AE478"
QUOTE_TEXT = "#FFFFFF"
QUOTE_MUTED = "#A0AEC0"


PRICING_TEXT_FIELDS = (
    "basic_assumptions_default",
    "revenue_calculation_default",
    "summary_default",
    "environmental_impact_default",
)

QUOTE_TEXT_FIELD_MAP = {
    "basic_assumptions_text": "basic_assumptions_default",
    "revenue_calculation_text": "revenue_calculation_default",
    "summary_text": "summary_default",
    "environmental_impact_text": "environmental_impact_default",
}


LEGACY_QUOTE_TEXT_DEFAULTS = {
    "basic_assumptions_default": (
        "1. החישוב מתבסס לפי חישוב של 1500 שעות שמש בשנה לתעריף חברת החשמל לצרכן: "
        "{tariff_threshold_kw} קילוואט ראשונים בתעריף {tariff_first_agorot} אגורות לקוט״ש "
        "וכל הספק מעל {tariff_threshold_kw} קילוואט בתעריף {tariff_second_agorot} אגורות לקוט״ש, "
        "בהתאם למסלול הנבחר, והחישוב מניח תחזוקה נאותה של "
        "המערכת לאורך כל תקופת הפעולה.\n"
        "2. כל הנתונים והחישובים המוצגים הינם הערכות בלבד, והכנסות מדויקות "
        "יתאפשרו רק לאחר התקנת המערכת וביצועיה בפועל.\n"
        "ירידה שנתית בייצור: {degradation_rate_percent}% | עלויות תפעול: "
        "{operating_cost_base_percent}% מעלות המערכת | עלייה שנתית בעלויות "
        "תפעול: {operating_cost_increase_percent}%."
    ),
    "revenue_calculation_default": (
        "חישוב ההכנסות מבוסס על ייצור שנתי של {annual_production} קוט״ש, הכנסה "
        "שנתית משוערת של ₪{annual_revenue}, ירידה שנתית הדרגתית בייצור, ותזרים "
        "מצטבר ל-25 שנה של ₪{total_cashflow_25}."
    ),
    "summary_default": (
        "השקעה במערכת סולארית היא השקעה חכמה לטווח ארוך. על פי החישובים, התזרים "
        "המצטבר ל-25 שנה הוא ₪{total_cashflow_25}, מה שמעיד על רווחיות גבוהה. "
        "נשמח לעמוד לשירותכם בכל שאלה."
    ),
    "environmental_impact_default": (
        "המערכת הסולארית שלך תייצר כ-{annual_production} קוט״ש של אנרגיה נקייה "
        "בשנה, שווה ערך לנטיעת {trees} עצים. במשך 25 שנה, זו תרומה משמעותית "
        "לקיימות סביבתית."
    ),
}


PLACEHOLDER_PATTERN = re.compile(r"\{([a-zA-Z0-9_]+)\}")


def get_first_tier_rate(urban_premium=False, configured_rate=STANDARD_TARIFF_RATE,
                        premium_rate=URBAN_PREMIUM_TARIFF_RATE):
    """Tariff for the first tier, using the administrator's premium setting."""
    if urban_premium:
        return float(URBAN_PREMIUM_TARIFF_RATE if premium_rate is None else premium_rate)
    return float(STANDARD_TARIFF_RATE if configured_rate is None else configured_rate)


def get_first_tier_limit(urban_premium=False, premium_limit=LARGE_SYSTEM_THRESHOLD_KW):
    if urban_premium and premium_limit is not None:
        return float(premium_limit)
    return LARGE_SYSTEM_THRESHOLD_KW


def get_effective_tariff_rate(system_size, configured_rate=STANDARD_TARIFF_RATE,
                              urban_premium=False, premium_rate=URBAN_PREMIUM_TARIFF_RATE,
                              premium_limit=LARGE_SYSTEM_THRESHOLD_KW):
    """Blended ₪/kWh tariff for a system (kept for backward compatibility).

    The real revenue is tiered (see :func:`calculate_tiered_annual_revenue`);
    this returns the size-weighted average rate so single-rate callers/displays
    still get a reasonable number.
    """
    size = float(system_size or 0)
    first_rate = get_first_tier_rate(urban_premium, configured_rate, premium_rate)
    threshold = get_first_tier_limit(urban_premium, premium_limit)
    if size <= 0:
        return first_rate
    first_kw = min(size, threshold)
    second_kw = max(0.0, size - threshold)
    blended = (first_kw * first_rate + second_kw * LARGE_SYSTEM_TARIFF_RATE) / size
    return blended


def calculate_tiered_annual_revenue(
    system_size,
    production_per_kwp,
    urban_premium=False,
    configured_rate=STANDARD_TARIFF_RATE,
    premium_rate=URBAN_PREMIUM_TARIFF_RATE,
    premium_limit=LARGE_SYSTEM_THRESHOLD_KW,
):
    """Annual revenue split at the standard or configured premium capacity limit.

    * First tier -> configured standard or Urban Premium rate and capacity limit
    * Above the first-tier limit -> 0.38 ₪/kWh

    Production is split proportionally by capacity. The standard limit and
    default premium limit are 22.5 kW.
    """
    size = float(system_size or 0)
    production_per_kw = float(production_per_kwp or 0)
    first_rate = get_first_tier_rate(urban_premium, configured_rate, premium_rate)
    threshold = get_first_tier_limit(urban_premium, premium_limit)

    first_kw = min(size, threshold)
    second_kw = max(0.0, size - threshold)

    first_production = first_kw * production_per_kw
    second_production = second_kw * production_per_kw
    return first_production * first_rate + second_production * LARGE_SYSTEM_TARIFF_RATE


def calculate_annual_income(
    annual_revenue,
    system_value_after_25_years=0,
    revenue_share=1.0,
):
    """Calculate displayed annual income (revenue share only).

    Note: ``system_value_after_25_years`` is retained for backward
    compatibility with existing callers but is intentionally NOT added to the
    annual income. The 25-year system value is instead surfaced separately in
    the ``ערך רבעוני משוער`` (estimated quarterly value) cube via
    :func:`calculate_quarterly_value`.
    """
    revenue = float(annual_revenue or 0)
    share = float(revenue_share if revenue_share is not None else 1.0)
    return revenue * share


def calculate_quarterly_value(total_income_after_25_years):
    """Estimated quarterly value = total 25-year income / 25 / 4."""
    total = float(total_income_after_25_years or 0)
    return total / SYSTEM_VALUE_AMORTIZATION_YEARS / 4


def get_legacy_quote_text_defaults():
    return dict(LEGACY_QUOTE_TEXT_DEFAULTS)


def render_quote_template(template, context):
    if not template:
        return ""

    def replace(match):
        key = match.group(1)
        value = context.get(key, "")
        return "" if value is None else str(value)

    return PLACEHOLDER_PATTERN.sub(replace, str(template))
