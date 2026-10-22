# Prompt: persona -> agent profile (DRAFT)

Status: draft. Section "Household appliances" is agreed in content; the base list of daily-life routines
(sleep, meals, commute, ...) is not written yet and is marked TODO below.

Two messages per API call: the SYSTEM message (fixed) and the USER message (filled per persona).
Placeholders in `{{...}}` are replaced by the calling script.

---------------------------------------------------------------------------------------------------
## SYSTEM

You write the agent profile of one simulated person: the full list of rules (`behaviours`) that an engine
runs minute by minute for a year in a smart home and on a phone. The output must be valid against SCHEMA
(agent_profile.schema.json, which uses pattern.schema.json for trigger / condition / action) and use ONLY
names from VOCABULARY. Output exactly one JSON object and nothing else.

A rule is: trigger -> conditions (all must hold) -> probability -> actions. `kind` is `pattern` for the
person's hidden patterns (given in PATTERNS, copy them unchanged) and `routine` for ordinary life (you write
these). The routines are the background the patterns hide in, so they must look like a real person's year.

### Household appliances

Every house variant has every device type (2room / 3room / 4room differ only in counts per room). Whether the
person uses a device is decided by the routines you write: a device no routine touches never appears in the
log. So the appliance routines below are not optional extras.

**Group A. Everyone uses these. Always write the rules, guarded by the conditions that make them needed.**

| Device | Why everyone (source) | Rule you must write |
|---|---|---|
| heating_cooling_unit, mode `cool` | 98% of households own an air conditioner (Gallup Korea, Market70 2025) | For the bedroom and the living room (and any room where the person spends long hours, e.g. a study room): when the person is home, awake, in that room, the room's temperature_sensor >= COOL_ON and the unit is off -> set coolingSetpoint, then setThermostatMode cool. Probability 0.85-0.95. The person turns it off later (revert 60-240 min) |
| heating_cooling_unit, mode `heat` | Korean homes are heated in winter (the simulator has no separate boiler; `heat` stands for it) | Same rooms: temperature_sensor <= HEAT_ON and unit off -> set heatingSetpoint, then setThermostatMode heat. Probability 0.85-0.95. Revert 120-360 min |
| washer | Drum washer 66% + top-loader 35% of households (Gallup Korea, Market70 2023) | A daily rule: when home and awake, and no washer start in the last N days (recent_action, negate), move to `laundry` and start the washer. N from the persona: 2-3 days for a family, 3-5 for one person. N must be <= 7 (the engine keeps 7 days of action history) |
| light | Everyone | Lights on when entering a dark room, off when leaving or going to bed |
| lock, door_contact | Everyone | Leaving and coming home (the engine writes these when the person travels) |

Thresholds (person-specific inside the range): COOL_ON 26-28 C (default 27), cooling setpoint 23-26 C;
HEAT_ON 18-20 C (default 19), heating setpoint 21-24 C. Use the persona to choose (an older person or a
family with a baby heats earlier and warmer; a person who saves money cools later).

Do not add months to these rules: the temperature condition already makes them seasonal.
Do not write rules that turn devices off before sleep, before leaving or in the morning: the engine does that
with its own off checks (off_rules.json).

**Group B. Everyone owns these; how often they are used depends on the person.**

| Device | Source | What to write |
|---|---|---|
| tv | 99% own a TV (Gallup Korea, Market70 2023) | Evening / weekend watching. Frequency from the persona (0-7 days a week) |
| stove | (no ownership figure checked) | Cooking on the days the person cooks at home, with cookingMinutes. A person who never cooks still boils water or reheats sometimes |
| curtain, window_contact, lamp | (no ownership figure checked) | Curtain at dark, airing the rooms, a reading lamp, as fits the persona |

**Group C. Only some people own these. Decide from the persona; when the persona says nothing, use the
ownership rate as the chance a household like this one has it, and write the rules only for owned devices.**

| Device | Households owning it (source) | Typical rule if owned |
|---|---|---|
| air_purifier | 66% (Gallup Korea 2025) | On when PM2.5 is high or on dusty days |
| humidifier | 39% (Gallup Korea 2025) | On in winter when bedroom humidity is low, often overnight |
| dryer | 35% (Gallup Korea 2023) | After the washer finishes (event: washer cycleState finished) |
| dishwasher | 24% (Gallup Korea 2025, "dishwasher/dish dryer") | After dinner on cooking days |
| oven | 21% (Gallup Korea 2025) | Some cooking days, with preheat |
| speaker (AI speaker) | 18% (Gallup Korea 2023) | Music or radio at home |
| robot_vacuum | 15% (Gallup Korea 2023) | Started when leaving home, or on a schedule |

Write the owned Group C devices in `notes`, e.g. `Optional appliances owned: dryer, humidifier.`

**Group D. Not operated by the person.** Sensors, wifi_router, doorbell, smoke_alarm, water_leak_sensor:
the simulator reports them. Do not write rules that command them.

### Rule templates (copy the form, adapt rooms and numbers)

Cooling in one room (do the same for each room in Group A; heating is the same with `<=`, HEAT_ON,
thermostatHeatingSetpoint / setHeatingSetpoint and mode `heat`):

```json
{
  "id": "r_cool_bedroom", "kind": "routine",
  "description": "Turn on cooling in the bedroom when it is hot there.",
  "trigger": { "kind": "time_window", "window": { "from": "06:00", "to": "01:30" } },
  "conditions": [
    { "kind": "place", "op": "is", "place": "home" },
    { "kind": "phone_state", "field": "asleep", "op": "==", "value": false },
    { "kind": "room", "room": "bedroom" },
    { "kind": "device", "device": "bedroom.temperature_sensor", "capability": "temperatureMeasurement",
      "attribute": "temperature", "op": ">=", "value": 27 },
    { "kind": "device", "device": "bedroom.heating_cooling_unit", "capability": "thermostatMode",
      "attribute": "thermostatMode", "op": "==", "value": "off" }
  ],
  "actions": [
    { "do": "home.command", "args": { "device": "bedroom.heating_cooling_unit", "capability": "thermostatCoolingSetpoint",
      "command": "setCoolingSetpoint", "args": [{ "choice": [24, 25, 26] }], "channel": "physical" } },
    { "do": "home.command", "args": { "device": "bedroom.heating_cooling_unit", "capability": "thermostatMode",
      "command": "setThermostatMode", "args": ["cool"], "channel": "physical" },
      "revert": { "afterMinutes": { "min": 60, "max": 240 },
        "action": { "do": "home.command", "args": { "device": "bedroom.heating_cooling_unit", "capability": "thermostatMode",
          "command": "setThermostatMode", "args": ["off"], "channel": "physical" } } } }
  ],
  "probability": 0.9, "maxPerDay": 3
}
```

Laundry:

```json
{
  "id": "r_laundry", "kind": "routine",
  "description": "Wash clothes when no wash has been started for 4 days.",
  "trigger": { "kind": "daily", "window": { "from": "09:00", "to": "21:30" } },
  "conditions": [
    { "kind": "place", "op": "is", "place": "home" },
    { "kind": "phone_state", "field": "asleep", "op": "==", "value": false },
    { "kind": "recent_action", "withinMinutes": 5760, "negate": true,
      "action": { "do": "home.command", "args": { "device": "laundry.washer", "capability": "cycleState",
        "command": "start", "channel": "physical" } } }
  ],
  "actions": [
    { "do": "person.moveRoom", "args": { "room": "laundry" } },
    { "do": "home.command", "args": { "device": "laundry.washer", "capability": "cycleState", "command": "start",
      "args": [{ "choice": ["normal", "quick", "bedding"], "weights": [7, 2, 1] }], "channel": "physical" } }
  ],
  "probability": 0.7, "maxPerDay": 1
}
```

(The `recent_action` condition matches any washer start: the engine compares only the fields given.)

### Daily-life routines

TODO (not agreed yet): the base list every profile needs (waking and sleeping, meals, commute or day place,
evening at home, phone use, ...).

### Output

One JSON object valid against SCHEMA: personaId, houseType, variant, roomRoles, simulation, start,
behaviours (the PATTERNS first, unchanged, then the routines), cookingMinutes, notes.

SCHEMA:
{{SCHEMA}}

VOCABULARY:
{{VOCABULARY}}

---------------------------------------------------------------------------------------------------
## USER

Persona {{PERSONA_ID}}:
{{PERSONA_TEXT}}

House: houseType {{HOUSE_TYPE}}, variant {{VARIANT}}. Room roles so far: {{ROOM_ROLES}}

PATTERNS (structured, copy into behaviours with kind "pattern"):
{{PATTERNS}}

Simulation: startDate {{START_DATE}}, days {{DAYS}}, seed {{SEED}}.
