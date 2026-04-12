"""
Chart Generator for Solar Energy Quotation System
Generates production charts for PDF reports
Supports Hebrew RTL text rendering with arabic-reshaper and python-bidi
"""

import io

import matplotlib
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

matplotlib.use("Agg")

CHART_BACKGROUND = "#14181F"
CHART_SURFACE = "#1A1D22"
CHART_ACCENT = "#3AE478"
CHART_ACCENT_LIGHT = "#7EF0A8"
CHART_GRID = "#A0AEC0"
CHART_TEXT = "#FFFFFF"
CHART_DARK_TEXT = "#14181F"

try:
    import arabic_reshaper
    from bidi.algorithm import get_display

    RTL_AVAILABLE = True
    print("[OK] RTL text libraries loaded (arabic_reshaper + bidi)")
except ImportError as e:
    RTL_AVAILABLE = False
    print(f"[WARNING] RTL text libraries not available: {e}")
    print("[INFO] Install with: pip install arabic-reshaper python-bidi")


def reshape_text_for_chart(text):
    if text is None:
        return ""

    text_str = str(text)
    if not text_str:
        return ""

    if RTL_AVAILABLE:
        try:
            return get_display(arabic_reshaper.reshape(text_str))
        except Exception as e:
            print(f"[WARNING] RTL text processing error: {e}")

    return text_str


HEBREW_MONTHS_RAW = [
    "ינואר",
    "פברואר",
    "מרץ",
    "אפריל",
    "מאי",
    "יוני",
    "יולי",
    "אוגוסט",
    "ספטמבר",
    "אוקטובר",
    "נובמבר",
    "דצמבר",
]

MONTHLY_COEFFICIENTS = [
    0.88,
    0.95,
    1.10,
    1.15,
    1.20,
    1.22,
    1.20,
    1.15,
    1.08,
    0.98,
    0.90,
    0.85,
]

DIRECTION_COEFFICIENTS = {
    "N": 0.60,
    "NE": 0.75,
    "E": 0.88,
    "SE": 0.95,
    "S": 1.00,
    "SW": 0.95,
    "W": 0.88,
    "NW": 0.75,
}


def style_axes(ax):
    ax.set_facecolor(CHART_SURFACE)
    ax.grid(axis="y", alpha=0.18, linestyle="--", linewidth=0.6, color=CHART_GRID, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(axis="both", labelsize=9, colors=CHART_TEXT, width=0.9)
    for spine in ax.spines.values():
        spine.set_edgecolor(CHART_GRID)
        spine.set_linewidth(0.9)


def generate_monthly_production_chart(system_kwp: float, annual_production: float) -> bytes:
    monthly_production = [(annual_production / 12) * coef for coef in MONTHLY_COEFFICIENTS]

    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor(CHART_BACKGROUND)

    bars = ax.bar(
        range(12),
        monthly_production,
        color=CHART_ACCENT,
        edgecolor=CHART_ACCENT_LIGHT,
        linewidth=1.5,
        width=0.75,
        zorder=3,
    )

    ax.bar(
        range(12),
        monthly_production,
        color="#0F1318",
        alpha=0.45,
        width=0.75,
        bottom=-max(monthly_production) * 0.02,
        zorder=1,
    )

    for bar in bars:
        height = bar.get_height()
        gradient = mpatches.Rectangle(
            (bar.get_x(), height * 0.6),
            bar.get_width(),
            height * 0.4,
            facecolor=CHART_ACCENT_LIGHT,
            edgecolor="none",
            alpha=0.22,
            zorder=4,
        )
        ax.add_patch(gradient)

    ax.set_xlabel(reshape_text_for_chart("חודש"), fontsize=10, fontweight="700", labelpad=10, color=CHART_TEXT)
    ax.set_ylabel(reshape_text_for_chart("ייצור (קוט״ש)"), fontsize=10, fontweight="700", labelpad=10, color=CHART_TEXT)

    title_text = f"ייצור סולארי חודשי - מערכת {system_kwp} קוט״ש"
    ax.set_title(reshape_text_for_chart(title_text), fontsize=12, fontweight="bold", pad=15, color=CHART_TEXT)

    ax.set_xticks(range(12))
    ax.set_xticklabels(
        [reshape_text_for_chart(month) for month in HEBREW_MONTHS_RAW],
        rotation=45,
        ha="right",
        fontsize=9,
        fontweight="500",
        color=CHART_TEXT,
    )
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x):,}"))
    style_axes(ax)

    total_kwh = sum(monthly_production)
    annotation_text = f"סה״כ: {total_kwh:,.0f} קוט״ש/שנה"
    ax.text(
        0.98,
        0.97,
        reshape_text_for_chart(annotation_text),
        transform=ax.transAxes,
        fontsize=9,
        fontweight="700",
        verticalalignment="top",
        horizontalalignment="right",
        color=CHART_DARK_TEXT,
        bbox=dict(
            boxstyle="round,pad=0.6",
            facecolor=CHART_ACCENT,
            edgecolor=CHART_ACCENT_LIGHT,
            linewidth=1.5,
            alpha=0.98,
        ),
    )

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor=CHART_BACKGROUND)
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def generate_directional_production_chart(system_kwp: float, annual_production: float) -> bytes:
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection="polar"))
    fig.patch.set_facecolor(CHART_BACKGROUND)
    ax.set_facecolor(CHART_BACKGROUND)

    directions = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
    angles = np.linspace(0, 2 * np.pi, len(directions), endpoint=False)
    production_values = [annual_production * DIRECTION_COEFFICIENTS[d] for d in directions]
    angles = np.concatenate((angles, [angles[0]]))
    production_values.append(production_values[0])

    shadow_values = [v * 0.95 for v in production_values]
    ax.fill(angles, shadow_values, alpha=0.12, color="#0F1318", zorder=1)
    ax.plot(angles, shadow_values, linewidth=1, color="#0F1318", alpha=0.25, zorder=1)

    for i, alpha_val in enumerate([0.15, 0.25, 0.35]):
        layer_values = [v * (0.4 + i * 0.2) for v in production_values]
        ax.fill(angles, layer_values, alpha=alpha_val, color=CHART_ACCENT, zorder=2 + i)

    ax.plot(
        angles,
        production_values,
        "o-",
        linewidth=3,
        color=CHART_ACCENT,
        markersize=10,
        markeredgecolor=CHART_ACCENT_LIGHT,
        markeredgewidth=2,
        zorder=5,
    )
    ax.fill(angles, production_values, alpha=0.35, color=CHART_ACCENT_LIGHT, zorder=4)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(directions, fontsize=13, fontweight="bold", color=CHART_TEXT)
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"{int(x / 1000)}k"))
    ax.tick_params(axis="y", labelsize=10, colors=CHART_TEXT)
    ax.grid(True, linestyle="--", alpha=0.25, linewidth=0.7, color=CHART_GRID)
    ax.set_ylim(0, max(production_values) * 1.1)
    ax.spines["polar"].set_edgecolor(CHART_GRID)
    ax.spines["polar"].set_linewidth(1.0)

    title_text = f"ייצור שנתי לפי כיוון גג\nמערכת {system_kwp} קוט״ש"
    ax.set_title(reshape_text_for_chart(title_text), fontsize=14, fontweight="bold", pad=20, y=1.08, color=CHART_TEXT)

    center_text = f"דרום\n{int(annual_production):,}\nקוט״ש/שנה"
    ax.text(
        0,
        0,
        reshape_text_for_chart(center_text),
        ha="center",
        va="center",
        fontsize=11,
        fontweight="bold",
        color=CHART_DARK_TEXT,
        bbox=dict(
            boxstyle="round,pad=0.8",
            facecolor=CHART_ACCENT,
            edgecolor=CHART_ACCENT_LIGHT,
            linewidth=2,
            alpha=0.98,
        ),
    )

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=180, bbox_inches="tight", facecolor=CHART_BACKGROUND)
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()


def generate_payback_chart(price: float, annual_revenue: float, years: int = 25) -> bytes:
    year_range = np.arange(0, years + 1)
    cumulative_savings = annual_revenue * year_range - price
    payback_years = price / annual_revenue if annual_revenue > 0 else 0

    fig, ax = plt.subplots(figsize=(10, 4.5))
    fig.patch.set_facecolor("white")

    ax.plot(year_range, cumulative_savings, linewidth=2, color="#00358A", marker="o", markersize=3)
    ax.fill_between(year_range, cumulative_savings, 0, where=(cumulative_savings <= 0), color="#ff4d4f", alpha=0.15, interpolate=True)
    ax.fill_between(year_range, cumulative_savings, 0, where=(cumulative_savings >= 0), color="#00358A", alpha=0.15, interpolate=True)
    ax.axhline(y=0, color="#4a5568", linestyle="-", linewidth=1, alpha=0.4)

    if 0 < payback_years <= years:
        payback_value = annual_revenue * payback_years - price
        ax.plot(payback_years, payback_value, "r*", markersize=15, zorder=5)
        ax.axvline(x=payback_years, color="#ef5350", linestyle="--", linewidth=1.2, alpha=0.6)

        annotation_text = f"נקודת איזון\n{payback_years:.1f} שנים"
        ax.annotate(
            reshape_text_for_chart(annotation_text),
            xy=(payback_years, 0),
            xytext=(payback_years + 2, price * 0.3),
            fontsize=8,
            fontweight="600",
            arrowprops=dict(arrowstyle="->", color="#ef5350", lw=1.5),
            bbox=dict(boxstyle="round,pad=0.4", facecolor="#fff3e0", edgecolor="#ef5350", alpha=0.8),
        )

    ax.set_xlabel(reshape_text_for_chart("שנים"), fontsize=9, fontweight="600", labelpad=8, color="#4a5568")
    ax.set_ylabel(reshape_text_for_chart("חיסכון מצטבר (₪)"), fontsize=9, fontweight="600", labelpad=8, color="#4a5568")
    ax.set_title(reshape_text_for_chart("תקופת החזר השקעה וחיסכון מצטבר"), fontsize=10, fontweight="bold", pad=12, color="#2d3748")
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f"₪{int(x / 1000)}k" if abs(x) >= 1000 else f"₪{int(x)}"))
    ax.tick_params(axis="both", labelsize=8, colors="#4a5568")
    ax.grid(True, alpha=0.2, linestyle="--", linewidth=0.5, color="#cbd5e0")
    ax.set_axisbelow(True)

    final_savings = cumulative_savings[-1]
    legend_text = f"חיסכון כולל ({years} שנים): ₪{final_savings:,.0f}"
    ax.text(
        0.98,
        0.02,
        reshape_text_for_chart(legend_text),
        transform=ax.transAxes,
        fontsize=8,
        fontweight="600",
        verticalalignment="bottom",
        horizontalalignment="right",
        bbox=dict(boxstyle="round,pad=0.5", facecolor="#f7fafc", edgecolor="#cbd5e0", alpha=0.9),
    )

    plt.tight_layout()

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    buf.seek(0)
    plt.close(fig)
    return buf.getvalue()
