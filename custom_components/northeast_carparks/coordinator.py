"""Data update coordinator."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import CarParkData, CannotConnect, InvalidAuth, UTMCApiClient, create_client
from .const import CONF_CARPARK_ID, CONF_PASSWORD, CONF_USERNAME, DOMAIN, SCAN_INTERVAL_SECONDS

_LOGGER = logging.getLogger(__name__)


class NortheastCarparksCoordinator(DataUpdateCoordinator[CarParkData]):
    """Fetch car park data from UTMC."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        client: UTMCApiClient,
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
            config_entry=entry,
        )
        self.client = client
        self.carpark_id = entry.data[CONF_CARPARK_ID]

    async def _async_update_data(self) -> CarParkData:
        """Refresh dynamic occupancy every poll; static metadata uses a shared 24-hour cache."""
        try:
            static = await self.client.async_get_static_carpark(self.carpark_id)
            dynamic = await self.client.async_get_dynamic_carpark(self.carpark_id)
            return CarParkData(static=static, dynamic=dynamic)
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed from err
        except CannotConnect as err:
            raise UpdateFailed(str(err)) from err


async def async_create_coordinator(
    hass: HomeAssistant, entry: ConfigEntry
) -> NortheastCarparksCoordinator:
    """Create coordinator and perform initial refresh."""
    client = create_client(
        hass,
        entry.data[CONF_USERNAME],
        entry.data[CONF_PASSWORD],
    )
    coordinator = NortheastCarparksCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    return coordinator
