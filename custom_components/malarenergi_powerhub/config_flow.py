"""Config flow for Mälarenergi PowerHub — BankID QR authentication."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import QrCodeSelector, QrCodeSelectorConfig

from .api import AuthError, bankid_poll, bankid_start
from .const import CONF_FACILITY_ID, CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)


class PowerHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """BankID QR config flow for Mälarenergi PowerHub."""

    VERSION = 1

    def __init__(self) -> None:
        self._transaction_id: str | None = None
        self._qr_code: str | None = None
        self._token: str | None = None
        self._failed: bool = False
        self._refresh_task: asyncio.Task | None = None

    def _cancel_task(self) -> None:
        if self._refresh_task and not self._refresh_task.done():
            self._refresh_task.cancel()
        self._refresh_task = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Start BankID session and begin polling."""
        self._cancel_task()
        self._token = None
        self._failed = False
        self._qr_code = None

        session = async_get_clientsession(self.hass)
        try:
            self._transaction_id, _ = await bankid_start(session)
        except Exception as err:
            _LOGGER.error("Failed to start BankID session: %s", err)
            return self.async_show_form(
                step_id="user",
                errors={"base": "cannot_connect"},
            )

        # Kick off background poller
        self._refresh_task = self.hass.async_create_task(
            self._run_poller(), eager_start=True
        )

        # Wait briefly for first QR
        await asyncio.sleep(0.1)

        return self._show_qr_form()

    async def _run_poller(self) -> None:
        """Background: poll BankID until complete/failed, storing latest QR."""
        session = async_get_clientsession(self.hass)
        try:
            async for status, qr, token in bankid_poll(
                session, self._transaction_id  # type: ignore[arg-type]
            ):
                if status == "pending" and qr:
                    self._qr_code = qr
                elif status == "complete" and token:
                    self._token = token
                    return
                elif status == "failed":
                    self._failed = True
                    return
        except asyncio.CancelledError:
            pass
        except Exception as err:
            _LOGGER.error("BankID polling error: %s", err)
            self._failed = True

    def _show_qr_form(self) -> config_entries.FlowResult:
        return self.async_show_form(
            step_id="bankid_qr",
            data_schema=vol.Schema({
                vol.Optional("qr"): QrCodeSelector(
                    QrCodeSelectorConfig(data=self._qr_code or "")
                ),
            }),
        )

    async def async_step_bankid_qr(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Called when user clicks Submit — check status and refresh QR."""
        if self._token:
            self._cancel_task()
            return await self._async_finish(self._token)

        if self._failed:
            self._cancel_task()
            return await self.async_step_user()

        # If poller has finished without token/failed flag, restart
        if self._refresh_task and self._refresh_task.done():
            return await self.async_step_user()

        # Return updated QR
        return self._show_qr_form()

    async def _async_finish(self, token: str) -> config_entries.FlowResult:
        """Create config entry after successful BankID login."""
        from .api import PowerHubApiClient
        session = async_get_clientsession(self.hass)
        client = PowerHubApiClient(session, token)
        try:
            facilities = await client.get_facilities()
        except AuthError:
            return self.async_show_form(
                step_id="user",
                errors={"base": "invalid_auth"},
            )
        except Exception as err:
            _LOGGER.error("Failed to fetch facilities: %s", err)
            return self.async_show_form(
                step_id="user",
                errors={"base": "cannot_connect"},
            )

        if not facilities:
            return self.async_show_form(
                step_id="user",
                errors={"base": "no_facilities"},
            )

        facility = facilities[0]
        await self.async_set_unique_id(facility.facility_id)
        self._abort_if_unique_id_configured(updates={CONF_TOKEN: token})

        return self.async_create_entry(
            title=f"{facility.street} {facility.house_number}",
            data={
                CONF_TOKEN: token,
                CONF_FACILITY_ID: facility.facility_id,
            },
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Re-authenticate when token expires."""
        return await self.async_step_user()
