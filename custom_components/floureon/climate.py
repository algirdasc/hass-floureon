
import logging
from socket import timeout
from typing import List, Optional

import voluptuous as vol

from custom_components.floureon import (
    BroadlinkThermostat,
    CONF_HOST,
    CONF_MAC,
    CONF_USE_EXTERNAL_TEMP,
    CONF_SCHEDULE,
    DEFAULT_SCHEDULE,
    DEFAULT_USE_EXTERNAL_TEMP,
    BROADLINK_ACTIVE,
    BROADLINK_IDLE,
    BROADLINK_POWER_ON,
    BROADLINK_POWER_OFF,
    BROADLINK_MODE_AUTO,
    BROADLINK_MODE_MANUAL,
    BROADLINK_SENSOR_INTERNAL,
    BROADLINK_SENSOR_EXTERNAL,
    BROADLINK_TEMP_AUTO,
    BROADLINK_TEMP_MANUAL
)

from homeassistant.components.climate import ClimateEntity, PLATFORM_SCHEMA
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util.temperature import convert as convert_temperature
from homeassistant.components.climate.const import (
    HVAC_MODE_OFF,
    HVAC_MODE_HEAT,
    HVAC_MODE_AUTO,
    CURRENT_HVAC_OFF,
    CURRENT_HVAC_HEAT,
    CURRENT_HVAC_IDLE,
    PRESET_NONE,
    PRESET_AWAY,
    SUPPORT_TARGET_TEMPERATURE,
    SUPPORT_PRESET_MODE,
    DEFAULT_MIN_TEMP,
    DEFAULT_MAX_TEMP
)

from homeassistant.const import (
    PRECISION_HALVES,
    ATTR_TEMPERATURE,
    PRECISION_HALVES,
    TEMP_CELSIUS,
    CONF_NAME
)

import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_MAC): cv.string,
    vol.Optional(CONF_SCHEDULE, default=DEFAULT_SCHEDULE): vol.All(int, vol.Range(min=0,max=2)),
    vol.Optional(CONF_USE_EXTERNAL_TEMP, default=DEFAULT_USE_EXTERNAL_TEMP): cv.boolean,
})


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the generic thermostat platform."""
    async_add_entities([FloureonClimate(hass, config)])


class FloureonClimate(ClimateEntity, RestoreEntity):

    def __init__(self, hass, config):
        if config.get(CONF_MAC) is not None:
            _LOGGER.error("{0} option is deprecated. It will be removed in future releases. "
                          "Please modify your config accordingly.".format(CONF_MAC))

        self._hass = hass
        self._thermostat = BroadlinkThermostat(config.get(CONF_HOST))

        self._name = config.get(CONF_NAME)
        self._use_external_temp = config.get(CONF_USE_EXTERNAL_TEMP)

        self._min_temp = DEFAULT_MIN_TEMP
        self._max_temp = DEFAULT_MAX_TEMP
        self._room_temp = None
        self._external_temp = None

        self._away_setpoint = DEFAULT_MIN_TEMP
        self._manual_setpoint = DEFAULT_MIN_TEMP

        self._preset_mode = None

        self._thermostat_loop_mode = config.get(CONF_SCHEDULE)
        self._thermostat_current_action = None
        self._thermostat_current_mode = None
        self._thermostat_current_temp = None
        self._thermostat_target_temp = None

    def thermostat_get_sensor(self) -> int:
        """Get sensor to use"""
        return BROADLINK_SENSOR_EXTERNAL if self._use_external_temp is True else BROADLINK_SENSOR_INTERNAL

    @property
    def name(self) -> str:
        """Return thermostat name"""
        return self._name

    @property
    def precision(self) -> float:
        """Return the precision of the system."""
        return PRECISION_HALVES

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def hvac_mode(self) -> str:
        """Return hvac operation ie. heat, cool mode.
        Need to be one of HVAC_MODE_*.
        """
        return self._thermostat_current_mode

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes.
        Need to be a subset of HVAC_MODES.
        """
        return [HVAC_MODE_AUTO, HVAC_MODE_HEAT, HVAC_MODE_OFF]

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported.
        Need to be one of CURRENT_HVAC_*.
        """
        return self._thermostat_current_action

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp.
        Requires SUPPORT_PRESET_MODE.
        """
        return self._preset_mode

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.
        Requires SUPPORT_PRESET_MODE.
        """
        return [PRESET_NONE, PRESET_AWAY]

    @property
    def current_temperature(self) -> Optional[float]:
        """Return the current temperature."""
        return self._thermostat_current_temp

    @property
    def target_temperature(self) -> Optional[float]:
        """Return the temperature we try to reach."""
        return self._thermostat_target_temp

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE | SUPPORT_PRESET_MODE

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return convert_temperature(self._min_temp, TEMP_CELSIUS,
                                   self.temperature_unit)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return convert_temperature(self._max_temp, TEMP_CELSIUS,
                                   self.temperature_unit)

    @property
    def device_state_attributes(self) -> dict:
        """Return the attribute(s) of the sensor"""
        return {
            'away_setpoint': self._away_setpoint,
            'manual_setpoint': self._manual_setpoint,
            'external_temp': self._external_temp,
            'room_temp': self._room_temp,
            'loop_mode': self._thermostat_loop_mode
        }

    async def async_added_to_hass(self) -> None:
        """Run when entity about to added."""
        await super().async_added_to_hass()

        # Set thermostat time
        self._hass.async_add_executor_job(self._thermostat.set_time)

        # Restore
        last_state = await self.async_get_last_state()

        if last_state is not None:
            for param in ['away_setpoint', 'manual_setpoint']:
                if param in last_state.attributes:
                    setattr(self, '_{0}'.format(param), last_state.attributes[param])

    async def async_set_temperature(self, **kwargs) -> None:
        """Set new target temperature."""
        if kwargs.get(ATTR_TEMPERATURE) is not None:
            target_temp = float(kwargs.get(ATTR_TEMPERATURE))

            device = self._thermostat.device()
            if device.auth():
                # device.set_power(BROADLINK_POWER_ON)
                device.set_mode(BROADLINK_MODE_MANUAL, self._thermostat_loop_mode, self.thermostat_get_sensor())
                device.set_temp(target_temp)

                # Save temperatures for future use
                if self._preset_mode == PRESET_AWAY:
                    self._away_setpoint = target_temp
                elif self._preset_mode == PRESET_NONE:
                    self._manual_setpoint = target_temp

        await self.async_update_ha_state()

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set operation mode."""
        device = self._thermostat.device()
        if device.auth():
            if hvac_mode == HVAC_MODE_OFF:
                device.set_power(BROADLINK_POWER_OFF)
            else:
                device.set_power(BROADLINK_POWER_ON)
                if hvac_mode == HVAC_MODE_AUTO:
                    device.set_mode(BROADLINK_MODE_AUTO, self._thermostat_loop_mode, self.thermostat_get_sensor())
                elif hvac_mode == HVAC_MODE_HEAT:
                    device.set_mode(BROADLINK_MODE_MANUAL, self._thermostat_loop_mode, self.thermostat_get_sensor())

        await self.async_update_ha_state()

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set new preset mode."""
        self._preset_mode = preset_mode

        device = self._thermostat.device()
        if device.auth():
            device.set_power(BROADLINK_POWER_ON)
            device.set_mode(BROADLINK_MODE_MANUAL, self._thermostat_loop_mode, self.thermostat_get_sensor())
            if self._preset_mode == PRESET_AWAY:
                device.set_temp(self._away_setpoint)
            elif self._preset_mode == PRESET_NONE:
                device.set_temp(self._manual_setpoint)

        await self.async_update_ha_state()

    async def async_turn_off(self) -> None:
        """Turn thermostat off"""
        await self.async_set_hvac_mode(HVAC_MODE_OFF)

    async def async_turn_on(self) -> None:
        """Turn thermostat on"""
        await self.async_set_hvac_mode(HVAC_MODE_AUTO)

    async def async_update(self) -> None:
        """Get thermostat info"""        
        data = await self._hass.async_add_executor_job(self._thermostat.read_status)

        if not data:
            return

        # Temperatures
        self._room_temp = data['room_temp']
        self._external_temp = data['external_temp']

        self._thermostat_current_temp = data['external_temp'] if self._use_external_temp else data['room_temp']

        # self._hysteresis = int(data['dif'])
        self._min_temp = int(data['svl'])
        self._max_temp = int(data['svh'])
        self._thermostat_target_temp = data['thermostat_temp']

        # Thermostat modes & status
        if data["power"] == BROADLINK_POWER_OFF:
            # Unset away mode
            self._preset_mode = PRESET_NONE
            self._thermostat_current_mode = HVAC_MODE_OFF
        else:
            # Set mode to manual when overridden auto mode or thermostat is in manual mode
            if data["auto_mode"] == BROADLINK_MODE_MANUAL or data['temp_manual'] == BROADLINK_TEMP_MANUAL:
                self._thermostat_current_mode = HVAC_MODE_HEAT
            else:
                # Unset away mode
                self._preset_mode = PRESET_NONE
                self._thermostat_current_mode = HVAC_MODE_AUTO

        # Thermostat action
        if data["power"] == BROADLINK_POWER_ON and data["active"] == BROADLINK_ACTIVE:
            self._thermostat_current_action = CURRENT_HVAC_HEAT
        elif data["power"] == BROADLINK_POWER_ON and data["active"] == BROADLINK_IDLE:
            self._thermostat_current_action = CURRENT_HVAC_IDLE
        elif data["power"] == BROADLINK_POWER_OFF:
            self._thermostat_current_action = CURRENT_HVAC_OFF
