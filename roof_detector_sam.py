"""
AI-Powered Roof Detection using Roboflow Segment Anything Model (SAM)
Zero memory on server - all processing done on Roboflow cloud
Free tier: $60/month in FREE credits
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


# Roboflow API configuration
ROBOFLOW_API_KEY = os.getenv("ROBOFLOW_API_KEY", "")
ROBOFLOW_SAM_URL = "https://outline.roboflow.com"


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 1) -> Dict:
    """
    Detect roof boundaries using Roboflow SAM API.

    Uses Roboflow's hosted SAM model - zero memory on server.
    Optimized for Render's 512MB memory constraint.

    Args:
        image_path: Path to the uploaded roof image
        max_candidates: Number of candidates to return (default: 1)

    Returns:
        Dict containing success, candidates, and metadata
    """
    try:
        # Check for Roboflow API key
        if not ROBOFLOW_API_KEY:
            print("[ROBOFLOW-SAM] ERROR: ROBOFLOW_API_KEY environment variable not set")
            return {
                "success": False,
                "error": "Roboflow API key not configured. Please add ROBOFLOW_API_KEY to environment variables."
            }

        # Load image
        if not os.path.exists(image_path):
            return {"success": False, "error": "Image file not found"}

        img = cv2.imread(image_path)
        if img is None:
            return {"success": False, "error": "Failed to load image"}

        original_height, original_width = img.shape[:2]
        print(f"[ROBOFLOW-SAM] Image loaded: {original_width}x{original_height}")

        # Resize image to reduce upload size and processing time
        max_dimension = 1024
        scale = 1.0

        if max(original_width, original_height) > max_dimension:
            scale = max_dimension / max(original_width, original_height)
            new_width = int(original_width * scale)
            new_height = int(original_height * scale)
            img_resized = cv2.resize(img, (new_width, new_height), interpolation=cv2.INTER_AREA)
            print(f"[ROBOFLOW-SAM] Resized for API: {new_width}x{new_height} (scale={scale:.3f})")
        else:
            img_resized = img
            new_width = original_width
            new_height = original_height
            print(f"[ROBOFLOW-SAM] No resize needed (already <= {max_dimension}px)")

        # Free original image
        del img
        gc.collect()

        # Convert to RGB and then to base64
        img_rgb = cv2.cvtColor(img_resized, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)

        # Convert to base64 for API
        buffer = BytesIO()
        pil_image.save(buffer, format="JPEG", quality=90)
        img_base64 = base64.b64encode(buffer.getvalue()).decode('utf-8')
        print(f"[ROBOFLOW-SAM] Image encoded: {len(img_base64)} chars")

        # Free resized image
        del img_resized, img_rgb, pil_image, buffer
        gc.collect()

        # Prepare bounding box prompt (central 70% of image for roof)
        padding = 0.15
        bbox_prompt = {
            "x": int(new_width / 2),
            "y": int(new_height / 2),
            "width": int(new_width * (1 - 2 * padding)),
            "height": int(new_height * (1 - 2 * padding))
        }
        print(f"[ROBOFLOW-SAM] Bbox prompt: center=({bbox_prompt['x']}, {bbox_prompt['y']}), size=({bbox_prompt['width']}x{bbox_prompt['height']})")

        # Call Roboflow SAM API
        print("[ROBOFLOW-SAM] Calling Roboflow Inference API...")

        try:
            # Prepare request payload
            payload = {
                "api_key": ROBOFLOW_API_KEY,
                "image": {
                    "type": "base64",
                    "value": img_base64
                },
                "box_prompt": [{
                    "x": bbox_prompt["x"],
                    "y": bbox_prompt["y"],
                    "width": bbox_prompt["width"],
                    "height": bbox_prompt["height"],
                    "label": "roof"
                }]
            }

            response = requests.post(
                ROBOFLOW_SAM_URL,
                json=payload,
                timeout=60
            )

            print(f"[ROBOFLOW-SAM] API response status: {response.status_code}")

            if response.status_code == 401:
                return {
                    "success": False,
                    "error": "Invalid Roboflow API key. Please check your ROBOFLOW_API_KEY environment variable."
                }

            if response.status_code == 429:
                return {
                    "success": True,
                    "candidates": [],
                    "message": "API rate limit exceeded. Please try again in a moment.",
                    "debug_info": "Roboflow rate limit (429)"
                }

            if response.status_code != 200:
                error_msg = response.text[:200] if response.text else "Unknown error"
                print(f"[ROBOFLOW-SAM] API error: {error_msg}")
                return {
                    "success": True,
                    "candidates": [],
                    "message": f"AI detection failed ({response.status_code}). Please use manual drawing.",
                    "debug_info": error_msg
                }

            # Parse response
            result = response.json()
            print(f"[ROBOFLOW-SAM] API response received")

            # Process masks from response
            candidates = process_roboflow_masks(result, new_width, new_height, scale, original_width, original_height, max_candidates)

            if candidates:
                top_candidates = candidates[:max_candidates]
                print(f"[ROBOFLOW-SAM] ✓✓✓ SUCCESS - {len(top_candidates)} candidate(s)")
                return {
                    "success": True,
                    "candidates": top_candidates,
                    "total_found": len(candidates),
                    "strategy_used": "Roboflow SAM API",
                    "image_dimensions": {
                        "width": original_width,
                        "height": original_height
                    }
                }

            print("[ROBOFLOW-SAM] No valid roof masks detected")
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please use manual drawing.",
                "debug_info": "Roboflow SAM returned no valid masks"
            }

        except requests.exceptions.Timeout:
            print("[ROBOFLOW-SAM] API timeout")
            return {
                "success": True,
                "candidates": [],
                "message": "AI detection timed out. Please use manual drawing or try again.",
                "debug_info": "Roboflow API timeout (60s)"
            }

        except requests.exceptions.RequestException as e:
            print(f"[ROBOFLOW-SAM] API request failed: {str(e)}")
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


def process_roboflow_masks(result: Dict, new_width: int, new_height: int, scale: float,
                           original_width: int, original_height: int, max_candidates: int) -> List[Dict]:
    """
    Process Roboflow SAM API response to extract polygon candidates
    """
    try:
        print("[ROBOFLOW-SAM] Processing masks...")

        # Roboflow SAM returns masks in the 'masks' field
        if 'masks' not in result or not result['masks']:
            print("[ROBOFLOW-SAM] No masks in response")
            return []

        masks = result['masks']
        print(f"[ROBOFLOW-SAM] Found {len(masks)} mask(s)")

        candidates = []

        for idx, mask_data in enumerate(masks):
            try:
                # Decode mask (Roboflow returns RLE or polygon format)
                if 'svg_path' in mask_data:
                    # SVG path format - convert to polygon
                    polygon = svg_path_to_polygon(mask_data['svg_path'], new_width, new_height)
                elif 'points' in mask_data:
                    # Direct polygon points
                    polygon = mask_data['points']
                else:
                    print(f"[ROBOFLOW-SAM] Mask {idx}: Unknown format")
                    continue

                if not polygon or len(polygon) < 4:
                    print(f"[ROBOFLOW-SAM] Mask {idx}: Invalid polygon")
                    continue

                # Scale points back to original image coordinates
                scaled_points = []
                for point in polygon:
                    x = point.get('x', point.get(0))
                    y = point.get('y', point.get(1))

                    if scale != 1.0:
                        x_original = x / scale
                        y_original = y / scale
                    else:
                        x_original = x
                        y_original = y

                    scaled_points.append({"x": float(x_original), "y": float(y_original)})

                # Calculate area and confidence
                area_px = calculate_polygon_area(scaled_points)
                area_ratio = area_px / (original_width * original_height)

                # Filter by area (5% to 85%)
                if area_ratio < 0.05 or area_ratio > 0.85:
                    print(f"[ROBOFLOW-SAM] Mask {idx}: Rejected by area ratio {area_ratio:.2%}")
                    continue

                num_vertices = len(scaled_points)
                confidence = calculate_confidence(area_ratio, num_vertices)

                candidates.append({
                    "points": scaled_points,
                    "vertices": num_vertices,
                    "area_px": float(area_px),
                    "area_ratio": float(area_ratio),
                    "confidence": float(confidence),
                    "mask_index": idx
                })

                print(f"[ROBOFLOW-SAM] ✓ Mask {idx}: {num_vertices} vertices, area={area_ratio:.1%}, conf={confidence:.1f}%")

            except Exception as e:
                print(f"[ROBOFLOW-SAM] Error processing mask {idx}: {str(e)}")
                continue

        # Sort by confidence
        candidates.sort(key=lambda x: x['confidence'], reverse=True)
        return candidates

    except Exception as e:
        print(f"[ROBOFLOW-SAM] Error processing masks: {str(e)}")
        import traceback
        traceback.print_exc()
        return []


def svg_path_to_polygon(svg_path: str, width: int, height: int) -> List[Dict]:
    """
    Convert SVG path to polygon points (simplified implementation)
    """
    # This is a simplified version - just extract M and L commands
    import re

    points = []
    commands = re.findall(r'[ML]\s*(-?\d+\.?\d*)\s+(-?\d+\.?\d*)', svg_path)

    for cmd, x, y in commands:
        points.append({"x": float(x), "y": float(y)})

    return points


def calculate_polygon_area(points: List[Dict]) -> float:
    """
    Calculate polygon area using shoelace formula
    """
    if len(points) < 3:
        return 0.0

    area = 0.0
    n = len(points)

    for i in range(n):
        j = (i + 1) % n
        area += points[i]['x'] * points[j]['y']
        area -= points[j]['x'] * points[i]['y']

    return abs(area) / 2.0


def calculate_confidence(area_ratio: float, num_vertices: int) -> float:
    """
    Calculate confidence score for detection
    """
    score = 0.0

    # Area score (0-50 points)
    if 0.10 <= area_ratio <= 0.60:
        score += 50
    elif 0.05 <= area_ratio < 0.10 or 0.60 < area_ratio <= 0.75:
        score += 40
    else:
        score += 30

    # Vertex count (0-50 points)
    if 4 <= num_vertices <= 8:
        score += 50
    elif 9 <= num_vertices <= 15:
        score += 45
    else:
        score += 35

    return min(score, 100.0)
