# Solar Quotation System - Free Deployment Guide

## Option 1: Render (RECOMMENDED - Easiest Free Option)

### Features:
- ✅ 100% Free (no credit card required)
- ✅ Automatic HTTPS/SSL
- ✅ Persistent disk for SQLite database
- ✅ Auto-deploy from GitHub
- ⚠️ Spins down after 15 min inactivity (50 sec to wake up)

### Step-by-Step Deployment:

1. **Push code to GitHub**
   ```bash
   cd d:\Project
   git init
   git add .
   git commit -m "Initial commit"
   git remote add origin https://github.com/YOUR_USERNAME/solar-quotation.git
   git push -u origin main
   ```

2. **Create Render Account**
   - Go to https://render.com
   - Sign up with GitHub (free, no credit card)

3. **Deploy Web Service**
   - Click "New +" → "Web Service"
   - Connect your GitHub repository
   - Configure:
     - **Name**: solar-quotation-system
     - **Runtime**: Python 3
     - **Build Command**: `pip install -r requirements.txt`
     - **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`
     - **Plan**: Free

4. **Add Persistent Disk** (Important for SQLite database)
   - In your service settings, go to "Disks"
   - Click "Add Disk"
   - **Name**: solar-data
   - **Mount Path**: /opt/render/project/src
   - **Size**: 1 GB (free)
   - Click "Create"

5. **Deploy!**
   - Click "Create Web Service"
   - Wait 3-5 minutes for deployment
   - Your app will be live at: `https://solar-quotation-system.onrender.com`

6. **Default Login**
   - Email: admin@solar.com
   - Password: admin123

---

## Option 2: Railway (Free $5 Monthly Credit)

### Features:
- ✅ $5 free credit every month
- ✅ Fast deployments
- ✅ No cold starts
- ⚠️ Requires credit card for free tier

### Deployment Steps:

1. **Push to GitHub** (same as Render above)

2. **Create Railway Account**
   - Go to https://railway.app
   - Sign up with GitHub
   - Add credit card (won't be charged, just for verification)

3. **Deploy**
   - Click "New Project" → "Deploy from GitHub repo"
   - Select your repository
   - Railway auto-detects Python and deploys
   - Click "Generate Domain" to get your URL

4. **Environment Variables** (optional)
   - No special config needed - uses PORT automatically

---

## Option 3: Fly.io (Good Free Tier)

### Features:
- ✅ 3 shared VMs free
- ✅ 3GB persistent storage free
- ✅ Fast global deployment
- ⚠️ Requires Docker knowledge

### Deployment Steps:

1. **Install Fly CLI**
   ```bash
   # Windows (PowerShell)
   iwr https://fly.io/install.ps1 -useb | iex
   ```

2. **Login and Deploy**
   ```bash
   cd d:\Project
   fly auth signup
   fly launch
   # Answer prompts (choose free tier)
   fly deploy
   ```

---

## Option 4: Hugging Face Spaces (Demo/Testing Only)

### Features:
- ✅ 100% Free
- ✅ Good for demos
- ⚠️ Not ideal for production apps
- ⚠️ Limited persistence

### Deployment Steps:

1. **Create Space**
   - Go to https://huggingface.co/new-space
   - Name: solar-quotation
   - SDK: Gradio (select Docker)
   - Create Space

2. **Push Code**
   ```bash
   git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/solar-quotation
   git push hf main
   ```

See `HUGGINGFACE.md` for detailed Hugging Face deployment.

---

## Recommended: Use Render

For your Solar Quotation System, **Render is the best free option** because:
- No credit card required
- Easy persistent disk for SQLite
- Automatic HTTPS
- Simple GitHub integration
- Perfect for business apps

The only downside is the 15-minute inactivity spin-down, but the app wakes up in ~50 seconds when accessed.

---

## Post-Deployment Checklist

After deployment, remember to:

1. ✅ Change default admin password
2. ✅ Configure company settings in Admin Panel
3. ✅ Upload company logo
4. ✅ Test PDF generation
5. ✅ Test widget embedding on your website
6. ✅ Create sales rep user accounts

---

## Support

- Render Docs: https://render.com/docs
- Railway Docs: https://docs.railway.app
- Fly.io Docs: https://fly.io/docs
