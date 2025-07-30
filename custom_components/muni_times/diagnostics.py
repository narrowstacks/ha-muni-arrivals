"""Diagnostics support for Muni Times integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Get basic configuration info (sanitized)
    config_data = dict(config_entry.data)
    # Remove sensitive information
    if "api_key" in config_data:
        config_data["api_key"] = "***REDACTED***"
    
    diagnostics = {
        "config_entry": {
            "title": config_entry.title,
            "version": config_entry.version,
            "domain": config_entry.domain,
            "data": config_data,
            "options": dict(config_entry.options),
        },
        "coordinator": {
            "last_update_success": coordinator.last_update_success,
            "last_update_success_time": (
                coordinator.last_update_success.isoformat()
                if coordinator.last_update_success
                else None
            ),
            "update_interval": str(coordinator.update_interval),
            "stops_count": len(coordinator.stops),
        },
        "api_status": {},
        "cache_status": {},
        "stops": [],
    }
    
    # Add API status if available
    if hasattr(coordinator.api, "health_monitor"):
        diagnostics["api_status"] = coordinator.api.health_monitor.get_health_info()
    
    # Add rate limiter status if available  
    if hasattr(coordinator.api, "rate_limiter"):
        diagnostics["api_status"]["rate_limiter"] = {
            "current_rate": coordinator.api.rate_limiter.current_rate,
            "time_until_reset": coordinator.api.rate_limiter.time_until_reset,
            "max_requests": coordinator.api.rate_limiter.max_requests,
        }
    
    # Add cache status if available
    if hasattr(coordinator, "cache"):
        cache_info = coordinator.cache.get_cache_info()
        diagnostics["cache_status"] = cache_info
    
    # Add stop-specific information
    for stop in coordinator.stops:
        stop_code = stop.get("stop_code")
        if not stop_code:
            continue
            
        stop_info = {
            "stop_code": stop_code,
            "stop_name": stop.get("stop_name", "Unknown"),
            "direction": stop.get("direction"),
            "has_data": stop_code in (coordinator.data or {}),
            "data_timestamp": None,
            "arrival_count": 0,
            "line_count": 0,
        }
        
        # Add data information if available
        if coordinator.data and stop_code in coordinator.data:
            stop_data = coordinator.data[stop_code]
            arrivals = stop_data.get("arrivals", [])
            
            stop_info["arrival_count"] = len(arrivals)
            stop_info["line_count"] = len(set(
                arrival.get("line_ref", "") for arrival in arrivals
            ))
            
            # Get timestamp from first arrival if available
            if arrivals and arrivals[0].get("times"):
                first_time = arrivals[0]["times"][0]
                stop_info["data_timestamp"] = first_time.get("arrival_time")
        
        diagnostics["stops"].append(stop_info)
    
    return diagnostics


async def async_get_device_diagnostics(
    hass: HomeAssistant, config_entry: ConfigEntry, device
) -> dict[str, Any]:
    """Return diagnostics for a device."""
    # Extract stop code from device identifiers
    stop_code = None
    for identifier in device.identifiers:
        if identifier[0] == DOMAIN:
            stop_code = identifier[1]
            break
    
    if not stop_code:
        return {"error": "Could not determine stop code from device"}
    
    coordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    # Find the stop configuration
    stop_config = None
    for stop in coordinator.stops:
        if stop.get("stop_code") == stop_code:
            stop_config = stop
            break
    
    diagnostics = {
        "device": {
            "name": device.name,
            "model": device.model,
            "manufacturer": device.manufacturer,
            "sw_version": device.sw_version,
            "identifiers": list(device.identifiers),
        },
        "stop_code": stop_code,
        "stop_config": stop_config,
        "current_data": {},
        "cached_data": {},
        "sensor_entities": [],
    }
    
    # Add current data if available
    if coordinator.data and stop_code in coordinator.data:
        stop_data = coordinator.data[stop_code]
        diagnostics["current_data"] = {
            "arrivals_count": len(stop_data.get("arrivals", [])),
            "last_updated": coordinator.last_update_success.isoformat() if coordinator.last_update_success else None,
            "arrivals": stop_data.get("arrivals", []),
        }
    
    # Add cached data if available
    if hasattr(coordinator, "cache"):
        try:
            cached_data = await coordinator.cache.get_cached_data(stop_code)
            if cached_data:
                diagnostics["cached_data"] = {
                    "has_cache": True,
                    "cached_at": cached_data.get("cached_at"),
                    "arrivals_count": len(cached_data.get("arrivals", [])),
                }
            else:
                diagnostics["cached_data"] = {"has_cache": False}
        except Exception as e:
            diagnostics["cached_data"] = {"error": str(e)}
    
    # Find related sensor entities
    device_registry = hass.helpers.device_registry.async_get(hass)
    entity_registry = hass.helpers.entity_registry.async_get(hass)
    
    entities = hass.helpers.entity_registry.async_entries_for_device(
        entity_registry, device.id
    )
    
    for entity in entities:
        entity_info = {
            "entity_id": entity.entity_id,
            "name": entity.name or entity.original_name,
            "platform": entity.platform,
            "disabled": entity.disabled_by is not None,
        }
        
        # Add current state if entity exists
        state = hass.states.get(entity.entity_id)
        if state:
            entity_info["state"] = state.state
            entity_info["available"] = state.state not in ["unavailable", "unknown"]
            entity_info["attributes_count"] = len(state.attributes)
        
        diagnostics["sensor_entities"].append(entity_info)
    
    return diagnostics