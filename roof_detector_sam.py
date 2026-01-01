"""
AI-Powered Roof Detection using SAM 3 (Segment Anything Model 3)

SAM 3 - Released November 2025 by Meta AI
- Text-based Promptable Concept Segmentation (PCS)
- 900M parameters - 2x better accuracy than SAM 2
- Open-vocabulary segmentation with text prompts
- Perfect for aerial/satellite imagery!
"""

import cv2
import numpy as np
from typing import List, Dict
import os
import gc
import torch
from PIL import Image
from transformers import Sam3Processor, Sam3Model


# Global model cache
_sam3_model = None
_sam3_processor = None


def get_sam3_model():
    """Load SAM 3 model once and cache it."""
    global _sam3_model, _sam3_processor

    if _sam3_model is None:
        print("[SAM3] Loading SAM 3 model from facebook/sam3...")
        device = "cuda" if torch.cuda.is_available() else "cpu"

        _sam3_model = Sam3Model.from_pretrained("facebook/sam3").to(device)
        _sam3_processor = Sam3Processor.from_pretrained("facebook/sam3")

        print(f"[SAM3] Model loaded on {device}")

    return _sam3_model, _sam3_processor


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 1) -> Dict:
    """
    Detect roof boundaries using SAM 3 with text prompts.

    Uses SAM 3 (Segment Anything Model 3) for roof detection:
    - Text prompts: "roof", "building roof", "rooftop"
    - Promptable Concept Segmentation (PCS) - 900M parameters
    - 2x better accuracy than SAM 2
    - Works great on aerial/satellite images!

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

        img_cv = cv2.imread(image_path)
        if img_cv is None:
            return {"success": False, "error": "Failed to load image"}

        original_height, original_width = img_cv.shape[:2]
        print(f"[SAM3] Image loaded: {original_width}x{original_height}")

        # Convert to PIL Image (RGB)
        img_rgb = cv2.cvtColor(img_cv, cv2.COLOR_BGR2RGB)
        pil_image = Image.fromarray(img_rgb)

        # Free OpenCV image
        del img_cv, img_rgb
        gc.collect()

        # Get SAM 3 model and processor
        model, processor = get_sam3_model()
        device = next(model.parameters()).device

        # Text prompts for roof detection
        text_prompts = ["roof", "building roof", "rooftop"]

        all_candidates = []

        print("[SAM3] Running SAM 3 with text prompts...")

        for text_prompt in text_prompts:
            print(f"[SAM3] Trying prompt: '{text_prompt}'")

            # Prepare inputs with text prompt
            inputs = processor(
                images=pil_image,
                text=text_prompt,
                return_tensors="pt"
            ).to(device)

            # Run SAM 3 inference
            with torch.no_grad():
                outputs = model(**inputs)

            # Post-process results
            results = processor.post_process_instance_segmentation(
                outputs,
                threshold=0.5,
                mask_threshold=0.5,
                target_sizes=inputs.get("original_sizes").tolist()
            )[0]

            num_masks = len(results.get('masks', []))
            print(f"[SAM3]   Found {num_masks} object(s) with prompt '{text_prompt}'")

            # Process each detected mask
            if num_masks > 0:
                masks = results['masks']
                boxes = results['boxes']
                scores = results['scores']

                for i in range(num_masks):
                    mask = masks[i].cpu().numpy().astype(np.uint8)
                    score = float(scores[i])
                    box = boxes[i].cpu().numpy()

                    # Find contours from mask
                    contours, _ = cv2.findContours(
                        mask,
                        cv2.RETR_EXTERNAL,
                        cv2.CHAIN_APPROX_SIMPLE
                    )

                    if contours:
                        # Get the largest contour
                        largest_contour = max(contours, key=cv2.contourArea)
                        area = cv2.contourArea(largest_contour)

                        # Convert contour to points
                        points = []
                        for point in largest_contour:
                            x, y = point[0]
                            points.append({"x": float(x), "y": float(y)})

                        # Simplify polygon (reduce points)
                        epsilon = 0.005 * cv2.arcLength(largest_contour, True)
                        approx = cv2.approxPolyDP(largest_contour, epsilon, True)

                        simplified_points = []
                        for point in approx:
                            x, y = point[0]
                            simplified_points.append({"x": float(x), "y": float(y)})

                        candidate = {
                            "points": simplified_points,
                            "confidence": score,
                            "area_px": float(area),
                            "prompt": text_prompt,
                            "source": "SAM3_PCS"
                        }

                        all_candidates.append(candidate)

        # Sort by confidence score
        all_candidates.sort(key=lambda x: x['confidence'], reverse=True)

        # Free resources
        del pil_image
        gc.collect()
        torch.cuda.empty_cache() if torch.cuda.is_available() else None

        if all_candidates:
            top_candidates = all_candidates[:max_candidates]
            print(f"[SAM3] SUCCESS - {len(top_candidates)} candidate(s)")
            return {
                "success": True,
                "candidates": top_candidates,
                "total_found": len(all_candidates),
                "strategy_used": "SAM 3 (Segment Anything Model 3) - Text-based PCS - 2x Better Accuracy!",
                "image_dimensions": {
                    "width": original_width,
                    "height": original_height
                }
            }
        else:
            print("[SAM3] No valid roof candidates detected")
            return {
                "success": True,
                "candidates": [],
                "message": "No roof detected. Please use manual drawing.",
                "debug_info": "SAM 3 returned no valid candidates"
            }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Detection failed: {str(e)}"
        }
