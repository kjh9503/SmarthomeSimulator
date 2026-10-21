# smarthome-sim

A simulated person's year of smart-home device logs and phone logs (SmartThings-style), produced by a probabilistic
agent that follows an **agent profile**: hidden behaviour patterns mixed with ordinary daily routines. The logs are meant
for training a model that learns a user's patterns and suggests actions.

Everything runs in Python 3.10+ with the standard library only. The browser page in `browser/` is the same simulator
with a screen (for looking at a house by hand); the Python package is a line-by-line port of its script.

## Layout

| Path | What it is |
|---|---|
| `smarthome_sim/` | the simulator and the agent runner (Python) |
| `smarthome_sim/weather.py` | outdoor Seoul conditions: monthly normals, per-date weather, PM2.5, rain washout, wind, daylight, noise |
| `smarthome_sim/house.py` | devices, house layouts, each room's true indoor values (temperature, humidity, PM2.5, CO2, light, noise) |
| `smarthome_sim/simulator.py` | commands, sensor reports, the log saving policy, front door, presence, appliance progress and limits |
| `smarthome_sim/phone.py` | the phone: trips, activity, Bluetooth, Wi-Fi, apps, media, calendar, sleep, exercise, health, SMARTTHINGS copies |
| `smarthome_sim/agent.py`, `run.py` | the agent runner and its command line |
| `smarthome_sim/off_rules.json` | the checks the person makes before sleeping, before leaving, after waking |
| `smarthome_sim/data/` | `device_spec.jsonl` (devices, capabilities, commands), `room_profiles.json` (9 layouts) |
| `profiles/063.json` | agent profile of persona 063: pattern p63_a + 26 routines |
| `pipeline/` | the LLM pipeline that turns written patterns into structured patterns (prompts, schemas, vocabulary, validators); see `pipeline/README.md` |
| `browser/smarthome-sim.html` | the browser simulator (open the file in a browser) |
| `tools/js/run_agent.js` | the earlier JavaScript runner (needs Node.js); same rules, kept for comparison |
| `tools/js_*_fixture.js` | make the JavaScript reference numbers used by the tests |
| `tests/` | checks that the Python port gives the browser simulator's numbers |

## Run

```
python3 -m smarthome_sim.run --profile profiles/063.json --out out/063
```

| Option | Default | Meaning |
|---|---|---|
| `--profile` | (required) | the agent profile |
| `--out` | `out/<personaId>` | output folder |
| `--days` | profile `simulation.days` | how many days |
| `--seed` | profile `simulation.seed` | random seed: the same profile and seed give the same output, line for line |
| `--trace` | off | also write `trace.jsonl` |
| `--off-rules` | `smarthome_sim/off_rules.json` | checks before sleep / leaving / after waking |
| `--vocabulary` | `pipeline/vocabulary.json` | for apps the profile uses that are not installed by default |
| `--full-format` | off | write SMARTTHINGS copies with every event-formats field (default: the stored form, below) |
| `--home-log` | off | also write `home_log.jsonl` (the home lines alone, for checking); they are always in the phone log |

`pip install -e .` also gives the command `smarthome-sim-run` with the same options.

From Python:

```python
import json
from smarthome_sim.agent import AgentRunner
summary = AgentRunner(json.load(open("profiles/063.json")), "out/063").run()
```

Check a profile before running it (needs `pip install jsonschema` for the schema part):
`python3 pipeline/check_profile.py profiles/063.json`.

Measured for 063 (365 days, 3room-A), Python 3.13 on one core: 6 min 21 s (the JavaScript runner: 110 s).
Output: `phone_log.jsonl` 359,464 events, of which 302,151 are copies of home lines: 152 MB in the stored form (6 MB with gzip); 319 MB with `--full-format`.

## Outputs

| File | Content |
|---|---|
| `phone_log.jsonl` | the dataset: every phone event, in time order (event-formats v3: type, source, title, text, timestamp, collectedAt, dedupeKey, payload, context {battery, weather, location}). Every saved home log line is in it as a SMARTTHINGS event (`payload.kind: "state"`: deviceId, roomId, change {capability, attribute, value, previousValue}, actor {kind user / sensor / device / event, channel, command, args, reason}); SmartThings alerts are `payload.kind: "notification"` |
| (stored form) | the SMARTTHINGS copies of home lines leave out the fields their other fields determine: `source`, `title`, `text`, `collectedAt`, `dedupeKey`, `payload.name`, `label`, `deviceTypeName`, `roomId`, `capabilities`, `change.unit`, and for sensor reports `payload.status` and the empty actor fields. `python3 tools/expand_log.py out/063/phone_log.jsonl > full.jsonl` puts them back; the result is byte for byte the `--full-format` log (`tests/test_port.py`). Rules in `smarthome_sim/formats.py` |
| `home_log.jsonl` | only with `--home-log`: the home lines alone (time, houseId, houseType, houseVariant, weather, deviceId, roomId, device, capability, attribute, value, previousValue, source, command, args, channel, reason) |
| `summary.json` | for checking the run, not training data: houseId, houseType, variant; cooking times drawn; per behaviour `triggered`, `conditionsTrue`, `followed`, `notFollowed`, `deferred` (minutes waited because the person was busy), `overMaxPerDay`, step results (`done`, `no_change`, `skipped`, `refused`) and refusal reasons; per check: devices checked, turned off, left on |
| `trace.jsonl` | with `--trace`: one line per decision (`followed` with each step's result, `not_followed`) and per device in a check |

## Agent profile

Format: `pipeline/agent_profile.schema.json`. A profile has the house (`houseType`, `variant`, `roomRoles`), the period
(`simulation.startDate`, `days`, `seed`), where the person starts, an optional `cookingMinutes`, and `behaviours`.
A behaviour is a hidden pattern (`kind: "pattern"`, with the full structured pattern in `pattern`) or an ordinary routine
(`kind: "routine"`). Both have `trigger`, `conditions`, `actions`, `probability`, `maxPerDay` and optional `priority`,
using the parts defined in `pipeline/pattern.schema.json` and the names in `pipeline/vocabulary.json`.

## What the runner does, every simulated minute

1. The world moves one minute: physics, appliances, sensors, phone battery, heart rate, trips.
2. New happenings are matched against `event` triggers: home log lines, phone events (also SMARTTHINGS copies and alerts),
   the person's movement (`depart`, `arrive`, `enter_room`, `wake`, `fall_asleep`) and weather changes.
3. Due items run: delayed event checks, reverts (undo later), the morning check.
4. Time triggers: `time_window` (every minute; the first minute the conditions hold decides with `probability`;
   not followed = no more tries that day; after a follow, the next false -> true change can fire again up to `maxPerDay`),
   `daily` (one random minute in the window), `rate` (each minute with chance perHour / 60).
5. Running behaviours continue (after a `wait`, or after a trip has arrived).

Rules:
- **Conditions** are checked when the trigger fires (for an event with `delayMinutes`: after the delay). A step's `when`
  is checked when that step is reached; if it does not hold the step is skipped.
- **Device values** in conditions are what the device / SmartThings app shows (a sensor's last report).
  Exception: `light_sensor` illuminance is the room's actual light level (the person sees it).
- **One thing at a time**: a time-triggered behaviour that moves the person or uses something by hand waits while another
  behaviour is in the middle of such steps (a behaviour in a wait with 15 minutes or more left does not count).
  A `daily` one waits at most 180 minutes, a `time_window` one tries again next minute, a `rate` one is dropped.
  Event-triggered behaviours do not wait.
- **By hand** (`channel: physical`, windows and doors): the person first walks to that room. From the phone
  (`mobile_app`) works anywhere, not while asleep or driving.
- **Refusals** come from the simulator (asleep, away, driving...). The step counts as refused and the behaviour goes on;
  a refused `person.travel` ends the behaviour.
- **Revert** (`revert.afterMinutes`): by the person, or with `byDevice: true` by the device itself (logged as the device's
  report, `reason: "timer"`). Pending reverts by the person (except the stove's cooking time) are dropped by the bedtime
  and leaving checks, which take them over.
- **Checks** (`off_rules.json`): before a behaviour with `phone.sleep` starts, and before every trip from home, every device
  that is on is turned off with its probability, in random order. What was still on when the person fell asleep is checked
  again 0-60 minutes after waking (morning probability). Missed devices stay on until a later check or behaviour.
- **Cooking**: each time the person turns the stove on, a cooking time is drawn from the profile's `cookingMinutes`
  (a step may have its own); then the person walks to the kitchen and turns it off. If the person is away or asleep by
  then, the stove's own limit does it.
- **Appliance limits**: stove off after 4 h on (Rinnai RBR-P2500 manual), oven after 12 h (GE range manual), `reason: "auto_off"`.
- **preference_shift**: `shift.before` actions before `shift.at`, the new actions after, mixed over `transitionDays`.
- Choices `{"choice": [...], "weights": [...]}` and ranges `{"min", "max"}` are drawn each time.
- A pattern's `prerequisites` are descriptions only; routines in the profile must make them happen.

## How the Python port is checked against the browser simulator

`python3 -m unittest discover -s tests` (about 10 s, no Node.js needed):

| Test | What is compared | Result when written |
|---|---|---|
| `test_outdoor_matches_js` | outdoor values at 600 moments of 2026 (weather state, temperature, humidity, PM2.5, daylight, wind, precipitation, noise) | equal to 1e-12 |
| `test_physics_matches_js` | every room's true values every 6 hours over a scripted 3 days with windows, stove, purifier, TV, lights, heating, cooling, humidifier, washer, dryer, dishwasher, robot vacuum, oven, balcony door, speaker and a person moving | equal to 1e-15 |
| `test_same_seed_same_output` | two 2-day runs of 063 with the same seed | identical files |

Random numbers (sensor noise, heart rate, steps, the person's choices) come from Python's generator, so a Python run and a
JavaScript run with the same seed are not the same line by line; their 1-year statistics were compared instead (see
`tools/compare_runs.md`). `tests/compare_outputs.py <js_out> <py_out>` checks that every kind of line has the same fields.

When `browser/smarthome-sim.html` changes, the same change has to be made in `smarthome_sim/`; then remake the fixtures
(`TZ=Asia/Seoul node tools/js_outdoor_fixture.js browser/smarthome-sim.html > tests/fixtures/outdoor_js.json`, and
`cd tools && TZ=Asia/Seoul node js_physics_fixture.js ../browser/smarthome-sim.html ./physics_script.json > ../tests/fixtures/physics_js.json`)
and run the tests.

## Known limits

- One person per house.
- The phone log is large (about 320 MB a year), mostly SMARTTHINGS copies that carry the device's full status.
- Smoke, water leak and dryer error states have no cause in the simulation; they only happen if something sets them.
- Showers add no moisture (moisture comes from the person, washer, dryer and humidifier).
