"""Sensor platform for Cellcom Energy integration."""

from __future__ import annotations

import logging
from datetime import date, datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BILL_DUE_DATE,
    ATTR_BILL_METHOD_DESC,
    ATTR_BILL_URL,
    ATTR_CONTRACT_NUMBER,
    ATTR_CYCLE_DATE,
    ATTR_DAYS_UNTIL_BILL,
    ATTR_DISCOUNT_DAYS,
    ATTR_DISCOUNT_HOURS_END,
    ATTR_DISCOUNT_HOURS_START,
    ATTR_DISCOUNT_PERCENT,
    ATTR_HISTORY,
    ATTR_INVOICE_NUMBER,
    ATTR_IS_CREDIT,
    ATTR_LAST_BILL_AMOUNT,
    ATTR_LAST_BILL_DATE,
    ATTR_METER_NUMBER,
    ATTR_PAYMENT_TYPE_DESC,
    ATTR_PERIOD_END,
    ATTR_PERIOD_START,
    ATTR_PLAN_CODE,
    ATTR_PLAN_DESCRIPTION,
    ATTR_PLAN_DETAILS_TEXT,
    ATTR_PLAN_START_DATE,
    ATTR_SUBSCRIBER_NUMBER,
    DOMAIN,
)
from .coordinator import CellcomEnergyCoordinator
from .models import CellcomData

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Cellcom Energy sensors from a config entry."""
    coordinator: CellcomEnergyCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            CellcomCurrentBillSensor(coordinator, entry),
            CellcomEnergyKwhSensor(coordinator, entry),
            CellcomDaysUntilBillSensor(coordinator, entry),
            CellcomTariffPlanSensor(coordinator, entry),
        ]
    )


def _days_until(date_str: str) -> int | None:
    """Return days from today to an ISO date string, or None if unparseable."""
    try:
        target = date.fromisoformat(date_str)
        return (target - date.today()).days
    except (ValueError, TypeError):
        return None


class _CellcomSensorBase(CoordinatorEntity[CellcomEnergyCoordinator], SensorEntity):
    """Base class for all Cellcom Energy sensors."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: CellcomEnergyCoordinator,
        entry: ConfigEntry,
        unique_suffix: str,
    ) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"cellcom_energy_{coordinator.ban}_{unique_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.ban)},
            name=f"Cellcom Energy ({coordinator.ban})",
            manufacturer="Cellcom",
            model="Energy",
            entry_type=None,
        )

    @property
    def _data(self) -> CellcomData | None:
        return self.coordinator.data


class CellcomCurrentBillSensor(_CellcomSensorBase):
    """Sensor reporting the current bill total amount in ILS."""

    _attr_name = "Current Bill"
    _attr_native_unit_of_measurement = "ILS"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:currency-ils"

    def __init__(self, coordinator: CellcomEnergyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "current_bill")

    @property
    def native_value(self) -> float | None:
        data = self._data
        if data and data.billing_period:
            return data.billing_period.total_sum
        if data and data.current_invoice:
            return data.current_invoice.amount.price
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        attrs: dict[str, Any] = {}
        if not data:
            return attrs

        bp = data.billing_period
        inv = data.current_invoice
        if bp:
            attrs[ATTR_BILL_DUE_DATE] = bp.bill_due_date
            attrs[ATTR_INVOICE_NUMBER] = bp.invoice_number
            attrs[ATTR_PAYMENT_TYPE_DESC] = bp.payment_type_desc
            attrs[ATTR_BILL_METHOD_DESC] = bp.bill_method_desc
            attrs[ATTR_PERIOD_START] = bp.period_start
            attrs[ATTR_PERIOD_END] = bp.period_end
            attrs[ATTR_DAYS_UNTIL_BILL] = _days_until(bp.bill_due_date)
        if inv:
            attrs[ATTR_IS_CREDIT] = inv.amount.is_credit
            attrs[ATTR_BILL_URL] = inv.bill_url
            attrs[ATTR_CYCLE_DATE] = inv.cycle_date
        return attrs


class CellcomEnergyKwhSensor(_CellcomSensorBase):
    """Sensor reporting the latest monthly energy consumption in kWh."""

    _attr_name = "Energy Consumption"
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_icon = "mdi:lightning-bolt"

    def __init__(self, coordinator: CellcomEnergyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "energy_kwh")

    @property
    def native_value(self) -> float | None:
        data = self._data
        if not data or not data.history:
            return None
        # Return the most recent non-zero history entry
        for entry in reversed(data.history):
            if entry.kwh:
                return round(entry.kwh, 3)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        if not data:
            return {}
        last_12 = data.history[-12:] if len(data.history) >= 12 else data.history
        return {
            ATTR_HISTORY: [
                {
                    "month": h.month,
                    "cycle_date": h.cycle_date,
                    "kwh": h.kwh,
                    "amount": h.amount,
                    "period": h.bill_periods,
                }
                for h in last_12
            ]
        }


class CellcomDaysUntilBillSensor(_CellcomSensorBase):
    """Sensor reporting the number of days until the next bill is due."""

    _attr_name = "Days Until Bill"
    _attr_native_unit_of_measurement = "d"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_icon = "mdi:calendar-clock"

    def __init__(self, coordinator: CellcomEnergyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "days_until_bill")

    @property
    def native_value(self) -> int | None:
        data = self._data
        if data and data.billing_period and data.billing_period.bill_due_date:
            return _days_until(data.billing_period.bill_due_date)
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        if not data or not data.billing_period:
            return {}
        return {
            ATTR_BILL_DUE_DATE: data.billing_period.bill_due_date,
            ATTR_LAST_BILL_AMOUNT: data.current_invoice.amount.price if data.current_invoice else None,
            ATTR_LAST_BILL_DATE: data.current_invoice.full_cycle_date if data.current_invoice else None,
        }


class CellcomTariffPlanSensor(_CellcomSensorBase):
    """Sensor reporting the current tariff plan name."""

    _attr_name = "Tariff Plan"
    _attr_icon = "mdi:tag-text"

    def __init__(self, coordinator: CellcomEnergyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator, entry, "tariff_plan")

    @property
    def native_value(self) -> str | None:
        data = self._data
        if data and data.tariff_plan:
            return data.tariff_plan.plan_description or data.tariff_plan.plan_code
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        attrs: dict[str, Any] = {}
        if not data:
            return attrs
        if data.tariff_plan:
            tp = data.tariff_plan
            attrs[ATTR_PLAN_CODE] = tp.plan_code
            attrs[ATTR_PLAN_DESCRIPTION] = tp.plan_description
            attrs[ATTR_PLAN_START_DATE] = tp.plan_start_date
            attrs[ATTR_PLAN_DETAILS_TEXT] = tp.plan_details_text
            attrs[ATTR_DISCOUNT_PERCENT] = tp.discount_percent
            attrs[ATTR_DISCOUNT_DAYS] = tp.discount_days
            attrs[ATTR_DISCOUNT_HOURS_START] = tp.discount_hours_start
            attrs[ATTR_DISCOUNT_HOURS_END] = tp.discount_hours_end
        if data.meter:
            attrs[ATTR_METER_NUMBER] = data.meter.meter_number
            attrs[ATTR_CONTRACT_NUMBER] = data.meter.contract_number
            attrs[ATTR_SUBSCRIBER_NUMBER] = data.meter.subscriber_number
        return attrs
