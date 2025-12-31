"""
AI-Powered Roof Detection using SAM 3 on HuggingFace Spaces
Zero memory on server - all processing done on HF Spaces (100% FREE)

SAM 3 - Segment Anything Model 3 (November 2025)
- Text-based semantic segmentation with Promptable Concept Segmentation (PCS)
- 848M parameters - SOTA accuracy (2x better than SAM 2)
- Single unified model (faster than Grounded SAM)
- Perfect for aerial/satellite imagery!
"""

import cv2
import numpy as np
from typing import List, Dict
import os
import gc
import requests
from io import BytesIO
from PIL import Image


# HuggingFace Space API URL
HF_SPACE_API_URL = "https://ramankamran-mobilesam-roof-api.hf.space/detect-roof"


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 1) -> Dict:
    """
    Detect roof boundaries using SAM 3 on HuggingFace Spaces.

    Uses SAM 3 (Segment Anything Model 3) for semantic roof detection:
    - Text-based Promptable Concept Segmentation (PCS)
    - 848M parameters - SOTA accuracy (2x better than SAM 2)
    - Single unified model (faster than Grounded SAM)
    - Works great on aerial/satellite images!

    Zero memory on server - 100% FREE - No API keys required!

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
        print(f"[SAM3] Image loaded: {original_width}x{original_height}")

        # Resize image to reduce upload size (max 1024px)
        max_dimension = 1024
        scale = 1.0

        if max(original_width, original_height) > max_dimension:
            scale = max_dimension / max(original_width, original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            img_resized = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
            print(f"[SAM3] Resized for API: {new_width}x{new_height} (scale={scale:.3f})")
        else:
            img_resized = img
            print(f"[SAM3] No resize needed (already <= {max_dimension}px)")

        # Free original image
        del img
        gc.collect()

        # Convert to RGB and encode as JPEG
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)

        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=90)
        buffer.seek(0)

        # Free resized image
        del img_resized, img_rgb, pil_image
        gc.collect()

        # Call HuggingFace Space API (SAM 3)
        print("[SAM3] Calling HuggingFace Space API (SAM 3)...")

        try:
            files = {"file": ("roof.jpg", buffer, "image/jpeg")}
            response = requests.post(
                HF_SPACE_API_URL,
                files=files,
                timeout=120  # 2 minutes (HF Spaces may wake up from sleep)
            )

            print(f"[SAM3] API response status: {response.status_code}")

            if response.status_code == 503:
                # Space is starting up (cold start)
                return {
                    "success": True,
                    "candidates": [],
                    "message": "AI model is starting up. Please try again in 30 seconds.",
                    "debug_info": "HF Space cold start (503)"
                }

            if response.status_code != 200:
                error_msg = response.text[:200] if response.text else "Unknown error"
                print(f"[SAM3] API error: {error_msg}")
                return {
                    "success": True,
                    "candidates": [],
                    "message": f"AI detection failed ({response.status_code}). Please use manual drawing.",
                    "debug_info": error_msg
                }

            # Parse response
            result = response.json()

            if not result.get("success"):
                return {
                    "success": True,
                    "candidates": [],
                    "message": "No roof detected. Please use manual drawing.",
                    "debug_info": "API returned success=false"
                }

            candidates = result.get("candidates", [])

            # Scale candidates back to original image size if we resized
            if scale != 1.0:
                for candidate in candidates:
                    for point in candidate.get("points", []):
                        point["x"] = point["x"] / scale
                        point["y"] = point["y"] / scale

                    # Recalculate area for original size
                    if "area_px" in candidate:
                        candidate["area_px"] = candidate["area_px"] / (scale * scale)

            if candidates:
                top_candidates = candidates[:max_candidates]
                print(f"[SAM3] SUCCESS - {len(top_candidates)} candidate(s)")
                return {
                    "success": True,
                    "candidates": top_candidates,
                    "total_found": len(candidates),
                    "strategy_used": "SAM 3 (Segment Anything Model 3) - Text-based PCS - 2x Better Accuracy!",
                    "image_dimensions": {
                        "width": original_width,
                        "height": original_height
                    }
                }
            else:
                print("[SAM3] No valid roof candidates")
                return {
                    "success": True,
                    "candidates": [],
                    "message": "No roof detected. Please use manual drawing.",
                    "debug_info": "API returned empty candidates"
                }

        except requests.exceptions.Timeout:
            print("[SAM3] API timeout")
            return {
                "success": True,
                "candidates": [],
                "message": "AI detection timed out. The service may be starting up. Please try again.",
                "debug_info": "HF Space timeout (120s)"
            }

        except requests.exceptions.RequestException as e:
            print(f"[SAM3] API request failed: {str(e)}")
            return {
                "success": True,
                "candidates": [],
                "message": "Cannot connect to AI service. Please use manual drawing.",
                "debug_info": f"Network error: {str(e)}"
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Detection failed: {str(e)}"
        }
