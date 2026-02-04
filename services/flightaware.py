"""
FlightAware AeroAPI integration for Pilot Logbook.

Fetches flight history by tail number and converts to logbook entries.
Uses /history/flights endpoint for historical data (up to years in the past).
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


class FlightAwareService:
    """Service for FlightAware AeroAPI integration."""

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

    def get_flight_track(self, fa_flight_id: str) -> Optional[list[dict]]:
        """
        Get the track/positions for a specific flight.

        Args:
            fa_flight_id: FlightAware flight ID

        Returns:
            List of position dictionaries with lat, lon, altitude, etc.
            Returns None if track not available.
        """
        # Try current flights endpoint first
        try:
            data = self._make_request(f"/flights/{fa_flight_id}/track")
            positions = data.get("positions", [])
            if positions:
                return positions
        except Exception as e:
            # If it fails due to being historical, try history endpoint
            if "10 days ago" in str(e) or "historical" in str(e).lower():
                pass  # Fall through to try historical endpoint
            else:
                print(f"Warning: Could not fetch track for {fa_flight_id}: {e}")
                return None

        # Try historical endpoint for older flights
        try:
            data = self._make_request(f"/history/flights/{fa_flight_id}/track")
            positions = data.get("positions", [])
            return positions if positions else None
        except Exception as e:
            print(f"Warning: Could not fetch historical track for {fa_flight_id}: {e}")
            return None

    def get_last_track_position(
        self, fa_flight_id: str
    ) -> Optional[tuple[float, float]]:
        """
        Get the last position from a flight's track (landing location).

        Args:
            fa_flight_id: FlightAware flight ID

        Returns:
            Tuple of (latitude, longitude) for the last track position,
            or None if track not available.
        """
        positions = self.get_flight_track(fa_flight_id)
        if not positions:
            return None

        # Get the last position (should be near landing)
        last_pos = positions[-1]
        lat = last_pos.get("latitude")
        lon = last_pos.get("longitude")

        if lat is not None and lon is not None:
            return (lat, lon)
        return None

    def get_flights_by_tail(
        self,
        tail_number: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        months_back: int = 12,
    ) -> list[dict]:
        """
        Get flight history for an aircraft by tail number.
        Uses /history/flights endpoint for historical data.

        Args:
            tail_number: Aircraft registration (e.g., "N790TB")
            start_date: Optional start date in YYYY-MM-DD format
            end_date: Optional end date in YYYY-MM-DD format
            months_back: How many months of history to fetch (default 12)

        Returns:
            List of flight dictionaries
        """
        # Clean up tail number
        tail_number = tail_number.upper().strip()
        if not tail_number.startswith("N"):
            tail_number = f"N{tail_number}"

        all_flights = []

        # Determine date range - use date only (no time component for clean math)
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        if end_date:
            end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            # End at yesterday to avoid "future date" errors
            end_dt = today - timedelta(days=1)

        if start_date:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            # Default to months_back months ago
            start_dt = end_dt - timedelta(days=months_back * 30)

        # First, try to get recent flights from /flights endpoint (last 10 days)
        try:
            recent_data = self._make_request(f"/flights/{tail_number}")
            recent_flights = recent_data.get("flights", [])
            all_flights.extend(recent_flights)
        except Exception:
            pass  # Continue with historical data even if recent fails

        # Now fetch historical data using /history/flights endpoint
        # API requires max 6-day windows (7 days is too strict with time components)
        window_days = 6
        current_end = end_dt

        while current_end > start_dt:
            current_start = current_end - timedelta(days=window_days)
            if current_start < start_dt:
                current_start = start_dt

            # Use consistent date format: YYYY-MM-DDT00:00:00Z
            params = {
                "start": current_start.strftime("%Y-%m-%dT00:00:00Z"),
                "end": current_end.strftime("%Y-%m-%dT00:00:00Z"),
            }

            try:
                data = self._make_request(f"/history/flights/{tail_number}", params)
                flights = data.get("flights", [])
                all_flights.extend(flights)
            except Exception as e:
                # Log but continue fetching other windows
                print(
                    f"Warning: Failed to fetch history for {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}: {e}"
                )

            # Move to the previous window (no gap, no overlap)
            current_end = current_start

        # Deduplicate flights by fa_flight_id
        seen_ids = set()
        unique_flights = []
        for flight in all_flights:
            flight_id = flight.get("fa_flight_id")
            if flight_id and flight_id not in seen_ids:
                seen_ids.add(flight_id)
                unique_flights.append(flight)
            elif not flight_id:
                unique_flights.append(flight)

        return unique_flights

    def get_flights_by_tail_streaming(
        self,
        tail_number: str,
        months_back: int = 12,
    ):
        """
        Generator that yields flights as they're fetched from FlightAware.
        Used for streaming results to the UI incrementally.

        Args:
            tail_number: Aircraft registration (e.g., "N790TB")
            months_back: How many months of history to fetch (default 12)

        Yields:
            Individual flight dictionaries as they're found
        """
        # Clean up tail number
        tail_number = tail_number.upper().strip()
        if not tail_number.startswith("N"):
            tail_number = f"N{tail_number}"

        seen_ids = set()

        # Determine date range
        today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        end_dt = today - timedelta(days=1)
        start_dt = end_dt - timedelta(days=months_back * 30)

        # First, try to get recent flights from /flights endpoint (last 10 days)
        try:
            recent_data = self._make_request(f"/flights/{tail_number}")
            recent_flights = recent_data.get("flights", [])
            for flight in recent_flights:
                flight_id = flight.get("fa_flight_id")
                if flight_id and flight_id not in seen_ids:
                    seen_ids.add(flight_id)
                    yield flight
                elif not flight_id:
                    yield flight
        except Exception:
            pass

        # Fetch historical data in 3-day windows (smaller for more frequent yields)
        window_days = 3
        current_end = end_dt

        while current_end > start_dt:
            current_start = current_end - timedelta(days=window_days)
            if current_start < start_dt:
                current_start = start_dt

            params = {
                "start": current_start.strftime("%Y-%m-%dT00:00:00Z"),
                "end": current_end.strftime("%Y-%m-%dT00:00:00Z"),
            }

            try:
                # Yield a keepalive signal before making API call
                yield {"_keepalive": True}

                data = self._make_request(f"/history/flights/{tail_number}", params)
                flights = data.get("flights", [])
                for flight in flights:
                    flight_id = flight.get("fa_flight_id")
                    if flight_id and flight_id not in seen_ids:
                        seen_ids.add(flight_id)
                        yield flight
                    elif not flight_id:
                        yield flight
            except Exception as e:
                print(
                    f"Warning: Failed to fetch history for {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}: {e}"
                )

            current_end = current_start

    def get_flights_incremental_streaming(
        self,
        tail_number: str,
        most_recent_flight_date: Optional[datetime] = None,
        max_lookback_months: int = 24,
    ):
        """
        Intelligent incremental import that fetches only NEW flights since the last import.

        For first import (no previous flights): Fetch up to max_lookback_months
        For subsequent imports: Fetch only flights since most_recent_flight_date

        Args:
            tail_number: Aircraft registration (e.g., "N790TB")
            most_recent_flight_date: Date of the most recent flight in logbook (None for first import)
            max_lookback_months: Maximum history to fetch on first import (default 24 months)

        Yields:
            Individual flight dictionaries as they're found
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
            # Incremental import: Start from day after the most recent flight
            start_dt = most_recent_flight_date + timedelta(days=1)
            print(f"Incremental import: Fetching flights since {start_dt.strftime('%Y-%m-%d')}")
        else:
            # First import: Fetch historical data (default 24 months)
            start_dt = end_dt - timedelta(days=max_lookback_months * 30)
            print(f"First import: Fetching up to {max_lookback_months} months of history")

        # If start date is after end date, there's nothing to fetch
        if start_dt > end_dt:
            print("No new flights to fetch (logbook is up to date)")
            return

        # First, try to get recent flights from /flights endpoint (last 10 days)
        try:
            recent_data = self._make_request(f"/flights/{tail_number}")
            recent_flights = recent_data.get("flights", [])
            for flight in recent_flights:
                flight_id = flight.get("fa_flight_id")
                if flight_id and flight_id not in seen_ids:
                    seen_ids.add(flight_id)
                    yield flight
                elif not flight_id:
                    yield flight
        except Exception:
            pass

        # Fetch historical data in 3-day windows (smaller for more frequent yields)
        window_days = 3
        current_end = end_dt

        while current_end > start_dt:
            current_start = current_end - timedelta(days=window_days)
            if current_start < start_dt:
                current_start = start_dt

            params = {
                "start": current_start.strftime("%Y-%m-%dT00:00:00Z"),
                "end": current_end.strftime("%Y-%m-%dT00:00:00Z"),
            }

            try:
                # Yield a keepalive signal before making API call
                yield {"_keepalive": True}

                data = self._make_request(f"/history/flights/{tail_number}", params)
                flights = data.get("flights", [])
                for flight in flights:
                    flight_id = flight.get("fa_flight_id")
                    if flight_id and flight_id not in seen_ids:
                        seen_ids.add(flight_id)
                        yield flight
                    elif not flight_id:
                        yield flight
            except Exception as e:
                print(
                    f"Warning: Failed to fetch history for {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}: {e}"
                )

            current_end = current_start

    def flight_to_logbook_entry(self, flight: dict) -> dict:
        """
        Convert a FlightAware flight to a logbook entry format.

        Args:
            flight: FlightAware flight dictionary

        Returns:
            Dictionary suitable for creating a LogbookEntry
        """
        from services.airport_lookup import (
            estimate_flight_duration,
            find_closest_airport,
            get_airport_coordinates,
        )
        from services.sun_calculator import estimate_night_hours, is_night_landing

        # Parse times
        departure_time = flight.get("actual_off") or flight.get("scheduled_off") or ""
        arrival_time = flight.get("actual_on") or flight.get("scheduled_on") or ""

        # Calculate duration in hours
        duration = 0.0
        duration_estimated = False
        dep_dt = None
        arr_dt = None

        if departure_time and arrival_time:
            try:
                dep_dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
                arr_dt = datetime.fromisoformat(arrival_time.replace("Z", "+00:00"))
                duration = (arr_dt - dep_dt).total_seconds() / 3600
                duration = round(duration, 1)

                # If using scheduled times instead of actual, mark as estimated
                if not flight.get("actual_off") or not flight.get("actual_on"):
                    duration_estimated = True
            except Exception:
                pass

        # If still no duration, try filed_ete (Estimated Time Enroute in seconds)
        if duration == 0.0 and flight.get("filed_ete"):
            try:
                duration = round(flight["filed_ete"] / 3600, 1)
                duration_estimated = True
            except Exception:
                pass

        # Get origin/destination from FlightAware
        origin = flight.get("origin", {}) or {}
        destination = flight.get("destination", {}) or {}

        def resolve_airport(location: dict) -> tuple[str, bool, float, float]:
            """
            Resolve airport from FlightAware location data.
            Returns (airport_code, is_estimated, lat, lon).

            Logic:
            - If valid ICAO code (4 letters), use it
            - If lat/long given (directly or in 'code' field), find closest ICAO airport with *
            - Otherwise return "-"
            """
            icao = location.get("code_icao") or ""
            lat = location.get("latitude")
            lon = location.get("longitude")

            # Check for valid ICAO code (4 letters, all alphabetic)
            if icao and len(icao) == 4 and icao.isalpha():
                # Get coordinates for this airport
                coords = get_airport_coordinates(icao)
                if coords:
                    return (icao, False, coords[0], coords[1])
                return (icao, False, lat or 0, lon or 0)

            # If no direct lat/lon, try to parse from 'code' field
            # FlightAware sometimes returns: "L 22.20140 113.60428"
            if lat is None or lon is None:
                code = location.get("code") or ""
                if code.startswith("L "):
                    try:
                        parts = code.split()
                        if len(parts) == 3:
                            lat = float(parts[1])
                            lon = float(parts[2])
                    except (ValueError, IndexError):
                        pass

            # If lat/long available, find closest airport with valid ICAO code
            if lat is not None and lon is not None:
                airport = find_closest_airport(
                    lat, lon, max_distance_nm=150, pure_distance=True, icao_only=True
                )
                if airport:
                    return (f"{airport['icao']}*", True, airport["lat"], airport["lon"])

            return ("-", False, 0, 0)

        route_from, from_estimated, _, _ = resolve_airport(origin)
        route_to, to_estimated, dest_lat, dest_lon = resolve_airport(destination)

        # If still no duration, try to estimate based on distance between airports
        if duration == 0.0:
            # Extract clean ICAO codes (remove asterisks)
            from_icao = route_from.rstrip("*") if route_from != "-" else None
            to_icao = route_to.rstrip("*") if route_to != "-" else None

            if from_icao and to_icao:
                # Use distance-based estimation (assume ~250 kts average speed for TBM)
                estimated_duration = estimate_flight_duration(
                    from_icao, to_icao, cruise_speed_kts=250
                )
                if estimated_duration:
                    duration = round(estimated_duration, 1)
                    duration_estimated = True

        # Get date from departure time
        flight_date = ""
        if departure_time:
            try:
                if dep_dt is None:
                    dep_dt = datetime.fromisoformat(
                        departure_time.replace("Z", "+00:00")
                    )
                flight_date = dep_dt.strftime("%m/%d/%Y")
            except Exception:
                pass

        # Get aircraft info
        aircraft = flight.get("aircraft_type") or ""
        tail_number = flight.get("registration") or ""

        # Determine if single engine land (SEL) - TBM7 is single engine turboprop
        is_sel = aircraft.upper() in [
            "TBM7",
            "TBM8",
            "TBM9",
            "TBM",
            "PC12",
            "C208",
            "C172",
            "C182",
            "C206",
            "PA28",
            "PA32",
            "SR22",
            "SR20",
        ]
        sel_time = duration if is_sel else 0.0
        mel_time = 0.0 if is_sel else duration  # If not SEL, assume MEL

        # Calculate night hours and determine landing type based on sunset
        night_hours = 0.0
        landings_day = 1
        landings_night = 0

        if dep_dt and arr_dt and dest_lat != 0 and dest_lon != 0:
            # Calculate night hours based on sunset at destination
            night_hours = estimate_night_hours(dep_dt, arr_dt, dest_lat, dest_lon)

            # Determine if landing was at night
            if is_night_landing(arr_dt, dest_lat, dest_lon):
                landings_night = 1
                landings_day = 0

        # Day hours is total minus night
        day_hours = round(max(0, duration - night_hours), 1)

        # Remarks will only contain approach info (set by UI when user selects approach)
        remarks = ""

        return {
            "date": flight_date,
            "aircraft_model": aircraft,
            "aircraft_ident": tail_number.upper(),
            "route_from": route_from,
            "route_to": route_to,
            "total_duration": duration,
            "duration_estimated": duration_estimated,
            "pic": duration,  # Assume PIC time = total time
            "day": day_hours,
            "sel": sel_time,  # Single engine land time
            "mel": mel_time,  # Multi engine land time
            "night": night_hours,
            "cross_country": duration if route_from != route_to else 0.0,
            "actual_inst": 0.0,
            "simulated_inst": 0.0,
            "num_inst_app": 0,
            "landings_day": landings_day,
            "landings_night": landings_night,
            "sic": 0.0,
            "dual_recd": 0.0,
            "dual_given": 0.0,
            "solo": 0.0,
            "remarks": remarks,
            # Store FlightAware ID to prevent duplicates
            "fa_flight_id": flight.get("fa_flight_id", ""),
            # Store destination coordinates for approach lookup
            "dest_lat": dest_lat,
            "dest_lon": dest_lon,
        }

    def get_flights_as_logbook_entries(
        self,
        tail_number: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        months_back: int = 12,
    ) -> list[dict]:
        """
        Get flights and convert them to logbook entry format.

        Args:
            tail_number: Aircraft registration
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            months_back: How many months of history to fetch (default 12)

        Returns:
            List of logbook entry dictionaries
        """
        flights = self.get_flights_by_tail(
            tail_number, start_date, end_date, months_back
        )

        entries = []
        for flight in flights:
            # Include flights that have either actual or scheduled times
            # Skip cancelled flights
            if flight.get("cancelled"):
                continue

            has_times = (
                (flight.get("actual_off") and flight.get("actual_on"))
                or (flight.get("scheduled_off") and flight.get("scheduled_on"))
                or flight.get("filed_ete")
            )

            if has_times:
                entry = self.flight_to_logbook_entry(flight)
                if entry["date"] and entry["route_from"]:  # Valid entry
                    entries.append(entry)

        # Sort by date descending (newest first)
        entries.sort(key=lambda x: x["date"], reverse=True)

        return entries

    def get_flights_as_logbook_entries_streaming(
        self,
        tail_number: str,
        most_recent_flight_date: Optional[datetime] = None,
        max_lookback_months: int = 24,
    ):
        """
        Generator that yields logbook entries as they're fetched.
        Uses intelligent incremental import.

        Args:
            tail_number: Aircraft registration
            most_recent_flight_date: Date of most recent flight in logbook (None for first import)
            max_lookback_months: Maximum history to fetch on first import (default 24 months)

        Yields:
            Logbook entry dictionaries as they're processed
        """
        for flight in self.get_flights_incremental_streaming(
            tail_number, most_recent_flight_date, max_lookback_months
        ):
            # Skip cancelled flights
            if flight.get("cancelled"):
                continue

            has_times = (
                (flight.get("actual_off") and flight.get("actual_on"))
                or (flight.get("scheduled_off") and flight.get("scheduled_on"))
                or flight.get("filed_ete")
            )

            if has_times:
                entry = self.flight_to_logbook_entry(flight)
                if entry["date"] and entry["route_from"]:
                    yield entry
