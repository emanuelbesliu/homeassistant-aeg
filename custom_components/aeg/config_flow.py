"""Config flow for AEG (Electrolux OCP) integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult
from homeassistant.exceptions import HomeAssistantError

from .api import OcpApi, OcpAuthError, OcpConnectionError
from .const import (
    BRAND_AEG,
    BRAND_ELECTROLUX,
    CONF_BRAND,
    CONF_COUNTRY_CODE,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
        vol.Required(CONF_BRAND, default=BRAND_AEG): vol.In(
            [BRAND_AEG, BRAND_ELECTROLUX]
        ),
        vol.Required(CONF_COUNTRY_CODE, default="RO"): str,
    }
)


async def validate_input(
    hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input by attempting authentication.

    Args:
        hass: Home Assistant instance.
        data: User-provided configuration data.

    Returns:
        Dict with "title" key for the config entry.

    Raises:
        InvalidAuth: If credentials are invalid.
        CannotConnect: If connection fails.
    """
    api = OcpApi(
        username=data[CONF_USERNAME],
        password=data[CONF_PASSWORD],
        country_code=data[CONF_COUNTRY_CODE],
        brand=data[CONF_BRAND],
    )

    try:
        await api.async_init()
        await api.authenticate()
    except OcpAuthError as err:
        raise InvalidAuth(str(err)) from err
    except OcpConnectionError as err:
        raise CannotConnect(str(err)) from err
    except Exception as err:
        _LOGGER.exception("Unexpected error during validation")
        raise CannotConnect(str(err)) from err
    finally:
        await api.async_close()

    brand = data[CONF_BRAND]
    username = data[CONF_USERNAME]
    return {"title": f"{brand} - {username}"}


class AegConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for AEG."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle the initial step - user enters credentials.

        Args:
            user_input: User-provided form data.

        Returns:
            FlowResult showing form or creating entry.
        """
        errors: dict[str, str] = {}

        if user_input is not None:
            try:
                info = await validate_input(self.hass, user_input)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            else:
                # Use username + brand as unique ID
                unique_id = (
                    f"{user_input[CONF_USERNAME]}_{user_input[CONF_BRAND]}"
                )
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()

                return self.async_create_entry(
                    title=info["title"], data=user_input
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> FlowResult:
        """Handle reauth when credentials expire.

        Args:
            entry_data: Existing config entry data.

        Returns:
            FlowResult delegating to reauth_confirm step.
        """
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        """Handle reauth confirmation - user enters new password.

        Args:
            user_input: User-provided form data (password only).

        Returns:
            FlowResult showing form or updating entry.
        """
        errors: dict[str, str] = {}

        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            # Combine existing data with new password
            combined_data = {**reauth_entry.data, **user_input}

            try:
                await validate_input(self.hass, combined_data)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except Exception:
                _LOGGER.exception("Unexpected exception during reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry, data=combined_data
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "username": reauth_entry.data.get(CONF_USERNAME, ""),
            },
        )


class CannotConnect(HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(HomeAssistantError):
    """Error to indicate there is invalid auth."""
