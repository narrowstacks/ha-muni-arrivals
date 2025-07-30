"""Sensor platform for Muni Times integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    CONF_MAX_RESULTS,
    CONF_SHOW_LINE_ICONS,
    CONF_TIME_FORMAT,
    DEFAULT_MAX_RESULTS,
    DEFAULT_SHOW_LINE_ICONS,
    DEFAULT_TIME_FORMAT,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Muni Times sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    entities = []
    
    # Create a sensor for each configured stop
    for stop in coordinator.stops:
        stop_code = stop.get("stop_code")
        stop_name = stop.get("stop_name", f"Stop {stop_code}")
        
        if stop_code:
            entities.append(
                MuniTimesStopSensor(
                    coordinator=coordinator,
                    stop_code=stop_code,
                    stop_name=stop_name,
                    stop_config=stop,
                    config_entry=config_entry,
                )
            )
    
    async_add_entities(entities, update_before_add=True)


class MuniTimesStopSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Muni Times stop sensor."""

    def __init__(
        self,
        coordinator,
        stop_code: str,
        stop_name: str,
        stop_config: dict,
        config_entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        
        self._stop_code = stop_code
        self._stop_name = stop_name
        self._stop_config = stop_config
        self._config_entry = config_entry
        
        self._attr_name = stop_name
        self._attr_unique_id = f"{DOMAIN}_{stop_code}"
        self._attr_icon = "mdi:bus"
        
        # Configuration options
        self._max_results = config_entry.data.get(CONF_MAX_RESULTS, DEFAULT_MAX_RESULTS)
        self._show_line_icons = config_entry.data.get(CONF_SHOW_LINE_ICONS, DEFAULT_SHOW_LINE_ICONS)
        self._time_format = config_entry.data.get(CONF_TIME_FORMAT, DEFAULT_TIME_FORMAT)

    @property
    def native_value(self) -> str | None:
        """Return the state of the sensor."""
        if not self.coordinator.data or self._stop_code not in self.coordinator.data:
            return "No data"
        
        stop_data = self.coordinator.data[self._stop_code]
        arrivals = stop_data.get("arrivals", [])
        
        if not arrivals:
            return "No arrivals"
        
        # Return the next arrival time for the first line
        first_line = arrivals[0]
        if first_line.get("times"):
            next_arrival = first_line["times"][0]
            return next_arrival.get("formatted_time", "?")
        
        return "No arrivals"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes."""
        if not self.coordinator.data or self._stop_code not in self.coordinator.data:
            return {}
        
        stop_data = self.coordinator.data[self._stop_code]
        arrivals = stop_data.get("arrivals", [])
        
        attributes = {
            "stop_code": self._stop_code,
            "stop_name": self._stop_name,
            "agency": self._config_entry.data.get("agency", "SF"),
            "last_updated": self.coordinator.last_update_success_time,
            "lines": [],
        }
        
        # Add arrival information for each line
        for arrival in arrivals[:self._max_results]:
            line_info = {
                "line": arrival.get("line", ""),
                "line_ref": arrival.get("line_ref", ""),
                "destinations": arrival.get("destinations", []),
                "arrivals": []
            }
            
            # Add up to max_results arrivals for this line
            for time_info in arrival.get("times", [])[:self._max_results]:
                line_info["arrivals"].append({
                    "minutes": time_info.get("minutes", "?"),
                    "formatted_time": time_info.get("formatted_time", "?"),
                    "destination": time_info.get("destination", ""),
                    "arrival_time": time_info.get("arrival_time", "")
                })
            
            attributes["lines"].append(line_info)
        
        # Add configuration info
        if self._stop_config.get("direction"):
            attributes["direction"] = self._stop_config["direction"]
        
        if self._stop_config.get("line_names"):
            attributes["line_name_overrides"] = self._stop_config["line_names"]
        
        return attributes

    @property
    def available(self) -> bool:
        """Return True if entity is available."""
        return self.coordinator.last_update_success

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information about this sensor."""
        return {
            "identifiers": {(DOMAIN, self._stop_code)},
            "name": self._stop_name,
            "manufacturer": "511.org",
            "model": "Transit Stop",
            "sw_version": "1.0.0",
        }