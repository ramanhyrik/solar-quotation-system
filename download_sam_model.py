"""
Download SAM (Segment Anything Model) checkpoint
This script downloads the SAM ViT-H model checkpoint required for roof detection
"""

import os
import urllib.request
from pathlib import Path
import sys

# SAM model details
SAM_MODEL_URL = "https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth"
SAM_MODEL_SIZE = "2.4 GB"
MODEL_DIR = "models"
MODEL_FILE = "sam_vit_h_4b8939.pth"

def download_sam_model(interactive=True):
    """Download SAM model checkpoint with progress reporting

    Args:
        interactive: If False, skip prompts and download automatically (for server startup)
    """

    if interactive:
        print("=" * 70)
        print("SAM Model Download Utility")
        print("=" * 70)
        print(f"\nModel: SAM ViT-H (Huge)")
        print(f"Size: ~{SAM_MODEL_SIZE}")
        print(f"URL: {SAM_MODEL_URL}")
        print(f"Destination: {os.path.join(MODEL_DIR, MODEL_FILE)}")
        print("\n" + "=" * 70)

    # Create models directory
    os.makedirs(MODEL_DIR, exist_ok=True)
    model_path = os.path.join(MODEL_DIR, MODEL_FILE)

    # Check if already exists
    if os.path.exists(model_path):
        file_size = os.path.getsize(model_path) / (1024 ** 3)  # Convert to GB
        print(f"[SAM] Model already exists: {model_path}")
        print(f"[SAM] File size: {file_size:.2f} GB")

        if interactive:
            response = input("\nDo you want to re-download? (y/N): ").strip().lower()
            if response != 'y':
                print("\nSkipping download. Using existing model.")
                return
        else:
            # Non-interactive mode: skip download if exists
            return

    if interactive:
        print("\n⚠ This will download ~2.4 GB. Make sure you have:")
        print("  • Stable internet connection")
        print("  • At least 3 GB free disk space")
        print("  • Time (may take 10-30 minutes depending on connection)")

        response = input("\nProceed with download? (y/N): ").strip().lower()
        if response != 'y':
            print("\nDownload cancelled.")
            return
    else:
        print(f"[SAM] Downloading model (~{SAM_MODEL_SIZE})...")
        print("[SAM] This may take 10-30 minutes depending on your connection...")

    if not interactive:
        print("[SAM] Starting download...")

    try:
        def report_progress(block_num, block_size, total_size):
            """Show download progress"""
            downloaded = block_num * block_size
            percent = min(100, (downloaded / total_size) * 100)
            downloaded_mb = downloaded / (1024 ** 2)
            total_mb = total_size / (1024 ** 2)

            bar_length = 50
            filled = int(bar_length * percent / 100)
            bar = '█' * filled + '░' * (bar_length - filled)

            print(f'\r{bar} {percent:.1f}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)', end='', flush=True)

        urllib.request.urlretrieve(SAM_MODEL_URL, model_path, reporthook=report_progress)
        print("\n")

        # Verify download
        if os.path.exists(model_path):
            file_size = os.path.getsize(model_path) / (1024 ** 3)
            print(f"✓ Download complete!")
            print(f"  Location: {model_path}")
            print(f"  Size: {file_size:.2f} GB")
            print("\n✓ SAM model is ready to use!")
            print("\nYou can now use the Roof Designer with SAM detection.")
        else:
            print("✗ Download failed - file not found")

    except Exception as e:
        print(f"\n✗ Download failed: {e}")
        print("\nAlternative: Download manually from:")
        print(f"  {SAM_MODEL_URL}")
        print(f"\nSave to: {model_path}")

if __name__ == "__main__":
    try:
        # Support automatic mode for deployment scripts
        auto_mode = "--auto" in sys.argv or "-a" in sys.argv
        download_sam_model(interactive=not auto_mode)
    except KeyboardInterrupt:
        print("\n\nDownload cancelled by user.")
    except Exception as e:
        print(f"\n\nError: {e}")
