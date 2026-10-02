# Plan: weather compensated Auto flow mode

Goal: a third flow mode for space heating periods, next to Min and Max, that sets the flow
temperature from outside temperature using a curve fitted to this house, with a slow PI trim
on room temperature. It replaces the PI attempt in `archive/hpctrl_v1.py`, which failed
because the on/off thermostat kept control (the PI only ever saw ±0.1° error), its integral
jumped after off periods (time step spanned them), it could only push upwards (clamped at 0),
its integral was far too slow for a house with hours of lag, and it had no feedforward.

## Where things stand (2 Oct 2026)

- Branch: **master** (fast-forwarded from dev after the restructure; dev is stale at `52651ba`).
  `e600224` (fit_house steady-sample fix) is committed but **not pushed**.
- Running on the Pi: the combined `service/hpctrl.py` (controller, sensors from emoncms feeds,
  CN105 command verification, `hpctrl` node feeds, tunable params, hot water Now/Stop).
- `tools/fit_house.py` exists and was run on the Pi over 365 days, without a hot water flag:

  | | result | verdict |
  |---|---|---|
  | Heat loss | 176 W/K, gains 150 W, R² 0.71 | plausible, gains likely too low (hot water counted as heating) |
  | Emitters | 89.4 x ΔT^1.30, n assumed, MWT error 5.6° | contaminated by hot water and transient samples |
  | Flow capacity | 795 W/K | plausible |
  | Thermal mass | 9.0 kWh/K, τ 51 h, R² 0.20 | plausible order, low confidence |
  | Backtest | curve -3.9° from what ran, RMS 7.2° | inflated by 50° hot water samples |

## Step 1: finish the house fit (tomorrow, first)

1. `git push origin master`, then on the Pi `git pull`.
2. Rerun excluding hot water: `python3 tools/fit_house.py --days 365 --dhw-flow 40`
   (space heating is capped at 34°, so flow > 40° is hot water). Also try `--days 180`
   over the last heating season with `--end`.
3. Paste the output into the session. Proceed when:
   - emitter n is fitted (no "n assumed"), MWT error well under 5.6°
   - heat loss R² ≥ 0.7, gains positive and plausible (a few hundred W)
   - backtest within a few degrees of Min mode (Min deliberately runs low, so the curve
     sitting 1-2° below it is fine; a large gap means the curve is wrong)
4. If the emitter fit is still poor: check `n` against `--days` windows; consider restricting
   to samples with flow rate above a threshold; check whether `heat` includes defrost negatives.
5. Start logging `hpctrl:valve` (and `flowT_target`, `heating`) to feeds in emoncms, so future
   fits have an exact hot water flag (`--dhw <valve feed id>`).

Save the accepted numbers: `python3 tools/fit_house.py ... --json > config/house.json`
(gitignore it, it's per install).

## Step 2: Auto strategy and a simulated house

New module `service/auto.py`, pure logic like `controller.py`:

- **Feedforward** from the fitted model, for set point `sp` and outside `out`:
  `Q = H (sp - out) - gains`; `MWT = sp + (Q / K)^(1/n)`; `flow = MWT + Q / (2 m)`.
  Exposed as 2 tunable curve parameters in the UI rather than raw H/K/n/m? Decide: either
  keep H, gains, K, n, m as params (loaded from `config/house.json` as defaults), or reduce to
  "flow at -3°" and "flow at 15°" plus curvature. Leaning: physical params, with the curve
  preview in the Control settings like the Min curve has.
- **PI trim** on room error, bounded ±3° (param), added to the feedforward:
  - time step capped at 60 s; integral frozen during start/stop phases, hot water, defrost
    (detect: flow drops below return, or CN105 if a defrost flag can be found), and while
    the output is at its bound in the direction of the error (anti-windup)
  - integral both signs; integral time several hours (start from τ = 51 h: Ti ≈ 4-8 h)
  - Kp small (room sensor is 0.1° resolution: ~1° flow per 1° error)
- **On/off**: in Auto, the thermostat becomes a limit, off at sp + 0.5 (param), on at sp - 0.2.
  When Q is below the heat pump's minimum modulated output, fall back to Min mode behaviour
  (return + dT) with minimum on/off times, instead of cycling on the 0.1° band.
- Controller: `flow_target()` dispatches on period mode `min | max | auto`; Auto state
  (integral) lives in the strategy object and is reported in status (`auto: {ff, trim, i}`).
- Params in `PARAMS`/`LIMITS` get a new "Auto mode" group in `PARAM_GROUPS` in `hpctrl.js`.

Tests, `tests/test_auto.py`, against `tests/house_sim.py`:

- House: `C dT/dt = Q_emit - H (T - out) + gains`, Q_emit from the emitter law at the
  commanded flow (assume the heat pump hits its flow target, within min/max output 1.5-5 kW).
- Scenarios: steady cold day settles within ±0.3° of set point in < 12 h; set point step
  18 → 20 recovers without > 0.5° overshoot; sunny afternoon gains spike doesn't wind up the
  integral; restart mid-cycle; hot water run mid-heating; outside step -5 → 10.
- Metrics asserted: cycles per hour, RMS room error, max flow temperature.

## Step 3: shadow mode (a week)

- Service computes the Auto target every step whatever mode is active, without applying it.
- Publish to the `hpctrl` emonhub node: `flowT_auto`, `auto_ff`, `auto_trim`.
- Log them to feeds; graph against `flowT_target`, room and outside temperature.
- Look for: Auto target tracking what Min mode needed on cold days; trim staying well inside
  its bound; no integral runaway when the thermostat is off.

## Step 4: switch over

- Schedule row mode toggle becomes Min / Max / Auto (`hpctrl_view.php`, `set_mode`).
- Enable Auto on the overnight period first, then widen.
- Compare to Min mode over similar weather: room RMS error, compressor starts per day
  (from `heating` feed transitions), COP (elec/heat feeds).

## Loose ends from today

- 22:32 event "Heating off: room 18.7° reached 12.1°" right after a restart: check whether the
  service ran a step on the 5° default schedule before the retained schedule arrived
  (`journalctl -u hpctrl` around then). `wait_for_schedule` only waits when there's no
  `config/schedule.json`.
- Activity events with the same timestamp show in reverse logical order (newest first). Could
  add a sequence number.
- Ideas parked: shade heat pump running periods on the day profile (from `heating` feed);
  persist controller state across restarts; offline/heat pump not responding alerts.
