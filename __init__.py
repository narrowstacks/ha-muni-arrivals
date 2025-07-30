"""The Muni Times integration."""
from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import (
    CONF_API_KEY,
    CONF_STOPS,
    CONF_AGENCY,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AGENCY,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
)
from .muni_api import MuniAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Muni Times from a config entry."""
    
    api_key = entry.data[CONF_API_KEY]
    stops = entry.data.get(CONF_STOPS, [])
    agency = entry.data.get(CONF_AGENCY, DEFAULT_AGENCY)
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    
    api = MuniAPI(api_key, agency)
    
    coordinator = MuniTimesDataUpdateCoordinator(
        hass,
        api=api,
        stops=stops,
        update_interval=timedelta(seconds=update_interval),
    )

    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok


class MuniTimesDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: MuniAPI,
        stops: list[dict],
        update_interval: timedelta,
    ) -> None:
        """Initialize."""
        self.api = api
        self.stops = stops
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self):
        """Update data via library."""
        try:
            data = {}
            for stop in self.stops:
                stop_code = stop.get("stop_code")
                if stop_code:
                    stop_data = await self.api.get_arrivals(stop_code)
                    data[stop_code] = {
                        "arrivals": stop_data,
                        "config": stop
                    }
            return data
        except Exception as exception:
            raise UpdateFailed(f"Error communicating with API: {exception}")