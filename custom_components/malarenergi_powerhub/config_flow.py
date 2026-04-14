"""Config flow for Mälarenergi PowerHub."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_HOST
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
    }
)


class PowerHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mälarenergi PowerHub."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                await self._test_connection(host)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"PowerHub ({host})",
                    data={CONF_HOST: host},
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, host: str) -> None:
        """Try to reach the device. Raises CannotConnect on failure."""
        session = async_get_clientsession(self.hass)
        # Try a simple ping-style check; actual endpoint TBD
        for path in ("/status", "/", "/data"):
            try:
                async with session.get(
                    f"http://{host}{path}",
                    timeout=aiohttp.ClientTimeout(total=5),
                ) as resp:
                    if resp.status < 500:
                        return
            except Exception:
                continue
        raise CannotConnect


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""
