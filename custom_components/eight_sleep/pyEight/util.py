"""Util functions for the Eight Sleep API."""

from .constants import RAW_TO_CELSIUS_MAP, RAW_TO_FAHRENHEIT_MAP
from .types import UnitOfTemperature


def heating_level_to_temp(heating_level: int, degree_unit: UnitOfTemperature) -> int:
    """Convert heating level (-100 to 100) to degrees.
    
    The Eight Sleep app does not use an algebraic formula to convert the heating level, so we use a lookup table.
    """
    temp_map = (
        RAW_TO_CELSIUS_MAP if degree_unit.lower() == "c" or degree_unit.lower() == "celsius" else RAW_TO_FAHRENHEIT_MAP
    )

    min_diff = 100
    closest_key = 0
    for key in temp_map:
        diff = abs(key - heating_level)
        if diff < min_diff:
            min_diff = diff
            closest_key = key

    return temp_map[closest_key]


def temp_to_heating_level(degrees: int, degree_unit: UnitOfTemperature) -> int:
    """Convert degrees to heating level (-100 to 100).
    
    The Eight Sleep app does not use an algebraic formula to convert the heating level, so we use a lookup table.
    """
    temp_map = (
        RAW_TO_CELSIUS_MAP if degree_unit.lower() == "c" or degree_unit.lower() == "celsius" else RAW_TO_FAHRENHEIT_MAP
    )

    min_diff = 100
    closest_key = 0
    for key, value in temp_map.items():
        diff = abs(value - degrees)
        if diff < min_diff:
            min_diff = diff
            closest_key = key

    return closest_key
