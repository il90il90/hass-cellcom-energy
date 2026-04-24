"""Typed dataclasses representing Cellcom API data."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Tokens:
    """Authentication token pair returned by LoginStep3."""

    access_token: str
    refresh_token: str
    access_expires_at: int   # Unix timestamp
    refresh_expires_at: int  # Unix timestamp
    device_id: str
    session_id: str


@dataclass
class InvoiceAmount:
    """Monetary amount split into shekels and agorot."""

    price: float          # e.g. 432.10
    amount: int           # shekel component, e.g. 432
    amount_agorot: int    # agorot component, e.g. 10
    is_credit: bool


@dataclass
class Invoice:
    """A single billing invoice from GetAllInvoicesAuth."""

    guid_id: str
    ban: str
    cycle_date: int          # e.g. 20260321
    full_cycle_date: str     # e.g. "20.03.26 - 21.02.26"
    period_start: str        # ISO date, e.g. "2026-02-21"
    period_end: str          # ISO date, e.g. "2026-03-20"
    amount: InvoiceAmount
    is_energy: bool
    services: list[str]
    bill_url: str


@dataclass
class MonthlyHistory:
    """One entry from the GetFullMainAuth consumption history."""

    month: str            # ISO year-month, e.g. "2026-02"
    cycle_date: int       # e.g. 20260221
    bill_periods: str     # e.g. "20.02.26 - 21.01.26"
    cycle_month_name: str # e.g. "פברואר"
    period_year: str
    kwh: float
    amount: float | None
    is_view_pdf: bool


@dataclass
class TariffPlan:
    """Tariff plan details from GetAllProductsAuth."""

    plan_code: str
    plan_description: str
    plan_start_date: str       # ISO date
    plan_details_text: str
    discount_percent: int
    discount_days: list[str]   # e.g. ["Sun", "Mon", "Tue", "Wed", "Thu"]
    discount_hours_start: str  # e.g. "07:00"
    discount_hours_end: str    # e.g. "17:00"
    future_plan_code: str
    future_plan_desc: str
    comments: list[str]


@dataclass
class MeterInfo:
    """Physical meter and contract information."""

    meter_number: str
    contract_number: str
    customer_address: str
    subscriber_number: str
    ban: str
    asset_external_id: str
    product_id: str
    product_status: str
    product_status_desc: str
    product_type: str
    is_business: bool
    is_energy_bundle: bool
    account_type: str


@dataclass
class BillingPeriod:
    """Current billing period summary from InvoiceData."""

    total_sum: float
    period_start: str    # ISO date
    period_end: str      # ISO date
    bill_due_date: str   # ISO date
    invoice_number: str
    payment_type: str
    payment_type_desc: str
    credit_card_type: str
    credit_card_type_desc: str
    bill_method: str
    bill_method_desc: str
    email_bill_dest: str


@dataclass
class CustomerInfo:
    """Basic account holder information."""

    first_name: str
    last_name: str
    phone: str
    email: str
    is_private: bool
    is_business: bool


@dataclass
class CellcomData:
    """Aggregated data fetched by the coordinator in one polling cycle."""

    # Account identifiers
    ban: str
    subscriber_number: str

    # Core data objects
    current_invoice: Invoice | None
    billing_period: BillingPeriod | None
    meter: MeterInfo | None
    tariff_plan: TariffPlan | None
    customer: CustomerInfo | None

    # Historical consumption
    history: list[MonthlyHistory] = field(default_factory=list)

    # Metadata
    last_updated: datetime = field(default_factory=datetime.now)
