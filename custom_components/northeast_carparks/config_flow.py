"""Config flow for Northeast Car Parks."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import CarParkStatic, CannotConnect, InvalidAuth, create_client, get_static_cache
from .const import CONF_CARPARK_ID, CONF_PASSWORD, CONF_USERNAME, DOMAIN

_LOGGER = logging.getLogger(__name__)

CREDENTIALS_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.TEXT)
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
    }
)


def _get_configured_carpark_ids(hass: HomeAssistant) -> set[str]:
    """Return car park IDs that already have a config entry."""
    return {
        entry.unique_id
        for entry in hass.config_entries.async_entries(DOMAIN)
        if entry.unique_id
    }


def _get_existing_credentials(hass: HomeAssistant) -> dict[str, str] | None:
    """Return credentials from any existing config entry, if present."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        username = entry.data.get(CONF_USERNAME)
        password = entry.data.get(CONF_PASSWORD)
        if username and password:
            return {CONF_USERNAME: username, CONF_PASSWORD: password}
    return None


@callback
def _async_update_all_entry_credentials(
    hass: HomeAssistant, username: str, password: str
) -> list[str]:
    """Update UTMC credentials on every config entry; return entry ids."""
    entry_ids: list[str] = []
    for entry in hass.config_entries.async_entries(DOMAIN):
        hass.config_entries.async_update_entry(
            entry,
            data={
                **entry.data,
                CONF_USERNAME: username,
                CONF_PASSWORD: password,
            },
        )
        entry_ids.append(entry.entry_id)
    return entry_ids


class NortheastCarparksConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config and reconfigure flows."""

    VERSION = 1

    def __init__(self) -> None:
        """Initialize flow state."""
        self._credentials: dict[str, str] = {}
        self._carparks: list[CarParkStatic] | None = None

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Start setup: use saved credentials or prompt for login."""
        if user_input is None:
            existing = _get_existing_credentials(self.hass)
            if existing and self.source != config_entries.SOURCE_RECONFIGURE:
                # Add another car park: skip the credential menu and go to selection.
                self._credentials = existing
                return await self.async_step_carpark()

        return await self.async_step_credentials(user_input)

    async def async_step_use_saved(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Continue setup with credentials from an existing config entry."""
        existing = _get_existing_credentials(self.hass)
        if not existing:
            return await self.async_step_user()
        self._credentials = existing
        return await self.async_step_carpark()

    async def async_step_enter_new(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt for new UTMC credentials."""
        return await self.async_step_credentials(user_input)

    async def async_step_credentials(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Validate and store credentials, or show the login form."""
        errors: dict[str, str] = {}

        if user_input is not None:
            self._credentials = {
                CONF_USERNAME: user_input[CONF_USERNAME],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
            }
            client = create_client(
                self.hass,
                self._credentials[CONF_USERNAME],
                self._credentials[CONF_PASSWORD],
            )
            try:
                self._carparks = await client.async_get_carpark_list()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error validating UTMC credentials")
                errors["base"] = "cannot_connect"
            else:
                return await self.async_step_carpark()

        return self.async_show_form(
            step_id="credentials",
            data_schema=CREDENTIALS_SCHEMA,
            errors=errors,
            description_placeholders={
                "account_hint": (
                    "Register free at netraveldata.co.uk if you need an account."
                )
            },
        )

    async def async_step_carpark(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select which car park to add."""
        errors: dict[str, str] = {}

        if self._carparks is None:
            client = create_client(
                self.hass,
                self._credentials[CONF_USERNAME],
                self._credentials[CONF_PASSWORD],
            )
            try:
                self._carparks = await client.async_get_carpark_list()
            except InvalidAuth:
                return await self.async_step_credentials()
            except CannotConnect:
                errors["base"] = "cannot_connect"
                return self.async_show_form(step_id="carpark", errors=errors)
            except Exception:
                _LOGGER.exception("Unexpected error loading car park list")
                errors["base"] = "cannot_connect"
                return self.async_show_form(step_id="carpark", errors=errors)

        carparks = self._carparks

        configured_ids = _get_configured_carpark_ids(self.hass)
        available_carparks = [
            cp for cp in carparks if cp.system_code_number not in configured_ids
        ]

        if not carparks:
            errors["base"] = "no_carparks"
            return self.async_show_form(step_id="carpark", errors=errors)

        if not available_carparks:
            errors["base"] = "all_configured"
            return self.async_show_form(step_id="carpark", errors=errors)

        if user_input is not None:
            carpark_id = user_input[CONF_CARPARK_ID]
            await self.async_set_unique_id(carpark_id)
            self._abort_if_unique_id_configured()

            static = next(
                (cp for cp in available_carparks if cp.system_code_number == carpark_id),
                None,
            )
            title = (
                static.short_description
                if static and static.short_description
                else carpark_id
            )

            return self.async_create_entry(
                title=title,
                data={
                    CONF_USERNAME: self._credentials[CONF_USERNAME],
                    CONF_PASSWORD: self._credentials[CONF_PASSWORD],
                    CONF_CARPARK_ID: carpark_id,
                },
            )

        options = [
            SelectOptionDict(
                value=cp.system_code_number,
                label=(
                    f"{cp.short_description or cp.system_code_number} "
                    f"({cp.system_code_number})"
                ),
            )
            for cp in sorted(
                available_carparks,
                key=lambda c: (c.short_description or c.system_code_number).lower(),
            )
        ]

        return self.async_show_form(
            step_id="carpark",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_CARPARK_ID): SelectSelector(
                        SelectSelectorConfig(
                            options=options,
                            mode=SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Update UTMC credentials from the device/integration configure action."""
        errors: dict[str, str] = {}
        reconfigure_entry = self._get_reconfigure_entry()

        if user_input is not None:
            client = create_client(
                self.hass,
                user_input[CONF_USERNAME],
                user_input[CONF_PASSWORD],
            )
            try:
                await client.async_get_carpark_list()
            except InvalidAuth:
                errors["base"] = "invalid_auth"
            except CannotConnect:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error reconfiguring UTMC credentials")
                errors["base"] = "cannot_connect"
            else:
                get_static_cache(self.hass).invalidate_all()
                entry_ids = _async_update_all_entry_credentials(
                    self.hass,
                    user_input[CONF_USERNAME],
                    user_input[CONF_PASSWORD],
                )
                await self.hass.config_entries.async_reload(reconfigure_entry.entry_id)
                for entry_id in entry_ids:
                    if entry_id != reconfigure_entry.entry_id:
                        await self.hass.config_entries.async_reload(entry_id)

                return self.async_abort(reason="reconfigure_successful")

        schema = self.add_suggested_values_to_schema(
            CREDENTIALS_SCHEMA,
            {
                CONF_USERNAME: reconfigure_entry.data.get(CONF_USERNAME, ""),
            },
        )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_reauth(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Re-authenticate when the API returns invalid credentials."""
        return await self.async_step_reconfigure(user_input)
