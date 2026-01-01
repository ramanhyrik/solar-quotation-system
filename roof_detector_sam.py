"""
AI-Powered Roof Detection using SAM 3 API (HuggingFace Spaces)

Calls the deployed SAM 3 API on HuggingFace Spaces instead of loading the model locally.
This avoids having to install SAM 3 dependencies locally.

HF Space URL: https://ramankamran-mobilesam-roof-api.hf.space/
"""

import os
import requests
from typing import Dict

# HuggingFace Space API URL
SAM3_API_URL = "https://ramankamran-mobilesam-roof-api.hf.space/detect-roof"
API_TIMEOUT = 120  # 2 minutes timeout for API calls


def auto_detect_roof_boundary(image_path: str, max_candidates: int = 1) -> Dict:
    """
    Detect roof boundaries using SAM 3 API on HuggingFace Spaces.

    Calls the deployed SAM 3 API instead of loading the model locally.
    The API uses SAM 3 with text prompts for roof detection.

    Args:
        image_path: Path to the uploaded roof image
        max_candidates: Number of candidates to return (default: 1)

    Returns:
        Dict containing success, candidates, and metadata
    """
    try:
        # Validate image file exists
        if not os.path.exists(image_path):
            return {"success": False, "error": "Image file not found"}

        print(f"[SAM3-API] Sending image to HF Space API: {SAM3_API_URL}")
        print(f"[SAM3-API] Image path: {image_path}")

        # Open image file and send to API
        with open(image_path, 'rb') as f:
            files = {'file': (os.path.basename(image_path), f, 'image/jpeg')}

            # Call the HF Space API
            response = requests.post(
                SAM3_API_URL,
                files=files,
                timeout=API_TIMEOUT
            )

        # Check HTTP response
        if response.status_code != 200:
            error_msg = f"API returned status {response.status_code}: {response.text}"
            print(f"[SAM3-API] ERROR: {error_msg}")
            return {
                "success": False,
                "error": error_msg
            }

        # Parse JSON response
        result = response.json()

        if result.get('success'):
            candidates = result.get('candidates', [])
            print(f"[SAM3-API] SUCCESS - {len(candidates)} candidate(s) detected")

            # Return top N candidates
            top_candidates = candidates[:max_candidates]

            return {
                "success": True,
                "candidates": top_candidates,
                "total_found": result.get('total_found', len(candidates)),
                "strategy_used": result.get('strategy_used', 'SAM 3 API'),
                "image_dimensions": result.get('image_dimensions', {})
            }
        else:
            # API returned success=False
            error_msg = result.get('error', result.get('message', 'Detection failed'))
            print(f"[SAM3-API] Detection returned no results: {error_msg}")
            return {
                "success": True,
                "candidates": [],
                "message": result.get('message', 'No roof detected. Please use manual drawing.')
            }

    except requests.exceptions.Timeout:
        error_msg = f"API request timed out after {API_TIMEOUT} seconds"
        print(f"[SAM3-API] ERROR: {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }

    except requests.exceptions.RequestException as e:
        error_msg = f"API request failed: {str(e)}"
        print(f"[SAM3-API] ERROR: {error_msg}")
        return {
            "success": False,
            "error": error_msg
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {
            "success": False,
            "error": f"Detection failed: {str(e)}"
        }
