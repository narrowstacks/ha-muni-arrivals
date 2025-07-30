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
    ATTR_API_HEALTH,
    ATTR_CACHE_STATUS,
    ATTR_CACHED_DATA_AGE,
    ATTR_CONNECTION_STATUS,
    ATTR_ERROR_COUNT,
    ATTR_LAST_ERROR,
    ATTR_SUCCESS_RATE,
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
        """Return the state of the sensor with cache indicators."""
        if not self.coordinator.data or self._stop_code not in self.coordinator.data:
            # Check if we're in an error state
            if hasattr(self.coordinator, 'consecutive_failures') and self.coordinator.consecutive_failures > 0:
                return "Connection error"
            return "No data"
        
        stop_data = self.coordinator.data[self._stop_code]
        arrivals = stop_data.get("arrivals", [])
        from_cache = stop_data.get("from_cache", False)
        
        if not arrivals:
            if from_cache:
                return "No arrivals (cached)"
            return "No arrivals"
        
        # Return the next arrival time for the first line
        first_line = arrivals[0]
        if first_line.get("times"):
            next_arrival = first_line["times"][0]
            formatted_time = next_arrival.get("formatted_time", "?")
            
            # Add cache indicator if data is from cache
            if from_cache:
                cache_age = stop_data.get("cache_age_minutes", 0)
                if cache_age > 0:
                    return f"{formatted_time} (cached {cache_age:.0f}m ago)"
                else:
                    return f"{formatted_time} (cached)"
            
            return formatted_time
        
        if from_cache:
            return "No arrivals (cached)"
        return "No arrivals"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return the state attributes with enhanced error and cache information."""
        # Base attributes always available
        attributes = {
            "stop_code": self._stop_code,
            "stop_name": self._stop_name,
            "agency": self._config_entry.data.get("agency", "SF"),
            "lines": [],
        }
        
        # Add error and health information
        if hasattr(self.coordinator, 'consecutive_failures'):
            attributes[ATTR_ERROR_COUNT] = self.coordinator.consecutive_failures
        
        if hasattr(self.coordinator, 'error_history') and self.coordinator.error_history:
            attributes[ATTR_LAST_ERROR] = self.coordinator.error_history[-1]
        
        # Add API health status
        if hasattr(self.coordinator, 'api') and hasattr(self.coordinator.api, 'get_health_status'):
            try:
                health_status = self.coordinator.api.get_health_status()
                attributes[ATTR_API_HEALTH] = {
                    "is_healthy": health_status.get("is_healthy", False),
                    "consecutive_failures": health_status.get("consecutive_failures", 0),
                }
                attributes[ATTR_SUCCESS_RATE] = health_status.get("success_rate", 0.0)
                
                # Connection status based on health
                if health_status.get("is_healthy", False):
                    attributes[ATTR_CONNECTION_STATUS] = "healthy"
                elif health_status.get("consecutive_failures", 0) > 3:
                    attributes[ATTR_CONNECTION_STATUS] = "unhealthy"
                else:
                    attributes[ATTR_CONNECTION_STATUS] = "degraded"
            except Exception as e:
                _LOGGER.debug("Failed to get API health status: %s", e)
                attributes[ATTR_CONNECTION_STATUS] = "unknown"
        
        # Add cache information
        cache_status = "disabled"
        if hasattr(self.coordinator, 'cache') and self.coordinator.cache:
            cache_status = "enabled"
            try:
                cache_info = self.coordinator.cache.get_cache_info()
                attributes[ATTR_CACHE_STATUS] = {
                    "enabled": True,
                    "total_entries": cache_info.get("total_entries", 0),
                    "valid_entries": cache_info.get("valid_entries", 0),
                }
            except Exception as e:
                _LOGGER.debug("Failed to get cache info: %s", e)
                attributes[ATTR_CACHE_STATUS] = {"enabled": True, "error": str(e)}
        else:
            attributes[ATTR_CACHE_STATUS] = {"enabled": False}
        
        # Add last updated time
        if self.coordinator.last_update_success_time:
            attributes["last_updated"] = self.coordinator.last_update_success_time.isoformat()
        
        # Process stop data if available
        if self.coordinator.data and self._stop_code in self.coordinator.data:
            stop_data = self.coordinator.data[self._stop_code]
            arrivals = stop_data.get("arrivals", [])
            from_cache = stop_data.get("from_cache", False)
            
            # Add cache-specific information
            if from_cache:
                attributes["data_source"] = "cache"
                cache_age = stop_data.get("cache_age_minutes", 0)
                attributes[ATTR_CACHED_DATA_AGE] = cache_age
                
                if stop_data.get("cached_at"):
                    attributes["cached_at"] = stop_data["cached_at"]
            else:
                attributes["data_source"] = "api"
                attributes[ATTR_CACHED_DATA_AGE] = 0
            
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
            
            # Update last updated time if we have fresh data
            if not from_cache and stop_data.get("last_updated"):
                attributes["last_updated"] = stop_data["last_updated"].isoformat()
        else:
            # No data available
            attributes["data_source"] = "none"
            attributes[ATTR_CACHED_DATA_AGE] = 0
        
        # Add configuration info
        if self._stop_config.get("direction"):
            attributes["direction"] = self._stop_config["direction"]
        
        if self._stop_config.get("line_names"):
            attributes["line_name_overrides"] = self._stop_config["line_names"]
        
        return attributes

    @property
    def available(self) -> bool:
        """Return True if entity is available, considering both fresh and cached data."""
        # Entity is available if we have any data (fresh or cached)
        if self.coordinator.data and self._stop_code in self.coordinator.data:
            return True
        
        # Also consider available if we had recent success, even without current data
        if self.coordinator.last_update_success:
            return True
        
        # Check if we have cached data available
        if (hasattr(self.coordinator, 'cache') and 
            self.coordinator.cache and 
            hasattr(self.coordinator, '_has_any_cached_data')):
            try:
                # This is an async method, so we can't call it directly
                # But the coordinator should have already checked this
                pass
            except Exception:
                pass
        
        # Consider unavailable only if we have no data and significant failures
        if (hasattr(self.coordinator, 'consecutive_failures') and 
            self.coordinator.consecutive_failures > 5):
            return False
        
        # Default to available to prevent sensors from going unavailable too quickly
        return True

    @property
    def device_info(self) -> dict[str, Any]:
        """Return device information about this sensor."""
        return {
            "identifiers": {(DOMAIN, self._stop_code)},
            "name": self._stop_name,
            "manufacturer": "511.org",
            "model": "Transit Stop",
            "sw_version": "2.0.0",  # Updated version to reflect enhanced features
        }
    
    @property
    def icon(self) -> str:
        """Return the icon for the sensor based on connection status."""
        # Change icon based on data source and connection status
        if not self.coordinator.data or self._stop_code not in self.coordinator.data:
            if hasattr(self.coordinator, 'consecutive_failures') and self.coordinator.consecutive_failures > 0:
                return "mdi:bus-alert"  # Error state
            return "mdi:bus-off"  # No data
        
        stop_data = self.coordinator.data[self._stop_code]
        from_cache = stop_data.get("from_cache", False)
        arrivals = stop_data.get("arrivals", [])
        
        if from_cache:
            if arrivals:
                return "mdi:bus-clock"  # Cached data with arrivals
            else:
                return "mdi:bus-off"  # Cached data but no arrivals
        else:
            if arrivals:
                return "mdi:bus"  # Fresh data with arrivals
            else:
                return "mdi:bus-stop"  # Fresh data but no arrivals
    
    @property
    def entity_picture(self) -> str | None:
        """Return entity picture if needed."""
        # Could be used to show different pictures based on transit type
        return None
    
    @property
    def should_poll(self) -> bool:
        """Return False as we use coordinator for updates."""
        return False