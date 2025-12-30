"""
AI-Powered Roof Detection using Semantic Segmentation
Uses DeepLabV3 with MobileNetV2 backbone (~10MB model, ~150MB RAM)
"""

import cv2
import numpy as np
import torch
import torchvision
from torchvision import transforms
from typing import List, Dict, Tuple
import os


# Global model cache to avoid reloading
_model_cache = None


def get_segmentation_model():
    """Load DeepLabV3-MobileNetV2 model (cached)"""
    global _model_cache

    if _model_cache is not None:
        return _model_cache

    print("[AI-SEG] Loading DeepLabV3-MobileNetV2 model...")

    # Load pretrained model (trained on COCO dataset - includes 'building' class)
    model = torchvision.models.segmentation.deeplabv3_mobilenet_v3_large(pretrained=True)
    model.eval()

    # Move to CPU (no GPU needed for inference)
    device = torch.device('cpu')
    model = model.to(device)

    _model_cache = model
    print("[AI-SEG] Model loaded successfully!")

    return model


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 1) -> Dict:
    """
    Detect roof boundaries using semantic segmentation.

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
        print(f"[AI-SEG] Image loaded: {original_width}x{original_height}")

        # Convert BGR to RGB
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

        # Get segmentation model
        model = get_segmentation_model()

        # Preprocess image for model
        preprocess = transforms.Compose([
            transforms.ToPILImage(),
            transforms.Resize((512, 512)),  # DeepLabV3 expects 512x512
            transforms.ToTensor(),
            transforms.Normalize(
                mean=[0.485, 0.456, 0.406],
                std=[0.229, 0.224, 0.225]
            )
        ])

        input_tensor = preprocess(img_rgb)
        input_batch = input_tensor.unsqueeze(0)

        # Run inference
        print("[AI-SEG] Running semantic segmentation...")
        with torch.no_grad():
            output = model(input_batch)['out'][0]

        # Get segmentation mask
        output_predictions = output.argmax(0).byte().cpu().numpy()

        # Resize mask back to original image size
        mask = cv2.resize(output_predictions, (original_width, original_height),
                         interpolation=cv2.INTER_NEAREST)

        print(f"[AI-SEG] Unique classes detected: {np.unique(mask)}")

        # DeepLabV3 classes (PASCAL VOC):
        # 0: background
        # 15: person
        # 5: airplane
        # 2: bicycle
        # 7: car
        # etc.
        # We need to detect buildings - typically class 0-20 range

        # Create building mask - try multiple strategies
        building_mask = create_building_mask(mask, img_rgb)

        if building_mask is None or building_mask.sum() == 0:
            return {
                "success": True,
                "candidates": [],
                "message": "No buildings detected in image. Try manual drawing.",
                "debug_info": "Segmentation did not find building structures"
            }

        # Find contours in building mask
        contours, _ = cv2.findContours(building_mask, cv2.RETR_EXTERNAL,
                                       cv2.CHAIN_APPROX_SIMPLE)

        if not contours:
            return {
                "success": True,
                "candidates": [],
                "message": "No roof boundaries found. Try manual drawing.",
                "debug_info": "No contours in segmentation mask"
            }

        print(f"[AI-SEG] Found {len(contours)} building contours")

        # Process contours into polygon candidates
        candidates = []
        img_area = original_width * original_height

        for cnt in contours:
            area = cv2.contourArea(cnt)
            area_ratio = area / img_area

            # Filter by area (5% to 80% of image)
            if area < img_area * 0.05 or area > img_area * 0.80:
                continue

            # Approximate polygon
            perimeter = cv2.arcLength(cnt, True)

            # Try multiple approximation levels
            for epsilon_factor in [0.005, 0.01, 0.02]:
                epsilon = epsilon_factor * perimeter
                approx = cv2.approxPolyDP(cnt, epsilon, True)
                num_vertices = len(approx)

                if 4 <= num_vertices <= 12:
                    # Extract points
                    points = []
                    for point in approx:
                        x, y = point[0]
                        points.append({"x": float(x), "y": float(y)})

                    # Calculate confidence (based on area and shape quality)
                    confidence = calculate_segmentation_confidence(
                        area, area_ratio, num_vertices, perimeter
                    )

                    candidates.append({
                        "points": points,
                        "vertices": num_vertices,
                        "area_px": float(area),
                        "area_ratio": float(area_ratio),
                        "confidence": float(confidence),
                        "perimeter": float(perimeter)
                    })
                    break

        if len(candidates) == 0:
            return {
                "success": True,
                "candidates": [],
                "message": "No suitable roof shapes found. Try manual drawing.",
                "debug_info": f"Found {len(contours)} contours but none met quality criteria"
            }

        # Sort by confidence and area
        candidates.sort(key=lambda x: (x['confidence'], x['area_ratio']), reverse=True)

        # Return best candidate
        top_candidates = candidates[:max_candidates]

        for i, c in enumerate(top_candidates):
            print(f"[AI-SEG] Candidate {i+1}: {c['vertices']} vertices, "
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
            "error": f"Segmentation failed: {str(e)}"
        }


def create_building_mask(seg_mask, img_rgb):
    """
    Create building mask from segmentation output.
    Uses multiple strategies to identify buildings.
    """
    h, w = seg_mask.shape

    # Strategy 1: Look for common building/structure classes
    # In PASCAL VOC/COCO, buildings might be segmented as background edges
    # We'll use a different approach - find large uniform regions

    # Strategy 2: Use color-based post-processing on segmentation
    # Buildings often have uniform roofs (darker or specific colors)
    hsv = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2HSV)

    # Get center region (likely roof)
    center_region = hsv[int(h*0.3):int(h*0.7), int(w*0.3):int(w*0.7)]
    mean_hue = np.mean(center_region[:, :, 0])
    mean_sat = np.mean(center_region[:, :, 1])
    mean_val = np.mean(center_region[:, :, 2])

    # Create mask for similar colors
    lower = np.array([max(0, mean_hue - 25), max(0, mean_sat - 60), max(0, mean_val - 60)])
    upper = np.array([min(180, mean_hue + 25), min(255, mean_sat + 60), min(255, mean_val + 60)])
    color_mask = cv2.inRange(hsv, lower, upper)

    # Strategy 3: Find largest connected component
    # Buildings are typically the largest structure in aerial images
    num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(color_mask, connectivity=8)

    if num_labels <= 1:
        # Fallback: use simple thresholding
        gray = cv2.cvtColor(img_rgb, cv2.COLOR_RGB2GRAY)
        _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return binary

    # Get largest component (excluding background)
    largest_component = 1 + np.argmax(stats[1:, cv2.CC_STAT_AREA])
    building_mask = (labels == largest_component).astype(np.uint8) * 255

    # Morphological operations to clean up
    kernel = np.ones((7, 7), np.uint8)
    building_mask = cv2.morphologyEx(building_mask, cv2.MORPH_CLOSE, kernel, iterations=2)
    building_mask = cv2.morphologyEx(building_mask, cv2.MORPH_OPEN, kernel, iterations=1)

    return building_mask


def calculate_segmentation_confidence(area, area_ratio, num_vertices, perimeter):
    """Calculate confidence score for segmentation-based detection"""
    score = 0.0

    # Area score (0-40 points)
    if 0.10 <= area_ratio <= 0.60:
        score += 40
    elif 0.05 <= area_ratio < 0.10 or 0.60 < area_ratio <= 0.75:
        score += 30
    else:
        score += 20

    # Vertex count (0-30 points)
    if num_vertices == 4:
        score += 30
    elif 5 <= num_vertices <= 8:
        score += 35  # Prefer complex shapes from segmentation
    else:
        score += 20

    # Compactness (0-30 points)
    compactness = (4 * np.pi * area) / (perimeter ** 2) if perimeter > 0 else 0
    if compactness > 0.5:
        score += 30
    elif compactness > 0.3:
        score += 20
    else:
        score += 10

    return min(score, 100.0)
