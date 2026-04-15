"""Config flow for Mälarenergi PowerHub — BankID QR authentication."""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
from typing import Any

from homeassistant import config_entries
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import AuthError, bankid_poll, bankid_start
from .const import CONF_FACILITY_ID, CONF_TOKEN, DOMAIN

_LOGGER = logging.getLogger(__name__)


def _write_qr_png(hass_config_path: str, qr_code: str) -> str:
    """Write a QR code PNG to the www dir and return the URL path."""
    try:
        import qrcode  # noqa: PLC0415
    except ImportError:
        return ""

    img = qrcode.make(qr_code)
    buf = io.BytesIO()
    img.save(buf, format="PNG")

    # Use a hash of the code as filename so each rotation gets a unique URL
    fname = hashlib.sha256(qr_code.encode()).hexdigest()[:16] + ".png"
    www_dir = os.path.join(hass_config_path, "custom_components", DOMAIN, "www")
    os.makedirs(www_dir, exist_ok=True)
    with open(os.path.join(www_dir, fname), "wb") as f:
        f.write(buf.getvalue())

    return f"/malarenergi_powerhub/{fname}"


def _qr_placeholders(hass_config_path: str, qr_code: str) -> dict:
    url = _write_qr_png(hass_config_path, qr_code)
    if url:
        return {
            "qr_code": qr_code,
            "qr_image": f"![]({url})",
        }
    return {"qr_code": qr_code, "qr_image": f"`{qr_code}`"}


class PowerHubConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """BankID QR config flow for Mälarenergi PowerHub."""

    VERSION = 1

    def __init__(self) -> None:
        self._transaction_id: str | None = None
        self._qr_code: str | None = None
        self._token: str | None = None
        self._poll_task: asyncio.Task | None = None

    def _ensure_static_path(self) -> None:
        """Register static path for QR images (idempotent)."""
        www_dir = self.hass.config.path("custom_components", DOMAIN, "www")
        os.makedirs(www_dir, exist_ok=True)
        try:
            self.hass.http.register_static_path(
                "/malarenergi_powerhub", www_dir, cache_headers=False
            )
        except RuntimeError:
            pass  # Already registered

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Show QR code and start BankID polling."""
        self._ensure_static_path()
        session = async_get_clientsession(self.hass)

        try:
            self._transaction_id, _ = await bankid_start(session)
        except Exception as err:
            _LOGGER.error("Failed to start BankID session: %s", err)
            return self.async_show_form(
                step_id="user",
                errors={"base": "cannot_connect"},
            )

        async for status, qr, token in bankid_poll(session, self._transaction_id):
            if status == "pending" and qr:
                self._qr_code = qr
                break
            if status == "complete" and token:
                return await self._async_finish(token)
            if status == "failed":
                return self.async_show_form(
                    step_id="user",
                    errors={"base": "bankid_failed"},
                )

        placeholders = await self.hass.async_add_executor_job(
            _qr_placeholders, self.hass.config.config_dir, self._qr_code or ""
        )
        return self.async_show_form(
            step_id="bankid_qr",
            description_placeholders=placeholders,
        )

    async def async_step_bankid_qr(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Poll BankID while user scans QR. Called when user clicks Submit."""
        if not self._transaction_id:
            return await self.async_step_user()

        session = async_get_clientsession(self.hass)

        async for status, qr, token in bankid_poll(session, self._transaction_id):
            if status == "pending" and qr:
                self._qr_code = qr
                placeholders = await self.hass.async_add_executor_job(
                    _qr_placeholders, self.hass.config.config_dir, qr
                )
                return self.async_show_form(
                    step_id="bankid_qr",
                    description_placeholders=placeholders,
                )
            if status == "complete" and token:
                return await self._async_finish(token)
            if status == "failed":
                return await self.async_step_user()

        return await self.async_step_user()

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
