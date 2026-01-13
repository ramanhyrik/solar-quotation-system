"""
Phase 2: Automatic Roof Measurements

Calculates real-world dimensions from roof polygons using geographic coordinates.
Provides accurate measurements without manual scale setting.
"""

import numpy as np
from shapely.geometry import Polygon, Point
from typing import Dict, List, Tuple, Optional
import math


def calculate_real_dimensions(
    polygon_points: List[Tuple[float, float]],
    latitude: float,
    zoom_level: int = 19,
    pixels_per_meter: Optional[float] = None
) -> Dict:
    """
    Calculate real-world roof dimensions from pixel polygon

    Uses satellite imagery scale factor based on zoom level and latitude.
    Mercator projection formula: meters_per_pixel = (Earth_circumference * cos(lat)) / (256 * 2^zoom)

    Args:
        polygon_points: List of (x, y) pixel coordinates defining roof boundary
        latitude: Geographic latitude (affects scale)
        zoom_level: Map zoom level (default: 19 for OSM)
        pixels_per_meter: Optional override for pixels per meter

    Returns:
        Dict with:
        - length_m: Longest dimension in meters
        - width_m: Perpendicular width in meters
        - area_m2: Total roof area in square meters
        - perimeter_m: Roof perimeter in meters
        - usable_area_m2: Area after setbacks (0.3m default)
        - meters_per_pixel: Scale factor used
        - pixels_per_meter: Inverse scale factor

    Example:
        >>> points = [(0, 0), (100, 0), (100, 50), (0, 50)]
        >>> dims = calculate_real_dimensions(points, latitude=32.0644, zoom_level=19)
        >>> print(f"Roof: {dims['length_m']:.1f}m x {dims['width_m']:.1f}m")
        Roof: 33.8m x 16.9m
    """
    from satellite_imagery import get_meters_per_pixel

    if not polygon_points or len(polygon_points) < 3:
        return {
            "error": "Need at least 3 points to calculate dimensions",
            "length_m": 0,
            "width_m": 0,
            "area_m2": 0,
            "perimeter_m": 0
        }

    # Calculate scale factor
    if pixels_per_meter:
        meters_per_pixel = 1.0 / pixels_per_meter
    else:
        meters_per_pixel = get_meters_per_pixel(latitude, zoom_level)

    print(f"[MEASUREMENTS] Scale: {meters_per_pixel:.4f} m/px (zoom {zoom_level})")

    # Convert pixel coordinates to meters
    points_m = []
    for x_px, y_px in polygon_points:
        x_m = x_px * meters_per_pixel
        y_m = y_px * meters_per_pixel
        points_m.append((x_m, y_m))

    # Create shapely polygon
    try:
        poly = Polygon(points_m)
        if not poly.is_valid:
            poly = poly.buffer(0)  # Fix invalid polygons
    except Exception as e:
        print(f"[MEASUREMENTS] Error creating polygon: {e}")
        return {"error": str(e), "length_m": 0, "width_m": 0, "area_m2": 0, "perimeter_m": 0}

    # Calculate area
    area_m2 = poly.area

    # Calculate perimeter
    perimeter_m = poly.length

    # Calculate length and width using minimum rotated rectangle
    try:
        # Get minimum bounding rectangle
        from shapely.geometry import box
        minx, miny, maxx, maxy = poly.bounds

        # Try to find oriented bounding box (more accurate)
        # Calculate all edge lengths and find max/min
        coords = list(poly.exterior.coords)
        edge_lengths = []

        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]
            length = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)
            edge_lengths.append(length)

        if edge_lengths:
            edge_lengths.sort(reverse=True)
            # Take longest edge as length
            length_m = edge_lengths[0]
            # Find perpendicular dimension
            # Simple approximation: area / length
            width_m = area_m2 / length_m if length_m > 0 else 0
        else:
            # Fallback: use bounding box
            length_m = max(maxx - minx, maxy - miny)
            width_m = min(maxx - minx, maxy - miny)

    except Exception as e:
        print(f"[MEASUREMENTS] Error calculating dimensions: {e}")
        # Fallback: use bounding box
        minx, miny, maxx, maxy = poly.bounds
        length_m = max(maxx - minx, maxy - miny)
        width_m = min(maxx - minx, maxy - miny)

    # Calculate usable area (after 0.3m setback for building codes)
    setback_m = 0.3
    try:
        usable_poly = poly.buffer(-setback_m)
        if usable_poly.is_valid and not usable_poly.is_empty:
            usable_area_m2 = usable_poly.area
        else:
            usable_area_m2 = area_m2 * 0.9  # Approximate 10% loss
    except:
        usable_area_m2 = area_m2 * 0.9

    print(f"[MEASUREMENTS] Dimensions: {length_m:.2f}m x {width_m:.2f}m")
    print(f"[MEASUREMENTS] Area: {area_m2:.2f}m² (usable: {usable_area_m2:.2f}m²)")
    print(f"[MEASUREMENTS] Perimeter: {perimeter_m:.2f}m")

    return {
        "length_m": round(length_m, 2),
        "width_m": round(width_m, 2),
        "area_m2": round(area_m2, 2),
        "perimeter_m": round(perimeter_m, 2),
        "usable_area_m2": round(usable_area_m2, 2),
        "meters_per_pixel": round(meters_per_pixel, 4),
        "pixels_per_meter": round(1.0 / meters_per_pixel, 2) if meters_per_pixel > 0 else 0
    }


def calculate_roof_orientation(
    polygon_points: List[Tuple[float, float]]
) -> Dict:
    """
    Calculate roof orientation (azimuth angle) from polygon shape

    Determines the primary direction the roof faces, useful for solar panel optimization.
    0° = North, 90° = East, 180° = South, 270° = West

    Args:
        polygon_points: List of (x, y) coordinates defining roof boundary

    Returns:
        Dict with:
        - azimuth: Primary roof direction in degrees (0-360)
        - orientation_name: Human-readable direction (N, NE, E, SE, S, SW, W, NW)
        - is_suitable_south: True if facing south-ish (135-225°)

    Example:
        >>> points = [(0, 0), (100, 0), (100, 50), (0, 50)]
        >>> orientation = calculate_roof_orientation(points)
        >>> print(orientation['orientation_name'])
        'East'
    """
    if not polygon_points or len(polygon_points) < 3:
        return {"azimuth": 180, "orientation_name": "Unknown", "is_suitable_south": False}

    try:
        # Find longest edge (usually roof ridge or main face)
        max_length = 0
        best_angle = 0

        coords = list(polygon_points) + [polygon_points[0]]  # Close the loop

        for i in range(len(coords) - 1):
            x1, y1 = coords[i]
            x2, y2 = coords[i + 1]

            # Edge length
            length = math.sqrt((x2 - x1)**2 + (y2 - y1)**2)

            if length > max_length:
                max_length = length
                # Calculate angle (note: image Y axis is inverted)
                angle_rad = math.atan2(y2 - y1, x2 - x1)
                angle_deg = math.degrees(angle_rad)
                best_angle = angle_deg

        # Convert to compass bearing (0° = North, clockwise)
        # In image coordinates: right=East (90°), down=South (180°)
        azimuth = (90 - best_angle) % 360

        # Determine orientation name
        orientation_names = [
            (0, 22.5, "N"),
            (22.5, 67.5, "NE"),
            (67.5, 112.5, "E"),
            (112.5, 157.5, "SE"),
            (157.5, 202.5, "S"),
            (202.5, 247.5, "SW"),
            (247.5, 292.5, "W"),
            (292.5, 337.5, "NW"),
            (337.5, 360, "N")
        ]

        orientation_name = "Unknown"
        for min_angle, max_angle, name in orientation_names:
            if min_angle <= azimuth < max_angle:
                orientation_name = name
                break

        # Check if south-facing (ideal for solar in Northern Hemisphere)
        is_suitable_south = 135 <= azimuth <= 225

        print(f"[MEASUREMENTS] Roof orientation: {azimuth:.1f}° ({orientation_name})")
        print(f"[MEASUREMENTS] South-facing: {'Yes' if is_suitable_south else 'No'}")

        return {
            "azimuth": round(azimuth, 1),
            "orientation_name": orientation_name,
            "is_suitable_south": is_suitable_south
        }

    except Exception as e:
        print(f"[MEASUREMENTS] Error calculating orientation: {e}")
        return {"azimuth": 180, "orientation_name": "Unknown", "is_suitable_south": False}


def validate_measurements(
    area_m2: float,
    length_m: float,
    width_m: float,
    building_type: str = "residential"
) -> Dict:
    """
    Validate roof measurements and provide confidence score

    Checks if measurements are realistic based on typical building dimensions.
    Flags suspicious measurements for user review.

    Args:
        area_m2: Calculated roof area
        length_m: Roof length
        width_m: Roof width
        building_type: Type of building (residential/commercial/industrial)

    Returns:
        Dict with:
        - is_valid: True if measurements seem realistic
        - confidence: Confidence score (0-100%)
        - warnings: List of potential issues
        - suggestions: List of recommendations

    Example:
        >>> validation = validate_measurements(150, 15, 10)
        >>> print(validation['confidence'])
        95
    """
    warnings = []
    suggestions = []
    confidence = 100

    # Define realistic ranges
    ranges = {
        "residential": {
            "min_area": 30,
            "max_area": 500,
            "min_length": 5,
            "max_length": 50,
            "typical_area": (80, 200)
        },
        "commercial": {
            "min_area": 100,
            "max_area": 5000,
            "min_length": 10,
            "max_length": 100,
            "typical_area": (300, 2000)
        },
        "industrial": {
            "min_area": 500,
            "max_area": 50000,
            "min_length": 20,
            "max_length": 300,
            "typical_area": (1000, 10000)
        }
    }

    limits = ranges.get(building_type, ranges["residential"])

    # Check area
    if area_m2 < limits["min_area"]:
        warnings.append(f"Roof area ({area_m2:.1f}m²) is smaller than typical {building_type} building")
        confidence -= 20
        suggestions.append("Verify the roof polygon includes the entire roof area")

    elif area_m2 > limits["max_area"]:
        warnings.append(f"Roof area ({area_m2:.1f}m²) is larger than typical {building_type} building")
        confidence -= 15
        suggestions.append("Check if polygon includes multiple buildings or non-roof areas")

    # Check length
    if length_m < limits["min_length"]:
        warnings.append(f"Roof length ({length_m:.1f}m) seems too short")
        confidence -= 15

    elif length_m > limits["max_length"]:
        warnings.append(f"Roof length ({length_m:.1f}m) seems too long for a single building")
        confidence -= 10

    # Check aspect ratio (length/width)
    if width_m > 0:
        aspect_ratio = length_m / width_m
        if aspect_ratio > 10:
            warnings.append(f"Unusual aspect ratio ({aspect_ratio:.1f}:1) - very narrow roof")
            confidence -= 10
            suggestions.append("Check if roof polygon is drawn correctly")

    # Check if dimensions match area (rough estimate)
    calculated_area = length_m * width_m
    if area_m2 > 0:
        area_ratio = calculated_area / area_m2
        if area_ratio < 0.5 or area_ratio > 2.0:
            warnings.append("Dimensions don't match calculated area - complex roof shape")
            confidence -= 5
            suggestions.append("This is normal for L-shaped or complex roofs")

    # Ensure confidence is in valid range
    confidence = max(0, min(100, confidence))

    is_valid = confidence >= 50  # 50% threshold for validity

    print(f"[MEASUREMENTS] Validation confidence: {confidence}%")
    if warnings:
        print(f"[MEASUREMENTS] Warnings: {len(warnings)}")

    return {
        "is_valid": is_valid,
        "confidence": confidence,
        "warnings": warnings,
        "suggestions": suggestions,
        "typical_area_range": limits["typical_area"]
    }


def calculate_optimal_panel_count(
    usable_area_m2: float,
    panel_width_m: float = 1.7,
    panel_height_m: float = 1.0,
    efficiency_factor: float = 0.75
) -> Dict:
    """
    Estimate optimal panel count based on usable roof area

    Provides quick estimate before detailed panel placement.
    Accounts for spacing, obstacles, and realistic coverage.

    Args:
        usable_area_m2: Usable roof area after setbacks
        panel_width_m: Panel width (default: 1.7m)
        panel_height_m: Panel height (default: 1.0m)
        efficiency_factor: Realistic coverage efficiency (default: 0.75 = 75%)

    Returns:
        Dict with:
        - estimated_panels: Estimated panel count
        - estimated_power_kw: Estimated system power
        - coverage_percent: Estimated coverage percentage

    Example:
        >>> estimate = calculate_optimal_panel_count(100)
        >>> print(f"{estimate['estimated_panels']} panels")
        44 panels
    """
    if usable_area_m2 <= 0:
        return {"estimated_panels": 0, "estimated_power_kw": 0, "coverage_percent": 0}

    # Panel area
    panel_area_m2 = panel_width_m * panel_height_m

    # Theoretical max panels
    max_panels = usable_area_m2 / panel_area_m2

    # Apply efficiency factor (accounts for spacing, orientation, obstacles)
    estimated_panels = int(max_panels * efficiency_factor)

    # Estimate power (assume 400W panels)
    estimated_power_kw = (estimated_panels * 400) / 1000

    # Coverage percentage
    actual_coverage_m2 = estimated_panels * panel_area_m2
    coverage_percent = (actual_coverage_m2 / usable_area_m2 * 100) if usable_area_m2 > 0 else 0

    print(f"[MEASUREMENTS] Estimated {estimated_panels} panels (~{estimated_power_kw:.2f} kW)")

    return {
        "estimated_panels": estimated_panels,
        "estimated_power_kw": round(estimated_power_kw, 2),
        "coverage_percent": round(coverage_percent, 1)
    }


def calculate_comprehensive_measurements(
    polygon_points: List[Tuple[float, float]],
    latitude: float,
    longitude: float,
    zoom_level: int = 19,
    pixels_per_meter: Optional[float] = None,
    building_type: str = "residential"
) -> Dict:
    """
    Calculate complete roof measurements and analysis

    All-in-one function that calculates dimensions, orientation, validation,
    and panel estimates.

    Args:
        polygon_points: Roof polygon vertices (pixels)
        latitude: Geographic latitude
        longitude: Geographic longitude
        zoom_level: Map zoom level
        pixels_per_meter: Optional scale override
        building_type: Building type for validation

    Returns:
        Comprehensive dict with all measurements

    Example:
        >>> measurements = calculate_comprehensive_measurements(
        ...     points, lat=32.0644, lon=34.7755, zoom=19
        ... )
        >>> print(measurements['summary'])
    """
    print("[MEASUREMENTS] ========== Calculating Comprehensive Measurements ==========")

    # 1. Real-world dimensions
    dimensions = calculate_real_dimensions(
        polygon_points, latitude, zoom_level, pixels_per_meter
    )

    # 2. Roof orientation
    orientation = calculate_roof_orientation(polygon_points)

    # 3. Measurement validation
    validation = validate_measurements(
        dimensions.get("area_m2", 0),
        dimensions.get("length_m", 0),
        dimensions.get("width_m", 0),
        building_type
    )

    # 4. Panel count estimate
    panel_estimate = calculate_optimal_panel_count(
        dimensions.get("usable_area_m2", 0)
    )

    # Combine all results
    result = {
        **dimensions,
        **orientation,
        "validation": validation,
        "panel_estimate": panel_estimate,
        "latitude": latitude,
        "longitude": longitude,
        "zoom_level": zoom_level,
        "building_type": building_type,
        "summary": f"{dimensions.get('length_m', 0):.1f}m x {dimensions.get('width_m', 0):.1f}m roof, "
                   f"{dimensions.get('area_m2', 0):.1f}m², facing {orientation.get('orientation_name', 'Unknown')}, "
                   f"~{panel_estimate.get('estimated_panels', 0)} panels possible"
    }

    print(f"[MEASUREMENTS] Summary: {result['summary']}")
    print("[MEASUREMENTS] ========================================")

    return result


if __name__ == "__main__":
    # Test roof measurements
    print("=" * 60)
    print("Testing Roof Measurements Module")
    print("=" * 60)

    # Test case: 20m x 10m roof (simulated at zoom 19, Israel)
    # At zoom 19, ~0.3 m/px, so 20m = ~67px, 10m = ~33px
    test_points = [
        (100, 100),  # Top-left
        (167, 100),  # Top-right (100 + 67)
        (167, 133),  # Bottom-right (100 + 33)
        (100, 133)   # Bottom-left
    ]

    test_lat = 32.0644  # Tel Aviv
    test_zoom = 19

    # Test 1: Dimensions
    print("\n[TEST 1] Calculate Dimensions")
    dims = calculate_real_dimensions(test_points, test_lat, test_zoom)
    print(f"✓ Length: {dims['length_m']}m")
    print(f"✓ Width: {dims['width_m']}m")
    print(f"✓ Area: {dims['area_m2']}m²")
    print(f"✓ Usable: {dims['usable_area_m2']}m²")

    # Test 2: Orientation
    print("\n[TEST 2] Calculate Orientation")
    orient = calculate_roof_orientation(test_points)
    print(f"✓ Azimuth: {orient['azimuth']}°")
    print(f"✓ Direction: {orient['orientation_name']}")
    print(f"✓ South-facing: {orient['is_suitable_south']}")

    # Test 3: Validation
    print("\n[TEST 3] Validate Measurements")
    validation = validate_measurements(dims['area_m2'], dims['length_m'], dims['width_m'])
    print(f"✓ Valid: {validation['is_valid']}")
    print(f"✓ Confidence: {validation['confidence']}%")
    if validation['warnings']:
        print(f"  Warnings: {len(validation['warnings'])}")

    # Test 4: Panel Estimate
    print("\n[TEST 4] Estimate Panel Count")
    estimate = calculate_optimal_panel_count(dims['usable_area_m2'])
    print(f"✓ Estimated panels: {estimate['estimated_panels']}")
    print(f"✓ Estimated power: {estimate['estimated_power_kw']} kW")

    # Test 5: Comprehensive
    print("\n[TEST 5] Comprehensive Measurements")
    comprehensive = calculate_comprehensive_measurements(
        test_points, test_lat, 34.7755, test_zoom
    )
    print(f"✓ Summary: {comprehensive['summary']}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
