"""Constants for the Cellcom Energy integration."""

DOMAIN = "cellcom_energy"

# ── Config entry keys ──────────────────────────────────────────────────────────
CONF_PHONE = "phone"
CONF_ID_NUMBER = "id_number"

# ── Storage ────────────────────────────────────────────────────────────────────
STORAGE_KEY = f"{DOMAIN}.tokens"
STORAGE_VERSION = 1

# ── API ────────────────────────────────────────────────────────────────────────
BASE_URL = "https://digital-api.cellcom.co.il"

# Authentication endpoints
ENDPOINT_LOGIN_STEP1 = "/api/otp/LoginStep1"
ENDPOINT_LOGIN_STEP2 = "/api/otp/LoginStep2"
ENDPOINT_LOGIN_STEP3 = "/api/otp/LoginStep3"
ENDPOINT_REFRESH_TOKEN = "/api/otp/RefreshToken"

# Data endpoints
ENDPOINT_CUSTOMER_INIT = "/api/General/CustomerInit"
ENDPOINT_ONBOARDING = "/api/SelfCare/GetSelfcareDataOnboarding"
ENDPOINT_SELFCARE_DATA = "/api/SelfCare/SelfCareData"
ENDPOINT_INVOICE_DATA = "/api/SelfCare/InvoiceData"
ENDPOINT_ALL_INVOICES = "/api/Ibill/GetAllInvoicesAuth"
ENDPOINT_FULL_MAIN = "/api/Ibill/GetFullMainAuth"
ENDPOINT_ALL_PRODUCTS = "/api/Ibill/GetAllProductsAuth"

# ── Fixed client identifiers (web portal constants) ────────────────────────────
# Fallback CLIENT_ID — the real value is extracted per-user from their JWT claim CLIENT_ID.
CLIENT_ID = "984193a2-8d29-11ea-bc55-0242ac130004"
OTP_ORIGIN = "main OTP"
SCOPE = "PRIVATE_WEBSITE"

# Cellcom Energy block identifier used in all Ibill POST requests.
ENERGY_BLOCK_ID = 69635

# ── Coordinator ────────────────────────────────────────────────────────────────
DEFAULT_SCAN_INTERVAL_MINUTES = 30

# Proactively refresh access token when fewer than this many seconds remain.
TOKEN_REFRESH_THRESHOLD_SECONDS = 300  # 5 minutes

# Retry settings for failed API calls
MAX_RETRIES = 3
RETRY_BACKOFF_BASE = 2  # seconds; actual delay = base ** attempt

# ── Platforms ──────────────────────────────────────────────────────────────────
PLATFORMS = ["sensor", "binary_sensor"]

# ── Attribute keys (used in sensor extra_state_attributes) ────────────────────
ATTR_BAN = "ban"
ATTR_SUBSCRIBER_NUMBER = "subscriber_number"
ATTR_METER_NUMBER = "meter_number"
ATTR_CONTRACT_NUMBER = "contract_number"
ATTR_CUSTOMER_ADDRESS = "customer_address"
ATTR_PLAN_CODE = "plan_code"
ATTR_PLAN_DESCRIPTION = "plan_description"
ATTR_PLAN_START_DATE = "plan_start_date"
ATTR_DISCOUNT_PERCENT = "discount_percent"
ATTR_DISCOUNT_DAYS = "discount_days"
ATTR_DISCOUNT_HOURS_START = "discount_hours_start"
ATTR_DISCOUNT_HOURS_END = "discount_hours_end"
ATTR_PLAN_DETAILS_TEXT = "plan_details_text"
ATTR_COMMENTS = "comments"
ATTR_BILL_ID = "bill_id"
ATTR_BILL_DATE = "bill_date"
ATTR_BILL_DUE_DATE = "bill_due_date"
ATTR_PERIOD_START = "period_start"
ATTR_PERIOD_END = "period_end"
ATTR_PERIOD_LABEL = "period_label"
ATTR_MAIN_AMOUNT = "main_amount"
ATTR_SUB_AMOUNT = "sub_amount"
ATTR_IS_CREDIT = "is_credit"
ATTR_INVOICE_SOURCE = "invoice_source"
ATTR_BILL_URL = "bill_url"
ATTR_SERVICES = "services"
ATTR_INVOICE_NUMBER = "invoice_number"
ATTR_PAYMENT_TYPE = "payment_type"
ATTR_PAYMENT_TYPE_DESC = "payment_type_desc"
ATTR_CREDIT_CARD_TYPE = "credit_card_type"
ATTR_CREDIT_CARD_TYPE_DESC = "credit_card_type_desc"
ATTR_BILL_METHOD = "bill_method"
ATTR_BILL_METHOD_DESC = "bill_method_desc"
ATTR_EMAIL_BILL_DEST = "email_bill_dest"
ATTR_HISTORY = "history"
ATTR_CURRENT_PERIOD = "current_period"
ATTR_CYCLE_DATE = "cycle_date"
ATTR_LAST_12_MONTHS_KWH = "last_12_months_kwh"
ATTR_LAST_12_MONTHS_COST = "last_12_months_cost"
ATTR_DAYS_UNTIL_BILL = "days_until_bill"
ATTR_LAST_BILL_DATE = "last_bill_date"
ATTR_LAST_BILL_AMOUNT = "last_bill_amount"
ATTR_OUTSTANDING_AMOUNT = "outstanding_amount"
ATTR_DUE_DATE = "due_date"
ATTR_DAYS_OVERDUE = "days_overdue"
ATTR_ACCESS_EXPIRES_IN_HOURS = "access_expires_in_hours"
ATTR_REFRESH_EXPIRES_IN_HOURS = "refresh_expires_in_hours"
ATTR_LAST_REFRESH = "last_refresh"
ATTR_LAST_API_CALL = "last_api_call"
ATTR_API_CALLS_TODAY = "api_calls_today"
