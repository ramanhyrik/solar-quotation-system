# Deploy to Render (100% Free)

## Quick Start - 5 Steps to Deploy

### Step 1: Push to GitHub

```bash
cd d:\Project

# Initialize Git
git init
git add .
git commit -m "Solar Quotation System - Ready for deployment"

# Create repository on GitHub (https://github.com/new)
# Then connect it:
git remote add origin https://github.com/YOUR_USERNAME/solar-quotation.git
git branch -M main
git push -u origin main
```

### Step 2: Create Render Account
- Go to https://render.com
- Click "Get Started for Free"
- Sign up with GitHub
- **No credit card required!**

### Step 3: Create Web Service
1. Click "New +" → "Web Service"
2. Click "Connect account" for GitHub
3. Find and select your `solar-quotation` repository
4. Fill in the settings:

```
Name: solar-quotation-system
Runtime: Python 3
Branch: main
Build Command: pip install -r requirements.txt
Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT
```

5. Select **Free** plan
6. Click "Create Web Service"

### Step 4: Add Persistent Disk (IMPORTANT!)
This preserves your database and uploaded files.

1. After service is created, go to service page
2. Click "Disks" in left sidebar
3. Click "Add Disk"
4. Configure:
```
Name: solar-data
Mount Path: /opt/render/project/src
Size: 1 GB
```
5. Click "Save"

**Note**: Adding a disk will trigger a redeploy (takes 2-3 minutes)

### Step 5: Access Your App!

After deployment completes (3-5 minutes):

- Your app URL: `https://solar-quotation-system.onrender.com`
- Login: admin@solar.com
- Password: admin123

**⚠️ Change your password immediately after first login!**

---

## Post-Deployment Setup

### 1. Change Admin Password
- Login to `/login`
- Go to Users page
- Update admin password

### 2. Configure Company Settings
- Go to Admin Panel
- Update:
  - Company name
  - Phone, email, address
  - Upload logo (300x100px recommended)

### 3. Configure Pricing
- Set price per kWp
- Set production per kWp
- Set tariff rate

### 4. Test Everything
- Create a test quote
- Generate PDF
- Download PDF and verify charts
- Test widget embedding (copy embed code)

---

## Important Notes

### Free Tier Limitations:
- ✅ 100% Free forever
- ✅ 750 hours/month (always-on if only service)
- ⚠️ Spins down after 15 min inactivity
- ⚠️ Takes ~50 seconds to wake up

### Keeping It Awake (Optional):
Use a free uptime monitor to ping your app every 10 minutes:
- UptimeRobot: https://uptimerobot.com (free)
- Cron-job.org: https://cron-job.org (free)

Set it to ping: `https://your-app.onrender.com` every 10 minutes

### Custom Domain (Free):
Render free tier supports custom domains!
1. Go to service settings → "Custom Domains"
2. Add your domain
3. Update DNS records as shown
4. Automatic HTTPS/SSL included

---

## Troubleshooting

### Build Failed?
- Check build logs in Render dashboard
- Ensure requirements.txt is correct
- Verify Python version (3.11 works best)

### App Not Loading?
- Wait a minute (might be cold start)
- Check if service is "Live" in Render dashboard
- View logs for errors

### Database Not Persisting?
- Verify disk is mounted at `/opt/render/project/src`
- Check disk is attached in Render dashboard
- Disk takes effect after redeploy

### Uploads Not Saving?
- Ensure disk is properly mounted
- Check `static/uploads/` directory permissions
- Verify disk size hasn't exceeded 1GB

---

## Updating Your App

When you make code changes:

```bash
git add .
git commit -m "Description of changes"
git push origin main
```

Render automatically redeploys when you push to GitHub!

---

## Support

- Render Documentation: https://render.com/docs
- Render Community: https://community.render.com
- This app's admin panel has built-in help

---

## Next Steps

1. ✅ Deploy to Render
2. ✅ Change admin password
3. ✅ Configure company settings
4. ✅ Upload logo
5. ✅ Create sales rep users
6. ✅ Test quote generation
7. ✅ Embed calculator widget on your website
8. ✅ Share your app URL with your team!

**Your solar quotation system is production-ready!** 🎉
