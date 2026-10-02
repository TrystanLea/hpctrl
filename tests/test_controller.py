"""Controller behaviour, matching archive/hpctrl_v1.py.

Run: python3 -m unittest discover tests
"""
import os
import sys
import datetime
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "service"))
from controller import Controller, active_period  # noqa: E402

HEATING = {"heating": [{"start": "0000", "set_point": 20.0, "flowT": 34.0, "mode": "min"}], "dhw": []}


class Sim:
    """Steps the controller every 10 s from 08:00 on a fixed day."""

    def __init__(self, inputs, schedule=HEATING, start=(8, 0)):
        self.c = Controller()
        self.inputs = dict(inputs)
        self.schedule = schedule
        self.now = datetime.datetime(2026, 1, 5, *start)
        self.out = None

    def step(self, **changes):
        self.inputs.update(changes)
        self.out = self.c.step(self.now, self.inputs, self.schedule)
        self.now += datetime.timedelta(seconds=10)
        return self.out

    def run(self, seconds, **changes):
        for _ in range(int(seconds / 10)):
            self.step(**changes)
        return self.out

    def events(self):
        texts = [text for _, text in self.c.events]
        self.c.events.clear()
        return texts


def off(**kw):
    """Inputs with the heat pump off and the room warm."""
    inputs = {"room": 20.5, "flow": 20.0, "return": 20.0, "flowrate": 0.0}
    inputs.update(kw)
    return inputs


class TestInputs(unittest.TestCase):

    def test_waits_until_required_inputs_configured(self):
        sim = Sim({"room": 19.0, "flow": 20.0})
        self.assertIsNone(sim.step())
        self.assertIn("Waiting for return, flowrate, outputs held", sim.events())

    def test_stale_required_input_holds_outputs(self):
        sim = Sim(off(room=19.0))
        sim.run(120)
        before = sim.out
        sim.step(**{"return": None})
        self.assertEqual(sim.out, before)
        self.assertEqual(sim.c.describe(0)[0], "Waiting")
        sim.run(30, **{"return": 25.0})
        self.assertIn("Inputs available, control resumed", sim.events())

    def test_stale_room_assumes_cold(self):
        sim = Sim(off(room=None))
        out = sim.step()
        self.assertEqual(out["power"], 1)

    def test_first_run_with_flow_resumes_heating(self):
        sim = Sim(off(room=20.0, flowrate=0.8, **{"return": 26.0}))
        out = sim.step()
        self.assertEqual((out["power"], out["valve"], out["mode"]), (1, 0, 1))
        self.assertEqual(sim.c.state, 1)
        self.assertEqual(out["flowT"], 30)  # straight into flow control

    def test_first_run_without_flow_is_off(self):
        out = Sim(off()).step()
        self.assertEqual((out["power"], out["valve"], out["mode"]), (0, 0, 0))


class TestHeating(unittest.TestCase):

    def test_heating_on_holds_idle_flow_for_60s(self):
        sim = Sim(off(room=19.8, **{"return": 26.0}))
        out = sim.step()
        self.assertEqual(out, {"power": 1, "valve": 0, "flowT": 20.0, "mode": 1})
        self.assertEqual(sim.run(50)["flowT"], 20.0)
        self.assertEqual(sim.step()["flowT"], 30)

    def test_min_mode_flow_target(self):
        # dT at return 26 = 2.667 -> 28.67, rounded up to an even number
        sim = Sim(off(room=19.0, **{"return": 26.0}))
        self.assertEqual(sim.run(80)["flowT"], 30)

    def test_min_mode_capped_at_period_flowT(self):
        schedule = {"heating": [{"start": "0000", "set_point": 20.0, "flowT": 28.0, "mode": "min"}]}
        sim = Sim(off(room=19.0, **{"return": 26.0}), schedule)
        self.assertEqual(sim.run(80)["flowT"], 28.0)

    def test_min_mode_target_cannot_fall_after_5_minutes(self):
        sim = Sim(off(room=19.0, **{"return": 26.0}))
        sim.run(310)
        self.assertEqual(sim.step(**{"return": 20.0})["flowT"], 30)  # defrost dip ignored
        self.assertEqual(sim.step(**{"return": 29.0})["flowT"], 32)  # rises

    def test_min_mode_target_follows_return_in_first_5_minutes(self):
        sim = Sim(off(room=19.0, **{"return": 26.0}))
        sim.run(80)
        self.assertEqual(sim.step(**{"return": 22.0})["flowT"], 26)

    def test_max_mode_uses_period_flowT(self):
        schedule = {"heating": [{"start": "0000", "set_point": 20.0, "flowT": 34.0, "mode": "max"}]}
        sim = Sim(off(room=19.0), schedule)
        self.assertEqual(sim.run(80)["flowT"], 34.0)

    def test_heating_off_sequence(self):
        sim = Sim(off(room=19.0, **{"return": 26.0}))
        sim.run(400)
        out = sim.step(room=20.1)
        self.assertEqual((out["power"], out["flowT"]), (1, 20.0))       # idle flow, pump still on
        self.assertEqual(sim.run(50)["power"], 1)
        out = sim.step()
        self.assertEqual((out["power"], out["valve"], out["mode"]), (0, 0, 0))
        # Holds 25 s even if the room cools straight away
        self.assertEqual(sim.step(room=19.0)["power"], 0)
        self.assertEqual(sim.step()["power"], 0)
        sim.run(20)
        self.assertEqual(sim.out["power"], 1)

    def test_hysteresis_band_keeps_state(self):
        sim = Sim(off(room=19.95))
        self.assertEqual(sim.step()["power"], 0)
        sim.step(room=19.85)
        self.assertEqual(sim.out["power"], 1)
        self.assertEqual(sim.run(200, room=20.05)["power"], 1)

    def test_schedule_period_change(self):
        schedule = {"heating": [
            {"start": "0000", "set_point": 18.0, "flowT": 34.0, "mode": "min"},
            {"start": "0805", "set_point": 20.0, "flowT": 34.0, "mode": "min"}]}
        sim = Sim(off(room=19.0), schedule)
        self.assertEqual(sim.run(290)["power"], 0)
        self.assertEqual(sim.run(20)["power"], 1)


class TestFrost(unittest.TestCase):

    def test_cycles_pump_when_pipe_cold(self):
        sim = Sim(off(extpipe=3.0))
        out = sim.step()
        self.assertEqual((out["power"], out["flowT"]), (1, 14.0))
        self.assertEqual(sim.run(600)["power"], 1)
        self.assertEqual(sim.run(20)["power"], 0)
        self.assertEqual(sim.run(1790)["power"], 0)
        self.assertEqual(sim.run(20)["power"], 1)

    def test_pump_off_when_pipe_warms(self):
        sim = Sim(off(extpipe=3.0))
        sim.step()
        self.assertEqual(sim.step(extpipe=5.0)["power"], 0)

    def test_stale_pipe_assumed_freezing(self):
        self.assertEqual(Sim(off(extpipe=None)).step()["power"], 1)

    def test_off_when_not_configured(self):
        self.assertEqual(Sim(off()).run(3000)["power"], 0)


DHW = {"heating": HEATING["heating"],
       "dhw": [{"start": "0200", "T": 42.0, "flowT": "auto", "mode": "min"}]}


class TestHotWater(unittest.TestCase):

    def dhw_sim(self, schedule=DHW, start=(2, 0), **kw):
        return Sim(off(cyl_top=35.0, cyl_bot=30.0, **kw), schedule, start)

    def test_min_mode_run(self):
        out = self.dhw_sim().step()
        self.assertEqual(out, {"power": 1, "valve": 1, "flowT": 37.0, "mode": 2})

    def test_max_mode_flowT(self):
        schedule = {"heating": DHW["heating"], "dhw": [{"start": "0200", "T": 42.0, "flowT": 50, "mode": "max"}]}
        self.assertEqual(self.dhw_sim(schedule).step()["flowT"], 50)
        schedule["dhw"][0]["flowT"] = "auto"
        self.assertEqual(self.dhw_sim(schedule).step()["flowT"], 49.0)

    def test_completion_sequence_then_heating_pause(self):
        sim = self.dhw_sim(room=19.0)
        sim.run(60)
        out = sim.step(cyl_top=42.5, cyl_bot=39.5)
        self.assertEqual((out["power"], out["valve"], out["flowT"]), (1, 1, 20.0))
        self.assertEqual(sim.run(20)["power"], 0)
        self.assertEqual(sim.out["valve"], 1)
        self.assertEqual(sim.run(10)["valve"], 0)
        sim.run(10)
        self.assertEqual(sim.c.mode, "heating")
        # Room is cold, but space heating waits 60 s after hot water
        self.assertEqual(sim.run(60)["power"], 0)
        self.assertEqual(sim.run(20)["power"], 1)

    def test_bottom_must_be_within_margin(self):
        sim = self.dhw_sim()
        self.assertEqual(sim.step(cyl_top=43.0, cyl_bot=38.0)["valve"], 1)
        self.assertEqual(sim.step(cyl_bot=39.0)["flowT"], 20.0)

    def test_runs_once_per_day(self):
        sim = self.dhw_sim()
        sim.step(cyl_top=45.0, cyl_bot=44.0)  # already hot: completes at once
        sim.run(120)
        self.assertEqual(sim.c.mode, "heating")
        self.assertEqual(sum("Hot water run started" in e for e in sim.events()), 1)

    def test_starts_late_within_window(self):
        self.assertEqual(self.dhw_sim(start=(2, 3)).step()["mode"], 2)
        self.assertEqual(self.dhw_sim(start=(2, 6)).step()["mode"], 0)

    def test_stale_cylinder_stops_run(self):
        sim = self.dhw_sim()
        sim.step()
        self.assertEqual(sim.step(cyl_top=None)["flowT"], 20.0)
        self.assertIn("Hot water run stopped: cylinder temperature missing", sim.events())

    def test_skipped_when_cylinder_not_configured(self):
        sim = Sim(off(), DHW, (2, 0))
        self.assertEqual(sim.step()["mode"], 0)
        self.assertIn("Hot water run skipped: cylinder inputs not configured", sim.events())


class TestSchedule(unittest.TestCase):

    def test_before_first_start_uses_last_period(self):
        periods = [{"start": "0700", "set_point": 20}, {"start": "2200", "set_point": 18}]
        self.assertEqual(active_period(periods, 6 * 60)["set_point"], 18)
        self.assertEqual(active_period(periods, 7 * 60)["set_point"], 20)
        self.assertEqual(active_period(periods, 23 * 60)["set_point"], 18)


if __name__ == "__main__":
    unittest.main()
