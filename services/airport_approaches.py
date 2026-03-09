"""
Airport instrument approaches database.

Provides approach information for US airports.
Uses a static database with actual FAA approach names,
with dynamic fallback using OurAirports runway data.
"""

import csv
import os
from pathlib import Path

_runway_cache: dict[str, list[str]] | None = None

# Static database for airports with actual FAA approach names
AIRPORT_APPROACHES = {
    # Alaska airports
    "PADU": [
        {"id": "RNAV13", "name": "RNAV (GPS) RWY 13", "type": "RNAV"},
        {"id": "RNAV31", "name": "RNAV (GPS) RWY 31", "type": "RNAV"},
        {"id": "VORDME-A", "name": "VOR/DME-A", "type": "VOR"},
    ],
    "PASY": [
        {"id": "RNAV23", "name": "RNAV (GPS) RWY 23", "type": "RNAV"},
        {"id": "RNAV05", "name": "RNAV (GPS) RWY 05", "type": "RNAV"},
        {"id": "TACAN23", "name": "TACAN RWY 23", "type": "TACAN"},
        {"id": "TACAN05", "name": "TACAN RWY 05", "type": "TACAN"},
    ],
    "PANC": [
        {"id": "ILS07L", "name": "ILS RWY 07L", "type": "ILS"},
        {"id": "ILS07R", "name": "ILS RWY 07R", "type": "ILS"},
        {"id": "ILS15", "name": "ILS RWY 15", "type": "ILS"},
        {"id": "RNAV07L", "name": "RNAV (GPS) RWY 07L", "type": "RNAV"},
        {"id": "RNAV07R", "name": "RNAV (GPS) RWY 07R", "type": "RNAV"},
        {"id": "RNAV15", "name": "RNAV (GPS) RWY 15", "type": "RNAV"},
        {"id": "RNAV25L", "name": "RNAV (GPS) RWY 25L", "type": "RNAV"},
        {"id": "RNAV25R", "name": "RNAV (GPS) RWY 25R", "type": "RNAV"},
        {"id": "RNAV33", "name": "RNAV (GPS) RWY 33", "type": "RNAV"},
    ],
    "PAFA": [
        {"id": "ILS02L", "name": "ILS RWY 02L", "type": "ILS"},
        {"id": "RNAV02L", "name": "RNAV (GPS) RWY 02L", "type": "RNAV"},
        {"id": "RNAV02R", "name": "RNAV (GPS) RWY 02R", "type": "RNAV"},
        {"id": "RNAV20L", "name": "RNAV (GPS) RWY 20L", "type": "RNAV"},
        {"id": "RNAV20R", "name": "RNAV (GPS) RWY 20R", "type": "RNAV"},
        {"id": "VOR02L", "name": "VOR RWY 02L", "type": "VOR"},
    ],
    "PAJN": [
        {"id": "ILS08", "name": "ILS RWY 08", "type": "ILS"},
        {"id": "LDASB08", "name": "LDA/GS-B RWY 08", "type": "LDA"},
        {"id": "RNAV08", "name": "RNAV (GPS) RWY 08", "type": "RNAV"},
        {"id": "RNAV26", "name": "RNAV (GPS) RWY 26", "type": "RNAV"},
        {"id": "VOR08", "name": "VOR RWY 08", "type": "VOR"},
    ],
    # Pacific Northwest
    "KPAE": [
        {"id": "ILS16R", "name": "ILS RWY 16R", "type": "ILS"},
        {"id": "RNAV16R", "name": "RNAV (GPS) RWY 16R", "type": "RNAV"},
        {"id": "RNAV34L", "name": "RNAV (GPS) RWY 34L", "type": "RNAV"},
        {"id": "VOR16R", "name": "VOR RWY 16R", "type": "VOR"},
        {"id": "VISUAL16R", "name": "Visual RWY 16R", "type": "VISUAL"},
        {"id": "VISUAL34L", "name": "Visual RWY 34L", "type": "VISUAL"},
    ],
    "KSEA": [
        {"id": "ILS16L", "name": "ILS RWY 16L", "type": "ILS"},
        {"id": "ILS16C", "name": "ILS RWY 16C", "type": "ILS"},
        {"id": "ILS16R", "name": "ILS RWY 16R", "type": "ILS"},
        {"id": "ILS34L", "name": "ILS RWY 34L", "type": "ILS"},
        {"id": "ILS34C", "name": "ILS RWY 34C", "type": "ILS"},
        {"id": "ILS34R", "name": "ILS RWY 34R", "type": "ILS"},
        {"id": "RNAV16L", "name": "RNAV (GPS) RWY 16L", "type": "RNAV"},
        {"id": "RNAV16C", "name": "RNAV (GPS) RWY 16C", "type": "RNAV"},
        {"id": "RNAV16R", "name": "RNAV (GPS) RWY 16R", "type": "RNAV"},
        {"id": "RNAV34L", "name": "RNAV (GPS) RWY 34L", "type": "RNAV"},
        {"id": "RNAV34C", "name": "RNAV (GPS) RWY 34C", "type": "RNAV"},
        {"id": "RNAV34R", "name": "RNAV (GPS) RWY 34R", "type": "RNAV"},
    ],
    "KBFI": [
        {"id": "ILS14R", "name": "ILS RWY 14R", "type": "ILS"},
        {"id": "RNAV14R", "name": "RNAV (GPS) RWY 14R", "type": "RNAV"},
        {"id": "RNAV32L", "name": "RNAV (GPS) RWY 32L", "type": "RNAV"},
        {"id": "VOR14R", "name": "VOR RWY 14R", "type": "VOR"},
        {"id": "LOC14R", "name": "LOC RWY 14R", "type": "LOC"},
    ],
    "KONP": [
        {"id": "RNAV16", "name": "RNAV (GPS) RWY 16", "type": "RNAV"},
        {"id": "RNAV34", "name": "RNAV (GPS) RWY 34", "type": "RNAV"},
        {"id": "VOR-A", "name": "VOR-A", "type": "VOR"},
    ],
    "KPDX": [
        {"id": "ILS10L", "name": "ILS Y RWY 10L", "type": "ILS"},
        {"id": "ILS10R", "name": "ILS Y RWY 10R", "type": "ILS"},
        {"id": "ILS28L", "name": "ILS Y RWY 28L", "type": "ILS"},
        {"id": "ILS28R", "name": "ILS Y RWY 28R", "type": "ILS"},
        {"id": "RNAV10L", "name": "RNAV (GPS) Y RWY 10L", "type": "RNAV"},
        {"id": "RNAV10R", "name": "RNAV (GPS) Y RWY 10R", "type": "RNAV"},
        {"id": "RNAV28L", "name": "RNAV (GPS) Y RWY 28L", "type": "RNAV"},
        {"id": "RNAV28R", "name": "RNAV (GPS) Y RWY 28R", "type": "RNAV"},
    ],
    # California
    "KOAK": [
        {"id": "ILS12", "name": "ILS RWY 12", "type": "ILS"},
        {"id": "ILS30", "name": "ILS RWY 30", "type": "ILS"},
        {"id": "RNAV12", "name": "RNAV (GPS) RWY 12", "type": "RNAV"},
        {"id": "RNAV30", "name": "RNAV (GPS) RWY 30", "type": "RNAV"},
    ],
    "KSFO": [
        {"id": "ILS28L", "name": "ILS RWY 28L", "type": "ILS"},
        {"id": "ILS28R", "name": "ILS RWY 28R", "type": "ILS"},
        {"id": "RNAV28L", "name": "RNAV (RNP) RWY 28L", "type": "RNAV"},
        {"id": "RNAV28R", "name": "RNAV (RNP) RWY 28R", "type": "RNAV"},
        {"id": "RNAV19L", "name": "RNAV (GPS) RWY 19L", "type": "RNAV"},
        {"id": "RNAV19R", "name": "RNAV (GPS) RWY 19R", "type": "RNAV"},
    ],
    "KSJC": [
        {"id": "ILS30L", "name": "ILS Y RWY 30L", "type": "ILS"},
        {"id": "ILS30R", "name": "ILS Y RWY 30R", "type": "ILS"},
        {"id": "RNAV30L", "name": "RNAV (GPS) Y RWY 30L", "type": "RNAV"},
        {"id": "RNAV30R", "name": "RNAV (GPS) Y RWY 30R", "type": "RNAV"},
        {"id": "RNAV12L", "name": "RNAV (GPS) RWY 12L", "type": "RNAV"},
        {"id": "RNAV12R", "name": "RNAV (GPS) RWY 12R", "type": "RNAV"},
    ],
    "KLAX": [
        {"id": "ILS24L", "name": "ILS RWY 24L", "type": "ILS"},
        {"id": "ILS24R", "name": "ILS RWY 24R", "type": "ILS"},
        {"id": "ILS25L", "name": "ILS RWY 25L", "type": "ILS"},
        {"id": "ILS25R", "name": "ILS RWY 25R", "type": "ILS"},
        {"id": "RNAV24L", "name": "RNAV (GPS) RWY 24L", "type": "RNAV"},
        {"id": "RNAV24R", "name": "RNAV (GPS) RWY 24R", "type": "RNAV"},
        {"id": "RNAV25L", "name": "RNAV (GPS) RWY 25L", "type": "RNAV"},
        {"id": "RNAV25R", "name": "RNAV (GPS) RWY 25R", "type": "RNAV"},
    ],
    # Southwest
    "KLAS": [
        {"id": "ILS26L", "name": "ILS RWY 26L", "type": "ILS"},
        {"id": "ILS26R", "name": "ILS RWY 26R", "type": "ILS"},
        {"id": "ILS01L", "name": "ILS RWY 01L", "type": "ILS"},
        {"id": "ILS01R", "name": "ILS RWY 01R", "type": "ILS"},
        {"id": "RNAV26L", "name": "RNAV (GPS) RWY 26L", "type": "RNAV"},
        {"id": "RNAV26R", "name": "RNAV (GPS) RWY 26R", "type": "RNAV"},
        {"id": "RNAV19L", "name": "RNAV (GPS) RWY 19L", "type": "RNAV"},
        {"id": "RNAV19R", "name": "RNAV (GPS) RWY 19R", "type": "RNAV"},
    ],
    "KPHX": [
        {"id": "ILS26", "name": "ILS RWY 26", "type": "ILS"},
        {"id": "ILS25L", "name": "ILS RWY 25L", "type": "ILS"},
        {"id": "ILS25R", "name": "ILS RWY 25R", "type": "ILS"},
        {"id": "RNAV26", "name": "RNAV (GPS) RWY 26", "type": "RNAV"},
        {"id": "RNAV25L", "name": "RNAV (GPS) RWY 25L", "type": "RNAV"},
        {"id": "RNAV25R", "name": "RNAV (GPS) RWY 25R", "type": "RNAV"},
        {"id": "RNAV7L", "name": "RNAV (GPS) RWY 7L", "type": "RNAV"},
        {"id": "RNAV7R", "name": "RNAV (GPS) RWY 7R", "type": "RNAV"},
        {"id": "RNAV8", "name": "RNAV (GPS) RWY 8", "type": "RNAV"},
    ],
    "KDEN": [
        {"id": "ILS34L", "name": "ILS RWY 34L", "type": "ILS"},
        {"id": "ILS34R", "name": "ILS RWY 34R", "type": "ILS"},
        {"id": "ILS35L", "name": "ILS RWY 35L", "type": "ILS"},
        {"id": "ILS35R", "name": "ILS RWY 35R", "type": "ILS"},
        {"id": "ILS17L", "name": "ILS RWY 17L", "type": "ILS"},
        {"id": "ILS17R", "name": "ILS RWY 17R", "type": "ILS"},
        {"id": "RNAV34L", "name": "RNAV (GPS) RWY 34L", "type": "RNAV"},
        {"id": "RNAV34R", "name": "RNAV (GPS) RWY 34R", "type": "RNAV"},
        {"id": "RNAV35L", "name": "RNAV (GPS) RWY 35L", "type": "RNAV"},
        {"id": "RNAV35R", "name": "RNAV (GPS) RWY 35R", "type": "RNAV"},
    ],
}


def get_approaches_for_airport(icao_code: str) -> list[dict]:
    """
    Get list of instrument approaches for an airport.

    Uses static database with actual FAA approach names.

    Args:
        icao_code: ICAO airport code (e.g., "KPAE", "PADU")

    Returns:
        List of approach dictionaries with id, name, and type
    """
    icao_code = icao_code.upper().strip()

    # Remove trailing asterisk if present (from coordinate-based lookups)
    icao_code = icao_code.rstrip("*")

    # Return from static database if available
    if icao_code in AIRPORT_APPROACHES:
        return AIRPORT_APPROACHES[icao_code]

    # Generate approaches from runway data
    runways = _get_runways(icao_code)
    if runways:
        approaches = []
        for rwy in runways:
            approaches.append({"id": f"RNAV{rwy}", "name": f"RNAV (GPS) RWY {rwy}", "type": "RNAV"})
            approaches.append({"id": f"ILS{rwy}", "name": f"ILS RWY {rwy}", "type": "ILS"})
            approaches.append({"id": f"VOR{rwy}", "name": f"VOR RWY {rwy}", "type": "VOR"})
            approaches.append({"id": f"LOC{rwy}", "name": f"LOC RWY {rwy}", "type": "LOC"})
            approaches.append({"id": f"VISUAL{rwy}", "name": f"Visual RWY {rwy}", "type": "VISUAL"})
        return approaches

    # Last resort: no runway data available
    return [
        {"id": "RNAV", "name": "RNAV (GPS)", "type": "RNAV"},
        {"id": "ILS", "name": "ILS", "type": "ILS"},
        {"id": "VOR", "name": "VOR", "type": "VOR"},
        {"id": "LOC", "name": "LOC", "type": "LOC"},
        {"id": "VISUAL", "name": "Visual", "type": "VISUAL"},
    ]


def _get_runways(icao_code: str) -> list[str]:
    """Get runway designators for an airport from runways.csv."""
    global _runway_cache

    if _runway_cache is None:
        _runway_cache = _load_runway_data()

    return _runway_cache.get(icao_code, [])


def _load_runway_data() -> dict[str, list[str]]:
    """Load runway designators from OurAirports runways.csv."""
    cache: dict[str, list[str]] = {}

    # Check multiple possible locations
    project_root = Path(__file__).parent.parent
    for candidate in [
        project_root / "data" / "runways.csv",
        Path("/tmp/runways.csv"),
    ]:
        if candidate.exists():
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        ident = row.get("airport_ident", "").upper()
                        if not ident or row.get("closed") == "1":
                            continue
                        le = row.get("le_ident", "").strip()
                        he = row.get("he_ident", "").strip()
                        if ident not in cache:
                            cache[ident] = []
                        if le and le not in cache[ident]:
                            cache[ident].append(le)
                        if he and he not in cache[ident]:
                            cache[ident].append(he)
                print(f"Loaded runway data for {len(cache)} airports")
            except Exception as e:
                print(f"Error loading runways.csv: {e}")
            break

    return cache


def search_airports(query: str) -> list[dict]:
    """
    Search for airports with approaches in database.

    Args:
        query: Search query (partial ICAO code)

    Returns:
        List of matching airport codes
    """
    query = query.upper().strip()
    matches = []
    for icao in AIRPORT_APPROACHES.keys():
        if query in icao:
            matches.append(
                {"icao": icao, "approach_count": len(AIRPORT_APPROACHES[icao])}
            )
    return matches
