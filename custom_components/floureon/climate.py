
import logging
from typing import List, Optional

import voluptuous as vol

from custom_components.floureon import (
    BroadlinkThermostat,
    CONF_HOST,
    CONF_USE_EXTERNAL_TEMP,
    CONF_SCHEDULE,
    CONF_UNIQUE_ID,
    CONF_PRECISION,
    CONF_USE_COOLING,
    DEFAULT_SCHEDULE,
    DEFAULT_USE_EXTERNAL_TEMP,
    DEFAULT_PRECISION,
    DEFAULT_USE_COOLING,
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

from homeassistant.components.climate import (
    ClimateEntity,
    HVACMode,
    HVACAction,
    ClimateEntityFeature,
    PLATFORM_SCHEMA
)

from homeassistant.helpers.restore_state import RestoreEntity
# Unused until HA 2023.4
# from homeassistant.util.unit_conversion import TemperatureConverter
from homeassistant.components.climate.const import (
    PRESET_NONE,
    PRESET_AWAY,
    DEFAULT_MIN_TEMP,
    DEFAULT_MAX_TEMP
)

from homeassistant.const import (
    PRECISION_HALVES,
    PRECISION_WHOLE,
    PRECISION_TENTHS,
    ATTR_TEMPERATURE,
    UnitOfTemperature,
    CONF_NAME
)

import homeassistant.helpers.config_validation as cv

_LOGGER = logging.getLogger(__name__)

PARALLEL_UPDATES = 0

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_HOST): cv.string,
    vol.Required(CONF_NAME): cv.string,
    vol.Optional(CONF_UNIQUE_ID): cv.string,
    vol.Optional(CONF_SCHEDULE, default=DEFAULT_SCHEDULE): vol.All(int, vol.Range(min=0, max=2)),
    vol.Optional(CONF_USE_EXTERNAL_TEMP, default=DEFAULT_USE_EXTERNAL_TEMP): cv.boolean,
    vol.Optional(CONF_PRECISION, default=DEFAULT_PRECISION): vol.In([PRECISION_HALVES, PRECISION_WHOLE, PRECISION_TENTHS]),
    vol.Optional(CONF_USE_COOLING, default=DEFAULT_USE_COOLING): cv.boolean
})


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Set up the generic thermostat platform."""
    async_add_entities([FloureonClimate(hass, config)])


class FloureonClimate(ClimateEntity, RestoreEntity):
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, hass, config):
        self._hass = hass
        self._thermostat = BroadlinkThermostat(config.get(CONF_HOST))

        self._name = config.get(CONF_NAME)
        self._use_external_temp = config.get(CONF_USE_EXTERNAL_TEMP)
        self._use_cooling = config.get(CONF_USE_COOLING)

        self._min_temp = DEFAULT_MIN_TEMP
        self._max_temp = DEFAULT_MAX_TEMP
        self._hysteresis = None
        self._room_temp = None
        self._external_temp = None
        self._precision = config.get(CONF_PRECISION)

        self._away_set_point = DEFAULT_MIN_TEMP
        self._manual_set_point = DEFAULT_MIN_TEMP

        self._preset_mode = None

        self._thermostat_loop_mode = config.get(CONF_SCHEDULE)
        self._thermostat_current_action = None
        self._thermostat_current_mode = None
        self._thermostat_current_temp = None
        self._thermostat_target_temp = None

        self._attr_name = self._name
        self._attr_unique_id = config.get(CONF_UNIQUE_ID)

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
        return self._precision

    @property
    def temperature_unit(self) -> str:
        """Return the unit of measurement."""
        return UnitOfTemperature.CELSIUS

    @property
    def hvac_mode(self) -> str:
        """Return hvac operation i.e. heat, cool mode.
        Need to be one of HVACMode.
        """
        return self._thermostat_current_mode

    @property
    def hvac_modes(self) -> List[str]:
        """Return the list of available hvac operation modes.
        Need to be a subset of HVACMode.
        """
        if self._use_cooling is True:
            return [HVACMode.AUTO, HVACMode.HEAT_COOL, HVACMode.OFF]

        return [HVACMode.AUTO, HVACMode.HEAT, HVACMode.OFF]

    @property
    def hvac_action(self) -> Optional[str]:
        """Return the current running hvac operation if supported.
        Need to be one of HVACAction.
        """
        return self._thermostat_current_action

    @property
    def preset_mode(self) -> Optional[str]:
        """Return the current preset mode, e.g., home, away, temp.
        Requires ClimateEntityFeature.PRESET_MODE.
        """
        return self._preset_mode

    @property
    def preset_modes(self) -> Optional[List[str]]:
        """Return a list of available preset modes.
        Requires ClimateEntityFeature.PRESET_MODE.
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
        return ClimateEntityFeature.TARGET_TEMPERATURE | ClimateEntityFeature.PRESET_MODE | ClimateEntityFeature.TURN_OFF | ClimateEntityFeature.TURN_ON

    # Backward compatibility until 2023.4
    def get_converter(self):
        try:
            from homeassistant.util.unit_conversion import TemperatureConverter
            convert = TemperatureConverter.convert
        except ModuleNotFoundError or ImportError as ee:
            from homeassistant.util.temperature import convert
        return convert

    @property
    def min_temp(self) -> float:
        """Return the minimum temperature."""
        return self.get_converter()(self._min_temp, UnitOfTemperature.CELSIUS,
                                    self.temperature_unit)

    @property
    def max_temp(self) -> float:
        """Return the maximum temperature."""
        return self.get_converter()(self._max_temp, UnitOfTemperature.CELSIUS,
                                    self.temperature_unit)

    @property
    def extra_state_attributes(self) -> dict:
        """Return the attribute(s) of the sensor"""
        return {
            'away_set_point': self._away_set_point,
            'manual_set_point': self._manual_set_point,
            'external_temp': self._external_temp,
            'room_temp': self._room_temp,
            'current_temp': self._thermostat_current_temp,
            'target_temp': self._thermostat_target_temp,
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
            for param in ['away_set_point', 'manual_set_point']:
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
                    self._away_set_point = target_temp
                elif self._preset_mode == PRESET_NONE:
                    self._manual_set_point = target_temp

        self.async_write_ha_state()

    async def async_set_hvac_mode(self, hvac_mode) -> None:
        """Set operation mode."""
        device = self._thermostat.device()
        if device.auth():
            if hvac_mode == HVACMode.OFF:
                device.set_power(BROADLINK_POWER_OFF)
            else:
                device.set_power(BROADLINK_POWER_ON)
                if hvac_mode == HVACMode.AUTO:
                    device.set_mode(BROADLINK_MODE_AUTO, self._thermostat_loop_mode, self.thermostat_get_sensor())
                elif hvac_mode == HVACMode.HEAT or hvac_mode == HVACMode.HEAT_COOL:
                    device.set_mode(BROADLINK_MODE_MANUAL, self._thermostat_loop_mode, self.thermostat_get_sensor())

        self.async_write_ha_state()

    async def async_set_preset_mode(self, preset_mode) -> None:
        """Set new preset mode."""
        self._preset_mode = preset_mode

        device = self._thermostat.device()
        if device.auth():
            device.set_power(BROADLINK_POWER_ON)
            device.set_mode(BROADLINK_MODE_MANUAL, self._thermostat_loop_mode, self.thermostat_get_sensor())
            if self._preset_mode == PRESET_AWAY:
                device.set_temp(self._away_set_point)
            elif self._preset_mode == PRESET_NONE:
                device.set_temp(self._manual_set_point)

        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Turn thermostat off"""
        await self.async_set_hvac_mode(HVACMode.OFF)

    async def async_turn_on(self) -> None:
        """Turn thermostat on"""
        await self.async_set_hvac_mode(HVACMode.AUTO)

    async def async_update(self) -> None:
        """Get thermostat info"""
        data = await self._hass.async_add_executor_job(self._thermostat.read_status)

        if not data:
            return

        # Temperatures
        self._room_temp = data['room_temp']
        self._external_temp = data['external_temp']

        self._hysteresis = int(data['dif'])
        self._min_temp = int(data['svl'])
        self._max_temp = int(data['svh'])

        self._thermostat_target_temp = data['thermostat_temp']
        self._thermostat_current_temp = data['external_temp'] if self._use_external_temp else data['room_temp']

        # Thermostat modes & status
        if data["power"] == BROADLINK_POWER_OFF:
            # Unset away mode
            self._preset_mode = PRESET_NONE
            self._thermostat_current_mode = HVACMode.OFF
        else:
            # Set mode to manual when overridden auto mode or thermostat is in manual mode
            if data["auto_mode"] == BROADLINK_MODE_MANUAL or data['temp_manual'] == BROADLINK_TEMP_MANUAL:
                if self._use_cooling is True:
                    self._thermostat_current_mode = HVACMode.HEAT_COOL
                else:
                    self._thermostat_current_mode = HVACMode.HEAT
            else:
                # Unset away mode
                self._preset_mode = PRESET_NONE
                self._thermostat_current_mode = HVACMode.AUTO

        # Thermostat action
        if data["power"] == BROADLINK_POWER_ON and data["active"] == BROADLINK_ACTIVE:
            if self._use_cooling is True:
                if self._thermostat_target_temp + self._hysteresis < self._thermostat_current_temp:
                    self._thermostat_current_action = HVACAction.COOLING
                else:
                    self._thermostat_current_action = HVACAction.HEATING
            else:
                self._thermostat_current_action = HVACAction.HEATING
        elif data["power"] == BROADLINK_POWER_ON and data["active"] == BROADLINK_IDLE:
            self._thermostat_current_action = HVACAction.IDLE
        elif data["power"] == BROADLINK_POWER_OFF:
            self._thermostat_current_action = HVACAction.OFF

        _LOGGER.debug(
            "Thermostat %s action=%s mode=%s",
            self._name, self._thermostat_current_action, self._thermostat_current_mode
        )
