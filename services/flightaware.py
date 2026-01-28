"""
FlightAware AeroAPI integration for Pilot Logbook.

Fetches flight history by tail number and converts to logbook entries.
Uses /history/flights endpoint for historical data (up to years in the past).
"""

from datetime import datetime, timedelta
from typing import Optional

import requests

from config import Config


class FlightAwareService:
    """Service for FlightAware AeroAPI integration."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or Config.FLIGHTAWARE_API_KEY
        self.base_url = Config.FLIGHTAWARE_API_URL

    def _make_request(self, endpoint: str, params: Optional[dict] = None) -> dict:
        """Make authenticated request to FlightAware API."""
        if not self.api_key:
            raise ValueError("FlightAware API key not configured. Set FLIGHTAWARE_API_KEY in .env")

        headers = {
            "x-apikey": self.api_key,
            "Accept": "application/json",
        }

        url = f"{self.base_url}{endpoint}"
        response = requests.get(url, headers=headers, params=params, timeout=30)

        if response.status_code == 401:
            raise ValueError("Invalid FlightAware API key")
        elif response.status_code == 404:
            return {"flights": [], "positions": []}
        elif response.status_code != 200:
            raise Exception(f"FlightAware API error: {response.status_code} - {response.text}")

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

    def get_last_track_position(self, fa_flight_id: str) -> Optional[tuple[float, float]]:
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
                print(f"Warning: Failed to fetch history for {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}: {e}")

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

        # Fetch historical data in 6-day windows
        window_days = 6
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
                print(f"Warning: Failed to fetch history for {current_start.strftime('%Y-%m-%d')} to {current_end.strftime('%Y-%m-%d')}: {e}")

            current_end = current_start

    def flight_to_logbook_entry(self, flight: dict) -> dict:
        """
        Convert a FlightAware flight to a logbook entry format.

        Args:
            flight: FlightAware flight dictionary

        Returns:
            Dictionary suitable for creating a LogbookEntry
        """
        from services.airport_lookup import find_closest_airport, estimate_flight_duration

        # Parse times
        departure_time = flight.get("actual_off") or flight.get("scheduled_off") or ""
        arrival_time = flight.get("actual_on") or flight.get("scheduled_on") or ""

        # Calculate duration in hours
        duration = 0.0
        duration_estimated = False

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

        def resolve_airport(location: dict) -> tuple[str, bool]:
            """
            Resolve airport from FlightAware location data.
            Returns (airport_code, is_estimated).

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
                return (icao, False)

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
                airport = find_closest_airport(lat, lon, max_distance_nm=150, pure_distance=True, icao_only=True)
                if airport:
                    return (f"{airport['icao']}*", True)

            return ("-", False)

        route_from, from_estimated = resolve_airport(origin)
        route_to, to_estimated = resolve_airport(destination)

        # If still no duration, try to estimate based on distance between airports
        if duration == 0.0:
            # Extract clean ICAO codes (remove asterisks)
            from_icao = route_from.rstrip('*') if route_from != '-' else None
            to_icao = route_to.rstrip('*') if route_to != '-' else None

            if from_icao and to_icao:
                # Use distance-based estimation (assume ~250 kts average speed for TBM)
                estimated_duration = estimate_flight_duration(from_icao, to_icao, cruise_speed_kts=250)
                if estimated_duration:
                    duration = round(estimated_duration, 1)
                    duration_estimated = True

        # Get date from departure time
        flight_date = ""
        if departure_time:
            try:
                dep_dt = datetime.fromisoformat(departure_time.replace("Z", "+00:00"))
                flight_date = dep_dt.strftime("%m/%d/%Y")
            except Exception:
                pass

        # Get aircraft info
        aircraft = flight.get("aircraft_type") or ""
        tail_number = flight.get("registration") or ""

        # Determine if single engine land (SEL) - TBM7 is single engine turboprop
        is_sel = aircraft.upper() in ["TBM7", "TBM8", "TBM9", "TBM", "PC12", "C208", "C172", "C182", "C206", "PA28", "PA32", "SR22", "SR20"]
        sel_time = duration if is_sel else 0.0
        mel_time = 0.0 if is_sel else duration  # If not SEL, assume MEL

        # Build remarks with flight details
        remarks_parts = []
        if flight.get("ident"):
            remarks_parts.append(f"Flight: {flight['ident']}")
        if flight.get("route"):
            remarks_parts.append(f"Route: {flight['route']}")

        # Add notes about estimated values
        notes = []
        if from_estimated:
            notes.append("origin estimated")
        if to_estimated:
            notes.append("dest estimated")
        if duration_estimated:
            notes.append("duration estimated")
        if notes:
            remarks_parts.append(f"Note: {', '.join(notes)}")

        return {
            "date": flight_date,
            "aircraft_model": aircraft,
            "aircraft_ident": tail_number.upper(),
            "route_from": route_from,
            "route_to": route_to,
            "total_duration": duration,
            "duration_estimated": duration_estimated,
            "pic": duration,  # Assume PIC time = total time
            "day": duration,  # Assume day flight (can be adjusted)
            "sel": sel_time,  # Single engine land time
            "mel": mel_time,  # Multi engine land time
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
            "remarks": "; ".join(remarks_parts),
            # Store FlightAware ID to prevent duplicates
            "fa_flight_id": flight.get("fa_flight_id", ""),
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
        flights = self.get_flights_by_tail(tail_number, start_date, end_date, months_back)

        entries = []
        for flight in flights:
            # Include flights that have either actual or scheduled times
            # Skip cancelled flights
            if flight.get("cancelled"):
                continue

            has_times = (
                (flight.get("actual_off") and flight.get("actual_on")) or
                (flight.get("scheduled_off") and flight.get("scheduled_on")) or
                flight.get("filed_ete")
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
        months_back: int = 12,
    ):
        """
        Generator that yields logbook entries as they're fetched.
        Used for streaming results to the UI incrementally.

        Args:
            tail_number: Aircraft registration
            months_back: How many months of history to fetch

        Yields:
            Logbook entry dictionaries as they're processed
        """
        for flight in self.get_flights_by_tail_streaming(tail_number, months_back):
            # Skip cancelled flights
            if flight.get("cancelled"):
                continue

            has_times = (
                (flight.get("actual_off") and flight.get("actual_on")) or
                (flight.get("scheduled_off") and flight.get("scheduled_on")) or
                flight.get("filed_ete")
            )

            if has_times:
                entry = self.flight_to_logbook_entry(flight)
                if entry["date"] and entry["route_from"]:
                    yield entry
