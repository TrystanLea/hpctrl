"""CN105 serial link to the Ecodan and the 3-way valve relay.

CN105 commands are only sent when the value changes, and the Ecodan's reply
isn't checked, so a lost command would never be repeated. Verifier compares
what was sent with the power and setpoint the Ecodan reports on each poll and
asks for a resend when they disagree.
"""

VALVE_GPIO = 27


def log(message):
    print(message, flush=True)


class Verifier:
    """Pure logic: check(sent, reported) -> fields to resend, with events and a per-field status."""

    CONFIRM_POLLS = 2   # a mismatch must last this many polls before a resend: the Ecodan may lag a poll
    MAX_RESENDS = 3     # then give up until the value sent changes (the Ecodan may be clamping it)

    # field sent -> key in the Ecodan's get_modes reply
    FIELDS = {"power": "power", "flowT": "heating_setpoint"}

    def __init__(self):
        self.fields = {}
        self.events = []

    @staticmethod
    def matches(field, sent, reported):
        if field == "flowT":
            # cn105.set_temp sends 0.1° resolution
            return abs(int(sent * 10) * 0.1 - reported) < 0.06
        return int(sent) == int(reported)

    def check(self, sent, reported):
        resend = []
        for field, key in self.FIELDS.items():
            if field not in sent:
                continue
            f = self.fields.get(field)
            if f is None or f["sent"] != sent[field]:
                f = self.fields[field] = {"sent": sent[field], "reported": None, "misses": 0, "resends": 0, "state": "pending"}
            if key not in reported:
                f["state"] = "unknown"
                continue
            f["reported"] = reported[key]

            if self.matches(field, f["sent"], f["reported"]):
                if f["resends"]:
                    self.events.append(("hardware", "Ecodan %s confirmed at %s after %d resend%s" % (
                        field, f["reported"], f["resends"], "" if f["resends"] == 1 else "s")))
                f.update(misses=0, resends=0, state="ok")
                continue

            f["misses"] += 1
            if f["state"] == "failed" or f["misses"] < self.CONFIRM_POLLS:
                continue
            if f["resends"] < self.MAX_RESENDS:
                f["resends"] += 1
                f["misses"] = 0
                f["state"] = "resending"
                resend.append(field)
                if f["resends"] == 1:
                    self.events.append(("hardware", "Ecodan reports %s %s, sent %s: resending" % (field, f["reported"], f["sent"])))
            else:
                f["state"] = "failed"
                self.events.append(("hardware", "Ecodan %s not confirmed after %d resends: reports %s, sent %s" % (
                    field, self.MAX_RESENDS, f["reported"], f["sent"])))
        return resend

    def status(self):
        return {field: {k: f[k] for k in ("state", "sent", "reported")} for field, f in self.fields.items()}

    def ok(self):
        return all(f["state"] in ("ok", "unknown") for f in self.fields.values())


class Hardware:
    """Errors from the serial port are raised to the service, which logs them."""

    def __init__(self, dry_run):
        self.dry_run = dry_run
        self.applied = None
        self.verifier = Verifier()
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
        """Read the Ecodan, then resend any command it hasn't taken up."""
        if self.dry_run:
            return {}
        data = {}
        for read in (self.ecodan.get_flow_return_dhw, self.ecodan.get_compressor_frequency,
                     self.ecodan.get_zone_and_outside, self.ecodan.get_modes):
            result = read()
            if isinstance(result, dict):
                data.update(result)

        if self.applied:
            for field in self.verifier.check(self.applied, data):
                log("Resending %s" % field)
                if field == "power":
                    self.ecodan.last_power = -1
                    self.ecodan.set_power(self.applied["power"])
                else:
                    self.ecodan.last_temp = -1
                    self.ecodan.set_temp(float(self.applied["flowT"]))
        return data
