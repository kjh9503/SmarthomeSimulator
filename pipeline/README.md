# Pattern pipeline: rewrite -> structure

1. **Rewrite** (`rewrite/`): `input/realistic_patterns.txt` -> patterns that use only what the simulator has
   (closest substitutes for missing devices, data and signals). Also assigns each persona's houseType.
2. **Structure** (this folder): rewritten text -> structured patterns (trigger, conditions, actions) for the agent engine.

## Step 1: rewrite (folder `rewrite/`)

| File | Role |
|---|---|
| `prompt_pattern_rewrite.md` | SYSTEM (rewrite rules, substitution guide, output format) + USER template |
| `simulator_capabilities.md` | Short readable list of the simulator's rooms, devices, places, phone signals and actions; made from vocabulary.json by `make_capabilities.py` |
| `rewrite_examples.json` | 3 made-up examples (device substitution, office device -> phone-visible signal, decoy note) |
| `build_rewrite_requests.py` | Assigns houseType by ratio (`--ratio 2room=1,3room=1,4room=1 --seed 7`, written to `personas.csv`) and writes requests, 10 personas each (~7k tokens) |
| `apply_rewrites.py` | Checks the replies (every row once, ids and types unchanged, fields present) and writes `patterns_rewritten.csv` + `rewrite_report.csv`; adds `newApps` to `../vocabulary_extra.json` |

```
cd rewrite
python3 build_rewrite_requests.py ../input/realistic_patterns.txt --ratio 2room=1,3room=1,4room=1
#   send each requests/rewrite_*.json to the model; save each reply (a JSON array) in replies/
python3 apply_rewrites.py ../input/realistic_patterns.txt replies/
python3 ../extract_vocabulary.py          # only if new apps were added
cd ..
python3 build_requests.py rewrite/patterns_rewritten.csv rewrite/personas.csv    # step 2
```

## Step 2: structure (natural-language pattern -> structured pattern)

Turns pattern sentences (patterns.csv) into structured patterns the agent engine can run on the smart-home +
phone simulator (`../browser/smarthome-sim.html`, Python port in `../smarthome_sim/`). The conversion is done by an LLM through an API; this folder holds the
prompt and everything the prompt needs.

## Files

| File | Role | Made by |
|---|---|---|
| `prompt_pattern_structuring.md` | The prompt: SYSTEM message (rules) and USER message template, with `{{...}}` placeholders | written |
| `prompt_agent_profile.md` | DRAFT prompt for step 3 (persona + structured patterns -> agent profile). Has the household-appliance groups (A: everyone uses, guarded by temperature / days; B: everyone owns, frequency varies; C: owned by some; D: not operated) with ownership sources and rule templates. The base daily-life list is still TODO | written |
| `sample_phone_person.py` | After the LLM wrote a profile: draws the person's phone-use numbers from population distributions (Winbush 2025 uses and app time within the `phoneUseLevel` third; quick-check share, screen-off habit, glances, time-out, day-to-day sigma) and rescales the phone-use rules to them; writes `phoneHabits` and `phonePerson`. `python3 pipeline/sample_phone_person.py profiles/<id>.json` | written |
| `vocabulary.json` | Every name a structured pattern may use: house types and rooms, device types with capabilities / attributes / values / commands, places, travel modes, activities, exercises, health measures and record fields, apps (+ extraApps), Bluetooth devices, weather, SmartThings alert categories, phone event types, the person's actions | generated from the simulator code, then the person-action list added |
| `pattern.schema.json` | JSON Schema (draft 2020-12) of one structured pattern; goes into the prompt and is used to validate replies | written |
| `structured_examples.json` | 3 worked examples (one per pattern type), made-up patterns so the model copies the form, not the content | written, checked by the validator |
| `build_requests.py` | Fills the placeholders and writes one request (system + user message) per persona to `requests/`; makes no API call | written |
| `validate_patterns.py` | Checks a reply against the schema and the vocabulary (unknown names, a device not in that room, wrong command arguments, values not allowed, hand actions while away, calendar conditions without a prerequisite) | written |
| `patterns_sample.csv` | The 6 sample patterns (columns: personaId, patternId, patternType, text) | from the conversation |
| `extract_vocabulary.py`, `tools_vocab_tail.js`, `vocabulary_extra.json` | Rebuild vocabulary.json from the simulator; the extra file holds the hand-written parts | written |
| `personas.csv` | personaId, houseType (2room / 3room / 4room), notes. **houseType is empty: fill it in** before building requests | template |

Inputs you provide per run: `patterns.csv` (same columns as the sample) and `personas.csv`.
Optional: `room_roles.json` = `{"<personaId>": {"study_room": "room2", ...}}` collected from earlier replies, so a
persona's room roles stay the same across batches.

Reference only (not sent): `../smarthome_sim/data/device_spec.jsonl` (source of vocabulary.deviceTypes), `event-formats-v3.json` (phone event examples with payload fields).

## Steps

1. Fill `personas.csv` (houseType per persona).
2. `python3 build_requests.py patterns.csv personas.csv [--roles room_roles.json]` -> `requests/<personaId>.json`
   (each about 18k tokens; almost all of it is the fixed SYSTEM message, so prompt caching helps).
3. Send each request's `messages` to the model. Ask for JSON only (JSON mode). The schema uses `oneOf`,
   which some providers' strict structured-output modes do not accept; in that case send it as text (as the
   prompt does) and rely on step 5. Provider limits were not checked.
4. Save the reply (a JSON array) as `structured/<personaId>.json`.
5. `python3 validate_patterns.py structured/<personaId>.json` (needs `pip install jsonschema` for the schema
   part). Fix or re-ask for any ERROR; read the WARNs.
6. Copy each pattern's `roomRoles` into `room_roles.json` for the next batch.

To regenerate `vocabulary.json` after the simulator changes: `python3 extract_vocabulary.py` (needs node). It reads the
simulator's own tables through `tools_vocab_tail.js` and merges the hand-written parts in `vocabulary_extra.json`
(person actions, extra apps, phone signals, room roles).

## Running a structured pattern

Put structured patterns and the persona's routines into an agent profile (`agent_profile.schema.json`, example
`../profiles/063.json`), check it with `python3 check_profile.py ../profiles/063.json`, and run it with
`python3 -m smarthome_sim.run --profile profiles/063.json` from the repo root (see `../README.md`).
The runner provides `phone.appNotice`, `phone.calendarUpdate` / `phone.calendarDelete` by `titleContains`, the apps in
`extraApps`, `prerequisites` only as descriptions (routines must make them happen), and `revert` actions.
Not provided yet: weather-app notifications (e.g. "Rain started"); today the weather is only in each event's `context`.
