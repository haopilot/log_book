#!/usr/bin/env python3
"""
Identify the exact bottleneck causing timeouts after 50 flights.
"""

import time
from datetime import datetime, timedelta
import sys

sys.path.insert(0, '/home/hcreal/log_book')
from services.flightaware import FlightAwareService

API_KEY = "C0c2uXoBwFMv7CHLZOJCEF2oxy6WpEIF"
TAIL_NUMBER = "N790TB"


def simulate_sse_stream():
    """Simulate SSE streaming to identify timeout point."""
    print("Simulating SSE Stream (100+ flights)")
    print("="*80)

    service = FlightAwareService(api_key=API_KEY)

    # Fetch 2 years of history to get ~100 flights
    flight_count = 0
    start_time = time.time()
    last_yield_time = start_time
    max_gap = 0
    cumulative_time = 0

    try:
        for entry in service.get_flights_as_logbook_entries_streaming(
            tail_number=TAIL_NUMBER,
            most_recent_flight_date=None,
            max_lookback_months=24
        ):
            flight_count += 1
            current_time = time.time()
            gap = current_time - last_yield_time
            cumulative_time = current_time - start_time
            max_gap = max(max_gap, gap)

            # Print every 10 flights
            if flight_count % 10 == 0:
                print(f"Flight {flight_count:3d}: {cumulative_time:6.1f}s elapsed | Gap: {gap:5.2f}s | Max gap: {max_gap:5.2f}s")

                # Most proxies/load balancers timeout after 60s
                if cumulative_time > 60:
                    print(f"\nWARNING: Exceeded 60s timeout threshold at {flight_count} flights")

                # Some timeout at 120s
                if cumulative_time > 120:
                    print(f"\nCRITICAL: Exceeded 120s timeout threshold at {flight_count} flights")
                    break

            last_yield_time = current_time

    except Exception as e:
        print(f"\nERROR at flight {flight_count}: {e}")

    total_time = time.time() - start_time

    print("\n" + "="*80)
    print("RESULTS:")
    print(f"  Total flights processed: {flight_count}")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Average per flight: {total_time/max(flight_count, 1):.3f}s")
    print(f"  Max gap between yields: {max_gap:.2f}s")
    print("="*80)

    # Analysis
    print("\nANALYSIS:")
    if max_gap > 10:
        print(f"  PROBLEM: Max gap of {max_gap:.2f}s is too long between yields")
        print("  This causes the SSE connection to appear stalled to the client")
    if total_time / max(flight_count, 1) > 1.0:
        print(f"  PROBLEM: Average processing time of {total_time/max(flight_count, 1):.3f}s per flight is too slow")
        print("  At this rate, 50 flights would take ~50+ seconds")
    if total_time > 60:
        print(f"  PROBLEM: Total time of {total_time:.2f}s exceeds typical 60s timeout")

    print("\nRECOMMENDATIONS:")
    print("  1. Two-phase import: Fetch minimal data fast, enrich later")
    print("  2. Defer expensive operations (airport lookup, sunset calc)")
    print("  3. Batch API calls differently")
    print("  4. Add progress persistence for resume capability")


if __name__ == "__main__":
    simulate_sse_stream()
