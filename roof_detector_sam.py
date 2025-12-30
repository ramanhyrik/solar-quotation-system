"""
AI-Powered Roof Detection using Advanced Computer Vision
Optimized algorithms for accurate roof boundary detection
Memory usage: ~50-100MB
"""

import cv2
import numpy as np
from typing import List, Dict
import os


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 1) -> Dict:
    """
    Detect roof boundaries using advanced computer vision techniques.

    Args:
        image_path: Path to the uploaded roof image
        max_candidates: Number of candidates to return (default: 1)

    Returns:
        Dict containing success, candidates, and metadata
    """
    try:
        # Load image
        if not os.path.exists(image_path):
            return {"success": False, "error": "Image file not found"}

        img = cv2.imread(image_path)
        if img is None:
            return {"success": False, "error": "Failed to load image"}

        original_height, original_width = img.shape[:2]
        print(f"[ROOF-DETECT] Image loaded: {original_width}x{original_height}")

        # Use enhanced CV detection
        return enhanced_cv_detection(img, original_width, original_height)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Roof detection failed: {str(e)}"
        }


def enhanced_cv_detection(img, width, height):
    """
    Enhanced computer vision detection using multiple strategies.
    Optimized for aerial roof detection.
    """
    print("[ROOF-DETECT] Using enhanced CV detection with 3 strategies")

    img_area = width * height
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # === Strategy 1: Watershed + Center Focus ===
    print("[ROOF-DETECT] Strategy 1: Watershed segmentation")
    mask1 = detect_using_watershed(img, gray, width, height)

    # === Strategy 2: Enhanced CLAHE + Adaptive Threshold ===
    print("[ROOF-DETECT] Strategy 2: CLAHE + Adaptive threshold")
    mask2 = detect_using_clahe_adaptive(gray)

    # === Strategy 3: Color-based with center bias ===
    print("[ROOF-DETECT] Strategy 3: Color segmentation with center bias")
    mask3 = detect_using_color_center(img, width, height)

    # Combine masks using voting
    combined_mask = combine_masks([mask1, mask2, mask3])

    if combined_mask is None or combined_mask.sum() == 0:
        return {
            "success": True,
            "candidates": [],
            "message": "No roof detected. Please try manual drawing.",
            "debug_info": "All strategies failed to find roof"
        }

    # Find contours in combined mask
    contours, _ = cv2.findContours(combined_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return {
            "success": True,
            "candidates": [],
            "message": "No contours found. Try manual drawing.",
            "debug_info": "No contours in combined mask"
        }

    # Get largest contour
    largest_contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest_contour)
    area_ratio = area / img_area

    if area < img_area * 0.05 or area > img_area * 0.85:
        return {
            "success": True,
            "candidates": [],
            "message": "Detected region size invalid. Try manual drawing.",
            "debug_info": f"Area ratio {area_ratio:.2%} outside 5-85% range"
        }

    # Approximate polygon with multiple attempts
    perimeter = cv2.arcLength(largest_contour, True)

    for epsilon_factor in [0.001, 0.003, 0.005, 0.008, 0.01, 0.015]:
        epsilon = epsilon_factor * perimeter
        approx = cv2.approxPolyDP(largest_contour, epsilon, True)
        num_vertices = len(approx)

        if 4 <= num_vertices <= 12:
            points = []
            for point in approx:
                x, y = point[0]
                points.append({"x": float(x), "y": float(y)})

            # Calculate confidence based on detection quality
            confidence = calculate_cv_confidence(area_ratio, num_vertices, perimeter, area)

            candidate = {
                "points": points,
                "vertices": num_vertices,
                "area_px": float(area),
                "area_ratio": float(area_ratio),
                "confidence": float(confidence),
                "perimeter": float(perimeter)
            }

            print(f"[ROOF-DETECT] Success: {num_vertices} vertices, area={area_ratio*100:.1f}%, confidence={confidence:.1f}%")

            return {
                "success": True,
                "candidates": [candidate],
                "total_found": 1,
                "image_dimensions": {"width": width, "height": height}
            }

    return {
        "success": True,
        "candidates": [],
        "message": "Could not create valid polygon. Try manual drawing.",
        "debug_info": "Polygon approximation failed for all epsilon values"
    }


def detect_using_watershed(img, gray, width, height):
    """Watershed segmentation focused on center region"""
    # Create markers for watershed
    ret, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    # Noise removal
    kernel = np.ones((5, 5), np.uint8)
    opening = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=2)

    # Sure background area
    sure_bg = cv2.dilate(opening, kernel, iterations=3)

    # Sure foreground area (center region)
    dist_transform = cv2.distanceTransform(opening, cv2.DIST_L2, 5)
    ret, sure_fg = cv2.threshold(dist_transform, 0.4*dist_transform.max(), 255, 0)

    # Unknown region
    sure_fg = np.uint8(sure_fg)
    unknown = cv2.subtract(sure_bg, sure_fg)

    # Marker labelling
    ret, markers = cv2.connectedComponents(sure_fg)

    # Add one to all labels so background is not 0, but 1
    markers = markers + 1

    # Mark unknown region as 0
    markers[unknown == 255] = 0

    # Apply watershed
    markers = cv2.watershed(img, markers)

    # Create mask from markers
    mask = np.zeros(gray.shape, dtype=np.uint8)
    mask[markers > 1] = 255

    return mask


def detect_using_clahe_adaptive(gray):
    """CLAHE with adaptive thresholding"""
    # Apply CLAHE for contrast enhancement
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Adaptive threshold
    binary = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 21, 5
    )

    # Morphological operations to clean up
    kernel = np.ones((7, 7), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=3)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)

    # Get largest component
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    if num_labels > 1:
        largest_idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        mask = (labels == largest_idx).astype(np.uint8) * 255
    else:
        mask = binary

    return mask


def detect_using_color_center(img, width, height):
    """Color segmentation with center region bias"""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    # Sample center region
    h, w = img.shape[:2]
    center_region = hsv[int(h*0.35):int(h*0.65), int(w*0.35):int(w*0.65)]

    mean_hue = np.mean(center_region[:, :, 0])
    mean_sat = np.mean(center_region[:, :, 1])
    mean_val = np.mean(center_region[:, :, 2])

    # Create mask for similar colors
    lower = np.array([max(0, mean_hue - 25), max(0, mean_sat - 60), max(0, mean_val - 60)])
    upper = np.array([min(180, mean_hue + 25), min(255, mean_sat + 60), min(255, mean_val + 60)])

    mask = cv2.inRange(hsv, lower, upper)

    # Clean up
    kernel = np.ones((7, 7), np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)

    return mask


def combine_masks(masks):
    """Combine multiple masks using voting - pixels present in 2+ masks"""
    if not masks or len(masks) == 0:
        return None

    # Stack masks
    stacked = np.stack([m for m in masks if m is not None], axis=-1)

    if stacked.size == 0:
        return None

    # Voting: pixel is 1 if present in at least 2 masks
    votes = np.sum(stacked > 0, axis=-1)
    combined = ((votes >= 2) * 255).astype(np.uint8)

    # Final cleanup
    kernel = np.ones((5, 5), np.uint8)
    combined = cv2.morphologyEx(combined, cv2.MORPH_CLOSE, kernel, iterations=2)

    return combined


def calculate_cv_confidence(area_ratio, num_vertices, perimeter, area):
    """Calculate confidence score for CV detection"""
    score = 0.0

    # Area score (0-40 points)
    if 0.10 <= area_ratio <= 0.60:
        score += 40
    elif 0.05 <= area_ratio < 0.10 or 0.60 < area_ratio <= 0.75:
        score += 30
    else:
        score += 15

    # Vertex count (0-30 points)
    if 4 <= num_vertices <= 6:
        score += 30
    elif 7 <= num_vertices <= 10:
        score += 25
    else:
        score += 15

    # Compactness (0-30 points)
    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    if compactness > 0.4:
        score += 30
    elif compactness > 0.25:
        score += 20
    else:
        score += 10

    return min(score, 100.0)
