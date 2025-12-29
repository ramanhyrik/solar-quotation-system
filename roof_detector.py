"""
Manual Roof Designer and Solar Panel Layout Calculator
Users manually draw roof boundaries and exclusion zones, then the calculator optimizes panel placement
"""

import numpy as np
from shapely.geometry import Polygon, Point, box, MultiPolygon
from shapely.ops import unary_union
from typing import List, Dict, Tuple, Optional
import json
from datetime import datetime
import os


class PanelLayoutCalculator:
    """Calculate optimal solar panel layout on a manually drawn roof polygon"""

    def __init__(self, roof_polygon: List[Tuple[float, float]],
                 obstacles: List[Dict] = None):
        """
        Initialize panel layout calculator

        Args:
            roof_polygon: List of (x, y) tuples defining roof boundary
            obstacles: List of obstacle dictionaries with x, y, width, height
        """
        # Create polygon and fix if invalid (self-intersecting, etc.)
        try:
            poly = Polygon(roof_polygon)

            # Check if polygon is valid
            if not poly.is_valid:
                print(f"[PANEL CALCULATOR] WARNING: Invalid polygon detected: {poly.is_valid_reason}")
                # Use buffer(0) trick to fix self-intersecting polygons
                poly = poly.buffer(0)

                # If still invalid or became a MultiPolygon, try simplification
                if not poly.is_valid or isinstance(poly, MultiPolygon):
                    print("[PANEL CALCULATOR] Attempting polygon simplification...")
                    poly = Polygon(roof_polygon).simplify(tolerance=2.0, preserve_topology=True)
                    poly = poly.buffer(0)

                # If it's a MultiPolygon after repair, use the largest polygon
                if isinstance(poly, MultiPolygon):
                    print("[PANEL CALCULATOR] MultiPolygon detected, using largest component")
                    poly = max(poly.geoms, key=lambda p: p.area)

                print(f"[PANEL CALCULATOR] Polygon repaired. Valid: {poly.is_valid}")

            self.roof_polygon = poly
        except Exception as e:
            print(f"[PANEL CALCULATOR] ERROR creating polygon: {e}")
            # Fallback: create a bounding box from points
            coords = np.array(roof_polygon)
            min_x, min_y = coords.min(axis=0)
            max_x, max_y = coords.max(axis=0)
            self.roof_polygon = box(min_x, min_y, max_x, max_y)
            print(f"[PANEL CALCULATOR] Using bounding box fallback")

        self.obstacles = obstacles or []

        # Create obstacle geometries
        self.obstacle_geoms = []
        for obs in self.obstacles:
            obs_box = box(obs['x'], obs['y'],
                         obs['x'] + obs['width'],
                         obs['y'] + obs['height'])
            self.obstacle_geoms.append(obs_box)

    def calculate_layout(self,
                        panel_width_m: float = 1.7,
                        panel_height_m: float = 1.0,
                        panel_power_w: int = 400,
                        spacing_m: float = 0.05,
                        pixels_per_meter: float = 100.0,
                        orientation: str = "landscape") -> Dict:
        """
        Calculate optimal panel placement

        Args:
            panel_width_m: Panel width in meters
            panel_height_m: Panel height in meters
            panel_power_w: Panel power in watts
            spacing_m: Spacing between panels in meters
            pixels_per_meter: Image scale (pixels per meter)
            orientation: "landscape" or "portrait"

        Returns:
            Dictionary with panel positions and statistics
        """
        print("[PANEL CALCULATOR] ========== Starting Panel Layout Calculation ==========")
        print(f"[PANEL CALCULATOR] Panel Specifications: {panel_width_m}m x {panel_height_m}m, {panel_power_w}W")
        print(f"[PANEL CALCULATOR] Orientation: {orientation}, Spacing: {spacing_m}m")
        print(f"[PANEL CALCULATOR] Scale: {pixels_per_meter} pixels/meter")

        # Get roof bounds and dimensions
        minx, miny, maxx, maxy = self.roof_polygon.bounds
        roof_width_px = maxx - minx
        roof_height_px = maxy - miny
        roof_area_px = self.roof_polygon.area

        print(f"[PANEL CALCULATOR] Roof bounds: ({minx:.1f}, {miny:.1f}) to ({maxx:.1f}, {maxy:.1f})")
        print(f"[PANEL CALCULATOR] Roof dimensions: {roof_width_px:.1f}px x {roof_height_px:.1f}px")
        print(f"[PANEL CALCULATOR] Roof area: {roof_area_px:.0f} px²")

        # Convert measurements to pixels
        panel_w_px = panel_width_m * pixels_per_meter
        panel_h_px = panel_height_m * pixels_per_meter
        spacing_px = spacing_m * pixels_per_meter

        # Swap dimensions if portrait
        if orientation == "portrait":
            panel_w_px, panel_h_px = panel_h_px, panel_w_px

        print(f"[PANEL CALCULATOR] Panel size in pixels: {panel_w_px:.1f}px x {panel_h_px:.1f}px")
        print(f"[PANEL CALCULATOR] Spacing in pixels: {spacing_px:.1f}px")

        # Sanity check: panel size shouldn't be larger than roof
        if panel_w_px > roof_width_px or panel_h_px > roof_height_px:
            print(f"[PANEL CALCULATOR] WARNING: Panel size ({panel_w_px:.0f}x{panel_h_px:.0f}px) larger than roof ({roof_width_px:.0f}x{roof_height_px:.0f}px)")
            print(f"[PANEL CALCULATOR] Consider adjusting pixels_per_meter. Current value: {pixels_per_meter}")
            # Suggest better scale
            suggested_scale = min(roof_width_px / (panel_width_m * 10), roof_height_px / (panel_height_m * 10))
            print(f"[PANEL CALCULATOR] Suggested pixels_per_meter: {suggested_scale:.0f}")

        # Grid-based placement with optimization
        panels = []
        current_y = miny + spacing_px
        row_num = 0
        attempts = 0
        fits_in_roof = 0
        blocked_by_obstacles = 0

        while current_y + panel_h_px <= maxy:
            current_x = minx + spacing_px
            col_num = 0

            while current_x + panel_w_px <= maxx:
                attempts += 1

                # Create panel box
                panel_box = box(current_x, current_y,
                              current_x + panel_w_px,
                              current_y + panel_h_px)

                # Check if panel fits in roof (allow 5% tolerance for edge cases)
                intersection = self.roof_polygon.intersection(panel_box)
                containment_ratio = intersection.area / panel_box.area if panel_box.area > 0 else 0

                if containment_ratio >= 0.95:  # At least 95% of panel must be within roof
                    fits_in_roof += 1

                    # Check overlap with obstacles
                    overlaps = False
                    for obstacle in self.obstacle_geoms:
                        if panel_box.intersects(obstacle):
                            # Check if significant overlap (>10%)
                            obstacle_intersection = panel_box.intersection(obstacle)
                            if obstacle_intersection.area / panel_box.area > 0.1:
                                overlaps = True
                                blocked_by_obstacles += 1
                                break

                    if not overlaps:
                        panels.append({
                            "x": int(current_x),
                            "y": int(current_y),
                            "width": int(panel_w_px),
                            "height": int(panel_h_px),
                            "row": row_num,
                            "col": col_num
                        })
                        col_num += 1

                current_x += panel_w_px + spacing_px

            current_y += panel_h_px + spacing_px
            row_num += 1

        print(f"[PANEL CALCULATOR] Grid attempts: {attempts}")
        print(f"[PANEL CALCULATOR] Panels fitting in roof: {fits_in_roof}")
        print(f"[PANEL CALCULATOR] Panels blocked by obstacles: {blocked_by_obstacles}")

        # Calculate statistics
        total_panels = len(panels)
        total_power_kw = (total_panels * panel_power_w) / 1000

        roof_area_m2 = self.roof_polygon.area / (pixels_per_meter ** 2)
        panel_area_m2 = total_panels * (panel_width_m * panel_height_m)
        coverage_percent = (panel_area_m2 / roof_area_m2 * 100) if roof_area_m2 > 0 else 0

        print(f"[PANEL CALCULATOR] ========== Layout Complete ==========")
        print(f"[PANEL CALCULATOR] Total Panels: {total_panels}")
        print(f"[PANEL CALCULATOR] Total Power: {total_power_kw:.2f} kW")
        print(f"[PANEL CALCULATOR] Roof Area: {roof_area_m2:.2f} m²")
        print(f"[PANEL CALCULATOR] Coverage: {coverage_percent:.1f}%")
        print(f"[PANEL CALCULATOR] =====================================")

        return {
            "panels": panels,
            "total_panels": total_panels,
            "total_power_kw": round(total_power_kw, 2),
            "coverage_percent": round(coverage_percent, 1),
            "roof_area_m2": round(roof_area_m2, 2),
            "success": True
        }


def calculate_panel_layout_from_data(
    roof_polygon: List[Tuple[float, float]],
    obstacles: List[Dict] = None,
    panel_width_m: float = 1.7,
    panel_height_m: float = 1.0,
    panel_power_w: int = 400,
    spacing_m: float = 0.05,
    pixels_per_meter: float = 100.0,
    orientation: str = "landscape"
) -> Dict:
    """
    Calculate panel layout from manually drawn roof data

    Returns:
        Panel layout results
    """
    try:
        # Validate and clean roof polygon
        if not roof_polygon or len(roof_polygon) < 3:
            return {
                "success": False,
                "error": "Roof polygon must have at least 3 points"
            }

        # Clean polygon points - remove None values
        cleaned_polygon = []
        for point in roof_polygon:
            try:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    x = float(point[0]) if point[0] is not None else 0.0
                    y = float(point[1]) if point[1] is not None else 0.0
                    cleaned_polygon.append((x, y))
                else:
                    print(f"[WARNING] Invalid point format: {point}")
            except (TypeError, ValueError) as e:
                print(f"[WARNING] Could not convert point {point}: {e}")
                continue

        if len(cleaned_polygon) < 3:
            return {
                "success": False,
                "error": "Not enough valid polygon points after cleaning"
            }

        # Clean obstacles
        cleaned_obstacles = []
        if obstacles:
            for obs in obstacles:
                try:
                    cleaned_obs = {
                        'x': float(obs.get('x', 0)) if obs.get('x') is not None else 0.0,
                        'y': float(obs.get('y', 0)) if obs.get('y') is not None else 0.0,
                        'width': float(obs.get('width', 0)) if obs.get('width') is not None else 0.0,
                        'height': float(obs.get('height', 0)) if obs.get('height') is not None else 0.0
                    }
                    if cleaned_obs['width'] > 0 and cleaned_obs['height'] > 0:
                        cleaned_obstacles.append(cleaned_obs)
                except (TypeError, ValueError) as e:
                    print(f"[WARNING] Could not convert obstacle {obs}: {e}")
                    continue

        calculator = PanelLayoutCalculator(cleaned_polygon, cleaned_obstacles)

        results = calculator.calculate_layout(
            panel_width_m=panel_width_m,
            panel_height_m=panel_height_m,
            panel_power_w=panel_power_w,
            spacing_m=spacing_m,
            pixels_per_meter=pixels_per_meter,
            orientation=orientation
        )

        return results

    except Exception as e:
        print(f"[ERROR] Panel layout calculation failed: {e}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }
