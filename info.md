# ⚡ Cellcom Energy

Unofficial Home Assistant integration for **Cellcom Energy** (סלקום אנרג'י) —
the Israeli electricity provider.

## Features

- 💰 **Current bill** — amount, due date, invoice PDF link
- 📊 **Monthly consumption** — kWh usage and 12-month history
- 📋 **Tariff plan** — plan name, discount hours and percentage
- 🔔 **Outstanding bill alert** — binary sensor for automations
- 🛠️ **Developer Tools** — all raw API fields as entity attributes
- 🌐 **Bilingual** — Hebrew and English UI

## Quick Setup

1. Install via HACS
2. **Settings → Add Integration → "Cellcom Energy"**
3. Three-step login: phone number → SMS OTP → Israeli ID number
4. Done — device and sensors are created automatically

## Note

Cellcom's API provides **billing data only** (updated monthly).
For real-time smart meter readings, also install
[ha-iec](https://github.com/GuyKh/ha-iec).
