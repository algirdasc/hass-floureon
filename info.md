# Your support
<a href="https://www.buymeacoffee.com/Ua0JwY9" target="_blank"><img src="https://www.buymeacoffee.com/assets/img/custom_images/orange_img.png" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;-webkit-box-shadow: 0px 3px 2px 0px rgba(190, 190, 190, 0.5) !important;" ></a>

# Intro
Component for controlling Floureon or other chinese-based WiFi smart thermostat (Beok and others). Climate component will have 3 modes: "auto" (in which will used thermostat's internal schedule), "heat (which is "manual" mode) and "off". Also, while in "heat" mode it is possible to use preset "away". Changing mode to other than "heat" will set preset to "none". 

If you want to use custom or more advanced controll, you should use switch component and generic thermostat in Home Assistant instead. See below for configuration.

# Configuration as a Climate

| Name | Type | Default | Description |
|------|:----:|:-------:|-------------|
| host ***(required)*** | string | | IP or hostname of thermostat
| mac ***(required)*** | string | | MAC address of thermostat, ex. `AB:CD:EF:00:11:22`
| name ***(required)*** | string | | Set a custom name which is displayed beside the icon.
| schedule | integer | `0` | Set which schedule to use (0 - `12345,67`, 1 - `123456,7`, 2 - `1234567`)
| use_external_temp | boolen | `true` | Set to false if you want to use thermostat`s internal temperature sensor for temperature calculation

#### Example:
```yaml
climate:
  platform: floureon
  name: livingroom_floor
  mac: 78:0f:77:00:00:00
  host: 192.168.0.1
  use_external_temp: false
```

# Configuration as a Switch
| Name | Type | Default | Description |
|------|:----:|:-------:|-------------|
| host ***(required)*** | string | | IP or hostname of thermostat
| mac ***(required)*** | string | | MAC address of thermostat, ex. `AB:CD:EF:00:11:22`
| name ***(required)*** | string | | Set a custom name which is displayed beside the icon.
| turn_off_mode | string | `min_temp` | Thermostat turn off. Set to `min_temp` and thermostat will be turned off by setting minimum temperature, `turn_off` - thermostat will be turned off by turning it off completely.
| turn_on_mode | string, float | `max_temp` | Thermostat turn on mode. Set to `max_temp` - thermostat will be turned on by setting maximum temperature, `float` - thermostat will be turned on by set temperature, ex. `20.5`. ***Note, that `.5` or `.0` is mandatory ***
| use_external_temp | boolen | `true` | Set to false if you want to use thermostat`s internal temperature sensor for temperature calculation
#### Example:
```yaml
switch:
  platform: floureon
  name: livingroom_floor
  mac: 78:0f:77:00:00:00
  host: 192.168.0.1
  turn_off_mode: min_temp
  turn_on_mode: 23.5
```
