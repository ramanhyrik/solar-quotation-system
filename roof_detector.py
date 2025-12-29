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
        for idx, obs in enumerate(self.obstacles):
            try:
                if 'points' in obs and obs['points']:
                    # Polygon obstacle
                    points = [(p['x'], p['y']) for p in obs['points']]
                    if len(points) >= 3:
                        obs_poly = Polygon(points)
                        if not obs_poly.is_valid:
                            print(f"[PANEL CALCULATOR] WARNING: Obstacle {idx} polygon invalid, repairing...")
                            obs_poly = obs_poly.buffer(0)
                        self.obstacle_geoms.append(obs_poly)
                        bounds = obs_poly.bounds
                        area = obs_poly.area
                        print(f"[PANEL CALCULATOR] Obstacle {idx}: Polygon with {len(points)} points")
                        print(f"  Bounds: ({bounds[0]:.0f}, {bounds[1]:.0f}) to ({bounds[2]:.0f}, {bounds[3]:.0f})")
                        print(f"  Area: {area:.0f} px²")
                elif 'x' in obs and 'y' in obs and 'width' in obs and 'height' in obs:
                    # Rectangle obstacle (backward compatibility)
                    obs_box = box(obs['x'], obs['y'],
                                obs['x'] + obs['width'],
                                obs['y'] + obs['height'])
                    self.obstacle_geoms.append(obs_box)
                    print(f"[PANEL CALCULATOR] Obstacle {idx}: Rectangle at ({obs['x']:.0f}, {obs['y']:.0f}) size {obs['width']:.0f}x{obs['height']:.0f}")
            except Exception as e:
                print(f"[PANEL CALCULATOR] ERROR creating obstacle {idx} geometry: {e}")
                continue

        print(f"[PANEL CALCULATOR] Total obstacles created: {len(self.obstacle_geoms)}")

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

        # Check roof containment - 100% inside required (no overlap at all)
        if not self.roof_polygon.contains(panel_box):
            # Panel extends outside roof boundary
            return False

        # Check obstacles - STRICT no overlap policy
        for obstacle in self.obstacle_geoms:
            if panel_box.intersects(obstacle):
                # ANY intersection with obstacle is rejected
                return False

        # Check overlap with already placed panels
        for placed_box in placed_panels:
            if panel_box.intersects(placed_box):
                # ANY overlap with existing panels is rejected
                return False

        return True

    def _place_panels_greedy_mixed(self, minx, miny, maxx, maxy,
                                    panel_w, panel_h, spacing):
        """
        Greedy mixed-orientation algorithm: Try BOTH orientations at EVERY position
        This maximizes coverage by placing whichever orientation fits at each location

        Args:
            minx, miny, maxx, maxy: Roof boundary
            panel_w, panel_h: Panel dimensions (landscape orientation)
            spacing: Spacing between panels

        Returns:
            List of placed panels
        """
        panels = []
        placed_boxes = []

        # Define both possible orientations
        orientations = [
            ("landscape", panel_w, panel_h),
            ("portrait", panel_h, panel_w)
        ]

        print("[PANEL CALCULATOR] ===== Multi-Pass Greedy Mixed-Orientation Placement =====")

        # PASS 1: Coarse grid (20% step size) - fast initial placement
        step_coarse = min(panel_w, panel_h) * 0.2
        print(f"[PANEL CALCULATOR] Pass 1: Coarse scan (step={step_coarse:.1f}px)")
        pass1_count = 0

        y = miny
        while y + max(panel_w, panel_h) <= maxy:
            x = minx
            while x + max(panel_w, panel_h) <= maxx:
                # Try both orientations at this position
                placed = False
                for orient_name, w, h in orientations:
                    if self._try_place_panel(x, y, w, h, placed_boxes):
                        panel_box = box(x, y, x + w, y + h)
                        placed_boxes.append(panel_box)
                        panels.append({
                            "x": int(x),
                            "y": int(y),
                            "width": int(w),
                            "height": int(h),
                            "row": -1,
                            "col": -1,
                            "orientation": orient_name
                        })
                        pass1_count += 1
                        placed = True
                        x += w + spacing  # Jump past placed panel
                        break

                if not placed:
                    x += step_coarse  # Small step to find next position
            y += step_coarse

        print(f"[PANEL CALCULATOR] Pass 1 complete: {pass1_count} panels placed")

        # PASS 2: Medium scan (12% step size) - fill medium gaps
        step_medium = min(panel_w, panel_h) * 0.12
        print(f"[PANEL CALCULATOR] Pass 2: Medium scan (step={step_medium:.1f}px)")
        pass2_count = 0

        y = miny
        while y + max(panel_w, panel_h) <= maxy:
            x = minx
            while x + max(panel_w, panel_h) <= maxx:
                # Try both orientations
                placed = False
                for orient_name, w, h in orientations:
                    if self._try_place_panel(x, y, w, h, placed_boxes):
                        panel_box = box(x, y, x + w, y + h)
                        placed_boxes.append(panel_box)
                        panels.append({
                            "x": int(x),
                            "y": int(y),
                            "width": int(w),
                            "height": int(h),
                            "row": -1,
                            "col": -1,
                            "orientation": orient_name
                        })
                        pass2_count += 1
                        placed = True
                        x += w + spacing
                        break

                if not placed:
                    x += step_medium
            y += step_medium

        print(f"[PANEL CALCULATOR] Pass 2 complete: {pass2_count} additional panels")

        # PASS 3: Fine scan (8% step size) - fill small gaps
        step_fine = min(panel_w, panel_h) * 0.08
        print(f"[PANEL CALCULATOR] Pass 3: Fine scan (step={step_fine:.1f}px)")
        pass3_count = 0

        y = miny
        while y + max(panel_w, panel_h) <= maxy:
            x = minx
            while x + max(panel_w, panel_h) <= maxx:
                # Try both orientations
                placed = False
                for orient_name, w, h in orientations:
                    if self._try_place_panel(x, y, w, h, placed_boxes):
                        panel_box = box(x, y, x + w, y + h)
                        placed_boxes.append(panel_box)
                        panels.append({
                            "x": int(x),
                            "y": int(y),
                            "width": int(w),
                            "height": int(h),
                            "row": -1,
                            "col": -1,
                            "orientation": orient_name
                        })
                        pass3_count += 1
                        placed = True
                        x += w + spacing
                        break

                if not placed:
                    x += step_fine
            y += step_fine

        print(f"[PANEL CALCULATOR] Pass 3 complete: {pass3_count} additional panels")

        # PASS 4: Ultra-fine scan (5% step size) - catch any remaining tiny gaps
        step_ultra = min(panel_w, panel_h) * 0.05
        print(f"[PANEL CALCULATOR] Pass 4: Ultra-fine scan (step={step_ultra:.1f}px)")
        pass4_count = 0

        y = miny
        while y + max(panel_w, panel_h) <= maxy:
            x = minx
            while x + max(panel_w, panel_h) <= maxx:
                # Try both orientations
                placed = False
                for orient_name, w, h in orientations:
                    if self._try_place_panel(x, y, w, h, placed_boxes):
                        panel_box = box(x, y, x + w, y + h)
                        placed_boxes.append(panel_box)
                        panels.append({
                            "x": int(x),
                            "y": int(y),
                            "width": int(w),
                            "height": int(h),
                            "row": -1,
                            "col": -1,
                            "orientation": orient_name
                        })
                        pass4_count += 1
                        placed = True
                        x += w + spacing
                        break

                if not placed:
                    x += step_ultra
            y += step_ultra

        print(f"[PANEL CALCULATOR] Pass 4 complete: {pass4_count} additional panels")
        print(f"[PANEL CALCULATOR] ===== Total: {len(panels)} panels placed =====")

        # Count orientation breakdown
        landscape_count = sum(1 for p in panels if p['orientation'] == 'landscape')
        portrait_count = sum(1 for p in panels if p['orientation'] == 'portrait')
        print(f"[PANEL CALCULATOR] Orientation mix: {landscape_count} landscape, {portrait_count} portrait")

        return panels

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
            # GREEDY MIXED-ORIENTATION ALGORITHM
            # Try BOTH orientations at EVERY position for maximum coverage
            print("[PANEL CALCULATOR] Using greedy mixed-orientation algorithm...")
            panels = self._place_panels_greedy_mixed(
                minx, miny, maxx, maxy,
                panel_w_px, panel_h_px, spacing_px
            )

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
        Highly optimized panel placement with fine-grained multi-pass scanning
        """
        panels = []
        placed_boxes = []

        # Very fine-grained step size (25% of panel size for thorough coverage)
        step_x = max(panel_w / 4, spacing)
        step_y = max(panel_h / 4, spacing)

        print(f"[PANEL CALCULATOR] Fine-grained scan with step: {step_x:.1f}px x {step_y:.1f}px")

        # Pass 1: Regular grid from top-left
        current_y = miny + spacing
        row_num = 0

        while current_y + panel_h <= maxy:
            current_x = minx + spacing
            col_num = 0

            while current_x + panel_w <= maxx:
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

        initial_count = len(panels)
        print(f"[PANEL CALCULATOR] Pass 1 complete: {initial_count} panels placed")

        # Pass 2: Fine scan for remaining gaps
        print(f"[PANEL CALCULATOR] Pass 2: Scanning for gaps...")
        gaps_filled = 0

        y = miny
        while y + panel_h <= maxy:
            x = minx
            while x + panel_w <= maxx:
                if self._try_place_panel(x, y, panel_w, panel_h, placed_boxes):
                    panel_box = box(x, y, x + panel_w, y + panel_h)
                    placed_boxes.append(panel_box)

                    panels.append({
                        "x": int(x),
                        "y": int(y),
                        "width": int(panel_w),
                        "height": int(panel_h),
                        "row": -1,  # Gap-fill panels
                        "col": -1,
                        "orientation": orientation
                    })
                    gaps_filled += 1
                    x += panel_w + spacing
                else:
                    x += step_x
            y += step_y

        if gaps_filled > 0:
            print(f"[PANEL CALCULATOR] Pass 2 complete: {gaps_filled} additional panels placed in gaps")

        return {"panels": panels}

    def _fill_gaps(self, minx, miny, maxx, maxy, panel_w, panel_h, spacing,
                   placed_boxes, orientation):
        """
        Aggressively fill remaining gaps with panels in alternate orientation
        Multi-pass approach for maximum coverage
        """
        gap_panels = []

        # Ultra-fine step for gap filling (20% of smallest dimension)
        step = min(panel_w, panel_h) / 5

        print(f"[PANEL CALCULATOR] Gap-fill step size: {step:.1f}px")

        # Pass 1: Standard grid with alternate orientation
        y = miny + spacing
        while y + panel_h <= maxy:
            x = minx + spacing
            while x + panel_w <= maxx:
                if self._try_place_panel(x, y, panel_w, panel_h, placed_boxes):
                    panel_box = box(x, y, x + panel_w, y + panel_h)
                    placed_boxes.append(panel_box)

                    gap_panels.append({
                        "x": int(x),
                        "y": int(y),
                        "width": int(panel_w),
                        "height": int(panel_h),
                        "row": -1,
                        "col": -1,
                        "orientation": orientation
                    })
                    x += panel_w + spacing
                else:
                    x += step
            y += panel_h + spacing

        pass1_count = len(gap_panels)

        # Pass 2: Very fine scan for tiny remaining gaps
        y = miny
        while y + panel_h <= maxy:
            x = minx
            while x + panel_w <= maxx:
                if self._try_place_panel(x, y, panel_w, panel_h, placed_boxes):
                    panel_box = box(x, y, x + panel_w, y + panel_h)
                    placed_boxes.append(panel_box)

                    gap_panels.append({
                        "x": int(x),
                        "y": int(y),
                        "width": int(panel_w),
                        "height": int(panel_h),
                        "row": -1,
                        "col": -1,
                        "orientation": orientation
                    })
                    x += panel_w + spacing
                else:
                    x += step
            y += step

        pass2_count = len(gap_panels) - pass1_count
        if pass2_count > 0:
            print(f"[PANEL CALCULATOR] Gap-fill pass 2: {pass2_count} additional panels")

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
