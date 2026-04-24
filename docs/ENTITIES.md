# Entity Reference

All entities belong to a single HA **device** identified by the Billing
Account Number (BAN). The device appears under
`Settings → Devices & Services → Cellcom Energy`.

---

## Sensors

### `sensor.cellcom_current_bill`

The total amount due for the current billing cycle.

| Property | Value |
|----------|-------|
| State | `432.10` |
| Unit | `ILS` (₪) |
| `device_class` | `monetary` |
| `state_class` | `measurement` |

**Attributes:**

| Attribute | Type | Example | Description |
|-----------|------|---------|-------------|
| `bill_id` | str | `"2AE2752D-..."` | Unique invoice GUID |
| `bill_date` | str | `"2026-03-20"` | Invoice issue date (ISO 8601) |
| `bill_due_date` | str | `"2026-05-04"` | Payment due date |
| `period_start` | str | `"2026-02-21"` | Billing period start |
| `period_end` | str | `"2026-03-20"` | Billing period end |
| `period_label` | str | `"20.03.26 - 21.02.26"` | Period as shown on invoice |
| `main_amount` | int | `432` | Shekel component |
| `sub_amount` | int | `10` | Agorot component |
| `is_credit` | bool | `false` | True if a credit note |
| `invoice_source` | str | `"Cellcom"` | Issuer |
| `bill_url` | str | `"https://..."` | Direct link to PDF invoice |
| `services` | list | `["ENERGY"]` | Service types on this bill |
| `ban` | str | `"403063083"` | Billing account number |

---

### `sensor.cellcom_monthly_consumption_kwh`

kWh consumed in the current billing period (from latest invoice data).

| Property | Value |
|----------|-------|
| State | `2340` |
| Unit | `kWh` |
| `device_class` | `energy` |
| `state_class` | `total_increasing` |

**Attributes:**

| Attribute | Type | Example | Description |
|-----------|------|---------|-------------|
| `current_period` | str | `"2026-03"` | Current billing month (ISO) |
| `period_label` | str | `"20.03.26 - 21.02.26"` | Human-readable period |
| `cycle_date` | str | `"2026-03-21"` | Billing cycle date |
| `history` | list | `[{month, kwh, amount}, ...]` | Last 12 months of data |
| `last_12_months_kwh` | float | `28080` | Total kWh over past year |
| `last_12_months_cost` | float | `5234.50` | Total cost over past year |

**History item schema:**
```yaml
- month: "2026-02"    # ISO year-month
  kwh: 2340
  amount: 579.21
  cycle_month_name: "פברואר"
  is_view_pdf: true
```

---

### `sensor.cellcom_meter`

The physical meter identifier and contract details.

| Property | Value |
|----------|-------|
| State | `6724246364` (meter number) |
| `device_class` | — |

**Attributes:**

| Attribute | Type | Example |
|-----------|------|---------|
| `contract_number` | str | `"345703607"` |
| `customer_address` | str | `"תפוח 20, נתיבות"` |
| `subscriber_number` | str | `"4446400775"` |
| `ban` | str | `"403063083"` |
| `asset_external_id` | str | `"330303466"` |
| `product_id` | str | `"47886625"` |
| `product_status` | str | `"Active"` |
| `product_status_desc` | str | `"פעיל"` |
| `product_type` | str | `"W"` |
| `is_business` | bool | `false` |
| `is_energy_bundle` | bool | `false` |
| `account_type` | str | `"I"` (Individual) |

---

### `sensor.cellcom_tariff_plan`

Current electricity tariff plan.

| Property | Value |
|----------|-------|
| State | `"עובדים מהבית"` |

**Attributes:**

| Attribute | Type | Example |
|-----------|------|---------|
| `plan_code` | str | `"A8HH"` |
| `plan_description` | str | `"עובדים מהבית"` |
| `plan_start_date` | str | `"2025-12-11"` |
| `discount_percent` | int | `15` |
| `discount_days` | list | `["Sun","Mon","Tue","Wed","Thu"]` |
| `discount_hours_start` | str | `"07:00"` |
| `discount_hours_end` | str | `"17:00"` |
| `plan_details_text` | str | Full plan description paragraph |
| `comments` | list | Legal notes from Cellcom |
| `future_plan_code` | str | `""` (empty if no upcoming change) |
| `future_plan_desc` | str | `""` |

---

### `sensor.cellcom_total_due`

Total outstanding balance on the account.

| Property | Value |
|----------|-------|
| State | `495.05` |
| Unit | `ILS` (₪) |
| `device_class` | `monetary` |

**Attributes:**

| Attribute | Type | Example |
|-----------|------|---------|
| `period_start` | str | `"2026-03-01"` |
| `period_end` | str | `"2026-03-31"` |
| `bill_due_date` | str | `"2026-05-04"` |
| `invoice_number` | str | `"372755320"` |
| `payment_type` | str | `"CC"` |
| `payment_type_desc` | str | `"כרטיס אשראי"` |
| `credit_card_type` | str | `"LC"` |
| `credit_card_type_desc` | str | `"לאומי קארד"` |
| `bill_method` | str | `"A"` |
| `bill_method_desc` | str | `"חשבונית במייל"` |
| `email_bill_dest` | str | `"user@example.com"` |

---

### `sensor.cellcom_next_bill_date`

Date the next payment will be charged.

| Property | Value |
|----------|-------|
| State | `"2026-05-04"` |
| `device_class` | `date` |

**Attributes:**

| Attribute | Type | Example |
|-----------|------|---------|
| `days_until_bill` | int | `10` |
| `bill_cycle` | str | `"21.05.26"` |
| `last_bill_date` | str | `"2026-03-20"` |
| `last_bill_amount` | float | `432.10` |

---

### `sensor.cellcom_customer_info` *(diagnostic)*

Account holder details.

| Property | Value |
|----------|-------|
| State | Full name (e.g. `"ישראל כהן"`) |
| `entity_category` | `diagnostic` |

**Attributes:** `first_name`, `last_name`, `phone` (masked), `email`,
`customer_type`, `is_private`, `is_business`

---

### `sensor.cellcom_token_expiry` *(diagnostic)*

Token health for troubleshooting.

| Property | Value |
|----------|-------|
| State | ISO 8601 expiry timestamp |
| `device_class` | `timestamp` |
| `entity_category` | `diagnostic` |

**Attributes:** `access_expires_in_hours`, `refresh_expires_in_hours`,
`last_refresh`, `last_api_call`, `api_calls_today`

---

## Binary Sensors

### `binary_sensor.cellcom_has_outstanding_bill`

`on` when there is an unpaid balance due.

| Property | Value |
|----------|-------|
| State | `on` / `off` |
| `device_class` | `problem` |

**Attributes:** `outstanding_amount`, `due_date`, `days_overdue`

---

## Using Attributes in Templates

```yaml
# Amount in integer shekels
{{ state_attr('sensor.cellcom_current_bill', 'main_amount') }}

# URL to open the PDF invoice
{{ state_attr('sensor.cellcom_current_bill', 'bill_url') }}

# Days until next payment
{{ state_attr('sensor.cellcom_next_bill_date', 'days_until_bill') }}

# Total kWh consumed this year
{{ state_attr('sensor.cellcom_monthly_consumption_kwh', 'history')
   | selectattr('month', 'match', '2026')
   | map(attribute='kwh') | sum }}

# Check if discount hours are active right now
{% set plan = state_attr('sensor.cellcom_tariff_plan', 'discount_days') %}
{% set weekday = now().strftime('%a') %}
{% if weekday in plan and 7 <= now().hour < 17 %}
  Discount active ({{ state_attr('sensor.cellcom_tariff_plan', 'discount_percent') }}% off)
{% else %}
  Standard rate
{% endif %}
```

---

## Energy Dashboard Integration

To add monthly consumption to the HA Energy Dashboard:

1. `Settings → Dashboards → Energy → Configure`
2. Under **Electricity grid → Grid consumption**, select
   `sensor.cellcom_monthly_consumption_kwh`
3. Optionally link `sensor.cellcom_current_bill` as the cost entity

> For **real-time** (15-minute interval) readings, install the companion
> integration [`ha-iec`](https://github.com/GuyKh/ha-iec) which connects
> directly to the Israeli Electric Corporation smart meter API.
