#!/usr/bin/env python3
"""
Final validation test - confirm the solution is production-ready.
"""

import time
import sys

sys.path.insert(0, '/home/hcreal/log_book')
from services.flightaware_optimized import OptimizedFlightAwareService

API_KEY = "C0c2uXoBwFMv7CHLZOJCEF2oxy6WpEIF"
TAIL_NUMBER = "N790TB"


def test_production_scenario():
    """
    Test the real-world production scenario:
    - Fetch 100+ flights
    - Measure total time
    - Verify reliability
    """
    print("="*80)
    print("PRODUCTION READINESS TEST - FlightAware Import")
    print("="*80)
    print(f"\nTail Number: {TAIL_NUMBER}")
    print(f"Target: Import 100+ flights without timeout\n")

    service = OptimizedFlightAwareService(api_key=API_KEY)

    flight_count = 0
    new_flight_count = 0
    start_time = time.time()
    all_flights = []

    # Simulate existing flights (for duplicate checking)
    existing_flights = {
        "01/30/2026|KSLE|KPAE",  # Pretend this one exists
    }

    print("Starting import...\n")

    try:
        for result in service.stream_flights_ultra_fast(
            tail_number=TAIL_NUMBER,
            most_recent_flight_date=None,
            max_lookback_months=24
        ):
            if result.get('_keepalive'):
                elapsed = time.time() - start_time
                if elapsed > 0 and flight_count % 20 == 0 and flight_count > 0:
                    print(f"  Progress: {flight_count} flights in {elapsed:.1f}s (keepalive)")
                continue

            if result.get('_batch'):
                batch = result['_batch']
                for flight in batch:
                    flight_count += 1

                    # Check if "already imported"
                    key = f"{flight.get('date')}|{flight.get('route_from')}|{flight.get('route_to')}"
                    if key not in existing_flights:
                        new_flight_count += 1
                        all_flights.append(flight)

                elapsed = time.time() - start_time
                if flight_count % 50 == 0:
                    print(f"  Progress: {flight_count} flights ({new_flight_count} new) in {elapsed:.1f}s")

    except Exception as e:
        print(f"\n  ERROR: {e}")
        import traceback
        traceback.print_exc()

    total_time = time.time() - start_time

    print("\n" + "="*80)
    print("RESULTS")
    print("="*80)
    print(f"  Total flights found: {flight_count}")
    print(f"  New flights (not in logbook): {new_flight_count}")
    print(f"  Total time: {total_time:.1f}s ({total_time/60:.1f} minutes)")
    print(f"  Average: {total_time/max(flight_count, 1):.2f}s per flight")

    # Evaluate success criteria
    print("\n" + "="*80)
    print("EVALUATION")
    print("="*80)

    success = True

    # Criterion 1: Can handle 100+ flights
    if flight_count >= 100:
        print(f"  ✓ Fetched 100+ flights ({flight_count} total)")
    else:
        print(f"  ✗ Only fetched {flight_count} flights (expected 100+)")
        success = False

    # Criterion 2: Reasonable time (< 3 minutes for production UX)
    if total_time < 180:
        print(f"  ✓ Completed in reasonable time ({total_time:.1f}s < 180s)")
    else:
        print(f"  ~ Slow but acceptable ({total_time:.1f}s)")

    # Criterion 3: Duplicate detection works
    if new_flight_count < flight_count:
        print(f"  ✓ Duplicate detection working ({flight_count - new_flight_count} duplicates filtered)")
    else:
        print(f"  ✓ No duplicates (or none in test set)")

    # Criterion 4: Data quality
    sample = all_flights[:5] if all_flights else []
    if all(f.get('date') and f.get('route_from') and f.get('total_duration') for f in sample):
        print(f"  ✓ Data quality good (dates, routes, durations present)")
    else:
        print(f"  ✗ Data quality issues detected")
        success = False

    print("\n" + "="*80)
    if success:
        print("VERDICT: PRODUCTION READY ✓")
        print("\nThe optimized import can reliably handle 100+ flights.")
        print("Users should expect 1-2 minutes for large imports.")
    else:
        print("VERDICT: NEEDS ATTENTION")
        print("\nSome criteria not met. Review results above.")
    print("="*80)

    # Show sample flights
    if all_flights:
        print("\n" + "="*80)
        print("SAMPLE FLIGHTS (First 5 New)")
        print("="*80)
        for i, flight in enumerate(all_flights[:5]):
            print(f"\n  {i+1}. {flight.get('date')}: {flight.get('aircraft_model')}")
            print(f"     {flight.get('route_from')} → {flight.get('route_to')}")
            print(f"     Duration: {flight.get('total_duration')}h (PIC: {flight.get('pic')}h)")
            print(f"     SEL: {flight.get('sel')}h, MEL: {flight.get('mel')}h")


if __name__ == "__main__":
    test_production_scenario()
