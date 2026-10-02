"""Heat pump control logic.

Pure logic: no Redis, serial, MQTT or clock access, so it can be tested with
fake inputs (see tests/test_controller.py). The service calls step() about
every 10 seconds and applies the outputs it returns.

Timed sequences (start, stop, end of a hot water run) are phases with an end
time rather than sleeps, so the service keeps polling the heat pump while they
run.
"""
import math

# Tunable from the UI settings page. LIMITS bounds what the UI can set.
PARAMS = {
    "hysteresis": 0.1,            # thermostat: on below set point - h, off above set point + h
    "room_fallback": 10.0,        # room temperature assumed when the room input is stale (heating on)
    "idle_flowT": 20.0,           # flow target while starting and stopping
    "start_hold": 60,             # after turning on, hold the idle flow target this long
    "stop_delay": 60,             # at set point: idle flow target this long, then pump off
    "stop_hold": 25,              # then wait this long before acting again
    "min_rT1": 24.0,              # Min mode: flow = return + dT, dT linear in return
    "min_dT1": 2.8,               #   through (min_rT1, min_dT1) and (min_rT2, min_dT2)
    "min_rT2": 28.5,
    "min_dT2": 2.5,
    "ratchet_after": 300,         # Min mode: flow target can't fall after this long (rides through defrosts)
    "frost_temperature": 4.0,     # external pipe temperature below which the pump is cycled
    "frost_off_interval": 1800,   # pump on after this long off
    "frost_on_duration": 600,     # for this long
    "frost_flowT": 14.0,
    "dhw_window": 300,            # a hot water run starts within this long of its start time, once a day
    "dhw_dT": 7.0,                # flow target above cylinder bottom (Min) or target (Max without flowT)
    "dhw_bottom_margin": 3.0,     # run until top >= T and bottom >= T - margin
    "dhw_heating_delay": 60,      # space heating waits this long after a hot water run
}

LIMITS = {
    "hysteresis": (0.05, 1.0), "room_fallback": (5, 25), "idle_flowT": (15, 30),
    "start_hold": (0, 600), "stop_delay": (0, 600), "stop_hold": (0, 600),
    "min_rT1": (10, 50), "min_dT1": (0.5, 10), "min_rT2": (10, 50), "min_dT2": (0.5, 10),
    "ratchet_after": (0, 3600),
    "frost_temperature": (-5, 10), "frost_off_interval": (60, 14400),
    "frost_on_duration": (60, 3600), "frost_flowT": (5, 30),
    "dhw_window": (60, 3600), "dhw_dT": (2, 15), "dhw_bottom_margin": (0, 10),
    "dhw_heating_delay": (0, 3600),
}

DHW_STOP_STEPS = (20, 10, 10)     # idle flow -> pump off -> valve to heating -> done
DHW_BOOST_T = 45.0                # manual hot water run target when there is no scheduled run to copy

REQUIRED = ("room", "flow", "return", "flowrate")
MODE_OFF, MODE_HEATING, MODE_DHW = 0, 1, 2


def minutes(start):
    """'0730' -> 450"""
    s = str(start).zfill(4)
    return int(s[:2]) * 60 + int(s[2:4])


def active_period(periods, hm):
    """Last period started by hm (minutes), else the last period from yesterday."""
    if not periods:
        return None
    active = periods[-1]
    for period in sorted(periods, key=lambda p: minutes(p["start"])):
        if hm >= minutes(period["start"]):
            active = period
    return active


def number(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


class Controller:

    def __init__(self, params=None):
        self.p = dict(PARAMS)
        self.events = []           # (kind, text), drained by the service
        if params:
            self.set_params(params)

        self.mode = "heating"      # or "dhw"
        self.state = 0             # 1 while the heat pump is heating
        self.phase = None          # (name, until)
        self.outputs = None        # {power, valve, flowT, mode} once decided
        self.first_run = True
        self.waiting = []
        self.period = None
        self.hp = {}

        self.last_flowT_target = 0
        self.heating_start = 0
        self.frost_state = 0
        self.frost_timer = 0
        self.dhw_run = None
        self.dhw_complete = 0
        self.dhw_done = set()      # (date, start minutes) of runs already started
        self.dhw_request = None    # manual run waiting to start
        self.dhw_cancel = False

    def set_params(self, params):
        """Defaults overridden by params. Unknown names and out of range values are rejected with an event.
        Returns True if the values in use changed."""
        new = dict(PARAMS)
        for name, value in (params or {}).items():
            value = number(value)
            if name not in LIMITS or value is None:
                self.event("error", "Ignored parameter %s" % name)
            elif not LIMITS[name][0] <= value <= LIMITS[name][1]:
                self.event("error", "Ignored %s = %g: outside %g to %g" % ((name, value) + LIMITS[name]))
            else:
                new[name] = value
        if new["min_rT1"] == new["min_rT2"]:
            self.event("error", "Ignored Min curve: the two return temperatures must differ")
            for k in ("min_rT1", "min_dT1", "min_rT2", "min_dT2"):
                new[k] = PARAMS[k]
        changed = new != self.p
        self.p = new
        return changed

    def request_dhw(self, run):
        """Start a hot water run now, outside the schedule."""
        self.dhw_request = run

    def cancel_dhw(self):
        self.dhw_cancel = True

    def event(self, kind, text):
        self.events.append((kind, text))

    def set(self, **kw):
        self.outputs.update(kw)

    # ------------------------------------------------------------------
    # inputs: {role: value}, None when stale, role absent when not configured
    # returns the outputs to apply, or None before the first decision
    # ------------------------------------------------------------------
    def step(self, now, inputs, schedule):
        t = now.timestamp()
        hm = now.hour * 60 + now.minute
        self.period = active_period(schedule.get("heating", []), hm)

        waiting = [k for k in REQUIRED if k not in inputs]
        waiting += [k for k in REQUIRED if k != "room" and k in inputs and inputs[k] is None]
        if self.period is None:
            waiting.append("schedule")
        if waiting != self.waiting:
            if waiting:
                self.event("input", "Waiting for " + ", ".join(waiting) + ", outputs held")
            elif self.waiting:
                self.event("input", "Inputs available, control resumed")
            self.waiting = waiting
        if waiting:
            return self.current()

        hp = dict(inputs)
        if hp["room"] is None:
            hp["room"] = self.p["room_fallback"]
        self.hp = hp

        if self.first_run:
            self.first_run = False
            if hp["flowrate"] > 0.0:
                self.state = 1
                self.outputs = {"power": 1, "valve": 0, "flowT": self.p["idle_flowT"], "mode": MODE_HEATING}
                self.event("heating", "Heat pump running at start (flow rate %.2f), heating" % hp["flowrate"])
            else:
                self.outputs = {"power": 0, "valve": 0, "flowT": self.p["idle_flowT"], "mode": MODE_OFF}
                self.event("heating", "Heat pump off at start")

        if self.phase and self.run_phase(t):
            return self.current()

        if self.mode == "heating":
            self.dhw_start(now, hm, schedule)
        self.manual_dhw(t)
        if self.phase:
            return self.current()

        if self.mode == "heating":
            self.heating(t)
        else:
            self.dhw(t)
        return self.current()

    def current(self):
        return dict(self.outputs) if self.outputs else None

    # ------------------------------------------------------------------
    # Phases: returns True while the phase is still running
    # ------------------------------------------------------------------
    def run_phase(self, t):
        name, until = self.phase
        if t < until:
            return True
        p = self.p
        if name == "starting":
            self.phase = None
            return False
        if name == "stopping":
            self.set(power=0, valve=0, mode=MODE_OFF)
            self.phase = ("stop_hold", t + p["stop_hold"])
            return True
        if name == "stop_hold":
            self.last_flowT_target = 0
            self.frost_state = 0
            self.frost_timer = t
            self.phase = None
            return False
        if name == "dhw_pump_off":
            self.set(power=0)
            self.phase = ("dhw_valve_off", t + DHW_STOP_STEPS[1])
            return True
        if name == "dhw_valve_off":
            self.set(valve=0)
            self.phase = ("dhw_done", t + DHW_STOP_STEPS[2])
            return True
        if name == "dhw_done":
            self.state = 0
            self.mode = "heating"
            self.dhw_run = None
            self.last_flowT_target = 0
            self.dhw_complete = t
            self.set(mode=MODE_OFF)
            self.phase = None
            return False
        self.phase = None
        return False

    # ------------------------------------------------------------------
    # Space heating
    # ------------------------------------------------------------------
    def heating(self, t):
        p, hp = self.p, self.hp
        if t - self.dhw_complete <= p["dhw_heating_delay"]:
            return

        sp = float(self.period["set_point"])
        h = p["hysteresis"]

        if hp["room"] >= sp + h and self.state != 0:
            self.state = 0
            self.set(flowT=p["idle_flowT"])
            self.phase = ("stopping", t + p["stop_delay"])
            self.event("heating", "Heating off: room %.1f° reached %.1f°" % (hp["room"], sp + h))
            return

        if hp["room"] <= sp - h and self.state != 1:
            self.state = 1
            self.set(power=1, valve=0, flowT=p["idle_flowT"], mode=MODE_HEATING)
            self.heating_start = t
            self.phase = ("starting", t + p["start_hold"])
            self.event("heating", "Heating on: room %.1f° below %.1f°" % (hp["room"], sp - h))
            return

        if self.state == 0:
            self.frost(t)
            self.set(mode=MODE_OFF)
        else:
            self.set(flowT=self.flow_target(t), mode=MODE_HEATING)

    def flow_target(self, t):
        period = self.period
        if period.get("mode") != "min":
            return float(period["flowT"])

        ret = self.hp["return"]
        p = self.p
        rT1, dt1, rT2, dt2 = p["min_rT1"], p["min_dT1"], p["min_rT2"], p["min_dT2"]
        m = (dt2 - dt1) / (rT2 - rT1)
        c = dt1 - m * rT1
        target = ret + m * ret + c

        # Do not let the target fall during a heating cycle, so a defrost doesn't pull it down
        if t - self.heating_start < self.p["ratchet_after"]:
            self.last_flowT_target = target
        elif target < self.last_flowT_target:
            target = self.last_flowT_target
        else:
            self.last_flowT_target = target

        target = math.ceil(target * 0.5) * 2
        return min(target, float(period["flowT"]))

    def frost(self, t):
        p = self.p
        if "extpipe" not in self.hp:
            return  # no external pipe input configured: frost protection off
        ext = self.hp["extpipe"]
        if ext is None:
            ext = 0.0  # stale: assume freezing

        if ext > p["frost_temperature"]:
            if self.frost_state == 1:
                self.frost_state = 0
                self.frost_timer = 0
                self.set(power=0)
                self.event("frost", "Frost protection pump off: pipe %.1f°" % ext)
            return

        if self.frost_state == 0 and t - self.frost_timer > p["frost_off_interval"]:
            self.frost_timer = t
            self.frost_state = 1
            self.set(power=1, flowT=p["frost_flowT"])
            self.event("frost", "Frost protection pump on: pipe %.1f°" % ext)
        elif self.frost_state == 1 and t - self.frost_timer > p["frost_on_duration"]:
            self.frost_timer = t
            self.frost_state = 0
            self.set(power=0, flowT=p["frost_flowT"])
            self.event("frost", "Frost protection pump off")

    # ------------------------------------------------------------------
    # Hot water
    # ------------------------------------------------------------------
    def dhw_start(self, now, hm, schedule):
        today = now.date()
        self.dhw_done = {d for d in self.dhw_done if d[0] == today}
        for run in schedule.get("dhw", []):
            start = minutes(run["start"])
            key = (today, start)
            if 0 <= (hm - start) * 60 < self.p["dhw_window"] and key not in self.dhw_done:
                self.dhw_done.add(key)
                if "cyl_top" not in self.hp or "cyl_bot" not in self.hp:
                    self.event("dhw", "Hot water run skipped: cylinder inputs not configured")
                    continue
                self.mode = "dhw"
                self.dhw_run = run
                self.event("dhw", "Hot water run started, target %.1f°" % float(run["T"]))
                return

    def manual_dhw(self, t):
        """Requests from the UI, handled once any start or stop sequence has finished."""
        if self.dhw_cancel:
            self.dhw_cancel = False
            self.dhw_request = None
            if self.mode == "dhw" and not self.phase:
                self.event("dhw", "Hot water run stopped manually")
                self.dhw_stop(t)
        if self.dhw_request and self.mode == "dhw":
            self.dhw_request = None  # already running
        if self.dhw_request and self.mode == "heating":
            run, self.dhw_request = self.dhw_request, None
            if "cyl_top" not in self.hp or "cyl_bot" not in self.hp:
                self.event("dhw", "Hot water run skipped: cylinder inputs not configured")
                return
            self.mode = "dhw"
            self.dhw_run = run
            self.event("dhw", "Hot water run started manually, target %.1f°" % float(run["T"]))

    def dhw(self, t):
        p, hp, run = self.p, self.hp, self.dhw_run
        self.set(mode=MODE_DHW)
        T = float(run["T"])
        top, bot = hp.get("cyl_top"), hp.get("cyl_bot")

        if top is None or bot is None:
            self.event("dhw", "Hot water run stopped: cylinder temperature missing")
            self.dhw_stop(t)
        elif top < T or bot < T - p["dhw_bottom_margin"]:
            if run.get("mode") == "max":
                flowT = number(run.get("flowT"))
                if flowT is None:
                    flowT = T + p["dhw_dT"]
            else:
                flowT = bot + p["dhw_dT"]
            self.set(power=1, valve=1, flowT=flowT)
            self.state = 1
        else:
            self.event("dhw", "Hot water complete: top %.1f°, bottom %.1f°" % (top, bot))
            self.dhw_stop(t)

    def dhw_stop(self, t):
        self.set(flowT=self.p["idle_flowT"])
        self.phase = ("dhw_pump_off", t + DHW_STOP_STEPS[0])

    # ------------------------------------------------------------------
    # Status for the UI
    # ------------------------------------------------------------------
    def describe(self, t):
        """Short label and a sentence on why."""
        p, hp = self.p, self.hp
        if self.waiting:
            return "Waiting", "Waiting for " + ", ".join(self.waiting)
        if self.outputs is None:
            return "Starting", "Service starting"
        phase = self.phase[0] if self.phase else None
        if phase == "starting":
            return "Starting", "Pump on, flow target held at %.0f° for %d s" % (p["idle_flowT"], p["start_hold"])
        if phase in ("stopping", "stop_hold"):
            return "Stopping", "Set point reached, running down before switching off"
        if self.mode == "dhw":
            if phase:
                return "Hot water", "Hot water run finishing"
            return "Hot water", "Cylinder top %s / bottom %s, target %.1f°" % (
                deg(hp.get("cyl_top")), deg(hp.get("cyl_bot")), float(self.dhw_run["T"]))
        if t - self.dhw_complete <= p["dhw_heating_delay"]:
            return "Paused", "Space heating resumes %d s after a hot water run" % p["dhw_heating_delay"]

        sp = float(self.period["set_point"])
        h = p["hysteresis"]
        if self.state == 1:
            return "Heating", "Room %s, heating until %.1f°, flow target %.0f°" % (
                deg(hp.get("room")), sp + h, self.outputs["flowT"])
        if self.frost_state == 1:
            return "Frost protection", "External pipe %s, circulating" % deg(hp.get("extpipe"))
        return "Holding", "Room %s, heating starts below %.1f°" % (deg(hp.get("room")), sp - h)

    def status(self, t):
        label, reason = self.describe(t)
        return {
            "label": label,
            "reason": reason,
            "mode": self.mode,
            "state": self.state,
            "phase": self.phase[0] if self.phase else None,
            "frost": self.frost_state,
            "outputs": self.outputs,
            "period": self.period,
            "dhw_run": self.dhw_run,
            "params": self.p,
            "param_defaults": PARAMS,
            "param_limits": LIMITS,
        }


def deg(x):
    return "--" if x is None else "%.1f°" % x
