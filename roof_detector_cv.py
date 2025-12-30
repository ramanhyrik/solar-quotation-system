"""
AI-Powered Roof Detection using Computer Vision
Lightweight edge-detection approach suitable for 512MB memory constraint
"""

import cv2
import numpy as np
from typing import List, Dict, Tuple
import os


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 3) -> Dict:
    """
    Automatically detect roof boundaries using multiple computer vision strategies.
    Uses traditional CV (no ML models) - fits easily in 512MB memory.

    Args:
        image_path: Path to the uploaded roof image
        max_candidates: Number of top candidates to return (default: 3)

    Returns:
        Dict containing:
        - success: bool
        - candidates: List of detected polygon candidates with confidence scores
        - error: str (if failed)
    """
    try:
        # Load image
        if not os.path.exists(image_path):
            return {"success": False, "error": "Image file not found"}

        img = cv2.imread(image_path)
        if img is None:
            return {"success": False, "error": "Failed to load image"}

        original_height, original_width = img.shape[:2]
        print(f"[AI-DETECT] Image loaded: {original_width}x{original_height}")

        # Resize for faster processing (max 800px for better quality)
        scale = 1.0
        if max(original_width, original_height) > 800:
            scale = 800 / max(original_width, original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            img = cv2.resize(img, (new_width, new_height))
            print(f"[AI-DETECT] Resized to: {new_width}x{new_height}, scale={scale:.3f}")

        img_area = img.shape[0] * img.shape[1]
        all_contours = []

        # Strategy 1: Simple Rectangle Detection using hough lines
        print("[AI-DETECT] Strategy 1: Hough Line Transform")
        rect_contours = detect_using_hough_lines(img)
        if rect_contours:
            all_contours.extend(rect_contours)
            print(f"  Found {len(rect_contours)} rectangle candidates")

        # Strategy 2: GrabCut for foreground extraction
        print("[AI-DETECT] Strategy 2: GrabCut Foreground Segmentation")
        grabcut_contours = detect_using_grabcut(img)
        if grabcut_contours:
            all_contours.extend(grabcut_contours)
            print(f"  Found {len(grabcut_contours)} grabcut candidates")

        # Strategy 3: Color-based segmentation (aerial roofs often darker)
        print("[AI-DETECT] Strategy 3: Color-based Segmentation")
        color_contours = detect_using_color_segmentation(img)
        if color_contours:
            all_contours.extend(color_contours)
            print(f"  Found {len(color_contours)} color-based candidates")

        # Strategy 4: Multi-scale edge detection
        print("[AI-DETECT] Strategy 4: Multi-scale Edge Detection")
        edge_contours = detect_using_multiscale_edges(img)
        if edge_contours:
            all_contours.extend(edge_contours)
            print(f"  Found {len(edge_contours)} edge-based candidates")

        print(f"[AI-DETECT] Total contours from all strategies: {len(all_contours)}")

        if not all_contours:
            return {
                "success": True,
                "candidates": [],
                "message": "No roof boundaries detected. Please try manual drawing.",
                "debug_info": "All detection strategies failed to find suitable contours"
            }

        # Process and score all candidates
        candidates = []
        for cnt in all_contours:
            area = cv2.contourArea(cnt)
            area_ratio = area / img_area

            # Filter by area
            if area < img_area * 0.05 or area > img_area * 0.95:
                continue

            # Approximate polygon
            perimeter = cv2.arcLength(cnt, True)

            # Try multiple approximation levels
            for epsilon_factor in [0.01, 0.02, 0.03]:
                epsilon = epsilon_factor * perimeter
                approx = cv2.approxPolyDP(cnt, epsilon, True)
                num_vertices = len(approx)

                if 3 <= num_vertices <= 15:
                    confidence = calculate_confidence_score(
                        approx, area, img_area, num_vertices, perimeter
                    )

                    # Scale points back to original image size
                    scaled_points = []
                    for point in approx:
                        x, y = point[0]
                        scaled_x = x / scale
                        scaled_y = y / scale
                        scaled_points.append({"x": float(scaled_x), "y": float(scaled_y)})

                    candidates.append({
                        "points": scaled_points,
                        "vertices": num_vertices,
                        "area_px": float(area / (scale * scale)),
                        "area_ratio": float(area_ratio),
                        "confidence": float(confidence),
                        "perimeter": float(perimeter / scale)
                    })
                    break  # Use first successful approximation

        if len(candidates) == 0:
            return {
                "success": True,
                "candidates": [],
                "message": "No suitable roof boundaries found. Try manual drawing.",
                "debug_info": f"Found {len(all_contours)} contours but none met quality criteria"
            }

        # Remove near-duplicate candidates (IoU > 0.7)
        candidates = remove_duplicate_candidates(candidates)

        # Sort by confidence
        candidates.sort(key=lambda x: x['confidence'], reverse=True)

        # Return top N candidates
        top_candidates = candidates[:max_candidates]

        for i, c in enumerate(top_candidates):
            print(f"[AI-DETECT] Candidate {i+1}: {c['vertices']} vertices, "
                  f"area={c['area_ratio']*100:.1f}%, confidence={c['confidence']:.1f}%")

        return {
            "success": True,
            "candidates": top_candidates,
            "total_found": len(candidates),
            "image_dimensions": {
                "width": original_width,
                "height": original_height
            }
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Auto-detection failed: {str(e)}"
        }


def detect_using_hough_lines(img):
    """Detect rectangles using Hough line transform"""
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray, 50, 150, apertureSize=3)

        # Detect lines
        lines = cv2.HoughLinesP(edges, 1, np.pi/180, threshold=80,
                               minLineLength=50, maxLineGap=10)

        if lines is None or len(lines) < 4:
            return []

        # Group lines into horizontal and vertical
        horizontal_lines = []
        vertical_lines = []

        for line in lines:
            x1, y1, x2, y2 = line[0]
            angle = np.abs(np.arctan2(y2 - y1, x2 - x1) * 180 / np.pi)

            if angle < 20 or angle > 160:  # Horizontal
                horizontal_lines.append(line[0])
            elif 70 < angle < 110:  # Vertical
                vertical_lines.append(line[0])

        # Try to form rectangles from line intersections
        contours = []
        # Simplified: just create a bounding box from detected lines
        if horizontal_lines and vertical_lines:
            all_x = []
            all_y = []
            for line in horizontal_lines + vertical_lines:
                all_x.extend([line[0], line[2]])
                all_y.extend([line[1], line[3]])

            x_min, x_max = int(np.percentile(all_x, 10)), int(np.percentile(all_x, 90))
            y_min, y_max = int(np.percentile(all_y, 10)), int(np.percentile(all_y, 90))

            rect = np.array([[x_min, y_min], [x_max, y_min],
                            [x_max, y_max], [x_min, y_max]], dtype=np.int32)
            contours.append(rect.reshape((-1, 1, 2)))

        return contours
    except:
        return []


def detect_using_grabcut(img):
    """Use GrabCut for foreground/background segmentation"""
    try:
        mask = np.zeros(img.shape[:2], np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)

        # Initialize rectangle (assume roof is in center 60% of image)
        h, w = img.shape[:2]
        rect = (int(w*0.2), int(h*0.2), int(w*0.6), int(h*0.6))

        # Run GrabCut
        cv2.grabCut(img, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)

        # Create mask where sure and probable foreground
        mask2 = np.where((mask == 2) | (mask == 0), 0, 1).astype('uint8')

        # Find contours in the mask
        contours, _ = cv2.findContours(mask2, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        return list(contours)
    except:
        return []


def detect_using_color_segmentation(img):
    """Detect based on color similarity"""
    try:
        # Convert to HSV for better color segmentation
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Calculate center region color (likely roof)
        h, w = img.shape[:2]
        center_region = hsv[int(h*0.4):int(h*0.6), int(w*0.4):int(w*0.6)]
        mean_hue = np.mean(center_region[:, :, 0])
        mean_sat = np.mean(center_region[:, :, 1])

        # Create mask for similar colors
        lower = np.array([max(0, mean_hue - 20), max(0, mean_sat - 50), 20])
        upper = np.array([min(180, mean_hue + 20), min(255, mean_sat + 50), 255])
        mask = cv2.inRange(hsv, lower, upper)

        # Clean up mask
        kernel = np.ones((7, 7), np.uint8)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        return list(contours)
    except:
        return []


def detect_using_multiscale_edges(img):
    """Multi-scale edge detection for better results"""
    try:
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Apply CLAHE for better contrast
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(gray)

        # Multiple scales of Gaussian blur and edge detection
        all_edges = np.zeros_like(enhanced)

        for sigma in [0.5, 1.0, 2.0]:
            blurred = cv2.GaussianBlur(enhanced, (0, 0), sigma)
            edges = cv2.Canny(blurred, 30, 90)
            all_edges = cv2.bitwise_or(all_edges, edges)

        # Morphological operations
        kernel = np.ones((5, 5), np.uint8)
        closed = cv2.morphologyEx(all_edges, cv2.MORPH_CLOSE, kernel, iterations=3)
        dilated = cv2.dilate(closed, kernel, iterations=1)

        # Find contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        return list(contours)
    except:
        return []


def remove_duplicate_candidates(candidates):
    """Remove near-duplicate polygons using IoU"""
    if len(candidates) <= 1:
        return candidates

    unique = []
    for i, cand1 in enumerate(candidates):
        is_duplicate = False
        for cand2 in unique:
            # Simple overlap check using bounding boxes
            pts1 = np.array([[p['x'], p['y']] for p in cand1['points']])
            pts2 = np.array([[p['x'], p['y']] for p in cand2['points']])

            x1_min, y1_min = pts1.min(axis=0)
            x1_max, y1_max = pts1.max(axis=0)
            x2_min, y2_min = pts2.min(axis=0)
            x2_max, y2_max = pts2.max(axis=0)

            # Calculate IoU of bounding boxes
            inter_x1 = max(x1_min, x2_min)
            inter_y1 = max(y1_min, y2_min)
            inter_x2 = min(x1_max, x2_max)
            inter_y2 = min(y1_max, y2_max)

            if inter_x2 > inter_x1 and inter_y2 > inter_y1:
                inter_area = (inter_x2 - inter_x1) * (inter_y2 - inter_y1)
                box1_area = (x1_max - x1_min) * (y1_max - y1_min)
                box2_area = (x2_max - x2_min) * (y2_max - y2_min)
                iou = inter_area / (box1_area + box2_area - inter_area)

                if iou > 0.7:  # High overlap threshold
                    is_duplicate = True
                    break

        if not is_duplicate:
            unique.append(cand1)

    return unique


def calculate_confidence_score(
    approx: np.ndarray,
    area: float,
    img_area: float,
    num_vertices: int,
    perimeter: float
) -> float:
    """
    Calculate confidence score for a detected polygon.
    Higher score = more likely to be a roof.

    Scoring factors:
    - Area percentage (roofs typically 10-60% of image)
    - Vertex count (4-6 vertices is ideal for roofs)
    - Compactness (area vs perimeter ratio)
    - Rectangularity (how close to a rectangle)
    """
    score = 0.0

    # 1. Area score (0-40 points) - More lenient
    area_ratio = area / img_area
    if 0.10 <= area_ratio <= 0.70:
        # Wider ideal range
        score += 40
    elif 0.05 <= area_ratio < 0.10 or 0.70 < area_ratio <= 0.85:
        # Acceptable range
        score += 30
    elif 0.02 <= area_ratio < 0.05 or 0.85 < area_ratio <= 0.95:
        # Still possible
        score += 20
    else:
        # Give some points anyway
        score += 10

    # 2. Vertex count score (0-30 points) - More lenient
    if num_vertices == 4:
        # Rectangular roof - most common
        score += 30
    elif num_vertices in [5, 6, 7, 8]:
        # Common polygon shapes
        score += 25
    elif num_vertices in [3, 9, 10]:
        # Also possible
        score += 20
    else:
        # Accept other shapes too
        score += 15

    # 3. Compactness score (0-20 points) - More lenient
    # Roofs can be various shapes
    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    if compactness > 0.5:
        # Reasonably compact
        score += 20
    elif compactness > 0.3:
        # Less compact but ok
        score += 15
    elif compactness > 0.1:
        # Elongated but possible
        score += 10
    else:
        # Very elongated
        score += 5

    # 4. Rectangularity score (0-10 points)
    if num_vertices == 4:
        # Check how close to a rectangle
        try:
            rect = cv2.minAreaRect(approx)
            rect_area = rect[1][0] * rect[1][1] if rect[1][0] > 0 and rect[1][1] > 0 else 1
            rectangularity = area / rect_area if rect_area > 0 else 0
            if rectangularity > 0.70:
                score += 10
            elif rectangularity > 0.50:
                score += 7
            else:
                score += 5
        except:
            score += 5
    else:
        # Not a rectangle, but that's ok
        score += 10

    # Normalize to 0-100
    return min(score, 100.0)


def detect_exclusion_zones(
    image_path: str,
    roof_polygon: List[Tuple[float, float]],
    min_area_ratio: float = 0.01
) -> Dict:
    """
    Detect potential exclusion zones (chimneys, vents, etc.) within the roof boundary.

    Args:
        image_path: Path to the uploaded roof image
        roof_polygon: The detected/confirmed roof boundary
        min_area_ratio: Minimum area as ratio of roof area (default: 1%)

    Returns:
        Dict containing detected exclusion zone candidates
    """
    try:
        img = cv2.imread(image_path)
        if img is None:
            return {"success": False, "error": "Failed to load image"}

        # Create mask of roof area
        roof_mask = np.zeros(img.shape[:2], dtype=np.uint8)
        roof_pts = np.array([[int(p[0]), int(p[1])] for p in roof_polygon], dtype=np.int32)
        cv2.fillPoly(roof_mask, [roof_pts], 255)

        # Apply mask to image
        masked_img = cv2.bitwise_and(img, img, mask=roof_mask)
        gray = cv2.cvtColor(masked_img, cv2.COLOR_BGR2GRAY)

        # Detect dark objects (chimneys, vents) using adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY_INV, 21, 10
        )

        # Remove noise
        kernel = np.ones((3, 3), np.uint8)
        cleaned = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(cleaned, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Calculate roof area
        roof_area = cv2.contourArea(roof_pts)
        min_area = roof_area * min_area_ratio

        exclusions = []
        for cnt in contours:
            area = cv2.contourArea(cnt)

            # Filter by size
            if area < min_area or area > roof_area * 0.2:  # Max 20% of roof
                continue

            # Approximate polygon
            perimeter = cv2.arcLength(cnt, True)
            epsilon = 0.02 * perimeter
            approx = cv2.approxPolyDP(cnt, epsilon, True)

            if len(approx) >= 3:  # At least a triangle
                points = [{"x": float(p[0][0]), "y": float(p[0][1])} for p in approx]
                exclusions.append({
                    "points": points,
                    "area_px": float(area),
                    "type": "detected_obstacle"
                })

        return {
            "success": True,
            "exclusions": exclusions,
            "count": len(exclusions)
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Exclusion detection failed: {str(e)}"
        }
