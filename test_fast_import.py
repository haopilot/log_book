#!/usr/bin/env python3
"""
Test the new fast two-phase import system.
"""

import time
import sys

sys.path.insert(0, '/home/hcreal/log_book')
from services.flightaware_fast import FastFlightAwareService

API_KEY = "C0c2uXoBwFMv7CHLZOJCEF2oxy6WpEIF"
TAIL_NUMBER = "N790TB"


def test_fast_streaming():
    """Test the fast minimal streaming."""
    print("Testing FAST Two-Phase Import")
    print("="*80)
    print("Phase 1: Minimal Data Fetch (should be FAST)\n")

    service = FastFlightAwareService(api_key=API_KEY)

    flight_count = 0
    start_time = time.time()
    last_yield_time = start_time
    max_gap = 0

    flights = []

    try:
        for entry in service.get_flights_minimal_streaming(
            tail_number=TAIL_NUMBER,
            most_recent_flight_date=None,
            max_lookback_months=24
        ):
            if entry.get('_keepalive'):
                continue

            flight_count += 1
            current_time = time.time()
            gap = current_time - last_yield_time
            max_gap = max(max_gap, gap)

            flights.append(entry)

            # Print every 10 flights
            if flight_count % 10 == 0:
                elapsed = current_time - start_time
                print(f"Flight {flight_count:3d}: {elapsed:6.1f}s | Gap: {gap:5.3f}s | Max: {max_gap:5.3f}s")

                # Check timeout threshold
                if elapsed > 60:
                    print(f"\nWARNING: Exceeded 60s at {flight_count} flights")
                if elapsed > 120:
                    print(f"\nCRITICAL: Exceeded 120s at {flight_count} flights")
                    break

            last_yield_time = current_time

    except Exception as e:
        print(f"\nERROR: {e}")

    phase1_time = time.time() - start_time

    print("\n" + "="*80)
    print("PHASE 1 RESULTS:")
    print(f"  Flights fetched: {flight_count}")
    print(f"  Total time: {phase1_time:.2f}s")
    print(f"  Average: {phase1_time/max(flight_count, 1):.3f}s per flight")
    print(f"  Max gap: {max_gap:.3f}s")
    print("="*80)

    # Analyze results
    if phase1_time > 60:
        print("\nPROBLEM: Still too slow for 60s timeout")
    elif phase1_time > 30:
        print("\nOK: Under 60s but still a bit slow")
    else:
        print("\nEXCELLENT: Fast enough to avoid timeouts!")

    if max_gap > 5:
        print(f"WARNING: Max gap of {max_gap:.3f}s is concerning")
    else:
        print(f"GOOD: Max gap of {max_gap:.3f}s is acceptable")

    # Test phase 2 enrichment
    print("\n" + "="*80)
    print("Phase 2: Enrichment (done selectively, not during stream)\n")

    if flights:
        print("Testing enrichment on 5 sample flights...")
        phase2_start = time.time()

        for i, flight in enumerate(flights[:5]):
            enrich_start = time.time()
            enriched = service.enrich_flight_entry(flight)
            enrich_time = time.time() - enrich_start

            print(f"  Flight {i+1}: {enrich_time:.3f}s - {enriched.get('route_from')} to {enriched.get('route_to')}")
            print(f"    Day: {enriched.get('day')}h, Night: {enriched.get('night')}h")

        phase2_time = time.time() - phase2_start
        print(f"\nEnrichment time (5 flights): {phase2_time:.2f}s")
        print(f"Average: {phase2_time/5:.3f}s per flight")

    print("\n" + "="*80)
    print("SUMMARY:")
    print(f"  Phase 1 (Fetch): {phase1_time:.2f}s for {flight_count} flights")
    print(f"  Phase 2 (Enrich): Can be done later, on-demand, or in batches")
    print(f"  Total connection time: {phase1_time:.2f}s (vs ~{1.6*flight_count:.1f}s with old method)")
    print("="*80)


if __name__ == "__main__":
    test_fast_streaming()
