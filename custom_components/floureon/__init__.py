from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any, cast

import broadlink
import broadlink.exceptions
from broadlink.climate import hysen
from homeassistant.const import CONF_NAME, PRECISION_HALVES, Platform
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_platform
from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC, DeviceInfo, format_mac
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

DOMAIN = 'floureon'

BROADLINK_ACTIVE = 1
BROADLINK_IDLE = 0
BROADLINK_POWER_ON = 1
BROADLINK_POWER_OFF = 0
BROADLINK_MODE_MANUAL = 0
BROADLINK_MODE_AUTO = 1
BROADLINK_SENSOR_INTERNAL = 0
BROADLINK_SENSOR_EXTERNAL = 1
BROADLINK_SENSOR_BOTH = 2
BROADLINK_TEMP_AUTO = 0
BROADLINK_TEMP_MANUAL = 1

# Switch turn on / turn off modes
BROADLINK_TURN_OFF = 'turn_off'
BROADLINK_MIN_TEMP = 'min_temp'
BROADLINK_MAX_TEMP = 'max_temp'
TURN_MODE_CUSTOM = 'custom'  # only used by the UI (config flow), mapped to a float temperature

CONF_HOST = 'host'
CONF_USE_EXTERNAL_TEMP = 'use_external_temp'
CONF_SCHEDULE = 'schedule'
CONF_UNIQUE_ID = 'unique_id'
CONF_PRECISION = 'precision'
CONF_USE_COOLING = 'use_cooling'
CONF_TURN_OFF_MODE = 'turn_off_mode'
CONF_TURN_ON_MODE = 'turn_on_mode'

# UI (config entry) only
CONF_ENTITY_TYPE = 'entity_type'
CONF_TURN_OFF_TEMP = 'turn_off_temp'
CONF_TURN_ON_TEMP = 'turn_on_temp'

ENTITY_TYPE_CLIMATE = 'climate'
ENTITY_TYPE_SWITCH = 'switch'

DEFAULT_SCHEDULE = 0
DEFAULT_USE_EXTERNAL_TEMP = True
DEFAULT_PRECISION = PRECISION_HALVES
DEFAULT_USE_COOLING = False
DEFAULT_TURN_OFF_MODE = BROADLINK_MIN_TEMP
DEFAULT_TURN_ON_MODE = BROADLINK_MAX_TEMP
DEFAULT_TURN_OFF_TEMP = 17.0
DEFAULT_TURN_ON_TEMP = 21.0

SERVICE_SET_TIME = 'set_time'


def platform_for_entry(entry: ConfigEntry) -> Platform:
    """Return the platform (climate / switch) a config entry sets up."""
    if entry.data.get(CONF_ENTITY_TYPE) == ENTITY_TYPE_SWITCH:
        return Platform.SWITCH
    return Platform.CLIMATE


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up a thermostat from a config entry (UI)."""
    await hass.config_entries.async_forward_entry_setups(entry, [platform_for_entry(entry)])
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, [platform_for_entry(entry)])


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when its options have been changed."""
    await hass.config_entries.async_reload(entry.entry_id)


def entry_to_config(entry: ConfigEntry) -> dict[str, Any]:
    """Convert a config entry into the same config dict structure the YAML platforms use."""
    cfg: dict[str, Any] = {**entry.data, **entry.options}

    cfg.setdefault(CONF_SCHEDULE, DEFAULT_SCHEDULE)
    cfg.setdefault(CONF_USE_EXTERNAL_TEMP, DEFAULT_USE_EXTERNAL_TEMP)
    cfg.setdefault(CONF_PRECISION, DEFAULT_PRECISION)
    cfg.setdefault(CONF_USE_COOLING, DEFAULT_USE_COOLING)

    off_mode = cfg.get(CONF_TURN_OFF_MODE, DEFAULT_TURN_OFF_MODE)
    if off_mode == TURN_MODE_CUSTOM:
        off_mode = float(cfg.get(CONF_TURN_OFF_TEMP, DEFAULT_TURN_OFF_TEMP))
    cfg[CONF_TURN_OFF_MODE] = off_mode

    on_mode = cfg.get(CONF_TURN_ON_MODE, DEFAULT_TURN_ON_MODE)
    if on_mode == TURN_MODE_CUSTOM:
        on_mode = float(cfg.get(CONF_TURN_ON_TEMP, DEFAULT_TURN_ON_TEMP))
    cfg[CONF_TURN_ON_MODE] = on_mode

    return cfg


def device_info_for(entry: ConfigEntry) -> DeviceInfo:
    """Device registry info for the thermostat of a config entry."""
    info = DeviceInfo(
        identifiers={(DOMAIN, entry.unique_id or entry.entry_id)},
        name=entry.data.get(CONF_NAME) or entry.title,
        manufacturer='Floureon / Broadlink',
        model='WiFi thermostat (Hysen)',
    )
    # unique_id is the MAC address (12 hex digits) when it could be read from the device
    if entry.unique_id and re.fullmatch(r'[0-9a-f]{12}', entry.unique_id):
        info['connections'] = {(CONNECTION_NETWORK_MAC, format_mac(entry.unique_id))}
    return info


def register_set_time_service() -> None:
    """Register the floureon.set_time entity service for the platform currently being set up."""
    platform = entity_platform.async_get_current_platform()
    try:
        platform.async_register_entity_service(SERVICE_SET_TIME, {}, 'async_set_time')
    except (HomeAssistantError, ValueError) as e:
        _LOGGER.debug("Service %s.%s not registered again: %s", DOMAIN, SERVICE_SET_TIME, e)


class BroadlinkThermostat:
    def __init__(self, host: str) -> None:
        self._host = host

    async def device(self) -> hysen:
        max_attempt = 3
        for attempt in range(0, max_attempt):
            try:
                attempt += 1
                return cast(hysen, await broadlink.hello(self._host, timeout=3))
            except broadlink.exceptions.NetworkTimeoutError as e:
                if attempt == max_attempt:
                    _LOGGER.error("Thermostat %s network error: %s", self._host, str(e))
                    raise
        raise AssertionError("Thermostat discovery exhausted retries")

    async def set_time(self) -> None:
        """Set thermostat time"""
        try:
            async with await self.device() as device:
                device = cast(hysen, device)
                if await device.auth():
                    now = dt_util.now()
                    await device.set_time(now.hour, now.minute, now.second, now.isoweekday())
                    _LOGGER.debug("Thermostat date / time is set")
        except Exception as e:
            _LOGGER.error("Thermostat %s set_time error: %s", self._host, str(e))

    async def read_status(self) -> dict | None:
        """Read thermostat data"""
        data = None
        try:
            async with await self.device() as device:
                device = cast(hysen, device)
                if await device.auth():
                    data = await device.get_full_status()
                    _LOGGER.debug("Received %s thermostat data: %s", self._host, data)
        except Exception as e:
            _LOGGER.warning("Thermostat %s read_status() error: %s", self._host, str(e))
        return data
