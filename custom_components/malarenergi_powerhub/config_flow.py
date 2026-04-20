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
        self._poll_task: asyncio.Task | None = None

    def _cancel_task(self) -> None:
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
        self._poll_task = None

    async def async_remove(self) -> None:
        """Cancel background polling when the flow is discarded."""
        self._cancel_task()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Start BankID session, fetch first QR synchronously, then poll in bg."""
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

        # Fetch first QR synchronously so it's ready when the form renders
        try:
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
        except Exception as err:
            _LOGGER.error("BankID first poll failed: %s", err)
            return self.async_show_form(
                step_id="user",
                errors={"base": "cannot_connect"},
            )

        # Start background task to keep polling and refreshing _qr_code
        self._poll_task = self.hass.async_create_task(self._run_poller())

        return self._show_qr_form()

    async def _run_poller(self) -> None:
        """Background: keep polling BankID, store latest QR / token / failed."""
        session = async_get_clientsession(self.hass)
        assert self._transaction_id is not None
        try:
            async for status, qr, token in bankid_poll(session, self._transaction_id):
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
        """Called when user clicks Submit — check status and show refreshed QR."""
        # Guard: if transaction is missing (e.g. flow resumed after HA restart),
        # restart from the beginning so we get a fresh BankID session.
        if not self._transaction_id or not self._poll_task:
            return await self.async_step_user()

        if self._token:
            self._cancel_task()
            return await self._async_finish(self._token)

        if self._failed:
            self._cancel_task()
            return await self.async_step_user()

        if self._poll_task.done():
            return await self.async_step_user()

        # Return updated QR (background task keeps _qr_code fresh)
        return self._show_qr_form()

    async def _async_finish(self, token: str) -> config_entries.FlowResult:
        """Complete the flow after successful BankID login.

        For a fresh install: create a new config entry.
        For a reauth: update the existing entry's token, reload, and abort with
        reason="reauth_successful" so HA dismisses the "re-auth required"
        notification.
        """
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

        # Reauth path — update existing entry in place. Preserve the
        # entry's original facility_id; only refresh the token. If we can't
        # unambiguously identify which entry is being reauthed, abort with a
        # reauth-specific reason rather than falling through to create_entry
        # (which would mutate unrelated configuration).
        if self.source == config_entries.SOURCE_REAUTH:
            entry_id = self.context.get("entry_id")
            existing = (
                self.hass.config_entries.async_get_entry(entry_id)
                if entry_id
                else None
            )
            # Fallback: locate the entry by unique_id against the returned
            # facilities. Require exactly one match — more than one means we
            # cannot safely choose which entry to update.
            if existing is None:
                candidates = [
                    e
                    for e in self.hass.config_entries.async_entries(DOMAIN)
                    if e.unique_id
                    and any(f.facility_id == e.unique_id for f in facilities)
                ]
                if len(candidates) == 1:
                    existing = candidates[0]
                elif len(candidates) > 1:
                    return self.async_abort(reason="reauth_ambiguous")

            if existing is None:
                # No entry identifiable as the reauth target — abort instead
                # of silently creating a new entry.
                return self.async_abort(reason="reauth_unresolved")

            # Sanity-check: the entry's facility must still be one the
            # just-authenticated account can see. If not, the user likely
            # logged in with a different BankID identity — abort rather
            # than silently retargeting.
            existing_facility_id = existing.data.get(CONF_FACILITY_ID)
            if not any(
                f.facility_id == existing_facility_id for f in facilities
            ):
                return self.async_abort(reason="reauth_wrong_account")
            self.hass.config_entries.async_update_entry(
                existing,
                data={**existing.data, CONF_TOKEN: token},
            )
            # Same account owns the token — push the refreshed token to
            # every sibling entry for this account too. Otherwise each
            # additional facility would need its own reauth flow when
            # the token expires (they all share one JWT).
            account_facility_ids = {f.facility_id for f in facilities}
            for sibling in self.hass.config_entries.async_entries(DOMAIN):
                if (
                    sibling.entry_id != existing.entry_id
                    and sibling.unique_id
                    and sibling.unique_id in account_facility_ids
                    and sibling.data.get(CONF_TOKEN) != token
                ):
                    self.hass.config_entries.async_update_entry(
                        sibling,
                        data={**sibling.data, CONF_TOKEN: token},
                    )
                    await self.hass.config_entries.async_reload(
                        sibling.entry_id
                    )
            await self.hass.config_entries.async_reload(existing.entry_id)
            return self.async_abort(reason="reauth_successful")

        # Fresh install path — create one entry per unconfigured facility.
        configured = {
            e.unique_id
            for e in self.hass.config_entries.async_entries(DOMAIN)
            if e.unique_id
        }
        new_facilities = [f for f in facilities if f.facility_id not in configured]

        if not new_facilities:
            return self.async_abort(reason="already_configured")

        # Schedule import flows for every facility after the first. Each
        # import flow runs independently and creates its own entry with the
        # shared token — no additional BankID login required.
        for facility in new_facilities[1:]:
            self.hass.async_create_task(
                self.hass.config_entries.flow.async_init(
                    DOMAIN,
                    context={"source": config_entries.SOURCE_IMPORT},
                    data={
                        CONF_TOKEN: token,
                        "facility_id": facility.facility_id,
                        "street": facility.street,
                        "house_number": facility.house_number,
                    },
                )
            )

        first = new_facilities[0]
        await self.async_set_unique_id(first.facility_id)
        self._abort_if_unique_id_configured(updates={CONF_TOKEN: token})
        return self.async_create_entry(
            title=f"{first.street} {first.house_number}",
            data={
                CONF_TOKEN: token,
                CONF_FACILITY_ID: first.facility_id,
            },
        )

    async def async_step_import(
        self, import_data: dict[str, Any]
    ) -> config_entries.FlowResult:
        """Create a config entry for an additional facility from a token
        that was already obtained in a sibling config flow. Skipped if the
        facility is already configured (race-safe)."""
        facility_id = import_data["facility_id"]
        await self.async_set_unique_id(facility_id)
        self._abort_if_unique_id_configured(
            updates={CONF_TOKEN: import_data[CONF_TOKEN]}
        )
        return self.async_create_entry(
            title=f"{import_data['street']} {import_data['house_number']}",
            data={
                CONF_TOKEN: import_data[CONF_TOKEN],
                CONF_FACILITY_ID: facility_id,
            },
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.FlowResult:
        """Re-authenticate when token expires."""
        return await self.async_step_user()
