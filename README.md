# Your support
This open-source project is developed in my free time.
Your donation would help me dedicate more time and resources to improve project, add new features, fix bugs,
as well as improve motivation and helps me understand, that this project is useful not only for me, but for more users.

<a href="https://www.buymeacoffee.com/algirdasci" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

# Intro
Component for controlling Floureon or other chinese-based WiFi smart thermostat (Beok and others). Climate component will have 3 modes: "auto" (in which will used thermostat's internal schedule), "heat (which is "manual" mode) and "off". Also, while in "heat" mode it is possible to use preset "away". Changing mode to other than "heat" will set preset to "none".

If you want to use custom or more advanced control, you should use switch component and generic thermostat in Home Assistant instead. See below for configuration.

# Setup

The integration can be set up either through the Home Assistant UI (recommended) or via `configuration.yaml` (see below).
Both ways can be used, but do not configure the same thermostat twice, otherwise you will get duplicate entities.

## Setup via UI

1. Go to **Settings → Devices & services → Add integration** and search for **Floureon**.
2. Enter the **host** (IP or hostname) and a **name** of the thermostat and choose how to set it up:
   * **Thermostat (climate)** - see [Configuration as a Climate](#configuration-as-a-climate).
   * **Switch** - see [Configuration as a Switch](#configuration-as-a-switch).
3. Adjust the settings for the chosen type. They correspond to the YAML options described below. For the switch, the
   temperature field is only used if the corresponding mode (turn off / turn on) is set to *Custom temperature*.

While adding, the integration connects to the thermostat to verify the connection. The MAC address of the thermostat is
used as unique id, so the same thermostat cannot be added twice. If you add a thermostat again after its IP address has
changed, the host of the existing entry is updated instead.

Every thermostat added via UI is shown as a **device** (Settings → Devices & services → Floureon) with its entity. The entity
is named after the device. Settings can be changed later with the **Configure** button of the entry; the entry is reloaded
automatically afterwards. The host cannot be changed there - to change it, add the thermostat again with the new address.

Setup via UI requires a recent Home Assistant version (options flow uses `self.config_entry` of the base class,
Home Assistant 2024.12 or newer).

# Development

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then set up the local environment:

```sh
uv sync
```

The project uses Python 3.13 by default. uv installs the integration dependencies and development tools into `.venv` using `uv.lock`.

Run the tests:

```sh
uv run pytest
```

Run lint, formatting, and type checks:

```sh
uv run ruff check .
uv run ruff format --check .
uv run ty check
```

Use `uv run ruff check --fix .` and `uv run ruff format .` to apply automatic fixes. Both tools are configured in `pyproject.toml`. ty checks the integration and tests while allowing the Home Assistant imports supplied by the host.

The tests mock Home Assistant and network I/O, so no Home Assistant installation or thermostat is needed. Home Assistant continues to install integration dependencies from `custom_components/floureon/manifest.json`; keep those requirements aligned with `pyproject.toml` when updating them. After changing dependencies, run `uv lock` and include the updated `uv.lock`.

# Configuration as a Climate

The same options are available in the UI setup, except `unique_id` (the MAC address is used).

Requires Python 3.13 or newer for `python-broadlink` 1.x.

| Name                  |  Type   | Default | Description                                                                                             |
|-----------------------|:-------:|:-------:|---------------------------------------------------------------------------------------------------------|
| host ***(required)*** | string  |         | IP or hostname of thermostat.                                                                           |
| name ***(required)*** | string  |         | Set a custom name which is displayed beside the icon.                                                   |
| unique_id             | string  |         | Set a unique id to allow entity customisation in HA GUI.                                                |
| schedule              | integer |   `0`   | Set which schedule to use (`0` - `12345,67`, `1` - `123456,7`, `2` - `1234567`).                        |
| use_external_temp     | boolean | `true`  | Set to `false` if you want to use thermostat`s internal temperature sensor for temperature calculation. |
| precision             |  float  |   0.5   | Set temperature precision `1.0` or `0.5`.                                                               |
| use_cooling           | boolean | `false` | Set to `true` if your thermostat has cooling function.                                                  |

#### Example:
```yaml
climate:
  platform: floureon
  name: livingroom_floor
  host: 192.168.0.1
  use_external_temp: false
```

# Configuration as a Switch
| Name                  |     Type      |  Default   | Description                                                                                                                                                                                                                                                         |
|-----------------------|:-------------:|:----------:|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| host ***(required)*** |    string     |            | IP or hostname of thermostat.                                                                                                                                                                                                                                       |
| name ***(required)*** |    string     |            | Set a custom name which is displayed beside the icon.                                                                                                                                                                                                               |
| unique_id             |    string     |            | Set a unique id to allow entity customisation in HA GUI.                                                                                                                                                                                                            |
| turn_off_mode         | string, float | `min_temp` | Thermostat turn off mode. Set to `min_temp` - thermostat will be turned off by setting minimum temperature, `turn_off` - thermostat will be turned off by turning it off completely, `float` - thermostat will be turned off by setting lower temperature, ex. `17` |
| turn_on_mode          | string, float | `max_temp` | Thermostat turn on mode. Set to `max_temp` - thermostat will be turned on by setting maximum temperature, `float` - thermostat will be turned on by set temperature, ex. `20.5`.                                                                                    |
| use_external_temp     |    boolean    |   `true`   | Set to `false` if you want to use thermostat`s internal temperature sensor for temperature calculation.                                                                                                                                                             |

#### Example:
```yaml
switch:
  platform: floureon
  name: livingroom_floor
  host: 192.168.0.1
  turn_off_mode: min_temp
  turn_on_mode: 23.5
```

# Time synchronization

Thermostats keep their own clock, which is used by the internal schedule ("auto" mode). The integration sets the thermostat
time to the Home Assistant time (using the time zone configured in Home Assistant) when the entity is loaded, i.e. on Home
Assistant start and whenever the entry / platform is reloaded.

To keep the clock accurate (clock drift, daylight saving time changes) you can synchronize it regularly with the
`floureon.set_time` service. It works for both climate and switch entities.

| Service             | Target                   | Description                                                      |
|---------------------|--------------------------|------------------------------------------------------------------|
| `floureon.set_time` | entity of the integration | Sets the thermostat clock to the current Home Assistant time.    |

#### Example automation:
```yaml
automation:
  - alias: Synchronize thermostat time
    trigger:
      - platform: time
        at: "03:30:00"
    action:
      - service: floureon.set_time
        target:
          entity_id:
            - climate.livingroom_floor
```

The service does not report errors back to the caller; if the thermostat is not reachable, an error is written to the
Home Assistant log (`Thermostat ... set_time error`).

If you use both climate and switch thermostats, check in **Developer tools → Actions** that the service reaches the entities
of both types.
