"""House model fitting against synthetic data with known answers."""
import os
import sys
import math
import array
import struct
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import fit_house  # noqa: E402

H, GAINS, K, N, M = 150.0, 300.0, 9.0, 1.3, 400.0   # W/K, W, emitters, W/K
PER_DAY = 86400 // fit_house.BUCKET


def heating_data(days=30, dhw=False):
    """Room held at 20, outside swinging daily and drifting from -2 to 12; heat matches the loss."""
    data = {k: [] for k in ("room", "outside", "heat", "flow", "return", "dhw")}
    for i in range(days * PER_DAY):
        h = i / (PER_DAY / 24)
        out = -2 + 14 * i / (days * PER_DAY) + 3 * math.sin(2 * math.pi * h / 24)
        q = max(0.0, H * (20 - out) - GAINS)
        mwt = 20 + (q / K) ** (1 / N) if q else 20
        dt = q / M
        is_dhw = dhw and h % 24 < 1          # an hour of hot water each night at 3 kW
        data["room"].append(20.0)
        data["outside"].append(out)
        data["heat"].append(3000.0 if is_dhw else q)
        data["flow"].append(50.0 if is_dhw else mwt + dt / 2)
        data["return"].append(45.0 if is_dhw else mwt - dt / 2)
        data["dhw"].append(1.0 if is_dhw else 0.0)
    return data


class TestFits(unittest.TestCase):

    def test_heat_loss_and_emitters(self):
        house = fit_house.analyse(heating_data(), 0)
        self.assertAlmostEqual(house["heat_loss"]["H"], H, delta=1)
        self.assertAlmostEqual(house["heat_loss"]["gains"], GAINS, delta=20)
        em = house["emitters"]
        self.assertTrue(em["n_fitted"])
        self.assertAlmostEqual(em["n"], N, delta=0.01)
        self.assertAlmostEqual(em["K"], K, delta=0.2)
        self.assertAlmostEqual(em["m"], M, delta=1)

    def test_hot_water_excluded(self):
        house = fit_house.analyse(heating_data(dhw=True), 0)
        self.assertAlmostEqual(house["heat_loss"]["H"], H, delta=8)
        self.assertAlmostEqual(house["emitters"]["n"], N, delta=0.01)

    def test_curve_reproduces_the_house(self):
        house = fit_house.analyse(heating_data(), 0)
        f = fit_house.flow_for(20, 0, house)
        q = H * 20 - GAINS
        self.assertAlmostEqual(f["heat"], q, delta=60)
        self.assertAlmostEqual(f["mwt"], 20 + (q / K) ** (1 / N), delta=0.5)
        self.assertIsNone(fit_house.flow_for(20, 19, house))  # gains cover it
        test = fit_house.backtest(heating_data(), house)
        self.assertLess(test["rmse"], 0.3)

    def test_thermal_mass_from_cooling(self):
        tau = 40.0
        runs = []
        for night in range(10):
            room, out, run = 20.0, 2.0 + night, []
            for _ in range(8):
                run.append((room, out))
                room = out + (room - out) * math.exp(-1 / tau)
            runs.append(run)
        tm = fit_house.fit_thermal_mass(runs, H)
        self.assertAlmostEqual(tm["tau"], tau, delta=1)
        self.assertAlmostEqual(tm["C"], H * tau / 1000, delta=0.2)

    def test_too_little_data(self):
        self.assertIsNone(fit_house.fit_heat_loss([(500, 20, 5)] * 3))
        self.assertIsNone(fit_house.fit_emitters([(1000, 35, 30, 20)] * 5))



class TestReadFeed(unittest.TestCase):

    def test_buckets_gaps_and_ends(self):
        with tempfile.TemporaryDirectory() as d:
            start_time, interval = 1_000_200, 10        # data starts 200 s into the window
            values = array.array("f", [float(i // 60) for i in range(240)])  # 40 min, value = bucket index
            for i in range(60, 120):
                values[i] = float("nan")                # second bucket missing
            with open(os.path.join(d, "7.meta"), "wb") as f:
                f.write(struct.pack("<IIII", 0, 0, interval, start_time))
            with open(os.path.join(d, "7.dat"), "wb") as f:
                f.write(values.tobytes())
            out = fit_house.read_feed(d, 7, 1_000_200 - 600, 1_000_200 + 3600, bucket=600)
            self.assertEqual(out, [None, 0.0, None, 2.0, 3.0, None, None])
            self.assertEqual(fit_house.last_time(d, 7), start_time + 239 * interval)


if __name__ == "__main__":
    unittest.main()
