"""
Fast FlightAware import - two-phase approach.

Phase 1: Fetch flight IDs and basic data FAST (no heavy processing)
Phase 2: Enrich with airport lookups and calculations (done separately)

This eliminates timeout issues by keeping the initial stream under 10-15 seconds
even for 100+ flights.
"""

from datetime import datetime, timedelta
from typing import Optional
import certifi
import requests
import urllib3
from config import Config

# FlightAware's SSL cert expired 2026-02-03. Suppress warnings until they renew.
# TODO: Remove verify=False once FlightAware renews their SSL certificate
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class FastFlightAwareService:
    """Lightweight FlightAware service that defers expensive operations."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.FLIGHTAWARE_API_KEY
        self.base_url = Config.FLIGHTAWARE_API_URL

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make authenticated request to FlightAware API."""
        if not self.api_key:
            raise ValueError(
                "FlightAware API key not configured. Set FLIGHTAWARE_API_KEY in .env"
            )

        headers = {
            "x-apikey": self.api_key,
            "Accept": "application/json",
        }

        url = f"{self.base_url}{endpoint}"
        # TODO: Change verify back to certifi.where() once FlightAware renews SSL cert
        response = requests.get(url, headers=headers, params=params, timeout=30, verify=False)

        if response.status_code == 401:
            raise ValueError("Invalid FlightAware API key")
        elif response.status_code == 404:
            return {"flights": [], "positions": []}
        elif response.status_code != 200:
            raise Exception(
                f"FlightAware API error: {response.status_code} - {response.text}"
            )

        return response.json()

    def get_flights_minimal_streaming(
        self,
        tail_number: str,
        most_recent_flight_date: Optional[datetime] = None,
        max_lookback_months: int = 24,
    ):
        """
        Stream flights with MINIMAL processing - just extract raw data.
        No airport lookups, no calculations, no heavy operations.

        Yields:
            Minimal flight dictionaries with raw FlightAware data
        """
        # Clean up tail number
        tail_number = tail_number.upper().strip()
        if not tail_number.startswith("N"):
            tail_number = f"N{tail_number}"

        seen_ids = set()

        # Determine date range
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = today - timedelta(days=1)

        if most_recent_flight_date:
            start_dt = most_recent_flight_date + timedelta(days=1)
        else:
            start_dt = end_dt - timedelta(days=max_lookback_months * 30)

        if start_dt > end_dt:
            return

        # First, try recent flights (last 10 days)
        try:
            recent_data = self._make_request(f"/flights/{tail_number}")
            recent_flights = recent_data.get("flights", [])
            for flight in recent_flights:
                flight_id = flight.get("fa_flight_id")
                if flight_id and flight_id not in seen_ids:
                    seen_ids.add(flight_id)
                    yield self._extract_minimal_data(flight)
                elif not flight_id:
                    yield self._extract_minimal_data(flight)
        except Exception:
            pass

        # Fetch historical data in 30-day windows (larger = faster)
        # FlightAware actually supports up to 6-7 days per call for /history endpoint
        # But we can use larger windows and let them handle it
        window_days = 30
        current_end = end_dt

        # Collect all flights first, then yield them (batch processing)
        batch = []
        batch_size = 20  # Yield in batches to keep connection alive

        while current_end > start_dt:
            current_start = current_end - timedelta(days=window_days)
            if current_start < start_dt:
                current_start = start_dt

            params = {
                "start": current_start.strftime("%Y-%m-%dT00:00:00Z"),
                "end": current_end.strftime("%Y-%m-%dT00:00:00Z"),
            }

            try:
                # Yield a keepalive signal before API call
                yield {"_keepalive": True}

                data = self._make_request(f"/history/flights/{tail_number}", params)
                flights = data.get("flights", [])

                # Process flights in this window
                for flight in flights:
                    if flight.get("cancelled"):
                        continue

                    flight_id = flight.get("fa_flight_id")
                    if flight_id and flight_id not in seen_ids:
                        seen_ids.add(flight_id)
                        batch.append(self._extract_minimal_data(flight))
                    elif not flight_id:
                        batch.append(self._extract_minimal_data(flight))

                    # Yield batch when it reaches size
                    if len(batch) >= batch_size:
                        for flight_data in batch:
                            yield flight_data
                        batch = []

            except Exception as e:
                # Try smaller window on error (might be exceeding API limits)
                if window_days > 7:
                    # Retry with 6-day window
                    print(f"Retrying with smaller window for {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}")
                    retry_end = current_end
                    while retry_end > current_start:
                        retry_start = retry_end - timedelta(days=6)
                        if retry_start < current_start:
                            retry_start = current_start

                        retry_params = {
                            "start": retry_start.strftime("%Y-%m-%dT00:00:00Z"),
                            "end": retry_end.strftime("%Y-%m-%dT00:00:00Z"),
                        }

                        try:
                            data = self._make_request(f"/history/flights/{tail_number}", retry_params)
                            flights = data.get("flights", [])
                            for flight in flights:
                                if flight.get("cancelled"):
                                    continue
                                flight_id = flight.get("fa_flight_id")
                                if flight_id and flight_id not in seen_ids:
                                    seen_ids.add(flight_id)
                                    batch.append(self._extract_minimal_data(flight))
                                elif not flight_id:
                                    batch.append(self._extract_minimal_data(flight))

                                if len(batch) >= batch_size:
                                    for flight_data in batch:
                                        yield flight_data
                                    batch = []
                        except Exception:
                            pass  # Skip this window

                        retry_end = retry_start
                else:
                    print(
                        f"Warning: Failed to fetch history for {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}: {e}"
                    )

            current_end = current_start

        # Yield remaining flights in batch
        for flight_data in batch:
            yield flight_data

    def _extract_minimal_data(self, flight: dict) -> dict:
        """
        Extract ONLY the essential data from a FlightAware flight.
        NO airport lookups, NO calculations, NO heavy operations.
        """
        # Parse times for date only
        departure_time = flight.get("actual_off") or flight.get("scheduled_off") or ""
        arrival_time = flight.get("actual_on") or flight.get("scheduled_on") or ""

        # Calculate duration (fast, simple math)
        duration = 0.0
        duration_estimated = False
        flight_date = ""

        if departure_time and arrival_time:
            try:
                dep_dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
                arr_dt = datetime.fromisoformat(arrival_time.replace("Z", "+00:00"))
                duration = round((arr_dt - dep_dt).total_seconds() / 3600, 1)
                flight_date = dep_dt.strftime("%m/%d/%Y")

                # Mark if using scheduled times
                if not flight.get("actual_off") or not flight.get("actual_on"):
                    duration_estimated = True
            except Exception:
                pass

        # If no duration from times, try filed_ete
        if duration == 0.0 and flight.get("filed_ete"):
            try:
                duration = round(flight["filed_ete"] / 3600, 1)
                duration_estimated = True
            except Exception:
                pass

        # Get airport codes directly from FlightAware (no lookups!)
        origin = flight.get("origin", {}) or {}
        destination = flight.get("destination", {}) or {}

        # Use ICAO codes if available, otherwise mark as needing enrichment
        route_from = origin.get("code_icao") or origin.get("code") or "-"
        route_to = destination.get("code_icao") or destination.get("code") or "-"

        # Get aircraft info
        aircraft = flight.get("aircraft_type") or ""
        tail_number = flight.get("registration") or ""

        # Simple single/multi engine detection
        is_sel = aircraft.upper() in [
            "TBM7", "TBM8", "TBM9", "TBM", "PC12", "C208",
            "C172", "C182", "C206", "PA28", "PA32", "SR22", "SR20"
        ]

        # Store raw data for later enrichment
        return {
            "date": flight_date,
            "aircraft_model": aircraft,
            "aircraft_ident": tail_number.upper(),
            "route_from": route_from,
            "route_to": route_to,
            "total_duration": duration,
            "duration_estimated": duration_estimated,
            "pic": duration,
            "sel": duration if is_sel else 0.0,
            "mel": 0.0 if is_sel else duration,
            # Defaults - will be enriched later
            "day": duration,  # Default to all day
            "night": 0.0,
            "cross_country": duration if route_from != route_to else 0.0,
            "actual_inst": 0.0,
            "simulated_inst": 0.0,
            "num_inst_app": 0,
            "landings_day": 1,
            "landings_night": 0,
            "sic": 0.0,
            "dual_recd": 0.0,
            "dual_given": 0.0,
            "solo": 0.0,
            "remarks": "",
            # Store raw data for enrichment
            "fa_flight_id": flight.get("fa_flight_id", ""),
            "departure_time": departure_time,
            "arrival_time": arrival_time,
            "origin_lat": origin.get("latitude"),
            "origin_lon": origin.get("longitude"),
            "dest_lat": destination.get("latitude"),
            "dest_lon": destination.get("longitude"),
            # Flag that this needs enrichment
            "_needs_enrichment": True,
        }

    def enrich_flight_entry(self, entry: dict) -> dict:
        """
        Enrich a minimal flight entry with airport lookups and calculations.
        This is done AFTER the initial import, not during streaming.
        """
        from services.airport_lookup import (
            find_closest_airport,
            get_airport_coordinates,
        )
        from services.sun_calculator import estimate_night_hours, is_night_landing

        # If already enriched, return as-is
        if not entry.get("_needs_enrichment"):
            return entry

        # Resolve airport codes if needed
        route_from = entry.get("route_from", "-")
        route_to = entry.get("route_to", "-")

        # Check if we need to look up airports by coordinates
        if route_from == "-" or not (len(route_from) == 4 and route_from.isalpha()):
            origin_lat = entry.get("origin_lat")
            origin_lon = entry.get("origin_lon")

            if origin_lat is not None and origin_lon is not None:
                airport = find_closest_airport(
                    origin_lat, origin_lon, max_distance_nm=150,
                    pure_distance=True, icao_only=True
                )
                if airport:
                    route_from = f"{airport['icao']}*"

        if route_to == "-" or not (len(route_to) == 4 and route_to.isalpha()):
            dest_lat = entry.get("dest_lat")
            dest_lon = entry.get("dest_lon")

            if dest_lat is not None and dest_lon is not None:
                airport = find_closest_airport(
                    dest_lat, dest_lon, max_distance_nm=150,
                    pure_distance=True, icao_only=True
                )
                if airport:
                    route_to = f"{airport['icao']}*"

        # Update airport codes
        entry["route_from"] = route_from
        entry["route_to"] = route_to

        # Calculate night hours if we have times and destination coordinates
        departure_time = entry.get("departure_time")
        arrival_time = entry.get("arrival_time")
        dest_lat = entry.get("dest_lat")
        dest_lon = entry.get("dest_lon")

        if all([departure_time, arrival_time, dest_lat, dest_lon]):
            try:
                dep_dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
                arr_dt = datetime.fromisoformat(arrival_time.replace("Z", "+00:00"))

                # Calculate night hours
                night_hours = estimate_night_hours(dep_dt, arr_dt, dest_lat, dest_lon)
                entry["night"] = night_hours
                entry["day"] = round(max(0, entry["total_duration"] - night_hours), 1)

                # Determine landing type
                if is_night_landing(arr_dt, dest_lat, dest_lon):
                    entry["landings_night"] = 1
                    entry["landings_day"] = 0
            except Exception as e:
                # If enrichment fails, keep defaults
                pass

        # Remove enrichment flag and temporary data
        entry.pop("_needs_enrichment", None)
        entry.pop("departure_time", None)
        entry.pop("arrival_time", None)
        entry.pop("origin_lat", None)
        entry.pop("origin_lon", None)
        entry.pop("dest_lat", None)
        entry.pop("dest_lon", None)

        return entry
