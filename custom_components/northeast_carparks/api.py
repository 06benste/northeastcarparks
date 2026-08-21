"""UTMC Open Data API client."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    API_DYNAMIC_URL,
    API_RETRY_BASE_DELAY_SECONDS,
    API_RETRY_MAX_ATTEMPTS,
    API_STATIC_URL,
    DOMAIN,
    LIVE_DATA_CARPARK_IDS,
    STATIC_CACHE_TTL_SECONDS,
    USER_AGENT,
)

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


def _build_static_index(items: list[dict[str, Any]]) -> dict[str, CarParkStatic]:
    """Build an O(1) lookup from system code number to static car park data."""
    index: dict[str, CarParkStatic] = {}
    for item in items:
        carpark = parse_static_item(item)
        if carpark.system_code_number:
            index[carpark.system_code_number] = carpark
    return index


def _build_dynamic_index(items: list[dict[str, Any]]) -> dict[str, CarParkDynamic]:
    """Build an O(1) lookup from system code number to dynamic car park data."""
    index: dict[str, CarParkDynamic] = {}
    for item in items:
        system_code_number = str(item.get("systemCodeNumber", ""))
        if system_code_number:
            index[system_code_number] = parse_dynamic_item(item)
    return index


CredentialsKey = tuple[str, str]


class UTMCStaticCache:
    """Shared static metadata cache keyed by UTMC credentials."""

    def __init__(self) -> None:
        self._indexes: dict[CredentialsKey, dict[str, CarParkStatic]] = {}
        self._expires_at: dict[CredentialsKey, float] = {}
        self._locks: dict[CredentialsKey, asyncio.Lock] = {}

    @staticmethod
    def _credentials_key(username: str, password: str) -> CredentialsKey:
        """Return a cache key for a credential pair."""
        return (username, password)

    def invalidate(self, username: str, password: str) -> None:
        """Drop cached static metadata for one credential pair."""
        key = self._credentials_key(username, password)
        self._indexes.pop(key, None)
        self._expires_at.pop(key, None)

    def invalidate_all(self) -> None:
        """Drop all cached static metadata."""
        self._indexes.clear()
        self._expires_at.clear()

    def get_cached_index(self, username: str, password: str) -> dict[str, CarParkStatic]:
        """Return the cached static index when still valid, otherwise an empty dict."""
        key = self._credentials_key(username, password)
        if key not in self._indexes:
            return {}
        if time.monotonic() >= self._expires_at.get(key, 0.0):
            return {}
        return self._indexes[key]

    async def async_get_index(
        self,
        username: str,
        password: str,
        fetcher: Callable[[], Awaitable[list[dict[str, Any]]]],
    ) -> dict[str, CarParkStatic]:
        """Return the static index for credentials, fetching at most once per TTL."""
        key = self._credentials_key(username, password)
        now = time.monotonic()
        if key in self._indexes and now < self._expires_at.get(key, 0.0):
            return self._indexes[key]

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            now = time.monotonic()
            if key in self._indexes and now < self._expires_at.get(key, 0.0):
                return self._indexes[key]

            items = await fetcher()
            self._indexes[key] = _build_static_index(items)
            self._expires_at[key] = now + STATIC_CACHE_TTL_SECONDS
            return self._indexes[key]


def get_static_cache(hass: HomeAssistant) -> UTMCStaticCache:
    """Return the shared static metadata cache for this Home Assistant instance."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if "static_cache" not in domain_data:
        domain_data["static_cache"] = UTMCStaticCache()
    return domain_data["static_cache"]


class UTMCApiClient:
    """HTTP client for UTMC car park feeds."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        static_cache: UTMCStaticCache,
    ) -> None:
        self._session = session
        self._auth = aiohttp.BasicAuth(username, password)
        self._username = username
        self._password = password
        self._static_cache = static_cache

    @property
    def carpark_index(self) -> dict[str, CarParkStatic]:
        """Return the cached static car park index (empty if not yet loaded)."""
        return self._static_cache.get_cached_index(self._username, self._password)

    async def _request_json_once(self, url: str) -> list[dict[str, Any]]:
        """Perform a single HTTP request and parse the JSON array response."""
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

    async def _request_json(self, url: str) -> list[dict[str, Any]]:
        """Request JSON with exponential backoff retry on transient failures."""
        last_error: CannotConnect | None = None

        for attempt in range(API_RETRY_MAX_ATTEMPTS):
            try:
                return await self._request_json_once(url)
            except InvalidAuth:
                raise
            except CannotConnect as err:
                last_error = err
                if attempt < API_RETRY_MAX_ATTEMPTS - 1:
                    delay = API_RETRY_BASE_DELAY_SECONDS * (2**attempt)
                    _LOGGER.debug(
                        "UTMC request to %s failed (attempt %s/%s), retrying in %ss: %s",
                        url,
                        attempt + 1,
                        API_RETRY_MAX_ATTEMPTS,
                        delay,
                        err,
                    )
                    await asyncio.sleep(delay)

        assert last_error is not None
        raise last_error

    async def _ensure_carpark_index(self) -> dict[str, CarParkStatic]:
        """Return the shared static car park index for these credentials."""
        return await self._static_cache.async_get_index(
            self._username,
            self._password,
            lambda: self._request_json(API_STATIC_URL),
        )

    async def async_get_carpark_list(self) -> list[CarParkStatic]:
        """Return car parks that provide live occupancy data."""
        index = await self._ensure_carpark_index()
        return [
            index[carpark_id]
            for carpark_id in LIVE_DATA_CARPARK_IDS
            if carpark_id in index
        ]

    async def async_get_static_carpark(self, carpark_id: str) -> CarParkStatic:
        """Return cached static data for one live-data car park."""
        if carpark_id not in LIVE_DATA_CARPARK_IDS:
            raise CarParkNotFound(carpark_id)

        index = await self._ensure_carpark_index()
        if carpark_id not in index:
            raise CarParkNotFound(carpark_id)
        return index[carpark_id]

    async def async_get_dynamic_carpark(self, carpark_id: str) -> CarParkDynamic | None:
        """Return dynamic occupancy data for one car park, if available."""
        try:
            items = await self._request_json(API_DYNAMIC_URL)
            return _build_dynamic_index(items).get(carpark_id)
        except UTMCError as err:
            _LOGGER.debug("Dynamic feed unavailable for %s: %s", carpark_id, err)
            return None

    async def async_get_carpark_data(self, carpark_id: str) -> CarParkData:
        """Return static and dynamic data for one live-data car park."""
        static = await self.async_get_static_carpark(carpark_id)
        dynamic = await self.async_get_dynamic_carpark(carpark_id)
        return CarParkData(static=static, dynamic=dynamic)


def create_client(hass: HomeAssistant, username: str, password: str) -> UTMCApiClient:
    """Create an API client using Home Assistant's aiohttp session."""
    return UTMCApiClient(
        async_get_clientsession(hass),
        username,
        password,
        get_static_cache(hass),
    )
