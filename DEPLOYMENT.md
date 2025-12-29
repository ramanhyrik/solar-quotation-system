# Deployment Guide

## Manual Roof Designer

This application uses a **manual polygon drawing approach** for roof boundary definition and solar panel placement. No AI or computer vision models are required.

## System Requirements

- **Memory**: Works perfectly on free tiers (512MB RAM)
- **Disk Space**: Minimal (< 100 MB for application code)
- **Dependencies**: Lightweight Python libraries only

## Deployment Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

All dependencies are lightweight and compatible with free hosting tiers:
- FastAPI for web framework
- Shapely for geometry calculations
- Pillow for basic image handling
- ReportLab for PDF generation
- NumPy for numerical operations

### 2. Start Server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

### 3. Deploy to Render (Free Tier)

The application is optimized for Render's free tier (512MB RAM):

```bash
# Push to git
git push origin main

# Render will automatically:
# - Install dependencies from requirements.txt
# - Start the server
# - No manual model downloads needed!
```

## How It Works

### User Workflow

1. **Upload Roof Image**: User uploads a satellite or drone image of the roof
2. **Draw Roof Boundary**: Manually click points to draw the roof polygon
3. **Add Exclusion Zones**: Drag rectangles to mark chimneys, vents, or shaded areas
4. **Configure Panels**: Select panel specifications (size, power, orientation)
5. **Calculate Layout**: System optimally places panels within the drawn boundaries
6. **Generate Quote**: Create professional PDF quote with layout visualization

### Technical Approach

- **No AI Detection**: Users manually define roof boundaries (more accurate than AI)
- **Geometry Calculations**: Shapely library handles polygon validation and panel placement
- **Grid-Based Layout**: Optimal panel placement using geometric algorithms
- **Realistic Rendering**: Solar panels rendered with authentic dark blue-grey color and cell grid patterns

## Advantages of Manual Approach

✓ **No Heavy Models**: Eliminates 2.4 GB SAM model and OpenCV dependencies
✓ **Free Tier Compatible**: Runs comfortably in 512MB RAM
✓ **Fast Deployment**: No model downloads, instant startup
✓ **User Control**: Customers define exact roof boundaries and exclusions
✓ **Higher Accuracy**: Manual drawing more precise than AI for complex roofs
✓ **Lightweight**: Total application size < 100 MB

## Memory Usage

- **Application**: ~50-100 MB
- **Per Request**: ~10-20 MB
- **Total Peak**: ~150 MB (well within 512MB free tier limit)

## File Structure

```
project/
├── main.py                    # FastAPI application
├── roof_detector.py           # Panel layout calculator
├── requirements.txt           # Lightweight dependencies only
├── templates/
│   ├── roof_designer.html     # Manual drawing interface
│   └── ...
├── static/
│   └── roof_images/          # Uploaded images
└── database.db               # SQLite database
```

## Browser Requirements

Users need a modern browser with:
- HTML5 Canvas support
- JavaScript enabled
- Minimum 1280x720 resolution (recommended)

## Troubleshooting

### Issue: Panels not appearing
**Solution**: Ensure roof polygon has at least 3 points and is closed

### Issue: "Invalid polygon" error
**Solution**: Check that roof boundary doesn't self-intersect

### Issue: No panels fit in roof
**Solution**: Adjust pixels_per_meter scale or draw larger roof boundary

## Performance

- **Image Upload**: < 1 second
- **Panel Calculation**: < 2 seconds for typical roof (50-100 panels)
- **PDF Generation**: < 3 seconds
- **Total Quote Generation**: < 10 seconds end-to-end

## Scaling

For high-traffic deployments:
- Use Render paid tier for more memory
- Add Redis for session caching
- Use CDN for static assets
- Consider PostgreSQL for database

## Support

For issues or questions, check:
- Application logs: `uvicorn` console output
- Browser console: F12 developer tools
- Database: Check `roof_designs` table for saved polygons
