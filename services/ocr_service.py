"""
OCR service for extracting flight data from logbook images.

Uses Google Gemini as primary method (multimodal LLM for best handwriting
recognition), with Google Vision API and Tesseract as fallbacks.
"""

from __future__ import annotations

import json
import os
from typing import Optional

try:
    import google.generativeai as genai
    from google.auth import default as google_auth_default
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    print("Warning: google-generativeai not installed. Install with: pip install google-generativeai")



class LogbookOCRService:
    """Service for extracting flight data from logbook images."""

    # Prompt for Gemini to extract structured flight data
    EXTRACTION_PROMPT = """You are analyzing a photo of a physical pilot logbook page.
Extract ALL flight entries visible in the image and return them as a JSON array.

Each flight entry should have these fields (use null if not readable):
- date: string in "M/D/YYYY" or "MM/DD/YYYY" format. The year may be written once at the top of the page - apply it to all entries.
- aircraft_model: aircraft type (e.g., "DA-20", "C-172", "PA-28", "TBM 700")
- aircraft_ident: tail number (e.g., "N636DC", "N95225")
- route_from: departure airport ICAO or FAA code (e.g., "BFI", "SEA", "PAE")
- route_to: destination airport ICAO or FAA code (e.g., "BFI", "SEA", "PAE")
- remarks: any remarks or endorsements text
- total_duration: total flight time in decimal hours (e.g., 1.4, 2.2)
- pic: pilot in command time in decimal hours
- sic: second in command time in decimal hours
- dual_recd: dual received time in decimal hours
- dual_given: dual given/flight instructor time in decimal hours
- solo: solo time in decimal hours
- cross_country: cross country time in decimal hours
- night: night time in decimal hours
- actual_inst: actual instrument time in decimal hours
- simulated_inst: simulated instrument (hood) time in decimal hours
- num_inst_app: number of instrument approaches (integer)
- landings_day: number of day landings (integer)
- landings_night: number of night landings (integer)

Important:
- You MUST output one entry for EVERY row of flight data visible in the logbook, even if you cannot read it well. Use empty strings for unreadable text fields and 0 for unreadable numbers. Never skip a row - the user needs a placeholder to fill in manually
- Airport codes MUST be valid real FAA or ICAO identifiers. If the handwriting is ambiguous, infer the most likely real airport code. For example, "BEE" is not a valid code but "BFI" (Boeing Field, Seattle) is. Common codes include: BFI, SEA, PAE, RNT, PWT, OLM, S43, S50, 0S9, HQM, BLI, etc.
- If a route shows multiple stops like "BFI-PAE-BFI", set route_from to the first, route_to to the last, and put the full route (e.g., "BFI-PAE-BFI") at the BEGINNING of the remarks field, followed by any other remarks
- Set numeric fields to 0 if the cell is empty (not null)
- Only extract ACTUAL FLIGHT entries. A real flight row has a date, aircraft, and airports. SKIP any summary/totals rows — these are rows that only contain numbers (column sums) without a date, aircraft type, or airport codes. They may be labeled "Totals", "Page Total", "Total this page", "Amounts forwarded", "Brought forward", etc., or they may just be an unlabeled row of numbers at the bottom of the page. These are NOT flights.
- The logbook is in standard ASA/Jeppesen format
- Include ALL columns you can read - do not skip any time categories

Return a JSON object with two fields:
1. "total_rows_visible": the total number of flight data rows you can see in the logbook (count every row that has ANY data written in it)
2. "entries": the JSON array of extracted flight entries

The length of "entries" MUST equal "total_rows_visible". If they don't match, you missed rows.

Example:
{"total_rows_visible": 1, "entries": [{"date": "5/9/2004", "aircraft_model": "DA-20", "aircraft_ident": "N636DC", "route_from": "BFI", "route_to": "BFI", "remarks": "Stalls, slow flight", "total_duration": 1.4, "pic": 0, "sic": 0, "dual_recd": 1.4, "dual_given": 0, "solo": 0, "cross_country": 0, "night": 0, "actual_inst": 0, "simulated_inst": 0, "num_inst_app": 0, "landings_day": 3, "landings_night": 0}]}"""

    def __init__(self):
        """Initialize OCR service."""
        self._gemini_initialized = False

    def _init_gemini(self):
        """Initialize Google Generative AI (Gemini)."""
        if self._gemini_initialized:
            return

        if not GEMINI_AVAILABLE:
            return

        try:
            # Use Application Default Credentials (service account)
            credentials, project_id = google_auth_default(
                scopes=['https://www.googleapis.com/auth/generative-language']
            )
            genai.configure(credentials=credentials)
            self._gemini_initialized = True
            print(f"Gemini initialized with project: {project_id}")

        except Exception as e:
            print(f"Error initializing Gemini: {e}")

    def extract_flights_with_gemini(self, image_path: str) -> list[dict]:
        """
        Extract flight entries from logbook image using Google Gemini.

        Gemini can see the image, understand the table layout, read handwriting,
        and return structured JSON directly - much better than traditional OCR.

        Args:
            image_path: Path to logbook image

        Returns:
            List of flight entry dicts, or empty list on failure
        """
        if not GEMINI_AVAILABLE:
            print("ERROR: google-generativeai not available")
            return [], 0, 0

        self._init_gemini()

        if not self._gemini_initialized:
            print("ERROR: Gemini not initialized")
            return [], 0, 0

        try:
            # Load image
            with open(image_path, 'rb') as f:
                image_bytes = f.read()

            print(f"Sending {len(image_bytes)} byte image to Gemini...")

            # Use inline image data (no File API needed)
            import base64
            image_b64 = base64.b64encode(image_bytes).decode('utf-8')

            image_part = {
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": image_b64
                }
            }

            # Use Gemini model
            model = genai.GenerativeModel("gemini-2.0-flash")
            response = model.generate_content(
                [self.EXTRACTION_PROMPT, image_part],
                generation_config=genai.GenerationConfig(
                    temperature=0.1,
                    max_output_tokens=8192,
                )
            )

            # Parse response
            response_text = response.text.strip()
            print(f"Gemini response length: {len(response_text)} chars")

            # Clean up response - remove markdown code blocks if present
            if response_text.startswith("```"):
                # Remove ```json and ``` markers
                lines = response_text.split('\n')
                lines = [l for l in lines if not l.strip().startswith('```')]
                response_text = '\n'.join(lines)

            # Parse JSON
            parsed = json.loads(response_text)

            # Handle both formats: object with total_rows_visible or plain list
            if isinstance(parsed, dict):
                expected_rows = parsed.get('total_rows_visible', 0)
                entries = parsed.get('entries', [])
                print(f"Gemini reports {expected_rows} rows visible, extracted {len(entries)} entries")

                if expected_rows > len(entries):
                    print(f"WARNING: Missing {expected_rows - len(entries)} rows! "
                          f"Expected {expected_rows}, got {len(entries)}")
            elif isinstance(parsed, list):
                entries = parsed
                expected_rows = len(entries)
            else:
                print(f"WARNING: Gemini returned unexpected type: {type(parsed)}")
                return [], 0, 0

            print(f"Gemini extracted {len(entries)} flight entries")

            # Normalize entries
            normalized = []
            for entry in entries:
                normalized.append(self._normalize_entry(entry))

            # Filter out summary/totals rows that Gemini missed
            filtered = [e for e in normalized if self._is_flight_entry(e)]
            if len(filtered) < len(normalized):
                print(f"Filtered out {len(normalized) - len(filtered)} summary/totals row(s)")

            return filtered, expected_rows, len(filtered)

        except json.JSONDecodeError as e:
            print(f"Error parsing Gemini JSON response: {e}")
            print(f"Response was: {response_text[:500]}")
            return [], 0, 0
        except Exception as e:
            print(f"Error with Gemini extraction: {e}")
            return [], 0, 0

    def _is_flight_entry(self, entry: dict) -> bool:
        """Return True if this looks like an actual flight, not a totals/summary row."""
        import re
        date_str = entry.get('date', '').strip()
        # Date must contain digits and a separator (/ or -) to be real
        has_date = bool(date_str) and bool(re.search(r'\d+[/\-]\d+', date_str))
        has_aircraft = bool(entry.get('aircraft_model', '').strip()) or bool(entry.get('aircraft_ident', '').strip())
        has_route = bool(entry.get('route_from', '').strip()) or bool(entry.get('route_to', '').strip())
        # Require at least 2 of 3 indicators to be a real flight
        score = sum([has_date, has_aircraft, has_route])
        return score >= 2

    def _normalize_entry(self, entry: dict) -> dict:
        """Normalize a flight entry to ensure all fields exist with proper types."""
        def to_float(val):
            if val is None:
                return 0.0
            try:
                return float(val)
            except (ValueError, TypeError):
                return 0.0

        def to_int(val):
            if val is None:
                return 0
            try:
                return int(val)
            except (ValueError, TypeError):
                return 0

        return {
            'date': str(entry.get('date', '') or ''),
            'aircraft_model': str(entry.get('aircraft_model', '') or ''),
            'aircraft_ident': str(entry.get('aircraft_ident', '') or ''),
            'route_from': str(entry.get('route_from', '') or ''),
            'route_to': str(entry.get('route_to', '') or ''),
            'remarks': str(entry.get('remarks', '') or ''),
            'total_duration': to_float(entry.get('total_duration')),
            'pic': to_float(entry.get('pic')),
            'sic': to_float(entry.get('sic')),
            'dual_recd': to_float(entry.get('dual_recd')),
            'dual_given': to_float(entry.get('dual_given')),
            'solo': to_float(entry.get('solo')),
            'cross_country': to_float(entry.get('cross_country')),
            'night': to_float(entry.get('night')),
            'actual_inst': to_float(entry.get('actual_inst')),
            'simulated_inst': to_float(entry.get('simulated_inst')),
            'num_inst_app': to_int(entry.get('num_inst_app')),
            'landings_day': to_int(entry.get('landings_day')),
            'landings_night': to_int(entry.get('landings_night')),
            'sel': to_float(entry.get('sel')),
            'mel': to_float(entry.get('mel')),
        }
