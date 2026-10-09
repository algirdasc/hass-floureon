from __future__ import annotations

import logging
from datetime import datetime
from typing import cast

import broadlink
import broadlink.exceptions
from broadlink.climate import hysen
from homeassistant.const import PRECISION_HALVES

_LOGGER = logging.getLogger(__name__)

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

CONF_HOST = 'host'
CONF_USE_EXTERNAL_TEMP = 'use_external_temp'
CONF_SCHEDULE = 'schedule'
CONF_UNIQUE_ID = 'unique_id'
CONF_PRECISION = 'precision'
CONF_USE_COOLING = 'use_cooling'

DEFAULT_SCHEDULE = 0
DEFAULT_USE_EXTERNAL_TEMP = True
DEFAULT_PRECISION = PRECISION_HALVES
DEFAULT_USE_COOLING = False


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
                    now = datetime.now()
                    await device.set_time(now.hour, now.minute, now.second, now.weekday() + 1)
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
