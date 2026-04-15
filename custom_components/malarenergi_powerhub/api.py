"""Mälarenergi PowerHub — Bitvis Flow API client.

Base URL:  https://malarenergi.prod.flow.bitv.is/powerapi/v1
Auth:      Bearer <JWT token> obtained via BankID QR flow

BankID authentication flow:
  1. GET  /bankid/auth
         → { transactionId, autoStartToken }
  2. GET  /bankid/check/{transactionId}   (poll every ~2s)
         → { status: "pending", qrCode: "bankid.xxx.N.hash" }  (QR rotates each second)
         → { status: "complete", token: "<JWT>" }
  3. Use token as:  Authorization: Bearer <token>
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import AsyncGenerator

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://malarenergi.prod.flow.bitv.is/powerapi/v1"
POLL_INTERVAL = 2  # seconds between bankid/check polls
POLL_TIMEOUT = 180  # seconds before giving up


class AuthError(Exception):
    """Authentication failed."""


class ApiError(Exception):
    """Generic API error."""


@dataclass
class FacilityInfo:
    facility_id: str
    street: str
    house_number: int
    city: str
    meter_id: str
    region: str
    customer_id: str


@dataclass
class MeterData:
    """One data point from consumption/production meter."""
    timestamp_ms: int
    value_wh: float  # Wh


@dataclass
class LiveData:
    """Most recent meter reading (latest data point of today)."""
    consumption_wh: float | None   # Wh consumed today so far
    production_wh: float | None    # Wh produced today so far


class PowerHubApiClient:
    """Async HTTP client for the Bitvis Flow PowerAPI."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    async def _get(self, path: str, **params) -> object:
        url = f"{BASE_URL}{path}"
        async with self._session.get(
            url,
            headers=self._headers,
            params=params or None,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise AuthError("Token expired or invalid")
            resp.raise_for_status()
            return await resp.json(content_type=None)

    # ------------------------------------------------------------------
    # Account / setup
    # ------------------------------------------------------------------

    async def get_facilities(self) -> list[FacilityInfo]:
        data = await self._get("/account/facility")
        results = []
        seen = set()
        for f in data:
            fid = f["facilityid"]
            if fid in seen:
                continue
            seen.add(fid)
            meta = f.get("metadata") or {}
            results.append(FacilityInfo(
                facility_id=fid,
                street=f.get("street", ""),
                house_number=f.get("houseNumber", 0),
                city=f.get("city", ""),
                meter_id=meta.get("meterId", ""),
                region=meta.get("region", "SE3"),
                customer_id=f.get("facilityOwnerId", ""),
            ))
        return results

    # ------------------------------------------------------------------
    # Energy data
    # ------------------------------------------------------------------

    async def get_today_consumption(self, facility_id: str, timestamp_ms: int) -> list[MeterData]:
        """Get consumption for a single day (15-min buckets)."""
        data = await self._get(
            f"/facility/{facility_id}/facility_consumption_meter",
            interval="DAY",
            type="START",
            timestamp=timestamp_ms,
        )
        return [MeterData(d["timestamp"], d["value"]) for d in data.get("data", [])]

    async def get_today_production(self, facility_id: str, timestamp_ms: int) -> list[MeterData]:
        """Get production (solar) for a single day (15-min buckets)."""
        data = await self._get(
            f"/facility/{facility_id}/facility_production_meter",
            interval="DAY",
            type="START",
            timestamp=timestamp_ms,
        )
        return [MeterData(d["timestamp"], d["value"]) for d in data.get("data", [])]

    async def get_spot_price_today(self, facility_id: str, timestamp_ms: int) -> list[dict]:
        """Get Nordpool spot price for a day (15-min buckets, öre/kWh)."""
        data = await self._get(
            f"/facility/{facility_id}/nordpool_spot_price",
            interval="DAY",
            type="START",
            timestamp=timestamp_ms,
        )
        return data.get("data", [])


# ------------------------------------------------------------------
# BankID authentication
# ------------------------------------------------------------------

async def bankid_start(session: aiohttp.ClientSession) -> tuple[str, str]:
    """Start a BankID auth session.

    Returns (transaction_id, auto_start_token).
    """
    async with session.get(
        f"{BASE_URL}/bankid/auth",
        timeout=aiohttp.ClientTimeout(total=15),
    ) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
    return data["transactionId"], data["autoStartToken"]


async def bankid_poll(
    session: aiohttp.ClientSession,
    transaction_id: str,
) -> AsyncGenerator[tuple[str, str | None, str | None], None]:
    """Poll BankID check endpoint until complete or failed.

    Yields (status, qr_code, token):
      - status: "pending" | "complete" | "failed"
      - qr_code: rotating QR string while pending (show in UI)
      - token: Bearer JWT when status == "complete"
    """
    deadline = asyncio.get_event_loop().time() + POLL_TIMEOUT
    while asyncio.get_event_loop().time() < deadline:
        async with session.get(
            f"{BASE_URL}/bankid/check/{transaction_id}",
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json(content_type=None)

        status = data.get("status", "failed")
        qr = data.get("qrCode")
        token = data.get("token")

        yield status, qr, token

        if status in ("complete", "failed"):
            return

        await asyncio.sleep(POLL_INTERVAL)

    yield "failed", None, None
