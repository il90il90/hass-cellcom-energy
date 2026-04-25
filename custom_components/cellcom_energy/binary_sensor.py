"""Binary sensor platform for Cellcom Energy integration."""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_BILL_DUE_DATE,
    ATTR_DAYS_OVERDUE,
    ATTR_OUTSTANDING_AMOUNT,
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
    """Set up Cellcom Energy binary sensors from a config entry."""
    coordinator: CellcomEnergyCoordinator = hass.data[DOMAIN][entry.entry_id]

    async_add_entities(
        [
            CellcomBillOverdueSensor(coordinator, entry),
        ]
    )


class CellcomBillOverdueSensor(
    CoordinatorEntity[CellcomEnergyCoordinator], BinarySensorEntity
):
    """Binary sensor that is ON when the current bill is past its due date."""

    _attr_has_entity_name = True
    _attr_name = "Bill Overdue"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle"

    def __init__(self, coordinator: CellcomEnergyCoordinator, entry: ConfigEntry) -> None:
        super().__init__(coordinator)
        self._entry = entry
        self._attr_unique_id = f"cellcom_energy_{coordinator.ban}_bill_overdue"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.ban)},
            name=f"Cellcom Energy ({coordinator.ban})",
            manufacturer="Cellcom",
            model="Energy",
        )

    @property
    def _data(self) -> CellcomData | None:
        return self.coordinator.data

    @property
    def is_on(self) -> bool | None:
        """Return True when the due date has passed and the amount is positive."""
        data = self._data
        if not data or not data.billing_period:
            return None
        bp = data.billing_period
        if not bp.bill_due_date:
            return None
        try:
            due = date.fromisoformat(bp.bill_due_date)
        except (ValueError, TypeError):
            return None
        return date.today() > due and bp.total_sum > 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self._data
        attrs: dict[str, Any] = {}
        if not data or not data.billing_period:
            return attrs
        bp = data.billing_period
        attrs[ATTR_BILL_DUE_DATE] = bp.bill_due_date
        attrs[ATTR_OUTSTANDING_AMOUNT] = bp.total_sum
        if bp.bill_due_date:
            try:
                due = date.fromisoformat(bp.bill_due_date)
                days_over = (date.today() - due).days
                attrs[ATTR_DAYS_OVERDUE] = max(0, days_over)
            except (ValueError, TypeError):
                pass
        return attrs
