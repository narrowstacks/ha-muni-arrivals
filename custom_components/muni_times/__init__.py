"""The Muni Times integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cache import MuniTimesCache
from .const import (
    CONF_AGENCY,
    CONF_API_KEY,
    CONF_CACHE_DURATION,
    CONF_CACHE_ENABLED,
    CONF_CACHE_MAX_SIZE,
    CONF_REQUEST_TIMEOUT,
    CONF_RETRY_DELAY,
    CONF_RETRY_MAX_ATTEMPTS,
    CONF_STOPS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AGENCY,
    DEFAULT_CACHE_DURATION,
    DEFAULT_CACHE_ENABLED,
    DEFAULT_CACHE_MAX_SIZE,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_RETRY_DELAY,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    SERVICE_CLEAR_CACHE,
    SERVICE_GET_DIAGNOSTICS,
    SERVICE_REFRESH_DATA,
    SERVICE_RESET_ERROR_COUNT,
    SERVICE_TEST_CONNECTION,
)
from .exceptions import MuniAPIError, MuniCacheError
from .muni_api import MuniAPI

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Muni Times from a config entry."""
    
    # Extract configuration
    api_key = entry.data[CONF_API_KEY]
    stops = entry.data.get(CONF_STOPS, [])
    agency = entry.data.get(CONF_AGENCY, DEFAULT_AGENCY)
    update_interval = entry.data.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
    
    # Cache configuration
    cache_enabled = entry.data.get(CONF_CACHE_ENABLED, DEFAULT_CACHE_ENABLED)
    cache_duration = entry.data.get(CONF_CACHE_DURATION, DEFAULT_CACHE_DURATION)
    cache_max_size = entry.data.get(CONF_CACHE_MAX_SIZE, DEFAULT_CACHE_MAX_SIZE)
    
    # API configuration
    max_retries = entry.data.get(CONF_RETRY_MAX_ATTEMPTS, DEFAULT_RETRY_MAX_ATTEMPTS)
    retry_delay = entry.data.get(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY)
    request_timeout = entry.data.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)
    
    # Initialize API client with configuration
    api = MuniAPI(
        api_key=api_key,
        agency=agency,
        max_retries=max_retries,
        retry_delay=retry_delay,
        request_timeout=request_timeout,
    )
    
    # Initialize cache if enabled
    cache = None
    if cache_enabled:
        try:
            cache = MuniTimesCache(
                hass=hass,
                cache_duration_minutes=cache_duration,
                max_cache_size_mb=cache_max_size,
            )
            _LOGGER.info("Cache enabled with %d minute duration", cache_duration)
        except Exception as e:
            _LOGGER.warning("Failed to initialize cache: %s", e)
    
    # Initialize coordinator
    coordinator = MuniTimesDataUpdateCoordinator(
        hass,
        api=api,
        stops=stops,
        cache=cache,
        update_interval=timedelta(seconds=update_interval),
        entry=entry,
    )

    try:
        await coordinator.async_config_entry_first_refresh()
    except UpdateFailed as e:
        _LOGGER.error("Failed to initialize integration: %s", e)
        # Don't fail setup if we have cache data
        if cache and await coordinator._has_any_cached_data():
            _LOGGER.info("Using cached data due to API failure during setup")
        else:
            raise

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    # Register services
    await _async_register_services(hass)

    # Set up platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    
    _LOGGER.info("Successfully set up Muni Times integration")
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    if unload_ok := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        coordinator = hass.data[DOMAIN].pop(entry.entry_id)
        
        # Clean up resources
        await coordinator.async_cleanup()

    return unload_ok


class MuniTimesDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from the API with caching and error handling."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: MuniAPI,
        stops: list[dict],
        cache: MuniTimesCache | None,
        update_interval: timedelta,
        entry: ConfigEntry,
    ) -> None:
        """Initialize with enhanced error handling and caching."""
        self.api = api
        self.stops = stops
        self.cache = cache
        self.entry = entry
        
        # Error tracking
        self.consecutive_failures = 0
        self.last_successful_update = None
        self.error_history: list[str] = []
        self.max_error_history = 10
        
        # Cache statistics
        self.cache_hits = 0
        self.cache_misses = 0
        
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
        )

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data via API with caching fallback."""
        data = {}
        api_errors = []
        cache_used = False
        
        for stop in self.stops:
            stop_code = stop.get("stop_code")
            if not stop_code:
                continue
            
            try:
                # Try to fetch fresh data from API
                stop_data = await self.api.get_arrivals(stop_code)
                
                # Cache the successful result
                if self.cache:
                    try:
                        await self.cache.cache_data(stop_code, {
                            "arrivals": stop_data,
                            "config": stop
                        })
                    except MuniCacheError as e:
                        _LOGGER.warning("Failed to cache data for stop %s: %s", stop_code, e)
                
                data[stop_code] = {
                    "arrivals": stop_data,
                    "config": stop,
                    "from_cache": False,
                    "last_updated": datetime.now(),
                }
                
                _LOGGER.debug("Fresh data retrieved for stop %s", stop_code)
                
            except MuniAPIError as e:
                api_errors.append(f"Stop {stop_code}: {e}")
                
                # Try to use cached data as fallback
                if self.cache:
                    try:
                        cached_data = await self.cache.get_cached_data(stop_code)
                        if cached_data:
                            data[stop_code] = {
                                "arrivals": cached_data.get("arrivals", []),
                                "config": cached_data.get("config", stop),
                                "from_cache": True,
                                "cached_at": cached_data.get("cached_at"),
                                "cache_age_minutes": cached_data.get("cache_age_minutes", 0),
                            }
                            cache_used = True
                            self.cache_hits += 1
                            
                            _LOGGER.info(
                                "Using cached data for stop %s (age: %.1f minutes)",
                                stop_code, cached_data.get("cache_age_minutes", 0)
                            )
                        else:
                            self.cache_misses += 1
                            _LOGGER.warning("No cached data available for stop %s", stop_code)
                    except MuniCacheError as cache_error:
                        _LOGGER.error("Cache error for stop %s: %s", stop_code, cache_error)
                        self.cache_misses += 1
                else:
                    _LOGGER.warning("No cache available for stop %s during API failure", stop_code)
        
        # Handle the case where we have some data (fresh or cached)
        if data:
            if api_errors:
                if cache_used:
                    # We have some cached data, so this is a partial success
                    _LOGGER.warning(
                        "API errors for some stops, using cached data: %s",
                        "; ".join(api_errors)
                    )
                    self.consecutive_failures = 0  # Reset because we have data
                else:
                    # We have fresh data for some stops but errors for others
                    _LOGGER.warning("Partial API failure: %s", "; ".join(api_errors))
                    self.consecutive_failures = 0  # Reset because we have some fresh data
            else:
                # Complete success
                self.consecutive_failures = 0
                self.last_successful_update = datetime.now()
            
            return data
        
        # No data at all - complete failure
        self.consecutive_failures += 1
        error_message = f"Failed to get data for all stops: {'; '.join(api_errors)}"
        
        # Track error history
        self.error_history.append(error_message)
        if len(self.error_history) > self.max_error_history:
            self.error_history.pop(0)
        
        _LOGGER.error("Complete update failure (consecutive failures: %d): %s", 
                     self.consecutive_failures, error_message)
        
        raise UpdateFailed(error_message)

    async def _has_any_cached_data(self) -> bool:
        """Check if we have cached data for any stops."""
        if not self.cache:
            return False
        
        for stop in self.stops:
            stop_code = stop.get("stop_code")
            if stop_code and await self.cache.has_cached_data(stop_code):
                return True
        
        return False

    async def async_refresh_data(self, stop_code: str | None = None) -> None:
        """Manually refresh data for all stops or a specific stop."""
        if stop_code:
            _LOGGER.info("Manual refresh requested for stop %s", stop_code)
            # Find the stop configuration
            stop_config = None
            for stop in self.stops:
                if stop.get("stop_code") == stop_code:
                    stop_config = stop
                    break
            
            if not stop_config:
                raise ValueError(f"Stop {stop_code} not found in configuration")
            
            # Refresh just this stop
            try:
                stop_data = await self.api.get_arrivals(stop_code)
                
                # Update the data
                if self.data is None:
                    self.data = {}
                
                self.data[stop_code] = {
                    "arrivals": stop_data,
                    "config": stop_config,
                    "from_cache": False,
                    "last_updated": datetime.now(),
                }
                
                # Cache the result
                if self.cache:
                    await self.cache.cache_data(stop_code, {
                        "arrivals": stop_data,
                        "config": stop_config
                    })
                
                _LOGGER.info("Successfully refreshed data for stop %s", stop_code)
                
            except MuniAPIError as e:
                _LOGGER.error("Failed to refresh data for stop %s: %s", stop_code, e)
                raise
        else:
            _LOGGER.info("Manual refresh requested for all stops")
            await self.async_request_refresh()

    async def async_clear_cache(self, stop_code: str | None = None) -> None:
        """Clear cache for all stops or a specific stop."""
        if not self.cache:
            _LOGGER.warning("Cache is not enabled")
            return
        
        try:
            await self.cache.clear_cache(stop_code)
            if stop_code:
                _LOGGER.info("Cache cleared for stop %s", stop_code)
            else:
                _LOGGER.info("All cache cleared")
        except MuniCacheError as e:
            _LOGGER.error("Failed to clear cache: %s", e)
            raise

    async def async_test_connection(self, test_stop_code: str | None = None) -> bool:
        """Test the API connection."""
        if test_stop_code is None and self.stops:
            test_stop_code = self.stops[0].get("stop_code")
        
        if not test_stop_code:
            _LOGGER.error("No stop code available for connection test")
            return False
        
        return await self.api.test_connection(test_stop_code)

    def reset_error_count(self) -> None:
        """Reset error counters and health monitoring."""
        self.consecutive_failures = 0
        self.error_history.clear()
        self.api.reset_health_monitoring()
        _LOGGER.info("Error counters and health monitoring reset")

    def get_diagnostics_data(self) -> dict[str, Any]:
        """Get diagnostic data for troubleshooting."""
        api_health = self.api.get_health_status()
        
        diagnostics = {
            "coordinator": {
                "consecutive_failures": self.consecutive_failures,
                "last_successful_update": (
                    self.last_successful_update.isoformat()
                    if self.last_successful_update else None
                ),
                "error_history": self.error_history.copy(),
                "cache_hits": self.cache_hits,
                "cache_misses": self.cache_misses,
                "stops_configured": len(self.stops),
            },
            "api_health": api_health,
            "cache_info": self.cache.get_cache_info() if self.cache else None,
        }
        
        return diagnostics

    async def async_cleanup(self) -> None:
        """Clean up resources."""
        try:
            # Close API client
            await self.api.close()
            
            # Clean up cache
            if self.cache:
                await self.cache.cleanup()
            
            _LOGGER.debug("Coordinator cleanup completed")
            
        except Exception as e:
            _LOGGER.warning("Error during coordinator cleanup: %s", e)


async def _async_register_services(hass: HomeAssistant) -> None:
    """Register services for the integration."""
    
    async def refresh_data_service(call: ServiceCall) -> None:
        """Handle refresh data service call."""
        stop_code = call.data.get("stop_code")
        
        # Find the coordinator for the service call
        # If no specific entry is provided, refresh all
        coordinators = []
        for entry_id, coordinator in hass.data[DOMAIN].items():
            coordinators.append(coordinator)
        
        if not coordinators:
            _LOGGER.error("No coordinators available for refresh")
            return
        
        # Refresh data for all coordinators
        for coordinator in coordinators:
            try:
                await coordinator.async_refresh_data(stop_code)
            except Exception as e:
                _LOGGER.error("Failed to refresh data: %s", e)

    async def clear_cache_service(call: ServiceCall) -> None:
        """Handle clear cache service call."""
        stop_code = call.data.get("stop_code")
        
        coordinators = []
        for entry_id, coordinator in hass.data[DOMAIN].items():
            coordinators.append(coordinator)
        
        for coordinator in coordinators:
            try:
                await coordinator.async_clear_cache(stop_code)
            except Exception as e:
                _LOGGER.error("Failed to clear cache: %s", e)

    async def test_connection_service(call: ServiceCall) -> None:
        """Handle test connection service call."""
        test_stop_code = call.data.get("stop_code")
        
        coordinators = []
        for entry_id, coordinator in hass.data[DOMAIN].items():
            coordinators.append(coordinator)
        
        if not coordinators:
            _LOGGER.error("No coordinators available for connection test")
            return
        
        # Test connection for the first coordinator
        coordinator = coordinators[0]
        try:
            success = await coordinator.async_test_connection(test_stop_code)
            if success:
                _LOGGER.info("Connection test successful")
            else:
                _LOGGER.error("Connection test failed")
        except Exception as e:
            _LOGGER.error("Connection test error: %s", e)

    async def get_diagnostics_service(call: ServiceCall) -> None:
        """Handle get diagnostics service call."""
        include_cache = call.data.get("include_cache", True)
        include_api_status = call.data.get("include_api_status", True)
        
        coordinators = []
        for entry_id, coordinator in hass.data[DOMAIN].items():
            coordinators.append(coordinator)
        
        for coordinator in coordinators:
            try:
                diagnostics = coordinator.get_diagnostics_data()
                _LOGGER.info("Diagnostics: %s", diagnostics)
            except Exception as e:
                _LOGGER.error("Failed to get diagnostics: %s", e)

    async def reset_error_count_service(call: ServiceCall) -> None:
        """Handle reset error count service call."""
        coordinators = []
        for entry_id, coordinator in hass.data[DOMAIN].items():
            coordinators.append(coordinator)
        
        for coordinator in coordinators:
            try:
                coordinator.reset_error_count()
            except Exception as e:
                _LOGGER.error("Failed to reset error count: %s", e)

    # Register services
    hass.services.async_register(
        DOMAIN, SERVICE_REFRESH_DATA, refresh_data_service
    )
    hass.services.async_register(
        DOMAIN, SERVICE_CLEAR_CACHE, clear_cache_service
    )
    hass.services.async_register(
        DOMAIN, SERVICE_TEST_CONNECTION, test_connection_service
    )
    hass.services.async_register(
        DOMAIN, SERVICE_GET_DIAGNOSTICS, get_diagnostics_service
    )
    hass.services.async_register(
        DOMAIN, SERVICE_RESET_ERROR_COUNT, reset_error_count_service
    )
    
    _LOGGER.info("Registered integration services")