# Implementation Plan — Cellcom Energy for Home Assistant

> A custom Home Assistant integration that connects to Cellcom Energy
> (Israeli electricity provider — סלקום אנרג'י) and exposes billing,
> consumption, and tariff data as sensors with rich attributes.

---

## Goals

1. Provide Home Assistant users with visibility into their Cellcom Energy
   account: bills, consumption history, tariff plan details.
2. Expose **all** raw API data as entity attributes so users can build
   templates, automations, and dashboards without code changes.
3. Publish to HACS as a maintained community integration.
4. Follow Home Assistant integration quality standards (Silver tier target).

## Non-Goals (v1.0)

- Real-time meter readings — Cellcom does not expose them via their API.
  Recommend [`ha-iec`](https://github.com/GuyKh/ha-iec) for this purpose.
- Bill payment or tariff plan modification (write actions).
- Multi-account support within a single config entry (use multiple entries).

---

## Phased Roadmap

### Phase 0 — Project Bootstrap ✅
- [x] Repository structure with `custom_components/cellcom_energy/`
- [x] `manifest.json` with HACS metadata
- [x] `hacs.json` for HACS store compatibility
- [x] `.github/workflows/validate.yml` (hassfest + HACS action)
- [x] `.gitignore` excluding secrets and research files
- [x] `LICENSE` (MIT)
- [x] `.vscode/launch.json` for HA devcontainer debugging
- [x] All documentation MD files

### Phase 1 — API Client (`api.py`)
- [ ] `CellcomEnergyClient` class using `aiohttp.ClientSession`
- [ ] Persistent `DeviceId` and `SessionID` UUID generation
- [ ] Three-step OTP login:
  - `async_login_step1(phone) → guid`
  - `async_login_step2(guid, otp) → preliminary_jwt`
  - `async_login_step3(preliminary_jwt, id_number) → Tokens`
- [ ] `async_refresh_token(refresh_token) → Tokens`
- [ ] Data endpoints:
  - `async_get_customer_init()` — subscriber product list
  - `async_get_all_products_auth(ban, subscriber)` — meter and plan details
  - `async_get_full_main_auth(ban)` — monthly consumption history
  - `async_get_all_invoices_auth(ban)` — invoice list with kWh
  - `async_get_invoice_data(ban)` — current billing period summary
- [ ] Custom exception hierarchy (see `exceptions.py`)
- [ ] Retry logic with exponential backoff on 5xx
- [ ] Unit tests with recorded API fixtures

### Phase 2 — Config Flow (`config_flow.py`)
- [ ] Step 1: phone number input → triggers `LoginStep1`
- [ ] Step 2: OTP code input → triggers `LoginStep2`
- [ ] Step 3: ID number input → triggers `LoginStep3`
- [ ] Friendly error messages for invalid OTP, wrong ID, expired code
- [ ] `async_step_reauth` triggered on `ConfigEntryAuthFailed`
- [ ] `unique_id` set from BAN to prevent duplicate entries
- [ ] "Resend OTP" action between steps

### Phase 3 — Data Coordinator (`coordinator.py`)
- [ ] Subclass `DataUpdateCoordinator[CellcomData]`
- [ ] Default update interval: 30 minutes
- [ ] Pre-refresh access token when expiry is less than 5 minutes away
- [ ] Raise `ConfigEntryAuthFailed` on HTTP 401
- [ ] Parse all API responses into `CellcomData` dataclass
- [ ] Persist refreshed tokens to HA Storage on every cycle

### Phase 4 — Entity Platforms
- [ ] `sensor.py` — 8 sensors (see `ENTITIES.md`)
- [ ] `binary_sensor.py` — 1 entity (`has_outstanding_bill`)
- [ ] Single shared `DeviceInfo` for unified device page
- [ ] Rich attributes for all entities
- [ ] Correct `state_class` and `device_class` for Energy Dashboard

### Phase 5 — Localization
- [ ] `strings.json` (English base)
- [ ] `translations/en.json`
- [ ] `translations/he.json` (Hebrew)
- [ ] Options flow: update interval, enable diagnostic sensors

### Phase 6 — Testing
- [ ] Unit tests: `api.py` (100% target)
- [ ] Integration tests: `config_flow.py`
- [ ] Integration tests: `coordinator.py`
- [ ] End-to-end reauth flow test
- [ ] Framework: `pytest-homeassistant-custom-component`

### Phase 7 — Documentation
- [ ] README with screenshots and HACS badge
- [ ] `info.md` HACS preview page
- [ ] Example dashboard YAML
- [ ] Example automation YAML

### Phase 8 — Release
- [ ] Version `v0.1.0` in `manifest.json`
- [ ] GitHub Release with auto-generated changelog
- [ ] HACS default repository submission (after maturity)

---

## Estimated Effort

| Phase | Deliverable           | Est. LOC |
|-------|-----------------------|----------|
| 0     | Scaffold + docs       | ~150     |
| 1     | API client            | ~400     |
| 2     | Config flow           | ~250     |
| 3     | Coordinator           | ~200     |
| 4     | Entities              | ~350     |
| 5     | Localization          | ~150     |
| 6     | Tests                 | ~600     |
| 7     | Docs                  | —        |
| 8     | Release               | —        |
| **Σ** |                       | **~2100**|

---

## Known Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Cellcom changes API endpoints | Integration breaks silently | Version-pin User-Agent; add mock CI tests; maintain hotfix branch |
| `refreshToken` lifetime (~3h) is short | Frequent reauth prompts | Investigate undiscovered refresh endpoint; fallback to reauth |
| No real-time readings in Cellcom API | Feature gap | Document clearly; recommend `ha-iec` for real-time |
| ID number is PII | Privacy concern | Store via HA Storage encryption; never log |

---

## Definition of Done (v1.0)

- [ ] HACS installation works end-to-end from custom repository
- [ ] OTP config flow completes successfully from HA UI
- [ ] All 9 entities display correct data
- [ ] Token auto-refresh operates silently
- [ ] Reauth notification appears on auth failure
- [ ] Entity attributes are visible in Developer Tools → States
- [ ] Hebrew and English translations are complete
- [ ] `hassfest` CI check passes
- [ ] HACS validation CI check passes
- [ ] README includes installation screenshots
- [ ] Integration runs stably for 7+ days without manual intervention
