"""
Chart Generator for Solar Energy Quotation System
Generates production charts for PDF reports
"""
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend for server-side rendering
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Wedge, Circle
import numpy as np
import io
from PIL import Image

# Hebrew month names for chart
HEBREW_MONTHS = ['ינואר', 'פברואר', 'מרץ', 'אפריל', 'מאי', 'יוני',
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

    # Create figure with custom styling - more compact
    fig, ax = plt.subplots(figsize=(10, 4))
    fig.patch.set_facecolor('white')

    # Create bars with gradient color
    bars = ax.bar(range(12), monthly_production, color='#667eea',
                   edgecolor='#5568d3', linewidth=1, alpha=0.85, width=0.7)

    # Customize appearance - smaller, more professional fonts
    ax.set_xlabel('חודש', fontsize=9, fontweight='600', labelpad=8, color='#4a5568')
    ax.set_ylabel('ייצור (קוט״ש)', fontsize=9, fontweight='600', labelpad=8, color='#4a5568')
    ax.set_title(f'ייצור סולארי חודשי - מערכת {system_kwp} קוט״ש',
                 fontsize=10, fontweight='bold', pad=12, color='#2d3748')

    # Set x-axis labels (months) - smaller fonts
    ax.set_xticks(range(12))
    ax.set_xticklabels(HEBREW_MONTHS, rotation=45, ha='right', fontsize=8)

    # Add grid for readability - lighter
    ax.grid(axis='y', alpha=0.2, linestyle='--', linewidth=0.5, color='#cbd5e0')
    ax.set_axisbelow(True)

    # Add value labels on top of bars - smaller fonts
    for i, (bar, value) in enumerate(zip(bars, monthly_production)):
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{int(value):,}',
                ha='center', va='bottom', fontsize=7, fontweight='600', color='#4a5568')

    # Format y-axis with thousands separator
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x):,}'))
    ax.tick_params(axis='both', labelsize=8, colors='#4a5568')

    # Add total annual production annotation - more subtle
    total_kwh = sum(monthly_production)
    ax.text(0.98, 0.96, f'סה״כ: {total_kwh:,.0f} קוט״ש/שנה',
            transform=ax.transAxes, fontsize=8, fontweight='600',
            verticalalignment='top', horizontalalignment='right',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#f7fafc', edgecolor='#cbd5e0', alpha=0.9))

    # Tight layout
    plt.tight_layout()

    # Save to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
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

    # Calculate production for each direction
    directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
    angles = np.linspace(0, 2 * np.pi, len(directions), endpoint=False)

    # Production values (relative to south-facing)
    production_values = [annual_production * DIRECTION_COEFFICIENTS[d] for d in directions]

    # Close the plot (connect last point to first)
    angles = np.concatenate((angles, [angles[0]]))
    production_values.append(production_values[0])

    # Plot
    ax.plot(angles, production_values, 'o-', linewidth=2, color='#52c41a', markersize=8)
    ax.fill(angles, production_values, alpha=0.25, color='#52c41a')

    # Set direction labels
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(directions, fontsize=12, fontweight='bold')

    # Set radial labels
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{int(x/1000)}k'))

    # Add grid
    ax.grid(True, linestyle='--', alpha=0.5)

    # Title
    ax.set_title(f'Annual Production by Roof Direction\n{system_kwp} kWp System',
                 fontsize=14, fontweight='bold', pad=20, y=1.08)

    # Add center annotation
    max_production = max(production_values)
    ax.text(0, 0, f'South:\n{int(annual_production):,}\nkWh/year',
            ha='center', va='center', fontsize=11, fontweight='bold',
            bbox=dict(boxstyle='round', facecolor='wheat', alpha=0.7))

    # Save to bytes
    buf = io.BytesIO()
    plt.savefig(buf, format='png', dpi=150, bbox_inches='tight', facecolor='white')
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
    ax.plot(year_range, cumulative_savings, linewidth=2, color='#667eea', marker='o', markersize=3)

    # Fill area below zero (investment period) in red
    ax.fill_between(year_range, cumulative_savings, 0,
                     where=(cumulative_savings <= 0),
                     color='#ff4d4f', alpha=0.15, interpolate=True)

    # Fill area above zero (profit period) in purple
    ax.fill_between(year_range, cumulative_savings, 0,
                     where=(cumulative_savings >= 0),
                     color='#667eea', alpha=0.15, interpolate=True)

    # Add zero line
    ax.axhline(y=0, color='#4a5568', linestyle='-', linewidth=1, alpha=0.4)

    # Mark payback point
    if 0 < payback_years <= years:
        payback_value = annual_revenue * payback_years - price
        ax.plot(payback_years, payback_value, 'r*', markersize=15,
                label=f'Payback: {payback_years:.1f} years', zorder=5)
        ax.axvline(x=payback_years, color='#ef5350', linestyle='--', linewidth=1.2, alpha=0.6)

        # Add annotation - smaller, more subtle
        ax.annotate(f'נקודת איזון\n{payback_years:.1f} שנים',
                   xy=(payback_years, 0), xytext=(payback_years + 2, price * 0.3),
                   fontsize=8, fontweight='600',
                   arrowprops=dict(arrowstyle='->', color='#ef5350', lw=1.5),
                   bbox=dict(boxstyle='round,pad=0.4', facecolor='#fff3e0', edgecolor='#ef5350', alpha=0.8))

    # Labels and title - smaller, professional fonts
    ax.set_xlabel('שנים', fontsize=9, fontweight='600', labelpad=8, color='#4a5568')
    ax.set_ylabel('חיסכון מצטבר (₪)', fontsize=9, fontweight='600', labelpad=8, color='#4a5568')
    ax.set_title(f'תקופת החזר השקעה וחיסכון מצטבר',
                 fontsize=10, fontweight='bold', pad=12, color='#2d3748')

    # Format y-axis with currency
    ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'₪{int(x/1000)}k' if abs(x) >= 1000 else f'₪{int(x)}'))
    ax.tick_params(axis='both', labelsize=8, colors='#4a5568')

    # Grid - lighter
    ax.grid(True, alpha=0.2, linestyle='--', linewidth=0.5, color='#cbd5e0')
    ax.set_axisbelow(True)

    # Add legend with final savings - smaller, more subtle
    final_savings = cumulative_savings[-1]
    ax.text(0.98, 0.02, f'חיסכון כולל ({years} שנים): ₪{final_savings:,.0f}',
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


# For testing
if __name__ == "__main__":
    # Test chart generation
    test_kwp = 15
    test_annual = 20400  # 15 kWp × 1360 kWh/kWp
    test_price = 61950   # 15 kWp × 4130 ILS/kWp
    test_revenue = 9792  # 20400 × 0.48 ILS/kWh

    print("Generating test charts...")

    # Generate monthly chart
    monthly_chart = generate_monthly_production_chart(test_kwp, test_annual)
    with open('test_monthly_chart.png', 'wb') as f:
        f.write(monthly_chart)
    print("[OK] Monthly chart saved to test_monthly_chart.png")

    # Generate directional chart
    directional_chart = generate_directional_production_chart(test_kwp, test_annual)
    with open('test_directional_chart.png', 'wb') as f:
        f.write(directional_chart)
    print("[OK] Directional chart saved to test_directional_chart.png")

    # Generate payback chart
    payback_chart = generate_payback_chart(test_price, test_revenue)
    with open('test_payback_chart.png', 'wb') as f:
        f.write(payback_chart)
    print("[OK] Payback chart saved to test_payback_chart.png")

    print("\nAll test charts generated successfully!")
