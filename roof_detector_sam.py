"""
AI-Powered Roof Detection using Hugging Face Inference API
Zero memory on server - all processing done on HF servers
Free tier: 30,000 requests/month
"""

import cv2
import numpy as np
from typing import List, Dict
import os
import gc
import requests
import base64
from io import BytesIO
from PIL import Image


# Hugging Face API configuration
HF_API_URL = "https://api-inference.huggingface.co/models/facebook/sam-vit-base"
HF_TOKEN = os.getenv("HUGGINGFACE_TOKEN", "")


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 1) -> Dict:
    """
    Detect roof boundaries using Hugging Face SAM Inference API.

    Uses HF's hosted SAM model - zero memory on server.
    Optimized for Render's 512MB memory constraint.

    Args:
        image_path: Path to the uploaded roof image
        max_candidates: Number of candidates to return (default: 1)

    Returns:
        Dict containing success, candidates, and metadata
    """
    try:
        # Check for HF token
        if not HF_TOKEN:
            print("[HF-SAM] ERROR: HUGGINGFACE_TOKEN environment variable not set")
            return {
                "success": False,
                "error": "Hugging Face API token not configured. Please add HUGGINGFACE_TOKEN to environment variables."
            }

        # Load image
        if not os.path.exists(image_path):
            return {"success": False, "error": "Image file not found"}

        img = cv2.imread(image_path)
        if img is None:
            return {"success": False, "error": "Failed to load image"}

        original_height, original_width = img.shape[:2]
        print(f"[HF-SAM] Image loaded: {original_width}x{original_height}")

        # Resize image to reduce upload size and processing time
        # HF API has image size limits, 1024px is safe
        max_dimension = 1024
        scale = 1.0

        if max(original_width, original_height) > max_dimension:
            scale = max_dimension / max(original_width, original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            img_resized = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
            print(f"[HF-SAM] Resized for API: {new_width}x{new_height} (scale={scale:.3f})")
        else:
            img_resized = img
            new_width = original_width
            new_height = original_height
            print(f"[HF-SAM] No resize needed (already <= {max_dimension}px)")

        # Free original image
        del img
        gc.collect()

        # Convert to RGB (OpenCV loads as BGR)
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)

        # Convert to bytes for API
        buffer = BytesIO()
        pil_image.save(buffer, format="PNG")
        image_bytes = buffer.getvalue()
        print(f"[HF-SAM] Image size: {len(image_bytes) / 1024:.1f} KB")

        # Free resized image
        del img_resized, img_rgb, pil_image
        gc.collect()

        # Prepare bounding box prompt (70% of image center)
        padding = 0.15
        bbox = {
            "xmin": int(new_width * padding),
            "ymin": int(new_height * padding),
            "xmax": int(new_width * (1 - padding)),
            "ymax": int(new_height * (1 - padding))
        }
        print(f"[HF-SAM] Bbox prompt: {bbox}")

        # Call Hugging Face Inference API
        print("[HF-SAM] Calling Hugging Face API...")
        headers = {
            "Authorization": f"Bearer {HF_TOKEN}"
        }

        try:
            response = requests.post(
                HF_API_URL,
                headers=headers,
                files={"image": image_bytes},
                data={"bbox": str(bbox)},
                timeout=60  # 60 second timeout
            )

            print(f"[HF-SAM] API response status: {response.status_code}")

            if response.status_code == 503:
                # Model is loading
                return {
                    "success": True,
                    "candidates": [],
                    "message": "AI model is loading on Hugging Face. Please try again in 20 seconds.",
                    "debug_info": "HF model loading (503)"
                }

            if response.status_code == 401:
                return {
                    "success": False,
                    "error": "Invalid Hugging Face API token. Please check your HUGGINGFACE_TOKEN environment variable."
                }

            if response.status_code != 200:
                error_msg = response.text[:200] if response.text else "Unknown error"
                print(f"[HF-SAM] API error: {error_msg}")
                return {
                    "success": True,
                    "candidates": [],
                    "message": f"AI detection failed ({response.status_code}). Please use manual drawing.",
                    "debug_info": error_msg
                }

            # Parse response
            result = response.json()
            print(f"[HF-SAM] API response received: {type(result)}")

            # HF SAM API returns masks
            if isinstance(result, list) and len(result) > 0:
                # Process masks
                masks_data = result[0].get("mask") if isinstance(result[0], dict) else None

                if masks_data:
                    # Convert mask to numpy array
                    mask = np.array(masks_data, dtype=np.uint8)
                    print(f"[HF-SAM] Mask shape: {mask.shape}")

                    # Process mask into polygon
                    candidates = process_mask_to_polygon(mask, new_width, new_height, scale, original_width, original_height)

                    if candidates:
                        top_candidates = candidates[:max_candidates]
                        print(f"[HF-SAM] ✓✓✓ SUCCESS - {len(top_candidates)} candidate(s)")
                        return {
                            "success": True,
                            "candidates": top_candidates,
                            "total_found": len(candidates),
                            "strategy_used": "Hugging Face API",
                            "image_dimensions": {
                                "width": original_width,
                                "height": original_height
                            }
                        }

            print("[HF-SAM] No valid masks in response")
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please use manual drawing.",
                "debug_info": "HF API returned no valid masks"
            }

        except requests.exceptions.Timeout:
            print("[HF-SAM] API timeout")
            return {
                "success": True,
                "candidates": [],
                "message": "AI detection timed out. Please use manual drawing or try again.",
                "debug_info": "HF API timeout (60s)"
            }

        except requests.exceptions.RequestException as e:
            print(f"[HF-SAM] API request failed: {str(e)}")
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


def process_mask_to_polygon(mask, new_width, new_height, scale, original_width, original_height):
    """
    Convert binary mask to polygon candidates
    """
    try:
        print("[HF-SAM] Processing mask to polygon...")

        # Find contours
        contours, _ = cv2.findContours(
            mask,
            cv2.RETR_EXTERNAL,
            cv2.CHAIN_APPROX_SIMPLE
        )
        print(f"[HF-SAM] Found {len(contours)} contours")

        if not contours:
            return []

        # Get largest contour
        largest_contour = max(contours, key=cv2.contourArea)
        area = cv2.contourArea(largest_contour)
        area_ratio = area / (new_width * new_height)
        print(f"[HF-SAM] Largest contour: area={area:.0f}, ratio={area_ratio:.2%}")

        # Filter by area (5% to 85%)
        if area_ratio < 0.05 or area_ratio > 0.85:
            print(f"[HF-SAM] Contour rejected: area_ratio={area_ratio:.2%}")
            return []

        # Approximate polygon
        perimeter = cv2.arcLength(largest_contour, True)
        candidates = []

        for epsilon_factor in [0.001, 0.003, 0.005, 0.008, 0.01, 0.015]:
            epsilon = epsilon_factor * perimeter
            approx = cv2.approxPolyDP(largest_contour, epsilon, True)
            num_vertices = len(approx)

            # Accept polygons with 4-12 vertices
            if 4 <= num_vertices <= 12:
                # Scale points back to original image coordinates
                points = []
                for point in approx:
                    x, y = point[0]
                    if scale != 1.0:
                        x_original = x / scale
                        y_original = y / scale
                    else:
                        x_original = x
                        y_original = y
                    points.append({"x": float(x_original), "y": float(y_original)})

                # Calculate confidence
                area_original = area / (scale * scale) if scale != 1.0 else area
                area_ratio_original = area_original / (original_width * original_height)
                confidence = calculate_confidence(area_ratio_original, num_vertices, perimeter, area, mask)

                candidates.append({
                    "points": points,
                    "vertices": num_vertices,
                    "area_px": float(area_original),
                    "area_ratio": float(area_ratio_original),
                    "confidence": float(confidence),
                    "perimeter": float(perimeter / scale if scale != 1.0 else perimeter),
                    "mask_index": 0
                })

                print(f"[HF-SAM] ✓ Candidate created: {num_vertices} vertices, conf={confidence:.1f}%")
                break

        # Sort by confidence
        candidates.sort(key=lambda x: x['confidence'], reverse=True)
        return candidates

    except Exception as e:
        print(f"[HF-SAM] Error processing mask: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def calculate_confidence(area_ratio, num_vertices, perimeter, area, mask):
    """Calculate confidence score for detection"""
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

    # Mask quality (0-10 points)
    mask_fill_ratio = np.sum(mask > 0.5) / mask.size if mask.size > 0 else 0
    if mask_fill_ratio > 0.3:
        score += 10
    elif mask_fill_ratio > 0.15:
        score += 7
    else:
        score += 5

    return min(score, 100.0)
