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

## Dashboard

![PowerHub panel](docs/images/13_panel_overview.jpg)

A **PowerHub** entry appears in the sidebar as soon as the integration is set up — nothing to add or configure
(after updating, restart Home Assistant and reload the browser). It shows grid import/export as an animated house,
phase load against your main fuse, today's energy, prices and device status.

Under **Settings** in the panel you tick your own sources — solar panels, home battery, wind turbine, generator,
EV — and each one is drawn on the picture with its own cable. The grid can come in as an overhead line or an
underground cable, and the panel speaks English, Svenska, Norsk, Dansk, Suomi and Íslenska.

## Features

- Import/export and spot-price sensors for the HA Energy dashboard
- Real-time power and per-phase current (1-minute resolution)
- Monthly insights, year-to-date, baseload; device diagnostics
- Writable fuse/power limits and notification settings; facility sharing
- Automatic re-authentication with BankID

Full entity list: **[user manual](docs/user_manual.md)**.

## Supported energy companies

| Energy company | Status |
|---|---|
| [Mälarenergi](https://www.malarenergi.se/el/elavtal/powerhub/) | ✅ Tested |
| [Boo Energi](https://www.booenergi.se/) | ✅ Confirmed by a user |
| [Bjäre Kraft](https://www.bjarekraft.se/), [Borås Elhandel](https://boraselhandel.se/), [Dala Energi](https://dalaenergi.se/), [Falu Energi & Vatten](https://fev.se/), [Kinnekulle Energi](https://kinnekulleenergi.se/), [Kraftringen](https://www.kraftringen.se/), [Kvänum Energi](https://kvanumenergi.se/), [Landskrona Energi](https://landskronaenergi.se/), [Norrtälje Energi](https://www.norrtaljeenergi.se/), [Nossebro Energi](https://nossebroenergi.se/), [Skånska Energi](https://www.skanska-energi.se/), [Södra Hallands Kraft](https://www.sodrahallandskraft.se/), [Tranås Energi](https://tranasenergi.se/), [Trelleborgs Energi](https://trelleborgsenergi.se/), [Vaggeryds Energi](https://www.vaggerydsenergi.se/), [VänerEnergi](https://vanerenergi.se/), [Varbergsortens Elkraft](https://vbgelkraft.se/) | Available, untested — please report! |

Company missing? Type its name in the setup dialog (lowercase, no spaces, å/ä/ö → a/a/o) and open an issue.

## Built-in Bitvis integration

Since **Home Assistant 2026.10**, the built-in [Bitvis Power Hub](https://www.home-assistant.io/integrations/bitvis)
integration reads the meter **locally** (needs the hub on the same subnet as HA). Use it for real-time power and
the Energy dashboard, and this integration for prices, insights, limits and settings — the panel picks up the
local values automatically.

## Development

The panel lives in `frontend/` (React + Vite): `npm ci && npm run build` writes the committed
`custom_components/malarenergi_powerhub/www/panel.js`; `npm run dev` previews it with synthetic data.
Tests: `python3 -m pytest tests/`. API findings: [docs/reverse_engineering.md](docs/reverse_engineering.md).

## Disclaimer

The cloud APIs are internal to Bitvis and may change without notice. Formerly named **ha-malarenergi-powerhub**;
old HACS installs keep working.

## License

MIT
