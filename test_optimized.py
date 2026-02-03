#!/usr/bin/env python3
"""Test the optimized batched import."""

import time
import sys

sys.path.insert(0, '/home/hcreal/log_book')
from services.flightaware_optimized import OptimizedFlightAwareService

API_KEY = "C0c2uXoBwFMv7CHLZOJCEF2oxy6WpEIF"
TAIL_NUMBER = "N790TB"


def test_optimized():
    print("Testing OPTIMIZED Batched Import")
    print("="*80)

    service = OptimizedFlightAwareService(api_key=API_KEY)

    flight_count = 0
    batch_count = 0
    start_time = time.time()
    all_flights = []

    try:
        for result in service.stream_flights_ultra_fast(
            tail_number=TAIL_NUMBER,
            most_recent_flight_date=None,
            max_lookback_months=24
        ):
            if result.get('_keepalive'):
                elapsed = time.time() - start_time
                print(f"  Keepalive at {elapsed:.1f}s ({flight_count} flights so far)")
                continue

            if result.get('_batch'):
                batch = result['_batch']
                batch_count += 1
                flight_count += len(batch)
                all_flights.extend(batch)

                elapsed = time.time() - start_time
                print(f"  Batch {batch_count}: +{len(batch)} flights (total {flight_count}) at {elapsed:.1f}s")

                if elapsed > 60:
                    print(f"\n  WARNING: Exceeded 60s at {flight_count} flights!")
                if elapsed > 120:
                    print(f"\n  CRITICAL: Exceeded 120s - stopping test")
                    break

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()

    total_time = time.time() - start_time

    print("\n" + "="*80)
    print("RESULTS:")
    print(f"  Total flights: {flight_count}")
    print(f"  Total batches: {batch_count}")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Average per flight: {total_time/max(flight_count, 1):.3f}s")
    print(f"  Average per batch: {total_time/max(batch_count, 1):.2f}s")
    print("="*80)

    if total_time < 60:
        print("\nSUCCESS: Under 60s timeout!")
    elif total_time < 120:
        print("\nOK: Under 120s but might timeout on some proxies")
    else:
        print("\nPROBLEM: Still too slow")

    # Test enrichment
    if all_flights:
        print("\n" + "="*80)
        print("Testing batch enrichment (first 10 flights)...")
        print("="*80)

        enrich_start = time.time()
        enriched = service.enrich_batch(all_flights[:10])
        enrich_time = time.time() - enrich_start

        print(f"\nEnriched 10 flights in {enrich_time:.2f}s ({enrich_time/10:.3f}s each)")
        for i, flight in enumerate(enriched[:3]):
            print(f"  {i+1}. {flight['date']}: {flight['route_from']} -> {flight['route_to']}")
            print(f"     Day: {flight['day']}h, Night: {flight['night']}h")


if __name__ == "__main__":
    test_optimized()
