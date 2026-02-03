#!/usr/bin/env python3
"""Quick test to identify the bottleneck."""

import time
from datetime import datetime, timedelta
import requests
import sys

API_KEY = "C0c2uXoBwFMv7CHLZOJCEF2oxy6WpEIF"
BASE_URL = "https://aeroapi.flightaware.com/aeroapi"
TAIL_NUMBER = "N790TB"


def test_single_api_call():
    """Test a single API call."""
    print("Testing single API call...")

    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    end_dt = today - timedelta(days=1)
    start_dt = end_dt - timedelta(days=6)

    params = {
        "start": start_dt.strftime("%Y-%m-%dT00:00:00Z"),
        "end": end_dt.strftime("%Y-%m-%dT00:00:00Z"),
    }

    headers = {
        "x-apikey": API_KEY,
        "Accept": "application/json",
    }

    url = f"{BASE_URL}/history/flights/{TAIL_NUMBER}"

    start = time.time()
    response = requests.get(url, headers=headers, params=params, timeout=30)
    elapsed = time.time() - start

    print(f"Status: {response.status_code}")
    print(f"Time: {elapsed:.2f}s")

    if response.status_code == 200:
        data = response.json()
        flights = data.get("flights", [])
        print(f"Flights found: {len(flights)}")
        return flights
    else:
        print(f"Error: {response.text}")
        return []


def test_processing():
    """Test processing overhead."""
    print("\nTesting processing overhead...")

    flights = test_single_api_call()

    if not flights:
        print("No flights to process")
        return

    sys.path.insert(0, '/home/hcreal/log_book')
    from services.flightaware import FlightAwareService

    service = FlightAwareService()

    print(f"\nProcessing {len(flights)} flights...")
    start = time.time()

    for i, flight in enumerate(flights):
        flight_start = time.time()
        entry = service.flight_to_logbook_entry(flight)
        flight_time = time.time() - flight_start
        print(f"  Flight {i+1}: {flight_time:.3f}s - {entry.get('route_from')} to {entry.get('route_to')}")

    total_time = time.time() - start
    print(f"\nTotal processing time: {total_time:.2f}s")
    print(f"Average per flight: {total_time/len(flights):.3f}s")


if __name__ == "__main__":
    print("Quick Performance Test\n")
    test_processing()
