#!/bin/bash
# SAM Model Setup Script
# Run this once after deployment to download the SAM model

echo "=========================================="
echo "SAM Model Setup"
echo "=========================================="
echo ""
echo "This will download the SAM model (~2.4 GB)"
echo "This is required for roof detection to work."
echo ""

# Check if Python is available
if ! command -v python &> /dev/null && ! command -v python3 &> /dev/null; then
    echo "Error: Python is not installed"
    exit 1
fi

# Use python or python3
PYTHON_CMD="python"
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
fi

echo "Using: $PYTHON_CMD"
echo ""

# Run the download script
$PYTHON_CMD download_sam_model.py --auto

# Check if successful
if [ -f "models/sam_vit_h_4b8939.pth" ]; then
    echo ""
    echo "=========================================="
    echo "Setup Complete!"
    echo "=========================================="
    echo "SAM model is ready. You can now start the server:"
    echo "  uvicorn main:app --host 0.0.0.0 --port 8000"
    echo ""
else
    echo ""
    echo "=========================================="
    echo "Setup Failed"
    echo "=========================================="
    echo "Model file not found. Please check the error messages above."
    echo ""
    exit 1
fi
