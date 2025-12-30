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
        print("[MOBILE-SAM] Using cached model")
        return _model_cache

    print("[MOBILE-SAM] Loading MobileSAM model...")

    try:
        from ultralytics import SAM
        print("[MOBILE-SAM] Ultralytics imported successfully")

        # Load MobileSAM (will auto-download on first use)
        print("[MOBILE-SAM] Initializing SAM('mobile_sam.pt')...")
        model = SAM("mobile_sam.pt")
        print(f"[MOBILE-SAM] Model object created: {type(model)}")

        _model_cache = model
        print("[MOBILE-SAM] Model loaded and cached successfully!")

        return model
    except Exception as e:
        print(f"[MOBILE-SAM] CRITICAL ERROR loading model: {str(e)}")
        import traceback
        traceback.print_exc()
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

        # Resize image for faster inference (critical for CPU)
        # MobileSAM works well at lower resolutions, and CPU inference is VERY slow
        # Using 256px for maximum speed on CPU-only inference (4x faster than 512px)
        max_dimension = 256  # Aggressive resize for sub-30s inference
        scale = 1.0

        if max(original_width, original_height) > max_dimension:
            scale = max_dimension / max(original_width, original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            img_resized = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
            print(f"[MOBILE-SAM] Resized for inference: {new_width}x{new_height} (scale={scale:.3f})")
        else:
            img_resized = img
            new_width = original_width
            new_height = original_height
            print(f"[MOBILE-SAM] No resize needed (already <= {max_dimension}px)")

        # Save resized image temporarily for SAM
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.jpg', delete=False) as tmp:
            temp_path = tmp.name
            cv2.imwrite(temp_path, img_resized)
            print(f"[MOBILE-SAM] Saved temp resized image: {temp_path}")

        # Get MobileSAM model
        print("[MOBILE-SAM] Getting model...")
        model = get_mobilesam_model()
        print("[MOBILE-SAM] Model retrieved")

        # Strategy: Use center point prompt on resized image
        # Assume the target building is in the center of the aerial image
        center_x = new_width // 2
        center_y = new_height // 2

        print(f"[MOBILE-SAM] Running segmentation with center point prompt ({center_x}, {center_y})")
        print(f"[MOBILE-SAM] Using temp resized image for inference")
        print(f"[MOBILE-SAM] Calling model.predict()...")

        # Run MobileSAM with point prompt (single point syntax: points=[x, y])
        try:
            results = model.predict(
                temp_path,  # Use resized temp image
                points=[center_x, center_y],  # Single point: flat list [x, y]
                labels=[1],  # 1 = foreground point
                verbose=False  # Reduce output
            )
            print(f"[MOBILE-SAM] Model call completed. Results type: {type(results)}")
            print(f"[MOBILE-SAM] Results length: {len(results) if results else 'None'}")

            # Clean up temp file
            import os as os_module
            os_module.unlink(temp_path)
            print(f"[MOBILE-SAM] Cleaned up temp file")

        except Exception as e:
            print(f"[MOBILE-SAM] ERROR during model inference: {str(e)}")
            # Clean up temp file on error
            import os as os_module
            if os_module.path.exists(temp_path):
                os_module.unlink(temp_path)
            import traceback
            traceback.print_exc()
            raise

        # Extract masks from results
        if not results or len(results) == 0:
            print("[MOBILE-SAM] No results returned from model")
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please try manual drawing.",
                "debug_info": "MobileSAM returned no results"
            }

        # Get the first result (single image)
        result = results[0]
        print(f"[MOBILE-SAM] First result type: {type(result)}")
        print(f"[MOBILE-SAM] First result attributes: {dir(result)}")

        # Check if masks exist
        if not hasattr(result, 'masks'):
            print("[MOBILE-SAM] Result has no 'masks' attribute")
            print(f"[MOBILE-SAM] Available attributes: {[a for a in dir(result) if not a.startswith('_')]}")
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please try manual drawing.",
                "debug_info": "MobileSAM result has no masks attribute"
            }

        if result.masks is None:
            print("[MOBILE-SAM] result.masks is None")
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please try manual drawing.",
                "debug_info": "MobileSAM returned None masks"
            }

        if len(result.masks) == 0:
            print("[MOBILE-SAM] result.masks is empty")
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please try manual drawing.",
                "debug_info": "MobileSAM returned zero masks"
            }

        # Extract mask data
        print(f"[MOBILE-SAM] Extracting mask data...")
        masks = result.masks.data.cpu().numpy()  # Shape: (N, H, W)
        print(f"[MOBILE-SAM] Masks shape: {masks.shape}")
        print(f"[MOBILE-SAM] Generated {len(masks)} mask(s)")

        # Process masks into polygon candidates
        candidates = []
        img_area = original_width * original_height
        resized_img_area = new_width * new_height

        for idx, mask in enumerate(masks):
            print(f"[MOBILE-SAM] Processing mask {idx}, shape: {mask.shape}, dtype: {mask.dtype}")

            # Convert mask to uint8 (0-255)
            mask_uint8 = (mask * 255).astype(np.uint8)
            print(f"[MOBILE-SAM] Converted to uint8, unique values: {np.unique(mask_uint8)[:10]}")

            # Find contours in the mask
            contours, _ = cv2.findContours(
                mask_uint8,
                cv2.RETR_EXTERNAL,
                cv2.CHAIN_APPROX_SIMPLE
            )
            print(f"[MOBILE-SAM] Found {len(contours)} contours in mask {idx}")

            if not contours:
                print(f"[MOBILE-SAM] No contours in mask {idx}, skipping")
                continue

            # Get largest contour
            largest_contour = max(contours, key=cv2.contourArea)
            area = cv2.contourArea(largest_contour)
            # Calculate area ratio based on RESIZED image for filtering
            area_ratio_resized = area / resized_img_area
            # Calculate actual area in original image coordinates
            area_original = area / (scale * scale) if scale != 1.0 else area
            area_ratio_original = area_original / img_area
            print(f"[MOBILE-SAM] Mask {idx}: contour area={area:.0f} (resized), "
                  f"ratio={area_ratio_resized:.2%} (resized), "
                  f"original_ratio={area_ratio_original:.2%}")

            # Filter by area (5% to 85% of RESIZED image for consistency)
            if area_ratio_resized < 0.05 or area_ratio_resized > 0.85:
                print(f"[MOBILE-SAM] Mask {idx} rejected: area_ratio={area_ratio_resized:.2%} outside 5-85% range")
                continue

            # Approximate polygon with multiple epsilon values
            perimeter = cv2.arcLength(largest_contour, True)
            print(f"[MOBILE-SAM] Contour perimeter: {perimeter:.1f}")

            polygon_found = False
            for epsilon_factor in [0.001, 0.003, 0.005, 0.008, 0.01, 0.015]:
                epsilon = epsilon_factor * perimeter
                approx = cv2.approxPolyDP(largest_contour, epsilon, True)
                num_vertices = len(approx)

                print(f"[MOBILE-SAM] epsilon_factor={epsilon_factor:.3f}, vertices={num_vertices}")

                # Accept polygons with 4-12 vertices
                if 4 <= num_vertices <= 12:
                    # Extract points and scale back to original image coordinates
                    points = []
                    for point in approx:
                        x, y = point[0]
                        # Scale coordinates back to original image size
                        if scale != 1.0:
                            x_original = x / scale
                            y_original = y / scale
                        else:
                            x_original = x
                            y_original = y
                        points.append({"x": float(x_original), "y": float(y_original)})

                    # Calculate confidence based on SAM quality (use original area ratio)
                    confidence = calculate_sam_confidence(
                        area_ratio_original, num_vertices, perimeter, area, mask
                    )

                    # Store values in original image coordinates
                    perimeter_original = perimeter / scale if scale != 1.0 else perimeter

                    candidates.append({
                        "points": points,  # Already scaled to original coordinates
                        "vertices": num_vertices,
                        "area_px": float(area_original),  # Original image area
                        "area_ratio": float(area_ratio_original),  # Original ratio
                        "confidence": float(confidence),
                        "perimeter": float(perimeter_original),  # Original perimeter
                        "mask_index": idx
                    })

                    print(f"[MOBILE-SAM] ✓ Candidate {len(candidates)} created: {num_vertices} vertices, "
                          f"area={area_ratio_original*100:.1f}%, confidence={confidence:.1f}%")
                    polygon_found = True
                    break

            if not polygon_found:
                print(f"[MOBILE-SAM] Mask {idx}: No suitable polygon found with 4-12 vertices")

        if len(candidates) == 0:
            print("[MOBILE-SAM] No candidates created - returning empty result")
            return {
                "success": True,
                "candidates": [],
                "message": "No suitable roof shapes found. Try manual drawing.",
                "debug_info": "MobileSAM masks did not meet quality criteria"
            }

        # Sort by confidence
        print(f"[MOBILE-SAM] Sorting {len(candidates)} candidates by confidence...")
        candidates.sort(key=lambda x: x['confidence'], reverse=True)

        # Return top candidate(s)
        top_candidates = candidates[:max_candidates]

        print(f"[MOBILE-SAM] ✓ SUCCESS - Returning {len(top_candidates)} candidate(s)")
        for i, c in enumerate(top_candidates):
            print(f"[MOBILE-SAM]   #{i+1}: {c['vertices']} vertices, conf={c['confidence']:.1f}%")

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
