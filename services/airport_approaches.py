"""
Airport instrument approaches database.

Provides approach information for US airports.
"""

# Common approach types
APPROACH_TYPES = {
    "ILS": "ILS",
    "LOC": "LOC",
    "VOR": "VOR",
    "RNAV": "RNAV (GPS)",
    "LPV": "LPV",
    "LNAV": "LNAV",
    "NDB": "NDB",
    "VISUAL": "Visual",
}

# Approach database for common airports (expandable)
# Format: airport_icao -> list of approaches
AIRPORT_APPROACHES = {
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
        {"id": "VOR16", "name": "VOR-A", "type": "VOR"},
    ],
    "KPDX": [
        {"id": "ILS10L", "name": "ILS RWY 10L", "type": "ILS"},
        {"id": "ILS10R", "name": "ILS RWY 10R", "type": "ILS"},
        {"id": "ILS28L", "name": "ILS RWY 28L", "type": "ILS"},
        {"id": "ILS28R", "name": "ILS RWY 28R", "type": "ILS"},
        {"id": "RNAV10L", "name": "RNAV (GPS) RWY 10L", "type": "RNAV"},
        {"id": "RNAV10R", "name": "RNAV (GPS) RWY 10R", "type": "RNAV"},
        {"id": "RNAV28L", "name": "RNAV (GPS) RWY 28L", "type": "RNAV"},
        {"id": "RNAV28R", "name": "RNAV (GPS) RWY 28R", "type": "RNAV"},
    ],
    "KOAK": [
        {"id": "ILS12", "name": "ILS RWY 12", "type": "ILS"},
        {"id": "ILS30", "name": "ILS RWY 30", "type": "ILS"},
        {"id": "RNAV12", "name": "RNAV (GPS) RWY 12", "type": "RNAV"},
        {"id": "RNAV30", "name": "RNAV (GPS) RWY 30", "type": "RNAV"},
    ],
    "KSFO": [
        {"id": "ILS28L", "name": "ILS RWY 28L", "type": "ILS"},
        {"id": "ILS28R", "name": "ILS RWY 28R", "type": "ILS"},
        {"id": "RNAV28L", "name": "RNAV (GPS) RWY 28L", "type": "RNAV"},
        {"id": "RNAV28R", "name": "RNAV (GPS) RWY 28R", "type": "RNAV"},
        {"id": "RNAV19L", "name": "RNAV (GPS) RWY 19L", "type": "RNAV"},
        {"id": "RNAV19R", "name": "RNAV (GPS) RWY 19R", "type": "RNAV"},
    ],
    "KSJC": [
        {"id": "ILS30L", "name": "ILS RWY 30L", "type": "ILS"},
        {"id": "ILS30R", "name": "ILS RWY 30R", "type": "ILS"},
        {"id": "RNAV30L", "name": "RNAV (GPS) RWY 30L", "type": "RNAV"},
        {"id": "RNAV30R", "name": "RNAV (GPS) RWY 30R", "type": "RNAV"},
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
    "KLAS": [
        {"id": "ILS26L", "name": "ILS RWY 26L", "type": "ILS"},
        {"id": "ILS26R", "name": "ILS RWY 26R", "type": "ILS"},
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
        {"id": "RNAV34L", "name": "RNAV (GPS) RWY 34L", "type": "RNAV"},
        {"id": "RNAV34R", "name": "RNAV (GPS) RWY 34R", "type": "RNAV"},
        {"id": "RNAV35L", "name": "RNAV (GPS) RWY 35L", "type": "RNAV"},
        {"id": "RNAV35R", "name": "RNAV (GPS) RWY 35R", "type": "RNAV"},
    ],
}


def get_approaches_for_airport(icao_code: str) -> list[dict]:
    """
    Get list of instrument approaches for an airport.

    Args:
        icao_code: ICAO airport code (e.g., "KPAE")

    Returns:
        List of approach dictionaries with id, name, and type
    """
    icao_code = icao_code.upper().strip()

    # Return from database if available
    if icao_code in AIRPORT_APPROACHES:
        return AIRPORT_APPROACHES[icao_code]

    # For unknown airports, return generic RNAV approaches
    # Most airports have at least RNAV approaches nowadays
    return [
        {"id": "RNAV", "name": "RNAV (GPS)", "type": "RNAV"},
        {"id": "ILS", "name": "ILS", "type": "ILS"},
        {"id": "VOR", "name": "VOR", "type": "VOR"},
        {"id": "LOC", "name": "LOC", "type": "LOC"},
        {"id": "VISUAL", "name": "Visual", "type": "VISUAL"},
    ]


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
            matches.append({"icao": icao, "approach_count": len(AIRPORT_APPROACHES[icao])})
    return matches
