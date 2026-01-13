"""
Geocoding Service using Nominatim API (OpenStreetMap)
Free geocoding service with no API key required

Rate Limit: 1 request per second (enforced by Nominatim)
Documentation: https://nominatim.org/release-docs/latest/api/Search/
"""

import requests
import time
from typing import Optional, Tuple, Dict, List
from functools import lru_cache

# Nominatim API endpoint
NOMINATIM_API = "https://nominatim.openstreetmap.org"

# Rate limiting (1 request per second)
_last_request_time = 0
_min_request_interval = 1.0  # seconds

# User agent (required by Nominatim terms of service)
USER_AGENT = "SolarQuotationSystem/1.0 (Solar Panel Design Software)"

# Cache for geocoding results (reduces API calls)
_geocoding_cache = {}


def _rate_limit():
    """Enforce rate limit of 1 request per second"""
    global _last_request_time
    current_time = time.time()
    time_since_last = current_time - _last_request_time

    if time_since_last < _min_request_interval:
        sleep_time = _min_request_interval - time_since_last
        print(f"[GEOCODING] Rate limiting: sleeping {sleep_time:.2f}s")
        time.sleep(sleep_time)

    _last_request_time = time.time()


def geocode_address(address: str, country: str = "Israel") -> Optional[Dict]:
    """
    Convert address to coordinates (latitude, longitude)

    Args:
        address: Street address (e.g., "Rothschild Blvd 1, Tel Aviv")
        country: Country name for better accuracy (default: "Israel")

    Returns:
        Dict with:
        - latitude: float
        - longitude: float
        - display_name: str (formatted address)
        - boundingbox: list (bounding box coordinates)
        Or None if geocoding fails

    Example:
        >>> result = geocode_address("Rothschild Blvd 1, Tel Aviv")
        >>> print(result['latitude'], result['longitude'])
        32.0644444 34.7755556
    """
    # Check cache first
    cache_key = f"{address}|{country}".lower()
    if cache_key in _geocoding_cache:
        print(f"[GEOCODING] Cache hit: {address}")
        return _geocoding_cache[cache_key]

    try:
        # Enforce rate limit
        _rate_limit()

        # Build search query
        search_query = f"{address}, {country}" if country else address

        print(f"[GEOCODING] Searching: {search_query}")

        # Make API request
        response = requests.get(
            f"{NOMINATIM_API}/search",
            params={
                'q': search_query,
                'format': 'json',
                'limit': 1,
                'addressdetails': 1
            },
            headers={
                'User-Agent': USER_AGENT
            },
            timeout=10
        )

        response.raise_for_status()
        results = response.json()

        if not results:
            print(f"[GEOCODING] No results found for: {search_query}")
            return None

        # Parse first result
        result = results[0]

        geocoded = {
            'latitude': float(result['lat']),
            'longitude': float(result['lon']),
            'display_name': result['display_name'],
            'boundingbox': result['boundingbox'],
            'place_id': result.get('place_id'),
            'osm_type': result.get('osm_type'),
            'osm_id': result.get('osm_id'),
            'address_details': result.get('address', {})
        }

        # Cache result
        _geocoding_cache[cache_key] = geocoded

        print(f"[GEOCODING] SUCCESS: {geocoded['display_name']}")
        print(f"[GEOCODING] Coordinates: ({geocoded['latitude']:.6f}, {geocoded['longitude']:.6f})")

        return geocoded

    except requests.exceptions.RequestException as e:
        print(f"[GEOCODING] API request failed: {e}")
        return None
    except Exception as e:
        print(f"[GEOCODING] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def reverse_geocode(latitude: float, longitude: float) -> Optional[Dict]:
    """
    Convert coordinates to address (reverse geocoding)

    Args:
        latitude: Latitude coordinate
        longitude: Longitude coordinate

    Returns:
        Dict with:
        - display_name: str (formatted address)
        - address: dict (structured address components)
        Or None if reverse geocoding fails

    Example:
        >>> result = reverse_geocode(32.0644444, 34.7755556)
        >>> print(result['display_name'])
        'Rothschild Boulevard, Tel Aviv, Israel'
    """
    # Check cache first
    cache_key = f"reverse|{latitude:.6f}|{longitude:.6f}"
    if cache_key in _geocoding_cache:
        print(f"[REVERSE GEOCODING] Cache hit: ({latitude}, {longitude})")
        return _geocoding_cache[cache_key]

    try:
        # Enforce rate limit
        _rate_limit()

        print(f"[REVERSE GEOCODING] Looking up: ({latitude:.6f}, {longitude:.6f})")

        # Make API request
        response = requests.get(
            f"{NOMINATIM_API}/reverse",
            params={
                'lat': latitude,
                'lon': longitude,
                'format': 'json',
                'addressdetails': 1
            },
            headers={
                'User-Agent': USER_AGENT
            },
            timeout=10
        )

        response.raise_for_status()
        result = response.json()

        if 'error' in result:
            print(f"[REVERSE GEOCODING] Error: {result['error']}")
            return None

        # Parse result
        geocoded = {
            'display_name': result['display_name'],
            'address': result.get('address', {}),
            'place_id': result.get('place_id'),
            'osm_type': result.get('osm_type'),
            'osm_id': result.get('osm_id'),
            'latitude': float(result['lat']),
            'longitude': float(result['lon'])
        }

        # Cache result
        _geocoding_cache[cache_key] = geocoded

        print(f"[REVERSE GEOCODING] SUCCESS: {geocoded['display_name']}")

        return geocoded

    except requests.exceptions.RequestException as e:
        print(f"[REVERSE GEOCODING] API request failed: {e}")
        return None
    except Exception as e:
        print(f"[REVERSE GEOCODING] Error: {e}")
        import traceback
        traceback.print_exc()
        return None


def search_addresses(query: str, country: str = "Israel", limit: int = 5) -> List[Dict]:
    """
    Search for multiple address matches (for autocomplete)

    Args:
        query: Partial address query
        country: Country name for better accuracy
        limit: Maximum number of results (default: 5)

    Returns:
        List of address results, each with:
        - latitude, longitude, display_name, etc.

    Example:
        >>> results = search_addresses("Rothschild", "Israel", limit=5)
        >>> for r in results:
        ...     print(r['display_name'])
    """
    # Check cache first
    cache_key = f"search|{query}|{country}|{limit}".lower()
    if cache_key in _geocoding_cache:
        print(f"[GEOCODING SEARCH] Cache hit: {query}")
        return _geocoding_cache[cache_key]

    try:
        # Enforce rate limit
        _rate_limit()

        # Build search query
        search_query = f"{query}, {country}" if country else query

        print(f"[GEOCODING SEARCH] Searching: {search_query} (limit={limit})")

        # Make API request
        response = requests.get(
            f"{NOMINATIM_API}/search",
            params={
                'q': search_query,
                'format': 'json',
                'limit': limit,
                'addressdetails': 1
            },
            headers={
                'User-Agent': USER_AGENT
            },
            timeout=10
        )

        response.raise_for_status()
        results = response.json()

        # Parse all results
        addresses = []
        for result in results:
            addresses.append({
                'latitude': float(result['lat']),
                'longitude': float(result['lon']),
                'display_name': result['display_name'],
                'boundingbox': result['boundingbox'],
                'place_id': result.get('place_id'),
                'osm_type': result.get('osm_type'),
                'osm_id': result.get('osm_id'),
                'address_details': result.get('address', {})
            })

        # Cache results
        _geocoding_cache[cache_key] = addresses

        print(f"[GEOCODING SEARCH] Found {len(addresses)} result(s)")

        return addresses

    except requests.exceptions.RequestException as e:
        print(f"[GEOCODING SEARCH] API request failed: {e}")
        return []
    except Exception as e:
        print(f"[GEOCODING SEARCH] Error: {e}")
        import traceback
        traceback.print_exc()
        return []


def validate_coordinates(latitude: float, longitude: float) -> bool:
    """
    Validate that coordinates are within valid ranges

    Args:
        latitude: Latitude (-90 to 90)
        longitude: Longitude (-180 to 180)

    Returns:
        True if coordinates are valid
    """
    return -90 <= latitude <= 90 and -180 <= longitude <= 180


def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate distance between two coordinates (Haversine formula)

    Args:
        lat1, lon1: First coordinate
        lat2, lon2: Second coordinate

    Returns:
        Distance in kilometers
    """
    from math import radians, sin, cos, sqrt, atan2

    # Earth radius in km
    R = 6371.0

    # Convert to radians
    lat1_rad = radians(lat1)
    lon1_rad = radians(lon1)
    lat2_rad = radians(lat2)
    lon2_rad = radians(lon2)

    # Haversine formula
    dlat = lat2_rad - lat1_rad
    dlon = lon2_rad - lon1_rad

    a = sin(dlat / 2)**2 + cos(lat1_rad) * cos(lat2_rad) * sin(dlon / 2)**2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))

    distance = R * c
    return distance


if __name__ == "__main__":
    # Test geocoding service
    print("=" * 60)
    print("Testing Geocoding Service")
    print("=" * 60)

    # Test 1: Forward geocoding
    print("\n[TEST 1] Forward Geocoding")
    result = geocode_address("Rothschild Blvd 1, Tel Aviv")
    if result:
        print(f"✓ Address: {result['display_name']}")
        print(f"✓ Coordinates: ({result['latitude']:.6f}, {result['longitude']:.6f})")
    else:
        print("✗ Geocoding failed")

    # Test 2: Reverse geocoding
    print("\n[TEST 2] Reverse Geocoding")
    if result:
        reverse = reverse_geocode(result['latitude'], result['longitude'])
        if reverse:
            print(f"✓ Reverse: {reverse['display_name']}")
        else:
            print("✗ Reverse geocoding failed")

    # Test 3: Search addresses
    print("\n[TEST 3] Address Search")
    results = search_addresses("Rothschild", "Israel", limit=3)
    for i, addr in enumerate(results, 1):
        print(f"  {i}. {addr['display_name']}")

    # Test 4: Validate coordinates
    print("\n[TEST 4] Coordinate Validation")
    print(f"✓ Valid: {validate_coordinates(32.0644, 34.7755)}")
    print(f"✗ Invalid: {validate_coordinates(100.0, 200.0)}")

    print("\n" + "=" * 60)
    print("All tests completed!")
    print("=" * 60)
