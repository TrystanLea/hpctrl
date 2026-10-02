# Heat pump control

Schedule based control of a 5kW Mitsubishi Ecodan via its CN105 port, running on an emonPi alongside emoncms.

![hpctrl UI](docs/screenshot.png)

- Room thermostat with a time-of-day setpoint schedule
- Low temperature "min" flow mode that tracks return temperature + a small dT, or a fixed "max" flow temperature
- Scheduled domestic hot water (DHW) runs via a 3-way valve relay
- Frost protection pump cycling based on external pipe temperature
- emoncms web UI for the schedule, with live flow, outside, electric, heat and COP

## How it fits together

```
 emoncms UI (hpctrl-module)
   │ set-config: saved to MySQL + published retained to MQTT hpctrl/config
   ▼
 hpctrl_mqtt.py ── MQTT hpctrl/config, room temp ──► redis hpctrl:config, hpmon5:roomT
   ▲                                                      │
   │ redis hpctrl:mode → MQTT emon/hpmon5/mode*           ▼
   └──────────────────────────────────────────────── hpctrl.py  (control logic)
                                                          │ redis hpctrl:r1 / ac1 / temp / mode
                                                          ▼
                                                     hpctrl_io.py ── CN105 serial ──► Ecodan
                                                          │          GPIO 27 ──► 3-way valve
                                                          └─ Ecodan readings ──► redis emonhub:sub
```

The three Python services only talk to each other through Redis:

| Key | Written by | Read by | Meaning |
|---|---|---|---|
| `hpctrl:config` | hpctrl_mqtt | hpctrl | New schedule JSON, deleted once loaded |
| `hpmon5:roomT` | hpctrl_mqtt | hpctrl | Room temperature (expires after 30 min) |
| `hpmon5:cyl_top`, `hpmon5:cyl_bot`, `hpmon5:ambient`, `hpmon5:28-00000976299e` | emonhub Redis interfacer | hpctrl | Cylinder, ambient and external pipe temperatures |
| `axioma:axioma_FlowT`, `_ReturnT`, `_FlowRate` | emonhub Redis interfacer (heat meter) | hpctrl | Flow, return and flow rate |
| `hpctrl:r1` | hpctrl | hpctrl_io | Heat pump on (1) / off (0) |
| `hpctrl:ac1` | hpctrl | hpctrl_io | 3-way valve: DHW (1) / heating (0) |
| `hpctrl:temp` | hpctrl | hpctrl_io | Flow temperature setpoint sent over CN105 |
| `hpctrl:mode` | hpctrl | hpctrl_mqtt | 0 off, 1 space heating, 2 DHW |

## Directory layout

```
hpctrl-module/   emoncms web module, symlinked to /var/www/emoncms/Modules/hpctrl
service/         the long-running services and the CN105 protocol library
systemd/         unit template and install script
config/          *.default / *.example files are tracked, local copies are gitignored
tools/           CN105 debugging and bench scripts
archive/         earlier versions of the controller, kept for reference
docs/
```

## Install

Web module:

    ln -s /opt/emoncms/modules/hpctrl/hpctrl-module /var/www/emoncms/Modules/hpctrl

Then run Admin > Update database in emoncms to create the `hpctrl` table.

Local config:

    cp config/ui_settings.default.php config/ui_settings.php   # emoncms user ids allowed to use the UI
    cp config/mqtt.example.json config/mqtt.json              # optional, only if not using emonSD MQTT defaults

Services:

    ./systemd/install_service.sh hpctrl_io
    ./systemd/install_service.sh hpctrl
    ./systemd/install_service.sh hpctrl_mqtt

Logs: `sudo journalctl -f -u hpctrl -o cat`

## Schedule format

The UI writes this for you; see [config/schedule.example.json](config/schedule.example.json). `start` is `HHMM`. The period in force is the last one whose start has passed. DHW runs start at exactly their `start` minute and stop once the cylinder reaches `T`.

## CN105 serial port

`service/cn105.py` defaults to the CP2102 adapter's `/dev/serial/by-id/...` path, which is stable across reboots. If you use a different adapter, change `DEFAULT_PORT` there. To read the heat pump directly:

    python3 tools/readinfo.py
