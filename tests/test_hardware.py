"""Command verification: resend when the Ecodan disagrees with what was sent."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from hardware import Verifier, Hardware  # noqa: E402


class FakeEcodan:
    """Sends only on change, like cn105.CN105, and drops the first flow temperature command."""

    def __init__(self):
        self.last_power, self.last_temp = -1, -1
        self.power, self.setpoint, self.sends, self.drop = 0, 20.0, [], 1

    def set_power(self, power):
        if power != self.last_power:
            self.last_power = power
            self.power = power

    def set_temp(self, temp):
        if temp != self.last_temp:
            self.last_temp = temp
            self.sends.append(temp)
            if self.drop:
                self.drop -= 1
            else:
                self.setpoint = temp

    def get_flow_return_dhw(self): return {}
    def get_compressor_frequency(self): return {}
    def get_zone_and_outside(self): return {}
    def get_modes(self): return {"power": self.power, "heating_setpoint": self.setpoint}


class TestVerifier(unittest.TestCase):

    def test_match_is_ok(self):
        v = Verifier()
        self.assertEqual(v.check({"power": 1, "flowT": 30}, {"power": 1, "heating_setpoint": 30.0}), [])
        self.assertTrue(v.ok())

    def test_flowT_compared_at_sent_resolution(self):
        v = Verifier()
        self.assertEqual(v.check({"power": 1, "flowT": 28.67}, {"power": 1, "heating_setpoint": 28.6}), [])
        self.assertEqual(v.fields["flowT"]["state"], "ok")

    def test_one_poll_lag_tolerated(self):
        v = Verifier()
        self.assertEqual(v.check({"power": 1}, {"power": 0}), [])
        self.assertEqual(v.check({"power": 1}, {"power": 1}), [])
        self.assertEqual(v.events, [])

    def test_resend_then_confirm(self):
        v = Verifier()
        sent = {"power": 1, "flowT": 34.0}
        v.check(sent, {"power": 1, "heating_setpoint": 20.0})
        self.assertEqual(v.check(sent, {"power": 1, "heating_setpoint": 20.0}), ["flowT"])
        self.assertFalse(v.ok())
        v.check(sent, {"power": 1, "heating_setpoint": 34.0})
        self.assertTrue(v.ok())
        self.assertEqual(len(v.events), 2)  # resending, confirmed

    def test_gives_up_after_max_resends(self):
        v = Verifier()
        sent = {"flowT": 14.0}
        resends = sum(len(v.check(sent, {"heating_setpoint": 25.0})) for _ in range(20))
        self.assertEqual(resends, Verifier.MAX_RESENDS)
        self.assertEqual(v.fields["flowT"]["state"], "failed")

    def test_new_value_resets(self):
        v = Verifier()
        for _ in range(20):
            v.check({"flowT": 14.0}, {"heating_setpoint": 25.0})
        v.check({"flowT": 30.0}, {"heating_setpoint": 20.0})
        self.assertEqual(v.check({"flowT": 30.0}, {"heating_setpoint": 20.0}), ["flowT"])

    def test_no_readback_is_unknown(self):
        v = Verifier()
        v.check({"power": 1}, {})
        self.assertEqual(v.fields["power"]["state"], "unknown")
        self.assertTrue(v.ok())



class TestHardwareResend(unittest.TestCase):

    def test_lost_command_is_resent(self):
        hw = Hardware.__new__(Hardware)
        hw.dry_run, hw.applied, hw.verifier = False, None, Verifier()
        hw.ecodan = hw.valve = FakeEcodan()
        hw.valve.on = hw.valve.off = lambda: None
        out = {"power": 1, "valve": 0, "flowT": 34.0, "mode": 1}
        for _ in range(4):
            hw.apply(out)
            data = hw.poll()
        self.assertEqual(hw.ecodan.sends, [34.0, 34.0])
        self.assertEqual(data["heating_setpoint"], 34.0)
        self.assertEqual(hw.verifier.fields["flowT"]["state"], "ok")


if __name__ == "__main__":
    unittest.main()
