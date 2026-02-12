"""
Parser for pilot logbook pages (ASA/Jeppesen format).

Extracts structured flight data from OCR text of physical logbook pages.
"""

import re
from datetime import datetime
from typing import Optional, List, Dict, Tuple


class LogbookParser:
    """Parser for ASA/Jeppesen format pilot logbooks."""

    # Standard column headers (case-insensitive fuzzy matching)
    COLUMN_PATTERNS = {
        'date': r'date',
        'aircraft_model': r'(aircraft\s+make|make\s*[/&]\s*model|aircraft\s+type)',
        'aircraft_ident': r'(aircraft\s+ident|registration|n[\-\s]?number|tail)',
        'route_from': r'(from|origin|dep)',
        'route_to': r'(to|dest|arr)',
        'sel': r'sel',
        'mel': r'mel',
        'cross_country': r'(cross\s+country|xc|x[\-\s]?c)',
        'night': r'night',
        'actual_inst': r'(actual\s+inst|actual\s+imc|act[\.\s]+inst)',
        'simulated_inst': r'(sim\s+inst|sim[\.\s]+inst|hood)',
        'num_inst_app': r'(#\s*inst|inst\s+app|approaches|appr)',
        'landings_day': r'(landings?\s+day|day\s+land)',
        'landings_night': r'(landings?\s+night|night\s+land)',
        'total_duration': r'(total\s+dur|total\s+time|total)',
        'pic': r'pic',
        'sic': r'sic',
        'dual_recd': r'(dual\s+rec|dual\s+recd|dual\s+received)',
        'dual_given': r'(dual\s+giv|cfi)',
        'remarks': r'(remarks|notes|comments)',
    }

    def __init__(self):
        """Initialize logbook parser."""
        pass

    def parse_logbook_page(self, text: str) -> List[Dict]:
        """
        Parse OCR text into structured flight entries.

        Args:
            text: OCR extracted text from logbook page

        Returns:
            List of flight entry dicts
        """
        if not text.strip():
            return []

        # Split into lines
        lines = [line.strip() for line in text.split('\n') if line.strip()]

        # Find header row
        header_idx, column_map = self._detect_columns(lines)
        if header_idx is None or not column_map:
            print("Warning: Could not detect logbook columns")
            return []

        # Extract entries from data rows
        entries = []
        for i in range(header_idx + 1, len(lines)):
            entry = self._extract_row(lines[i], column_map)
            if entry and entry.get('date'):  # Must have at least a date
                normalized = self._normalize_entry(entry)
                entries.append(normalized)

        return entries

    def _detect_columns(self, lines: List[str]) -> Tuple[Optional[int], Dict]:
        """
        Detect column headers and their positions.

        Args:
            lines: List of text lines from OCR

        Returns:
            Tuple of (header_line_index, column_map)
            column_map format: {field_name: (start_pos, end_pos)}
        """
        # Look for header row (usually contains multiple keywords)
        for idx, line in enumerate(lines[:10]):  # Check first 10 lines
            lower_line = line.lower()

            # Count keyword matches
            matches = sum(
                1 for pattern in self.COLUMN_PATTERNS.values()
                if re.search(pattern, lower_line)
            )

            # If 5+ columns found, likely a header
            if matches >= 5:
                return idx, self._map_column_positions(line)

        return None, {}

    def _map_column_positions(self, header_line: str) -> Dict:
        """
        Map column names to their positions in the header line.

        Args:
            header_line: Header line text

        Returns:
            Dict mapping field names to (start_pos, end_pos) tuples
        """
        column_map = {}
        lower_header = header_line.lower()

        # For each expected column, find its position
        for field, pattern in self.COLUMN_PATTERNS.items():
            match = re.search(pattern, lower_header)
            if match:
                start = match.start()
                end = match.end()
                column_map[field] = (start, end)

        return column_map

    def _extract_row(self, line: str, column_map: Dict) -> Dict:
        """
        Extract values from a data row based on column positions.

        Args:
            line: Data row text
            column_map: Column positions from header

        Returns:
            Dict of extracted values
        """
        entry = {}

        # Sort columns by start position for sequential extraction
        sorted_cols = sorted(column_map.items(), key=lambda x: x[1][0])

        for i, (field, (start, end)) in enumerate(sorted_cols):
            # Determine where this column's data ends
            # (start of next column or end of line)
            if i < len(sorted_cols) - 1:
                next_start = sorted_cols[i + 1][1][0]
                value_end = next_start
            else:
                value_end = len(line)

            # Extract value using column boundaries
            value = line[start:value_end].strip()

            # Clean up the value
            value = self._clean_value(value, field)

            if value:
                entry[field] = value

        return entry

    def _clean_value(self, value: str, field: str) -> str:
        """
        Clean and normalize an extracted value.

        Args:
            value: Raw extracted value
            field: Field name (for type-specific cleaning)

        Returns:
            Cleaned value
        """
        if not value:
            return ""

        # Remove extra whitespace
        value = ' '.join(value.split())

        # Field-specific cleaning
        if field in ['route_from', 'route_to', 'aircraft_ident']:
            # Airport codes and tail numbers: uppercase, remove spaces
            value = value.upper().replace(' ', '')

        elif field == 'date':
            # Try to parse and normalize date format
            value = self._normalize_date(value)

        elif field in ['sel', 'mel', 'night', 'cross_country', 'actual_inst',
                       'simulated_inst', 'pic', 'sic', 'dual_recd', 'dual_given',
                       'solo', 'total_duration']:
            # Numeric hours: remove non-numeric except decimal point
            value = re.sub(r'[^\d.]', '', value)

        elif field in ['num_inst_app', 'landings_day', 'landings_night']:
            # Integer counts: remove non-numeric
            value = re.sub(r'[^\d]', '', value)

        return value

    def _normalize_date(self, date_str: str) -> str:
        """
        Normalize date to MM/DD/YYYY format.

        Args:
            date_str: Date string in various formats

        Returns:
            Normalized date in MM/DD/YYYY format, or original if unparseable
        """
        if not date_str:
            return ""

        # Try common date formats
        formats = [
            '%m/%d/%Y',  # 01/15/2025
            '%m/%d/%y',  # 01/15/25
            '%m-%d-%Y',  # 01-15-2025
            '%m-%d-%y',  # 01-15-25
            '%Y-%m-%d',  # 2025-01-15 (ISO)
            '%d/%m/%Y',  # 15/01/2025 (European)
            '%d-%m-%Y',  # 15-01-2025
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                return dt.strftime('%m/%d/%Y')
            except ValueError:
                continue

        # If all parsing fails, return original
        return date_str

    def _normalize_entry(self, entry: Dict) -> Dict:
        """
        Normalize and validate an extracted entry.

        Args:
            entry: Raw extracted entry

        Returns:
            Normalized entry with proper types
        """
        normalized = {}

        # String fields (keep as-is after cleaning)
        for field in ['date', 'aircraft_model', 'aircraft_ident', 'route_from',
                      'route_to', 'remarks']:
            normalized[field] = entry.get(field, "")

        # Float fields (hours)
        for field in ['sel', 'mel', 'day', 'night', 'cross_country', 'actual_inst',
                      'simulated_inst', 'pic', 'sic', 'dual_recd', 'dual_given',
                      'solo', 'total_duration']:
            value = entry.get(field, "0")
            try:
                normalized[field] = float(value) if value else 0.0
            except ValueError:
                normalized[field] = 0.0

        # Integer fields (counts)
        for field in ['num_inst_app', 'landings_day', 'landings_night']:
            value = entry.get(field, "0")
            try:
                normalized[field] = int(value) if value else 0
            except ValueError:
                normalized[field] = 0

        return normalized
