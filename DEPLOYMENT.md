# Deployment Guide

## SAM Model Setup

This application uses Meta's SAM (Segment Anything Model) for roof detection. The model file is **2.4 GB** and is **not included in the git repository** to keep the repo lightweight.

### Automatic Download (Recommended)

The server will **automatically download the SAM model** on first startup if it's not present:

1. Deploy your application to the server
2. Run `uvicorn main:app` or your deployment command
3. The server will check for the SAM model during startup
4. If missing, it will download automatically (takes 10-30 minutes on first run)
5. The model persists on the server - **no need to download again**

The model is saved to `models/sam_vit_h_4b8939.pth` and excluded from git via `.gitignore`.

### Manual Download

If you prefer to download manually:

```bash
# Interactive mode (with prompts)
python download_sam_model.py

# Automatic mode (for scripts)
python download_sam_model.py --auto
```

### Deployment Options

#### Option 1: Let Server Download (Recommended)
- Just deploy and start the server
- Model downloads automatically on first startup
- Persists across restarts
- ✓ Simple and clean

#### Option 2: Pre-download Before Deployment
```bash
# SSH into your server
python download_sam_model.py --auto
# Then start your server
```

#### Option 3: Cloud Storage (Advanced)
- Upload model to S3/Google Cloud Storage
- Modify `download_sam_model.py` to fetch from your cloud storage
- Faster downloads, more control

### Storage Requirements

- Model size: 2.4 GB
- Ensure server has at least 3 GB free disk space
- Model location: `models/sam_vit_h_4b8939.pth`

### Why Not in Git?

- GitHub has a 100 MB file size limit
- Git LFS has 2 GB/month bandwidth limits
- 2.4 GB model would make git clone/pull extremely slow
- Better to download once on the server and persist

### Troubleshooting

If the model fails to download automatically:

1. Check server has internet access to `dl.fbaipublicfiles.com`
2. Verify 3 GB free disk space
3. Run manual download: `python download_sam_model.py --auto`
4. Check logs for download errors

### Model Information

- **Name**: SAM ViT-H (Vision Transformer - Huge)
- **Size**: 2.4 GB
- **Source**: Facebook AI Research
- **URL**: https://dl.fbaipublicfiles.com/segment_anything/sam_vit_h_4b8939.pth
- **License**: Apache 2.0
