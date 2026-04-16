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
from dataclasses import dataclass, field
from typing import AsyncGenerator

import aiohttp

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://malarenergi.prod.flow.bitv.is/powerapi/v1"
POLL_INTERVAL = 1  # seconds between bankid/check polls
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


@dataclass
class MeterResponse:
    """Full envelope returned by consumption/production meter endpoints."""
    facility_id: str
    start_ms: int
    end_ms: int
    count: int
    value_min: float
    value_max: float
    avg: float
    data: list[MeterData]


@dataclass
class FacilityAttributes:
    """Physical attributes of a facility."""
    heating_type: str          # e.g. "DISTRICT_HEATING"
    fuse_size: int             # Ampere
    occupants: int
    area: int                  # m²
    facility_type: str         # e.g. "APARTMENT" / "HOUSE"
    ev_type: str | None        # e.g. "NONE"
    has_battery: bool
    has_solar: bool


@dataclass
class AccountProfile:
    """Mälarenergi account holder information."""
    name: str
    phone: str
    email: str
    customer_number: str


@dataclass
class Agreement:
    """Active supply agreement."""
    agreement_number: str
    supply_service_name: str
    supply_start_date_ms: int
    price_model: str           # e.g. "SPOT"
    utility: str               # e.g. "ELECTRICITY"
    facility_id: str


@dataclass
class Invitation:
    """Sharing invitation created by this account."""
    invitation_id: str
    expires: int               # epoch ms
    created: int               # epoch ms
    claimed: bool
    accessed_facilities: list[str] = field(default_factory=list)


@dataclass
class InvitationCreated:
    """Result returned when a sharing invitation is created."""
    invitation_id: str
    code: str             # Short alphanumeric code for manual entry (e.g. "ELX4CULD")
    created: str          # ISO 8601 timestamp
    expires: str          # ISO 8601 timestamp
    accessed_facilities: list[dict]


@dataclass
class Invitee:
    """Person who has been granted access to a facility."""
    invitee_id: str
    claimer_name: str
    facility_id: str
    share_all_devices: bool


@dataclass
class MonthlyInsights:
    """Monthly energy insights comparison."""
    facility_id: str
    month_timestamp_ms: int
    your_average_price: float | None      # öre/kWh or kr/kWh; None for production meter
    monthly_average_price: float | None   # öre/kWh or kr/kWh - market average; None for production
    price_trend: str | None               # "ABOVE" / "BELOW"; None for production
    current_year_value: float             # kWh year-to-date
    previous_year_value: float | None     # kWh same period last year
    year_percentage_change: float | None
    year_trend: str | None
    daily_peaks: list[dict]
    baseload_kw: float
    baseload_kwh: float
    baseload_percentage: float
    total_kwh: float
    off_peak_score: float | None          # None for production meter
    off_peak_rating: str | None           # e.g. "GOOD" / "AVERAGE" / "POOR"


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

    async def _post(self, path: str, body: dict) -> object:
        url = f"{BASE_URL}{path}"
        async with self._session.post(
            url,
            headers=self._headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise AuthError("Token expired or invalid")
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def _put(self, path: str, body: dict) -> object:
        url = f"{BASE_URL}{path}"
        async with self._session.put(
            url,
            headers=self._headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise AuthError("Token expired or invalid")
            resp.raise_for_status()
            return await resp.json(content_type=None)

    async def _delete(self, path: str) -> None:
        url = f"{BASE_URL}{path}"
        async with self._session.delete(
            url,
            headers=self._headers,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise AuthError("Token expired or invalid")
            resp.raise_for_status()

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

    async def get_profile(self) -> AccountProfile:
        """Get account holder profile (name, phone, email)."""
        data = await self._get("/account/profile")
        return AccountProfile(
            name=data.get("name", ""),
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            customer_number=data.get("customerNumber", ""),
        )

    async def get_agreements(self) -> list[Agreement]:
        """Get active supply agreements."""
        data = await self._get("/account/agreement")
        return [
            Agreement(
                agreement_number=a.get("agreementNumber", ""),
                supply_service_name=a.get("supplyServiceName", ""),
                supply_start_date_ms=a.get("supplyStartDate", 0),
                price_model=(a.get("attributes") or {}).get("agreementPriceModel", ""),
                utility=(a.get("attributes") or {}).get("utility", ""),
                facility_id=(a.get("facility") or {}).get("facilityid", ""),
            )
            for a in (data if isinstance(data, list) else [])
        ]

    async def get_invitations(self) -> list[Invitation]:
        """Get invitations created by this account."""
        data = await self._get("/account/invitation")
        return [
            Invitation(
                invitation_id=inv.get("id", ""),
                expires=inv.get("expires", 0),
                created=inv.get("created", 0),
                claimed=inv.get("claimed", False),
                accessed_facilities=inv.get("accessedFacilities", []),
            )
            for inv in (data if isinstance(data, list) else [])
        ]

    async def create_invitation(
        self,
        facility_id: str,
        share_all_devices: bool = True,
    ) -> InvitationCreated:
        """Create a sharing invitation for a facility.

        Returns the new invitation including a short alphanumeric code
        that the recipient can use for manual entry.
        """
        body = {
            "accessedFacilities": [
                {"facilityId": facility_id, "shareAllDevices": share_all_devices}
            ]
        }
        resp = await self._post("/account/invitation", body)
        data = resp.get("data", {})
        return InvitationCreated(
            invitation_id=data.get("id", ""),
            code=data.get("code", ""),
            created=data.get("created", ""),
            expires=data.get("expires", ""),
            accessed_facilities=data.get("accessedFacilities", []),
        )

    async def delete_invitation(self, invitation_id: str) -> None:
        """Delete a sharing invitation by its ID."""
        await self._delete(f"/account/invitation/{invitation_id}")

    # ------------------------------------------------------------------
    # Facility
    # ------------------------------------------------------------------

    async def get_facility_attributes(self, facility_id: str) -> FacilityAttributes:
        """Get physical attributes of a facility."""
        data: dict = await self._get(f"/facility/{facility_id}/attributes")  # type: ignore[assignment]
        # fuseSize is returned as e.g. "A20" — strip leading letter and parse
        raw_fuse = data.get("fuseSize", "0")
        try:
            fuse_amps = int(str(raw_fuse).lstrip("Aa"))
        except ValueError:
            fuse_amps = 0
        return FacilityAttributes(
            heating_type=data.get("heatingType", ""),
            fuse_size=fuse_amps,
            occupants=data.get("occupants", 0),
            area=data.get("area", 0),
            facility_type=data.get("type", ""),
            ev_type=data.get("evType"),
            has_battery=bool(data.get("battery", False)),
            has_solar=bool(data.get("solar", False)),
        )

    async def get_invitees(self, facility_id: str) -> list[Invitee]:
        """Get people who have been granted access to a facility."""
        data = await self._get(f"/facility/{facility_id}/invitees")
        return [
            Invitee(
                invitee_id=inv.get("id", ""),
                claimer_name=inv.get("claimerName", ""),
                facility_id=inv.get("facilityId", facility_id),
                share_all_devices=inv.get("shareAllDevices", False),
            )
            for inv in (data if isinstance(data, list) else [])
        ]

    async def update_facility_attributes(
        self, facility_id: str, attrs: FacilityAttributes
    ) -> FacilityAttributes:
        """Update physical attributes of a facility (PUT — full object required).

        The API requires all fields to be sent; partial updates are not supported.
        """
        body = {
            "heatingType": attrs.heating_type,
            "fuseSize": f"A{attrs.fuse_size}",
            "occupants": attrs.occupants,
            "area": attrs.area,
            "type": attrs.facility_type,
            "icon": attrs.facility_type.lower() if attrs.facility_type else "villa",
            "evType": attrs.ev_type or "NONE",
            "battery": attrs.has_battery,
            "solar": attrs.has_solar,
        }
        data: dict = await self._put(f"/facility/{facility_id}/attributes", body)  # type: ignore[assignment]
        raw_fuse = data.get("fuseSize", "0")
        try:
            fuse_amps = int(str(raw_fuse).lstrip("Aa"))
        except ValueError:
            fuse_amps = attrs.fuse_size
        return FacilityAttributes(
            heating_type=data.get("heatingType", attrs.heating_type),
            fuse_size=fuse_amps,
            occupants=data.get("occupants", attrs.occupants),
            area=data.get("area", attrs.area),
            facility_type=data.get("type", attrs.facility_type),
            ev_type=data.get("evType", attrs.ev_type),
            has_battery=bool(data.get("battery", attrs.has_battery)),
            has_solar=bool(data.get("solar", attrs.has_solar)),
        )

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
        """Get Nordpool spot price for a day (15-min buckets, öre/kWh or kr/kWh)."""
        data = await self._get(
            f"/facility/{facility_id}/nordpool_spot_price",
            interval="DAY",
            type="START",
            timestamp=timestamp_ms,
        )
        return data.get("data", [])

    async def get_month_consumption(self, facility_id: str, month_start_ms: int) -> MeterResponse:
        """Get consumption for a full month (daily buckets)."""
        return await self._get_meter(
            f"/facility/{facility_id}/facility_consumption_meter",
            "MONTH",
            month_start_ms,
        )

    async def get_month_production(self, facility_id: str, month_start_ms: int) -> MeterResponse:
        """Get production for a full month (daily buckets)."""
        return await self._get_meter(
            f"/facility/{facility_id}/facility_production_meter",
            "MONTH",
            month_start_ms,
        )

    async def get_year_consumption(self, facility_id: str, year_start_ms: int) -> MeterResponse:
        """Get consumption for a full year (monthly buckets)."""
        return await self._get_meter(
            f"/facility/{facility_id}/facility_consumption_meter",
            "YEAR",
            year_start_ms,
        )

    async def get_notifications(
        self,
        firebase_token: str = "ha-integration",
        topics: str = "operatingStatus,todaySpotPrice,generic",
        page_size: int = 25,
    ) -> list[dict]:
        """Get recent push notifications from the Mälarenergi app backend.

        Returns a list of notification dicts with keys:
          title, body, type, read, created (epoch ms), facilityId
        """
        data = await self._get(
            "/notifications",
            firebase_token=firebase_token,
            topics=topics,
            page=1,
            page_size=page_size,
        )
        return data if isinstance(data, list) else []

    async def get_monthly_insights(
        self,
        facility_id: str,
        month_start_ms: int,
        meter_type: str = "consumption",
        region: str = "SE3",
    ) -> MonthlyInsights:
        """Get monthly energy insights (price comparison, year-over-year, peaks, baseload)."""
        data = await self._get(
            f"/facility/{facility_id}/insights/monthly/{month_start_ms}",
            meterType=meter_type,
            region=region,
        )
        price = data.get("priceComparison") or {}
        year = data.get("yearComparison") or {}
        peaks = data.get("powerPeaks") or {}
        baseload_obj = data.get("baseload") or {}
        off_peak = data.get("offPeakScore")  # dict or None
        return MonthlyInsights(
            facility_id=data.get("facilityId", facility_id),
            month_timestamp_ms=data.get("monthTimestamp", month_start_ms),
            your_average_price=price.get("yourAveragePrice"),
            monthly_average_price=price.get("monthlyAveragePrice"),
            price_trend=price.get("trend"),
            current_year_value=year.get("currentYearValue", 0.0),
            previous_year_value=year.get("previousYearValue"),
            year_percentage_change=year.get("percentageChange"),
            year_trend=year.get("trend"),
            daily_peaks=(peaks.get("dailyPeaks") or []),
            baseload_kw=baseload_obj.get("baseload", 0.0),
            baseload_kwh=baseload_obj.get("baseloadKwh", 0.0),
            baseload_percentage=baseload_obj.get("baseloadPercentage", 0.0),
            total_kwh=baseload_obj.get("totalKwh", 0.0),
            off_peak_score=off_peak.get("offPeakScore") if off_peak else None,
            off_peak_rating=off_peak.get("rating") if off_peak else None,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_meter(self, path: str, interval: str, timestamp_ms: int) -> MeterResponse:
        data = await self._get(path, interval=interval, type="START", timestamp=timestamp_ms)
        return MeterResponse(
            facility_id=data.get("facilityid", ""),
            start_ms=data.get("start", 0),
            end_ms=data.get("end", 0),
            count=data.get("count", 0),
            value_min=data.get("min", 0.0),
            value_max=data.get("max", 0.0),
            avg=data.get("avg", 0.0),
            data=[MeterData(d["timestamp"], d["value"]) for d in data.get("data", [])],
        )


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
