"""
OCR service for extracting flight data from logbook images.

Uses Google Gemini as primary method (multimodal LLM for best handwriting
recognition), with Google Vision API and Tesseract as fallbacks.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
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
- date: MUST always be in "MM/DD/YYYY" format with leading zeros and a 4-digit year. Examples: "05/09/2004", "12/03/2023", "01/15/2010". In handwritten logbooks, the year is often written only once at the top of the page or column, or only on the first entry — you MUST apply that year to every entry on the page. If the year is not visible anywhere on this page, infer it from context: the dates should be sequential and realistic for a pilot logbook (typically 2000-2025). If a date spans multiple days (e.g., "3/26-28"), use the first date. Every date you output MUST have a 4-digit year — never output just "03/10", always "03/10/2004".
- aircraft_model: FAA aircraft type designator (e.g., "DA20", "C172", "PA28", "TBM7", "C206", "SR22", "BE36"). Use standard FAA designators WITHOUT hyphens. Be careful with OCR-ambiguous characters: Y vs 7, T vs 7, O vs 0, I vs 1, S vs 5. For example, "C2067" is not valid — it should be "C206T" or another real designator. If the same aircraft type appears on multiple rows, ensure consistency.
- aircraft_ident: tail number (e.g., "N636DC", "N95225"). If the same tail number appears on multiple rows, ensure consistency — handwriting OCR often confuses Y/7, T/7, O/0, I/1, S/5, B/8. Pick the most likely real tail number.
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
{"total_rows_visible": 1, "entries": [{"date": "05/09/2004", "aircraft_model": "DA20", "aircraft_ident": "N636DC", "route_from": "BFI", "route_to": "BFI", "remarks": "Stalls, slow flight", "total_duration": 1.4, "pic": 0, "sic": 0, "dual_recd": 1.4, "dual_given": 0, "solo": 0, "cross_country": 0, "night": 0, "actual_inst": 0, "simulated_inst": 0, "num_inst_app": 0, "landings_day": 3, "landings_night": 0}]}"""

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

    def extract_flights_with_gemini(self, image_path: str,
                                     known_idents: set[str] | None = None,
                                     known_models: set[str] | None = None) -> list[dict]:
        """
        Extract flight entries from logbook image using Google Gemini.

        Gemini can see the image, understand the table layout, read handwriting,
        and return structured JSON directly - much better than traditional OCR.

        Args:
            image_path: Path to logbook image
            known_idents: Known aircraft tail numbers from existing entries (for correction)
            known_models: Known aircraft types from existing entries (for correction)

        Returns:
            Tuple of (entries list, expected_rows, actual_rows)
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

            # Fix dates: normalize format, fix garbled years, propagate missing years
            filtered = self._normalize_dates(filtered)

            # Fix aircraft identifiers using frequency analysis + known idents
            filtered = self._fix_aircraft_idents(filtered, known_idents)

            # Fix aircraft types against known FAA designators
            filtered = self._fix_aircraft_models(filtered, known_models)

            return filtered, expected_rows, len(filtered)

        except json.JSONDecodeError as e:
            print(f"Error parsing Gemini JSON response: {e}")
            print(f"Response was: {response_text[:500]}")
            return [], 0, 0
        except Exception as e:
            print(f"Error with Gemini extraction: {e}")
            return [], 0, 0

    def _normalize_dates(self, entries: list[dict]) -> list[dict]:
        """Fix dates across all entries: normalize format, fix garbled years, propagate missing years."""
        # First pass: normalize each date individually, preserve date ranges in remarks
        for entry in entries:
            raw_date = entry.get('date', '')
            normalized, date_range = self._normalize_date(raw_date)
            entry['date'] = normalized
            if date_range:
                remarks = entry.get('remarks', '').strip()
                entry['remarks'] = f"{date_range} {remarks}".strip() if remarks else date_range
                print(f"Date range '{raw_date}' → date='{normalized}', added range to remarks")

        # Second pass: propagate years to entries missing them
        # Find the most common year from entries that have one
        years = []
        for entry in entries:
            m = re.match(r'(\d{1,2})/(\d{1,2})/(\d{4})$', entry['date'])
            if m:
                years.append(m.group(3))

        default_year = max(set(years), key=years.count) if years else None

        for entry in entries:
            date = entry['date']
            # If date is just MM/DD with no year, add the default year
            m = re.match(r'^(\d{1,2})/(\d{1,2})$', date)
            if m and default_year:
                entry['date'] = f"{int(m.group(1)):02d}/{int(m.group(2)):02d}/{default_year}"
                print(f"Date fix: '{date}' → '{entry['date']}' (added year)")

        return entries

    def _normalize_date(self, date_str: str) -> tuple[str, str | None]:
        """Normalize a single date string to MM/DD/YYYY format with leading zeros.

        Returns:
            (normalized_date, date_range_or_None) — date_range is the original
            range string (e.g. "3/26-3/28/2023") if the date was a range, else None.
        """
        date_str = date_str.strip()
        if not date_str:
            return '', None

        date_range = None

        # Handle date ranges like "3/26-3/28/2023" — use first date, save range
        range_match = re.match(r'^(\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})/(\d{1,2})/(\d{1,4})$', date_str)
        if range_match:
            date_range = date_str
            month, day = range_match.group(1), range_match.group(2)
            year = range_match.group(5)
            date_str = f"{month}/{day}/{year}"
        else:
            # "3/26-28/2023" format (same month)
            range_match2 = re.match(r'^(\d{1,2})/(\d{1,2})\s*-\s*(\d{1,2})/(\d{1,4})$', date_str)
            if range_match2:
                date_range = date_str
                month, day = range_match2.group(1), range_match2.group(2)
                year = range_match2.group(4)
                date_str = f"{month}/{day}/{year}"

        # Now parse M/D/YYYY or M/D
        m = re.match(r'^(\d{1,2})/(\d{1,2})(?:/(\d{1,4}))?$', date_str)
        if not m:
            return date_str, date_range  # Can't parse, return as-is

        month, day, year = int(m.group(1)), int(m.group(2)), m.group(3)

        if year:
            year = self._fix_year(year)
            return f"{month:02d}/{day:02d}/{year}", date_range
        else:
            # No year — return MM/DD, will be fixed in second pass
            return f"{month:02d}/{day:02d}", date_range

    def _fix_year(self, year_str: str) -> str:
        """Fix garbled year strings to valid 4-digit years."""
        year_str = year_str.strip()
        n = int(year_str)

        if 1950 <= n <= 2099:
            return str(n)

        # 1-2 digit: assume 2000s (e.g., "4" → "2004", "23" → "2023")
        if n <= 99:
            return str(2000 + n) if n <= 50 else str(1900 + n)

        # 3-digit garbled year: e.g., "206" → "2006", "202" → "2020"?
        # Most likely a dropped digit from a 200x year
        s = year_str
        if len(s) == 3:
            # Try inserting a '0' at each position to make a valid 4-digit year
            for i in range(len(s) + 1):
                candidate = s[:i] + '0' + s[i:]
                cn = int(candidate)
                if 1990 <= cn <= 2099:
                    print(f"Year fix: '{year_str}' → '{candidate}'")
                    return candidate
            # Fallback: prepend '2' if starts with '0'
            if s.startswith('0'):
                return '2' + s

        return year_str  # Can't fix, return as-is

    def _is_flight_entry(self, entry: dict) -> bool:
        """Return True if this looks like an actual flight, not a totals/summary row."""
        date_str = entry.get('date', '').strip()
        # Date must contain digits and a separator (/ or -) to be real
        has_date = bool(date_str) and bool(re.search(r'\d+[/\-]\d+', date_str))
        has_aircraft = bool(entry.get('aircraft_model', '').strip()) or bool(entry.get('aircraft_ident', '').strip())
        has_route = bool(entry.get('route_from', '').strip()) or bool(entry.get('route_to', '').strip())
        # Require at least 2 of 3 indicators to be a real flight
        score = sum([has_date, has_aircraft, has_route])
        return score >= 2

    # Common OCR character confusions (bidirectional)
    OCR_CONFUSIONS = {
        'Y': '7', '7': 'Y',
        'T': '7',
        'O': '0', '0': 'O',
        'I': '1', '1': 'I',
        'S': '5', '5': 'S',
        'B': '8', '8': 'B',
        'G': '6', '6': 'G',
        'Z': '2', '2': 'Z',
        'D': '0',
    }

    # Common FAA aircraft type designators
    KNOWN_AIRCRAFT_TYPES = {
        # Cessna
        'C150', 'C152', 'C170', 'C172', 'C175', 'C177', 'C180', 'C182',
        'C185', 'C190', 'C195', 'C206', 'C207', 'C208', 'C210', 'C310',
        'C320', 'C335', 'C337', 'C340', 'C402', 'C404', 'C414', 'C421',
        'C425', 'C441', 'C500', 'C510', 'C525', 'C550', 'C560',
        'C206T',  # Turbo 206
        # Piper
        'PA11', 'PA12', 'PA18', 'PA20', 'PA22', 'PA23', 'PA24', 'PA28',
        'PA30', 'PA31', 'PA32', 'PA34', 'PA38', 'PA44', 'PA46',
        'PA46T',  # Malibu Meridian
        # Beechcraft
        'BE33', 'BE35', 'BE36', 'BE55', 'BE58', 'BE60', 'BE76', 'BE95',
        'BE99', 'BE9L', 'B200', 'B300', 'B350',
        'BE36', 'BE58',
        # Mooney
        'M20', 'M20T', 'M20J', 'M20K', 'M20R', 'M20S',
        # Diamond
        'DA20', 'DA40', 'DA42', 'DA62',
        # Cirrus
        'SR20', 'SR22', 'SF50',
        # SOCATA / Daher / TBM
        'TBM7', 'TBM8', 'TBM9', 'TB9', 'TB10', 'TB20', 'TB21',
        # Grumman / American General
        'AA1', 'AA5', 'GA7',
        # Maule
        'M4', 'M5', 'M6', 'M7',
        # Vans RV
        'RV4', 'RV6', 'RV7', 'RV8', 'RV9', 'RV10', 'RV12', 'RV14',
        # Pilatus
        'PC12', 'PC6', 'PC24',
        # Extra / Aerobatic
        'E300', 'E330', 'E530',
        # Boeing / Airbus (airline types)
        'B737', 'B738', 'B739', 'B752', 'B753', 'B763', 'B772', 'B77W',
        'B788', 'B789', 'A319', 'A320', 'A321', 'A332', 'A333', 'A339',
        'A346', 'A359', 'A388',
        # Embraer
        'E170', 'E175', 'E190', 'E195', 'E75L', 'E75S',
        # Bombardier / CRJ
        'CRJ2', 'CRJ7', 'CRJ9', 'CL30', 'CL35', 'CL60', 'GL5T', 'GLEX',
        # De Havilland / Viking
        'DHC2', 'DHC3', 'DHC6',
        # Robinson Helicopters
        'R22', 'R44', 'R66',
        # Bell Helicopters
        'B206', 'B407', 'B412',
        # Eurocopter / Airbus Helicopters
        'AS50', 'EC30', 'EC35', 'EC45',
    }

    def _fix_aircraft_idents(self, entries: list[dict], known_idents: set[str] | None = None) -> list[dict]:
        """Fix aircraft identifiers using frequency analysis and OCR character correction.

        If a tail number appears rarely but is 1 character off from a frequent one,
        correct it to the frequent version (e.g., N61637 → N6163Y).
        Also uses known_idents from existing database entries.
        """
        # Count ident frequencies across extracted entries
        ident_counts = Counter(e['aircraft_ident'] for e in entries if e.get('aircraft_ident'))

        # Merge with known idents (treat them as high-frequency)
        if known_idents:
            for ident in known_idents:
                ident_counts[ident] = ident_counts.get(ident, 0) + 10  # Boost known idents

        # Build correction map for rare idents
        corrections = {}
        for ident, count in list(ident_counts.items()):
            if count > 2:
                continue  # Likely correct already
            # Check if there's a frequent ident that's 1 OCR-char away
            best_match = self._find_ocr_match(ident, ident_counts, min_freq=2)
            if best_match:
                corrections[ident] = best_match

        # Apply corrections
        for entry in entries:
            ident = entry.get('aircraft_ident', '')
            if ident in corrections:
                print(f"Ident fix: '{ident}' → '{corrections[ident]}'")
                entry['aircraft_ident'] = corrections[ident]

        return entries

    def _find_ocr_match(self, value: str, candidates: Counter, min_freq: int = 2) -> str | None:
        """Find a frequently-occurring candidate that differs by 1 OCR-confusable character."""
        if not value:
            return None
        for candidate, freq in candidates.items():
            if freq < min_freq or candidate == value:
                continue
            if len(candidate) != len(value):
                continue
            # Count character differences
            diffs = []
            for i, (a, b) in enumerate(zip(value.upper(), candidate.upper())):
                if a != b:
                    diffs.append((i, a, b))
            if len(diffs) != 1:
                continue
            # Check if the single diff is an OCR confusion
            _, char_a, char_b = diffs[0]
            if self.OCR_CONFUSIONS.get(char_a) == char_b or self.OCR_CONFUSIONS.get(char_b) == char_a:
                return candidate
        return None

    def _fix_aircraft_models(self, entries: list[dict], known_models: set[str] | None = None) -> list[dict]:
        """Fix aircraft type designators using known FAA types and OCR correction.

        Validates against known FAA type designators. If a model isn't recognized,
        tries OCR character substitutions to find a valid match.
        Also uses frequency analysis within the batch.
        """
        valid_types = set(self.KNOWN_AIRCRAFT_TYPES)
        if known_models:
            valid_types.update(known_models)

        # Normalize: strip hyphens/spaces for comparison
        def normalize_model(m):
            return re.sub(r'[-\s]', '', m).upper()

        # Build a lookup of normalized known types
        normalized_known = {}
        for t in valid_types:
            normalized_known[normalize_model(t)] = t

        # Count model frequencies across entries
        model_counts = Counter(normalize_model(e['aircraft_model'])
                               for e in entries if e.get('aircraft_model'))

        for entry in entries:
            raw = entry.get('aircraft_model', '').strip()
            if not raw:
                continue
            normed = normalize_model(raw)

            # Already a known type
            if normed in normalized_known:
                entry['aircraft_model'] = normalized_known[normed]
                continue

            # Try OCR substitutions on each character
            fixed = self._try_ocr_fix_against_set(normed, normalized_known)
            if fixed:
                print(f"Model fix: '{raw}' → '{fixed}'")
                entry['aircraft_model'] = fixed
                continue

            # Try frequency-based correction within batch
            freq_match = self._find_ocr_match(normed, model_counts, min_freq=2)
            if freq_match and freq_match in normalized_known:
                print(f"Model fix (freq): '{raw}' → '{normalized_known[freq_match]}'")
                entry['aircraft_model'] = normalized_known[freq_match]

        return entries

    def _try_ocr_fix_against_set(self, value: str, known_set: dict) -> str | None:
        """Try single-character OCR substitutions to match a known value."""
        for i, char in enumerate(value):
            # Try direct confusion mapping
            alt = self.OCR_CONFUSIONS.get(char)
            if alt:
                candidate = value[:i] + alt + value[i+1:]
                if candidate in known_set:
                    return known_set[candidate]
            # Also try reverse: what if this char is the correct one
            # and another mapping would work
            for orig, replacement in self.OCR_CONFUSIONS.items():
                if replacement == char:
                    candidate = value[:i] + orig + value[i+1:]
                    if candidate in known_set:
                        return known_set[candidate]
        return None

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
