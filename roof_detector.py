"""
AI-Powered Roof Detection and Solar Panel Layout Calculator
Uses Computer Vision and SAM (Segment Anything Model) to detect roof areas, obstacles, and calculate optimal panel placement
"""

import cv2
import numpy as np
from shapely.geometry import Polygon, Point, box, MultiPolygon
from shapely.ops import unary_union
from typing import List, Dict, Tuple, Optional
import json
from datetime import datetime
import os

# SAM (Segment Anything Model) - optional, fallback to traditional CV if not available
try:
    from segment_anything import sam_model_registry, SamAutomaticMaskGenerator
    import torch
    SAM_AVAILABLE = True
    print("[ROOF DETECTOR] SAM (Segment Anything Model) is available")
except ImportError:
    SAM_AVAILABLE = False
    print("[ROOF DETECTOR] SAM not available, using traditional computer vision methods")


class RoofDetector:
    """AI-powered roof area detection using computer vision"""

    def __init__(self, image_path: str):
        """
        Initialize roof detector with image

        Args:
            image_path: Path to roof image file
        """
        self.image_path = image_path
        self.image = cv2.imread(image_path)

        if self.image is None:
            raise ValueError(f"Could not load image from {image_path}")

        self.height, self.width = self.image.shape[:2]
        self.gray = cv2.cvtColor(self.image, cv2.COLOR_BGR2GRAY)

    def detect_roof_area(self, min_area_ratio: float = 0.1, use_sam: bool = True) -> Dict:
        """
        Detect main roof area using SAM (Segment Anything Model) ONLY

        Args:
            min_area_ratio: Minimum area ratio (compared to image) to consider as roof
            use_sam: Whether to use SAM (Segment Anything Model) if available

        Returns:
            Dictionary with roof polygon, area, and confidence score
        """
        print("[ROOF DETECTOR] ========== SAM-ONLY MODE ==========")
        print("[ROOF DETECTOR] Starting SAM-exclusive roof area detection...")

        # Check if SAM is available
        if not SAM_AVAILABLE:
            print("[ROOF DETECTOR] ERROR: SAM is not available!")
            print("[ROOF DETECTOR] Install SAM dependencies:")
            print("                pip install torch torchvision segment-anything")
            return None

        # Use SAM exclusively
        roof_polygon = None
        detection_method = "sam"

        print("[ROOF DETECTOR] Attempting SAM-based detection...")
        try:
            roof_polygon = self._detect_roof_sam()
            if roof_polygon:
                print("[ROOF DETECTOR] SAM detection successful!")
            else:
                print("[ROOF DETECTOR] SAM returned no valid roof segment")
                return None
        except Exception as e:
            print(f"[ROOF DETECTOR] SAM detection FAILED: {e}")
            import traceback
            traceback.print_exc()
            return None

        if roof_polygon:
            area_pixels = cv2.contourArea(np.array(roof_polygon, dtype=np.int32))
            area_ratio = area_pixels / (self.width * self.height)

            # Calculate confidence (SAM is highly reliable)
            confidence = self._calculate_confidence(roof_polygon, area_pixels)
            confidence = min(0.95, confidence * 1.2)  # SAM confidence boost

            print(f"[ROOF DETECTOR] ========== SAM DETECTION COMPLETE ==========")
            print(f"[ROOF DETECTOR] Detection Method: SAM")
            print(f"[ROOF DETECTOR] Polygon Points: {len(roof_polygon)}")
            print(f"[ROOF DETECTOR] Area: {area_pixels:.0f} px² ({area_ratio*100:.1f}% of image)")
            print(f"[ROOF DETECTOR] Confidence: {confidence:.2f}")
            print(f"[ROOF DETECTOR] ===============================================")

            return {
                "roof_polygon": roof_polygon,
                "area_pixels": float(area_pixels),
                "area_ratio": float(area_ratio),
                "confidence": float(confidence),
                "detection_method": detection_method,
                "image_dimensions": {"width": self.width, "height": self.height}
            }

        print("[ROOF DETECTOR] Failed to detect roof area with SAM")
        return None

    def _detect_roof_edges(self) -> Optional[List[Tuple[int, int]]]:
        """Detect roof using edge detection and contour analysis"""

        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(self.gray, (5, 5), 0)

        # Multi-scale edge detection
        edges1 = cv2.Canny(blurred, 30, 100)
        edges2 = cv2.Canny(blurred, 50, 150)
        edges = cv2.bitwise_or(edges1, edges2)

        # Morphological operations to close gaps
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edges = cv2.dilate(edges, kernel, iterations=2)
        edges = cv2.erode(edges, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        # Get largest contour (assume it's the roof)
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)

        # Filter out too small detections
        if area < (self.width * self.height * 0.05):  # At least 5% of image
            return None

        # Simplify polygon (reduce number of points)
        epsilon = 0.005 * cv2.arcLength(largest_contour, True)
        approx_polygon = cv2.approxPolyDP(largest_contour, epsilon, True)

        # Convert to list of tuples
        points = [(int(pt[0][0]), int(pt[0][1])) for pt in approx_polygon]

        return points

    def _detect_roof_color_segmentation(self) -> Optional[List[Tuple[int, int]]]:
        """Detect roof using color-based segmentation"""

        # Convert to LAB color space for better segmentation
        lab = cv2.cvtColor(self.image, cv2.COLOR_BGR2LAB)

        # Apply K-means clustering to find dominant colors
        pixels = lab.reshape(-1, 3).astype(np.float32)
        criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 100, 0.2)
        k = 4  # Number of clusters
        _, labels, centers = cv2.kmeans(pixels, k, None, criteria, 10, cv2.KMEANS_PP_CENTERS)

        # Find the cluster with largest area (likely the roof)
        label_counts = np.bincount(labels.flatten())
        dominant_label = np.argmax(label_counts)

        # Create mask for dominant cluster
        mask = (labels.reshape(self.height, self.width) == dominant_label).astype(np.uint8) * 255

        # Clean up mask
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (7, 7))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        largest_contour = max(contours, key=cv2.contourArea)
        epsilon = 0.005 * cv2.arcLength(largest_contour, True)
        approx_polygon = cv2.approxPolyDP(largest_contour, epsilon, True)

        points = [(int(pt[0][0]), int(pt[0][1])) for pt in approx_polygon]
        return points

    def _detect_largest_contour(self, min_area_ratio: float) -> Optional[List[Tuple[int, int]]]:
        """Fallback: detect largest contour in image"""

        # Aggressive thresholding
        _, thresh = cv2.threshold(self.gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

        # Find contours
        contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return None

        # Filter by minimum area
        min_area = self.width * self.height * min_area_ratio
        valid_contours = [c for c in contours if cv2.contourArea(c) >= min_area]

        if not valid_contours:
            return None

        largest_contour = max(valid_contours, key=cv2.contourArea)
        epsilon = 0.01 * cv2.arcLength(largest_contour, True)
        approx_polygon = cv2.approxPolyDP(largest_contour, epsilon, True)

        points = [(int(pt[0][0]), int(pt[0][1])) for pt in approx_polygon]
        return points

    def _detect_roof_sam(self) -> Optional[List[Tuple[int, int]]]:
        """
        Detect roof using SAM (Segment Anything Model)

        Uses automatic mask generation to find the largest meaningful segment
        """
        if not SAM_AVAILABLE:
            return None

        try:
            # Get or load SAM model
            sam_checkpoint = os.path.join("models", "sam_vit_h_4b8939.pth")

            # Check if model exists, if not use a lighter version or skip
            if not os.path.exists(sam_checkpoint):
                print(f"[SAM] Model checkpoint not found at {sam_checkpoint}")
                print("[SAM] Skipping SAM detection. Download SAM model from:")
                print("      https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth")
                return None

            # Load SAM model
            device = "cuda" if torch.cuda.is_available() else "cpu"
            print(f"[SAM] Loading model on {device}...")

            sam = sam_model_registry["vit_h"](checkpoint=sam_checkpoint)
            sam.to(device=device)

            # Create mask generator
            mask_generator = SamAutomaticMaskGenerator(
                model=sam,
                points_per_side=32,
                pred_iou_thresh=0.86,
                stability_score_thresh=0.92,
                crop_n_layers=1,
                crop_n_points_downscale_factor=2,
                min_mask_region_area=1000,
            )

            # Convert image to RGB (SAM expects RGB)
            rgb_image = cv2.cvtColor(self.image, cv2.COLOR_BGR2RGB)

            print("[SAM] Generating masks...")
            masks = mask_generator.generate(rgb_image)

            if not masks:
                print("[SAM] No masks generated")
                return None

            # Sort masks by area (largest first)
            masks = sorted(masks, key=lambda x: x['area'], reverse=True)

            # Get the largest mask that covers a reasonable portion of the image
            total_pixels = self.width * self.height
            for mask_data in masks:
                mask_area = mask_data['area']
                area_ratio = mask_area / total_pixels

                # Roof should be between 10% and 90% of image
                if 0.1 <= area_ratio <= 0.9:
                    # Get the segmentation mask
                    mask = mask_data['segmentation'].astype(np.uint8) * 255

                    # Find contour from mask
                    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

                    if contours:
                        largest_contour = max(contours, key=cv2.contourArea)

                        # Simplify polygon
                        epsilon = 0.002 * cv2.arcLength(largest_contour, True)
                        approx_polygon = cv2.approxPolyDP(largest_contour, epsilon, True)

                        # Convert to list of tuples
                        points = [(int(pt[0][0]), int(pt[0][1])) for pt in approx_polygon]

                        # Validate polygon
                        if len(points) >= 3:
                            print(f"[SAM] Found roof segment: {len(points)} points, {area_ratio*100:.1f}% of image")
                            return points

            print("[SAM] No suitable roof segment found in masks")
            return None

        except Exception as e:
            print(f"[SAM] Error during detection: {e}")
            import traceback
            traceback.print_exc()
            return None

    def _calculate_confidence(self, polygon: List[Tuple[int, int]], area: float) -> float:
        """Calculate detection confidence score based on multiple factors"""

        confidence = 0.5  # Base confidence

        # Factor 1: Area ratio (roofs typically occupy 20-80% of image)
        area_ratio = area / (self.width * self.height)
        if 0.2 <= area_ratio <= 0.8:
            confidence += 0.2
        elif 0.1 <= area_ratio <= 0.9:
            confidence += 0.1

        # Factor 2: Polygon complexity (roofs are usually not too complex)
        num_points = len(polygon)
        if 4 <= num_points <= 12:  # Reasonable complexity
            confidence += 0.2
        elif num_points <= 20:
            confidence += 0.1

        # Factor 3: Convexity (roofs are generally convex)
        hull = cv2.convexHull(np.array(polygon, dtype=np.int32))
        hull_area = cv2.contourArea(hull)
        if hull_area > 0:
            convexity = area / hull_area
            if convexity > 0.85:
                confidence += 0.1

        return min(confidence, 1.0)

    def detect_obstacles(self, roof_polygon: List[Tuple[int, int]],
                        min_obstacle_size: int = 500) -> List[Dict]:
        """
        Detect obstacles on roof (chimneys, vents, AC units, etc.)

        Args:
            roof_polygon: List of (x, y) tuples defining roof boundary
            min_obstacle_size: Minimum area in pixels to consider as obstacle

        Returns:
            List of obstacle dictionaries with position and size
        """
        print("[ROOF DETECTOR] Detecting obstacles...")

        # Create mask for roof area
        roof_mask = np.zeros((self.height, self.width), dtype=np.uint8)
        roof_contour = np.array(roof_polygon, dtype=np.int32)
        cv2.fillPoly(roof_mask, [roof_contour], 255)

        # Method 1: Detect dark objects (shadows from obstacles)
        obstacles = self._detect_shadow_obstacles(roof_mask, min_obstacle_size)

        # Method 2: Detect edge-based objects
        edge_obstacles = self._detect_edge_obstacles(roof_mask, min_obstacle_size)

        # Merge detections (avoid duplicates)
        all_obstacles = self._merge_obstacles(obstacles + edge_obstacles)

        # Filter obstacles inside roof
        roof_poly = Polygon(roof_polygon)
        valid_obstacles = []

        for obs in all_obstacles:
            center = Point(obs['x'] + obs['width']/2, obs['y'] + obs['height']/2)
            if roof_poly.contains(center):
                valid_obstacles.append(obs)

        print(f"[ROOF DETECTOR] Found {len(valid_obstacles)} obstacles")

        return valid_obstacles

    def _detect_shadow_obstacles(self, roof_mask: np.ndarray,
                                 min_size: int) -> List[Dict]:
        """Detect obstacles based on shadow/darkness"""

        # Apply adaptive thresholding to detect dark regions
        blurred = cv2.GaussianBlur(self.gray, (7, 7), 0)
        adaptive_thresh = cv2.adaptiveThreshold(
            blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 25, 5
        )

        # Apply roof mask
        obstacles_mask = cv2.bitwise_and(adaptive_thresh, roof_mask)

        # Morphological operations to clean up
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
        obstacles_mask = cv2.morphologyEx(obstacles_mask, cv2.MORPH_CLOSE, kernel)
        obstacles_mask = cv2.morphologyEx(obstacles_mask, cv2.MORPH_OPEN, kernel)

        # Find obstacle contours
        contours, _ = cv2.findContours(obstacles_mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        obstacles = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= min_size:
                x, y, w, h = cv2.boundingRect(contour)
                obstacles.append({
                    "x": int(x),
                    "y": int(y),
                    "width": int(w),
                    "height": int(h),
                    "area": float(area),
                    "type": "shadow"
                })

        return obstacles

    def _detect_edge_obstacles(self, roof_mask: np.ndarray,
                               min_size: int) -> List[Dict]:
        """Detect obstacles based on edges within roof area"""

        # Edge detection
        edges = cv2.Canny(self.gray, 50, 150)
        edges = cv2.bitwise_and(edges, roof_mask)

        # Dilate to connect nearby edges
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        edges = cv2.dilate(edges, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        obstacles = []
        for contour in contours:
            area = cv2.contourArea(contour)
            if area >= min_size:
                x, y, w, h = cv2.boundingRect(contour)
                obstacles.append({
                    "x": int(x),
                    "y": int(y),
                    "width": int(w),
                    "height": int(h),
                    "area": float(area),
                    "type": "edge"
                })

        return obstacles

    def _merge_obstacles(self, obstacles: List[Dict],
                        overlap_threshold: float = 0.5) -> List[Dict]:
        """Merge overlapping obstacle detections"""

        if not obstacles:
            return []

        # Convert to Shapely boxes for easier overlap detection
        boxes = []
        for obs in obstacles:
            boxes.append(box(obs['x'], obs['y'],
                           obs['x'] + obs['width'],
                           obs['y'] + obs['height']))

        # Merge overlapping boxes
        merged = []
        used = set()

        for i, box1 in enumerate(boxes):
            if i in used:
                continue

            merged_box = box1
            for j, box2 in enumerate(boxes):
                if i == j or j in used:
                    continue

                # Check overlap
                intersection = merged_box.intersection(box2)
                if intersection.area / min(merged_box.area, box2.area) > overlap_threshold:
                    merged_box = merged_box.union(box2).envelope
                    used.add(j)

            bounds = merged_box.bounds
            merged.append({
                "x": int(bounds[0]),
                "y": int(bounds[1]),
                "width": int(bounds[2] - bounds[0]),
                "height": int(bounds[3] - bounds[1]),
                "area": float(merged_box.area),
                "type": "merged"
            })
            used.add(i)

        return merged

    def save_visualization(self, output_path: str, roof_polygon: List[Tuple[int, int]],
                          obstacles: List[Dict] = None, panels: List[Dict] = None):
        """
        Save visualization image with detected roof, obstacles, and panels

        Args:
            output_path: Path to save visualization image
            roof_polygon: Roof boundary polygon
            obstacles: List of detected obstacles
            panels: List of placed panels
        """
        vis_image = self.image.copy()

        # Draw roof polygon
        if roof_polygon:
            roof_contour = np.array(roof_polygon, dtype=np.int32)
            cv2.polylines(vis_image, [roof_contour], True, (0, 255, 0), 3)

            # Fill with semi-transparent green
            overlay = vis_image.copy()
            cv2.fillPoly(overlay, [roof_contour], (0, 255, 0))
            cv2.addWeighted(overlay, 0.2, vis_image, 0.8, 0, vis_image)

        # Draw obstacles
        if obstacles:
            for obs in obstacles:
                cv2.rectangle(vis_image,
                            (obs['x'], obs['y']),
                            (obs['x'] + obs['width'], obs['y'] + obs['height']),
                            (0, 0, 255), 2)

        # Draw panels
        if panels:
            for panel in panels:
                cv2.rectangle(vis_image,
                            (panel['x'], panel['y']),
                            (panel['x'] + panel['width'], panel['y'] + panel['height']),
                            (255, 165, 0), 2)

        # Save image
        cv2.imwrite(output_path, vis_image)
        print(f"[ROOF DETECTOR] Visualization saved to {output_path}")


class PanelLayoutCalculator:
    """Calculate optimal solar panel placement on roof"""

    def __init__(self, roof_polygon: List[Tuple[int, int]],
                 obstacles: List[Dict] = None):
        """
        Initialize panel layout calculator

        Args:
            roof_polygon: List of (x, y) tuples defining roof boundary
            obstacles: List of obstacle dictionaries
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
            import numpy as np
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
                            "rotation": 0,
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

        print(f"[PANEL CALCULATOR] Placed {total_panels} panels")
        print(f"[PANEL CALCULATOR] Total power: {total_power_kw:.2f} kW")
        print(f"[PANEL CALCULATOR] Coverage: {coverage_percent:.1f}%")

        return {
            "panels": panels,
            "total_panels": total_panels,
            "total_power_kw": round(total_power_kw, 2),
            "coverage_percent": round(coverage_percent, 2),
            "roof_area_m2": round(roof_area_m2, 2),
            "panel_area_m2": round(panel_area_m2, 2)
        }


# Utility functions for API endpoints
def process_roof_image(image_path: str,
                      min_obstacle_size: int = 500) -> Dict:
    """
    Complete roof analysis pipeline

    Args:
        image_path: Path to roof image
        min_obstacle_size: Minimum obstacle size in pixels

    Returns:
        Complete analysis results
    """
    try:
        detector = RoofDetector(image_path)

        # Detect roof area
        roof_data = detector.detect_roof_area()

        if not roof_data:
            return {
                "success": False,
                "error": "Could not detect roof area in image"
            }

        # Detect obstacles
        obstacles = detector.detect_obstacles(
            roof_data['roof_polygon'],
            min_obstacle_size
        )

        return {
            "success": True,
            "roof_polygon": roof_data['roof_polygon'],
            "roof_area_pixels": roof_data['area_pixels'],
            "confidence": roof_data['confidence'],
            "obstacles": obstacles,
            "image_dimensions": roof_data['image_dimensions']
        }

    except Exception as e:
        print(f"[ERROR] Roof analysis failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }


def calculate_panel_layout_from_data(
    roof_polygon: List[Tuple[int, int]],
    obstacles: List[Dict],
    panel_width_m: float = 1.7,
    panel_height_m: float = 1.0,
    panel_power_w: int = 400,
    spacing_m: float = 0.05,
    pixels_per_meter: float = 100.0,
    orientation: str = "landscape"
) -> Dict:
    """
    Calculate panel layout from roof data

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

        return {
            "success": True,
            **results
        }

    except Exception as e:
        print(f"[ERROR] Panel calculation failed: {str(e)}")
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": str(e)
        }
