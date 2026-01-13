"""
Satellite Imagery Service with Multiple Providers

PRIMARY (NO CARD REQUIRED):
- OpenStreetMap Tiles - 100% FREE, no API key, no card details
- Quality: Good for most use cases

ALTERNATIVE (Requires card on file):
- Mapbox Static API - 100k requests/month FREE (requires MAPBOX_ACCESS_TOKEN)
- Google Maps Static API - $200 free credit/month (requires GOOGLE_MAPS_API_KEY)
"""

import requests
import os
from typing import Optional, Tuple
from io import BytesIO
from PIL import Image

# Mapbox API configuration
MAPBOX_ACCESS_TOKEN = os.getenv("MAPBOX_ACCESS_TOKEN", "")
MAPBOX_STATIC_API = "https://api.mapbox.com/styles/v1"

# Default map style (satellite imagery)
DEFAULT_STYLE = "mapbox/satellite-v9"

# Image settings
DEFAULT_WIDTH = 1200  # pixels
DEFAULT_HEIGHT = 800  # pixels
DEFAULT_ZOOM = 20  # Maximum zoom for building-level detail

# Cache directory for satellite images
CACHE_DIR = os.path.join("static", "map_cache")
os.makedirs(CACHE_DIR, exist_ok=True)


def _get_cache_path(latitude: float, longitude: float, zoom: int, width: int, height: int) -> str:
    """Generate cache file path for satellite image"""
    filename = f"sat_{latitude:.6f}_{longitude:.6f}_z{zoom}_{width}x{height}.jpg"
    return os.path.join(CACHE_DIR, filename)


def fetch_satellite_image_osm(
    latitude: float,
    longitude: float,
    zoom: int = 19,  # OSM max zoom is 19
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    use_cache: bool = True
) -> Optional[bytes]:
    """
    Fetch satellite imagery using OpenStreetMap tiles (100% FREE, no API key)

    Uses tile servers that provide satellite/aerial imagery:
    - Esri WorldImagery (free, no registration)
    - Quality: Good enough for roof detection
    - No rate limits for reasonable use

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        zoom: Map zoom level (1-19, default: 19 for building detail)
        width: Image width in pixels (max: 1280)
        height: Image height in pixels (max: 1280)
        use_cache: Whether to use cached images (default: True)

    Returns:
        Image data as bytes, or None if fetch fails

    Note:
        - Zoom 19 provides ~0.3 meters per pixel
        - Completely FREE, no API key required
        - No card details needed
    """
    from PIL import Image, ImageDraw
    import math

    # Check cache first
    cache_path = _get_cache_path(latitude, longitude, zoom, width, height)
    if use_cache and os.path.exists(cache_path):
        print(f"[OSM] Cache hit: {cache_path}")
        with open(cache_path, "rb") as f:
            return f.read()

    try:
        print(f"[OSM] Fetching tiles: lat={latitude:.6f}, lon={longitude:.6f}, zoom={zoom}")

        # Calculate tile coordinates
        # Convert lat/lon to tile numbers
        def deg2num(lat_deg, lon_deg, zoom):
            lat_rad = math.radians(lat_deg)
            n = 2.0 ** zoom
            xtile = int((lon_deg + 180.0) / 360.0 * n)
            ytile = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
            return (xtile, ytile)

        # Calculate how many tiles we need
        tiles_x = math.ceil(width / 256)
        tiles_y = math.ceil(height / 256)

        # Get center tile
        center_x, center_y = deg2num(latitude, longitude, zoom)

        # Calculate tile range
        start_x = center_x - tiles_x // 2
        start_y = center_y - tiles_y // 2

        # Create composite image
        composite = Image.new('RGB', (tiles_x * 256, tiles_y * 256))

        # Esri WorldImagery tile server (FREE, no API key)
        tile_url_template = "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"

        print(f"[OSM] Fetching {tiles_x}x{tiles_y} tiles...")

        # Fetch tiles
        for i in range(tiles_x):
            for j in range(tiles_y):
                tile_x = start_x + i
                tile_y = start_y + j

                # Build tile URL
                tile_url = tile_url_template.format(z=zoom, x=tile_x, y=tile_y)

                try:
                    response = requests.get(tile_url, timeout=10)
                    response.raise_for_status()

                    tile_img = Image.open(BytesIO(response.content))
                    composite.paste(tile_img, (i * 256, j * 256))

                except Exception as e:
                    print(f"[OSM] Warning: Failed to fetch tile ({tile_x}, {tile_y}): {e}")
                    # Continue with other tiles

        # Crop to desired size
        composite = composite.crop((0, 0, width, height))

        # Convert to bytes
        output = BytesIO()
        composite.save(output, format='JPEG', quality=85)
        image_data = output.getvalue()

        print(f"[OSM] SUCCESS: {len(image_data)} bytes")

        # Save to cache
        if use_cache:
            with open(cache_path, "wb") as f:
                f.write(image_data)
            print(f"[OSM] Cached: {cache_path}")

        return image_data

    except Exception as e:
        print(f"[OSM] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def fetch_satellite_image(
    latitude: float,
    longitude: float,
    zoom: int = DEFAULT_ZOOM,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    use_cache: bool = True,
    prefer_free: bool = True
) -> Optional[bytes]:
    """
    Fetch satellite imagery for given coordinates

    Automatically chooses provider:
    1. OpenStreetMap tiles (FREE, no API key) - if prefer_free=True
    2. Mapbox Static API - if MAPBOX_ACCESS_TOKEN configured
    3. Fallback to OSM if Mapbox fails

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        zoom: Map zoom level (1-22, default: 20 for building detail)
        width: Image width in pixels (max: 1280)
        height: Image height in pixels (max: 1280)
        use_cache: Whether to use cached images (default: True)
        prefer_free: Prefer FREE option (OSM) over Mapbox (default: True)

    Returns:
        Image data as bytes, or None if fetch fails

    Example:
        >>> image_data = fetch_satellite_image(32.0644, 34.7755, zoom=19)
        >>> if image_data:
        ...     with open("roof.jpg", "wb") as f:
        ...         f.write(image_data)
    """
    # If prefer_free or Mapbox not configured, use OpenStreetMap
    if prefer_free or not MAPBOX_ACCESS_TOKEN:
        print("[SATELLITE] Using OpenStreetMap tiles (FREE, no API key)")
        # OSM max zoom is 19, adjust if needed
        osm_zoom = min(zoom, 19)
        result = fetch_satellite_image_osm(latitude, longitude, osm_zoom, width, height, use_cache)

        if result:
            return result

        # If OSM fails and Mapbox available, try Mapbox as fallback
        if MAPBOX_ACCESS_TOKEN:
            print("[SATELLITE] OSM failed, trying Mapbox fallback...")
        else:
            return None

    # Try Mapbox if configured
    if MAPBOX_ACCESS_TOKEN:
        return fetch_satellite_image_mapbox(latitude, longitude, zoom, width, height, use_cache)

    return None


def fetch_satellite_image_mapbox(
    latitude: float,
    longitude: float,
    zoom: int = DEFAULT_ZOOM,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    use_cache: bool = True
) -> Optional[bytes]:
    """
    Fetch satellite imagery using Mapbox Static API

    NOTE: Requires MAPBOX_ACCESS_TOKEN and card on file
    FREE tier: 100,000 requests/month
    """
    # Check cache first
    cache_path = _get_cache_path(latitude, longitude, zoom, width, height)
    if use_cache and os.path.exists(cache_path):
        print(f"[MAPBOX] Cache hit: {cache_path}")
        with open(cache_path, "rb") as f:
            return f.read()

    if not MAPBOX_ACCESS_TOKEN:
        print("[MAPBOX] ERROR: MAPBOX_ACCESS_TOKEN not configured")
        return None

    try:
        url = (
            f"{MAPBOX_STATIC_API}/{DEFAULT_STYLE}/static/"
            f"{longitude},{latitude},{zoom}/{width}x{height}"
        )

        print(f"[MAPBOX] Fetching: lat={latitude:.6f}, lon={longitude:.6f}, zoom={zoom}")

        response = requests.get(
            url,
            params={'access_token': MAPBOX_ACCESS_TOKEN},
            timeout=30
        )

        response.raise_for_status()
        image_data = response.content

        # Validate image
        img = Image.open(BytesIO(image_data))
        img.verify()
        print(f"[MAPBOX] SUCCESS: {img.format} image, {img.size[0]}x{img.size[1]}px")

        # Save to cache
        if use_cache:
            with open(cache_path, "wb") as f:
                f.write(image_data)
            print(f"[MAPBOX] Cached: {cache_path}")

        return image_data

    except Exception as e:
        print(f"[MAPBOX] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def get_meters_per_pixel(latitude: float, zoom: int) -> float:
    """
    Calculate meters per pixel at given latitude and zoom level

    Uses Mercator projection scale factor:
    meters_per_pixel = (Earth_circumference * cos(latitude)) / (256 * 2^zoom)

    Args:
        latitude: Latitude coordinate (affects scale)
        zoom: Map zoom level

    Returns:
        Meters per pixel at given location and zoom

    Example:
        >>> mpp = get_meters_per_pixel(32.0644, 20)
        >>> print(f"{mpp:.3f} meters per pixel")
        0.149 meters per pixel
    """
    from math import cos, radians

    # Earth circumference at equator (meters)
    earth_circumference = 40075016.686

    # Mercator projection scale factor
    meters_per_pixel = (
        earth_circumference * cos(radians(latitude))
    ) / (256 * (2 ** zoom))

    return meters_per_pixel


def calculate_optimal_zoom(
    latitude: float,
    roof_length_m: float,
    image_width_px: int = DEFAULT_WIDTH
) -> int:
    """
    Calculate optimal zoom level to fit roof in image

    Args:
        latitude: Latitude coordinate
        roof_length_m: Approximate roof length in meters
        image_width_px: Image width in pixels

    Returns:
        Optimal zoom level (1-22)

    Example:
        >>> zoom = calculate_optimal_zoom(32.0644, 20)  # 20m wide roof
        >>> print(f"Optimal zoom: {zoom}")
        Optimal zoom: 19
    """
    # We want the roof to take up ~60% of image width
    target_coverage = 0.6
    desired_width_m = roof_length_m / target_coverage

    # Binary search for optimal zoom
    for zoom in range(22, 0, -1):
        mpp = get_meters_per_pixel(latitude, zoom)
        image_coverage_m = mpp * image_width_px

        if image_coverage_m >= desired_width_m:
            return min(zoom, 22)  # Cap at max zoom

    return 18  # Default fallback


def get_bounding_box_from_image(
    latitude: float,
    longitude: float,
    zoom: int,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT
) -> Tuple[float, float, float, float]:
    """
    Calculate geographic bounding box (min_lat, min_lon, max_lat, max_lon)
    for a map image at given center and zoom

    Args:
        latitude: Center latitude
        longitude: Center longitude
        zoom: Zoom level
        width: Image width in pixels
        height: Image height in pixels

    Returns:
        Tuple: (min_lat, min_lon, max_lat, max_lon)
    """
    from math import cos, radians, degrees, tan, atan, sinh, asinh, pi

    # Meters per pixel
    mpp = get_meters_per_pixel(latitude, zoom)

    # Image dimensions in meters
    width_m = mpp * width
    height_m = mpp * height

    # Approximate coordinate offsets (simplified Mercator)
    # 1 degree latitude ≈ 111,111 meters
    # 1 degree longitude ≈ 111,111 * cos(latitude) meters

    meters_per_degree_lat = 111111
    meters_per_degree_lon = 111111 * cos(radians(latitude))

    lat_offset = (height_m / 2) / meters_per_degree_lat
    lon_offset = (width_m / 2) / meters_per_degree_lon

    min_lat = latitude - lat_offset
    max_lat = latitude + lat_offset
    min_lon = longitude - lon_offset
    max_lon = longitude + lon_offset

    return (min_lat, min_lon, max_lat, max_lon)


def is_mapbox_configured() -> bool:
    """Check if Mapbox API token is configured"""
    return bool(MAPBOX_ACCESS_TOKEN)


def get_setup_instructions() -> str:
    """Get setup instructions for Mapbox API"""
    return """
    Mapbox Setup Instructions:

    1. Create free Mapbox account: https://account.mapbox.com/
    2. Get your access token from the dashboard
    3. Set environment variable:

       Windows (PowerShell):
       $env:MAPBOX_ACCESS_TOKEN="your_token_here"

       Linux/Mac:
       export MAPBOX_ACCESS_TOKEN="your_token_here"

       Or add to .env file:
       MAPBOX_ACCESS_TOKEN=your_token_here

    4. Free tier includes: 100,000 requests/month

    Alternative (if Mapbox quota exceeded):
    - Use Google Maps Static API (requires billing, $200 free credit)
    - Use OpenStreetMap tiles (lower quality satellite imagery)
    """


# Google Maps Static API alternative (requires billing enabled)
def fetch_satellite_image_google(
    latitude: float,
    longitude: float,
    zoom: int = 20,
    width: int = DEFAULT_WIDTH,
    height: int = DEFAULT_HEIGHT,
    api_key: Optional[str] = None
) -> Optional[bytes]:
    """
    Alternative: Fetch satellite imagery using Google Maps Static API

    Note: Requires Google Cloud account with billing enabled
    Free tier: $200 credit/month = ~28,000 static map loads
    After free credit: $2 per 1,000 requests

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate
        zoom: Map zoom level (1-21)
        width: Image width in pixels (max: 640 for free tier, 2048 for paid)
        height: Image height in pixels
        api_key: Google Maps API key

    Returns:
        Image data as bytes, or None if fetch fails
    """
    if not api_key:
        api_key = os.getenv("GOOGLE_MAPS_API_KEY", "")
        if not api_key:
            print("[GOOGLE MAPS] ERROR: GOOGLE_MAPS_API_KEY not configured")
            return None

    try:
        # Google Maps Static API URL
        url = "https://maps.googleapis.com/maps/api/staticmap"

        params = {
            'center': f"{latitude},{longitude}",
            'zoom': zoom,
            'size': f"{width}x{height}",
            'maptype': 'satellite',
            'key': api_key
        }

        print(f"[GOOGLE MAPS] Fetching: lat={latitude:.6f}, lon={longitude:.6f}, zoom={zoom}")

        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()

        image_data = response.content

        # Validate image
        img = Image.open(BytesIO(image_data))
        img.verify()
        print(f"[GOOGLE MAPS] SUCCESS: {img.size[0]}x{img.size[1]}px")

        return image_data

    except Exception as e:
        print(f"[GOOGLE MAPS] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


if __name__ == "__main__":
    # Test satellite imagery service
    print("=" * 60)
    print("Testing Satellite Imagery Service")
    print("=" * 60)

    # Check configuration
    print("\n[CHECK] Mapbox Configuration")
    if is_mapbox_configured():
        print("✓ Mapbox API token is configured")
    else:
        print("✗ Mapbox API token NOT configured")
        print(get_setup_instructions())
        exit(1)

    # Test coordinates (Tel Aviv, Rothschild Blvd)
    test_lat = 32.0644444
    test_lon = 34.7755556

    # Test 1: Calculate meters per pixel
    print(f"\n[TEST 1] Meters per Pixel Calculation")
    for zoom in [18, 19, 20, 21]:
        mpp = get_meters_per_pixel(test_lat, zoom)
        print(f"  Zoom {zoom}: {mpp:.3f} m/px")

    # Test 2: Calculate optimal zoom
    print(f"\n[TEST 2] Optimal Zoom Calculation")
    for roof_size in [10, 20, 50]:
        zoom = calculate_optimal_zoom(test_lat, roof_size)
        print(f"  {roof_size}m roof: Zoom {zoom}")

    # Test 3: Fetch satellite image
    print(f"\n[TEST 3] Fetch Satellite Image")
    image_data = fetch_satellite_image(
        test_lat, test_lon,
        zoom=20,
        width=800,
        height=600,
        use_cache=True
    )

    if image_data:
        print(f"✓ Image fetched: {len(image_data)} bytes")

        # Save test image
        test_path = "test_satellite.jpg"
        with open(test_path, "wb") as f:
            f.write(image_data)
        print(f"✓ Saved to: {test_path}")
    else:
        print("✗ Image fetch failed")

    # Test 4: Calculate bounding box
    print(f"\n[TEST 4] Calculate Bounding Box")
    bbox = get_bounding_box_from_image(test_lat, test_lon, 20, 800, 600)
    print(f"  Min: ({bbox[0]:.6f}, {bbox[1]:.6f})")
    print(f"  Max: ({bbox[2]:.6f}, {bbox[3]:.6f})")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
