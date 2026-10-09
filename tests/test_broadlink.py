"""Exercise the real Broadlink API with network I/O and HA boundaries mocked.

Run with: python -m pytest (requires pytest, voluptuous, python-broadlink==1.0.6).
These tests do not require a Home Assistant installation or a thermostat.
"""

import asyncio
import importlib
import sys
from datetime import datetime
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock, call

import broadlink
import broadlink.exceptions
import pytest
import voluptuous as vol
from broadlink.climate import hysen


@pytest.fixture
def integration(monkeypatch):
    """Provide only the Home Assistant interfaces used by these platforms."""

    class Entity:
        async_added_to_hass = AsyncMock()
        async_update_ha_state = AsyncMock()
        async_write_ha_state = Mock()

    class RestoreEntity:
        async_get_last_state = AsyncMock(return_value=None)

    constants = dict(
        PRECISION_HALVES=0.5,
        PRECISION_WHOLE=1,
        PRECISION_TENTHS=0.1,
        ATTR_TEMPERATURE='temperature',
        CONF_NAME='name',
        STATE_ON='on',
        STATE_OFF='off',
        STATE_UNAVAILABLE='unavailable',
        UnitOfTemperature=SimpleNamespace(CELSIUS='°C'),
    )
    modules = {
        'homeassistant': {},
        'homeassistant.const': constants,
        'homeassistant.components': {},
        'homeassistant.components.climate': dict(
            ClimateEntity=Entity,
            PLATFORM_SCHEMA=vol.Schema({}),
            HVACMode=SimpleNamespace(AUTO='auto', HEAT='heat', HEAT_COOL='heat_cool', OFF='off'),
            HVACAction=SimpleNamespace(HEATING='heating', COOLING='cooling', IDLE='idle', OFF='off'),
            ClimateEntityFeature=SimpleNamespace(TARGET_TEMPERATURE=1, PRESET_MODE=2, TURN_OFF=4, TURN_ON=8),
        ),
        'homeassistant.components.climate.const': dict(
            PRESET_NONE='none',
            PRESET_AWAY='away',
            DEFAULT_MIN_TEMP=7,
            DEFAULT_MAX_TEMP=35,
        ),
        'homeassistant.components.switch': dict(SwitchEntity=Entity, PLATFORM_SCHEMA=vol.Schema({})),
        'homeassistant.helpers': {},
        'homeassistant.helpers.restore_state': dict(RestoreEntity=RestoreEntity),
        'homeassistant.helpers.config_validation': dict(string=str, boolean=bool),
    }
    for name, attributes in modules.items():
        module = ModuleType(name)
        module.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, module)
        if '.' in name:
            parent, attribute = name.rsplit('.', 1)
            setattr(sys.modules[parent], attribute, module)
    for name in [
        'custom_components.floureon.climate',
        'custom_components.floureon.switch',
        'custom_components.floureon',
    ]:
        monkeypatch.delitem(sys.modules, name, raising=False)
    return SimpleNamespace(
        thermostat=importlib.import_module('custom_components.floureon'),
        climate=importlib.import_module('custom_components.floureon.climate'),
        switch=importlib.import_module('custom_components.floureon.switch'),
    )


@pytest.fixture
def device(monkeypatch):
    device = hysen(('192.0.2.1', 80), bytes(6), 0x4EAD)
    monkeypatch.setattr(device, 'auth', AsyncMock(return_value=True))
    monkeypatch.setattr(device, 'send_request', AsyncMock())
    monkeypatch.setattr(device, 'aclose', AsyncMock(wraps=device.aclose))
    monkeypatch.setattr(broadlink, 'hello', AsyncMock(return_value=device))
    return device


def test_discovery_retries_network_timeouts(integration, device):
    error = broadlink.exceptions.NetworkTimeoutError(-4000, 'Timeout')
    hello = cast(AsyncMock, broadlink.hello)
    hello.side_effect = [error, error, device]
    thermostat = integration.thermostat.BroadlinkThermostat('192.0.2.1')
    assert asyncio.run(thermostat.device()) is device
    assert hello.await_args_list == [call('192.0.2.1', timeout=3)] * 3


def test_discovery_raises_after_three_timeouts(integration, device):
    hello = cast(AsyncMock, broadlink.hello)
    hello.side_effect = broadlink.exceptions.NetworkTimeoutError(-4000, 'Timeout')
    thermostat = integration.thermostat.BroadlinkThermostat('192.0.2.1')
    with pytest.raises(broadlink.exceptions.NetworkTimeoutError):
        asyncio.run(thermostat.device())
    assert hello.await_count == 3


def test_read_status_returns_device_data(integration, device, monkeypatch):
    status = {'room_temp': 21.5}
    monkeypatch.setattr(device, 'get_full_status', AsyncMock(return_value=status))
    thermostat = integration.thermostat.BroadlinkThermostat('192.0.2.1')
    assert asyncio.run(thermostat.read_status()) == status
    device.auth.assert_awaited_once()
    device.aclose.assert_awaited_once()


def test_read_status_closes_device_on_failure(integration, device):
    device.send_request.side_effect = OSError('Network failure')
    thermostat = integration.thermostat.BroadlinkThermostat('192.0.2.1')
    assert asyncio.run(thermostat.read_status()) is None
    device.aclose.assert_awaited_once()


def test_read_status_preserves_cancellation(integration, device):
    device.send_request.side_effect = asyncio.CancelledError()
    thermostat = integration.thermostat.BroadlinkThermostat('192.0.2.1')
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(thermostat.read_status())
    device.aclose.assert_awaited_once()


def test_set_time_sends_current_time(integration, device, monkeypatch):
    now = datetime(2026, 10, 9, 12, 34, 56)
    monkeypatch.setattr(integration.thermostat, 'datetime', SimpleNamespace(now=lambda: now))
    thermostat = integration.thermostat.BroadlinkThermostat('192.0.2.1')
    asyncio.run(thermostat.set_time())
    device.send_request.assert_awaited_once_with([1, 16, 0, 8, 0, 2, 4, 12, 34, 56, 5])
    device.aclose.assert_awaited_once()


@pytest.mark.parametrize(
    'method,args,requests',
    [
        ('async_set_temperature', {'temperature': 21.5}, [[1, 6, 0, 2, 16, 1], [1, 6, 0, 1, 0, 43]]),
        ('async_set_hvac_mode', {'hvac_mode': 'off'}, [[1, 6, 0, 0, 0, 0]]),
        ('async_set_hvac_mode', {'hvac_mode': 'auto'}, [[1, 6, 0, 0, 0, 1], [1, 6, 0, 2, 17, 1]]),
        ('async_set_hvac_mode', {'hvac_mode': 'heat'}, [[1, 6, 0, 0, 0, 1], [1, 6, 0, 2, 16, 1]]),
        (
            'async_set_preset_mode',
            {'preset_mode': 'away'},
            [[1, 6, 0, 0, 0, 1], [1, 6, 0, 2, 16, 1], [1, 6, 0, 1, 0, 14]],
        ),
    ],
)
def test_climate_commands_send_requests(integration, device, method, args, requests):
    entity = integration.climate.FloureonClimate(
        Mock(), {'host': '192.0.2.1', 'schedule': 0, 'use_external_temp': True}
    )
    asyncio.run(getattr(entity, method)(**args))
    assert device.send_request.await_args_list == [call(request) for request in requests]
    device.auth.assert_awaited_once()
    device.aclose.assert_awaited_once()


@pytest.mark.parametrize(
    'method,off_mode,on_mode,requests',
    [
        ('async_turn_on', 'min_temp', 'max_temp', [[1, 6, 0, 0, 0, 1], [1, 6, 0, 2, 16, 1], [1, 6, 0, 1, 0, 70]]),
        ('async_turn_on', 'min_temp', 21.5, [[1, 6, 0, 0, 0, 1], [1, 6, 0, 2, 16, 1], [1, 6, 0, 1, 0, 43]]),
        ('async_turn_off', 'turn_off', 'max_temp', [[1, 6, 0, 0, 0, 0]]),
        ('async_turn_off', 'min_temp', 'max_temp', [[1, 6, 0, 2, 16, 1], [1, 6, 0, 1, 0, 14]]),
        ('async_turn_off', 17, 'max_temp', [[1, 6, 0, 2, 16, 1], [1, 6, 0, 1, 0, 34]]),
    ],
)
def test_switch_commands_send_requests(integration, device, method, off_mode, on_mode, requests):
    entity = integration.switch.FloureonSwitch(
        Mock(),
        {
            'host': '192.0.2.1',
            'use_external_temp': True,
            'turn_off_mode': off_mode,
            'turn_on_mode': on_mode,
        },
    )
    asyncio.run(getattr(entity, method)())
    assert device.send_request.await_args_list == [call(request) for request in requests]
    device.aclose.assert_awaited_once()


@pytest.mark.parametrize('platform,class_name', [('climate', 'FloureonClimate'), ('switch', 'FloureonSwitch')])
def test_entity_startup_sets_time(integration, device, platform, class_name):
    entity = getattr(getattr(integration, platform), class_name)(
        Mock(),
        {
            'host': '192.0.2.1',
            'turn_off_mode': 'min_temp',
            'turn_on_mode': 'max_temp',
        },
    )
    asyncio.run(entity.async_added_to_hass())
    assert device.send_request.await_args.args[0][:7] == [1, 16, 0, 8, 0, 2, 4]
    device.aclose.assert_awaited_once()


@pytest.mark.parametrize('platform,class_name', [('climate', 'FloureonClimate'), ('switch', 'FloureonSwitch')])
def test_entity_polling_updates_temperature(integration, device, monkeypatch, platform, class_name):
    monkeypatch.setattr(
        device,
        'get_full_status',
        AsyncMock(
            return_value={
                'room_temp': 20,
                'external_temp': 21.5,
                'thermostat_temp': 22,
                'dif': 1,
                'svl': 7,
                'svh': 35,
                'power': 1,
                'active': 1,
                'auto_mode': 0,
                'temp_manual': 0,
            }
        ),
    )
    entity = getattr(getattr(integration, platform), class_name)(
        Mock(),
        {
            'host': '192.0.2.1',
            'use_external_temp': True,
            'turn_off_mode': 'min_temp',
            'turn_on_mode': 'max_temp',
        },
    )
    asyncio.run(entity.async_update())
    assert entity._thermostat_current_temp == 21.5
    assert entity._thermostat_target_temp == 22
    device.aclose.assert_awaited_once()
