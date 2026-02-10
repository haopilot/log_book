"""
Weather service for estimating IMC time using Open-Meteo historical data.

Samples cloud cover along the flight route and estimates time spent in clouds
based on cruise altitude and flight phase.
"""

import math
from datetime import datetime
from typing import Optional

import requests


# Minimum IMC to record (below this, don't bother logging)
MIN_IMC_HOURS = 0.1


def great_circle_points(lat1: float, lon1: float, lat2: float, lon2: float, num_points: int) -> list[tuple[float, float]]:
    """Generate points along the great circle path between two coordinates."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)

    points = []
    for i in range(num_points):
        f = i / (num_points - 1) if num_points > 1 else 0

        # Great circle distance
        d = math.acos(min(1, max(-1,
            math.sin(lat1_r) * math.sin(lat2_r) +
            math.cos(lat1_r) * math.cos(lat2_r) * math.cos(lon2_r - lon1_r)
        )))

        if d < 0.0001:
            points.append((lat1, lon1))
            continue

        # Spherical interpolation
        A = math.sin((1 - f) * d) / math.sin(d)
        B = math.sin(f * d) / math.sin(d)

        x = A * math.cos(lat1_r) * math.cos(lon1_r) + B * math.cos(lat2_r) * math.cos(lon2_r)
        y = A * math.cos(lat1_r) * math.sin(lon1_r) + B * math.cos(lat2_r) * math.sin(lon2_r)
        z = A * math.sin(lat1_r) + B * math.sin(lat2_r)

        lat = math.degrees(math.atan2(z, math.sqrt(x*x + y*y)))
        lon = math.degrees(math.atan2(y, x))
        points.append((lat, lon))

    return points


def haversine_nm(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in nautical miles between two coordinates."""
    R = 3440.065  # Earth radius in nm
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat, dlon = lat2_r - lat1_r, lon2_r - lon1_r
    a = math.sin(dlat/2)**2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def query_cloud_cover(lat: float, lon: float, date: str, timeout: float = 8.0) -> Optional[dict]:
    """
    Query Open-Meteo for cloud cover at a specific location and date.

    Args:
        lat: Latitude
        lon: Longitude
        date: Date in YYYY-MM-DD format
        timeout: Request timeout in seconds

    Returns:
        Dict with 'low', 'mid', 'high' cloud cover percentages, or None on error
    """
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": lat,
        "longitude": lon,
        "start_date": date,
        "end_date": date,
        "hourly": "cloud_cover_low,cloud_cover_mid,cloud_cover_high",
        "timezone": "UTC"
    }

    try:
        resp = requests.get(url, params=params, timeout=timeout)
        if resp.status_code == 200:
            hourly = resp.json().get("hourly", {})
            low = hourly.get("cloud_cover_low", [0] * 24)
            mid = hourly.get("cloud_cover_mid", [0] * 24)
            high = hourly.get("cloud_cover_high", [0] * 24)

            # Average daytime hours (14-22 UTC covers most US flight times)
            avg_low = sum(low[14:22]) / 8 if len(low) >= 22 else 0
            avg_mid = sum(mid[14:22]) / 8 if len(mid) >= 22 else 0
            avg_high = sum(high[14:22]) / 8 if len(high) >= 22 else 0

            return {"low": avg_low, "mid": avg_mid, "high": avg_high}
    except Exception:
        pass

    return None


def estimate_imc(
    dep_lat: float,
    dep_lon: float,
    arr_lat: float,
    arr_lon: float,
    flight_date: str,
    duration_hrs: float,
    cruise_alt_ft: int = 18000
) -> float:
    """
    Estimate actual IMC time for a flight by sampling weather along the route.

    Args:
        dep_lat, dep_lon: Departure coordinates
        arr_lat, arr_lon: Arrival coordinates
        flight_date: Date in YYYY-MM-DD format
        duration_hrs: Flight duration in hours
        cruise_alt_ft: Cruise altitude in feet (default 18000 for turboprop)

    Returns:
        Estimated IMC hours (0.0 if below MIN_IMC_HOURS threshold)
    """
    if duration_hrs <= 0:
        return 0.0

    # Calculate route distance and sampling density
    route_dist = haversine_nm(dep_lat, dep_lon, arr_lat, arr_lon)
    if route_dist < 10:
        return 0.0  # Too short to bother

    # Sample every ~40nm (matches weather grid resolution)
    num_samples = max(5, min(40, int(route_dist / 40)))
    sample_points = great_circle_points(dep_lat, dep_lon, arr_lat, arr_lon, num_samples)

    # Query weather at each point
    weather_data = []
    for lat, lon in sample_points:
        cloud = query_cloud_cover(lat, lon, flight_date)
        if cloud:
            weather_data.append(cloud)
        else:
            weather_data.append({"low": 0, "mid": 0, "high": 0})

    if not weather_data:
        return 0.0

    # Calculate IMC for each segment
    segment_time = duration_hrs / (num_samples - 1)
    total_imc = 0.0

    for i in range(len(weather_data) - 1):
        w1, w2 = weather_data[i], weather_data[i + 1]

        # Average cloud cover for segment
        seg_low = (w1["low"] + w2["low"]) / 2
        seg_mid = (w1["mid"] + w2["mid"]) / 2
        seg_high = (w1["high"] + w2["high"]) / 2

        # Determine flight phase based on progress
        progress = (i + 0.5) / (num_samples - 1)

        # Climb/descent phases use mixed low/mid clouds
        if progress < 0.08:  # Climb
            relevant_cloud = seg_low * 0.6 + seg_mid * 0.4
        elif progress > 0.92:  # Descent
            relevant_cloud = seg_low * 0.6 + seg_mid * 0.4
        else:  # Cruise - cloud layer depends on altitude
            if cruise_alt_ft < 10000:
                relevant_cloud = seg_low  # Low-level clouds
            elif cruise_alt_ft < 26000:
                relevant_cloud = seg_mid  # Mid-level clouds (FL100-FL260)
            else:
                relevant_cloud = seg_high  # High-level clouds (FL260+)

        # Convert cloud coverage to IMC probability
        # Only significant cloud cover counts as actual IMC
        if relevant_cloud > 70:
            imc_fraction = 0.8  # High probability of being in cloud
        elif relevant_cloud > 50:
            imc_fraction = 0.4  # Moderate probability
        elif relevant_cloud > 30:
            imc_fraction = 0.1  # Low probability (brief encounters)
        else:
            imc_fraction = 0.0  # Clear

        total_imc += segment_time * imc_fraction

    # Apply minimum threshold
    if total_imc < MIN_IMC_HOURS:
        return 0.0

    return round(total_imc, 1)


def estimate_imc_for_flight(flight: dict) -> float:
    """
    Convenience function to estimate IMC for a flight dict.

    Expects flight to have:
        - date: MM/DD/YYYY format
        - route_from, route_to: ICAO codes
        - total_duration: hours
        - _raw.origin.latitude/longitude (optional)
        - _raw.destination.latitude/longitude (optional)

    Returns estimated IMC hours or 0.0
    """
    # Get coordinates from raw flight data or look up from airport codes
    raw = flight.get("_raw", {})
    origin = raw.get("origin", {}) or {}
    dest = raw.get("destination", {}) or {}

    dep_lat = origin.get("latitude")
    dep_lon = origin.get("longitude")
    arr_lat = dest.get("latitude")
    arr_lon = dest.get("longitude")

    # If no coordinates in raw data, try to look up from airport codes
    if not (dep_lat and dep_lon and arr_lat and arr_lon):
        try:
            from services.airport_lookup import get_airport_coordinates
            if not (dep_lat and dep_lon):
                coords = get_airport_coordinates(flight.get("route_from", ""))
                if coords:
                    dep_lat, dep_lon = coords
            if not (arr_lat and arr_lon):
                coords = get_airport_coordinates(flight.get("route_to", ""))
                if coords:
                    arr_lat, arr_lon = coords
        except Exception:
            pass

    if not (dep_lat and dep_lon and arr_lat and arr_lon):
        return 0.0

    # Parse date from MM/DD/YYYY to YYYY-MM-DD
    date_str = flight.get("date", "")
    try:
        if "/" in date_str:
            dt = datetime.strptime(date_str, "%m/%d/%Y")
            iso_date = dt.strftime("%Y-%m-%d")
        else:
            iso_date = date_str
    except Exception:
        return 0.0

    duration = flight.get("total_duration", 0.0) or 0.0
    if duration <= 0:
        return 0.0

    # Default cruise altitude for TBM: FL250
    cruise_alt = 25000

    return estimate_imc(
        dep_lat, dep_lon,
        arr_lat, arr_lon,
        iso_date,
        duration,
        cruise_alt
    )
