# Setup Guide — Mälarenergi PowerHub

## Prerequisites

- A Mälarenergi electricity subscription with a PowerHub device installed
- [HACS](https://hacs.xyz/) installed in Home Assistant
- The **BankID** app on your phone (same app used for the Mälarenergi app)

---

## Step 1 — Install via HACS

1. Open HACS in Home Assistant
2. Go to **Integrations** → click the three-dot menu (⋮) → **Custom repositories**
3. Add: `https://github.com/8408323/ha-malarenergi-powerhub` — category: **Integration**
4. Search for **Mälarenergi PowerHub** and click **Download**
5. Restart Home Assistant

---

## Step 2 — Add the integration

1. Go to **Settings → Devices & Services → Integrations**
2. Click **+ Add integration** and search for **Mälarenergi PowerHub**
3. A dialog appears with a QR code:

   ![BankID QR code dialog](images/setup_qr_dialog.png)

---

## Step 3 — Authenticate with BankID

1. Open the **BankID** app on your phone
2. Tap **Scan QR code**
3. Point your camera at the QR code shown in the Home Assistant dialog
4. Approve the login in BankID

   > **Note:** The QR code rotates every few seconds — scan it quickly, or click **Submit** in the dialog to refresh it.

5. Once approved, the integration completes automatically

---

## Step 4 — Verify sensors

After authentication, three sensors are created under your facility address:

| Entity | Description | Unit |
|---|---|---|
| `sensor.malarenergi_energy_consumption` | Today's energy consumption (midnight → now) | Wh |
| `sensor.malarenergi_energy_production` | Today's solar/production (0 if no solar) | Wh |
| `sensor.malarenergi_spot_price` | Current Nordpool spot price (SE3) | öre/kWh |

These sensors update every 60 seconds and are compatible with the **HA Energy dashboard**.

---

## Re-authentication

When the JWT token expires (typically after a few months), Home Assistant will show a notification requesting re-authentication. Follow the same BankID QR process to renew the token.

---

## Troubleshooting

**Dialog appears blank / no QR code**
- Ensure you are running the latest version (check HACS → Mälarenergi PowerHub → three-dot menu → Update information → Redownload)
- Restart Home Assistant after updating

**BankID login fails**
- Make sure you are using the same personal identity number registered with Mälarenergi
- Try closing and reopening the BankID app

**No facilities found**
- Your Mälarenergi account must have an active PowerHub device registered
