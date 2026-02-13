#!/usr/bin/env python3
"""
Compare FlightAware actual tracks vs great circle paths.
Run this on the server where FLIGHTAWARE_API_KEY is configured.

Usage: python scripts/compare_track_vs_gc.py
"""

import os
import sys
import math
import requests

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()


def great_circle_points(lat1, lon1, lat2, lon2, num_points):
    """Generate points along great circle path."""
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)

    points = []
    for i in range(num_points):
        f = i / (num_points - 1) if num_points > 1 else 0

        d = math.acos(min(1, max(-1,
            math.sin(lat1_r) * math.sin(lat2_r) +
            math.cos(lat1_r) * math.cos(lat2_r) * math.cos(lon2_r - lon1_r)
        )))

        if d < 0.0001:
            points.append((lat1, lon1, 0))
            continue

        A = math.sin((1 - f) * d) / math.sin(d)
        B = math.sin(f * d) / math.sin(d)

        x = A * math.cos(lat1_r) * math.cos(lon1_r) + B * math.cos(lat2_r) * math.cos(lon2_r)
        y = A * math.cos(lat1_r) * math.sin(lon1_r) + B * math.cos(lat2_r) * math.sin(lon2_r)
        z = A * math.sin(lat1_r) + B * math.sin(lat2_r)

        lat = math.degrees(math.atan2(z, math.sqrt(x*x + y*y)))
        lon = math.degrees(math.atan2(y, x))
        points.append((lat, lon))

    return points


def haversine_nm(lat1, lon1, lat2, lon2):
    """Distance in nautical miles."""
    R = 3440.065
    lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
    lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
    dlat, dlon = lat2_r - lat1_r, lon2_r - lon1_r
    a = math.sin(dlat/2)**2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))


def main():
    api_key = os.environ.get("FLIGHTAWARE_API_KEY", "")
    if not api_key:
        print("ERROR: FLIGHTAWARE_API_KEY not configured")
        sys.exit(1)

    base_url = "https://aeroapi.flightaware.com/aeroapi"
    headers = {"x-apikey": api_key, "Accept": "application/json"}

    tail = os.environ.get("AIRCRAFT_TAIL_NUMBER", "N790TB")
    print(f"Fetching recent flights for {tail}...")

    resp = requests.get(f"{base_url}/flights/{tail}", headers=headers, timeout=30)
    if resp.status_code != 200:
        print(f"API Error: {resp.status_code} - {resp.text[:200]}")
        sys.exit(1)

    flights = resp.json().get("flights", [])
    print(f"Found {len(flights)} flights\n")

    analyzed = 0
    for flight in flights:
        # Only analyze completed flights with coordinates
        if not (flight.get("actual_off") and flight.get("actual_on")):
            continue

        origin = flight.get("origin", {}) or {}
        dest = flight.get("destination", {}) or {}

        if not (origin.get("latitude") and dest.get("latitude")):
            continue

        fa_id = flight.get("fa_flight_id")
        dep_code = origin.get("code", "????")
        arr_code = dest.get("code", "????")

        # Get track
        track_resp = requests.get(f"{base_url}/flights/{fa_id}/track",
                                  headers=headers, timeout=30)

        if track_resp.status_code != 200:
            continue

        positions = track_resp.json().get("positions", [])
        if len(positions) < 10:
            continue

        print("="*70)
        print(f"Flight: {dep_code} → {arr_code}")
        print(f"FA ID: {fa_id}")
        print(f"Track points: {len(positions)}")

        # Calculate route distance
        dep_lat, dep_lon = origin["latitude"], origin["longitude"]
        arr_lat, arr_lon = dest["latitude"], dest["longitude"]
        route_dist = haversine_nm(dep_lat, dep_lon, arr_lat, arr_lon)
        print(f"Route distance: {route_dist:.0f} nm")

        # Generate great circle path matching track density
        gc_path = great_circle_points(dep_lat, dep_lon, arr_lat, arr_lon, len(positions))

        # Compare actual vs estimated
        deviations = []
        for i, pos in enumerate(positions):
            if i >= len(gc_path):
                break
            actual_lat = pos.get("latitude", 0)
            actual_lon = pos.get("longitude", 0)
            est_lat, est_lon = gc_path[i]

            dev = haversine_nm(actual_lat, actual_lon, est_lat, est_lon)
            deviations.append(dev)

        if deviations:
            avg_dev = sum(deviations) / len(deviations)
            max_dev = max(deviations)

            print(f"\nDeviation from great circle:")
            print(f"  Average: {avg_dev:.1f} nm")
            print(f"  Maximum: {max_dev:.1f} nm")

            # Show altitude profile from actual track
            altitudes = [p.get("altitude", 0) for p in positions if p.get("altitude")]
            if altitudes:
                print(f"\nAltitude profile:")
                print(f"  Max: {max(altitudes):,} ft")
                print(f"  Avg cruise: {sum(altitudes[len(altitudes)//4:3*len(altitudes)//4])//(len(altitudes)//2):,} ft")

            # Recommendation
            print(f"\nFor IMC estimation:")
            weather_samples = max(5, int(route_dist / 40))
            print(f"  Recommended weather samples: {weather_samples} points (~40nm spacing)")

            if max_dev < 20:
                print(f"  ✓ Great circle adequate (max dev {max_dev:.0f}nm < 20nm)")
            else:
                print(f"  ⚠ Consider using actual track (max dev {max_dev:.0f}nm)")

        print()
        analyzed += 1

        if analyzed >= 3:  # Analyze up to 3 flights
            break

    if analyzed == 0:
        print("No completed flights with track data found")


if __name__ == "__main__":
    main()
