"""
Airport lookup service.

Finds the closest airport given latitude/longitude coordinates.
Uses the airports.csv database from OurAirports.
"""

import csv
import math
import os
import re
from typing import Optional


# Path to airports.csv - check multiple locations
AIRPORTS_CSV_PATHS = [
    os.path.join(os.path.dirname(__file__), "..", "data", "airports.csv"),
    os.path.join(os.path.dirname(__file__), "..", "..", "Flight", "airports.csv"),
    "/Users/hcreal/Dev/project/Flight/airports.csv",
]

# Cache for airports data
_airports_cache: list[dict] = []


def _load_airports() -> list[dict]:
    """Load airports from CSV file into memory."""
    global _airports_cache

    if _airports_cache:
        return _airports_cache

    # Find the airports file
    airports_file = None
    for path in AIRPORTS_CSV_PATHS:
        if os.path.exists(path):
            airports_file = path
            break

    if not airports_file:
        print("Warning: airports.csv not found")
        return []

    airports = []
    try:
        with open(airports_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Only include airports with valid coordinates and ICAO codes
                try:
                    lat = float(row.get("latitude_deg", 0))
                    lon = float(row.get("longitude_deg", 0))
                    icao = row.get("icao_code") or row.get("ident", "")
                    name = row.get("name", "")
                    airport_type = row.get("type", "")

                    # Skip if no valid ICAO code or coordinates
                    if not icao or lat == 0 or lon == 0:
                        continue

                    # Prefer real airports over heliports for general aviation
                    airports.append({
                        "icao": icao,
                        "name": name,
                        "lat": lat,
                        "lon": lon,
                        "type": airport_type,
                    })
                except (ValueError, TypeError):
                    continue

        _airports_cache = airports
        print(f"Loaded {len(airports)} airports from database")
    except Exception as e:
        print(f"Warning: Failed to load airports: {e}")

    return airports


def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Calculate the great-circle distance between two points on Earth.

    Args:
        lat1, lon1: First point coordinates in degrees
        lat2, lon2: Second point coordinates in degrees

    Returns:
        Distance in nautical miles
    """
    R = 3440.065  # Earth's radius in nautical miles

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    a = (math.sin(delta_lat / 2) ** 2 +
         math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(delta_lon / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c


def parse_coordinate_string(coord_str: str) -> Optional[tuple[float, float]]:
    """
    Parse a coordinate string like "L 31.42877 124.40918" into (lat, lon).

    Args:
        coord_str: String containing coordinates

    Returns:
        Tuple of (latitude, longitude) or None if not parseable
    """
    if not coord_str:
        return None

    # Pattern: "L lat lon" or just numbers with decimals
    # Examples: "L 31.42877 124.40918", "47.123 -122.456"
    patterns = [
        r"L\s+([-\d.]+)\s+([-\d.]+)",  # "L lat lon"
        r"([-\d.]+)\s+([-\d.]+)",       # "lat lon"
    ]

    for pattern in patterns:
        match = re.search(pattern, coord_str)
        if match:
            try:
                lat = float(match.group(1))
                lon = float(match.group(2))
                # Validate reasonable coordinate ranges
                if -90 <= lat <= 90 and -180 <= lon <= 180:
                    return (lat, lon)
            except (ValueError, TypeError):
                continue

    return None


def is_coordinate_code(code: str) -> bool:
    """
    Check if an airport code looks like a coordinate string.

    Args:
        code: Airport code to check

    Returns:
        True if it looks like coordinates, False otherwise
    """
    if not code:
        return False

    # Check for patterns that indicate coordinates
    # - Starts with "L " (lat/lon marker)
    # - Contains decimal points with numbers
    if code.startswith("L "):
        return True

    # Check if it has decimal numbers (coordinates have decimals, airport codes don't)
    if re.search(r"\d+\.\d+", code):
        return True

    return False


def is_non_icao_code(code: str) -> bool:
    """
    Check if an airport code is a non-standard identifier (like BD-0034).

    Valid ICAO codes are 4 letters (e.g., KPAE, KSEA, EGLL).
    Valid IATA codes are 3 letters (e.g., SEA, LAX).

    Args:
        code: Airport code to check

    Returns:
        True if it's a non-standard code, False otherwise
    """
    if not code:
        return False

    # Already identified as coordinate
    if is_coordinate_code(code):
        return False

    # Check for codes with dashes (like BD-0034, XX-1234)
    if "-" in code:
        return True

    # Check for codes that are too long or have numbers in wrong places
    # Valid: KPAE (4 letters), SEA (3 letters), K00F (letter-number combo for small US airports)
    # Invalid: BD0034, 12345
    if len(code) > 4:
        return True

    # If mostly numbers, it's likely not a valid code
    num_digits = sum(1 for c in code if c.isdigit())
    if num_digits > 2:
        return True

    return False


def find_closest_airport(
    lat: float,
    lon: float,
    max_distance_nm: float = 50,
    prefer_types: Optional[list[str]] = None,
    pure_distance: bool = False,
    icao_only: bool = False,
) -> Optional[dict]:
    """
    Find the closest airport to given coordinates.

    Args:
        lat: Latitude in degrees
        lon: Longitude in degrees
        max_distance_nm: Maximum distance to search in nautical miles
        prefer_types: List of preferred airport types (e.g., ["large_airport", "medium_airport"])
        pure_distance: If True, ignore type preferences and use pure distance only
        icao_only: If True, only return airports with valid ICAO codes (4 letters)

    Returns:
        Dictionary with airport info, or None if no airport found within range
    """
    if prefer_types is None:
        prefer_types = ["large_airport", "medium_airport", "small_airport"]

    airports = _load_airports()
    if not airports:
        return None

    best_match = None
    best_distance = float("inf")

    for airport in airports:
        # Filter for valid ICAO codes only if requested
        if icao_only:
            icao = airport.get("icao", "")
            # Valid ICAO codes are 4 letters (e.g., KPAE, VMMC, ZGKL)
            if not (icao and len(icao) == 4 and icao.isalpha()):
                continue

        distance = haversine_distance(lat, lon, airport["lat"], airport["lon"])

        if distance > max_distance_nm:
            continue

        if pure_distance:
            # Use pure distance without type preference
            score = distance
        else:
            # Prefer certain airport types
            type_preference = 0
            if airport["type"] in prefer_types:
                type_preference = prefer_types.index(airport["type"])
            else:
                type_preference = len(prefer_types)  # Lower priority

            # Score: lower is better (distance + type penalty)
            score = distance + (type_preference * 5)  # 5nm penalty per type level

        if score < best_distance:
            best_distance = score
            best_match = {
                **airport,
                "distance_nm": round(distance, 1),
            }

    return best_match


def get_airport_coordinates(icao_code: str) -> Optional[tuple[float, float]]:
    """
    Get the coordinates for an airport by ICAO code.

    Args:
        icao_code: ICAO airport code (e.g., "KPAE")

    Returns:
        Tuple of (latitude, longitude) or None if not found
    """
    airports = _load_airports()
    icao_upper = icao_code.upper().strip()

    for airport in airports:
        if airport["icao"].upper() == icao_upper:
            return (airport["lat"], airport["lon"])

    return None


def estimate_flight_duration(
    origin: str,
    destination: str,
    cruise_speed_kts: float = 300,
) -> Optional[float]:
    """
    Estimate flight duration based on great circle distance between airports.

    Args:
        origin: Origin airport code or coordinate string
        destination: Destination airport code or coordinate string
        cruise_speed_kts: Assumed cruise speed in knots (default 300 for TBM)

    Returns:
        Estimated duration in hours, or None if cannot calculate
    """
    # Get origin coordinates
    origin_coords = None
    if is_coordinate_code(origin):
        origin_coords = parse_coordinate_string(origin)
    else:
        origin_coords = get_airport_coordinates(origin)

    # Get destination coordinates
    dest_coords = None
    if is_coordinate_code(destination):
        dest_coords = parse_coordinate_string(destination)
    else:
        dest_coords = get_airport_coordinates(destination)

    if not origin_coords or not dest_coords:
        return None

    # Calculate distance
    distance_nm = haversine_distance(
        origin_coords[0], origin_coords[1],
        dest_coords[0], dest_coords[1]
    )

    # Estimate time: distance / speed + 0.2 hours for taxi/climb/descent
    duration = (distance_nm / cruise_speed_kts) + 0.2

    return round(duration, 1)


def resolve_airport_code(code: str, max_search_nm: float = 200) -> tuple[str, bool]:
    """
    Resolve an airport code, converting coordinates to nearest airport if needed.

    Args:
        code: Airport code or coordinate string
        max_search_nm: Maximum search distance in nautical miles (default 200nm)

    Returns:
        Tuple of (ICAO airport code, was_estimated)
        - was_estimated is True if the code was derived from coordinates/lookup
    """
    if not code:
        return ("", False)

    # Check if it's a coordinate string
    if is_coordinate_code(code):
        coords = parse_coordinate_string(code)
        if coords:
            lat, lon = coords
            # Use pure_distance=True to get the actual closest airport
            airport = find_closest_airport(lat, lon, max_distance_nm=max_search_nm, pure_distance=True)
            if airport:
                return (airport["icao"], True)  # Estimated from coordinates
        return (code, False)  # Couldn't resolve, return original

    # Check if it's a non-ICAO code (like BD-0034)
    if is_non_icao_code(code):
        # For now, just mark it as needing review
        # Future: could try to look up in a database
        return (code, True)  # Mark as estimated/needs review

    # Normal ICAO/IATA code
    return (code, False)
