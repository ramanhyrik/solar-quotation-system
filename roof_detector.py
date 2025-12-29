"""
Enterprise-Grade Manual Roof Designer and Solar Panel Layout Calculator
Advanced multi-orientation panel placement with polygon exclusion zones
"""

import numpy as np
from shapely.geometry import Polygon, Point, box, MultiPolygon
from shapely.ops import unary_union
from typing import List, Dict, Tuple, Optional
import json
from datetime import datetime
import os


class AdvancedPanelLayoutCalculator:
    """
    Enterprise-grade solar panel layout calculator with:
    - Multi-orientation optimization (landscape + portrait mixed)
    - Polygon-based exclusion zones
    - Edge-to-edge coverage
    - Gap-filling algorithm
    """

    def __init__(self, roof_polygon: List[Tuple[float, float]],
                 obstacles: List[Dict] = None):
        """
        Initialize panel layout calculator

        Args:
            roof_polygon: List of (x, y) tuples defining roof boundary
            obstacles: List of obstacle dictionaries with 'points' (polygon) or 'x,y,width,height' (rectangle)
        """
        # Create polygon and fix if invalid
        try:
            poly = Polygon(roof_polygon)

            if not poly.is_valid:
                print(f"[PANEL CALCULATOR] WARNING: Invalid polygon detected: {poly.is_valid_reason}")
                poly = poly.buffer(0)

                if not poly.is_valid or isinstance(poly, MultiPolygon):
                    print("[PANEL CALCULATOR] Attempting polygon simplification...")
                    poly = Polygon(roof_polygon).simplify(tolerance=2.0, preserve_topology=True)
                    poly = poly.buffer(0)

                if isinstance(poly, MultiPolygon):
                    print("[PANEL CALCULATOR] MultiPolygon detected, using largest component")
                    poly = max(poly.geoms, key=lambda p: p.area)

                print(f"[PANEL CALCULATOR] Polygon repaired. Valid: {poly.is_valid}")

            self.roof_polygon = poly
        except Exception as e:
            print(f"[PANEL CALCULATOR] ERROR creating polygon: {e}")
            coords = np.array(roof_polygon)
            min_x, min_y = coords.min(axis=0)
            max_x, max_y = coords.max(axis=0)
            self.roof_polygon = box(min_x, min_y, max_x, max_y)
            print(f"[PANEL CALCULATOR] Using bounding box fallback")

        self.obstacles = obstacles or []

        # Create obstacle geometries - support both polygons and rectangles
        self.obstacle_geoms = []
        for obs in self.obstacles:
            try:
                if 'points' in obs and obs['points']:
                    # Polygon obstacle
                    points = [(p['x'], p['y']) for p in obs['points']]
                    if len(points) >= 3:
                        obs_poly = Polygon(points)
                        if not obs_poly.is_valid:
                            obs_poly = obs_poly.buffer(0)
                        self.obstacle_geoms.append(obs_poly)
                elif 'x' in obs and 'y' in obs and 'width' in obs and 'height' in obs:
                    # Rectangle obstacle (backward compatibility)
                    obs_box = box(obs['x'], obs['y'],
                                obs['x'] + obs['width'],
                                obs['y'] + obs['height'])
                    self.obstacle_geoms.append(obs_box)
            except Exception as e:
                print(f"[PANEL CALCULATOR] Error creating obstacle geometry: {e}")
                continue

    def _try_place_panel(self, x: float, y: float, width: float, height: float,
                        placed_panels: List[box]) -> bool:
        """
        Check if a panel can be placed at given position without overlapping

        Args:
            x, y: Top-left corner position
            width, height: Panel dimensions
            placed_panels: List of already placed panel boxes

        Returns:
            True if panel can be placed
        """
        panel_box = box(x, y, x + width, y + height)

        # Check roof containment (95% threshold)
        intersection = self.roof_polygon.intersection(panel_box)
        containment_ratio = intersection.area / panel_box.area if panel_box.area > 0 else 0

        if containment_ratio < 0.95:
            return False

        # Check obstacles
        for obstacle in self.obstacle_geoms:
            if panel_box.intersects(obstacle):
                obstacle_intersection = panel_box.intersection(obstacle)
                if obstacle_intersection.area / panel_box.area > 0.05:  # 5% tolerance
                    return False

        # Check overlap with already placed panels
        for placed_box in placed_panels:
            if panel_box.intersects(placed_box):
                overlap = panel_box.intersection(placed_box)
                if overlap.area > 1:  # Allow 1px² tolerance
                    return False

        return True

    def calculate_layout(self,
                        panel_width_m: float = 1.7,
                        panel_height_m: float = 1.0,
                        panel_power_w: int = 400,
                        spacing_m: float = 0.05,
                        pixels_per_meter: float = 100.0,
                        orientation: str = "auto") -> Dict:
        """
        Calculate optimal panel placement using multi-pass algorithm

        Args:
            panel_width_m: Panel width in meters
            panel_height_m: Panel height in meters
            panel_power_w: Panel power in watts
            spacing_m: Spacing between panels in meters
            pixels_per_meter: Image scale (pixels per meter)
            orientation: "landscape", "portrait", or "auto" (mixed optimization)

        Returns:
            Dictionary with panel positions and statistics
        """
        print("[PANEL CALCULATOR] ========== Advanced Layout Calculation ==========")
        print(f"[PANEL CALCULATOR] Panel Specs: {panel_width_m}m x {panel_height_m}m, {panel_power_w}W")
        print(f"[PANEL CALCULATOR] Orientation: {orientation}, Spacing: {spacing_m}m")

        # Get roof bounds
        minx, miny, maxx, maxy = self.roof_polygon.bounds
        roof_area_px = self.roof_polygon.area

        # Convert to pixels
        panel_w_px = panel_width_m * pixels_per_meter
        panel_h_px = panel_height_m * pixels_per_meter
        spacing_px = spacing_m * pixels_per_meter

        print(f"[PANEL CALCULATOR] Roof bounds: ({minx:.0f}, {miny:.0f}) to ({maxx:.0f}, {maxy:.0f})")
        print(f"[PANEL CALCULATOR] Panel size: {panel_w_px:.1f}px x {panel_h_px:.1f}px")

        # Multi-pass placement algorithm
        if orientation == "auto":
            # Try both orientations and pick the best
            result_landscape = self._place_panels_optimized(
                minx, miny, maxx, maxy,
                panel_w_px, panel_h_px, spacing_px, "landscape"
            )
            result_portrait = self._place_panels_optimized(
                minx, miny, maxx, maxy,
                panel_h_px, panel_w_px, spacing_px, "portrait"  # Swapped dimensions
            )

            # Pick orientation with more panels
            if len(result_portrait['panels']) > len(result_landscape['panels']):
                print(f"[PANEL CALCULATOR] Auto-selected PORTRAIT: {len(result_portrait['panels'])} panels vs {len(result_landscape['panels'])} landscape")
                panels = result_portrait['panels']
                final_orientation = "portrait"
            else:
                print(f"[PANEL CALCULATOR] Auto-selected LANDSCAPE: {len(result_landscape['panels'])} panels vs {len(result_portrait['panels'])} portrait")
                panels = result_landscape['panels']
                final_orientation = "landscape"

            # Try mixed orientation (fill gaps with alternate orientation)
            print(f"[PANEL CALCULATOR] Attempting gap-filling with alternate orientation...")
            placed_boxes = [box(p['x'], p['y'], p['x'] + p['width'], p['y'] + p['height'])
                          for p in panels]

            # Try filling gaps with the other orientation
            if final_orientation == "landscape":
                gap_w, gap_h = panel_h_px, panel_w_px  # Portrait for gaps
                gap_orient = "portrait"
            else:
                gap_w, gap_h = panel_w_px, panel_h_px  # Landscape for gaps
                gap_orient = "landscape"

            gap_panels = self._fill_gaps(minx, miny, maxx, maxy, gap_w, gap_h,
                                        spacing_px, placed_boxes, gap_orient)

            if gap_panels:
                print(f"[PANEL CALCULATOR] Added {len(gap_panels)} panels in gaps with {gap_orient} orientation")
                panels.extend(gap_panels)

        else:
            # Single orientation
            if orientation == "portrait":
                panel_w_px, panel_h_px = panel_h_px, panel_w_px

            result = self._place_panels_optimized(
                minx, miny, maxx, maxy,
                panel_w_px, panel_h_px, spacing_px, orientation
            )
            panels = result['panels']

        # Calculate statistics
        total_panels = len(panels)
        total_power_kw = (total_panels * panel_power_w) / 1000

        roof_area_m2 = self.roof_polygon.area / (pixels_per_meter ** 2)
        panel_area_m2 = total_panels * (panel_width_m * panel_height_m)
        coverage_percent = (panel_area_m2 / roof_area_m2 * 100) if roof_area_m2 > 0 else 0

        print(f"[PANEL CALCULATOR] ========== Layout Complete ==========")
        print(f"[PANEL CALCULATOR] Total Panels: {total_panels}")
        print(f"[PANEL CALCULATOR] Total Power: {total_power_kw:.2f} kW")
        print(f"[PANEL CALCULATOR] Coverage: {coverage_percent:.1f}%")
        print(f"[PANEL CALCULATOR] ==========================================")

        return {
            "panels": panels,
            "total_panels": total_panels,
            "total_power_kw": round(total_power_kw, 2),
            "coverage_percent": round(coverage_percent, 1),
            "roof_area_m2": round(roof_area_m2, 2),
            "success": True
        }

    def _place_panels_optimized(self, minx, miny, maxx, maxy,
                                panel_w, panel_h, spacing, orientation):
        """
        Optimized panel placement starting from edges with fine-grained grid
        """
        panels = []
        placed_boxes = []

        # Use smaller step size for better coverage (50% overlap in scan)
        step_x = max(panel_w / 2, spacing * 2)
        step_y = max(panel_h / 2, spacing * 2)

        print(f"[PANEL CALCULATOR] Scanning with step: {step_x:.1f}px x {step_y:.1f}px")

        row_num = 0
        current_y = miny + spacing

        while current_y + panel_h <= maxy + spacing:
            col_num = 0
            current_x = minx + spacing

            while current_x + panel_w <= maxx + spacing:
                if self._try_place_panel(current_x, current_y, panel_w, panel_h, placed_boxes):
                    panel_box = box(current_x, current_y, current_x + panel_w, current_y + panel_h)
                    placed_boxes.append(panel_box)

                    panels.append({
                        "x": int(current_x),
                        "y": int(current_y),
                        "width": int(panel_w),
                        "height": int(panel_h),
                        "row": row_num,
                        "col": col_num,
                        "orientation": orientation
                    })
                    col_num += 1

                    # Jump to next non-overlapping position
                    current_x += panel_w + spacing
                else:
                    # Small step to find next valid position
                    current_x += step_x

            current_y += panel_h + spacing
            row_num += 1

        return {"panels": panels}

    def _fill_gaps(self, minx, miny, maxx, maxy, panel_w, panel_h, spacing,
                   placed_boxes, orientation):
        """
        Fill remaining gaps with panels in alternate orientation
        """
        gap_panels = []

        # Fine-grained grid search for gaps
        step = min(panel_w, panel_h) / 3

        y = miny
        row_num = 0
        while y + panel_h <= maxy:
            x = minx
            col_num = 0
            while x + panel_w <= maxx:
                if self._try_place_panel(x, y, panel_w, panel_h, placed_boxes):
                    panel_box = box(x, y, x + panel_w, y + panel_h)
                    placed_boxes.append(panel_box)

                    gap_panels.append({
                        "x": int(x),
                        "y": int(y),
                        "width": int(panel_w),
                        "height": int(panel_h),
                        "row": row_num,
                        "col": col_num,
                        "orientation": orientation
                    })
                    col_num += 1
                    x += panel_w + spacing
                else:
                    x += step

            y += step
            row_num += 1

        return gap_panels


def calculate_panel_layout_from_data(
    roof_polygon: List[Tuple[float, float]],
    obstacles: List[Dict] = None,
    panel_width_m: float = 1.7,
    panel_height_m: float = 1.0,
    panel_power_w: int = 400,
    spacing_m: float = 0.05,
    pixels_per_meter: float = 100.0,
    orientation: str = "auto"
) -> Dict:
    """
    Calculate panel layout from manually drawn roof data

    Returns:
        Panel layout results
    """
    try:
        # Validate roof polygon
        if not roof_polygon or len(roof_polygon) < 3:
            return {
                "success": False,
                "error": "Roof polygon must have at least 3 points"
            }

        # Clean polygon points
        cleaned_polygon = []
        for point in roof_polygon:
            try:
                if isinstance(point, (list, tuple)) and len(point) >= 2:
                    x = float(point[0]) if point[0] is not None else 0.0
                    y = float(point[1]) if point[1] is not None else 0.0
                    cleaned_polygon.append((x, y))
                elif isinstance(point, dict) and 'x' in point and 'y' in point:
                    x = float(point['x']) if point['x'] is not None else 0.0
                    y = float(point['y']) if point['y'] is not None else 0.0
                    cleaned_polygon.append((x, y))
            except (TypeError, ValueError) as e:
                print(f"[WARNING] Could not convert point {point}: {e}")
                continue

        if len(cleaned_polygon) < 3:
            return {
                "success": False,
                "error": "Not enough valid polygon points after cleaning"
            }

        # Clean obstacles (support both polygon and rectangle formats)
        cleaned_obstacles = []
        if obstacles:
            for obs in obstacles:
                try:
                    if 'points' in obs and obs['points']:
                        # Polygon obstacle
                        cleaned_points = []
                        for p in obs['points']:
                            if isinstance(p, dict) and 'x' in p and 'y' in p:
                                cleaned_points.append({
                                    'x': float(p['x']),
                                    'y': float(p['y'])
                                })
                        if len(cleaned_points) >= 3:
                            cleaned_obstacles.append({'points': cleaned_points})
                    elif 'x' in obs and 'y' in obs:
                        # Rectangle obstacle (backward compatibility)
                        cleaned_obs = {
                            'x': float(obs.get('x', 0)),
                            'y': float(obs.get('y', 0)),
                            'width': float(obs.get('width', 0)),
                            'height': float(obs.get('height', 0))
                        }
                        if cleaned_obs['width'] > 0 and cleaned_obs['height'] > 0:
                            cleaned_obstacles.append(cleaned_obs)
                except (TypeError, ValueError) as e:
                    print(f"[WARNING] Could not convert obstacle {obs}: {e}")
                    continue

        calculator = AdvancedPanelLayoutCalculator(cleaned_polygon, cleaned_obstacles)

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
