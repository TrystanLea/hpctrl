"""Fit a simple model of the house from emoncms feed history.

Reads PHPFina feed files directly (no API key needed) and estimates:

  heat loss    H  W/K   space heating = H x (room - outside) - gains, from daily averages
  emitters     K, n     heat output = K x (mean water temperature - room)^n, while heating
  flow         m  W/K   heat output / (flow - return), the system's flow capacity
  thermal mass C  kWh/K from how fast the room cools with the heat pump off; tau = C / H

and from them a weather compensation curve: the flow temperature needed to hold a
set point at each outside temperature.

Usage (on the emonPi, as pi):
  python3 tools/fit_house.py                       # last 30 days, sensors from config/sensors.json
  python3 tools/fit_house.py --days 60 --setpoint 20
  python3 tools/fit_house.py --heat 33 --dhw 56    # feed ids not in the sensor mapping
  python3 tools/fit_house.py --json                # machine readable results

Feeds default to the hpctrl sensor mapping (room, flow, return, outside), with the
heat output and hot water flag found by name (heatpump_heat, heatpump_dhw).
"""
import os
import re
import sys
import json
import math
import array
import struct
import argparse
import datetime

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EMONCMS_DIR = "/var/www/emoncms"
BUCKET = 600  # s, data is averaged to 10 minutes


# ----------------------------------------------------------------------------
# Reading PHPFina feeds
# ----------------------------------------------------------------------------

def emoncms_setting(section, key, default):
    """A value from emoncms settings.ini, else default-settings.ini."""
    for name in ("settings.ini", "default-settings.ini"):
        try:
            with open(os.path.join(EMONCMS_DIR, name)) as f:
                text = f.read()
        except OSError:
            continue
        block = re.search(r"^\[%s\](.*?)(?=^\[|\Z)" % re.escape(section), text, re.M | re.S)
        if block:
            m = re.search(r"^\s*%s\s*=\s*['\"]?([^'\"\n]*)['\"]?\s*$" % re.escape(key), block.group(1), re.M)
            if m:
                return m.group(1).strip()
    return default


def read_feed(datadir, feedid, start, end, bucket=BUCKET):
    """Bucket averages from start to end (unix s): a list with None where there is no data."""
    with open(os.path.join(datadir, "%d.meta" % feedid), "rb") as f:
        meta = f.read(16)
    interval, start_time = struct.unpack("<II", meta[8:16])
    n = int((end - start) // bucket)
    sums, counts = [0.0] * n, [0] * n

    first = max(0, int((start - start_time) // interval))
    last = int((end - start_time) // interval)
    if last > first:
        values = array.array("f")
        with open(os.path.join(datadir, "%d.dat" % feedid), "rb") as f:
            f.seek(first * 4)
            raw = f.read((last - first) * 4)
            values.frombytes(raw[:len(raw) // 4 * 4])
        if sys.byteorder != "little":
            values.byteswap()
        for i, v in enumerate(values):
            if v != v:  # NaN: no data
                continue
            b = int((start_time + (first + i) * interval - start) // bucket)
            if 0 <= b < n:
                sums[b] += v
                counts[b] += 1
    return [sums[i] / counts[i] if counts[i] else None for i in range(n)]


def last_time(datadir, feedid):
    """Time of the last value written to a feed."""
    with open(os.path.join(datadir, "%d.meta" % feedid), "rb") as f:
        interval, start_time = struct.unpack("<II", f.read(16)[8:16])
    size = os.path.getsize(os.path.join(datadir, "%d.dat" % feedid))
    return start_time + (size // 4 - 1) * interval


def find_feeds_by_name(names):
    """{name: feed id} from the feed:<id> hashes emoncms keeps in Redis."""
    try:
        import redis
        r = redis.Redis()
        prefix = emoncms_setting("redis", "prefix", "")
        found = {}
        for key in r.scan_iter(prefix + "feed:*"):
            key = key.decode()
            if not re.fullmatch(re.escape(prefix) + r"feed:\d+", key):
                continue
            name = r.hget(key, "name")
            if name and name.decode() in names:
                found[name.decode()] = int(key.split(":")[-1])
        return found
    except ImportError:
        print("Note: python3 redis module not available, so feeds can't be found by name", file=sys.stderr)
        return {}
    except Exception:
        return {}


# ----------------------------------------------------------------------------
# Fitting: plain lists in, numbers out
# ----------------------------------------------------------------------------

def linfit(xs, ys):
    """Least squares y = a x + b. Returns (a, b, r2)."""
    n = len(xs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    a = sxy / sxx
    b = my - a * mx
    ss_res = sum((y - (a * x + b)) ** 2 for x, y in zip(xs, ys))
    ss_tot = sum((y - my) ** 2 for y in ys)
    return a, b, (1 - ss_res / ss_tot) if ss_tot else 0.0


def median(xs):
    s = sorted(xs)
    n = len(s)
    return (s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2) if n else None


def fit_heat_loss(days, min_heat=100):
    """days: [(mean space heat W, mean room, mean outside)]. Heat = H (room - outside) - G.

    Days with less than min_heat average are left out: with the heating off the room
    floats and the balance doesn't hold."""
    used = [d for d in days if d[0] >= min_heat]
    if len(used) < 5:
        return None
    H, b, r2 = linfit([d[1] - d[2] for d in used], [d[0] for d in used])
    return {"H": H, "gains": -b, "r2": r2, "days": len(used), "days_total": len(days),
            "dT_range": [min(d[1] - d[2] for d in used), max(d[1] - d[2] for d in used)]}


def fit_emitters(samples, n_default=1.3):
    """samples: [(heat W, flow, return, room)] while space heating.

    Fits heat = K (MWT - room)^n by log-log regression; n outside 1.0 to 1.6 (noise,
    or a narrow range of conditions) falls back to n_default with K fitted alone."""
    pts = [(q, (f + r) / 2 - room) for q, f, r, room in samples if q > 300 and (f + r) / 2 - room > 2]
    if len(pts) < 30:
        return None
    n, logK, r2 = linfit([math.log(dt) for _, dt in pts], [math.log(q) for q, _ in pts])
    fitted = 1.0 <= n <= 1.6
    if not fitted:
        n = n_default
        logK = math.log(median([q / dt ** n for q, dt in pts]))
    K = math.exp(logK)
    # Error in mean water temperature terms: what the model would need vs what was seen
    errs = [room_dt - (q / K) ** (1 / n) for q, room_dt in pts]
    m = median([q / (f - r) for q, f, r, _ in samples if q > 300 and f - r > 0.5])
    return {"K": K, "n": n, "n_fitted": fitted, "r2": r2, "samples": len(pts),
            "mwt_rmse": math.sqrt(sum(e * e for e in errs) / len(errs)), "m": m}


def fit_thermal_mass(runs, H):
    """runs: lists of hourly (room, outside) with the heat pump off, in time order.

    Cooling: C dRoom/dt = -H (room - outside) + gains, so the rate (K/h) against
    (room - outside) has slope -H/C."""
    xs, ys = [], []
    for run in runs:
        for (r0, o0), (r1, o1) in zip(run, run[1:]):
            xs.append((r0 + r1) / 2 - (o0 + o1) / 2)
            ys.append(r1 - r0)
    if len(xs) < 12 or not H:
        return None
    slope, b, r2 = linfit(xs, ys)
    if slope >= 0:
        return {"C": None, "tau": None, "r2": r2, "hours": len(xs)}
    tau = -1 / slope                  # hours
    C = H * tau / 1000                # kWh/K
    return {"C": C, "tau": tau, "r2": r2, "hours": len(xs)}


def flow_for(setpoint, outside, house):
    """Flow temperature to hold setpoint at outside, or None if no heat is needed."""
    hl, em = house["heat_loss"], house["emitters"]
    q = hl["H"] * (setpoint - outside) - hl["gains"]
    if q <= 0:
        return None
    mwt = setpoint + (q / em["K"]) ** (1 / em["n"])
    dt = q / em["m"] if em.get("m") else 0
    return {"heat": q, "mwt": mwt, "flow": mwt + dt / 2, "return": mwt - dt / 2}


# ----------------------------------------------------------------------------
# From feeds to fits
# ----------------------------------------------------------------------------

def analyse(data, start, bucket=BUCKET, dhw_flow=None):
    """data: {role: [bucket averages]} for room, outside, heat, and optionally flow, return, dhw."""
    n = len(data["room"])
    get = lambda role, i: data[role][i] if role in data else None  # noqa: E731

    def is_dhw(i):
        if "dhw" in data:
            return (get("dhw", i) or 0) > 0.1
        if dhw_flow is not None and get("flow", i) is not None:
            return get("flow", i) > dhw_flow
        return False

    # Daily space heating balance
    per_day = 86400 // bucket
    days = []
    for d in range(n // per_day):
        idx = range(d * per_day, (d + 1) * per_day)
        ok = [i for i in idx if None not in (get("room", i), get("outside", i), get("heat", i))]
        if len(ok) < 0.8 * per_day:
            continue
        heat = sum(0 if is_dhw(i) else max(0, get("heat", i)) for i in ok) / len(ok)
        days.append((heat, sum(get("room", i) for i in ok) / len(ok), sum(get("outside", i) for i in ok) / len(ok)))

    # Space heating samples for the emitters
    samples = []
    if "flow" in data and "return" in data:
        for i in range(n):
            vals = (get("heat", i), get("flow", i), get("return", i), get("room", i))
            if None not in vals and not is_dhw(i):
                samples.append(vals)

    # Off periods of 3 h or more, hourly, for the thermal mass
    per_hour = 3600 // bucket
    runs, run = [], []
    for h in range(n // per_hour):
        idx = range(h * per_hour, (h + 1) * per_hour)
        off = all(get("heat", i) is not None and get("heat", i) < 50 and not is_dhw(i) for i in idx)
        rooms = [get("room", i) for i in idx if get("room", i) is not None]
        outs = [get("outside", i) for i in idx if get("outside", i) is not None]
        if off and rooms and outs:
            run.append((sum(rooms) / len(rooms), sum(outs) / len(outs)))
        else:
            if len(run) >= 3:
                runs.append(run)
            run = []
    if len(run) >= 3:
        runs.append(run)

    heat_loss = fit_heat_loss(days)
    return {
        "heat_loss": heat_loss,
        "emitters": fit_emitters(samples),
        "thermal_mass": fit_thermal_mass(runs, heat_loss["H"] if heat_loss else None),
    }


def backtest(data, house, bucket=BUCKET):
    """Flow temperature the curve gives for each heating sample's room and outside, against what ran."""
    if not (house["heat_loss"] and house["emitters"]) or "flow" not in data:
        return None
    errs = []
    for i in range(len(data["room"])):
        room, out, flow, heat = (data[r][i] for r in ("room", "outside", "flow", "heat"))
        if None in (room, out, flow, heat) or heat < 300:
            continue
        if "dhw" in data and (data["dhw"][i] or 0) > 0.1:
            continue
        pred = flow_for(room, out, house)
        if pred:
            errs.append(pred["flow"] - flow)
    if not errs:
        return None
    return {"samples": len(errs), "mean": sum(errs) / len(errs), "rmse": math.sqrt(sum(e * e for e in errs) / len(errs))}


# ----------------------------------------------------------------------------
# Report
# ----------------------------------------------------------------------------

def warnings(house):
    """Signs that the data doesn't support the fit."""
    out = []
    hl, em, tm = house["heat_loss"], house["emitters"], house["thermal_mass"]
    if hl:
        if hl["r2"] < 0.6:
            out.append("Heat loss fit is weak (R² %.2f): colder days, with a wider range of room - outside, would help" % hl["r2"])
        if hl["dT_range"][1] - hl["dT_range"][0] < 8:
            out.append("Room - outside only spans %.1f°: the heat loss slope is uncertain" % (hl["dT_range"][1] - hl["dT_range"][0]))
        if hl["gains"] < 0:
            out.append("Gains came out negative, which isn't physical: treat the heat loss figures as unreliable")
    if em and em["r2"] < 0.6 and em["n_fitted"]:
        out.append("Emitter fit is weak (R² %.2f)" % em["r2"])
    if tm and tm["C"] and tm["r2"] < 0.3:
        out.append("Thermal mass fit is weak (R² %.2f): sun and occupancy move the room more than cooling does" % tm["r2"])
    return out


def report(house, feeds, start, end, setpoint, test):
    out = []
    p = out.append
    fmt = lambda t: datetime.datetime.fromtimestamp(t).strftime("%Y-%m-%d")  # noqa: E731
    p("House model from %s to %s" % (fmt(start), fmt(end)))
    p("Feeds: " + ", ".join("%s %d" % kv for kv in feeds.items()))
    p("")

    hl = house["heat_loss"]
    if hl:
        p("Heat loss        %.0f W/K, gains %.0f W   (R² %.2f, %d of %d days, room - outside %.1f to %.1f°)" % (
            hl["H"], hl["gains"], hl["r2"], hl["days"], hl["days_total"], hl["dT_range"][0], hl["dT_range"][1]))
        p("                 at -3° outside and %.0f° inside: %.1f kW" % (setpoint, (hl["H"] * (setpoint + 3) - hl["gains"]) / 1000))
    else:
        p("Heat loss        not enough heating days (need 5 with at least 100 W average)")

    em = house["emitters"]
    if em:
        p("Emitters         heat = %.1f x (MWT - room)^%.2f%s   (%d samples, MWT error %.1f°)" % (
            em["K"], em["n"], "" if em["n_fitted"] else " (n assumed)", em["samples"], em["mwt_rmse"]))
        if em["m"]:
            p("Flow capacity    %.0f W/K   (flow - return of %.1f° at 3 kW)" % (em["m"], 3000 / em["m"]))
    else:
        p("Emitters         needs flow and return feeds with heating data")

    tm = house["thermal_mass"]
    if tm and tm["C"]:
        p("Thermal mass     %.1f kWh/K, time constant %.0f h   (R² %.2f, %d off hours)" % (tm["C"], tm["tau"], tm["r2"], tm["hours"]))
    elif tm:
        p("Thermal mass     no clear cooling trend in %d off hours" % tm["hours"])
    else:
        p("Thermal mass     not enough off periods of 3 h or more")

    if hl and em:
        p("")
        p("Weather compensation for %.0f° inside" % setpoint)
        p("  outside   heat   flow  return")
        for outside in range(-5, 20, 5):
            f = flow_for(setpoint, outside, house)
            if f:
                p("  %5.0f°  %5.1f kW  %4.1f°  %4.1f°" % (outside, f["heat"] / 1000, f["flow"], f["return"]))
            else:
                p("  %5.0f°   no heat needed" % outside)
        if test:
            p("")
            p("Against past heating: the curve's flow is %+.1f° on average from what ran (RMS %.1f°, %d samples)" % (
                test["mean"], test["rmse"], test["samples"]))

    notes = warnings(house)
    if notes:
        p("")
        for note in notes:
            p("! " + note)
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description="Fit a house model from emoncms feed history")
    parser.add_argument("--days", type=int, default=30)
    parser.add_argument("--end", help="YYYY-MM-DD, default: the last data")
    parser.add_argument("--setpoint", type=float, default=20.0)
    for role in ("room", "outside", "heat", "flow", "return", "dhw"):
        parser.add_argument("--" + role, type=int, help="%s feed id" % role)
    parser.add_argument("--dhw-flow", type=float, default=None,
                        help="without a hot water flag feed, treat flow above this as hot water")
    parser.add_argument("--datadir", default=None)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    datadir = args.datadir or emoncms_setting("feed", "phpfina[datadir]", "/var/opt/emoncms/phpfina/")

    feeds = {}
    try:
        with open(os.path.join(REPO, "config", "sensors.json")) as f:
            sensors = json.load(f)
        for role, key in (("room", "room"), ("outside", "ambient"), ("flow", "flow"), ("return", "return")):
            if key in sensors:
                feeds[role] = sensors[key]
    except (OSError, ValueError):
        pass
    by_name = find_feeds_by_name({"heatpump_heat", "heatpump_dhw", "heatpump_roomT", "heatpump_outsideT",
                                  "heatpump_flowT", "heatpump_returnT"})
    for role, name in (("heat", "heatpump_heat"), ("dhw", "heatpump_dhw"), ("room", "heatpump_roomT"),
                       ("outside", "heatpump_outsideT"), ("flow", "heatpump_flowT"), ("return", "heatpump_returnT")):
        if role not in feeds and name in by_name:
            feeds[role] = by_name[name]
    for role in ("room", "outside", "heat", "flow", "return", "dhw"):
        if getattr(args, role):
            feeds[role] = getattr(args, role)
    # Feeds without data files (e.g. virtual) are dropped
    feeds = {r: i for r, i in feeds.items() if os.path.exists(os.path.join(datadir, "%d.dat" % i))}

    missing = [r for r in ("room", "outside", "heat") if r not in feeds]
    if missing:
        sys.exit("Need feeds for: %s (pass --%s ID)" % (", ".join(missing), missing[0]))

    if args.end:
        end = int(datetime.datetime.strptime(args.end, "%Y-%m-%d").timestamp())
    else:
        end = min(last_time(datadir, feeds[r]) for r in ("room", "outside", "heat"))
    end = end // 86400 * 86400
    start = end - args.days * 86400

    data = {role: read_feed(datadir, feedid, start, end) for role, feedid in feeds.items()}
    data = {role: v for role, v in data.items() if any(x is not None for x in v)}
    house = analyse(data, start, dhw_flow=args.dhw_flow)
    test = backtest(data, house)

    if args.json:
        print(json.dumps({"start": start, "end": end, "feeds": feeds, "setpoint": args.setpoint,
                          "backtest": test, "warnings": warnings(house), **house}, indent=2))
    else:
        if "dhw" not in feeds and args.dhw_flow is None:
            print("Note: no hot water flag feed (--dhw ID or --dhw-flow), so hot water heat counts as space heating", file=sys.stderr)
        print(report(house, {r: feeds[r] for r in data}, start, end, args.setpoint, test))


if __name__ == "__main__":
    main()
