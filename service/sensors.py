"""Control sensors read from emoncms feeds in Redis.

The UI settings page maps each role to an emoncms feed id. emoncms keeps the
latest value of each feed in the Redis hash feed:<id> (time, value, name, tag),
updated on every post. Feeds come after input processing, so any scaling or
calibration set up in emoncms is applied, and their history is on disk.
"""

ROLES = ("room", "flow", "return", "flowrate", "cyl_top", "cyl_bot", "ambient", "extpipe")

# Seconds after which a value is treated as missing
STALE_AFTER = {"room": 1800}
STALE_DEFAULT = 600


class Sensors:

    def __init__(self, redis, prefix=""):
        self.redis = redis
        self.prefix = prefix
        self.mapping = {}          # role -> emoncms feed id
        self.details = {}          # role -> {id, name, value, age, stale} for the status
        self.stale = set()
        self.events = []

    def configure(self, mapping):
        """mapping: {role: feed id}. Unknown roles and ids <= 0 are ignored. Returns True if changed."""
        clean = {}
        for role, feedid in (mapping or {}).items():
            try:
                feedid = int(feedid)
            except (TypeError, ValueError):
                continue
            if role in ROLES and feedid > 0:
                clean[role] = feedid
        if clean == self.mapping:
            return False
        self.mapping = clean
        self.stale = set()
        return True

    def read(self, t):
        """{role: value} for configured roles, None when stale or unreadable."""
        values, details = {}, {}
        for role, feedid in self.mapping.items():
            value, age, name = None, None, None
            try:
                ts, raw, fname, tag = self.redis.hmget("%sfeed:%d" % (self.prefix, feedid), "time", "value", "name", "tag")
                if fname is not None:
                    name = "%s:%s" % ((tag or b"").decode(), fname.decode())
                if ts is not None and raw is not None:
                    age = max(0, int(t - float(ts)))
                    value = float(raw)
            except Exception as e:
                self.events.append(("error", "Reading %s feed %d: %s" % (role, feedid, e)))
            stale = value is None or age > STALE_AFTER.get(role, STALE_DEFAULT)
            values[role] = None if stale else value
            details[role] = {"id": feedid, "name": name, "value": value, "age": age, "stale": stale}

            if stale and role not in self.stale:
                self.stale.add(role)
                why = "no feed %d" % feedid if name is None else "no value" if age is None else "%d s old" % age
                self.events.append(("input", "%s sensor stale (%s)" % (role, why)))
            elif not stale and role in self.stale:
                self.stale.discard(role)
                self.events.append(("input", "%s sensor back" % role))
        self.details = details
        return values
