#!/usr/bin/env python3
"""
Performance testing for FlightAware API integration.
Tests API response times and identifies bottlenecks in the import process.
"""

import time
from datetime import datetime, timedelta
import requests
import sys

API_KEY = "C0c2uXoBwFMv7CHLZOJCEF2oxy6WpEIF"
BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
TAIL_NUMBER = "N790TB"


def test_api_call(endpoint, params=None):
    """Make a single API call and measure response time."""
    headers = {
        "x-apikey": API_KEY,
        "Accept": "application/json",
    }

    url = f"{BASE_URL}{endpoint}"
    start = time.time()

    try:
        response = requests.get(url, headers=headers, params=params, timeout=30)
        elapsed = time.time() - start

        if response.status_code == 200:
            data = response.json()
            return {
                "success": True,
                "elapsed": elapsed,
                "data": data,
                "size": len(response.content)
            }
        else:
            return {
                "success": False,
                "elapsed": elapsed,
                "status": response.status_code,
                "error": response.text
            }
    except Exception as e:
        elapsed = time.time() - start
        return {
            "success": False,
            "elapsed": elapsed,
            "error": str(e)
        }


def test_bulk_history_fetch():
    """Test fetching history in different window sizes."""
    print("\n" + "="*80)
    print("TEST 1: API Response Times for Different Window Sizes")
    print("="*80)

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = today - timedelta(days=1)

    window_sizes = [1, 3, 6, 14, 30]

    for window_days in window_sizes:
        start_dt = end_dt - timedelta(days=window_days)
        params = {
            "start": start_dt.strftime("%Y-%m-%dT00:00:00Z"),
            "end": end_dt.strftime("%Y-%m-%dT00:00:00Z"),
        }

        print(f"\nWindow size: {window_days} days ({start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')})")
        result = test_api_call(f"/history/flights/{TAIL_NUMBER}", params)

        if result["success"]:
            flights = result["data"].get("flights", [])
            print(f"  Time: {result['elapsed']:.2f}s | Flights: {len(flights)} | Size: {result['size']:,} bytes")
        else:
            print(f"  FAILED: {result.get('error', 'Unknown error')}")


def test_sequential_windows():
    """Test fetching 100 flights worth of data with different strategies."""
    print("\n" + "="*80)
    print("TEST 2: Time to Fetch ~100 Flights with Different Strategies")
    print("="*80)

    # Estimate: N790TB has ~50-60 flights per year
    # To get ~100 flights, we need about 2 years of data

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = today - timedelta(days=1)
    start_dt = end_dt - timedelta(days=730)  # 2 years

    strategies = [
        ("6-day windows", 6),
        ("14-day windows", 14),
        ("30-day windows", 30),
    ]

    for strategy_name, window_days in strategies:
        print(f"\n{strategy_name}:")
        print(f"  Fetching from {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}")

        total_time = 0
        total_flights = 0
        api_calls = 0
        current_end = end_dt

        while current_end > start_dt:
            current_start = current_end - timedelta(days=window_days)
            if current_start < start_dt:
                current_start = start_dt

            params = {
                "start": current_start.strftime("%Y-%m-%dT00:00:00Z"),
                "end": current_end.strftime("%Y-%m-%dT00:00:00Z"),
            }

            result = test_api_call(f"/history/flights/{TAIL_NUMBER}", params)
            api_calls += 1

            if result["success"]:
                flights = result["data"].get("flights", [])
                total_flights += len(flights)
                total_time += result["elapsed"]
                print(f"    Window {api_calls}: {result['elapsed']:.2f}s, {len(flights)} flights")
            else:
                print(f"    Window {api_calls}: FAILED - {result.get('error', 'Unknown')}")
                break

            current_end = current_start

        print(f"  TOTAL: {total_time:.2f}s for {total_flights} flights across {api_calls} API calls")
        print(f"  Average: {total_time/api_calls:.2f}s per call, {total_time/max(total_flights, 1):.3f}s per flight")


def test_processing_overhead():
    """Test the overhead of airport lookups and calculations."""
    print("\n" + "="*80)
    print("TEST 3: Processing Overhead (Airport Lookups, Calculations)")
    print("="*80)

    # Import the services
    sys.path.insert(0, '/home/hcreal/log_book')
    from services.flightaware import FlightAwareService
    from services.airport_lookup import find_closest_airport, get_airport_coordinates
    from services.sun_calculator import estimate_night_hours, is_night_landing

    # Fetch a small sample
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = today - timedelta(days=1)
    start_dt = end_dt - timedelta(days=30)

    params = {
        "start": start_dt.strftime("%Y-%m-%dT00:00:00Z"),
        "end": end_dt.strftime("%Y-%m-%dT00:00:00Z"),
    }

    print("\nFetching sample flights...")
    result = test_api_call(f"/history/flights/{TAIL_NUMBER}", params)

    if not result["success"]:
        print("Failed to fetch sample data")
        return

    flights = result["data"].get("flights", [])
    print(f"Processing {len(flights)} flights...")

    service = FlightAwareService()

    # Test processing time
    processing_start = time.time()
    for flight in flights:
        if flight.get("cancelled"):
            continue
        entry = service.flight_to_logbook_entry(flight)
    processing_time = time.time() - processing_start

    print(f"\nProcessing time: {processing_time:.2f}s for {len(flights)} flights")
    print(f"Average: {processing_time/len(flights):.3f}s per flight")

    # Test individual operations
    print("\nTesting individual operations (100 iterations):")

    # Airport lookup
    test_lat, test_lon = 33.9425, -118.408  # LAX
    start = time.time()
    for _ in range(100):
        find_closest_airport(test_lat, test_lon, max_distance_nm=150, pure_distance=True, icao_only=True)
    elapsed = time.time() - start
    print(f"  Airport lookup: {elapsed/100*1000:.2f}ms per lookup")

    # Coordinate lookup
    start = time.time()
    for _ in range(100):
        get_airport_coordinates("KLAX")
    elapsed = time.time() - start
    print(f"  Coordinate lookup: {elapsed/100*1000:.2f}ms per lookup")

    # Night hours calculation
    dep_dt = datetime(2024, 6, 1, 10, 0, 0)
    arr_dt = datetime(2024, 6, 1, 12, 30, 0)
    start = time.time()
    for _ in range(100):
        estimate_night_hours(dep_dt, arr_dt, test_lat, test_lon)
    elapsed = time.time() - start
    print(f"  Night hours calc: {elapsed/100*1000:.2f}ms per calculation")


def test_sse_simulation():
    """Simulate SSE streaming and identify timeout issues."""
    print("\n" + "="*80)
    print("TEST 4: SSE Streaming Simulation (50+ Flights)")
    print("="*80)

    sys.path.insert(0, '/home/hcreal/log_book')
    from services.flightaware import FlightAwareService

    service = FlightAwareService()

    # Simulate fetching 100+ flights
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = today - timedelta(days=1)
    start_dt = end_dt - timedelta(days=730)  # 2 years

    print(f"Streaming flights from {start_dt.strftime('%Y-%m-%d')} to {end_dt.strftime('%Y-%m-%d')}")
    print("Simulating SSE keepalives every 5 flights...\n")

    flight_count = 0
    start_time = time.time()
    last_yield = start_time
    max_gap = 0

    try:
        for entry in service.get_flights_as_logbook_entries_streaming(
            tail_number=TAIL_NUMBER,
            most_recent_flight_date=None,
            max_lookback_months=24
        ):
            flight_count += 1
            current_time = time.time()
            gap = current_time - last_yield
            max_gap = max(max_gap, gap)

            if flight_count % 5 == 0:
                elapsed = current_time - start_time
                print(f"  Flight {flight_count}: {elapsed:.1f}s elapsed, {gap:.2f}s since last yield (max gap: {max_gap:.2f}s)")

                # Check if we'd timeout (typically 60s for most proxies/load balancers)
                if elapsed > 60:
                    print(f"\n  WARNING: Would timeout after {flight_count} flights!")
                    break

            last_yield = current_time
    except Exception as e:
        print(f"\n  ERROR: {e}")

    total_time = time.time() - start_time
    print(f"\nCompleted: {flight_count} flights in {total_time:.2f}s")
    print(f"Average: {total_time/flight_count:.3f}s per flight")
    print(f"Max gap between yields: {max_gap:.2f}s")

    if max_gap > 15:
        print("\nBOTTLENECK IDENTIFIED: Processing is too slow between yields!")
        print("Each flight takes too long to process. Need to optimize or defer processing.")


if __name__ == "__main__":
    print("FlightAware API Performance Testing")
    print(f"Tail Number: {TAIL_NUMBER}")
    print(f"API Key: {API_KEY[:10]}...")

    # Run tests
    test_bulk_history_fetch()
    test_sequential_windows()
    test_processing_overhead()
    test_sse_simulation()

    print("\n" + "="*80)
    print("TESTING COMPLETE")
    print("="*80)
