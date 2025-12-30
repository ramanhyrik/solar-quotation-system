"""
AI-Powered Roof Detection using MobileSAM
Lightweight version of Meta's Segment Anything Model
Model size: ~40MB (vs SAM's 2.4GB)
Memory usage: ~200-250MB
"""

import cv2
import numpy as np
import torch
from typing import List, Dict
import os
import urllib.request
from pathlib import Path

# Global model cache
_model_cache = None
_predictor_cache = None


def download_mobilesam_checkpoint():
    """Download MobileSAM checkpoint if not exists"""
    checkpoint_dir = Path("models")
    checkpoint_dir.mkdir(exist_ok=True)

    checkpoint_path = checkpoint_dir / "mobile_sam.pt"

    if checkpoint_path.exists():
        print(f"[MobileSAM] Using cached checkpoint: {checkpoint_path}")
        return str(checkpoint_path)

    print("[MobileSAM] Downloading checkpoint (~40MB)...")
    url = "https://github.com/ChaoningZhang/MobileSAM/raw/master/weights/mobile_sam.pt"

    try:
        urllib.request.urlretrieve(url, str(checkpoint_path))
        print(f"[MobileSAM] Checkpoint downloaded: {checkpoint_path}")
        return str(checkpoint_path)
    except Exception as e:
        print(f"[MobileSAM] Download failed: {e}")
        # Fallback to alternative approach
        return None


def get_mobilesam_predictor():
    """Load MobileSAM predictor (cached)"""
    global _model_cache, _predictor_cache

    if _predictor_cache is not None:
        return _predictor_cache

    try:
        from mobile_sam import sam_model_registry, SamPredictor

        print("[MobileSAM] Loading MobileSAM model...")

        # Download checkpoint if needed
        checkpoint_path = download_mobilesam_checkpoint()

        if checkpoint_path is None or not os.path.exists(checkpoint_path):
            print("[MobileSAM] Checkpoint not available, using fallback")
            return None

        # Load MobileSAM model
        model_type = "vit_t"  # MobileSAM uses tiny ViT
        device = torch.device("cpu")  # Use CPU (no GPU needed)

        sam = sam_model_registry[model_type](checkpoint=checkpoint_path)
        sam.to(device=device)
        sam.eval()

        # Create predictor
        predictor = SamPredictor(sam)

        _model_cache = sam
        _predictor_cache = predictor

        print("[MobileSAM] Model loaded successfully!")
        return predictor

    except Exception as e:
        print(f"[MobileSAM] Failed to load model: {e}")
        import traceback
        traceback.print_exc()
        return None


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
        print(f"[MobileSAM] Image loaded: {original_width}x{original_height}")

        # Convert BGR to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Get MobileSAM predictor
        predictor = get_mobilesam_predictor()

        if predictor is None:
            # Fallback to improved CV approach
            print("[MobileSAM] Model not available, using enhanced CV fallback")
            return fallback_cv_detection(img_rgb, original_width, original_height)

        # Set image for SAM
        predictor.set_image(img_rgb)

        # Generate automatic point prompts
        # Strategy: Use multiple points across center region
        h, w = original_height, original_width

        # Generate grid of positive points in center region
        point_coords = []
        point_labels = []

        # Center point (strongest positive)
        point_coords.append([w // 2, h // 2])
        point_labels.append(1)

        # Additional points in center region
        for offset_x in [-w//6, 0, w//6]:
            for offset_y in [-h//6, 0, h//6]:
                if offset_x == 0 and offset_y == 0:
                    continue  # Skip center (already added)
                x = w // 2 + offset_x
                y = h // 2 + offset_y
                point_coords.append([x, y])
                point_labels.append(1)

        # Add negative points at edges (avoid capturing entire image)
        # Top edge
        point_coords.append([w // 2, 20])
        point_labels.append(0)
        # Bottom edge
        point_coords.append([w // 2, h - 20])
        point_labels.append(0)
        # Left edge
        point_coords.append([20, h // 2])
        point_labels.append(0)
        # Right edge
        point_coords.append([w - 20, h // 2])
        point_labels.append(0)

        point_coords = np.array(point_coords)
        point_labels = np.array(point_labels)

        print(f"[MobileSAM] Using {len(point_coords)} point prompts ({sum(point_labels)} positive, {len(point_labels) - sum(point_labels)} negative)")

        # Predict masks
        masks, scores, logits = predictor.predict(
            point_coords=point_coords,
            point_labels=point_labels,
            multimask_output=True  # Get 3 mask proposals
        )

        print(f"[MobileSAM] Generated {len(masks)} masks with scores: {scores}")

        # Process masks into polygon candidates
        candidates = []
        img_area = original_width * original_height

        for idx, (mask, score) in enumerate(zip(masks, scores)):
            # Convert mask to uint8
            mask_uint8 = (mask * 255).astype(np.uint8)

            # Find contours in mask
            contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                continue

            # Get largest contour (main roof)
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            area_ratio = area / img_area

            # Filter by area (5% to 85% of image)
            if area < img_area * 0.05 or area > img_area * 0.85:
                continue

            # Approximate polygon
            perimeter = cv2.arcLength(largest_contour, True)

            # Try multiple approximation levels
            for epsilon_factor in [0.002, 0.005, 0.01]:
                epsilon = epsilon_factor * perimeter
                approx = cv2.approxPolyDP(largest_contour, epsilon, True)
                num_vertices = len(approx)

                if 4 <= num_vertices <= 20:
                    # Extract points
                    points = []
                    for point in approx:
                        x, y = point[0]
                        points.append({"x": float(x), "y": float(y)})

                    # Calculate confidence (SAM score + shape quality)
                    confidence = calculate_sam_confidence(
                        score, area, area_ratio, num_vertices, perimeter
                    )

                    candidates.append({
                        "points": points,
                        "vertices": num_vertices,
                        "area_px": float(area),
                        "area_ratio": float(area_ratio),
                        "confidence": float(confidence),
                        "perimeter": float(perimeter),
                        "sam_score": float(score)
                    })
                    break

        if len(candidates) == 0:
            return {
                "success": True,
                "candidates": [],
                "message": "No suitable roof boundaries found. Try manual drawing.",
                "debug_info": "SAM masks did not produce valid polygons"
            }

        # Sort by confidence
        candidates.sort(key=lambda x: x['confidence'], reverse=True)

        # Return best candidate
        top_candidates = candidates[:max_candidates]

        for i, c in enumerate(top_candidates):
            print(f"[MobileSAM] Candidate {i+1}: {c['vertices']} vertices, "
                  f"area={c['area_ratio']*100:.1f}%, confidence={c['confidence']:.1f}%, "
                  f"SAM score={c['sam_score']:.3f}")

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


def fallback_cv_detection(img_rgb, width, height):
    """
    Enhanced CV fallback when MobileSAM is not available.
    Uses multiple strategies with better filtering.
    """
    print("[FALLBACK] Using enhanced computer vision detection")

    img_bgr = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2BGR)
    img_area = width * height

    # Strategy 1: Adaptive threshold + largest component
    gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)

    # Apply CLAHE
    clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Adaptive threshold
    binary = cv2.adaptiveThreshold(
        enhanced, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV, 21, 5
    )

    # Morphological operations
    kernel = np.ones((9, 9), np.uint8)
    binary = cv2.morphologyEx(binary, cv2.MORPH_CLOSE, kernel, iterations=3)
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=2)

    # Find largest connected component
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(binary, connectivity=8)

    if num_labels > 1:
        # Get largest component (excluding background)
        largest_idx = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
        mask = (labels == largest_idx).astype(np.uint8) * 255
    else:
        mask = binary

    # Find contours
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return {
            "success": True,
            "candidates": [],
            "message": "No roof detected. Please try manual drawing.",
            "debug_info": "Fallback CV found no contours"
        }

    # Get largest contour
    largest_contour = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest_contour)
    area_ratio = area / img_area

    if area < img_area * 0.05 or area > img_area * 0.85:
        return {
            "success": True,
            "candidates": [],
            "message": "Detected region too small/large. Try manual drawing.",
            "debug_info": f"Area ratio {area_ratio:.2%} outside valid range"
        }

    # Approximate polygon
    perimeter = cv2.arcLength(largest_contour, True)

    for epsilon_factor in [0.002, 0.005, 0.01, 0.02]:
        epsilon = epsilon_factor * perimeter
        approx = cv2.approxPolyDP(largest_contour, epsilon, True)
        num_vertices = len(approx)

        if 4 <= num_vertices <= 15:
            points = []
            for point in approx:
                x, y = point[0]
                points.append({"x": float(x), "y": float(y)})

            confidence = 60.0  # Lower confidence for fallback

            candidate = {
                "points": points,
                "vertices": num_vertices,
                "area_px": float(area),
                "area_ratio": float(area_ratio),
                "confidence": confidence,
                "perimeter": float(perimeter)
            }

            print(f"[FALLBACK] Detected roof: {num_vertices} vertices, area={area_ratio*100:.1f}%")

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
        "debug_info": "Polygon approximation failed"
    }


def calculate_sam_confidence(sam_score, area, area_ratio, num_vertices, perimeter):
    """Calculate confidence score combining SAM score with shape quality"""

    # SAM score (0-50 points) - SAM's own confidence
    sam_points = min(sam_score * 50, 50)

    # Area score (0-25 points)
    if 0.10 <= area_ratio <= 0.65:
        area_points = 25
    elif 0.05 <= area_ratio < 0.10 or 0.65 < area_ratio <= 0.80:
        area_points = 15
    else:
        area_points = 5

    # Vertex count (0-15 points)
    if 4 <= num_vertices <= 6:
        vertex_points = 15
    elif 7 <= num_vertices <= 10:
        vertex_points = 10
    else:
        vertex_points = 5

    # Compactness (0-10 points)
    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    if compactness > 0.4:
        compact_points = 10
    elif compactness > 0.2:
        compact_points = 7
    else:
        compact_points = 3

    total = sam_points + area_points + vertex_points + compact_points
    return min(total, 100.0)
