"""
Phase 4: Energy Production & Financial Calculations Module

Calculates annual energy production, savings, ROI, and environmental impact
for solar panel installations.

Key Features:
- Annual kWh production estimate
- Monthly production breakdown
- Financial savings calculation
- ROI and payback period
- CO2 offset estimation
- Electricity bill savings

All calculations use industry-standard formulas and Israel-specific data.
"""

from typing import Dict, List, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


def _to_float(value) -> float:
    """Coerce numeric inputs (including Decimal) to float for math operations."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected numeric value, got {value!r}") from exc


# Israel-specific constants
ISRAEL_ELECTRICITY_RATE = 0.55  # NIS per kWh (average 2024)
ISRAEL_FEED_IN_TARIFF = 0.40  # NIS per kWh sold back to grid
ISRAEL_AVG_SUNSHINE_HOURS = 3200  # Annual sunshine hours
ISRAEL_CO2_FACTOR = 0.527  # kg CO2 per kWh (Israel Electric Corp)

# System loss factors
DEFAULT_SYSTEM_LOSSES = {
    'inverter_efficiency': 0.96,      # 96% inverter efficiency
    'wiring_losses': 0.98,            # 2% wiring losses
    'soiling_losses': 0.97,           # 3% dust/dirt losses
    'temperature_losses': 0.92,       # 8% temperature derating (hot climate)
    'mismatch_losses': 0.98,          # 2% panel mismatch
    'availability': 0.99,             # 1% downtime
}

# Panel cost estimates (NIS)
PANEL_COST_PER_WATT = 2.5  # NIS per watt (installed)
INVERTER_COST_RATIO = 0.15  # 15% of panel cost
INSTALLATION_COST_RATIO = 0.20  # 20% of panel cost
PERMIT_AND_CONNECTION = 3000  # Fixed costs in NIS


def calculate_system_losses(custom_losses: Dict = None) -> float:
    """
    Calculate total system efficiency considering all losses.

    Returns:
        Combined efficiency factor (0-1)
    """
    losses = DEFAULT_SYSTEM_LOSSES.copy()
    if custom_losses:
        losses.update(custom_losses)

    total_efficiency = 1.0
    for factor in losses.values():
        total_efficiency *= factor

    return round(total_efficiency, 4)


def calculate_annual_production(
    system_power_kw: float,
    latitude: float,
    orientation_efficiency: float = 100,
    custom_losses: Dict = None
) -> Dict:
    """
    Calculate estimated annual energy production.

    Args:
        system_power_kw: Total system power in kW
        latitude: Location latitude for sunshine hours adjustment
        orientation_efficiency: Roof orientation efficiency (0-100%)
        custom_losses: Optional custom loss factors

    Returns:
        Dictionary with annual and monthly production estimates
    """
    system_power_kw = _to_float(system_power_kw)
    latitude = _to_float(latitude)
    orientation_efficiency = _to_float(orientation_efficiency)

    # Adjust sunshine hours based on latitude (Israel range: 29-33°N)
    # Southern Israel gets more sun
    lat_adjustment = 1.0 + (31 - latitude) * 0.01  # ~1% per degree from center
    adjusted_sunshine = ISRAEL_AVG_SUNSHINE_HOURS * max(0.9, min(1.1, lat_adjustment))

    # Peak sun hours (effective hours at 1000 W/m²)
    # Typically 4.5-5.5 hours/day in Israel
    peak_sun_hours_daily = adjusted_sunshine / 365

    # System efficiency
    system_efficiency = calculate_system_losses(custom_losses)

    # Orientation factor
    orientation_factor = orientation_efficiency / 100

    # Annual production formula:
    # kWh/year = System_kW × Peak_Sun_Hours × 365 × System_Efficiency × Orientation_Factor
    annual_kwh = (
        system_power_kw *
        peak_sun_hours_daily *
        365 *
        system_efficiency *
        orientation_factor
    )

    # Monthly breakdown (accounting for seasonal variation)
    monthly_factors = {
        'ינואר': 0.60,
        'פברואר': 0.70,
        'מרץ': 0.90,
        'אפריל': 1.05,
        'מאי': 1.15,
        'יוני': 1.25,
        'יולי': 1.30,
        'אוגוסט': 1.25,
        'ספטמבר': 1.10,
        'אוקטובר': 0.90,
        'נובמבר': 0.70,
        'דצמבר': 0.55,
    }

    monthly_avg = annual_kwh / 12
    monthly_production = {
        month: round(monthly_avg * factor)
        for month, factor in monthly_factors.items()
    }

    return {
        'annual_kwh': round(annual_kwh),
        'monthly_kwh': monthly_production,
        'daily_avg_kwh': round(annual_kwh / 365, 1),
        'peak_sun_hours': round(peak_sun_hours_daily, 1),
        'system_efficiency': round(system_efficiency * 100, 1),
        'orientation_factor': round(orientation_factor * 100, 1)
    }


def calculate_financial_estimates(
    system_power_kw: float,
    annual_kwh: float,
    electricity_rate: float = ISRAEL_ELECTRICITY_RATE,
    feed_in_tariff: float = ISRAEL_FEED_IN_TARIFF,
    self_consumption_ratio: float = 0.70
) -> Dict:
    """
    Calculate financial estimates for solar installation.

    Args:
        system_power_kw: Total system power in kW
        annual_kwh: Annual energy production in kWh
        electricity_rate: Cost per kWh in NIS
        feed_in_tariff: Rate for selling excess to grid
        self_consumption_ratio: Percentage of energy used on-site (0-1)

    Returns:
        Dictionary with financial calculations
    """
    system_power_kw = _to_float(system_power_kw)
    annual_kwh = _to_float(annual_kwh)
    electricity_rate = _to_float(electricity_rate)
    feed_in_tariff = _to_float(feed_in_tariff)
    self_consumption_ratio = _to_float(self_consumption_ratio)

    system_watts = system_power_kw * 1000

    # System cost estimate
    panel_cost = system_watts * PANEL_COST_PER_WATT
    inverter_cost = panel_cost * INVERTER_COST_RATIO
    installation_cost = panel_cost * INSTALLATION_COST_RATIO
    total_cost = panel_cost + inverter_cost + installation_cost + PERMIT_AND_CONNECTION

    # Annual savings calculation
    self_consumed_kwh = annual_kwh * self_consumption_ratio
    exported_kwh = annual_kwh * (1 - self_consumption_ratio)

    savings_from_self_consumption = self_consumed_kwh * electricity_rate
    income_from_export = exported_kwh * feed_in_tariff
    total_annual_savings = savings_from_self_consumption + income_from_export

    # ROI calculations
    simple_payback_years = total_cost / total_annual_savings if total_annual_savings > 0 else 0

    # 25-year financial projection (typical panel warranty)
    years = 25
    degradation_rate = 0.005  # 0.5% annual degradation
    electricity_inflation = 0.03  # 3% annual increase

    cumulative_savings = 0
    yearly_breakdown = []

    for year in range(1, years + 1):
        year_production = annual_kwh * ((1 - degradation_rate) ** (year - 1))
        year_rate = electricity_rate * ((1 + electricity_inflation) ** (year - 1))
        year_tariff = feed_in_tariff * ((1 + electricity_inflation) ** (year - 1))

        year_self_consumed = year_production * self_consumption_ratio
        year_exported = year_production * (1 - self_consumption_ratio)

        year_savings = (year_self_consumed * year_rate) + (year_exported * year_tariff)
        cumulative_savings += year_savings

        yearly_breakdown.append({
            'year': year,
            'production_kwh': round(year_production),
            'savings_nis': round(year_savings),
            'cumulative_nis': round(cumulative_savings)
        })

    # Find break-even year
    break_even_year = None
    for year_data in yearly_breakdown:
        if year_data['cumulative_nis'] >= total_cost:
            break_even_year = year_data['year']
            break

    # Total ROI over 25 years
    total_roi = ((cumulative_savings - total_cost) / total_cost) * 100 if total_cost > 0 else 0

    return {
        'system_cost': {
            'panels': round(panel_cost),
            'inverter': round(inverter_cost),
            'installation': round(installation_cost),
            'permits': PERMIT_AND_CONNECTION,
            'total': round(total_cost)
        },
        'annual_savings': {
            'self_consumption': round(savings_from_self_consumption),
            'grid_export': round(income_from_export),
            'total': round(total_annual_savings)
        },
        'payback_years': round(simple_payback_years, 1),
        'break_even_year': break_even_year,
        'roi_25_years': round(total_roi, 1),
        'total_savings_25_years': round(cumulative_savings),
        'yearly_projection': yearly_breakdown[:5],  # First 5 years only for response size
        'assumptions': {
            'electricity_rate_nis': electricity_rate,
            'feed_in_tariff_nis': feed_in_tariff,
            'self_consumption_ratio': self_consumption_ratio,
            'annual_degradation': degradation_rate,
            'electricity_inflation': electricity_inflation
        }
    }


def calculate_environmental_impact(annual_kwh: float) -> Dict:
    """
    Calculate environmental benefits of solar installation.

    Args:
        annual_kwh: Annual energy production in kWh

    Returns:
        Dictionary with environmental impact metrics
    """
    annual_kwh = _to_float(annual_kwh)

    # CO2 offset
    annual_co2_kg = annual_kwh * ISRAEL_CO2_FACTOR
    lifetime_co2_tonnes = (annual_co2_kg * 25) / 1000  # 25 years, convert to tonnes

    # Equivalencies (approximate)
    trees_equivalent = annual_co2_kg / 21  # ~21 kg CO2 absorbed per tree per year
    car_km_equivalent = annual_co2_kg / 0.12  # ~120g CO2 per km for average car
    flights_equivalent = annual_co2_kg / 250  # ~250 kg CO2 per short-haul flight

    return {
        'annual_co2_offset_kg': round(annual_co2_kg),
        'lifetime_co2_offset_tonnes': round(lifetime_co2_tonnes, 1),
        'equivalencies': {
            'trees_planted': round(trees_equivalent),
            'car_km_avoided': round(car_km_equivalent),
            'flights_avoided': round(flights_equivalent, 1)
        },
        'co2_factor_kg_per_kwh': ISRAEL_CO2_FACTOR
    }


def calculate_electrical_stringing(
    panel_count: int,
    panel_power_w: int = 400,
    panel_voc: float = 49.5,  # Open circuit voltage
    panel_vmp: float = 41.5,  # Voltage at max power
    panel_isc: float = 10.5,  # Short circuit current
    panel_imp: float = 9.6,   # Current at max power
    inverter_max_voltage: float = 600,  # Max DC voltage
    inverter_min_voltage: float = 200,  # Min MPPT voltage
    inverter_max_current: float = 20,   # Max input current per MPPT
    mppt_count: int = 2,      # Number of MPPT inputs
    min_string_length: int = 6,
    max_string_length: int = 15
) -> Dict:
    """
    Calculate optimal electrical stringing configuration.

    Groups panels into strings for inverter connection, considering:
    - Voltage limits (min/max for MPPT operation)
    - Current limits per MPPT input
    - Balanced string lengths

    Args:
        panel_count: Total number of panels
        panel_power_w: Panel wattage
        panel_voc: Open circuit voltage (V)
        panel_vmp: Voltage at maximum power (V)
        panel_isc: Short circuit current (A)
        panel_imp: Current at maximum power (A)
        inverter_max_voltage: Maximum DC input voltage
        inverter_min_voltage: Minimum MPPT operating voltage
        inverter_max_current: Maximum current per MPPT
        mppt_count: Number of MPPT inputs on inverter
        min_string_length: Minimum panels per string
        max_string_length: Maximum panels per string

    Returns:
        Dictionary with stringing configuration
    """
    # Calculate voltage limits for string length
    # Account for temperature variations (+/- 15% from STC)
    voc_hot = panel_voc * 0.85   # Voltage decreases when hot
    voc_cold = panel_voc * 1.15  # Voltage increases when cold

    # Max string length based on cold Voc (highest voltage scenario)
    max_by_voltage = int(inverter_max_voltage / voc_cold)

    # Min string length based on hot Vmp (lowest voltage scenario)
    min_by_voltage = int(inverter_min_voltage / (panel_vmp * 0.85)) + 1

    # Clamp to reasonable range
    effective_min = max(min_string_length, min_by_voltage)
    effective_max = min(max_string_length, max_by_voltage)

    if effective_min > effective_max:
        # Voltage requirements conflict - use defaults
        effective_min = min_string_length
        effective_max = max_string_length

    # Calculate optimal string length for equal distribution
    strings = []
    remaining_panels = panel_count

    # Try to create balanced strings
    # Start with optimal length (middle of range)
    optimal_length = (effective_min + effective_max) // 2

    # Calculate number of strings needed
    num_strings = max(1, round(panel_count / optimal_length))

    # Adjust to fit MPPT constraints
    if num_strings > mppt_count * 2:  # Allow 2 strings per MPPT (parallel)
        num_strings = mppt_count * 2
        optimal_length = panel_count // num_strings

    # Create strings
    panels_per_string = panel_count // num_strings
    extra_panels = panel_count % num_strings

    for i in range(num_strings):
        string_length = panels_per_string + (1 if i < extra_panels else 0)
        if string_length > 0:
            strings.append({
                'string_id': i + 1,
                'panel_count': string_length,
                'voltage_voc': round(string_length * panel_voc, 1),
                'voltage_vmp': round(string_length * panel_vmp, 1),
                'power_w': string_length * panel_power_w,
                'mppt': (i % mppt_count) + 1
            })

    # Calculate totals
    total_dc_power = sum(s['power_w'] for s in strings)
    max_string_voc = max(s['voltage_voc'] for s in strings) if strings else 0

    # Assign strings to MPPTs
    mppt_assignments = {}
    for i in range(mppt_count):
        mppt_strings = [s for s in strings if s['mppt'] == i + 1]
        mppt_assignments[f'MPPT {i + 1}'] = {
            'strings': len(mppt_strings),
            'panels': sum(s['panel_count'] for s in mppt_strings),
            'power_w': sum(s['power_w'] for s in mppt_strings)
        }

    # Recommended inverter size (typically 90-110% of DC power)
    recommended_inverter_kw = round(total_dc_power / 1000 * 0.95, 1)

    return {
        'panel_count': panel_count,
        'string_count': len(strings),
        'strings': strings,
        'mppt_assignments': mppt_assignments,
        'total_dc_power_kw': round(total_dc_power / 1000, 2),
        'max_string_voltage': round(max_string_voc, 1),
        'recommended_inverter_kw': recommended_inverter_kw,
        'voltage_limits': {
            'min_string_length': effective_min,
            'max_string_length': effective_max,
            'panels_voc': panel_voc,
            'panels_vmp': panel_vmp
        },
        'warnings': _get_stringing_warnings(strings, inverter_max_voltage, inverter_max_current, panel_isc)
    }


def _get_stringing_warnings(strings: List[Dict], max_voltage: float,
                           max_current: float, panel_isc: float) -> List[str]:
    """Generate warnings for stringing configuration."""
    warnings = []

    for s in strings:
        if s['voltage_voc'] > max_voltage * 0.9:
            warnings.append(f"String {s['string_id']}: Voltage ({s['voltage_voc']}V) approaching inverter limit")

    # Check if parallel strings exceed current limit
    from collections import Counter
    mppt_string_counts = Counter(s['mppt'] for s in strings)
    for mppt, count in mppt_string_counts.items():
        parallel_current = panel_isc * count
        if parallel_current > max_current:
            warnings.append(f"MPPT {mppt}: Parallel current ({parallel_current:.1f}A) exceeds limit ({max_current}A)")

    return warnings


def calculate_complete_estimate(
    system_power_kw: float,
    panel_count: int,
    latitude: float,
    orientation_efficiency: float = 100,
    self_consumption_ratio: float = 0.70
) -> Dict:
    """
    Calculate complete energy and financial estimates.

    This is the main function that combines all calculations.

    Args:
        system_power_kw: Total system power in kW
        panel_count: Number of panels
        latitude: Location latitude
        orientation_efficiency: Roof orientation efficiency (0-100%)
        self_consumption_ratio: Ratio of energy used on-site

    Returns:
        Complete estimate dictionary
    """
    # Production estimate
    production = calculate_annual_production(
        system_power_kw, latitude, orientation_efficiency
    )

    # Financial estimate
    financial = calculate_financial_estimates(
        system_power_kw,
        production['annual_kwh'],
        self_consumption_ratio=self_consumption_ratio
    )

    # Environmental impact
    environmental = calculate_environmental_impact(production['annual_kwh'])

    return {
        'summary': {
            'system_power_kw': round(_to_float(system_power_kw), 2),
            'panel_count': panel_count,
            'annual_production_kwh': production['annual_kwh'],
            'annual_savings_nis': financial['annual_savings']['total'],
            'payback_years': financial['payback_years'],
            'co2_offset_kg': environmental['annual_co2_offset_kg']
        },
        'production': production,
        'financial': financial,
        'environmental': environmental,
        'generated_at': datetime.now().isoformat()
    }


# Example usage and testing
if __name__ == "__main__":
    # Test with example system
    result = calculate_complete_estimate(
        system_power_kw=6.4,  # 16 panels × 400W
        panel_count=16,
        latitude=32.0,
        orientation_efficiency=85,
        self_consumption_ratio=0.70
    )

    print("=== Energy Production Estimate ===")
    print(f"Annual Production: {result['production']['annual_kwh']} kWh")
    print(f"Daily Average: {result['production']['daily_avg_kwh']} kWh")
    print(f"System Efficiency: {result['production']['system_efficiency']}%")

    print("\n=== Financial Estimate ===")
    print(f"System Cost: ₪{result['financial']['system_cost']['total']:,}")
    print(f"Annual Savings: ₪{result['financial']['annual_savings']['total']:,}")
    print(f"Payback Period: {result['financial']['payback_years']} years")
    print(f"25-Year ROI: {result['financial']['roi_25_years']}%")

    print("\n=== Environmental Impact ===")
    print(f"Annual CO2 Offset: {result['environmental']['annual_co2_offset_kg']} kg")
    print(f"Equivalent Trees: {result['environmental']['equivalencies']['trees_planted']}")
