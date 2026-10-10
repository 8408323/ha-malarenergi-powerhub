# ha-powerhub-cloud

Home Assistant custom integration for the **PowerHub** — the HAN-port energy monitor made by [Bitvis AB](https://bitvis.se/) and sold by Swedish energy companies (Mälarenergi, Kraftringen, Boo Energi and [16 more](#supported-energy-companies)).

> **Status**: Working prototype — BankID auth + cloud API implemented.

## Support

If you find this integration useful, you can buy me a coffee ☕

[![Buy me a coffee](https://img.buymeacoffee.com/button-api/?text=Buy+me+a+coffee&emoji=&slug=jhara&button_colour=FFDD00&font_colour=000000&font_family=Cookie&outline_colour=000000&coffee_colour=ffffff)](https://www.buymeacoffee.com/jhara)

## Installation

### HACS (recommended)

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=8408323&repository=ha-powerhub-cloud&category=integration)

Or manually:

1. In HACS, go to **Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/8408323/ha-powerhub-cloud` as an **Integration**.
3. Search for **PowerHub** and click **Download**.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/malarenergi_powerhub/` to your HA `config/custom_components/` directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration**.
2. Search for *PowerHub*.
3. Choose your energy company.
4. Scan the BankID QR code that appears with the BankID app.

See the **[full setup guide](docs/setup.md) (including the dashboard)** for step-by-step instructions with screenshots.

## Features

- HA Energy dashboard compatible import/export/spot-price sensors
- Real-time power and per-phase current (1-minute resolution)
- Monthly insights: your average price vs. market, year-to-date consumption and production, baseload estimate
- Device diagnostics: Wi-Fi signal, firmware, uptime, HAN port state
- Writable fuse/power limits and notification preferences
- Push notification mirroring (energy company → HA sensor)
- Facility sharing services (create / revoke invitations)
- Automatic token re-auth when JWT expires

See the **[user manual](docs/user_manual.md)** for the full entity list and usage.

## Details

### Supported energy companies

| Energy company | Status |
|---|---|
| [Mälarenergi](https://www.malarenergi.se/el/elavtal/powerhub/) | Tested |
| Boo Energi | Confirmed working by a user |
| Bjäre Kraft, Borås Elhandel, Dala Energi, Falu Energi, Kinnekulle Energi, Kraftringen, Kvänum Energi, Landskrona Energi, Norrtälje Energi, Nossebro Energi, Skånska Energi, Södra Hallands Kraft, Tranås Energi, Trelleborgs Energi, Vaggeryds Energi, Vänerenergi, Varbergsortens Elkraft | Bitvis backend with BankID login exists; untested — please report! |

Another company not listed? Type its name in the setup dialog (lowercase, no spaces, å/ä/ö → a/a/o) and open an issue so it can be added.

### Dashboard panel

**How to get it:** nothing to add or configure. Once the integration is set up (v0.4.0 or later), a **PowerHub**
entry appears in Home Assistant's left sidebar for every user. Right after updating through HACS, restart Home
Assistant and reload the browser page (in the phone app: pull to refresh) so the new sidebar entry shows up. You can
also open it directly at `/powerhub`. Only administrators can change its settings.

A **PowerHub** sidebar panel shows grid import/export as an animated house picture, phase load against the main
fuse, today's energy, prices and device status. If Home Assistant's built-in **Bitvis** integration is set up for
the same hub, the panel uses its local real-time values (badge "Live (local)"); otherwise the 1-minute cloud values.

The PowerHub only measures the grid connection, so it can't tell where exported power comes from. Under
**Settings** in the panel you tick your local sources (solar, home battery, wind, generator/CHP, EV with V2H/V2G,
other) and whether you have a plain EV charger. Production sources are drawn as one node with an icon each; a V2G
car can feed the house from the garage. Optionally pick a combined production-power sensor, battery sensors and an
EV power sensor so their values appear in the picture. The panel's language follows Home Assistant by default
(English, Svenska, Norsk, Dansk, Suomi, Íslenska; others fall back to English) and can be set there too.
The panel's **Show PowerHub in the sidebar** setting hides it for everyone (it stays reachable at `/powerhub`); to hide
it just for yourself, use Home Assistant's own sidebar editing (long-press the sidebar title, or Profile → *Change the
order and hide items from the sidebar*).

![Panel](docs/images/13_panel_overview.jpg)

The panel source is in `frontend/` (React + Vite); `npm ci && npm run build` writes
`custom_components/malarenergi_powerhub/www/panel.js`, which is committed. `npm run dev` opens a preview with
synthetic data (`frontend/index.html` lists the URL flags).

### Works together with the built-in Bitvis Power Hub integration

Since **Home Assistant 2026.10** HA ships a [Bitvis Power Hub](https://www.home-assistant.io/integrations/bitvis) integration that reads the meter **locally** (UDP push on your LAN, no login). Use both:

| | Built-in `bitvis` (local) | This integration (cloud) |
|---|---|---|
| Real-time power, per-phase voltage/current, meter energy totals | ✅ best source — use for the Energy dashboard | 1-minute power and currents |
| Spot price, agreement, price model/zone | | ✅ |
| Monthly insights, year-to-date, baseload | | ✅ |
| Fuse/power limits, notification settings, sharing | | ✅ |

Both identify the hub by its MAC address, but HA keeps one device per integration, so the hub shows up as two devices — one local, one cloud. (On HA versions before 2026.8, if another integration such as a router's device tracker already claims the hub's MAC, the cloud device simply doesn't get the MAC.)

#### Network requirement for the local integration

The hub and Home Assistant must be on the **same subnet**, or your router must **forward UDP port 58220** traffic from the hub to HA (Bitvis' requirement). The hub appears to *broadcast* its readings, and broadcasts don't cross VLANs, so a plain "allow" firewall rule or an mDNS proxy alone is not enough — you need real UDP broadcast relaying/forwarding to HA, or put the hub on HA's network (e.g. UniFi *Virtual Network Override* on the hub's client page), or give HA an interface on the hub's VLAN. This integration (cloud) works regardless.

> Running both side by side hasn't been tested yet — the maintainer's hub is on a separate IoT VLAN. If you run both, please report how it goes in an issue.

### Hardware

| Property | Value |
|---|---|
| Manufacturer | Bitvis AB (OEM for the energy companies above) |
| SoC | Espressif ESP32 (OUI `94:54:C5`) |
| Connectivity | Wi-Fi 2.4 GHz |
| HAN port | RJ45 (Norwegian standard, P1/IEC 62056-21) |
| Meter | Kaifa MA304 |
| Cloud backend | Bitvis "Flow" platform — `<company>.prod.flow.bitv.is` |

The hub has no open TCP ports; it **pushes** meter readings over UDP on the LAN (what the built-in `bitvis` integration reads) and to Bitvis's cloud. This integration uses the same REST API as the energy companies' PowerHub apps.

### Authentication

Login uses **Swedish BankID** (same as your energy company's PowerHub app). During setup a QR code is displayed in the HA config flow — scan it with the BankID app on your phone.

The integration stores the JWT Bearer token in the HA config entry. When the token expires, HA triggers a re-auth flow automatically.

### Entities

The integration exposes ~40 entities — sensors, binary sensors, switches, numbers and selects. The full reference (entity IDs, units, writable controls, services) is in the [user manual](docs/user_manual.md).

### Repository name

Formerly **ha-malarenergi-powerhub** — renamed since it supports many energy companies. Existing HACS installs keep
working (GitHub redirects the old URL); the integration's internal domain `malarenergi_powerhub` is unchanged.

## Development

### Requirements

```
pip install pytest pytest-asyncio aioresponses aiohttp
```

### Run tests

```bash
python3 -m pytest tests/ -v
```

### Traffic capture (for further reverse engineering)

```bash
# Install mitmproxy
pip install mitmproxy

# Start capture proxy (optionally filter by device/phone IP)
CAPTURE_PHONE_IP=192.168.1.x mitmdump -s tools/capture.py --listen-port 8080 --ssl-insecure
```

See [docs/reverse_engineering.md](docs/reverse_engineering.md) for full findings on the cloud API.

## Disclaimer

The cloud APIs are internal to Bitvis and not officially supported; they may change without notice. For guaranteed-stable meter data use the built-in `bitvis` integration.

## Contributing

Pull requests are welcome. Please open an issue first to discuss what you'd like to change.

## License

MIT
