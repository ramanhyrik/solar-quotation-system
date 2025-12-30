"""
AI-Powered Roof Detection using MobileSAM
Lightweight SAM model (40MB) for accurate roof boundary detection
Memory usage: ~150-200MB total
"""

import cv2
import numpy as np
from typing import List, Dict
import os


# Global model cache to avoid reloading
_model_cache = None


def get_mobilesam_model():
    """Load MobileSAM model (cached)"""
    global _model_cache

    if _model_cache is not None:
        return _model_cache

    print("[MOBILE-SAM] Loading MobileSAM model...")

    try:
        from ultralytics import SAM

        # Load MobileSAM (will auto-download on first use)
        model = SAM("mobile_sam.pt")

        _model_cache = model
        print("[MOBILE-SAM] Model loaded successfully!")

        return model
    except Exception as e:
        print(f"[MOBILE-SAM] Error loading model: {str(e)}")
        raise


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 1) -> Dict:
    """
    Detect roof boundaries using MobileSAM.

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
        print(f"[MOBILE-SAM] Image loaded: {original_width}x{original_height}")

        # Get MobileSAM model
        model = get_mobilesam_model()

        # Strategy: Use center point prompt
        # Assume the target building is in the center of the aerial image
        center_x = original_width // 2
        center_y = original_height // 2

        print(f"[MOBILE-SAM] Running segmentation with center point prompt ({center_x}, {center_y})")

        # Run MobileSAM with point prompt
        results = model(
            image_path,
            points=[[center_x, center_y]],
            labels=[1]  # 1 = foreground point
        )

        # Extract masks from results
        if not results or len(results) == 0:
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please try manual drawing.",
                "debug_info": "MobileSAM returned no results"
            }

        # Get the first result (single image)
        result = results[0]

        # Check if masks exist
        if not hasattr(result, 'masks') or result.masks is None or len(result.masks) == 0:
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please try manual drawing.",
                "debug_info": "MobileSAM returned no masks"
            }

        # Extract mask data
        masks = result.masks.data.cpu().numpy()  # Shape: (N, H, W)

        print(f"[MOBILE-SAM] Generated {len(masks)} mask(s)")

        # Process masks into polygon candidates
        candidates = []
        img_area = original_width * original_height

        for idx, mask in enumerate(masks):
            # Convert mask to uint8 (0-255)
            mask_uint8 = (mask * 255).astype(np.uint8)

            # Find contours in the mask
            contours, _ = cv2.findContours(
                mask_uint8,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )

            if not contours:
                continue

            # Get largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            area_ratio = area / img_area

            # Filter by area (5% to 85% of image)
            if area < img_area * 0.05 or area > img_area * 0.85:
                print(f"[MOBILE-SAM] Mask {idx} rejected: area_ratio={area_ratio:.2%}")
                continue

            # Approximate polygon with multiple epsilon values
            perimeter = cv2.arcLength(largest_contour, True)

            for epsilon_factor in [0.001, 0.003, 0.005, 0.008, 0.01, 0.015]:
                epsilon = epsilon_factor * perimeter
                approx = cv2.approxPolyDP(largest_contour, epsilon, True)
                num_vertices = len(approx)

                # Accept polygons with 4-12 vertices
                if 4 <= num_vertices <= 12:
                    # Extract points
                    points = []
                    for point in approx:
                        x, y = point[0]
                        points.append({"x": float(x), "y": float(y)})

                    # Calculate confidence based on SAM quality
                    confidence = calculate_sam_confidence(
                        area_ratio, num_vertices, perimeter, area, mask
                    )

                    candidates.append({
                        "points": points,
                        "vertices": num_vertices,
                        "area_px": float(area),
                        "area_ratio": float(area_ratio),
                        "confidence": float(confidence),
                        "perimeter": float(perimeter),
                        "mask_index": idx
                    })

                    print(f"[MOBILE-SAM] Candidate {len(candidates)}: {num_vertices} vertices, "
                          f"area={area_ratio*100:.1f}%, confidence={confidence:.1f}%")
                    break

        if len(candidates) == 0:
            return {
                "success": True,
                "candidates": [],
                "message": "No suitable roof shapes found. Try manual drawing.",
                "debug_info": "MobileSAM masks did not meet quality criteria"
            }

        # Sort by confidence
        candidates.sort(key=lambda x: x['confidence'], reverse=True)

        # Return top candidate(s)
        top_candidates = candidates[:max_candidates]

        print(f"[MOBILE-SAM] Returning {len(top_candidates)} candidate(s)")

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
            "error": f"MobileSAM detection failed: {str(e)}"
        }


def calculate_sam_confidence(area_ratio, num_vertices, perimeter, area, mask):
    """
    Calculate confidence score for MobileSAM detection.
    MobileSAM produces high-quality masks, so scoring is more lenient.
    """
    score = 0.0

    # Area score (0-40 points)
    if 0.10 <= area_ratio <= 0.60:
        score += 40
    elif 0.05 <= area_ratio < 0.10 or 0.60 < area_ratio <= 0.75:
        score += 35
    else:
        score += 25

    # Vertex count (0-30 points)
    if 4 <= num_vertices <= 6:
        score += 30
    elif 7 <= num_vertices <= 10:
        score += 28
    else:
        score += 20

    # Compactness (0-20 points)
    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    if compactness > 0.4:
        score += 20
    elif compactness > 0.25:
        score += 15
    else:
        score += 10

    # Mask quality (0-10 points) - SAM produces clean masks
    # Check mask fill ratio (how solid the mask is)
    mask_fill_ratio = np.sum(mask > 0.5) / mask.size
    if mask_fill_ratio > 0.3:
        score += 10
    elif mask_fill_ratio > 0.15:
        score += 7
    else:
        score += 5

    return min(score, 100.0)
