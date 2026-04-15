# Agent Instructions — ha-malarenergi-powerhub

Home Assistant custom integration for the Mälarenergi PowerHub cloud energy monitor.
See [README.md](README.md) for hardware/API context and [CONTRIBUTING.md](CONTRIBUTING.md) for branch/commit conventions.

## Build & Test

```bash
# Install dependencies (Python 3.12)
pip install pytest pytest-asyncio aioresponses aiohttp homeassistant "qrcode[pil]==8.0"

# Run tests
python -m pytest tests/ -v
```

Tests use `aioresponses` to mock all HTTP — never make real network calls in tests.

## Architecture

| File | Role |
|---|---|
| `api.py` | HTTP client for the Bitvis Flow API; contains BankID auth + all REST calls |
| `config_flow.py` | BankID QR authentication flow for HA onboarding/reauth |
| `coordinator.py` | `DataUpdateCoordinator` — polls API every 60 s, aggregates daily totals |
| `sensor.py` | `SensorEntityDescription`-driven entities; reads from coordinator data |
| `const.py` | Domain, config entry keys, scan interval constant |

## Key Conventions

**Timezone**: All day-boundary calculations must use `Europe/Stockholm` (not system TZ) to align with Swedish utility billing.

**Data model**: `PowerHubData` is an immutable dataclass snapshot. Consumption/production are `TOTAL_INCREASING` (cumulative Wh); spot price is `MEASUREMENT` (instantaneous öre/kWh).

**Auth**: JWT token stored in the HA config entry. `AuthError` in the coordinator triggers `entry.async_start_reauth()` automatically. No passwords are stored — BankID QR only.

**One facility per config entry**: `get_facilities()` deduplicates by `facilityid`; `config_flow` picks `facilities[0]`. Multiple meters require multiple entries.

**Sensor pattern**: Add sensors by extending `SENSOR_DESCRIPTIONS` in `sensor.py` with a `PowerHubSensorDescription` that includes a `value_fn` lambda.

**API pattern**: All API methods live in `PowerHubApiClient`. New endpoints follow the same `async with self._session.get(..., headers={"Authorization": f"Bearer {self._token}"})` pattern; raise `AuthError` on 401.

## Pitfalls

- The device has **no local API** — any local-only approach will not work.
- BankID polling uses an async generator (`bankid_poll`). Awaiting it incorrectly will break the config flow.
- `pyrightconfig.json` suppresses missing-import warnings (HA stubs unavailable locally); type errors in HA-provided classes are expected.
- Unit for spot price is `öre/kWh` (Swedish öre — not EUR, not SEK). Do not change this unit.

## Translation Keys

Add new user-visible strings to both `translations/en.json` and `translations/sv.json`.

## Reverse Engineering

See [docs/reverse_engineering.md](docs/reverse_engineering.md) for the full API findings and traffic capture setup.
