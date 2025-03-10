"""Utility functions for the Eight Sleep integration."""

from homeassistant.const import UnitOfTemperature as HassUnitOfTemperature

from .pyEight.types import UnitOfTemperature as PyEightUnitOfTemperature


def convert_hass_temp_unit_to_pyeight_temp_unit(
    hass_temp_unit: HassUnitOfTemperature,
) -> PyEightUnitOfTemperature:
    """Convert Home Assistant temperature unit to pyEight temperature unit."""
    if hass_temp_unit == HassUnitOfTemperature.CELSIUS:
        return "c"
    return "f"
