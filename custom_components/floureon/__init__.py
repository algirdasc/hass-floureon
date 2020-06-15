import broadlink
import logging
from datetime import datetime
from socket import timeout


_LOGGER = logging.getLogger(__name__)

BROADLINK_ACTIVE = 1
BROADLINK_IDLE = 0
BROADLINK_POWER_ON = 1
BROADLINK_POWER_OFF = 0
BROADLINK_MODE_AUTO = 1  # or 2?
BROADLINK_MODE_MANUAL = 0
BROADLINK_SENSOR_INTERNAL = 0
BROADLINK_SENSOR_EXTERNAL = 1
BROADLINK_SENSOR_BOTH = 2
BROADLINK_TEMP_AUTO = 0
BROADLINK_TEMP_MANUAL = 1

CONF_HOST = 'host'
CONF_MAC = 'mac'
CONF_USE_EXTERNAL_TEMP = 'use_external_temp'
CONF_SCHEDULE = 'schedule'

DEFAULT_SCHEDULE = 0
DEFAULT_USE_EXTERNAL_TEMP = True


class BroadlinkThermostat:

    def __init__(self, host, mac):
        self._host = host
        self._port = 80
        self._mac = bytes.fromhex(''.join(reversed(mac.split(':'))))

    def device(self):
        return broadlink.gendevice(0x4EAD, (self._host, self._port), self._mac)

    def thermostat_set_time(self):
        """Set thermostat time"""
        try:
            device = self.device()
            if device.auth():
                now = datetime.now()
                device.set_time(now.hour,
                                now.minute,
                                now.second,
                                now.weekday() + 1)
        except timeout:
            pass
        except Exception as e:
            _LOGGER.error("Thermostat %s set_time error: %s", self._host, str(e))

    def thermostat_read_status(self):
        """Read thermostat data"""
        data = None
        try:
            device = self.device()
            if device.auth():
                data = device.get_full_status()
        except timeout:
            pass
        except Exception as e:
            _LOGGER.warning("Thermostat %s read_status error: %s", self._host, str(e))
        finally:
            return data
