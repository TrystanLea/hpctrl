"""Sensor values from emoncms feeds in Redis."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from sensors import Sensors  # noqa: E402


class FakeRedis:
    def __init__(self, hashes):
        self.hashes = hashes

    def hmget(self, key, *fields):
        h = self.hashes.get(key, {})
        return [None if h.get(f) is None else str(h[f]).encode() for f in fields]


T = 1_000_000


def sensors(hashes, mapping, prefix=""):
    s = Sensors(FakeRedis(hashes), prefix)
    s.configure(mapping)
    return s


class TestSensors(unittest.TestCase):

    def test_reads_feed_value_and_name(self):
        s = sensors({"feed:5": {"time": T - 20, "value": 19.5, "name": "heatpump_roomT", "tag": "heatpump"}}, {"room": 5})
        self.assertEqual(s.read(T), {"room": 19.5})
        self.assertEqual(s.details["room"], {"id": 5, "name": "heatpump:heatpump_roomT", "value": 19.5, "age": 20, "stale": False})

    def test_stale_after_role_limit(self):
        hashes = {"feed:5": {"time": T - 1000, "value": 19.5, "name": "r"}, "feed:6": {"time": T - 1000, "value": 30, "name": "f"}}
        s = sensors(hashes, {"room": 5, "flow": 6})
        self.assertEqual(s.read(T), {"room": 19.5, "flow": None})  # room allows 30 min, others 10
        self.assertEqual(s.events, [("input", "flow sensor stale (1000 s old)")])

    def test_missing_feed(self):
        s = sensors({}, {"flow": 9})
        self.assertEqual(s.read(T), {"flow": None})
        self.assertEqual(s.events, [("input", "flow sensor stale (no feed 9)")])

    def test_back_event(self):
        hashes = {"feed:6": {"time": T - 1000, "value": 30, "name": "f"}}
        s = sensors(hashes, {"flow": 6})
        s.read(T)
        hashes["feed:6"]["time"] = T
        s.read(T)
        self.assertEqual(s.events[-1], ("input", "flow sensor back"))

    def test_prefix(self):
        s = sensors({"emoncmsfeed:5": {"time": T, "value": 1, "name": "x"}}, {"room": 5}, prefix="emoncms")
        self.assertEqual(s.read(T), {"room": 1.0})

    def test_configure_filters(self):
        s = Sensors(FakeRedis({}))
        self.assertTrue(s.configure({"room": "5", "bogus": 3, "flow": 0, "return": "x"}))
        self.assertEqual(s.mapping, {"room": 5})
        self.assertFalse(s.configure({"room": 5}))


if __name__ == "__main__":
    unittest.main()
