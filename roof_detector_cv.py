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
    Automatically detect roof boundaries using edge detection and contour finding.
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

        # Resize for faster processing (max 1024px)
        scale = 1.0
        if max(original_width, original_height) > 1024:
            scale = 1024 / max(original_width, original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            img = cv2.resize(img, (new_width, new_height))
            print(f"[AI-DETECT] Resized to: {new_width}x{new_height}, scale={scale:.3f}")

        # Convert to grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Apply Gaussian blur to reduce noise
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Try multiple edge detection strategies
        # Strategy 1: Lower threshold Canny (more lenient)
        edges1 = cv2.Canny(blurred, 20, 60)

        # Strategy 2: Adaptive thresholding
        thresh = cv2.adaptiveThreshold(blurred, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                       cv2.THRESH_BINARY_INV, 11, 2)

        # Combine both strategies
        edges = cv2.bitwise_or(edges1, thresh)

        # Morphological operations to close gaps
        kernel = np.ones((5, 5), np.uint8)
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=3)

        # Dilate to connect nearby edges
        dilated = cv2.dilate(closed, kernel, iterations=2)

        # Find contours
        contours, _ = cv2.findContours(dilated, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        print(f"[AI-DETECT] Found {len(contours)} total contours")

        if not contours:
            return {
                "success": True,
                "candidates": [],
                "message": "No contours detected. Try adjusting image quality or contrast.",
                "debug_info": "No contours found after edge detection"
            }

        # Process and score candidates
        candidates = []
        img_area = img.shape[0] * img.shape[1]
        print(f"[AI-DETECT] Image area: {img_area}px")

        filtered_count = 0
        for idx, cnt in enumerate(contours):
            area = cv2.contourArea(cnt)
            area_ratio = area / img_area

            # More lenient area filtering (2% to 98%)
            if area < img_area * 0.02:
                filtered_count += 1
                continue

            if area > img_area * 0.98:
                filtered_count += 1
                continue

            # Approximate polygon using Douglas-Peucker algorithm
            perimeter = cv2.arcLength(cnt, True)

            # Try multiple epsilon values for polygon approximation
            for epsilon_factor in [0.002, 0.005, 0.01, 0.02]:
                epsilon = epsilon_factor * perimeter
                approx = cv2.approxPolyDP(cnt, epsilon, True)
                num_vertices = len(approx)

                # More lenient vertex count (3-20 vertices)
                if 3 <= num_vertices <= 20:
                    # Calculate confidence score
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
                        "area_px": float(area / (scale * scale)),  # Scale area back
                        "area_ratio": float(area_ratio),
                        "confidence": float(confidence),
                        "perimeter": float(perimeter / scale),
                        "epsilon_factor": epsilon_factor
                    })

                    # Use the first successful approximation
                    break

        print(f"[AI-DETECT] Filtered {filtered_count} contours (too small/large)")
        print(f"[AI-DETECT] Generated {len(candidates)} candidates")

        if len(candidates) == 0:
            return {
                "success": True,
                "candidates": [],
                "message": "No suitable roof boundaries found. Try a clearer image or manual drawing.",
                "debug_info": f"Found {len(contours)} contours but none matched criteria"
            }

        # Sort by confidence (highest first)
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
