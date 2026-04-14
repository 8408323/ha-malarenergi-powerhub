"""Config flow for Mälarenergi PowerHub."""
from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import CONF_FLOW_URL, CONF_USERNAME, CONF_PASSWORD, DOMAIN

_LOGGER = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_FLOW_URL): str,
        vol.Required(CONF_USERNAME): str,
        vol.Required(CONF_PASSWORD): str,
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
            flow_url = user_input[CONF_FLOW_URL].strip().rstrip("/")
            username = user_input[CONF_USERNAME]
            password = user_input[CONF_PASSWORD]
            try:
                await self._test_connection(flow_url, username, password)
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"
            else:
                await self.async_set_unique_id(flow_url)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="Mälarenergi PowerHub",
                    data={
                        CONF_FLOW_URL: flow_url,
                        CONF_USERNAME: username,
                        CONF_PASSWORD: password,
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
        )

    async def _test_connection(self, flow_url: str, username: str, password: str) -> None:
        """Try to reach the Bitvis Flow API. Raises CannotConnect on failure."""
        session = async_get_clientsession(self.hass)
        auth = aiohttp.BasicAuth(username, password)
        # A lightweight probe — just check that the host responds
        probe_url = f"{flow_url}/"
        try:
            async with session.get(
                probe_url,
                auth=auth,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                # 200/401/403/404 all mean the server exists
                if resp.status < 500:
                    return
        except Exception:
            pass
        raise CannotConnect


class CannotConnect(Exception):
    """Error to indicate we cannot connect."""
