"""Config flow for Muni Times integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .const import (
    CONF_AGENCY,
    CONF_API_KEY,
    CONF_CACHE_DURATION,
    CONF_CACHE_ENABLED,
    CONF_CACHE_MAX_SIZE,
    CONF_MAX_RESULTS,
    CONF_REQUEST_TIMEOUT,
    CONF_RETRY_DELAY,
    CONF_RETRY_MAX_ATTEMPTS,
    CONF_SHOW_LINE_ICONS,
    CONF_STOPS,
    CONF_TIME_FORMAT,
    CONF_TIME_ZONE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AGENCY,
    DEFAULT_CACHE_DURATION,
    DEFAULT_CACHE_ENABLED,
    DEFAULT_CACHE_MAX_SIZE,
    DEFAULT_MAX_RESULTS,
    DEFAULT_REQUEST_TIMEOUT,
    DEFAULT_RETRY_DELAY,
    DEFAULT_RETRY_MAX_ATTEMPTS,
    DEFAULT_SHOW_LINE_ICONS,
    DEFAULT_TIME_FORMAT,
    DEFAULT_TIME_ZONE,
    DEFAULT_UPDATE_INTERVAL,
    DOMAIN,
    TIME_FORMAT_FULL,
    TIME_FORMAT_MINUTES,
    TIME_FORMAT_VERBOSE,
)
from .muni_api import MuniAPI

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_API_KEY): str,
        vol.Optional(CONF_AGENCY, default=DEFAULT_AGENCY): str,
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            int, vol.Range(min=30, max=3600)
        ),
        vol.Optional(CONF_MAX_RESULTS, default=DEFAULT_MAX_RESULTS): vol.All(
            int, vol.Range(min=1, max=10)
        ),
        vol.Optional(CONF_SHOW_LINE_ICONS, default=DEFAULT_SHOW_LINE_ICONS): bool,
        vol.Optional(CONF_TIME_FORMAT, default=DEFAULT_TIME_FORMAT): vol.In([
            TIME_FORMAT_MINUTES,
            TIME_FORMAT_VERBOSE,
            TIME_FORMAT_FULL
        ]),
        vol.Optional(CONF_TIME_ZONE, default=DEFAULT_TIME_ZONE): str,
    }
)

STEP_OPTIONS_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): vol.All(
            int, vol.Range(min=30, max=3600)
        ),
        vol.Optional(CONF_MAX_RESULTS, default=DEFAULT_MAX_RESULTS): vol.All(
            int, vol.Range(min=1, max=10)
        ),
        vol.Optional(CONF_SHOW_LINE_ICONS, default=DEFAULT_SHOW_LINE_ICONS): bool,
        vol.Optional(CONF_TIME_FORMAT, default=DEFAULT_TIME_FORMAT): vol.In([
            TIME_FORMAT_MINUTES,
            TIME_FORMAT_VERBOSE,
            TIME_FORMAT_FULL
        ]),
        vol.Optional(CONF_TIME_ZONE, default=DEFAULT_TIME_ZONE): str,
        vol.Optional(CONF_CACHE_ENABLED, default=DEFAULT_CACHE_ENABLED): bool,
        vol.Optional(CONF_CACHE_DURATION, default=DEFAULT_CACHE_DURATION): vol.All(
            int, vol.Range(min=5, max=180)
        ),
        vol.Optional(CONF_CACHE_MAX_SIZE, default=DEFAULT_CACHE_MAX_SIZE): vol.All(
            int, vol.Range(min=1, max=100)
        ),
        vol.Optional(CONF_RETRY_MAX_ATTEMPTS, default=DEFAULT_RETRY_MAX_ATTEMPTS): vol.All(
            int, vol.Range(min=1, max=10)
        ),
        vol.Optional(CONF_RETRY_DELAY, default=DEFAULT_RETRY_DELAY): vol.All(
            vol.Coerce(float), vol.Range(min=0.5, max=10.0)
        ),
        vol.Optional(CONF_REQUEST_TIMEOUT, default=DEFAULT_REQUEST_TIMEOUT): vol.All(
            int, vol.Range(min=10, max=120)
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    
    # Extract API configuration
    api_key = data[CONF_API_KEY]
    agency = data.get(CONF_AGENCY, DEFAULT_AGENCY)
    max_retries = data.get(CONF_RETRY_MAX_ATTEMPTS, DEFAULT_RETRY_MAX_ATTEMPTS)
    retry_delay = data.get(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY)
    request_timeout = data.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)
    
    api = MuniAPI(
        api_key=api_key,
        agency=agency,
        max_retries=max_retries,
        retry_delay=retry_delay,
        request_timeout=request_timeout,
    )
    
    try:
        # Try to make a test API call to validate the key
        # Using a known SF Muni stop code for testing
        test_data = await api.get_arrivals("13543")  # A real SF Muni stop
        await api.close()
        
        # Return info that we want to store in the config entry
        return {"title": f"Muni Times ({agency})"}
        
    except Exception as e:
        await api.close()
        _LOGGER.error("API validation failed: %s", e)
        raise InvalidAuth from e


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Muni Times."""

    VERSION = 1

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry):
        """Get options flow."""
        return OptionsFlow(config_entry)

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
                # Add default values for new configuration options
                user_input.setdefault(CONF_CACHE_ENABLED, DEFAULT_CACHE_ENABLED)
                user_input.setdefault(CONF_CACHE_DURATION, DEFAULT_CACHE_DURATION)
                user_input.setdefault(CONF_CACHE_MAX_SIZE, DEFAULT_CACHE_MAX_SIZE)
                user_input.setdefault(CONF_RETRY_MAX_ATTEMPTS, DEFAULT_RETRY_MAX_ATTEMPTS)
                user_input.setdefault(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY)
                user_input.setdefault(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)
                
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Add empty stops array - user will configure stops later
                user_input[CONF_STOPS] = []
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_DATA_SCHEMA, errors=errors
        )


class OptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Muni Times."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Manage the options."""
        if user_input is not None:
            # Update the config entry with new options
            return self.async_create_entry(title="", data=user_input)

        # Get current configuration values
        current_config = dict(self.config_entry.data)
        
        # Create schema with current values as defaults
        options_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_UPDATE_INTERVAL,
                    default=current_config.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL)
                ): vol.All(int, vol.Range(min=30, max=3600)),
                vol.Optional(
                    CONF_MAX_RESULTS,
                    default=current_config.get(CONF_MAX_RESULTS, DEFAULT_MAX_RESULTS)
                ): vol.All(int, vol.Range(min=1, max=10)),
                vol.Optional(
                    CONF_SHOW_LINE_ICONS,
                    default=current_config.get(CONF_SHOW_LINE_ICONS, DEFAULT_SHOW_LINE_ICONS)
                ): bool,
                vol.Optional(
                    CONF_TIME_FORMAT,
                    default=current_config.get(CONF_TIME_FORMAT, DEFAULT_TIME_FORMAT)
                ): vol.In([TIME_FORMAT_MINUTES, TIME_FORMAT_VERBOSE, TIME_FORMAT_FULL]),
                vol.Optional(
                    CONF_TIME_ZONE,
                    default=current_config.get(CONF_TIME_ZONE, DEFAULT_TIME_ZONE)
                ): str,
                vol.Optional(
                    CONF_CACHE_ENABLED,
                    default=current_config.get(CONF_CACHE_ENABLED, DEFAULT_CACHE_ENABLED)
                ): bool,
                vol.Optional(
                    CONF_CACHE_DURATION,
                    default=current_config.get(CONF_CACHE_DURATION, DEFAULT_CACHE_DURATION)
                ): vol.All(int, vol.Range(min=5, max=180)),
                vol.Optional(
                    CONF_CACHE_MAX_SIZE,
                    default=current_config.get(CONF_CACHE_MAX_SIZE, DEFAULT_CACHE_MAX_SIZE)
                ): vol.All(int, vol.Range(min=1, max=100)),
                vol.Optional(
                    CONF_RETRY_MAX_ATTEMPTS,
                    default=current_config.get(CONF_RETRY_MAX_ATTEMPTS, DEFAULT_RETRY_MAX_ATTEMPTS)
                ): vol.All(int, vol.Range(min=1, max=10)),
                vol.Optional(
                    CONF_RETRY_DELAY,
                    default=current_config.get(CONF_RETRY_DELAY, DEFAULT_RETRY_DELAY)
                ): vol.All(vol.Coerce(float), vol.Range(min=0.5, max=10.0)),
                vol.Optional(
                    CONF_REQUEST_TIMEOUT,
                    default=current_config.get(CONF_REQUEST_TIMEOUT, DEFAULT_REQUEST_TIMEOUT)
                ): vol.All(int, vol.Range(min=10, max=120)),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
            description_placeholders={
                "cache_note": "Caching helps provide data during API outages",
                "retry_note": "Higher retry counts may slow down updates during network issues",
                "timeout_note": "Longer timeouts may help with slow connections",
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""