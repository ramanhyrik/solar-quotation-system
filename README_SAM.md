# SAM Model Setup Guide

This application uses Meta's **Segment Anything Model (SAM)** for AI-powered roof detection. The model provides highly accurate roof boundary detection from satellite or drone images.

## Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Download SAM Model (One-Time Setup)
The SAM model is 2.4 GB and must be downloaded separately:

**Option A: Automatic (Recommended)**
```bash
python download_sam_model.py --auto
```

**Option B: Interactive**
```bash
python download_sam_model.py
```

**Option C: Using Setup Script (Linux/Mac)**
```bash
chmod +x setup_sam.sh
./setup_sam.sh
```

### 3. Start Server
```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

## Why Manual Download?

The SAM model file is **2.4 GB**, which:
- Exceeds GitHub's 100 MB file size limit
- Would make git clone/pull extremely slow
- Could cause memory issues if downloaded during server startup

By downloading it once and keeping it out of git, we maintain a lightweight repository while still having SAM available.

## Model Information

- **File**: `models/sam_vit_h_4b8939.pth`
- **Size**: ~2.4 GB
- **Source**: Facebook AI Research
- **License**: Apache 2.0
- **Download URL**: https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth

## Troubleshooting

### Model Not Found Error
If you see "SAM model not found" errors:
```bash
python download_sam_model.py --auto
```

### Download Fails
If the automatic download fails, manually download from:
https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth

Save it to: `models/sam_vit_h_4b8939.pth`

### Server Shows "Roof detection unavailable"
The server checks for the SAM model on startup. If you see this warning, run the download script and restart the server.

## Git Ignore

The model file is automatically excluded from git via `.gitignore`:
```
# SAM Model files (too large for git - 2.4 GB)
models/
*.pth
```

This means:
- ✓ Model persists on your server across deployments
- ✓ Repository stays lightweight
- ✓ Fast git operations
- ✗ Need to download once per server/environment
