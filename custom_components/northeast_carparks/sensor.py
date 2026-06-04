"""Sensor platform for Northeast Car Parks."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .api import CarParkData
from .const import STATE_DESCRIPTIONS
from .coordinator import NortheastCarparksCoordinator
from .entity import NortheastCarparkEntity

# Fallback display names if translations are not loaded yet.
ENTITY_NAMES: dict[str, str] = {
    "short_description": "Name",
    "long_description": "Address",
    "capacity": "Capacity",
    "occupancy": "Occupancy",
    "spaces_free": "Spaces free",
    "state_description": "State",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up sensors for a car park."""
    coordinator: NortheastCarparksCoordinator = entry.runtime_data
    async_add_entities(
        NortheastCarparkSensor(coordinator, description)
        for description in SENSOR_DESCRIPTIONS
    )


class NortheastCarparkSensor(NortheastCarparkEntity, SensorEntity):
    """Sensor for one UTMC data field."""

    def __init__(
        self,
        coordinator: NortheastCarparksCoordinator,
        description: SensorDescription,
    ) -> None:
        super().__init__(coordinator, description.key)
        self._description = description
        self._attr_name = ENTITY_NAMES.get(description.key, description.key)
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        if description.options:
            self._attr_options = list(description.options)
        if description.native_unit_of_measurement:
            self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        if description.suggested_display_precision is not None:
            self._attr_suggested_display_precision = (
                description.suggested_display_precision
            )

    @property
    def native_value(self) -> str | int | float | datetime | None:
        """Return sensor value from coordinator data."""
        data = self.coordinator.data
        value = self._description.value_fn(data)
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if self._description.whole_number:
            return _coerce_int(value)
        return value


class SensorDescription:
    """Metadata for a sensor entity."""

    def __init__(
        self,
        key: str,
        value_fn: Callable[[CarParkData], str | int | float | datetime | None],
        *,
        device_class: SensorDeviceClass | None = None,
        state_class: SensorStateClass | None = None,
        options: tuple[str, ...] | None = None,
        native_unit_of_measurement: str | None = None,
        suggested_display_precision: int | None = None,
        whole_number: bool = False,
    ) -> None:
        self.key = key
        self.value_fn = value_fn
        self.device_class = device_class
        self.state_class = state_class
        self.options = options
        self.native_unit_of_measurement = native_unit_of_measurement
        self.suggested_display_precision = suggested_display_precision
        self.whole_number = whole_number


def _coerce_int(value: Any) -> int | None:
    """Return a whole number, avoiding float artefacts in state and graphs."""
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def _capacity(data: CarParkData) -> int | None:
    return _coerce_int(data.static.capacity)


def _occupancy(data: CarParkData) -> int | None:
    if data.dynamic is None:
        return None
    return _coerce_int(data.dynamic.occupancy)


def _static_value(
    attr: str,
) -> Callable[[CarParkData], str | int | float | datetime | None]:
    def getter(data: CarParkData) -> str | int | float | datetime | None:
        return getattr(data.static, attr, None)

    return getter


def _dynamic_value(
    attr: str,
) -> Callable[[CarParkData], str | int | float | datetime | None]:
    def getter(data: CarParkData) -> str | int | float | datetime | None:
        if data.dynamic is None:
            return None
        return getattr(data.dynamic, attr, None)

    return getter


def _spaces_free(data: CarParkData) -> int | None:
    """Return available spaces when capacity and occupancy are known."""
    capacity = _coerce_int(data.static.capacity)
    if data.dynamic is None or capacity is None:
        return None
    occupancy = _coerce_int(data.dynamic.occupancy)
    if occupancy is None:
        return None
    return max(capacity - occupancy, 0)


SENSOR_DESCRIPTIONS: tuple[SensorDescription, ...] = (
    SensorDescription("short_description", _static_value("short_description")),
    SensorDescription("long_description", _static_value("long_description")),
    SensorDescription(
        "capacity",
        _capacity,
        suggested_display_precision=0,
        whole_number=True,
    ),
    SensorDescription(
        "occupancy",
        _occupancy,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        whole_number=True,
    ),
    SensorDescription(
        "spaces_free",
        _spaces_free,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="spaces",
        suggested_display_precision=0,
        whole_number=True,
    ),
    SensorDescription(
        "state_description",
        _dynamic_value("state_description"),
        device_class=SensorDeviceClass.ENUM,
        options=STATE_DESCRIPTIONS,
    ),
)
