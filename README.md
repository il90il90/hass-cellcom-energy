# ⚡ Cellcom Energy — Home Assistant Integration

[![HACS Custom](https://img.shields.io/badge/HACS-Custom-orange.svg?logo=home-assistant-community-store)](https://hacs.xyz)
[![GitHub Release](https://img.shields.io/github/v/release/il90il90/hass-cellcom-energy?label=release)](https://github.com/il90il90/hass-cellcom-energy/releases)
[![HA Minimum Version](https://img.shields.io/badge/Home%20Assistant-%3E%3D2024.1-blue?logo=home-assistant)](https://www.home-assistant.io/)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

Unofficial Home Assistant integration for **Cellcom Energy** (סלקום אנרג'י) —
the Israeli electricity provider.

Exposes your billing data, monthly consumption, tariff plan details, and more
as HA sensors with **rich attributes** that you can use in automations,
templates, and dashboards.

---

## ✨ Features

| Feature | Details |
|---------|---------|
| 💰 Current bill | Amount, due date, invoice PDF link |
| 📊 Monthly consumption | kWh per billing cycle, 12-month history |
| 📋 Tariff plan | Plan name, discount hours, discount % |
| 💳 Payment info | Card type, billing method, email destination |
| 🔔 Outstanding bill alert | Binary sensor triggers automations |
| 🔄 Auto token refresh | Runs silently; prompts only when re-login needed |
| 🛠️ Developer Tools | **All raw API fields** exposed as entity attributes |
| 🌐 Bilingual UI | Hebrew and English translations |

---

## ⚠️ Important Limitations

Cellcom Energy's API **does not expose real-time or hourly meter readings** —
billing data is updated monthly by the Israeli Electric Corporation.

For real-time smart meter readings (15-minute intervals), install the companion
integration:
👉 **[ha-iec](https://github.com/GuyKh/ha-iec)** — connects directly to IEC's API

You can use both integrations together: IEC for consumption data, Cellcom for
cost and billing information.

---

## 🛠️ Installation

### Method 1 — Via HACS (Recommended)

> HACS must be installed. See [hacs.xyz](https://hacs.xyz) if you haven't set it up.

**Step 1:** Add this repository as a custom HACS source.

Click the button below, or follow the manual steps:

[![Add to HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=il90il90&repository=hass-cellcom-energy&category=integration)

**Manual steps:**
1. In Home Assistant, go to **HACS → Integrations**
2. Click the three-dot menu `⋮` in the top-right corner
3. Select **Custom repositories**
4. In the **Repository** field, enter:
   ```
   https://github.com/il90il90/hass-cellcom-energy
   ```
5. Set **Category** to `Integration`
6. Click **ADD**

**Step 2:** Install the integration.

1. Search for **"Cellcom Energy"** in HACS → Integrations
2. Click **Download**
3. **Restart Home Assistant**

---

### Method 2 — Manual Installation

1. Download the [latest release](https://github.com/il90il90/hass-cellcom-energy/releases/latest)
2. Extract the archive
3. Copy the `custom_components/cellcom_energy/` folder into your HA
   configuration directory:
   ```
   <config>/custom_components/cellcom_energy/
   ```
4. **Restart Home Assistant**

---

## ⚙️ Configuration

### Step 1 — Log in to Cellcom in your browser

Open the Cellcom login page and sign in with your phone number and SMS code:

👉 **[https://cellcom.co.il/Authentication/otp-login-page/](https://cellcom.co.il/Authentication/otp-login-page/)**

---

### Step 2 — Copy your token from the browser console

After logging in, open the **browser console** (press **F12** → click the **Console** tab).

Run one of these commands. **Try the first one first** — it copies the access token:

```javascript
copy(localStorage.getItem('auth_token').replace(/"/g,''))
```

If that does not work, try the refresh token:

```javascript
copy(localStorage.getItem('refresh_token').replace(/"/g,''))
```

You will see `undefined` printed in the console — that is normal.
Your token is now in the clipboard.

> **Tip:** The command removes any surrounding quote characters automatically.

---

### Step 3 — Paste the token into Home Assistant

1. Go to **Settings → Devices & Services**
2. Click **+ Add Integration**
3. Search for **"Cellcom Energy"**
4. In the dialog that opens, **paste** (Ctrl+V) the token into the field
5. Click **Submit**

The integration validates the token, finds your energy account, and creates all sensors automatically.

> Your token is stored in HA's encrypted storage and is never logged in plain text.

---

## 📊 Available Entities

After setup you will have:

**Sensors:**
- `sensor.cellcom_current_bill` — Current bill amount (₪)
- `sensor.cellcom_monthly_consumption_kwh` — Monthly kWh
- `sensor.cellcom_meter` — Meter number and contract details
- `sensor.cellcom_tariff_plan` — Active tariff plan
- `sensor.cellcom_total_due` — Outstanding balance (₪)
- `sensor.cellcom_next_bill_date` — Next payment date
- `sensor.cellcom_customer_info` *(diagnostic)* — Account holder info
- `sensor.cellcom_token_expiry` *(diagnostic)* — Auth token health

**Binary Sensors:**
- `binary_sensor.cellcom_has_outstanding_bill` — `on` when payment is due

See [docs/ENTITIES.md](docs/ENTITIES.md) for a full attribute reference.

---

## 🛠️ Developer Tools — Exploring Raw Data

All data returned by the Cellcom API is preserved as entity attributes.

To explore it:
1. Go to **Developer Tools → States**
2. Filter by `cellcom` in the entity search box
3. Click any entity to see its full attribute tree

Example attributes on `sensor.cellcom_current_bill`:
```yaml
state: "432.10"
attributes:
  bill_id: "2AE2752D-CBC2-EFAF-19A0-F6AA9A22DC00"
  bill_date: "2026-03-20"
  bill_due_date: "2026-05-04"
  period_start: "2026-02-21"
  period_end: "2026-03-20"
  main_amount: 432
  sub_amount: 10
  bill_url: "https://cellcom.co.il/selfcare/InvoicePageNew?id=..."
  services: ["ENERGY"]
  ban: "403063083"
```

---

## 🤖 Example Automation

Get notified when your electricity bill is high:

```yaml
automation:
  - alias: "High Electricity Bill Alert"
    trigger:
      - platform: state
        entity_id: sensor.cellcom_current_bill
    condition:
      - condition: template
        value_template: "{{ states('sensor.cellcom_current_bill') | float > 500 }}"
    action:
      - service: notify.mobile_app_your_phone
        data:
          title: "⚡ High electricity bill"
          message: >
            Current bill: ₪{{ states('sensor.cellcom_current_bill') }}.
            Due on {{ state_attr('sensor.cellcom_current_bill', 'bill_due_date') }}.
          data:
            url: "{{ state_attr('sensor.cellcom_current_bill', 'bill_url') }}"
```

---

## 📋 Example Dashboard Card

```yaml
type: entities
title: ⚡ Cellcom Energy
entities:
  - entity: sensor.cellcom_current_bill
    name: Current Bill
  - entity: sensor.cellcom_next_bill_date
    name: Due Date
  - entity: sensor.cellcom_monthly_consumption_kwh
    name: Monthly kWh
  - entity: sensor.cellcom_tariff_plan
    name: Tariff Plan
  - entity: binary_sensor.cellcom_has_outstanding_bill
    name: Outstanding Balance
```

---

## 🔄 Re-authentication

The integration uses short-lived JWT tokens (~20 hours). When a token expires
and cannot be refreshed automatically, Home Assistant will show a notification:

> ⚠️ **Cellcom Energy — Re-authentication required**

Click it to repeat the OTP flow. Your phone number is pre-filled;
you only need to enter the new SMS code and your ID number.

---

## 🐞 Troubleshooting

**Integration not found after installation:**
Ensure you restarted Home Assistant after downloading via HACS.

**OTP code not received:**
Check that the phone number matches the one registered with Cellcom.
Wait 60 seconds before requesting a new code.

**Sensors show "unavailable":**
Check `Settings → Devices & Services → Cellcom Energy` for an error badge.
Enable debug logging:
```yaml
logger:
  logs:
    custom_components.cellcom_energy: debug
```

**"Re-authentication required" keeps appearing:**
The refresh token (~3 hours) may be expiring before the access token (~20 hours).
This is a known limitation. The integration will prompt for re-login every ~20 hours
until a refresh endpoint is discovered.

---

## 🤝 Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md).

Report issues at:
👉 [github.com/il90il90/hass-cellcom-energy/issues](https://github.com/il90il90/hass-cellcom-energy/issues)

---

## 📜 License

[MIT](LICENSE) — see the file for details.

---

## ⚖️ Disclaimer

This is an **unofficial** integration, not affiliated with, endorsed by, or
connected to Cellcom Israel Ltd. in any way.

The Cellcom API used here is reverse-engineered from the public web portal
and may change without notice. Use at your own risk.
