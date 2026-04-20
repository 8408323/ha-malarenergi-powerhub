"""Mälarenergi PowerHub — Bitvis Flow API client + Bitvis Power API client.

Flow API base URL:  https://malarenergi.prod.flow.bitv.is/powerapi/v1
Power API base URL: https://api.prod.power.bitv.is
Auth (both):        Bearer <JWT token> obtained via BankID QR flow

BankID authentication flow:
  1. GET  /bankid/auth
         → { transactionId, autoStartToken }
  2. GET  /bankid/check/{transactionId}   (poll every ~1s)
         → { status: "pending", qrCode: "bankid.xxx.N.hash" }  (QR rotates each second)
         → { status: "complete", token: "<JWT>" }
  3. Use token as:  Authorization: Bearer <token>
"""
from __future__ import annotations

import asyncio
import logging
import struct
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator, Iterator

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
    expires: str               # ISO 8601 timestamp
    created: str               # ISO 8601 timestamp
    claimed: bool
    code: str | None = None    # Short alphanumeric code; null once claimed
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

    async def _get(self, path: str, **params) -> Any:
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

    async def _post(self, path: str, body: dict) -> Any:
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
                expires=inv.get("expires", ""),
                created=inv.get("created", ""),
                claimed=bool(inv.get("claimed")),
                code=inv.get("code"),
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

    async def get_year_production(self, facility_id: str, year_start_ms: int) -> MeterResponse:
        """Get production (solar export) for a full year (monthly buckets)."""
        return await self._get_meter(
            f"/facility/{facility_id}/facility_production_meter",
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
# Bitvis Power API
# ------------------------------------------------------------------

POWER_BASE_URL = "https://api.prod.power.bitv.is"


@dataclass
class PowerHubDevice:
    device_id: str
    model: str
    facility_id: str
    mac_address: str


@dataclass
class PowerTelemetry:
    """One 1-minute sample from the Power telemetry endpoint."""
    timestamp: datetime
    power_import_kw: float   # power_active_delivered_to_client_kw
    power_export_kw: float   # power_active_delivered_by_client_kw


@dataclass
class PhaseTelemetry:
    """One 1-minute per-phase sample.

    The Bitvis Power backend only serves per-phase *current* for this endpoint —
    per-phase power fields in the query are accepted but never populated in the
    response, so we don't expose them.
    """
    timestamp: datetime
    current_l1_a: float
    current_l2_a: float
    current_l3_a: float


@dataclass
class HourlyEnergy:
    """One hourly energy bucket from the aggregated energy endpoint."""
    bucket_start: datetime
    window_start: datetime
    window_end: datetime
    sample_count: int
    energy_import_wh: float
    energy_export_wh: float


@dataclass
class PowerDiagnostics:
    uptime_s: int
    wifi_rssi_dbm: int
    sw_version: str
    han_port_state: str      # "ACTIVE" / "INACTIVE"


@dataclass
class FacilityControl:
    fuse_limit_a: float
    power_limit_kw: float
    action_on_fuse_limit: str   # "NOTIFY" / "CUT"
    action_on_power_limit: str


@dataclass
class FcrStatus:
    fcrd_down_enabled: bool


@dataclass
class NotificationSettings:
    notify_total_power: bool
    notify_phase_load: bool
    notify_control_disabled_exceeded_phase: bool
    notify_control_disabled_exceeded_power: bool
    notify_control_enabled_exceeded_phase: bool
    notify_control_enabled_exceeded_power: bool

    def to_dict(self) -> dict:
        return {
            "notifyTotalPower": self.notify_total_power,
            "notifyPhaseLoad": self.notify_phase_load,
            "notifyControlDisabledExceededPhase": self.notify_control_disabled_exceeded_phase,
            "notifyControlDisabledExceededPower": self.notify_control_disabled_exceeded_power,
            "notifyControlEnabledExceededPhase": self.notify_control_enabled_exceeded_phase,
            "notifyControlEnabledExceededPower": self.notify_control_enabled_exceeded_power,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "NotificationSettings":
        return cls(
            notify_total_power=bool(data.get("notifyTotalPower", False)),
            notify_phase_load=bool(data.get("notifyPhaseLoad", False)),
            notify_control_disabled_exceeded_phase=bool(data.get("notifyControlDisabledExceededPhase", False)),
            notify_control_disabled_exceeded_power=bool(data.get("notifyControlDisabledExceededPower", False)),
            notify_control_enabled_exceeded_phase=bool(data.get("notifyControlEnabledExceededPhase", False)),
            notify_control_enabled_exceeded_power=bool(data.get("notifyControlEnabledExceededPower", False)),
        )


def _read_varint(data: bytes, pos: int) -> tuple[int, int]:
    """Read a varint from data at pos. Returns (value, new_pos)."""
    val = 0
    shift = 0
    while pos < len(data):
        b = data[pos]; pos += 1
        val |= (b & 0x7f) << shift
        shift += 7
        if not (b & 0x80):
            break
    return val, pos


def _parse_submessage(sub: bytes) -> dict[int, int | float | bytes]:
    """Parse a flat protobuf submessage into {field_num: value}.

    Handles: varint (wire=0), fixed32 float (wire=5), length-delimited (wire=2).
    Length-delimited values are stored as raw bytes under their field number.
    """
    fields: dict[int, int | float | bytes] = {}
    sp = 0
    while sp < len(sub):
        tag_val, sp = _read_varint(sub, sp)
        field_num = tag_val >> 3
        wire = tag_val & 7
        if wire == 0:
            val, sp = _read_varint(sub, sp)
            fields[field_num] = val
        elif wire == 5:
            if sp + 4 > len(sub):
                break
            fields[field_num] = struct.unpack_from("<f", sub, sp)[0]
            sp += 4
        elif wire == 2:
            length, sp = _read_varint(sub, sp)
            fields[field_num] = sub[sp:sp + length]
            sp += length
        elif wire == 1:
            sp += 8  # skip 64-bit
        else:
            break
    return fields


def _iter_delimited(raw: bytes) -> Iterator[dict[int, int | float | bytes]]:
    """Yield one decoded submessage per record from a length-delimited protobuf stream.

    Wire format (``application/x-protobuf;delimited=true``): a varint length
    prefix followed by that many bytes of submessage, repeated to end of buffer.
    """
    pos = 0
    n = len(raw)
    while pos < n:
        sub_len, pos = _read_varint(raw, pos)
        if pos + sub_len > n:
            return
        yield _parse_submessage(raw[pos:pos + sub_len])
        pos += sub_len


def _decode_telemetry_proto(raw: bytes) -> list[PowerTelemetry]:
    """Decode 2-field power telemetry (import + export kW).

    Each record: field1 varint ts_s, field6 float32 import, field7 float32 export.
    """
    results: list[PowerTelemetry] = []
    for fields in _iter_delimited(raw):
        ts_s = fields.get(1)
        if isinstance(ts_s, int):
            results.append(PowerTelemetry(
                timestamp=datetime.fromtimestamp(ts_s, tz=timezone.utc),
                power_import_kw=float(fields.get(6, 0.0)),
                power_export_kw=float(fields.get(7, 0.0)),
            ))
    return results


def _decode_phase_telemetry_proto(raw: bytes) -> list[PhaseTelemetry]:
    """Decode per-phase current telemetry.

    Each record: field1 varint ts_s, fields 17/18/19 float32 currents L1/L2/L3.
    The per-phase power fields in the query are not served by the backend.
    """
    results: list[PhaseTelemetry] = []
    for f in _iter_delimited(raw):
        ts_s = f.get(1)
        if isinstance(ts_s, int):
            results.append(PhaseTelemetry(
                timestamp=datetime.fromtimestamp(ts_s, tz=timezone.utc),
                current_l1_a=float(f.get(17, 0.0)),
                current_l2_a=float(f.get(18, 0.0)),
                current_l3_a=float(f.get(19, 0.0)),
            ))
    return results


def _ts_from_submsg(raw: bytes) -> int | None:
    """Extract the varint timestamp from a nested timestamp submessage."""
    f = _parse_submessage(raw)
    val = f.get(1)
    return val if isinstance(val, int) else None


def _decode_hourly_energy_proto(raw: bytes) -> list[HourlyEnergy]:
    """Decode aggregated hourly energy (EnergyDelta protobuf).

    Outer: repeated field1 length-delimited. Each record:
      field1 (msg): bucket start ts submessage  → field1 varint ts_s
      field2 varint: sample count
      field3 (msg): window start ts submessage
      field4 (msg): window end ts submessage
      field7 float32: energy_import_wh
      field10 float32: energy_export_wh
    """
    results: list[HourlyEnergy] = []
    pos = 0
    n = len(raw)
    while pos < n:
        tag_val, pos = _read_varint(raw, pos)
        wire = tag_val & 7
        if wire != 2:
            break
        length, pos = _read_varint(raw, pos)
        if pos + length > n:
            break
        f = _parse_submessage(raw[pos:pos + length])
        pos += length

        bucket_raw = f.get(1)
        win_start_raw = f.get(3)
        win_end_raw = f.get(4)
        if not (isinstance(bucket_raw, bytes) and isinstance(win_start_raw, bytes) and isinstance(win_end_raw, bytes)):
            continue
        bucket_ts = _ts_from_submsg(bucket_raw)
        win_start_ts = _ts_from_submsg(win_start_raw)
        win_end_ts = _ts_from_submsg(win_end_raw)
        if bucket_ts is None or win_start_ts is None or win_end_ts is None:
            continue
        results.append(HourlyEnergy(
            bucket_start=datetime.fromtimestamp(bucket_ts, tz=timezone.utc),
            window_start=datetime.fromtimestamp(win_start_ts, tz=timezone.utc),
            window_end=datetime.fromtimestamp(win_end_ts, tz=timezone.utc),
            sample_count=int(f.get(2, 0)),
            energy_import_wh=float(f.get(7, 0.0)),
            energy_export_wh=float(f.get(10, 0.0)),
        ))
    return results


class PowerApiClient:
    """Async HTTP client for the Bitvis Power backend."""

    def __init__(self, session: aiohttp.ClientSession, token: str) -> None:
        self._session = session
        self._token = token

    @property
    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self._token}"}

    async def _get_json(self, path: str, **params) -> Any:
        url = f"{POWER_BASE_URL}{path}"
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

    async def _get_bytes(self, path: str, params: list[tuple] | None = None) -> bytes:
        url = f"{POWER_BASE_URL}{path}"
        async with self._session.get(
            url,
            headers=self._headers,
            params=params,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise AuthError("Token expired or invalid")
            resp.raise_for_status()
            return await resp.read()

    async def get_device(self) -> PowerHubDevice:
        """Get PowerHub device info (deviceId, model, facilityId)."""
        data = await self._get_json("/devices/powerhub")
        if isinstance(data, list):
            if not data:
                raise ValueError("No PowerHub device returned by backend")
            d = data[0]
        else:
            d = data
        return PowerHubDevice(
            device_id=d.get("deviceId", ""),
            model=d.get("model", ""),
            facility_id=d.get("facilityId", ""),
            mac_address=d.get("macAddress", ""),
        )

    async def get_current_power(self, facility_id: str) -> PowerTelemetry | None:
        """Fetch the most recent 1-minute power sample."""
        now = datetime.now(tz=timezone.utc)
        start = (now - timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = await self._get_bytes(
            f"/data-extraction/powerhub/telemetry/{facility_id}",
            params=[
                ("start", start),
                ("end", end),
                ("fields", "power_active_delivered_to_client_kw"),
                ("fields", "power_active_delivered_by_client_kw"),
            ],
        )
        samples = _decode_telemetry_proto(raw)
        if not samples:
            return None
        return max(samples, key=lambda s: s.timestamp)

    async def get_diagnostics(self, facility_id: str) -> PowerDiagnostics:
        """Get device status (uptime, WiFi RSSI, SW version, HAN port state)."""
        data: dict = await self._get_json(  # type: ignore[assignment]
            f"/data-extraction/powerhub/diagnostics/{facility_id}"
        )
        return PowerDiagnostics(
            uptime_s=data.get("uptimeS", 0),
            wifi_rssi_dbm=data.get("wifiRssiDbm", 0),
            sw_version=(data.get("deviceInfoSwVersion") or ""),
            han_port_state=data.get("hanPortState", ""),
        )

    async def get_current_power_phases(self, facility_id: str) -> PhaseTelemetry | None:
        """Fetch the most recent per-phase power sample (3-phase currents + powers)."""
        now = datetime.now(tz=timezone.utc)
        start = (now - timedelta(minutes=3)).strftime("%Y-%m-%dT%H:%M:%SZ")
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ")
        raw = await self._get_bytes(
            f"/data-extraction/powerhub/telemetry/{facility_id}",
            params=[
                ("start", start),
                ("end", end),
                ("fields", "phase_current_l1_a"),
                ("fields", "phase_current_l2_a"),
                ("fields", "phase_current_l3_a"),
                ("fields", "power_active_l1_delivered_to_client_kw"),
                ("fields", "power_active_l1_delivered_by_client_kw"),
                ("fields", "power_active_l2_delivered_to_client_kw"),
                ("fields", "power_active_l2_delivered_by_client_kw"),
                ("fields", "power_active_l3_delivered_to_client_kw"),
                ("fields", "power_active_l3_delivered_by_client_kw"),
            ],
        )
        samples = _decode_phase_telemetry_proto(raw)
        if not samples:
            return None
        return max(samples, key=lambda s: s.timestamp)

    async def get_hourly_energy(
        self, facility_id: str, start: datetime, end: datetime
    ) -> list[HourlyEnergy]:
        """Fetch hourly energy aggregates (max 745 hours window)."""
        raw = await self._get_bytes(
            f"/data-extraction/powerhub/telemetry/{facility_id}/aggregated/energy",
            params=[
                ("start", start.strftime("%Y-%m-%dT%H:%M:%SZ")),
                ("end", end.strftime("%Y-%m-%dT%H:%M:%SZ")),
                ("resolution", "HOURLY"),
            ],
        )
        return _decode_hourly_energy_proto(raw)

    async def get_facility_control(self, facility_id: str) -> FacilityControl:
        """Get fuse/power limits for the facility."""
        data: dict = await self._get_json(  # type: ignore[assignment]
            f"/activation/facilitycontrol/{facility_id}"
        )
        return FacilityControl(
            fuse_limit_a=data.get("fuseLimitA", 0.0),
            power_limit_kw=data.get("powerLimitKw", 0.0),
            action_on_fuse_limit=data.get("actionOnFuseLimit", ""),
            action_on_power_limit=data.get("actionOnPowerLimit", ""),
        )

    async def get_fcr_status(self, facility_id: str) -> FcrStatus:
        """Get FCR (Frequency Containment Reserve) enablement status."""
        data: dict = await self._get_json(  # type: ignore[assignment]
            f"/activation/fcr/facility-enablements/{facility_id}"
        )
        return FcrStatus(
            fcrd_down_enabled=bool(data.get("fcrdDownEnabled", False)),
        )

    async def update_facility_control(
        self,
        facility_id: str,
        control: FacilityControl,
    ) -> None:
        """Update fuse/power limits via POST /activation/facilitycontrol."""
        body = {
            "facilityId": facility_id,
            "fuseLimitA": control.fuse_limit_a,
            "actionOnFuseLimit": control.action_on_fuse_limit,
            "powerLimitKw": control.power_limit_kw,
            "actionOnPowerLimit": control.action_on_power_limit,
        }
        url = f"{POWER_BASE_URL}/activation/facilitycontrol"
        async with self._session.post(
            url,
            headers=self._headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise AuthError("Token expired or invalid")
            resp.raise_for_status()

    async def get_notification_settings(self, facility_id: str) -> NotificationSettings:
        """Get push notification preferences."""
        data: dict = await self._get_json(  # type: ignore[assignment]
            f"/customer/settings/{facility_id}/notifications"
        )
        return NotificationSettings.from_dict(data)

    async def update_notification_settings(
        self, facility_id: str, settings: NotificationSettings
    ) -> NotificationSettings:
        """Update push notification preferences via PATCH."""
        url = f"{POWER_BASE_URL}/customer/settings/{facility_id}/notifications"
        async with self._session.patch(
            url,
            headers=self._headers,
            json=settings.to_dict(),
            timeout=aiohttp.ClientTimeout(total=15),
        ) as resp:
            if resp.status == 401:
                raise AuthError("Token expired or invalid")
            resp.raise_for_status()
            result = await resp.json(content_type=None)
            return NotificationSettings.from_dict(result if isinstance(result, dict) else {})


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
