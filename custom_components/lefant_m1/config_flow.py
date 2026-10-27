"""Config flow for Lefant M1 integration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import (
    CONF_DEVICE_ID,
    CONF_LOCAL_KEY,
    CONF_PROTOCOL,
    DEFAULT_PROTOCOL,
    DOMAIN,
    SUPPORTED_PROTOCOLS,
)
from .tuya_lan_adapter import TinytuyaClient, TuyaLanAuthError, TuyaLanConnectionError

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_DEVICE_ID): str,
        vol.Required(CONF_LOCAL_KEY): str,
        vol.Optional(CONF_PROTOCOL, default=DEFAULT_PROTOCOL): vol.In(
            list(SUPPORTED_PROTOCOLS)
        ),
    }
)


async def validate_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    """Validate that we can connect to the robot and read its datapoints."""
    host = data[CONF_HOST].strip()
    device_id = data[CONF_DEVICE_ID].strip()
    local_key = data[CONF_LOCAL_KEY].strip()
    version = float(data.get(CONF_PROTOCOL, DEFAULT_PROTOCOL))

    client = TinytuyaClient(
        host=host,
        device_id=device_id,
        local_key=local_key,
        version=version,
    )
    try:
        await client.connect()
        await client.query_dps()
    finally:
        client.close()

    return {"title": f"Lefant M1 ({device_id[-4:] if len(device_id) >= 4 else device_id})"}


class LefantM1ConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Lefant M1."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial user step."""
        errors: dict[str, str] = {}

        if user_input is not None:
            device_id = user_input[CONF_DEVICE_ID].strip()
            await self.async_set_unique_id(device_id)
            self._abort_if_unique_id_configured()

            try:
                info = await validate_input(self.hass, user_input)
            except TuyaLanAuthError:
                errors["base"] = "invalid_auth"
            except (TuyaLanConnectionError, ConnectionError, OSError, asyncio.TimeoutError):
                errors["base"] = "cannot_connect"
            except Exception:  # pylint: disable=broad-except
                _LOGGER.exception("Unexpected exception during Lefant M1 setup")
                errors["base"] = "unknown"
            else:
                return self.async_create_entry(title=info["title"], data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )
