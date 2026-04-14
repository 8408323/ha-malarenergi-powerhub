"""DataUpdateCoordinator for Mälarenergi PowerHub.

NOTE: The local API protocol is not yet fully reverse-engineered.
This coordinator contains placeholder logic that will be updated
as more information about the device's local endpoints becomes available.

See docs/reverse_engineering.md for current findings.
"""
from __future__ import annotations

import logging
from datetime import timedelta

import aiohttp

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .const import CONF_HOST, DEFAULT_SCAN_INTERVAL, DOMAIN

_LOGGER = logging.getLogger(__name__)


class PowerHubData:
    """Represents a snapshot of data from the PowerHub device."""

    def __init__(self, raw: dict) -> None:
        self._raw = raw

    @property
    def power_import_w(self) -> float | None:
        """Active power import in watts."""
        return self._raw.get("power_import_w")

    @property
    def power_export_w(self) -> float | None:
        """Active power export in watts (solar/generation)."""
        return self._raw.get("power_export_w")

    @property
    def energy_import_kwh(self) -> float | None:
        """Cumulative energy import in kWh."""
        return self._raw.get("energy_import_kwh")

    @property
    def energy_export_kwh(self) -> float | None:
        """Cumulative energy export in kWh."""
        return self._raw.get("energy_export_kwh")

    @property
    def voltage_l1(self) -> float | None:
        """Phase L1 voltage in V."""
        return self._raw.get("voltage_l1")

    @property
    def voltage_l2(self) -> float | None:
        """Phase L2 voltage in V."""
        return self._raw.get("voltage_l2")

    @property
    def voltage_l3(self) -> float | None:
        """Phase L3 voltage in V."""
        return self._raw.get("voltage_l3")

    @property
    def current_l1(self) -> float | None:
        """Phase L1 current in A."""
        return self._raw.get("current_l1")

    @property
    def current_l2(self) -> float | None:
        """Phase L2 current in A."""
        return self._raw.get("current_l2")

    @property
    def current_l3(self) -> float | None:
        """Phase L3 current in A."""
        return self._raw.get("current_l3")


class PowerHubCoordinator(DataUpdateCoordinator[PowerHubData]):
    """Coordinator that polls the PowerHub device for data."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._host = entry.data[CONF_HOST]
        self._session = async_get_clientsession(hass)
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=DEFAULT_SCAN_INTERVAL),
        )

    async def _async_update_data(self) -> PowerHubData:
        """Fetch data from the PowerHub device.

        TODO: The actual local API endpoints are not yet known.
        This method attempts several common ESP32 firmware endpoints.
        Update once reverse engineering is complete.
        """
        candidate_paths = [
            "/status",
            "/data",
            "/api/v1/data",
            "/energy",
            "/metrics",
        ]

        for path in candidate_paths:
            url = f"http://{self._host}{path}"
            try:
                async with self._session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                    if resp.status == 200:
                        try:
                            data = await resp.json(content_type=None)
                            _LOGGER.debug("Got data from %s: %s", url, data)
                            return PowerHubData(self._parse_response(data))
                        except Exception:
                            text = await resp.text()
                            _LOGGER.debug("Non-JSON response from %s: %s", url, text[:200])
            except aiohttp.ClientConnectorError:
                pass
            except Exception as err:
                _LOGGER.debug("Error fetching %s: %s", url, err)

        raise UpdateFailed(
            f"Could not fetch data from PowerHub at {self._host}. "
            "No known local API endpoint responded. "
            "See docs/reverse_engineering.md — the device may be cloud-only."
        )

    def _parse_response(self, data: dict) -> dict:
        """Normalize raw API response to internal data format.

        This mapping will be updated as the actual API is understood.
        """
        # Attempt common key names seen in similar ESP32 energy devices
        normalized: dict = {}

        # Power (W)
        for key in ("power", "power_import", "activeImport", "p_import", "watt", "W"):
            if key in data:
                normalized["power_import_w"] = float(data[key])
                break

        for key in ("power_export", "activeExport", "p_export"):
            if key in data:
                normalized["power_export_w"] = float(data[key])
                break

        # Energy (kWh)
        for key in ("energy", "energy_import", "cumulativeActiveImport", "kwh"):
            if key in data:
                normalized["energy_import_kwh"] = float(data[key])
                break

        for key in ("energy_export", "cumulativeActiveExport"):
            if key in data:
                normalized["energy_export_kwh"] = float(data[key])
                break

        # Voltages
        for phase, keys in [
            ("l1", ("voltageL1", "voltage_l1", "u1", "U1")),
            ("l2", ("voltageL2", "voltage_l2", "u2", "U2")),
            ("l3", ("voltageL3", "voltage_l3", "u3", "U3")),
        ]:
            for key in keys:
                if key in data:
                    normalized[f"voltage_{phase}"] = float(data[key])
                    break

        # Currents
        for phase, keys in [
            ("l1", ("currentL1", "current_l1", "i1", "I1")),
            ("l2", ("currentL2", "current_l2", "i2", "I2")),
            ("l3", ("currentL3", "current_l3", "i3", "I3")),
        ]:
            for key in keys:
                if key in data:
                    normalized[f"current_{phase}"] = float(data[key])
                    break

        return normalized
