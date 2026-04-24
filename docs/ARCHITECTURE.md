# Architecture

## Component Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                       Home Assistant                            │
│                                                                 │
│   ┌──────────────┐    ┌───────────────┐    ┌────────────────┐  │
│   │ Config Flow  │    │  Coordinator  │    │    Entities    │  │
│   │              │    │  (30 min poll)│    │  sensor.* × 8  │  │
│   │ Step 1: Phone│    │               │    │  binary_sensor │  │
│   │ Step 2: OTP  │───►│ Tokens        │───►│  × 1           │  │
│   │ Step 3: ID   │    │ CellcomData   │    │                │  │
│   └──────────────┘    └───────┬───────┘    └────────────────┘  │
│                               │                                 │
│                    ┌──────────▼──────────┐                      │
│                    │    API Client       │                      │
│                    │  (aiohttp-based)    │                      │
│                    └──────────┬──────────┘                      │
└───────────────────────────────┼─────────────────────────────────┘
                                │ HTTPS / JSON
                    ┌───────────▼────────────┐
                    │  digital-api.cellcom   │
                    │       .co.il           │
                    └────────────────────────┘
```

## Module Responsibilities

| Module             | Responsibility                                          |
|--------------------|---------------------------------------------------------|
| `__init__.py`      | Entry setup/unload, platform forwarding                 |
| `api.py`           | HTTP client, JWT handling, all API calls                |
| `coordinator.py`   | Polling orchestration, data normalisation               |
| `config_flow.py`   | User onboarding and reauth UI                           |
| `const.py`         | Domain constant, API endpoints, default values          |
| `models.py`        | Typed dataclasses (`CellcomData`, `Invoice`, `Plan`)    |
| `sensor.py`        | Sensor entity classes                                   |
| `binary_sensor.py` | Binary sensor entity classes                            |
| `exceptions.py`    | Custom exception hierarchy                              |

## Data Flow

```
LoginStep1 ──┐
LoginStep2 ──┤── Config Flow (once) ──► accessToken + refreshToken
LoginStep3 ──┘                                    │
                                                  ▼
                              ┌───────────────────────────────┐
                              │      HA Storage (encrypted)   │
                              │  access_token, refresh_token  │
                              │  device_id, session_id        │
                              └────────────────┬──────────────┘
                                               │ loaded on every poll
                                               ▼
                              ┌───────────────────────────────┐
                              │     DataUpdateCoordinator     │
                              │  1. Check token expiry        │
                              │  2. Refresh if < 5 min left   │
                              │  3. Call 5 data endpoints     │
                              │     (asyncio.gather)          │
                              │  4. Parse → CellcomData       │
                              └────────────────┬──────────────┘
                                               │
                              ┌────────────────▼──────────────┐
                              │  Entities read coordinator    │
                              │  .data and push state +       │
                              │  attributes to HA             │
                              └───────────────────────────────┘
```

## Token Lifecycle

```
Login (OTP)
    │
    ▼
[accessToken ~20h] ──── every call uses Bearer token
    │
    ├─ expires in < 5min? ──► POST /refresh ──► new accessToken
    │                                                │
    │                          fails? ──────────────►│
    │                                                ▼
    └─ expired? ──────────────────────► ConfigEntryAuthFailed
                                                     │
                                         HA reauth notification
                                                     │
                                         User repeats OTP flow
```

## Threading Model

- All I/O is `async`/`await` via `aiohttp`.
- A single `aiohttp.ClientSession` is shared via `async_get_clientsession(hass)`.
- No blocking calls are made on the HA event loop.
- Token refresh is mutex-locked to prevent concurrent refresh races.

## Storage Schema

Tokens persisted under `Store(hass, 1, "cellcom_energy.tokens")`:

```json
{
  "access_token": "<JWT>",
  "refresh_token": "<JWT>",
  "access_expires_at": 1777110120,
  "refresh_expires_at": 1777049367,
  "device_id": "acfaaa-0e0-8d8-2567-7365413fc734",
  "session_id": "23175af-7a41-fadc-f7-36fa37cf72d7"
}
```
