"""
Phase 3: Sun Position and Shadow Analysis Module

Calculates sun position, shadow patterns, and solar potential for roof analysis.
Uses astronomical algorithms to determine sun azimuth and elevation based on
location and time.

Key Features:
- Solar position calculation (azimuth, elevation)
- Shadow length and direction analysis
- Optimal sun hours calculation
- Solar potential estimation based on roof orientation
- Seasonal variation analysis

All calculations use FREE algorithms - no external API required.
"""

import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import logging

logger = logging.getLogger(__name__)

# Constants
EARTH_AXIAL_TILT = 23.44  # degrees

def _to_float(value) -> float:
    """Coerce numeric inputs (including Decimal) to float for math operations."""
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Expected numeric value, got {value!r}") from exc


def calculate_julian_day(dt: datetime) -> float:
    """
    Calculate Julian Day Number for a given datetime.
    Used as basis for solar position calculations.
    """
    year = dt.year
    month = dt.month
    day = dt.day + dt.hour / 24.0 + dt.minute / 1440.0 + dt.second / 86400.0

    if month <= 2:
        year -= 1
        month += 12

    A = int(year / 100)
    B = 2 - A + int(A / 4)

    jd = int(365.25 * (year + 4716)) + int(30.6001 * (month + 1)) + day + B - 1524.5
    return jd


def calculate_sun_position(latitude: float, longitude: float,
                           dt: datetime = None, timezone_offset: float = 2.0) -> Dict:
    """
    Calculate sun position (azimuth and elevation) for a given location and time.

    Uses simplified astronomical algorithms accurate to within ~1 degree.

    Args:
        latitude: Latitude in degrees (-90 to 90)
        longitude: Longitude in degrees (-180 to 180)
        dt: Datetime for calculation (default: now)
        timezone_offset: Hours offset from UTC (default: 2 for Israel)

    Returns:
        Dictionary with:
        - azimuth: Sun azimuth in degrees (0=North, 90=East, 180=South, 270=West)
        - elevation: Sun elevation in degrees (0=horizon, 90=zenith)
        - is_daytime: Boolean indicating if sun is above horizon
        - sunrise: Approximate sunrise time
        - sunset: Approximate sunset time
        - solar_noon: Time when sun is highest
    """
    if dt is None:
        dt = datetime.now()

    latitude = _to_float(latitude)
    longitude = _to_float(longitude)
    timezone_offset = _to_float(timezone_offset)

    # Convert to UTC for calculations
    utc_dt = dt - timedelta(hours=timezone_offset)

    # Calculate Julian Day
    jd = calculate_julian_day(utc_dt)

    # Julian Century
    jc = (jd - 2451545.0) / 36525.0

    # Geometric Mean Longitude of Sun (degrees)
    geom_mean_long = (280.46646 + jc * (36000.76983 + 0.0003032 * jc)) % 360

    # Geometric Mean Anomaly of Sun (degrees)
    geom_mean_anom = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)

    # Eccentricity of Earth's Orbit
    eccent = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)

    # Sun's Equation of Center
    sin_anom = math.sin(math.radians(geom_mean_anom))
    sin_2anom = math.sin(math.radians(2 * geom_mean_anom))
    sin_3anom = math.sin(math.radians(3 * geom_mean_anom))

    sun_eq_center = sin_anom * (1.914602 - jc * (0.004817 + 0.000014 * jc)) + \
                    sin_2anom * (0.019993 - 0.000101 * jc) + \
                    sin_3anom * 0.000289

    # Sun's True Longitude
    sun_true_long = geom_mean_long + sun_eq_center

    # Sun's Apparent Longitude
    omega = 125.04 - 1934.136 * jc
    sun_app_long = sun_true_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))

    # Mean Obliquity of the Ecliptic
    mean_obliq = 23 + (26 + ((21.448 - jc * (46.8150 + jc * (0.00059 - jc * 0.001813)))) / 60) / 60

    # Corrected Obliquity
    obliq_corr = mean_obliq + 0.00256 * math.cos(math.radians(omega))

    # Sun's Declination
    sun_declin = math.degrees(math.asin(
        math.sin(math.radians(obliq_corr)) * math.sin(math.radians(sun_app_long))
    ))

    # Equation of Time (minutes)
    var_y = math.tan(math.radians(obliq_corr / 2)) ** 2
    eq_of_time = 4 * math.degrees(
        var_y * math.sin(2 * math.radians(geom_mean_long)) -
        2 * eccent * math.sin(math.radians(geom_mean_anom)) +
        4 * eccent * var_y * math.sin(math.radians(geom_mean_anom)) * math.cos(2 * math.radians(geom_mean_long)) -
        0.5 * var_y ** 2 * math.sin(4 * math.radians(geom_mean_long)) -
        1.25 * eccent ** 2 * math.sin(2 * math.radians(geom_mean_anom))
    )

    # Hour Angle Sunrise (degrees)
    lat_rad = math.radians(latitude)
    declin_rad = math.radians(sun_declin)

    # Check for polar day/night
    cos_ha = -math.tan(lat_rad) * math.tan(declin_rad)

    if cos_ha > 1:
        # Polar night - sun never rises
        ha_sunrise = 0
        sunrise_time = None
        sunset_time = None
    elif cos_ha < -1:
        # Polar day - sun never sets
        ha_sunrise = 180
        sunrise_time = None
        sunset_time = None
    else:
        ha_sunrise = math.degrees(math.acos(cos_ha))

        # Solar Noon (LST)
        solar_noon_lst = (720 - 4 * longitude - eq_of_time + timezone_offset * 60) / 60

        # Sunrise and Sunset times
        sunrise_decimal = solar_noon_lst - ha_sunrise * 4 / 60
        sunset_decimal = solar_noon_lst + ha_sunrise * 4 / 60

        sunrise_time = f"{int(sunrise_decimal):02d}:{int((sunrise_decimal % 1) * 60):02d}"
        sunset_time = f"{int(sunset_decimal):02d}:{int((sunset_decimal % 1) * 60):02d}"

    # Calculate current hour angle
    time_decimal = dt.hour + dt.minute / 60.0 + dt.second / 3600.0
    solar_noon_decimal = (720 - 4 * longitude - eq_of_time + timezone_offset * 60) / 60
    hour_angle = (time_decimal - solar_noon_decimal) * 15  # 15 degrees per hour

    # Solar Elevation Angle
    sin_elevation = math.sin(lat_rad) * math.sin(declin_rad) + \
                    math.cos(lat_rad) * math.cos(declin_rad) * math.cos(math.radians(hour_angle))
    elevation = math.degrees(math.asin(max(-1, min(1, sin_elevation))))

    # Solar Azimuth Angle
    cos_azimuth = (math.sin(declin_rad) - math.sin(lat_rad) * math.sin(math.radians(elevation))) / \
                  (math.cos(lat_rad) * math.cos(math.radians(elevation)))
    cos_azimuth = max(-1, min(1, cos_azimuth))  # Clamp to valid range

    azimuth = math.degrees(math.acos(cos_azimuth))

    # Adjust azimuth based on hour angle (morning vs afternoon)
    if hour_angle > 0:
        azimuth = 360 - azimuth

    # Solar noon time
    solar_noon_time = f"{int(solar_noon_decimal):02d}:{int((solar_noon_decimal % 1) * 60):02d}"

    return {
        'azimuth': round(azimuth, 2),
        'elevation': round(elevation, 2),
        'is_daytime': elevation > 0,
        'sunrise': sunrise_time,
        'sunset': sunset_time,
        'solar_noon': solar_noon_time,
        'declination': round(sun_declin, 2),
        'hour_angle': round(hour_angle, 2)
    }


def calculate_shadow_length(object_height: float, sun_elevation: float) -> float:
    """
    Calculate shadow length for an object given sun elevation.

    Args:
        object_height: Height of object in meters
        sun_elevation: Sun elevation angle in degrees

    Returns:
        Shadow length in meters (0 if sun is below horizon)
    """
    if sun_elevation <= 0:
        return float('inf')  # No direct sunlight

    return object_height / math.tan(math.radians(sun_elevation))


def calculate_shadow_direction(sun_azimuth: float) -> float:
    """
    Calculate shadow direction based on sun azimuth.
    Shadow falls opposite to sun direction.

    Args:
        sun_azimuth: Sun azimuth in degrees (0=North)

    Returns:
        Shadow direction in degrees (0=North)
    """
    return (sun_azimuth + 180) % 360


def analyze_daily_shadows(latitude: float, longitude: float,
                         date: datetime = None,
                         obstruction_height: float = 0,
                         timezone_offset: float = 2.0) -> Dict:
    """
    Analyze shadow patterns throughout a day for a location.

    Args:
        latitude: Location latitude
        longitude: Location longitude
        date: Date to analyze (default: today)
        obstruction_height: Height of nearby obstructions in meters
        timezone_offset: Hours offset from UTC

    Returns:
        Dictionary with hourly shadow analysis and summary statistics
    """
    latitude = _to_float(latitude)
    longitude = _to_float(longitude)
    obstruction_height = _to_float(obstruction_height) if obstruction_height is not None else 0.0
    timezone_offset = _to_float(timezone_offset)

    if date is None:
        date = datetime.now().replace(hour=0, minute=0, second=0)

    hourly_data = []
    sun_hours = 0
    max_elevation = 0

    for hour in range(5, 21):  # 5 AM to 8 PM
        dt = date.replace(hour=hour, minute=0)
        sun_pos = calculate_sun_position(latitude, longitude, dt, timezone_offset)

        shadow_length = None
        shadow_direction = None

        if sun_pos['elevation'] > 0:
            sun_hours += 1
            max_elevation = max(max_elevation, sun_pos['elevation'])

            if obstruction_height > 0:
                shadow_length = calculate_shadow_length(obstruction_height, sun_pos['elevation'])
                shadow_direction = calculate_shadow_direction(sun_pos['azimuth'])

        hourly_data.append({
            'hour': hour,
            'time': f"{hour:02d}:00",
            'azimuth': sun_pos['azimuth'],
            'elevation': sun_pos['elevation'],
            'is_daytime': sun_pos['is_daytime'],
            'shadow_length': round(shadow_length, 2) if shadow_length else None,
            'shadow_direction': round(shadow_direction, 2) if shadow_direction else None
        })

    # Get sunrise/sunset for the day
    noon_pos = calculate_sun_position(latitude, longitude, date.replace(hour=12), timezone_offset)

    return {
        'date': date.strftime('%Y-%m-%d'),
        'location': {'latitude': latitude, 'longitude': longitude},
        'sunrise': noon_pos['sunrise'],
        'sunset': noon_pos['sunset'],
        'solar_noon': noon_pos['solar_noon'],
        'daylight_hours': sun_hours,
        'max_elevation': round(max_elevation, 2),
        'hourly_data': hourly_data
    }


def calculate_solar_potential(latitude: float, longitude: float,
                             roof_azimuth: float, roof_tilt: float = 0,
                             timezone_offset: float = 2.0) -> Dict:
    """
    Calculate solar potential for a roof based on its orientation.

    Estimates annual solar energy potential considering:
    - Roof orientation vs optimal (south-facing in northern hemisphere)
    - Seasonal variation
    - Average sun hours

    Args:
        latitude: Location latitude
        longitude: Location longitude
        roof_azimuth: Roof facing direction (0=North, 180=South)
        roof_tilt: Roof tilt angle in degrees (0=flat)
        timezone_offset: Hours offset from UTC

    Returns:
        Dictionary with solar potential analysis
    """
    latitude = _to_float(latitude)
    longitude = _to_float(longitude)
    roof_azimuth = _to_float(roof_azimuth)
    roof_tilt = _to_float(roof_tilt) if roof_tilt is not None else 0.0
    timezone_offset = _to_float(timezone_offset)

    # Optimal azimuth (south in northern hemisphere, north in southern)
    optimal_azimuth = 180 if latitude >= 0 else 0

    # Calculate azimuth deviation penalty
    azimuth_diff = abs(roof_azimuth - optimal_azimuth)
    if azimuth_diff > 180:
        azimuth_diff = 360 - azimuth_diff

    # Efficiency based on azimuth (100% at optimal, decreasing with deviation)
    # Loses about 25% at 90 degrees off optimal
    azimuth_efficiency = 100 - (azimuth_diff / 180) * 50

    # Calculate seasonal averages
    seasonal_data = []
    total_annual_hours = 0

    # Sample 4 representative days (equinoxes and solstices)
    sample_dates = [
        datetime(2024, 3, 21),   # Spring equinox
        datetime(2024, 6, 21),   # Summer solstice
        datetime(2024, 9, 21),   # Fall equinox
        datetime(2024, 12, 21),  # Winter solstice
    ]

    season_names = ['אביב', 'קיץ', 'סתיו', 'חורף']

    for i, date in enumerate(sample_dates):
        daily = analyze_daily_shadows(latitude, longitude, date, 0, timezone_offset)
        seasonal_data.append({
            'season': season_names[i],
            'date': date.strftime('%Y-%m-%d'),
            'daylight_hours': daily['daylight_hours'],
            'max_elevation': daily['max_elevation'],
            'sunrise': daily['sunrise'],
            'sunset': daily['sunset']
        })
        total_annual_hours += daily['daylight_hours'] * 91.25  # ~91 days per season

    # Estimate annual sun hours (accounting for weather - ~70% clear days in Israel)
    estimated_clear_days = 0.70
    annual_sun_hours = total_annual_hours * estimated_clear_days

    # Optimal tilt angle (approximately latitude for fixed panels)
    optimal_tilt = abs(latitude)
    tilt_diff = abs(roof_tilt - optimal_tilt)
    tilt_efficiency = 100 - (tilt_diff / 90) * 30  # Loses ~30% at 90 degrees off

    # Combined efficiency
    overall_efficiency = (azimuth_efficiency * tilt_efficiency) / 100

    # Determine orientation quality
    if azimuth_efficiency >= 90:
        orientation_quality = 'מצוין'
        orientation_quality_en = 'Excellent'
    elif azimuth_efficiency >= 75:
        orientation_quality = 'טוב מאוד'
        orientation_quality_en = 'Very Good'
    elif azimuth_efficiency >= 60:
        orientation_quality = 'טוב'
        orientation_quality_en = 'Good'
    elif azimuth_efficiency >= 45:
        orientation_quality = 'סביר'
        orientation_quality_en = 'Fair'
    else:
        orientation_quality = 'לא אופטימלי'
        orientation_quality_en = 'Not Optimal'

    # Direction name in Hebrew
    direction_names = {
        (337.5, 360): 'צפון',
        (0, 22.5): 'צפון',
        (22.5, 67.5): 'צפון-מזרח',
        (67.5, 112.5): 'מזרח',
        (112.5, 157.5): 'דרום-מזרח',
        (157.5, 202.5): 'דרום',
        (202.5, 247.5): 'דרום-מערב',
        (247.5, 292.5): 'מערב',
        (292.5, 337.5): 'צפון-מערב'
    }

    roof_direction = 'לא ידוע'
    for (min_az, max_az), direction in direction_names.items():
        if min_az <= roof_azimuth < max_az:
            roof_direction = direction
            break

    return {
        'roof_azimuth': roof_azimuth,
        'roof_direction': roof_direction,
        'roof_tilt': roof_tilt,
        'optimal_azimuth': optimal_azimuth,
        'optimal_tilt': round(optimal_tilt, 1),
        'azimuth_deviation': round(azimuth_diff, 1),
        'azimuth_efficiency': round(azimuth_efficiency, 1),
        'tilt_efficiency': round(tilt_efficiency, 1),
        'overall_efficiency': round(overall_efficiency, 1),
        'orientation_quality': orientation_quality,
        'orientation_quality_en': orientation_quality_en,
        'annual_sun_hours': round(annual_sun_hours),
        'seasonal_data': seasonal_data,
        'recommendations': generate_recommendations(azimuth_diff, roof_azimuth, latitude)
    }


def generate_recommendations(azimuth_diff: float, roof_azimuth: float,
                            latitude: float) -> List[str]:
    """Generate recommendations based on roof orientation analysis."""
    recommendations = []

    if azimuth_diff <= 30:
        recommendations.append('כיוון הגג אופטימלי לייצור אנרגיה סולארית')
    elif azimuth_diff <= 60:
        recommendations.append('כיוון הגג טוב, עם ירידה קלה ביעילות')
    elif azimuth_diff <= 90:
        recommendations.append('שקול התקנת פאנלים בזווית מותאמת לפיצוי על כיוון הגג')
    else:
        recommendations.append('כיוון הגג פחות אופטימלי - שקול מערכת מעקב או פאנלים דו-צדדיים')

    # East/West facing roofs
    if 60 <= roof_azimuth <= 120 or 240 <= roof_azimuth <= 300:
        recommendations.append('גגות מזרח/מערב מייצרים יותר בבוקר/אחר הצהריים - מתאים לצריכה לא אחידה')

    # Latitude-specific recommendations
    if latitude > 30:
        recommendations.append('בקווי רוחב גבוהים, זווית הטיה גבוהה יותר משפרת ייצור בחורף')

    return recommendations


def get_current_sun_position(latitude: float, longitude: float,
                            timezone_offset: float = 2.0) -> Dict:
    """
    Get current sun position for a location.
    Convenience function for real-time display.
    """
    return calculate_sun_position(latitude, longitude, datetime.now(), timezone_offset)


def calculate_annual_irradiance_estimate(latitude: float, roof_azimuth: float,
                                        roof_tilt: float = 0) -> Dict:
    """
    Estimate annual solar irradiance for a roof.

    Uses simplified model based on latitude and orientation.
    Values are approximate and suitable for initial planning.

    Returns estimated kWh/m²/year
    """
    latitude = _to_float(latitude)
    roof_azimuth = _to_float(roof_azimuth)
    roof_tilt = _to_float(roof_tilt) if roof_tilt is not None else 0.0

    # Base irradiance by latitude (approximate values for clear sky)
    # Israel range: ~1800-2200 kWh/m²/year
    base_irradiance = 2000 - abs(latitude - 31) * 20  # Optimized for Israel (~31°N)

    # Get solar potential for efficiency factors
    potential = calculate_solar_potential(latitude, 0, roof_azimuth, roof_tilt)

    # Adjusted irradiance
    adjusted_irradiance = base_irradiance * (potential['overall_efficiency'] / 100)

    # Monthly breakdown (simplified)
    monthly_factors = [0.6, 0.7, 0.85, 1.0, 1.15, 1.2, 1.2, 1.15, 1.0, 0.85, 0.7, 0.6]
    monthly_avg = adjusted_irradiance / 12
    monthly_irradiance = [round(monthly_avg * factor) for factor in monthly_factors]

    return {
        'annual_kwh_per_m2': round(adjusted_irradiance),
        'monthly_kwh_per_m2': monthly_irradiance,
        'efficiency_factor': potential['overall_efficiency'],
        'base_irradiance': base_irradiance
    }


# Example usage and testing
if __name__ == "__main__":
    # Test with Tel Aviv coordinates
    lat, lon = 32.0853, 34.7818

    print("=== Current Sun Position (Tel Aviv) ===")
    current = get_current_sun_position(lat, lon)
    print(f"Azimuth: {current['azimuth']}°")
    print(f"Elevation: {current['elevation']}°")
    print(f"Sunrise: {current['sunrise']}")
    print(f"Sunset: {current['sunset']}")
    print(f"Solar Noon: {current['solar_noon']}")

    print("\n=== Daily Shadow Analysis ===")
    daily = analyze_daily_shadows(lat, lon, obstruction_height=3.0)
    print(f"Daylight hours: {daily['daylight_hours']}")
    print(f"Max elevation: {daily['max_elevation']}°")

    print("\n=== Solar Potential (South-facing roof) ===")
    potential = calculate_solar_potential(lat, lon, roof_azimuth=180)
    print(f"Orientation quality: {potential['orientation_quality']}")
    print(f"Overall efficiency: {potential['overall_efficiency']}%")
    print(f"Annual sun hours: {potential['annual_sun_hours']}")

    print("\n=== Solar Potential (East-facing roof) ===")
    potential_east = calculate_solar_potential(lat, lon, roof_azimuth=90)
    print(f"Orientation quality: {potential_east['orientation_quality']}")
    print(f"Overall efficiency: {potential_east['overall_efficiency']}%")

    print("\n=== Annual Irradiance Estimate ===")
    irradiance = calculate_annual_irradiance_estimate(lat, roof_azimuth=180)
    print(f"Annual: {irradiance['annual_kwh_per_m2']} kWh/m²")
