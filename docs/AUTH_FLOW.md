# Authentication Flow

## Overview

Cellcom uses a three-step OTP login flow. There is no persistent username/password
authentication — every new session requires an SMS code. However, the issued
`accessToken` is valid for ~20 hours, and a `refreshToken` can extend the session
without a new OTP for up to ~3 hours.

---

## First-Time Login (Config Flow)

```
User (HA UI)          Home Assistant          Cellcom API        User's Phone
     │                      │                      │                  │
     │  Add Integration      │                      │                  │
     │─────────────────────►│                      │                  │
     │                      │                      │                  │
     │  Enter phone number   │                      │                  │
     │─────────────────────►│                      │                  │
     │                      │── PUT /LoginStep1 ──►│                  │
     │                      │◄── { Guid } ─────────│                  │
     │                      │                      │── SMS OTP ──────►│
     │                      │                      │                  │
     │  Enter OTP from SMS   │                      │                  │
     │─────────────────────►│                      │                  │
     │                      │── PUT /LoginStep2 ──►│                  │
     │                      │◄── preliminary JWT ──│                  │
     │                      │                      │                  │
     │  Enter ID number      │                      │                  │
     │─────────────────────►│                      │                  │
     │                      │── PUT /LoginStep3 ──►│                  │
     │                      │◄── accessToken       │                  │
     │                      │    + refreshToken ───│                  │
     │                      │                      │                  │
     │                      │  Store tokens        │                  │
     │                      │  Create device       │                  │
     │◄─────────────────────│  Create sensors      │                  │
     │  Setup complete!      │                      │                  │
```

---

## Runtime — Token Refresh (Silent)

Runs automatically inside the coordinator before every data fetch:

```
access_token expires in < 5 minutes?
        │
       YES ──► POST /api/otp/RefreshToken (refreshToken)
                │
               OK ──► new accessToken saved to Storage ──► continue
                │
              FAIL ──► ConfigEntryAuthFailed ──► reauth notification
        │
        NO ──► use existing accessToken ──► fetch data
```

---

## Reauth Flow (When Token Expires Completely)

```
Coordinator detects HTTP 401
        │
        ▼
Raise ConfigEntryAuthFailed
        │
        ▼
HA shows persistent notification:
  "⚠️ Cellcom Energy — Re-authentication required"
        │
        ▼
User clicks notification ──► Reauth config flow opens
  (phone number pre-filled from stored config)
        │
        ▼
User receives new SMS OTP ──► enters code ──► enters ID ──► done
        │
        ▼
New tokens stored, coordinator resumes normally
```

---

## Token Details

Both tokens are signed JWTs using RS256, issued by `cellcom.idp`.

### `accessToken` Claims

| Claim | Value (example) |
|-------|----------------|
| `FIRST_NAME` | Hebrew name (base64-encoded UTF-8) |
| `LAST_NAME` | Hebrew name |
| `CONTACT_VALUE` | Subscriber phone number |
| `LOGIN_TYPE` | `OTPCUSTOMER` |
| `SCOPES` | `["PRIVATE_WEBSITE"]` |
| `CLIENT_ID` | `984193a2-8d29-11ea-bc55-0242ac130004` |
| `nbf` | Issued-at timestamp |
| `exp` | Expiry (~20 hours after `nbf`) |
| `iss` | `cellcom.idp` |
| `aud` | `cellcom.idp` |

### `refreshToken` Claims

Subset of accessToken — no user identity claims.
- `exp` — ~3 hours after issuance

---

## Persistence

Tokens stored via HA's encrypted `Store` helper under key:
`cellcom_energy.tokens`

```json
{
  "access_token": "<JWT>",
  "refresh_token": "<JWT>",
  "access_expires_at": 1777110120,
  "refresh_expires_at": 1777049367,
  "device_id": "<persistent-uuid>",
  "session_id": "<session-uuid>"
}
```

`device_id` is generated once on first install and kept stable across
HA restarts to avoid server-side fraud detection triggers.

---

## Security Notes

- Tokens are **never** written to HA logs.
- Phone number and ID number are masked in any diagnostic output.
- PII (phone, ID) is stored in the config entry's encrypted `data` dict.
- Tokens are stored in HA's encrypted Storage (AES-256 at rest).
