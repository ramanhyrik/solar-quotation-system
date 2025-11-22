"""
Chart Generator for Solar Energy Quotation System
Generates production charts for PDF reports
Supports Hebrew RTL text rendering with arabic-reshaper and python-bidi
"""
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for server-side rendering
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Wedge, Circle
import numpy as np
import io
from PIL import Image

# Try to import libraries for proper RTL text handling in charts
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
    """
    Reshape Hebrew/Arabic text for proper RTL display in matplotlib charts.
    This requires both arabic_reshaper and python-bidi libraries.
    """
    if text is None:
        return ''

    text_str = str(text)
    if not text_str:
        return ''

    if RTL_AVAILABLE:
        try:
            # Step 1: Reshape the text (handles character connections)
            reshaped_text = arabic_reshaper.reshape(text_str)
            # Step 2: Apply bidi algorithm for proper RTL display
            bidi_text = get_display(reshaped_text)
            return bidi_text
        except Exception as e:
            print(f"[WARNING] RTL text processing error: {e}")
            return text_str

    # Fallback if libraries not available
    return text_str

# Hebrew month names for chart (will be reshaped for RTL display)
HEBREW_MONTHS_RAW = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
                     'יולי', 'אוגוסט', 'ספטמבר', 'אוקטובר', 'נובמבר', 'דצמבר']

# Monthly production coefficients (relative to annual average)
# Based on typical solar production patterns in Israel
MONTHLY_COEFFICIENTS = [
    0.88,  # January
    0.95,  # February
    1.10,  # March
    1.15,  # April
    1.20,  # May
    1.22,  # June
    1.20,  # July
    1.15,  # August
    1.08,  # September
    0.98,  # October
    0.90,  # November
    0.85   # December
]

# Directional production coefficients (relative to south-facing)
DIRECTION_COEFFICIENTS = {
    'N': 0.60,    # North
    'NE': 0.75,   # Northeast
    'E': 0.88,    # East
    'SE': 0.95,   # Southeast
    'S': 1.00,    # South (optimal)
    'SW': 0.95,   # Southwest
    'W': 0.88,    # West
    'NW': 0.75    # Northwest
}


def generate_monthly_production_chart(system_kwp: float, annual_production: float) -> bytes:
    """
    Generate a bar chart showing monthly energy production.

    Args:
        system_kwp: System size in kWp
        annual_production: Total annual production in kWh

    Returns:
        PNG image as bytes
    """
    # Calculate monthly production values
    monthly_production = [(annual_production / 12) * coef for coef in MONTHLY_COEFFICIENTS]

    # Create figure with increased height for better visibility
    fig, ax = plt.subplots(figsize=(10, 5.5))
    fig.patch.set_facecolor('white')

    # Create bars with 3D-like gradient effect
    bars = ax.bar(range(12), monthly_production,
                   color='#00358A',
                   edgecolor='#1a4d8f',
                   linewidth=1.5,
                   width=0.75,
                   zorder=3)

    # Add 3D depth effect with shadow bars
    shadow_offset = 0.08
    ax.bar(range(12), monthly_production,
           color='#001d3d',
           alpha=0.15,
           width=0.75,
           bottom=-max(monthly_production)*0.02,
           zorder=1)

    # Add gradient-like effect by overlaying lighter bars
    for i, bar in enumerate(bars):
        # Create gradient effect
        height = bar.get_height()
        gradient = mpatches.Rectangle(
            (bar.get_x(), height * 0.6),
            bar.get_width(),
            height * 0.4,
            facecolor='#4a7bc8',
            edgecolor='none',
            alpha=0.3,
            zorder=4
        )
        ax.add_patch(gradient)

    # Customize appearance - professional fonts with proper RTL text
    ax.set_xlabel(reshape_text_for_chart('חודש'), fontsize=10, fontweight='700', labelpad=10, color='#2d3748')
    ax.set_ylabel(reshape_text_for_chart('ייצור (קוט״ש)'), fontsize=10, fontweight='700', labelpad=10, color='#2d3748')

    # Title with proper RTL formatting
    title_text = f'ייצור סולארי חודשי - מערכת {system_kwp} קוט״ש'
    ax.set_title(reshape_text_for_chart(title_text),
                 fontsize=12, fontweight='bold', pad=15, color='#00358A')

    # Set x-axis labels (months) with proper RTL text
    hebrew_months_display = [reshape_text_for_chart(month) for month in HEBREW_MONTHS_RAW]
    ax.set_xticks(range(12))
    ax.set_xticklabels(hebrew_months_display, rotation=45, ha='right', fontsize=9, fontweight='500')

    # Add professional grid
    ax.grid(axis='y', alpha=0.15, linestyle='--', linewidth=0.8, color='#94a3b8', zorder=0)
    ax.set_axisbelow(True)

    # Format y-axis with thousands separator
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
    ax.tick_params(axis='both', labelsize=9, colors='#475569', width=1.2)

    # Add total annual production annotation with proper RTL text
    total_kwh = sum(monthly_production)
    annotation_text = f'סה״כ: {total_kwh:,.0f} קוט״ש/שנה'
    ax.text(0.98, 0.97, reshape_text_for_chart(annotation_text),
            transform=ax.transAxes, fontsize=9, fontweight='700',
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round,pad=0.6', facecolor='#f1f5f9',
                     edgecolor='#cbd5e0', linewidth=1.5, alpha=0.95))

    # Add subtle background
    ax.set_facecolor('#fafbfc')

    # Style spines
    for spine in ax.spines.values():
        spine.set_edgecolor('#cbd5e0')
        spine.set_linewidth(1.2)

    # Tight layout
    plt.tight_layout()

    # Save to bytes with higher DPI for better quality
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=180, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def generate_directional_production_chart(system_kwp: float, annual_production: float) -> bytes:
    """
    Generate a compass-style chart showing production by roof direction.

    Args:
        system_kwp: System size in kWp
        annual_production: Total annual production in kWh (assumes south-facing)

    Returns:
        PNG image as bytes
    """
    # Create figure
    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection='polar'))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('#fafbfc')

    # Calculate production for each direction
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    angles = np.linspace(0, 2 * np.pi, len(directions), endpoint=False)

    # Production values (relative to south-facing)
    production_values = [annual_production * DIRECTION_COEFFICIENTS[d] for d in directions]

    # Close the plot (connect last point to first)
    angles = np.concatenate((angles, [angles[0]]))
    production_values.append(production_values[0])

    # Add 3D depth effect - shadow layer beneath main plot
    shadow_values = [v * 0.95 for v in production_values]
    ax.fill(angles, shadow_values, alpha=0.08, color='#001d3d', zorder=1)
    ax.plot(angles, shadow_values, linewidth=1, color='#001d3d', alpha=0.15, zorder=1)

    # Add gradient-like layers for depth (multiple fills with decreasing alpha)
    for i, alpha_val in enumerate([0.15, 0.25, 0.35]):
        layer_values = [v * (0.4 + i * 0.2) for v in production_values]
        ax.fill(angles, layer_values, alpha=alpha_val, color='#00358A', zorder=2 + i)

    # Main plot with professional styling
    ax.plot(angles, production_values, 'o-', linewidth=3, color='#00358A',
            markersize=10, markeredgecolor='#1a4d8f', markeredgewidth=2,
            zorder=5, label='Production')

    # Main fill with gradient effect
    ax.fill(angles, production_values, alpha=0.3, color='#4a7bc8', zorder=4)

    # Set direction labels with better styling
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(directions, fontsize=13, fontweight='bold', color='#2d3748')

    # Set radial labels with professional formatting
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1000)}k'))
    ax.tick_params(axis='y', labelsize=10, colors='#4a5568')

    # Add professional grid
    ax.grid(True, linestyle='--', alpha=0.3, linewidth=1, color='#94a3b8')

    # Set radial axis limits for better appearance
    ax.set_ylim(0, max(production_values) * 1.1)

    # Title with brand color and proper RTL text
    title_text = f'ייצור שנתי לפי כיוון גג\nמערכת {system_kwp} קוט״ש'
    ax.set_title(reshape_text_for_chart(title_text),
                 fontsize=14, fontweight='bold', pad=20, y=1.08, color='#00358A')

    # Add center annotation with brand styling and proper RTL text
    center_text = f'דרום\n{int(annual_production):,}\nקוט״ש/שנה'
    ax.text(0, 0, reshape_text_for_chart(center_text),
            ha='center', va='center', fontsize=11, fontweight='bold',
            color='#2d3748',
            bbox=dict(boxstyle='round,pad=0.8', facecolor='#f1f5f9',
                     edgecolor='#00358A', linewidth=2, alpha=0.95))

    # Save to bytes with higher DPI
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=180, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()


def generate_payback_chart(price: float, annual_revenue: float, years: int = 25) -> bytes:
    """
    Generate a line chart showing cumulative savings over time with payback period.

    Args:
        price: Initial system cost in ILS
        annual_revenue: Annual revenue/savings in ILS
        years: Number of years to project (default 25)

    Returns:
        PNG image as bytes
    """
    # Calculate cumulative savings
    year_range = np.arange(0, years + 1)
    cumulative_savings = annual_revenue * year_range - price

    # Calculate payback period
    payback_years = price / annual_revenue if annual_revenue > 0 else 0

    # Create figure - more compact
    fig, ax = plt.subplots(figsize=(10, 4.5))
    fig.patch.set_facecolor('white')

    # Plot cumulative savings - thinner line, smaller markers
    ax.plot(year_range, cumulative_savings, linewidth=2, color='#00358A', marker='o', markersize=3)

    # Fill area below zero (investment period) in red
    ax.fill_between(year_range, cumulative_savings, 0,
                     where=(cumulative_savings <= 0),
                     color='#ff4d4f', alpha=0.15, interpolate=True)

    # Fill area above zero (profit period) in purple
    ax.fill_between(year_range, cumulative_savings, 0,
                     where=(cumulative_savings >= 0),
                     color='#00358A', alpha=0.15, interpolate=True)

    # Add zero line
    ax.axhline(y=0, color='#4a5568', linestyle='-', linewidth=1, alpha=0.4)

    # Mark payback point
    if 0 < payback_years <= years:
        payback_value = annual_revenue * payback_years - price
        ax.plot(payback_years, payback_value, 'r*', markersize=15,
                label=f'Payback: {payback_years:.1f} years', zorder=5)
        ax.axvline(x=payback_years, color='#ef5350', linestyle='--', linewidth=1.2, alpha=0.6)

        # Add annotation - smaller, more subtle with proper RTL text
        annotation_text = f'נקודת איזון\n{payback_years:.1f} שנים'
        ax.annotate(reshape_text_for_chart(annotation_text),
                   xy=(payback_years, 0), xytext=(payback_years + 2, price * 0.3),
                   fontsize=8, fontweight='600',
                   arrowprops=dict(arrowstyle='->', color='#ef5350', lw=1.5),
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='#fff3e0', edgecolor='#ef5350', alpha=0.8))

    # Labels and title - smaller, professional fonts with proper RTL text
    ax.set_xlabel(reshape_text_for_chart('שנים'), fontsize=9, fontweight='600', labelpad=8, color='#4a5568')
    ax.set_ylabel(reshape_text_for_chart('חיסכון מצטבר (₪)'), fontsize=9, fontweight='600', labelpad=8, color='#4a5568')
    ax.set_title(reshape_text_for_chart('תקופת החזר השקעה וחיסכון מצטבר'),
                 fontsize=10, fontweight='bold', pad=12, color='#2d3748')

    # Format y-axis with currency
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₪{int(x/1000)}k' if abs(x) >= 1000 else f'₪{int(x)}'))
    ax.tick_params(axis='both', labelsize=8, colors='#4a5568')

    # Grid - lighter
    ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5, color='#cbd5e0')
    ax.set_axisbelow(True)

    # Add legend with final savings - smaller, more subtle with proper RTL text
    final_savings = cumulative_savings[-1]
    legend_text = f'חיסכון כולל ({years} שנים): ₪{final_savings:,.0f}'
    ax.text(0.98, 0.02, reshape_text_for_chart(legend_text),
            transform=ax.transAxes, fontsize=8, fontweight='600',
            verticalalignment='bottom', horizontalalignment='right',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#f7fafc', edgecolor='#cbd5e0', alpha=0.9))

    # Tight layout
    plt.tight_layout()

    # Save to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
    buf.seek(0)
    plt.close(fig)

    return buf.getvalue()
