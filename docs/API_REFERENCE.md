# Cellcom Digital API Reference

> **Disclaimer:** This API is reverse-engineered from the official Cellcom
> self-care web portal (`cellcom.co.il`) in April 2026. It is undocumented,
> unofficial, and may change without notice.

**Base URL:** `https://digital-api.cellcom.co.il`

---

## Common Request Headers

The following headers are sent on **all** requests:

| Header | Value | Notes |
|--------|-------|-------|
| `ClientID` | `984193a2-8d29-11ea-bc55-0242ac130004` | Fixed web-client identifier |
| `DeviceId` | `<UUID>` | Generated once per install, persisted to Storage |
| `SessionID` | `<UUID>` | Generated per HA session |
| `Content-Type` | `application/json` | |
| `Accept` | `application/json, text/plain, */*` | |
| `Origin` | `https://cellcom.co.il` | Required for CORS |
| `Referer` | `https://cellcom.co.il/` | |
| `User-Agent` | Chrome/147 string | Server may check this |

Authenticated data requests additionally include:

```
Authorization: Bearer <accessToken>
```

> **Note:** reCAPTCHA tokens (`x-cell-recaptcha-token`) are present in
> browser requests but **not validated server-side** for LoginStep3 or
> any data endpoints. The OTP flow works without them.

---

## Authentication Endpoints

### `PUT /api/otp/LoginStep1`

Initiates the login flow. Sends an SMS OTP to the subscriber's registered phone.

**Request body:**
```json
{
  "Subscriber": "0502959996",
  "IsExtended": false,
  "ProcessType": "",
  "OtpOrigin": "main OTP"
}
```

**Success response (`ReturnCode: 0`):**
```json
{
  "Header": { "ReturnCode": 0, "ReturnCodeMessage": "SUCCESS" },
  "Body": { "Guid": "daa292a3-45c3-473d-8350-8d95b8357a9f" }
}
```

**Error codes (ReturnCode ≠ 0):**
- `1001` — Subscriber not found
- `1002` — Too many OTP attempts, try again later

---

### `PUT /api/otp/LoginStep2`

Verifies the SMS OTP code. Returns a preliminary JWT for Step 3.

**Request body:**
```json
{
  "Guid": "<guid-from-step1>",
  "OtpCode": "055672",
  "Subscriber": "0502959996",
  "RestrictCode": "",
  "TermsAccepted": false,
  "CheckPhoneNumber": "",
  "LoginType": "",
  "idNumber": "",
  "CustomerEmail": "",
  "ProcessType": "",
  "OtpOrigin": "main OTP",
  "OriginProcess": ""
}
```

**Success response:** Returns a preliminary JWT in the body.
The token has `LOGIN_TYPE: OTPSUBSCRIBER` and limited scope — only usable for Step 3.

---

### `PUT /api/otp/LoginStep3`

Verifies the Israeli ID number. Returns the full production token pair.

**Additional header:**
```
Authorization: Bearer <preliminary-jwt-from-step2>
```

**Request body:**
```json
{
  "Subscriber": "0502959996",
  "IdNumber": "201236957",
  "Scope": "PRIVATE_WEBSITE",
  "Code": "",
  "OtpOrigin": "main OTP"
}
```

**Success response:**
```json
{
  "Header": { "ReturnCode": 0, "ReturnCodeMessage": "SUCCESS" },
  "Body": {
    "isSuccess": true,
    "extra": {
      "accessToken": "<JWT>",
      "refreshToken": "<JWT>",
      "tokenDet": {
        "access_token": "<JWT>",
        "refresh_token": "<JWT>",
        "expires_in": 71552,
        "token_type": "client_credentials",
        "scopes": ["PRIVATE_WEBSITE"]
      }
    }
  }
}
```

Token lifetimes (observed):
- `accessToken` — ~20 hours (`expires_in: 71552`)
- `refreshToken` — ~3 hours

---

## Data Endpoints

All data endpoints require `Authorization: Bearer <accessToken>`.

### `PUT /api/General/CustomerInit`

Returns the list of all products (mobile, internet, **Energy**) on the account.

**Key response fields (Energy subscriber):**
```json
{
  "subscribersByProduct": {
    "Energy": [{
      "ban": "403063083",
      "productSubscriberNo": "4446400775",
      "productId": "47886625",
      "productStatus": "A",
      "pricePlanCode": "A8HH",
      "pricePlanDesc": "עובדים מהבית"
    }]
  }
}
```

---

### `PUT /api/SelfCare/GetSelfcareDataOnboarding`

Returns subscriber metadata per product.

**Key response fields (Energy):**
```json
{
  "productsAndServicesDetails": {
    "Energy": [{
      "customerAddress": "תפוח 20 ,נתיבות",
      "productStatus": "Active",
      "subscriberNumber": "4446400775",
      "ban": "403063083",
      "packageName": "עובדים מהבית",
      "assetExternalId": "330303466",
      "isEnergyBundle": false
    }]
  }
}
```

---

### `PUT /api/SelfCare/InvoiceData`

Returns a summary of the current billing period for a given BAN.

**Key response fields:**
```json
{
  "customerPerBan": {
    "totalSum": "495.05",
    "periodStartDate": "01/03/2026",
    "periodEndDate": "31/03/2026",
    "billDueDate": "04/05/2026",
    "invoiceNo": "372755320",
    "paymentType": "CC",
    "creditCardTypeDesc": "לאומי קארד",
    "emailBillDest": "user@example.com"
  }
}
```

---

### `PUT /api/Ibill/GetAllInvoicesAuth`

Returns invoice list per BAN with amounts and kWh.

**Key response fields:**
```json
{
  "dataInvoices": [{
    "guidId": "2AE2752D-CBC2-EFAF-19A0-F6AA9A22DC00",
    "ban": "403063083",
    "cycle_date": 20260321,
    "fullCycleDate": "20.03.26 - 21.02.26",
    "invoivePrice": {
      "price": "432.10",
      "amount": "432",
      "amountAgorot": "10"
    },
    "isEnergy": true,
    "listServices": ["ENERGY"]
  }]
}
```

---

### `PUT /api/Ibill/GetFullMainAuth`

Returns monthly consumption history with kWh data.

**Key response fields:**
```json
{
  "history": [{
    "ban": 403063083,
    "cycleDate": 20260321,
    "billPeriods": "20.03.26 - 21.02.26",
    "cycleMonthName": "מרץ",
    "periodYear": "2026",
    "kwhDetails": { "kwh": "2340" },
    "amountData": { "price": "432.10" }
  }]
}
```

---

### `PUT /api/Ibill/GetAllProductsAuth`

Returns meter number, contract number, tariff plan details and comments.

**Key response fields:**
```json
{
  "allDetailsCliProduct": [{
    "detailsType": "ENERGY",
    "allDalDetailsCli": [{
      "title": "מספר מונה",
      "titleDescription": "6724246364",
      "subTitle": "מספר חוזה",
      "subTitleDescription": "345703607",
      "address": "תפוח 20 נתיבות",
      "listPlanDtlText": [["פרטי תוכנית עיקריים: ..."]],
      "listCommentText": [["* נתוני צריכת החשמל..."]]
    }]
  }]
}
```

---

## Error Handling Strategy

| Condition | Action |
|-----------|--------|
| HTTP 200 + `ReturnCode != 0` | Raise `CellcomAPIError` with code + message |
| HTTP 401 | Attempt token refresh; if that fails → `ConfigEntryAuthFailed` |
| HTTP 429 | Wait and retry with exponential backoff |
| HTTP 5xx | Retry up to 3 times with exponential backoff |
| Network timeout | Raise `CellcomConnectionError` |
| Invalid OTP | Raise `CellcomOTPError` with user-friendly message |
