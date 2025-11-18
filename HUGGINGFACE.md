# Deploying to Hugging Face Spaces (Free)

## ⚠️ Important Note

While Hugging Face Spaces is 100% free, it's designed for AI/ML demos, not production business apps. For a production solar quotation system, **Render is recommended** (see DEPLOYMENT.md).

However, if you want to deploy on Hugging Face for testing/demo purposes, follow this guide.

## Features & Limitations

### ✅ Pros:
- 100% Free forever
- No credit card required
- Public or private spaces
- Good for demos and testing

### ⚠️ Cons:
- File persistence issues (database may reset)
- Not designed for business apps
- Slower performance
- Limited to 16GB RAM

---

## Step-by-Step Deployment

### 1. Create Hugging Face Account
- Go to https://huggingface.co/join
- Sign up (free, no credit card)
- Verify your email

### 2. Create a New Space
- Go to https://huggingface.co/new-space
- **Space name**: `solar-quotation` (or your choice)
- **License**: Apache-2.0
- **SDK**: Select **Docker**
- **Hardware**: CPU basic (free)
- **Visibility**: Public or Private
- Click "Create Space"

### 3. Prepare Your Repository

You'll need to add a `README.md` with special Hugging Face headers:

```bash
cd d:\Project
```

Create a file called `README_HF.md` with this content:

```markdown
---
title: Solar Quotation System
emoji: ☀️
colorFrom: purple
colorTo: blue
sdk: docker
app_port: 7860
pinned: false
---

# Solar Energy Quotation System

Professional solar energy quotation and proposal generation system.

## Features
- Generate accurate solar energy quotes
- Professional PDF reports with charts
- User management (Admin & Sales Reps)
- Embeddable calculator widget
- Company branding with logo upload

## Default Login
- Email: admin@solar.com
- Password: admin123

**⚠️ Change the default password after first login!**
```

### 4. Push to Hugging Face

```bash
# Initialize git if not already done
git init

# Add all files
git add .
git commit -m "Initial commit"

# Add Hugging Face remote
git remote add hf https://huggingface.co/spaces/YOUR_USERNAME/solar-quotation

# Rename README for Hugging Face
git mv README.md README_LOCAL.md
git mv README_HF.md README.md
git add .
git commit -m "Update README for Hugging Face"

# Push to Hugging Face
git push hf main
```

Replace `YOUR_USERNAME` with your Hugging Face username.

### 5. Wait for Deployment
- Go to your Space URL: `https://huggingface.co/spaces/YOUR_USERNAME/solar-quotation`
- Hugging Face will automatically build and deploy
- Initial build takes 5-10 minutes
- Watch the build logs in the "Building" tab

### 6. Access Your App
Once deployed:
- App URL: `https://YOUR_USERNAME-solar-quotation.hf.space`
- Login with default credentials
- Change password immediately

---

## Important: Database Persistence

**Warning**: Hugging Face Spaces may reset your database on rebuilds. To avoid data loss:

### Option 1: Use Hugging Face Datasets (Recommended)
Store data in Hugging Face Datasets instead of SQLite. This requires code changes.

### Option 2: External Database
Use a free PostgreSQL database:
- ElephantSQL (20MB free): https://www.elephantsql.com
- Supabase (500MB free): https://supabase.com

Update `database.py` to use PostgreSQL instead of SQLite.

### Option 3: Accept Data Loss
For demo purposes only - data may be lost on restarts.

---

## Troubleshooting

### Build Fails
- Check build logs in Hugging Face
- Ensure Dockerfile is present
- Verify requirements.txt has all dependencies

### App Not Loading
- Check port is set to 7860 in README.md header
- Verify uvicorn command in Dockerfile uses port 7860

### Database Issues
- Files uploaded (logos) will be lost on restart
- SQLite data resets on container restart
- Consider using external storage

---

## Alternative: Keep on Render

For a real production deployment with:
- Persistent database ✅
- Reliable file storage ✅
- Better performance ✅
- No data loss ✅

**Use Render instead** - it's still 100% free with no credit card required!

See `DEPLOYMENT.md` for Render deployment guide.
