"""hpctrl service: schedule based control of an Ecodan heat pump.

One process, one loop, every 10 seconds:
  read control inputs (emoncms inputs in Redis)
  run the controller (controller.py)
  apply its outputs: CN105 power and flow temperature, 3-way valve relay
  poll the Ecodan over CN105 and pass its readings to emonhub
  publish the mode over MQTT and the status and events to Redis for the UI

The schedule (hpctrl/config) and the input mapping (hpctrl/inputs) arrive as
retained MQTT messages from the emoncms UI. The paho network thread hands
them to the main loop. A local copy of each is kept in config/ for when MQTT
is unavailable at start.

Usage: python3 hpctrl.py [--dry-run]
  --dry-run  no serial port, relay or MQTT publishing; decisions are logged
             and shown in the UI. Safe to run while another controller is in
             charge of the heat pump, e.g. to check the inputs before switching.
"""
import os
import re
import sys
import json
import time
import datetime
import argparse
import traceback

import redis
import paho.mqtt.client as mqtt

from controller import Controller
from inputs import Inputs

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(REPO, "config")
SCHEDULE_FILE = os.path.join(CONFIG, "schedule.json")
INPUTS_FILE = os.path.join(CONFIG, "inputs.json")
MQTT_FILE = os.path.join(CONFIG, "mqtt.json")
EMONCMS_DIR = "/var/www/emoncms"

STEP_INTERVAL = 10
EVENTS_KEPT = 200
VALVE_GPIO = 27

# Heat pump off until a schedule arrives
DEFAULT_SCHEDULE = {
    "heating": [{"start": "0000", "set_point": 5.0, "flowT": 20.0, "mode": "min"}],
    "dhw": []
}


def log(message):
    print(message, flush=True)


def load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def save_json(path, data):
    try:
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    except OSError as e:
        log("Could not save %s: %s" % (path, e))


def emoncms_redis_prefix():
    """emoncms prefixes its Redis keys with [redis] prefix from settings.ini, else default-settings.ini."""
    for name in ("settings.ini", "default-settings.ini"):
        try:
            with open(os.path.join(EMONCMS_DIR, name)) as f:
                text = f.read()
        except OSError:
            continue
        section = re.search(r"^\[redis\](.*?)(?=^\[|\Z)", text, re.M | re.S)
        if section:
            m = re.search(r"^\s*prefix\s*=\s*['\"]?([^'\"\n]*)['\"]?\s*$", section.group(1), re.M)
            if m:
                return m.group(1).strip()
    return ""


class Hardware:
    """CN105 serial link and the 3-way valve relay. Errors are logged, not raised."""

    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.applied = None
        if dry_run:
            return
        import gpiozero
        from cn105 import CN105, DEFAULT_PORT
        self.valve = gpiozero.LED(VALVE_GPIO)
        self.ecodan = CN105(DEFAULT_PORT, 2400)
        self.ecodan.connect()

    def apply(self, out):
        if out != self.applied:
            log("Outputs: power %d, valve %s, flow %.1f°" % (out["power"], "DHW" if out["valve"] else "heating", out["flowT"]))
        self.applied = dict(out)
        if self.dry_run:
            return
        # CN105 commands are only sent when the value changes
        self.ecodan.set_power(out["power"])
        if out["valve"]:
            self.valve.on()
        else:
            self.valve.off()
        self.ecodan.set_temp(float(out["flowT"]))

    def poll(self):
        if self.dry_run:
            return {}
        data = {}
        for read in (self.ecodan.get_flow_return_dhw, self.ecodan.get_compressor_frequency,
                     self.ecodan.get_zone_and_outside, self.ecodan.get_modes):
            result = read()
            if isinstance(result, dict):
                data.update(result)
        return data


class Service:

    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.started = int(time.time())
        self.prefix = emoncms_redis_prefix()
        self.redis = redis.Redis()
        self.controller = Controller()
        self.inputs = Inputs(self.redis, self.prefix)
        self.hardware = Hardware(dry_run)
        self.ecodan = {}
        self.outputs = None

        self.schedule = load_json(SCHEDULE_FILE, DEFAULT_SCHEDULE)
        self.inputs.configure(load_json(INPUTS_FILE, {}))
        self.pending = {}   # topic -> payload, from the MQTT thread

        self.event("service", "hpctrl started%s, %d heating periods, inputs: %s" % (
            " (dry run)" if dry_run else "", len(self.schedule.get("heating", [])),
            ", ".join(sorted(self.inputs.mapping)) or "none"))
        log("emoncms redis prefix: '%s'" % self.prefix)
        self.mqtt_start()

    # ------------------------------------------------------------------
    # Events and status, read by the UI through hpctrl/status
    # ------------------------------------------------------------------
    def event(self, kind, text):
        log("[%s] %s" % (kind, text))
        try:
            key = self.prefix + "hpctrl:events"
            self.redis.lpush(key, json.dumps({"time": int(time.time()), "type": kind, "text": text}))
            self.redis.ltrim(key, 0, EVENTS_KEPT - 1)
        except redis.RedisError:
            pass

    def drain(self, source):
        for kind, text in source.events:
            self.event(kind, text)
        source.events.clear()

    def write_status(self, t):
        status = self.controller.status(t)
        status.update({
            "time": int(t),
            "started": self.started,
            "dry_run": self.dry_run,
            "mqtt": self.mqtt_connected,
            "inputs": self.inputs.details,
            "ecodan": self.ecodan,
        })
        self.redis.set(self.prefix + "hpctrl:status", json.dumps(status))
        return status

    # ------------------------------------------------------------------
    # MQTT
    # ------------------------------------------------------------------
    def mqtt_start(self):
        settings = {"user": "emonpi", "password": "emonpimqtt2016", "host": "127.0.0.1", "port": 1883}
        settings.update(load_json(MQTT_FILE, {}))
        self.mqtt_connected = False
        try:
            self.mqttc = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        except AttributeError:
            self.mqttc = mqtt.Client()  # paho-mqtt < 2.0
        self.mqttc.username_pw_set(settings["user"], settings["password"])
        self.mqttc.on_connect = self.on_connect
        self.mqttc.on_disconnect = self.on_disconnect
        self.mqttc.on_message = self.on_message
        # connect_async + loop_start: paho keeps retrying in its own thread
        self.mqttc.connect_async(settings["host"], int(settings["port"]), 60)
        self.mqttc.loop_start()

    # Callback signatures fit both paho-mqtt 1.x and the 2.x VERSION2 API
    def on_connect(self, client, userdata, flags, rc, *args):
        self.mqtt_connected = rc == 0
        if rc == 0:
            log("MQTT connected")
            client.subscribe("hpctrl/config")
            client.subscribe("hpctrl/inputs")
        else:
            log("MQTT connect failed: %s" % rc)

    def on_disconnect(self, client, userdata, *args):
        self.mqtt_connected = False
        log("MQTT disconnected")

    def on_message(self, client, userdata, msg):
        self.pending[msg.topic] = msg.payload

    def handle_messages(self):
        while self.pending:
            topic, payload = self.pending.popitem()
            try:
                data = json.loads(payload)
            except ValueError:
                self.event("error", "Invalid JSON on %s" % topic)
                continue
            if topic == "hpctrl/config":
                if isinstance(data, dict) and data.get("heating") and data != self.schedule:
                    self.schedule = data
                    save_json(SCHEDULE_FILE, data)
                    self.event("config", "Schedule updated: %d heating periods, %d hot water runs" % (
                        len(data["heating"]), len(data.get("dhw", []))))
            elif topic == "hpctrl/inputs":
                if isinstance(data, dict) and self.inputs.configure(data):
                    save_json(INPUTS_FILE, self.inputs.mapping)
                    self.event("config", "Inputs updated: %s" % (", ".join(sorted(self.inputs.mapping)) or "none"))

    def publish_mode(self, mode):
        if self.dry_run or not self.mqtt_connected:
            return
        sh = 1 if mode == 1 else 0
        dhw = 1 if mode == 2 else 0
        for topic, value in (("mode", mode), ("mode_sh_elec", sh), ("mode_dhw_elec", dhw),
                             ("mode_sh_heat", sh), ("mode_dhw_heat", dhw)):
            self.mqttc.publish("emon/hpmon5/" + topic, value)

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------
    def step(self):
        t = time.time()
        self.handle_messages()

        values = self.inputs.read(t)
        self.drain(self.inputs)

        outputs = self.controller.step(datetime.datetime.fromtimestamp(t), values, self.schedule)
        self.drain(self.controller)

        if outputs:
            try:
                self.hardware.apply(outputs)
            except Exception as e:
                self.event("error", "CN105 write failed: %s" % e)

        try:
            self.ecodan = self.hardware.poll()
            if self.ecodan and not self.dry_run:
                self.redis.rpush("emonhub:sub", json.dumps(dict(self.ecodan, time=int(t), node="ecodan")))
        except Exception as e:
            log("CN105 read failed: %s" % e)

        if outputs:
            self.publish_mode(outputs["mode"])

        status = self.write_status(t)
        log("room:%s flow:%s return:%s flowrate:%s cylt:%s cylb:%s ambient:%s extpipe:%s | %s: %s" % (
            tuple(fmt(values.get(k)) for k in ("room", "flow", "return", "flowrate", "cyl_top", "cyl_bot", "ambient", "extpipe"))
            + (status["label"], status["reason"])))

    def wait_for_schedule(self, timeout=20):
        """Without a local copy, wait for the retained schedule rather than run on the default."""
        if os.path.exists(SCHEDULE_FILE):
            return
        log("No local schedule, waiting for hpctrl/config")
        end = time.time() + timeout
        while time.time() < end and "hpctrl/config" not in self.pending:
            time.sleep(0.5)
        time.sleep(1)  # let hpctrl/inputs arrive too
        if "hpctrl/config" not in self.pending:
            self.event("config", "No schedule received, using the default (5° set point)")

    def run(self):
        self.wait_for_schedule()
        while True:
            start = time.time()
            try:
                self.step()
            except redis.RedisError as e:
                log("Redis error: %s" % e)
            except Exception:
                # A controller bug: log it and let systemd restart the service
                self.event("error", "Service stopped: " + traceback.format_exc().strip().splitlines()[-1])
                raise
            time.sleep(max(1.0, STEP_INTERVAL - (time.time() - start)))


def fmt(x):
    return "--" if x is None else "%.2f" % x


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="hpctrl heat pump control service")
    parser.add_argument("--dry-run", action="store_true", help="no serial, relay or MQTT publishing")
    args = parser.parse_args()
    try:
        Service(args.dry_run).run()
    except KeyboardInterrupt:
        sys.exit(0)
