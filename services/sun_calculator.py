"""
Sun position calculator for determining sunset times.

Uses astronomical calculations to determine sunset time at a given location.
"""

import math
from datetime import datetime, timedelta, timezone
from typing import Optional


def calculate_sunset(lat: float, lon: float, date: datetime) -> Optional[datetime]:
    """
    Calculate sunset time for a given location and date.
    
    Uses the NOAA solar calculator algorithm.
    
    Args:
        lat: Latitude in degrees (positive = North)
        lon: Longitude in degrees (positive = East)
        date: Date for which to calculate sunset
        
    Returns:
        Sunset time as datetime in UTC, or None if calculation fails
    """
    try:
        # Julian Day calculation
        year = date.year
        month = date.month
        day = date.day
        
        if month <= 2:
            year -= 1
            month += 12
            
        A = math.floor(year / 100)
        B = 2 - A + math.floor(A / 4)
        
        JD = math.floor(365.25 * (year + 4716)) + math.floor(30.6001 * (month + 1)) + day + B - 1524.5
        
        # Julian Century
        T = (JD - 2451545.0) / 36525.0
        
        # Geometric Mean Longitude of Sun (degrees)
        L0 = (280.46646 + T * (36000.76983 + 0.0003032 * T)) % 360
        
        # Geometric Mean Anomaly of Sun (degrees)
        M = 357.52911 + T * (35999.05029 - 0.0001537 * T)
        
        # Eccentricity of Earth's orbit
        e = 0.016708634 - T * (0.000042037 + 0.0000001267 * T)
        
        # Sun's Equation of Center
        M_rad = math.radians(M)
        C = (math.sin(M_rad) * (1.914602 - T * (0.004817 + 0.000014 * T)) +
             math.sin(2 * M_rad) * (0.019993 - 0.000101 * T) +
             math.sin(3 * M_rad) * 0.000289)
        
        # Sun's True Longitude
        sun_long = L0 + C
        
        # Sun's Apparent Longitude
        omega = 125.04 - 1934.136 * T
        sun_apparent_long = sun_long - 0.00569 - 0.00478 * math.sin(math.radians(omega))
        
        # Mean Obliquity of the Ecliptic
        obliquity = 23.439291 - 0.0130042 * T
        
        # Corrected Obliquity
        obliquity_corr = obliquity + 0.00256 * math.cos(math.radians(omega))
        
        # Sun's Declination
        sun_decl = math.degrees(math.asin(
            math.sin(math.radians(obliquity_corr)) * math.sin(math.radians(sun_apparent_long))
        ))
        
        # Equation of Time (minutes)
        var_y = math.tan(math.radians(obliquity_corr / 2)) ** 2
        eq_of_time = 4 * math.degrees(
            var_y * math.sin(2 * math.radians(L0)) -
            2 * e * math.sin(M_rad) +
            4 * e * var_y * math.sin(M_rad) * math.cos(2 * math.radians(L0)) -
            0.5 * var_y ** 2 * math.sin(4 * math.radians(L0)) -
            1.25 * e ** 2 * math.sin(2 * M_rad)
        )
        
        # Solar Noon (LST) - in minutes from midnight
        solar_noon = 720 - 4 * lon - eq_of_time
        
        # Hour Angle for Sunset
        # Using -0.833 degrees for atmospheric refraction at sunset
        zenith = 90.833
        lat_rad = math.radians(lat)
        decl_rad = math.radians(sun_decl)
        
        cos_hour_angle = (
            math.cos(math.radians(zenith)) / (math.cos(lat_rad) * math.cos(decl_rad)) -
            math.tan(lat_rad) * math.tan(decl_rad)
        )
        
        # Check if sun sets at this location on this date
        if cos_hour_angle > 1 or cos_hour_angle < -1:
            return None  # No sunset (polar day/night)
            
        hour_angle = math.degrees(math.acos(cos_hour_angle))
        
        # Sunset time in minutes from midnight (local solar time)
        sunset_minutes = solar_noon + hour_angle * 4
        
        # Convert to UTC
        sunset_hours = sunset_minutes / 60
        sunset_dt = datetime(year, month, day, tzinfo=timezone.utc) + timedelta(hours=sunset_hours)
        
        return sunset_dt
        
    except Exception as e:
        print(f"Error calculating sunset: {e}")
        return None


def estimate_night_hours(
    departure_time: datetime,
    arrival_time: datetime,
    dest_lat: float,
    dest_lon: float,
    night_landings: int = 0,
) -> float:
    """
    Estimate night flying hours based on sunset time and flight times.
    
    Night is defined as the time between the end of evening civil twilight
    and the beginning of morning civil twilight. For simplicity, we use
    sunset + 30 minutes as the start of "night" (approximate civil twilight end).
    
    Args:
        departure_time: Departure time (UTC)
        arrival_time: Arrival time (UTC)
        dest_lat: Destination airport latitude
        dest_lon: Destination airport longitude
        night_landings: Number of night landings (used as a hint)
        
    Returns:
        Estimated night hours (rounded to 1 decimal)
    """
    if not departure_time or not arrival_time:
        return 0.0
        
    # Calculate sunset at destination
    sunset = calculate_sunset(dest_lat, dest_lon, arrival_time)
    
    if not sunset:
        # If we can't calculate sunset, use night landings as a hint
        if night_landings > 0:
            total_duration = (arrival_time - departure_time).total_seconds() / 3600
            # Assume at least 30 min of night flying for a night landing
            return min(total_duration, max(0.5, total_duration * 0.3))
        return 0.0
    
    # Night begins ~30 minutes after sunset (end of civil twilight)
    night_begins = sunset + timedelta(minutes=30)
    
    # Calculate night portion of flight
    if arrival_time <= night_begins:
        # Entire flight was during day
        return 0.0
    elif departure_time >= night_begins:
        # Entire flight was at night
        total_duration = (arrival_time - departure_time).total_seconds() / 3600
        return round(total_duration, 1)
    else:
        # Flight crossed into night
        night_portion = (arrival_time - night_begins).total_seconds() / 3600
        return round(max(0.0, night_portion), 1)


def is_night_landing(arrival_time: datetime, dest_lat: float, dest_lon: float) -> bool:
    """
    Determine if a landing occurred at night.
    
    Args:
        arrival_time: Arrival time (UTC)
        dest_lat: Destination airport latitude  
        dest_lon: Destination airport longitude
        
    Returns:
        True if landing was at night
    """
    sunset = calculate_sunset(dest_lat, dest_lon, arrival_time)
    
    if not sunset:
        return False
    
    # Night begins ~30 minutes after sunset
    night_begins = sunset + timedelta(minutes=30)
    
    return arrival_time >= night_begins
