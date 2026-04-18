# User Manual — Mälarenergi PowerHub

Once the integration is set up (see [docs/setup.md](setup.md)), a single **PowerHub** device appears under *Settings → Devices & Services → Mälarenergi PowerHub*. This document describes every entity it exposes, what the writable controls actually do, and how to use the two services for sharing your facility.

For installation and BankID onboarding, see [docs/setup.md](setup.md).

---

## Table of contents

- [Device overview](#device-overview)
- [Sensors](#sensors)
  - [Energy — Energy dashboard compatible](#energy--energy-dashboard-compatible)
  - [Real-time power](#real-time-power)
  - [Per-phase power and current](#per-phase-power-and-current)
  - [Monthly insights](#monthly-insights)
  - [Device diagnostics](#device-diagnostics)
  - [Account and facility metadata](#account-and-facility-metadata)
  - [Sharing](#sharing)
  - [Push notifications](#push-notifications)
- [Binary sensors](#binary-sensors)
- [Switches — writable](#switches--writable)
- [Numbers — writable](#numbers--writable)
- [Selects — writable](#selects--writable)
- [Services](#services)
- [Update cadence](#update-cadence)
- [Re-authentication](#re-authentication)
- [Troubleshooting](#troubleshooting)

---

## Device overview

The integration creates **one device** per configured facility. All entities live under that device:

| Property | Value |
|---|---|
| Name | PowerHub |
| Manufacturer | Bitvis / Mälarenergi |
| Model | PowerHub (ESP32, Kaifa MA304) |

Device identifiers are the config entry ID, so re-adding the integration produces a fresh device (previous entities become unavailable).

---

## Sensors

### Energy — Energy dashboard compatible

| Entity | Unit | State class | Notes |
|---|---|---|---|
| `sensor.powerhub_import_today` | kWh | `TOTAL` | Grid import since midnight (Europe/Stockholm) |
| `sensor.powerhub_export_today` | kWh | `TOTAL` | Grid export since midnight |
| `sensor.powerhub_spot_price` | öre/kWh | none | Current Nordpool 15-minute bucket |

Use *Settings → Dashboards → Energy* and add the **import** and **export** sensors to the grid section. Spot price can drive automations directly — it resets every 15 minutes.

### Real-time power

Updated every 60 seconds from the most recent 1-minute power sample.

| Entity | Unit | Notes |
|---|---|---|
| `sensor.powerhub_power_import` | kW | Total instantaneous grid import |
| `sensor.powerhub_power_export` | kW | Total instantaneous grid export |

### Per-phase power and current

| Entity | Unit | Notes |
|---|---|---|
| `sensor.powerhub_power_l1_import` / `l2` / `l3` | kW | Per-phase import |
| `sensor.powerhub_power_l1_export` / `l2` / `l3` | kW | Per-phase export |
| `sensor.powerhub_current_l1` / `l2` / `l3` | A | Per-phase current |

> Per-phase values may read 0 A / 0 kW on some firmware revisions while total import/export is non-zero. This is a known upstream decode issue; see [issue tracker](https://github.com/8408323/ha-malarenergi-powerhub/issues).

### Monthly insights

Refreshed every 60 seconds. Values are derived server-side by Bitvis.

| Entity | Unit | Meaning |
|---|---|---|
| `sensor.powerhub_avg_price_this_month` | öre/kWh | Your volume-weighted average price this month |
| `sensor.powerhub_market_avg_price_this_month` | öre/kWh | Market average for your price zone |
| `sensor.powerhub_consumption_ytd` | kWh | Year-to-date consumption |
| `sensor.powerhub_production_ytd` | kWh | Year-to-date production |
| `sensor.powerhub_baseload_power` | kW | Estimated always-on baseload |

### Device diagnostics

Under the device card's *Diagnostic* section.

| Entity | Notes |
|---|---|
| `sensor.powerhub_wifi_rssi` | Signal strength (dBm) |
| `sensor.powerhub_sw_version` | Firmware version reported by the PowerHub |
| `sensor.powerhub_han_port_state` | State of the HAN/P1 port to the electricity meter |
| `sensor.powerhub_uptime` | Device uptime (seconds since boot) |
| `sensor.powerhub_power_limit` | Current power limit in kW (see numbers) |
| `sensor.powerhub_fcr_enabled` | `True` / `False` — FCR-D Down participation |

### Account and facility metadata

Read-only, sourced from your Mälarenergi account. Diagnostic.

| Entity | Notes |
|---|---|
| `sensor.powerhub_account_name` | Account holder |
| `sensor.powerhub_customer_number` | Mälarenergi customer number |
| `sensor.powerhub_facility_address` | Street + house number |
| `sensor.powerhub_meter_id` | Electricity meter serial |
| `sensor.powerhub_price_zone` | SE1 / SE2 / SE3 / SE4 |
| `sensor.powerhub_agreement_number` | First supply agreement |
| `sensor.powerhub_price_model` | e.g. `FIXED`, `SPOT` |

### Sharing

| Entity | State | Extra attributes |
|---|---|---|
| `sensor.powerhub_active_invitations` | Count of unredeemed invitations | `invitations[].id / code / claimed / expires / created` |
| `sensor.powerhub_invitees` | Comma-separated names | `count`, `invitees[].id / name / share_all_devices` |

The `code` attribute on `active_invitations` is what the recipient types into the Mälarenergi app.

### Push notifications

`sensor.powerhub_latest_notification` — the body of the most recent push notification Mälarenergi sent to your account. State is truncated to 255 characters; the full list lives in `extra_state_attributes.all_notifications`.

Useful as a trigger:

```yaml
trigger:
  platform: state
  entity_id: sensor.powerhub_latest_notification
action:
  service: notify.mobile_app_<your_phone>
  data:
    title: "{{ state_attr('sensor.powerhub_latest_notification', 'title') }}"
    message: "{{ states('sensor.powerhub_latest_notification') }}"
```

---

## Binary sensors

| Entity | Meaning |
|---|---|
| `binary_sensor.powerhub_has_solar` | Whether your facility is flagged as having solar |
| `binary_sensor.powerhub_has_battery` | Whether a battery is registered |

These mirror the writable switches below — they exist so automations can read the flags without relying on a switch entity.

---

## Switches — writable

All switches are *config* category (under the device settings panel, not the dashboard by default).

### Facility flags

| Entity | Effect when toggled |
|---|---|
| `switch.powerhub_has_solar` | Writes `hasSolar` to the facility profile |
| `switch.powerhub_has_battery` | Writes `hasBattery` to the facility profile |

> **These are server-side metadata, not device controls.** Toggling them does not turn solar/battery hardware on or off — it updates your Mälarenergi facility profile so their apps know what you have installed. Use when you add or remove solar/battery hardware.

### Push notification preferences

Each toggle maps to the matching preference in the Mälarenergi app (*Notifications* section). Changes take effect on the next server sync.

| Entity | Mälarenergi setting |
|---|---|
| `switch.powerhub_notify_total_power` | Total power over limit |
| `switch.powerhub_notify_phase_load` | Individual phase over limit |
| `switch.powerhub_notify_control_disabled_exceeded_phase` | Phase exceeded *while* fuse control is disabled |
| `switch.powerhub_notify_control_disabled_exceeded_power` | Power exceeded *while* fuse control is disabled |
| `switch.powerhub_notify_control_enabled_exceeded_phase` | Phase exceeded *while* fuse control is enabled |
| `switch.powerhub_notify_control_enabled_exceeded_power` | Power exceeded *while* fuse control is enabled |

---

## Numbers — writable

### Facility attributes

| Entity | Unit | Range | Writes to |
|---|---|---|---|
| `number.powerhub_area` | m² | 1–2000 | Facility `area` |
| `number.powerhub_occupants` | — | 1–20 | Facility `occupants` |

These are used by Mälarenergi to personalise insights (e.g. "your baseload per occupant"). No effect on the device.

### Power and fuse limits — *use with care*

| Entity | Unit | Range | Step |
|---|---|---|---|
| `number.powerhub_fuse_limit_set` | A | 1–63 | 1 |
| `number.powerhub_power_limit_set` | kW | 0.1–100.0 | 0.1 |

These are the soft limits the PowerHub uses to notify you (and, if *fuse control* is enabled, to act). The current effective limit is mirrored as `sensor.powerhub_power_limit`. Setting a value lower than your actual load can trigger constant notifications or, if control is active, disconnect loads — double-check before changing.

---

## Selects — writable

| Entity | Options | Writes to |
|---|---|---|
| `select.powerhub_fuse_size` | `A10`, `A16`, `A20`, `A25`, `A32`, `A35`, `A50`, `A63` | `fuseSize` (parsed to int, e.g. `A20` → `20`) |
| `select.powerhub_heating_type` | `DISTRICT_HEATING`, `ELECTRIC`, `HEATING_PUMP`, `GAS`, `OIL`, `WOOD`, `NONE` | `heatingType` |
| `select.powerhub_facility_type` | `VILLA`, `APARTMENT`, `TOWNHOUSE`, `CABIN`, `OTHER` | `type` |
| `select.powerhub_ev_type` | `NONE`, `ONE_PHASE`, `THREE_PHASE` | `evType` |

Fuse size is the *installed* main fuse rating (metadata) — distinct from the writable `fuse_limit_set` number, which is the PowerHub's soft trigger threshold.

---

## Services

Exposed under *Developer Tools → Services*, namespace `malarenergi_powerhub`.

### `malarenergi_powerhub.create_invitation`

Creates a sharing invitation — gives someone read access to your facility in the Mälarenergi app.

```yaml
service: malarenergi_powerhub.create_invitation
data:
  share_all_devices: true   # optional, default true
  # facility_id is optional — omit if you only have one facility configured
```

After calling, the new invitation appears in `sensor.powerhub_active_invitations`'s `invitations` attribute. The `code` field is what the recipient enters in the app.

### `malarenergi_powerhub.delete_invitation`

Revokes an unredeemed invitation.

```yaml
service: malarenergi_powerhub.delete_invitation
data:
  invitation_id: "7adfa928-4081-4c3e-a27d-55c3833fd383"
```

Get the `invitation_id` from the `invitations[].id` attribute of `sensor.powerhub_active_invitations`. Deleting a *claimed* invitation does not revoke the invitee's access — to remove an invitee you'll need to use the Mälarenergi app.

---

## Update cadence

- Polling interval: **60 seconds**.
- Spot price resolution: 15-minute buckets.
- Real-time power / per-phase sensors: 1-minute resolution server-side — values may repeat across two polls if the backend hasn't published a new sample yet.
- Facility attributes, account profile, supply agreements, and facility info are fetched **once** on first successful update and cached. Toggling a writable attribute refreshes the cache.

---

## Re-authentication

JWT tokens obtained from BankID expire. When that happens:

1. HA surfaces a *Re-authentication required* notification for **Mälarenergi PowerHub**.
2. Click the notification — the same BankID QR flow from setup appears.
3. Scan with the BankID app. Polling resumes automatically.

No entities are deleted during re-auth — they just hold their last value until the new token takes effect.

---

## Troubleshooting

**Entities show `unknown` or `unavailable`**
The first poll after setup takes up to 60 seconds. If it persists, check *Settings → System → Logs* for warnings from `custom_components.malarenergi_powerhub`.

**`sensor.powerhub_export_today` stays at 0 even with solar**
Confirm `binary_sensor.powerhub_has_solar` is `on`. If not, toggle `switch.powerhub_has_solar`. Export data is only published by Mälarenergi once the facility is flagged with solar.

**Per-phase power/current sensors read 0**
Known limitation — see the note under *Per-phase power and current*. Total import/export are unaffected.

**Changing a writable entity doesn't stick**
Values are written then the coordinator requests a refresh. If the server rejects the change (e.g. fuse size out of bounds for your agreement) the sensor reverts on the next poll. Check logs for `API error:` warnings.

**Services don't show up in Developer Tools**
The services only register after the integration successfully loads. If setup is stuck on re-auth, they won't appear — complete the BankID flow first.
