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
- If a route shows multiple stops like "BFI-PAE-BFI", set route_from to the first and route_to to the last
- Set numeric fields to 0 if the cell is empty (not null)
- The logbook is in standard ASA/Jeppesen format
- Include ALL columns you can read - do not skip any time categories

Return ONLY valid JSON array, no other text. Example:
[{"date": "5/9/2004", "aircraft_model": "DA-20", "aircraft_ident": "N636DC", "route_from": "BFI", "route_to": "BFI", "remarks": "Stalls, slow flight", "total_duration": 1.4, "pic": 0, "sic": 0, "dual_recd": 1.4, "dual_given": 0, "solo": 0, "cross_country": 0, "night": 0, "actual_inst": 0, "simulated_inst": 0, "num_inst_app": 0, "landings_day": 3, "landings_night": 0}]"""

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
            print("ERROR: Vertex AI not available")
            return []

        self._init_gemini()

        if not self._gemini_initialized:
            print("ERROR: Gemini not initialized")
            return []

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
            entries = json.loads(response_text)

            if not isinstance(entries, list):
                print(f"WARNING: Gemini returned non-list: {type(entries)}")
                return []

            print(f"Gemini extracted {len(entries)} flight entries")

            # Normalize entries
            normalized = []
            for entry in entries:
                normalized.append(self._normalize_entry(entry))

            return normalized

        except json.JSONDecodeError as e:
            print(f"Error parsing Gemini JSON response: {e}")
            print(f"Response was: {response_text[:500]}")
            return []
        except Exception as e:
            print(f"Error with Gemini extraction: {e}")
            return []

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
