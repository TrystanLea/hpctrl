"""Control inputs read from emoncms inputs in Redis.

The UI settings page maps each role to an emoncms input id. emoncms keeps the
latest value of each input in the Redis hash input:lastvalue:<id> (time, value).
"""

ROLES = ("room", "flow", "return", "flowrate", "cyl_top", "cyl_bot", "ambient", "extpipe")

# Seconds after which a value is treated as missing
STALE_AFTER = {"room": 1800}
STALE_DEFAULT = 600


class Inputs:

    def __init__(self, redis, prefix=""):
        self.redis = redis
        self.prefix = prefix
        self.mapping = {}          # role -> emoncms input id
        self.details = {}          # role -> {id, value, age, stale} for the status
        self.stale = set()
        self.events = []

    def configure(self, mapping):
        """mapping: {role: input id}. Unknown roles and ids <= 0 are ignored. Returns True if changed."""
        clean = {}
        for role, inputid in (mapping or {}).items():
            try:
                inputid = int(inputid)
            except (TypeError, ValueError):
                continue
            if role in ROLES and inputid > 0:
                clean[role] = inputid
        if clean == self.mapping:
            return False
        self.mapping = clean
        self.stale = set()
        return True

    def read(self, t):
        """{role: value} for configured roles, None when stale or unreadable."""
        values, details = {}, {}
        for role, inputid in self.mapping.items():
            value, age = None, None
            try:
                ts, raw = self.redis.hmget("%sinput:lastvalue:%d" % (self.prefix, inputid), "time", "value")
                if ts is not None and raw is not None:
                    age = max(0, int(t - float(ts)))
                    value = float(raw)
            except Exception as e:
                self.events.append(("error", "Reading %s input %d: %s" % (role, inputid, e)))
            stale = value is None or age > STALE_AFTER.get(role, STALE_DEFAULT)
            values[role] = None if stale else value
            details[role] = {"id": inputid, "value": value, "age": age, "stale": stale}

            if stale and role not in self.stale:
                self.stale.add(role)
                self.events.append(("input", "%s input stale (%s)" % (role, "no value" if age is None else "%d s old" % age)))
            elif not stale and role in self.stale:
                self.stale.discard(role)
                self.events.append(("input", "%s input back" % role))
        self.details = details
        return values
