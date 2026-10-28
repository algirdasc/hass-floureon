"""Config flow for the Floureon thermostat integration."""
from __future__ import annotations

import logging
import re
from typing import Any

import broadlink.exceptions
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

from custom_components.floureon import (
    BROADLINK_MAX_TEMP,
    BROADLINK_MIN_TEMP,
    BROADLINK_TURN_OFF,
    CONF_ENTITY_TYPE,
    CONF_HOST,
    CONF_PRECISION,
    CONF_SCHEDULE,
    CONF_TURN_OFF_MODE,
    CONF_TURN_OFF_TEMP,
    CONF_TURN_ON_MODE,
    CONF_TURN_ON_TEMP,
    CONF_USE_COOLING,
    CONF_USE_EXTERNAL_TEMP,
    DEFAULT_PRECISION,
    DEFAULT_SCHEDULE,
    DEFAULT_TURN_OFF_MODE,
    DEFAULT_TURN_OFF_TEMP,
    DEFAULT_TURN_ON_MODE,
    DEFAULT_TURN_ON_TEMP,
    DEFAULT_USE_COOLING,
    DEFAULT_USE_EXTERNAL_TEMP,
    DOMAIN,
    ENTITY_TYPE_CLIMATE,
    ENTITY_TYPE_SWITCH,
    TURN_MODE_CUSTOM,
    BroadlinkThermostat,
)

_LOGGER = logging.getLogger(__name__)


class CannotConnect(Exception):
    """Thermostat is not reachable or authentication failed."""


async def _async_probe(host: str) -> str:
    """Connect to the thermostat and return its unique id (MAC address, falls back to host)."""
    thermostat = BroadlinkThermostat(host)
    try:
        async with await thermostat.device() as device:
            if not await device.auth():
                raise CannotConnect
            raw_mac = getattr(device, 'mac', None)
    except CannotConnect:
        raise
    except (broadlink.exceptions.BroadlinkException, OSError, TimeoutError) as err:
        raise CannotConnect from err

    if isinstance(raw_mac, (bytes, bytearray)):
        mac = bytes(raw_mac).hex()
    elif raw_mac:
        mac = re.sub(r'[^0-9a-f]', '', str(raw_mac).lower())
    else:
        mac = ''
    return mac or host


def _select(options: list[str], key: str) -> SelectSelector:
    return SelectSelector(
        SelectSelectorConfig(options=options, translation_key=key, mode=SelectSelectorMode.DROPDOWN)
    )


def _temp_selector() -> NumberSelector:
    return NumberSelector(
        NumberSelectorConfig(min=5, max=35, step=0.5, mode=NumberSelectorMode.BOX, unit_of_measurement='°C')
    )


def _climate_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_SCHEDULE, default=str(d.get(CONF_SCHEDULE, DEFAULT_SCHEDULE))): _select(
                ['0', '1', '2'], CONF_SCHEDULE
            ),
            vol.Required(
                CONF_USE_EXTERNAL_TEMP, default=d.get(CONF_USE_EXTERNAL_TEMP, DEFAULT_USE_EXTERNAL_TEMP)
            ): BooleanSelector(),
            vol.Required(CONF_PRECISION, default=str(float(d.get(CONF_PRECISION, DEFAULT_PRECISION)))): _select(
                ['0.1', '0.5', '1.0'], CONF_PRECISION
            ),
            vol.Required(CONF_USE_COOLING, default=d.get(CONF_USE_COOLING, DEFAULT_USE_COOLING)): BooleanSelector(),
        }
    )


def _switch_schema(d: dict[str, Any]) -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(
                CONF_USE_EXTERNAL_TEMP, default=d.get(CONF_USE_EXTERNAL_TEMP, DEFAULT_USE_EXTERNAL_TEMP)
            ): BooleanSelector(),
            vol.Required(CONF_TURN_OFF_MODE, default=d.get(CONF_TURN_OFF_MODE, DEFAULT_TURN_OFF_MODE)): _select(
                [BROADLINK_MIN_TEMP, BROADLINK_TURN_OFF, TURN_MODE_CUSTOM], CONF_TURN_OFF_MODE
            ),
            vol.Required(CONF_TURN_OFF_TEMP, default=d.get(CONF_TURN_OFF_TEMP, DEFAULT_TURN_OFF_TEMP)): _temp_selector(),
            vol.Required(CONF_TURN_ON_MODE, default=d.get(CONF_TURN_ON_MODE, DEFAULT_TURN_ON_MODE)): _select(
                [BROADLINK_MAX_TEMP, TURN_MODE_CUSTOM], CONF_TURN_ON_MODE
            ),
            vol.Required(CONF_TURN_ON_TEMP, default=d.get(CONF_TURN_ON_TEMP, DEFAULT_TURN_ON_TEMP)): _temp_selector(),
        }
    )


def _normalize_climate(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_SCHEDULE] = int(data[CONF_SCHEDULE])
    data[CONF_PRECISION] = float(data[CONF_PRECISION])
    return data


def _normalize_switch(user_input: dict[str, Any]) -> dict[str, Any]:
    data = dict(user_input)
    data[CONF_TURN_OFF_TEMP] = float(data[CONF_TURN_OFF_TEMP])
    data[CONF_TURN_ON_TEMP] = float(data[CONF_TURN_ON_TEMP])
    return data


class FloureonConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for a Floureon thermostat."""

    VERSION = 1

    def __init__(self) -> None:
        self._data: dict[str, Any] = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> FloureonOptionsFlow:
        return FloureonOptionsFlow()

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            try:
                unique_id = await _async_probe(host)
            except CannotConnect:
                errors['base'] = 'cannot_connect'
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected error while connecting to %s", host)
                errors['base'] = 'unknown'
            else:
                await self.async_set_unique_id(unique_id)
                # Also updates the host if the thermostat got a new IP address
                self._abort_if_unique_id_configured(updates={CONF_HOST: host})

                self._data = {
                    CONF_HOST: host,
                    CONF_NAME: user_input[CONF_NAME].strip(),
                    CONF_ENTITY_TYPE: user_input[CONF_ENTITY_TYPE],
                }
                if user_input[CONF_ENTITY_TYPE] == ENTITY_TYPE_SWITCH:
                    return await self.async_step_switch()
                return await self.async_step_climate()

        defaults = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=defaults.get(CONF_HOST, '')): TextSelector(),
                vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, 'Thermostat')): TextSelector(),
                vol.Required(
                    CONF_ENTITY_TYPE, default=defaults.get(CONF_ENTITY_TYPE, ENTITY_TYPE_CLIMATE)
                ): _select([ENTITY_TYPE_CLIMATE, ENTITY_TYPE_SWITCH], CONF_ENTITY_TYPE),
            }
        )
        return self.async_show_form(step_id='user', data_schema=schema, errors=errors)

    async def async_step_climate(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._data[CONF_NAME], data={**self._data, **_normalize_climate(user_input)}
            )
        return self.async_show_form(step_id='climate', data_schema=_climate_schema({}))

    async def async_step_switch(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(
                title=self._data[CONF_NAME], data={**self._data, **_normalize_switch(user_input)}
            )
        return self.async_show_form(step_id='switch', data_schema=_switch_schema({}))


class FloureonOptionsFlow(config_entries.OptionsFlow):
    """Change the settings of an already configured thermostat."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> config_entries.ConfigFlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        is_switch = current.get(CONF_ENTITY_TYPE) == ENTITY_TYPE_SWITCH

        if user_input is not None:
            data = _normalize_switch(user_input) if is_switch else _normalize_climate(user_input)
            return self.async_create_entry(title='', data=data)

        schema = _switch_schema(current) if is_switch else _climate_schema(current)
        return self.async_show_form(step_id='init', data_schema=schema)
