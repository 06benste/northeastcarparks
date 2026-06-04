"""Base entity for Northeast Car Parks."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import NortheastCarparksCoordinator


class NortheastCarparkEntity(CoordinatorEntity[NortheastCarparksCoordinator]):
    """Base entity attached to a car park device."""

    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: NortheastCarparksCoordinator,
        entity_key: str,
    ) -> None:
        super().__init__(coordinator)
        self.entity_key = entity_key
        self._attr_unique_id = f"{coordinator.carpark_id}_{entity_key}"
        self._attr_translation_key = entity_key

    @property
    def device_info(self) -> DeviceInfo:
        """Link entity to the car park device."""
        static = self.coordinator.data.static
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.carpark_id)},
            name=static.short_description or self.coordinator.carpark_id,
            manufacturer=MANUFACTURER,
            model=self.coordinator.carpark_id,
            configuration_url="https://www.netraveldata.co.uk/?page_id=32",
        )
