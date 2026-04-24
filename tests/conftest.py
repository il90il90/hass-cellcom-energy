"""Shared pytest fixtures for Cellcom Energy tests."""

from unittest.mock import AsyncMock, patch

import pytest

from custom_components.cellcom_energy.models import (
    BillingPeriod,
    CellcomData,
    CustomerInfo,
    Invoice,
    InvoiceAmount,
    MeterInfo,
    MonthlyHistory,
    TariffPlan,
    Tokens,
)


@pytest.fixture
def mock_tokens() -> Tokens:
    """Return a valid Tokens instance for use in tests."""
    return Tokens(
        access_token="test_access_token",
        refresh_token="test_refresh_token",
        access_expires_at=9999999999,  # Far future
        refresh_expires_at=9999999999,
        device_id="test-device-id-1234",
        session_id="test-session-id-5678",
    )


@pytest.fixture
def mock_cellcom_data() -> CellcomData:
    """Return a fully populated CellcomData instance for sensor tests."""
    return CellcomData(
        ban="403063083",
        subscriber_number="4446400775",
        current_invoice=Invoice(
            guid_id="2AE2752D-CBC2-EFAF-19A0-F6AA9A22DC00",
            ban="403063083",
            cycle_date=20260321,
            full_cycle_date="20.03.26 - 21.02.26",
            period_start="2026-02-21",
            period_end="2026-03-20",
            amount=InvoiceAmount(
                price=432.10,
                amount=432,
                amount_agorot=10,
                is_credit=False,
            ),
            is_energy=True,
            services=["ENERGY"],
            bill_url="https://cellcom.co.il/selfcare/InvoicePageNew?id=2AE2752D",
        ),
        billing_period=BillingPeriod(
            total_sum=495.05,
            period_start="2026-03-01",
            period_end="2026-03-31",
            bill_due_date="2026-05-04",
            invoice_number="372755320",
            payment_type="CC",
            payment_type_desc="כרטיס אשראי",
            credit_card_type="LC",
            credit_card_type_desc="לאומי קארד",
            bill_method="A",
            bill_method_desc="חשבונית במייל",
            email_bill_dest="user@example.com",
        ),
        meter=MeterInfo(
            meter_number="6724246364",
            contract_number="345703607",
            customer_address="תפוח 20, נתיבות",
            subscriber_number="4446400775",
            ban="403063083",
            asset_external_id="330303466",
            product_id="47886625",
            product_status="A",
            product_status_desc="פעיל",
            product_type="W",
            is_business=False,
            is_energy_bundle=False,
            account_type="I",
        ),
        tariff_plan=TariffPlan(
            plan_code="A8HH",
            plan_description="עובדים מהבית",
            plan_start_date="2025-12-11",
            plan_details_text="פרטי תוכנית עיקריים: החל מתאריך 11.12.2025...",
            discount_percent=15,
            discount_days=["Sun", "Mon", "Tue", "Wed", "Thu"],
            discount_hours_start="07:00",
            discount_hours_end="17:00",
            future_plan_code="",
            future_plan_desc="",
            comments=["* נתוני צריכת החשמל מתקבלים מחברת החשמל..."],
        ),
        customer=CustomerInfo(
            first_name="ישראל",
            last_name="כהן",
            phone="0502959996",
            email="user@example.com",
            is_private=True,
            is_business=False,
        ),
        history=[
            MonthlyHistory(
                month="2026-02",
                cycle_date=20260221,
                bill_periods="20.02.26 - 21.01.26",
                cycle_month_name="פברואר",
                period_year="2026",
                kwh=2340.0,
                amount=579.21,
                is_view_pdf=True,
            ),
            MonthlyHistory(
                month="2026-03",
                cycle_date=20260321,
                bill_periods="20.03.26 - 21.02.26",
                cycle_month_name="מרץ",
                period_year="2026",
                kwh=2340.0,
                amount=432.10,
                is_view_pdf=True,
            ),
        ],
    )
