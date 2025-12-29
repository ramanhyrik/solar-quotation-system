# Deployment Guide

## SAM Model Setup

This application uses Meta's SAM (Segment Anything Model) for roof detection. The model file is **2.4 GB** and is **not included in the git repository** to keep the repo lightweight.

### Download Before Starting Server (Recommended)

**You must download the SAM model BEFORE starting the server** for the first time:

```bash
# After deploying your code, run this first:
python download_sam_model.py --auto

# Then start the server:
uvicorn main:app
```

The server checks for the model during startup but **does not download automatically** to avoid memory issues. The model persists on the server - you only need to download once.

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

#### Option 1: Direct Download on Server (Recommended)
```bash
# SSH into your server after deployment
python download_sam_model.py --auto
# Then start your server
uvicorn main:app
```
- Simple and straightforward
- Model persists across restarts
- One-time setup

#### Option 2: Download Locally, Then Upload
```bash
# On your local machine
python download_sam_model.py
# Upload models/sam_vit_h_4b8939.pth to server
scp models/sam_vit_h_4b8939.pth user@server:/path/to/app/models/
```
- Useful if server has slow internet
- Download once, deploy multiple times

#### Option 3: Cloud Storage (Advanced)
- Upload model to S3/Google Cloud Storage
- Modify `download_sam_model.py` to fetch from your cloud storage
- Faster downloads, more control
- Good for multiple servers

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
