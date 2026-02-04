"""
Ultra-optimized FlightAware import with aggressive batching and minimal overhead.

Key optimizations:
1. Largest possible API windows (6 days max for /history endpoint)
2. Batch yielding - yield multiple flights at once
3. Minimal processing - only essential data extraction
4. No expensive operations during streaming
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


class OptimizedFlightAwareService:
    """Ultra-fast FlightAware service with aggressive optimizations."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.FLIGHTAWARE_API_KEY
        self.base_url = Config.FLIGHTAWARE_API_URL

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make authenticated request to FlightAware API."""
        if not self.api_key:
            raise ValueError("FlightAware API key not configured")

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
            return {"flights": []}
        elif response.status_code != 200:
            raise Exception(f"FlightAware API error: {response.status_code}")

        return response.json()

    def stream_flights_ultra_fast(
        self,
        tail_number: str,
        most_recent_flight_date: Optional[datetime] = None,
        max_lookback_months: int = 24,
    ):
        """
        Stream flights with ULTRA FAST processing.
        Yields batches of flights to minimize overhead.
        """
        # Clean tail number
        tail_number = tail_number.upper().strip()
        if not tail_number.startswith("N"):
            tail_number = f"N{tail_number}"

        seen_ids = set()
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = today - timedelta(days=1)
        is_incremental = most_recent_flight_date is not None

        if most_recent_flight_date:
            start_dt = most_recent_flight_date + timedelta(days=1)
        else:
            start_dt = end_dt - timedelta(days=max_lookback_months * 30)

        # Yield search metadata so frontend knows what's happening
        yield {"_meta": {
            "is_incremental": is_incremental,
            "start_date": start_dt.strftime("%Y-%m-%d"),
            "end_date": end_dt.strftime("%Y-%m-%d"),
            "tail_number": tail_number,
        }}

        if start_dt > end_dt:
            return

        api_errors = 0

        # Try recent flights first (fast, no windowing needed)
        try:
            recent_data = self._make_request(f"/flights/{tail_number}")
            recent_flights = recent_data.get("flights", [])
            batch = []
            for flight in recent_flights:
                if flight.get("cancelled"):
                    continue
                flight_id = flight.get("fa_flight_id")
                if flight_id and flight_id not in seen_ids:
                    seen_ids.add(flight_id)
                    batch.append(self._fast_extract(flight))

            if batch:
                yield {"_batch": batch}
        except Exception as e:
            api_errors += 1
            print(f"Warning: Recent flights lookup failed: {e}")
            yield {"_warning": f"Recent flights lookup failed: {e}"}

        # Historical data with maximum window size (6 days for /history)
        window_days = 6
        current_end = end_dt
        windows_attempted = 0

        while current_end > start_dt:
            current_start = current_end - timedelta(days=window_days)
            if current_start < start_dt:
                current_start = start_dt

            params = {
                "start": current_start.strftime("%Y-%m-%dT00:00:00Z"),
                "end": current_end.strftime("%Y-%m-%dT00:00:00Z"),
            }

            try:
                # Keepalive before API call
                yield {"_keepalive": True}

                windows_attempted += 1
                data = self._make_request(f"/history/flights/{tail_number}", params)
                flights = data.get("flights", [])

                # Process entire window as a batch
                batch = []
                for flight in flights:
                    if flight.get("cancelled"):
                        continue
                    flight_id = flight.get("fa_flight_id")
                    if flight_id and flight_id not in seen_ids:
                        seen_ids.add(flight_id)
                        batch.append(self._fast_extract(flight))
                    elif not flight_id:
                        batch.append(self._fast_extract(flight))

                # Yield entire batch at once
                if batch:
                    yield {"_batch": batch}

            except Exception as e:
                api_errors += 1
                print(f"Warning: Failed window {current_start.date()} to {current_end.date()}: {e}")
                # Surface persistent errors to frontend
                if api_errors >= 3:
                    yield {"_warning": f"Multiple API errors ({api_errors}): {e}"}

            current_end = current_start

        # Yield summary so the caller knows what happened
        yield {"_summary": {
            "windows_attempted": windows_attempted,
            "api_errors": api_errors,
        }}

    def _fast_extract(self, flight: dict) -> dict:
        """ULTRA FAST extraction - absolute minimum processing."""
        # Get times
        dep = flight.get("actual_off") or flight.get("scheduled_off") or ""
        arr = flight.get("actual_on") or flight.get("scheduled_on") or ""

        # Duration and date
        duration = 0.0
        estimated = False
        date = ""

        if dep and arr:
            try:
                dep_dt = datetime.fromisoformat(dep.replace("Z", "+00:00"))
                arr_dt = datetime.fromisoformat(arr.replace("Z", "+00:00"))
                duration = round((arr_dt - dep_dt).total_seconds() / 3600, 1)
                date = dep_dt.strftime("%m/%d/%Y")
                estimated = not (flight.get("actual_off") and flight.get("actual_on"))
            except Exception:
                pass

        if duration == 0.0 and flight.get("filed_ete"):
            try:
                duration = round(flight["filed_ete"] / 3600, 1)
                estimated = True
            except Exception:
                pass

        # Airport codes - use directly from API
        orig = flight.get("origin", {}) or {}
        dest = flight.get("destination", {}) or {}
        from_code = orig.get("code_icao") or orig.get("code") or "-"
        to_code = dest.get("code_icao") or dest.get("code") or "-"

        # Aircraft type
        aircraft = flight.get("aircraft_type") or ""
        tail = flight.get("registration") or ""

        # Simple SEL detection
        is_sel = aircraft.upper() in ["TBM7", "TBM8", "TBM9", "TBM", "PC12", "C208", "C172", "C182", "C206", "PA28", "PA32", "SR22", "SR20"]

        # Return minimal data
        return {
            "date": date,
            "aircraft_model": aircraft,
            "aircraft_ident": tail.upper(),
            "route_from": from_code,
            "route_to": to_code,
            "total_duration": duration,
            "duration_estimated": estimated,
            "pic": duration,
            "sel": duration if is_sel else 0.0,
            "mel": 0.0 if is_sel else duration,
            "day": duration,  # Default all day
            "night": 0.0,
            "cross_country": duration if from_code != to_code else 0.0,
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
            "fa_flight_id": flight.get("fa_flight_id", ""),
            # Raw data for optional enrichment
            "_raw": {
                "dep_time": dep,
                "arr_time": arr,
                "orig_lat": orig.get("latitude"),
                "orig_lon": orig.get("longitude"),
                "dest_lat": dest.get("latitude"),
                "dest_lon": dest.get("longitude"),
            }
        }

    def enrich_batch(self, flights: list[dict]) -> list[dict]:
        """
        Enrich a batch of flights with airport lookups and calculations.
        This is done AFTER streaming, not during.
        """
        from services.airport_lookup import find_closest_airport
        from services.sun_calculator import estimate_night_hours, is_night_landing

        enriched = []
        for flight in flights:
            raw = flight.get("_raw", {})

            # Airport lookup if needed
            route_from = flight.get("route_from", "-")
            route_to = flight.get("route_to", "-")

            # Check if codes need resolution
            if route_from == "-" or len(route_from) != 4:
                lat = raw.get("orig_lat")
                lon = raw.get("orig_lon")
                if lat and lon:
                    airport = find_closest_airport(lat, lon, max_distance_nm=150, pure_distance=True, icao_only=True)
                    if airport:
                        route_from = f"{airport['icao']}*"

            if route_to == "-" or len(route_to) != 4:
                lat = raw.get("dest_lat")
                lon = raw.get("dest_lon")
                if lat and lon:
                    airport = find_closest_airport(lat, lon, max_distance_nm=150, pure_distance=True, icao_only=True)
                    if airport:
                        route_to = f"{airport['icao']}*"

            flight["route_from"] = route_from
            flight["route_to"] = route_to

            # Night hours calculation
            dep_time = raw.get("dep_time")
            arr_time = raw.get("arr_time")
            dest_lat = raw.get("dest_lat")
            dest_lon = raw.get("dest_lon")

            if all([dep_time, arr_time, dest_lat, dest_lon]):
                try:
                    dep_dt = datetime.fromisoformat(dep_time.replace("Z", "+00:00"))
                    arr_dt = datetime.fromisoformat(arr_time.replace("Z", "+00:00"))
                    night = estimate_night_hours(dep_dt, arr_dt, dest_lat, dest_lon)
                    flight["night"] = night
                    flight["day"] = round(max(0, flight["total_duration"] - night), 1)

                    if is_night_landing(arr_dt, dest_lat, dest_lon):
                        flight["landings_night"] = 1
                        flight["landings_day"] = 0
                except Exception:
                    pass

            # Remove raw data
            flight.pop("_raw", None)
            enriched.append(flight)

        return enriched
