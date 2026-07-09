import re


LARGE_SYSTEM_THRESHOLD_KW = 22
STANDARD_TARIFF_RATE = 0.48
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
        "1. החישוב מתבסס לפי חישוב של 1500 שעות שמש בשנה לתעריף חברת החשמל לצרכן "
        "({tariff_agorot} אגורות לקוט״ש) בהתאם למסלול הנבחר, והחישוב מניח תחזוקה נאותה של "
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


def get_effective_tariff_rate(system_size, configured_rate=STANDARD_TARIFF_RATE):
    """Return the tariff that applies to a system of the given size."""
    size = float(system_size or 0)
    if size > LARGE_SYSTEM_THRESHOLD_KW:
        return LARGE_SYSTEM_TARIFF_RATE
    return float(configured_rate or STANDARD_TARIFF_RATE)


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
