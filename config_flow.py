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
    CONF_MAX_RESULTS,
    CONF_SHOW_LINE_ICONS,
    CONF_STOPS,
    CONF_TIME_FORMAT,
    CONF_TIME_ZONE,
    CONF_UPDATE_INTERVAL,
    DEFAULT_AGENCY,
    DEFAULT_MAX_RESULTS,
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
        vol.Optional(CONF_UPDATE_INTERVAL, default=DEFAULT_UPDATE_INTERVAL): int,
        vol.Optional(CONF_MAX_RESULTS, default=DEFAULT_MAX_RESULTS): int,
        vol.Optional(CONF_SHOW_LINE_ICONS, default=DEFAULT_SHOW_LINE_ICONS): bool,
        vol.Optional(CONF_TIME_FORMAT, default=DEFAULT_TIME_FORMAT): vol.In([
            TIME_FORMAT_MINUTES,
            TIME_FORMAT_VERBOSE,
            TIME_FORMAT_FULL
        ]),
        vol.Optional(CONF_TIME_ZONE, default=DEFAULT_TIME_ZONE): str,
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate the user input allows us to connect."""
    
    api = MuniAPI(data[CONF_API_KEY], data.get(CONF_AGENCY, DEFAULT_AGENCY))
    
    try:
        # Try to make a test API call to validate the key
        # Using a known SF Muni stop code for testing
        test_data = await api.get_arrivals("13543")  # A real SF Muni stop
        await api.close()
        
        # Return info that we want to store in the config entry
        return {"title": f"Muni Times ({data.get(CONF_AGENCY, DEFAULT_AGENCY)})"}
    except Exception as e:
        await api.close()
        raise InvalidAuth from e


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Muni Times."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        
        if user_input is not None:
            try:
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


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""