"""UTMC Open Data API client."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import API_DYNAMIC_URL, API_STATIC_URL, LIVE_DATA_CARPARK_IDS, USER_AGENT

_LOGGER = logging.getLogger(__name__)


class UTMCError(Exception):
    """Base UTMC API error."""


class InvalidAuth(UTMCError):
    """Invalid credentials."""


class CannotConnect(UTMCError):
    """Connection or unexpected response error."""


class CarParkNotFound(UTMCError):
    """Car park ID not found in feed."""


@dataclass
class CarParkStatic:
    """Static car park metadata."""

    system_code_number: str
    short_description: str | None
    long_description: str | None
    easting: float | None
    northing: float | None
    latitude: float | None
    longitude: float | None
    definition_last_updated: datetime | None
    capacity: int | None
    configuration_date: datetime | None


@dataclass
class CarParkDynamic:
    """Dynamic occupancy data."""

    occupancy: int | None
    state_description: str | None
    last_updated: datetime | None


@dataclass
class CarParkData:
    """Merged static and dynamic data for one car park."""

    static: CarParkStatic
    dynamic: CarParkDynamic | None


def _parse_iso8601(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    if len(normalized) >= 5 and normalized[-5] in "+-" and normalized[-3] != ":":
        normalized = f"{normalized[:-2]}:{normalized[-2:]}"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _first(items: list[Any] | None) -> dict[str, Any] | None:
    if not items:
        return None
    item = items[0]
    return item if isinstance(item, dict) else None


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return None


def parse_static_item(raw: dict[str, Any]) -> CarParkStatic:
    """Parse one static feed item."""
    definition = _first(raw.get("definitions")) or {}
    point = definition.get("point") or {}
    configuration = _first(raw.get("configurations")) or {}
    capacity = _to_int(configuration.get("capacity"))

    return CarParkStatic(
        system_code_number=str(raw.get("systemCodeNumber", "")),
        short_description=definition.get("shortDescription"),
        long_description=definition.get("longDescription"),
        easting=_to_float(point.get("easting")),
        northing=_to_float(point.get("northing")),
        latitude=_to_float(point.get("latitude")),
        longitude=_to_float(point.get("longitude")),
        definition_last_updated=_parse_iso8601(definition.get("lastUpdated")),
        capacity=capacity,
        configuration_date=_parse_iso8601(configuration.get("configurationDate")),
    )


def parse_dynamic_item(raw: dict[str, Any]) -> CarParkDynamic:
    """Parse one dynamic feed item."""
    dynamics = _first(raw.get("dynamics")) or {}
    occupancy = _to_int(dynamics.get("occupancy"))

    return CarParkDynamic(
        occupancy=occupancy,
        state_description=dynamics.get("stateDescription"),
        last_updated=_parse_iso8601(dynamics.get("lastUpdated")),
    )


class UTMCApiClient:
    """HTTP client for UTMC car park feeds."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
    ) -> None:
        self._session = session
        self._auth = aiohttp.BasicAuth(username, password)

    async def _request_json(self, url: str) -> list[dict[str, Any]]:
        headers = {
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        try:
            async with self._session.get(
                url,
                auth=self._auth,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status in (401, 403):
                    raise InvalidAuth if response.status == 401 else CannotConnect(
                        f"HTTP {response.status}: access denied (check credentials)"
                    )
                response.raise_for_status()
                payload = await response.json(content_type=None)
        except InvalidAuth:
            raise
        except aiohttp.ClientError as err:
            raise CannotConnect(str(err)) from err
        except (ValueError, TypeError) as err:
            raise CannotConnect(f"Invalid response from UTMC API: {err}") from err

        if not isinstance(payload, list):
            raise CannotConnect(f"Expected JSON array, got {type(payload).__name__}")
        return payload

    async def async_get_carpark_list(self) -> list[CarParkStatic]:
        """Return car parks that provide live occupancy data."""
        items = await self._request_json(API_STATIC_URL)
        return [
            carpark
            for item in items
            if (carpark := parse_static_item(item)).system_code_number
            in LIVE_DATA_CARPARK_IDS
        ]

    async def async_get_carpark_data(self, carpark_id: str) -> CarParkData:
        """Return static and dynamic data for one live-data car park."""
        if carpark_id not in LIVE_DATA_CARPARK_IDS:
            raise CarParkNotFound(carpark_id)

        static_items = await self._request_json(API_STATIC_URL)
        static_raw = next(
            (
                item
                for item in static_items
                if str(item.get("systemCodeNumber", "")) == carpark_id
            ),
            None,
        )
        if static_raw is None:
            raise CarParkNotFound(carpark_id)

        static = parse_static_item(static_raw)
        dynamic: CarParkDynamic | None = None
        try:
            dynamic_items = await self._request_json(API_DYNAMIC_URL)
            dynamic_raw = next(
                (
                    item
                    for item in dynamic_items
                    if str(item.get("systemCodeNumber", "")) == carpark_id
                ),
                None,
            )
            if dynamic_raw is not None:
                dynamic = parse_dynamic_item(dynamic_raw)
        except UTMCError as err:
            _LOGGER.debug("Dynamic feed unavailable for %s: %s", carpark_id, err)

        return CarParkData(static=static, dynamic=dynamic)


def create_client(hass: Any, username: str, password: str) -> UTMCApiClient:
    """Create an API client using Home Assistant's aiohttp session."""
    return UTMCApiClient(async_get_clientsession(hass), username, password)
