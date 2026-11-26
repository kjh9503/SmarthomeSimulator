# Agent simulator: design notes and references

State: 2026-10-29, repo commit a1d0c42. Korean version: `docs/agent_design_notes.ko.md`. What was decided, why, what was checked, and the sources.
Marks: **[src]** taken from a source listed in References; **[assume]** our assumption, no source;
**[ours]** measured in our own runs (profile 063, Python, seed 63, 365 days of 2026, unless noted).

## 1. Purpose and framing

- The data set is a **controlled benchmark**: one simulated person per profile, one year of a smart home and a phone,
  with hidden patterns whose ground truth is known. It is not claimed to be "realistic life data".
- The method to be tested reads the raw phone log and outputs the person's patterns as **if-then rules**.
- Consequences for the design:
  - patterns and ordinary life must not differ in form (no log line that only patterns make, see 8);
  - realism matters where it changes how hard the patterns are to find; values should come from recent sources;
  - runs must be reproducible: same profile + same seed = same log (tested in `tests/test_port.py`).

## 2. Profile = list of rules

- A rule (`behaviours` entry): trigger -> conditions (all must hold) -> probability -> actions.
  `kind` is `pattern` (hidden, ground truth) or `routine` (ordinary life).
- Triggers: `time_window` (checked every minute, fires when the conditions turn true), `daily` (one random minute in
  a window), `rate` (perHour), `event` (home device report, phone event, person arrive/depart/wake/sleep, weather).
- Per-step options: `when` (step only if conditions hold), `probability`, `revert` (afterMinutes, byDevice = device
  timer), `{"choice": [...], "weights": [...]}` and `{min, max}` values drawn each time, `cookingMinutes`.
- The probability of a rule is one number. Variation by season or time of day is made by splitting rules (`months`,
  `days`, windows) or by conditions on weather / outdoor values / sensors (e.g. airing the window: Apr-Oct 0.35,
  Nov-Mar 0.12). Only window and balcony-door rules differ by month in 063.

## 3. Engine (agent runner, `smarthome_sim/agent.py`)

- Loop per minute: `sim.tick()` (world advances one minute), event rules for new happenings, scheduled items
  (reverts, delayed checks, morning check), time triggers, running tasks continue.
- The engine never writes simulator variables: it calls simulator functions per action (`home.command` -> `sim.run`,
  `home.record` -> `sim.set_value`, `person.moveRoom` -> `phone.move_room`, app control -> `phone.control_home`).
  Refusals (asleep, not at home, not in that room, driving) come from the simulator.
- A body action first moves the person to the device's room (`go_to`), so the log shows the occupancy change.
- One body task at a time; a task in a wait of 15 min or more can be interrupted; a daily rule is deferred at most 180 min.
- Actions inside a minute advance by 3-15 s each; phone app chains run at their own seconds (never before what
  already happened in that minute).

## 4. Off checks (`smarthome_sim/off_rules.json`) [assume, agreed with the user]

Before sleep, before leaving, and in the morning (within 60 min after waking) the person switches off what is on,
each with its own probability:

| Device | Bedtime | Leaving | Morning |
|---|---|---|---|
| light | 0.95 | 0.98 | 0.9 |
| lamp | 0.9 | 0.97 | 0.85 |
| tv, speaker | 0.95 | 0.99 | 0.9 |
| air purifier, heating, humidifier | 0.8 | 0.9 | 0.8 |
| cooling | 0.8 | 0.92 | 0.8 |
| window / balcony door Nov-Mar | 0.98 | 0.99 | 0.95 |
| window / balcony door Apr-Oct | 0.85 | 0.95 | 0.5 |

Stove and oven: cooking time is drawn (063: lognormal median 15 min, sigma 0.6; breakfast median 6, sigma 0.5) and the
off is scheduled; device auto-off after 240 min (stove) and 720 min (oven) as a last guard. [assume]

## 5. Household appliances (prompt `pipeline/prompt_agent_profile.md`)

Every house variant has every device type; whether a person uses one is decided by the rules. Groups:

| Group | Devices | Rule | Source |
|---|---|---|---|
| A everyone uses, guarded by conditions | cooling, heating, washer, light, lock/door | must be written | air conditioner 98% of households [src Gallup 2025]; drum washer 66% + top-loader 35% [src Gallup 2023] |
| B everyone owns, frequency varies | tv, stove, curtain, window, lamp | as the persona | TV 99% [src Gallup 2023] |
| C owned by some | air purifier 66%, humidifier 39%, dryer 35%, dishwasher 24%, oven 21%, AI speaker 18%, robot vacuum 15% | only if owned | [src Gallup 2023, 2025] |
| D not operated | sensors, router, doorbell, smoke alarm | none | |

Thresholds: cooling on at 26-28 C (default 27), heating on at 18-20 C (default 19) [assume]. Test with 063 + these
rules [ours]: 28/18 C gave cooling on 8 days a year; 27/19 C gave cooling 26 days (Jul-Aug only), heating 107 days,
washer 45 days. Open: summer indoor temperatures in the simulator may be low (Aug living room max 28.8 C without
cooling); sleeping with cooling on conflicts with the bedtime off check.

## 6. Repeated operations on one device

- No minimum interval per device in the engine. Most short on->off pairs come from one rule (hall light, cooking),
  as the rule means. Collisions between paths were all "switch on / open -> soon leaving or sleeping -> the off check
  switches it off" [ours].
- (a) second action too soon: not seen on its own in 063; on hold. (b) switching on just before leaving or sleep:
  **solved 2026-10-29** by "a person does not switch on what they are about to leave" (agent.py `leaving_soon`):
  before switching on / opening, the engine looks at today's planned departures and sleep (the minutes of daily
  rules, drawn now in the same way if not drawn yet, and running tasks); if one comes within the device's minimum
  time the step is skipped, for patterns and routines alike. Minimum times [assume]: window / balcony door 10 min,
  heating / cooling 30, TV / purifier / humidifier 20; lights, lamps, stove not limited. Result [ours, 063 + appliance
  rules, one year]: on and then off by a check sooner than the minimum 19 -> 0; 132 steps skipped (heating 72, TV 27,
  cooling 13, window 17, pattern p63_a 3).
- Event rules: once the event has happened and its delay is drawn, that time is used too (`eventCheck` items in
  `scheduled`, 2026-11-03); departures and sleep from events that have not happened yet cannot be known. Rerun
  [ours, same test profile, one year, 2026-11-03]: 0 short on->off by a check. The one case of the run before
  (12-25 23:29 heating -> 23:48 bedtime check; sleep from the arrive-home event rule `r_bedtime_late`) did not recur
  because the day went differently; not checked whether `eventCheck` would have stopped it.
- Fixed 2026-11-04: planned rules were counted without their conditions [ours, 063, one year: all 10 skips of p63_a
  were wrong]: 6 were "back home from the library / outside" rules (`r_library_home`, `r_weekend_back`) counted as a
  departure while the person was at home, 4 were `r_bedtime_late` (condition 23:30-03:00) counted as sleep at 22:xx.
  Now a planned rule's conditions are judged at its minute (place, devices etc. as now) and travel home is not a
  departure. p63_a skips 10 -> 0; the test profile still has 0 short on->off by a check. Left: a planned rule with
  `probability` < 1 still counts as certain.
- Wrong-skip check (2026-11-04): every skip is recorded and checked: did the person leave home (the trip's start) or
  fall asleep (seen up to a minute late, so one minute of grace) within the device's minimum time? `plan_skips.jsonl`
  (one skip a line, `wrong`) and `planSkips` in the summary (by kind of source). Result [ours, one year]: 063 2 wrong of
  11, test profile 5 wrong of 87; all wrong ones came from daily rules with probability < 1 (`r_to_campus` 0.92,
  `r_weekend_out`, `r_sunday_run`).
- Fixed 2026-11-04 (agreed (a)): daily rules and delayed event rules draw whether they will be followed
  (`probability`) when their minute is drawn, and use that decision when they run; plans leave out rules decided "not
  followed". Result [ours, one year]: wrong skips 063 0 of 13, test profile 0 of 69; follow rates match the
  probabilities (`r_to_campus` 0.92 -> 0.91, `r_weekend_out` 0.55 -> 0.52 / 0.61, `r_sunday_run` 0.4 -> 0.39 / 0.47);
  still 0 short on->off by a check in the test profile. The random order changed: the same seed gives a different year.
- **keepOn** (2026-11-03): a switch-on meant to stay on while away or asleep (e.g. cooling before leaving on a hot day)
  carries `"keepOn": true`. Engine: not skipped by the rule above; the leaving and bedtime checks leave that device on
  (the morning check does not); cleared on arriving home or waking. Prompt: so that keepOn is not a hint for patterns,
  when a pattern uses keepOn one routine must use it too (decoy rule). `check_profile.py` warns when a rule switches on
  without keepOn and a departure or sleep follows in the same rule, or the rule starts on a depart / fall-asleep event.
  Test [ours, July, 2 weeks]: without keepOn, cooling just before leaving skipped 9 times; with it, cooling stayed on
  (keptOn 10) and the bedtime check switched it off after the return.
- Ground truth: a run of a pattern whose actions were all skipped by this rule (nothing in the log) is counted as not
  followed (`notFollowed`, of these `notFollowedPlan`).
- Very short uses made by the profile's own distributions (left tail of cooking time): almost none in 063 (shortest
  cooking 2.6 min). No engine rule; to be measured over many LLM-written profiles (on hold).

## 7. Steps before an operation

Two criteria (agreed): (1) make a preceding step only if it leaves a log line; (2) if there is only one way to do it,
the engine adds it automatically (no probability); if there are several ways, the profile chooses with a probability.

| Operation | Preceding step (log line) | Ways | Decision |
|---|---|---|---|
| home device from the app | SmartThings in front | one | automatic, **done** (section 11, app tasks) |
| calendar add / change / delete | Calendar in front | one (other apps not considered) | automatic, **done** |
| outgoing call / SMS / photo | Phone / Messages / Camera in front | one | automatic, **done** |
| health entry, exercise, music play/pause | app in front or none (device, watch, earbuds, notification) | several | probability (not built) |
| screenshot, clipboard | some app in front | | the app in front, else a random installed one, **done** |
| install / uninstall | | | left out (not in any pattern) |
| hand operation at home | person in that room (occupancy) | one | done (`go_to`) |
| leaving / arriving | front door, lock | one | done |

Found before this rule existed [ours]: in 063 the app control of the air purifier by routines (25) and the leaving
check (3) had no SmartThings app line, while the pattern opened the app: a log no real phone can make, and a cue
that only patterns produce.

## 8. Benchmark validity

Expected reviewer points [assume, predicted]: circularity (the method finds what the generator encoded), generator
artifacts usable as shortcuts, hand-set probabilities without real data, independence of rules, no change over the
year, little diversity of LLM-written profiles, no transfer to real logs. The related work AgentSense (AAAI) showed
usefulness by training on generated data and testing on 5 real HAR data sets [src].

Checked so far [ours, `tools/pattern_only_lines.py`]:
- line kinds made only by the pattern in 063: purifier 60% by app, purifier 0% by device timer, SmartThings app opened;
- the pattern's action always came within the same minute as its last condition turned true (26 of 26 evenings:
  21:00 window start 19, PM2.5 crossing 3, window closed 1, arriving home 3) because `time_window` fires on the edge.
After app tasks [ours, 063, one year, run before 2026-11-03]: all 58 app controls happen inside SmartThings (0
outside); SmartThings foreground lines are pattern 25 / other 33, so no longer pattern-only. Still pattern-only:
purifier 60% by app, purifier 0% by device timer, the sequence kind "bedtime, purifier on for 10-30 min" (2 cases).
Agreed to be problems; not fixed yet: immediate response timing, pattern-only values.

### Ground truth file `ground_truth.jsonl` (agreed 2026-11-03)
- The answer is what the engine recorded while running, not the LLM-written pattern JSON: the engine does not run
  the pattern's actions as written (app steps merged, `wait` dropped, switch-on skipped before leaving or sleep, no
  opening of an app already in front), and the LLM may write steps the source text does not have (063's `wait 0-1 min`).
- One line per run of a `kind: pattern` behaviour whose conditions were true: `outcome` followed / not_followed
  (probability) / not_followed_plan (leaving or sleep soon) / unfinished (running at the end of the year); `if`: the
  trigger and each condition with the value seen then (`observed`; the engine judges conditions as written, so `if`
  equals the JSON); `then`: the steps the person did (result done / no_change) with time and arguments: app opening
  included (absent when the app was already in front), app closing, screen and `wait` left out. A person revert
  belongs to the same line (2026-11-04): the line is written when the revert ran or was dropped; `reverts` holds the
  planned time and result (done / not_followed with a reason: `off_check:bedtime` when the check switched it off first,
  or a refusal), and the app opening and switch-off it did are added to `then`.
- Device timers (`byDevice`) are not used (2026-11-04): no device has a timer with a SmartThings definition yet. p63_a
  "for 30 minutes": the person switches it off from the phone 25-35 minutes later (uniform [assume]). Prompts, schema
  and `check_profile.py` (warning) updated. Person reverts now run at their planned second (before: next minute, 0 s).
- Check [ours, 063, one year, 2026-11-04]: 31 lines (followed 28, not_followed 3); all 28 followed runs have then =
  open app -> 60% -> open app -> 0%, 26.2-35.3 min from on to off. A test (063 with window 23:00-23:30, 120 days) showed
  a bedtime check switching it off first, recorded as not_followed, `off_check:bedtime` (1 case, run before the
  condition fix).
- Check [ours, 063, one year]: 31 lines (followed 23, not_followed 4, not_followed_plan 4), as in the summary; all 46
  `then` steps match a log line at the same time (SmartThings FOREGROUND, purifier line); SmartThings was never already
  in front that year. Log line count unchanged by the recording (431,761).

## 9. Android Emulator (decided: not used)

See `docs/android_emulator_review.md`. In short: the agent still has to open apps (it moves complexity, not removes
it); more than half of the log (home copies, health, activity, Wi-Fi per place) would still be ours; no clock setter in
the console; real time; runs not reproducible; KVM needed; real apps need accounts.

## 10. Apps

- Base apps (every persona, 16): KakaoTalk, Chrome, YouTube, Spotify (music, podcasts), Instagram, Google Maps,
  SmartThings (home devices, laundry), Calendar, Phone, Messages, Camera, Samsung Health, Samsung Notes, Clock,
  Reminder (tasks), Weather. Preinstalled Samsung/Google apps on a Korean Galaxy (Z Fold7 list) [src Samsung];
  most used apps in Korea: KakaoTalk, YouTube, Naver, Coupang, Naver Map, Instagram by monthly users [src WiseApp 2024].
- Extra apps (only if the profile uses them): Coupang, Coupang Eats, NAVER (news), Millie (e-books), Kakao T.
- App kinds needed by the raw patterns (user's list): commute, e-book, laundry, music, note, podcast, news, shopping,
  task, video. Music: Spotify (YouTube Music has the largest share in Korea, 42%, Spotify 14% [src WiseApp 2025-04]).
- Fixed uid and data rate per app; new data rates are estimates [assume]. Package names checked where marked in the
  commit history (sysapps, Apptopia, WebCatalog); Coupang's main package inferred from Coupang Eats'.

## 11. Phone use and screen model

Engine:
- `phone.useApps`: first app from `first`, then with probability `continue` another app from `next`, each for a
  lognormal number of seconds (cut at 3600 s); with probability `check.share` the use is one app for a few seconds.
- Screen: on when a phone use starts (apps, app control, calendar, outgoing calls/SMS, photos, ...); after the use it
  goes off by hand within 1-3 s (probability `manualScreenOff`) or after `screenTimeoutSeconds`; an app in front goes
  to the background when the screen goes off.
- Glances: screen on without apps, off after a lognormal time (median 56 s, mean 88 s [src Hintze 2014]); the rate
  uses yesterday's idle waking minutes so that `glancesPerDay` is the real count.
- Day-to-day: each day the rate of the phone-use rules is multiplied by a lognormal factor (mean 1, `dailySigma`).
- App tasks (2026-11-03; user decision (1): the agent, not the simulator, opens and closes apps): an operation that
  needs an app (home device from the app, calendar, outgoing call, SMS, photo, `phone.appNotice`) is open app -> task
  -> close app, with one distribution for patterns and routines alike (agreed (a)). Written open (+wait) / task /
  (wait) / close steps in a profile are merged into the task at load (`merge_app_steps`). Time in the app (lognormal,
  cut at 600 s):

| Kind | Apps | Median | sigma | Min | Source |
|---|---|---|---|---|---|
| tap | SmartThings, Camera, others | 12 s | 1.56 | 3 s | weather-app use 33% / 67% quantiles 6 s / 23 s [src Tian 2021]; borrowed, no home-app data [assume] |
| input | Notes, Reminder, Calendar, Messages, KakaoTalk | 30 s | 0.7 | 5 s | PDA appointment entry 37.7 s [src Starner 2004]; phone typing 36.2 wpm [src Palin 2019] |

  The tap distribution has a long tail (sigma 1.56): 90% under about 88 s, 99% under about 450 s [computed]. SmartThings
  times seen in the year run: 4 s, 112 s, 599 s [ours].

Per person (`pipeline/sample_phone_person.py`): the LLM chooses `phoneUseLevel` (light / medium / heavy = lower,
middle, upper third) and the relative rules; the script draws the numbers and rescales the rules.

| Value | Distribution | Source |
|---|---|---|
| unlocks per hour | lognormal median 1.71, IQR 1.10-2.49 (sigma 0.606); day = x24 | [src Winbush 2025] |
| app minutes per hour | lognormal median 15.16, IQR 10.8-20.6 (sigma 0.479) | [src Winbush 2025] |
| share of quick checks | uniform 0.25-0.55; check time lognormal median 10 s, sigma 0.8 | [assume]; 41% of sessions under 40 s [src arXiv 2609.24477] |
| apps per use | `continue` 0.32 -> 68 / 22 / 7 % | [src Bohmer 2011: 68.2 / 19.5 / 6.6 %] |
| first app | messenger in about half of uses | [src Bohmer 2011: communication 49.6%] |
| manual screen-off | beta(4.5, 0.5), mean 0.9 | [assume]; people differ [src Hintze 2014] |
| glances per day | lognormal median 22, sigma 0.90 | [src Hintze 2014: median 22, mean 33] |
| screen time-out | 15 s 10%, 30 s 50%, 60 s 20%, 120 s 10%, 300 s 7%, 600 s 3% | [assume]; default 30 s [src Samsung] |
| day-to-day sigma | uniform 0.15-0.55 | [src Appiah 2026: within-person CV 16-60%, mostly > 25%] |

Checks against Korea [src]: app time 5.2 h a day (data.ai, Q1 2022); KakaoTalk about 52 opens and 22 min a day,
YouTube about 80 min a day per user (WiseApp 2025; our division of totals by monthly users).

Results [ours, after commit a1d0c42; target in brackets]:

| Level | Uses a day | App minutes a day | Uses under 40 s | Day-to-day CV of uses | KakaoTalk opens |
|---|---|---|---|---|---|
| light | 16.3 (17) | 146 (155) | 47.7% | 0.30 | 10.7 |
| medium | 33.9 (35) | 298 (311) | 46.6% | 0.22 | 22.8 |
| heavy (063) | 57.6 (60) | 453 (468) | 46.8% | 0.19 | 38.7 |

Known gaps: one-app uses about 83% (Bohmer 68.2%; left as is, agreed); uses under 5 s about 9% (Bohmer 49.8% of
chains, 2011); app time 94-97% of target.

Log size [ours, background lines fixed at 500 a day]: phone log 359,464 lines a year before the screen model; 063 heavy
437,281 (+22%, about 80,000 phone-use lines); light 361,495; medium 394,979. File 151.8 MB -> 185.2 MB (heavy).

## 12. Environment checks (simulator side)

- House and room areas (2026-11-04) [src: MOLIT statistics (stat.molit.go.kr) housing survey, ranges given by the user,
  original not checked]: 2room living+kitchen 18-22, master 11-13, small 7-9, other 8-10 m2; 3room 25-35, 12-14, 9-11,
  7-9, other 10-15; 4room 35-45, 14-16, 10-12, 9-11, 6-8, other 15-22. Each house takes the same position in every range
  (where its floor area lies in the range sum); the house area becomes that sum: 2room 54 / 49 / 54, 3room 84 / 84 / 74,
  4room 114 / 101 / 114 m2. Living / kitchen / dining split as before. Bathrooms: 3room and 4room have two (`bathroom`,
  `master_bathroom`), 4.3 / 2.6 m2 at 84 m2 scaled with the house area; 2room one. Both bathrooms have the same devices.
  Laundry, closet, hallway, entryway share the rest of "other" as before.
- Air conditioning (2026-11-04): system units in the living room and every room, kitchen only in 4room; none in the
  dining room, hallway or 2room / 3room kitchen (open to the living room, cooled by its unit).
- Speaker device removed (2026-11-04).
- Air between rooms (2026-11-04, house.py `CONNECTIONS`, `exchange`): before, each room mixed toward the house mean
  at 4% / 0.5% a minute (open plan / other), temperature not mixed (no source). Now joined rooms swap air in m3/min, the
  same air carrying heat, moisture, PM2.5 and CO2; no heat through walls (agreed). Joins [assume, flat-type layout]:
  see CONNECTIONS. Flow: open door and open plan Q = Cd/3 W H sqrt(g H dT/T) [src Brown & Solvason 1962] with
  Cd = 0.0835 (dT/T)^-0.313 [src Riffat 1989, measured through a doorway between floors], dT held at 0.5-13 K [src
  Lidwell 1977: no fall to zero]; door 0.9 x 2.1 m; open widths [assume] living-kitchen / living-dining 3 m,
  kitchen-dining 2 m, living-hallway / hallway-entryway / living-entryway 1.2 m, height 2.3 m; closed door 0.1 m3/h
  [src NIST 2017: undercut, yearly mean 0.12 m3/h]. Each pair is solved with an exact exponential decay (no overshoot).
  Door rule (agreed): a room's unit switched on at home closes its door (stays closed when the person leaves); switched on
  from outside by the app leaves it open; switched off opens it. Bathrooms, closet, laundry: always closed.
  Check [ours, Aug, 3room-A, 4 h]: only room1 cooled to 24 C, door closed -> room1 24.0 C, living room / room2 / kitchen
  stay 27.4 C. Switched on from outside (door open) -> living 25.5, room2 26.3 C. Living room cooled -> kitchen / dining
  24.2 C, open room1 24.9 C. Year (test profile): kitchen / dining median 25.1 / 25.2 C while the living room cools.
  RH while cooling is still high (living median 74%, max 90%): the unit's dehumidifying (next step).
- Cooling (2026-11-04/05): Korean home system air conditioning specs; see house.py AC_* comments (2.3 kW rooms and 4room
  kitchen, living 3.2 / 7.2 / 7.2 kW; airflow proportional to 2.3 kW [assume]; inverter 0.34-1.61 [assume, from a 2.3 kW
  single unit]; fan follows output [assume]; ideal coil, saturated outlet below the dew point).
- Room heat (2026-11-05): ISO 13790 5R1C per room instead of the relaxation to a "free indoor temperature" (no source;
  room1 1.0 W/K to outside). Values and sources in house.py PHYS["envelope"]: wall 0.170, window 1.0 W/m2K [src design
  standard, central 2], ACH50 3.51 [src Yoon 2013] / 20 [src Persily; Sherman N ~ 20], heavy 260 kJ/m2K, mass area 3x
  [src ISO 13790 via Modelica]. [assume]: window share 40/25/15%, wall length sqrt(area), SHGC 0.5, 110 lux per W/m2,
  curtain shading as for light, internal gains (person 65 W and light 10 W/m2 [src Kim & Byun 2008], TV 100, stove 2000,
  oven 2000, dryer 300, washer 150, dishwasher 300 W). No heat to the neighbours. The 15 C floor is gone. Heat mode is a
  stand-in until floor heating (rated kW into the air, no source).
  Check [ours]: Aug 3room-A 4 h at 24 C: living 71 -> 40%, room1 -> 52% (no rise at start); 16 C living 26%. Year (test
  profile): RH while cooling living median 49% (p10-p90 35-69), room1 53%; living room with the unit off median Jan 18.0,
  May 26.5, Aug 27.4, Oct 24.7 C; stove on for 240 min: kitchen 35.7 C in Aug (gains to check); Jan room1 with nothing on
  15.0 -> 10.5 C in 72 h. Wrong skips 14 of 166, all daily bedtime / departures that came late (deferred; not a problem).
- Physics test: compared with the Python simulator's own output (`tests/fixtures/physics_ref.json`), no longer the
  browser version; rewrite it after an intended physics change with `python3 tests/test_port.py --write-reference`.
  The browser version is not maintained until the user asks.

- Device definitions moved to SmartThings standard capabilities (2026-11-04). Checked against the 328 standard
  capabilities in Flobul/smartthings-capabilities (definitions fetched from the SmartThings API with the CLI, 2026-05),
  names only. Before: 37 of 48 standard names, 11 not in any definition, no Samsung extension.
  - Washer, dryer, dishwasher: `cycleState`, `remainingTime` -> `washerOperatingState` / `dryerOperatingState` /
    `dishwasherOperatingState` (live): `machineState` stop / run / pause, job state wash -> finish (dryer drying ->
    finished; agreed: these two only), `completionTime` set at start. Start = `mode.setMode(course)` then
    `setMachineState ["run"]`. The remaining-time lines every 5 min are gone.
  - Dropped (no standard definition): dryer `errorCode` and its alert, dryer timeDry course, dishwasher `startHeatedDry`.
  - Dryer time: delicate 80 + 0-20 min uniform [assume, no data]; normal course by the person's load shares (profile
    `dryerLoad`, chosen by the LLM from the persona, no data): small 60-100 min uniform [assume] / standard 100 min /
    large 100 + 16-50 min triangular, mode 16 [src Samsung service: 9 kg dryer standard 1 h 40 min for 4 kg, shorter when
    small, +16-50 min near the end when large].
  - Oven: `preheat` -> `ovenOperatingState` (`machineState` ready / running, `ovenJobState` ready / preheat / cooking);
    the preheat alert fires on preheat -> cooking.
  - Still without a real definition: humidifier `humiditySetpoint`, speaker `connection`, router `connectedDevices`
    (closest `wifiMeshRouter`, deprecated).
  - Check [ours, one year]: 063 dishwasher 36 runs, all run -> wash -> finish -> stop, 119-120 min, 36 alerts. Dryer test
    (test profile + dry-after-wash rule, `dryerLoad` 0.3 / 0.4 / 0.3): dryer 45 runs 71-142 min, washer 50 runs 29-90 min.
    `tests/test_port.py` passes (the JS dryer used the old 60-minute command, so the test pins the dryer to 60 min).
  - Not changed: the browser JS simulator and `tools/physics_script.json`. `vocabulary.json` (normally extracted from the
    JS) was edited from the Python device spec.

- Heating energy vs measured (2026-11-18). Lee et al. 2014 (104.6-107.7 kWh/m2 a) is heating plus hot water ("not
  separated") in flats built 1991-2008. Seoul end-use metering (Jin et al. 2019): heating 83.5, hot water 24.8 kWh/m2 a,
  so heating alone in Lee's figure is about 81. 063 with older U-values (wall 0.47, window 3.84): 72.9; plus 0.5 air
  changes/h: 79.5 [ours, one year]. So the gap is mostly the envelope standard and the hot water. Neighbours at 22 C are
  not the cause: 063 heats above 23 C and loses heat to them (-5.0); without them 21.7. (2026-11-26: the neighbours are now 20.0 C in winter, measured; see
  "Neighbours above and below".) No measured figure found for flats
  built to the 2018+ standard. Heating-season balance (063, kWh/m2): windows -17.6, ventilation/infiltration -10.9,
  floor heating downwards -5.2, neighbours -5.0, walls -4.1, sun +9.8, internal +4.5, floor heating 29.2.
- Sun on windows (2026-11-20). Before: daylight (clear noon 25,000 lux x sin altitude) / 110 x an azimuth factor
  (0.35-1); horizontal irradiation was 26% of Seoul measurements (0.87 vs 3.33 kWh/m2 a day) and the sun height was
  ignored (south windows got too much in summer, too little in winter). Now `weather.solar_at`: sun position (Spencer
  1971), Haurwitz (1945) clear sky x weather factor (clear 1, cloudy 0.4, rain 0.15, snow 0.2) x monthly calibration
  (`SOLAR_CAL` 0.77-1.06, `tools/calibrate_solar.py`, years 2024-2028 fitted to Seoul 1982-2009 monthly means, Jo et al.
  2011), Erbs (1982) beam/diffuse split, vertical window = beam x cos(incidence) + diffuse x 0.5 + horizontal x 0.2 x 0.5
  [assume isotropic sky, albedo 0.2]. Daylight lux and indoor illuminance unchanged (heat only).
  - Check [ours, one year, 063]: heating 45.2 -> 17.5 kWh/m2 a; January living room hourly median 23.5 C. Jul-Aug living
    room 39.2 C (10-90%: 37.2-41.5): no cooling, windows nearly always shut, no balcony shade (the balcony is only an
    outdoor space). Balconies: all expanded (agreed 2026-11-20: no shade; summer sun is handled by window,
    curtain and cooling habits; no figure found for the share of expanded flats). Next: window and cooling habits.
- Cooling and window habits (agreed 2026-11-20, per person like heating and ventilation). The LLM writes `coolingRanges`
  (uses, switch-on temperature, setpoint, bedtime / leaving keep or off, unused rooms) and `windowRanges` (opens hot rooms,
  opening temperature, sleeps with it open, airings a day 0/1/2, airing minutes, winter airing minutes);
  `pipeline/sample_cooling_person.py` / `sample_window_person.py` draw them. Engine (`cooling_*`, `window_*`, `airing_*`):
  awake at home, the room the person is in is cooled once it reaches the switch-on temperature (its window closed first;
  kitchen / dining / hallway / entryway use the living room unit, a 4-room kitchen its own); a hot room's window is opened
  when outdoor air is at least 1 C cooler and closed 2 C below the opening temperature, when outdoor air is hotter or for
  cooling (only windows the habit opened); every window is closed for rain or snow; airing: the living room window at
  9-11 and/or 17-19, usual minutes x 0.7-1.3. At bedtime / leaving the habits decide cooling units and windows (the off
  rules for them are not used); at bedtime a window may stay open on a warm dry night when the room is warmer than
  outdoors. Figures: switch-on 29.8 C, switch-off 27.3 C on average (Chun & Bae 2005, Seoul flats); cooled rooms 25.2 C
  (Yun et al. 2020); airing once a day 49.7%, twice 30.7%, under 20 min 43.0%, 20-40 min 39.6%, mornings 9-11 55.8%,
  evenings 17-19 33.4% (Lee 2010, spring survey of 154 flats); winter: 75% 1-2 times a day under 10 min (Cho & Choi
  2013). No data for bedtime / leaving habits, opening for heat, sleeping with the window open (LLM's choice).
  - Check [ours, one year]: 063 (drew no cooling, opens at 26 C, sleeps with it open, airs twice a day): Jul-Aug living
    room hourly median 33.5 C (10-90%: 31.5-35.8), its window open 860 of 1488 h, heating 20.8 kWh/m2. Same person with
    a cooling habit (on at 30 C to 27 C, kept on at night, off when leaving): 28.3 C (26.7-30.2), 121 switch-ons. Outdoor
    hourly median 25.6 C. Measured (Yun et al. 2020): summer indoor 26.6 vs outdoor 23.6, cooling off 26.9 vs 23.3. That
    063 stays +7.9 C with the window open 58% of the time looks due to the open-window airflow (`windowOpen` large 0.04
    per min = 2.4/h, no source) and windows shut while the flat is empty in the day; to check.
- Open windows (2026-11-20). Before: fixed rates (large 0.04 per min = 2.4/h, medium 1.8, small 1.2; no source) x a wind
  factor. Now single-sided flow, De Gids & Phaff (1982), the basis of EN 16798-7: Q = 1/2 A sqrt(0.001 U10^2 + 0.0035 h dT
  + 0.01); A = half the glass (one sash of a sliding pair; "half the window", Cho & Choi 2013), h = 2.1 / 1.5 / 1.0 m for
  large / medium / small [assume]; the balcony door counts as the living room's large window; capped at 0.8 of the room
  air a minute. PM2.5 and CO2 exchange use the same rate (CO2 was a fixed 0.05 per min). Example: living room, half
  open, 2.3 m/s, 5 C difference -> about 36/h. Measured: Beijing bedroom, windows open more than 3 cm, 0.89-2.31/h
  seasonal means (Liu et al. 2022; opening width not recorded).
  - A window opened for heat stays open at least 60 min and closes 4 C below the opening temperature (with 2 C the 063
    living room window opened 5,575 times a year, every few minutes; no data, chosen to stop that).
  - Check [ours, one year, 063: no cooling, opens at 26 C]: Jul-Aug living room hourly median 26.6 C (10-90%: 24.1-28.9),
    room1 27.3, room3 28.2; outdoor 25.6. Living room window opened 98 times in Jul-Aug (1.6 a day), open 792 of 1488 h.
    January living room 23.8 C; heating 29.5 kWh/m2 (more airing loss). Measured (Yun et al. 2020, whole summer):
    indoor 26.6, outdoor 23.6.
- Stove and range hood (2026-11-21). While the stove is on: one large burner at full flame [assume], 4.07 kW (Rinnai
  RBR-S3000, city gas, seller's table; Danawa gives 8.84 kW in all, not resolved) x 0.30 sensible = 1.22 kW, x 0.20
  latent = 0.81 kW as water vapour (about 1.2 kg/h) (Building America gas range fractions). Before: 2000 W sensible, no
  vapour. The range hood has no SmartThings capability (effect only): each cooking it runs with the person's share
  (`hoodRanges.useShare`, `pipeline/sample_hood_person.py`; no usage survey found, LLM's choice), until the stove is off:
  0.018 m3/s exhaust (stage 1, one Korean flat measured, Lee, Jeong & Kang 2017) made up by outdoor air, 85% of the
  cooking PM2.5 removed (80-90%, Lee 2016).
  - Check: Aug 5 18:00, closed flat starting 30.8 C, 240 min: kitchen 34.0 at 10 min, 35.3 C at 180 min, RH 62 -> 88%;
    with the hood 34.6 C, 85%. Before (2000 W, start 28.9 C): +5.0 K at 10 min, 36.1 C at 180 min. 063 one year (share
    0.55): hood on 131 of 244 cookings; kitchen temperature report lines max 35.1 -> 33.0 C, median 23.9 C.
- Indoor moisture (2026-11-21). The fixed +3 hPa over outdoor air (`moistureOffset`, no source) is gone; physical sources:
  a person 52 g/h (family of 4: 0.44 pint/h, Minnesota 1988 table; 1.25 L a day, Quirouette, NRC Canada; was about
  2.5 g/h for a 10 m2 room), a shower 0.24 kg per 5 min = 48 g/min (same table), indoor laundry drying 2.2-2.9 kg a load
  (same table) released evenly over 8-12 h [assume the hours]. Shower habit: the LLM's `showerRanges` (0/1/2 a day,
  morning / evening, minutes) -> `pipeline/sample_shower_person.py` -> engine-made routines (bathroom, light on,
  `person.shower`, light off; morning 3-20 min after waking, evening 21-23). Laundry (revised 2026-11-21, agreed: a per-person
  share): 5-40 min after a wash ends [assume], once home and awake, the person starts the dryer by hand (logged) with
  the share `laundryRanges.dryerShare` (`pipeline/sample_laundry_person.py`; 0 without a dryer), else hangs it on a rack in
  the laundry room (else the living room); a dryer a rule started meanwhile counts as the dryer. Washing itself is a habit too (agreed
  2026-11-21): from `laundryRanges.washesPerWeek` (whole) and `weekendShare` the engine makes two routines (weekend 09-12
  with probability n x share / 2, weekday 19-22 with n x (1 - share) / 5; to the laundry room, washer on by hand). More
  than half of 20-50 year olds wash once every two days (Laundrygo "2022 Korean Laundry Report", Aju News 2022-08-18; a
  laundry service's survey). Times of day: no data.
  - Check [ours, one year, 063: 2 a week, weekend 0.55, dryer 0.65]: 57 washes (about 1.1 a week; skipped when not home
    then), 36 dryer, 21 rack. January living room 13% (11-16). Rack and shower write
  no line of their own (seen in the humidity sensors). Korean dryer ownership 12% (2020) -> 35% (2023) (Gallup Korea,
  Herald Economy 2025-11-18).
  - Check [ours, one year, 063]: January living room hourly median 21% -> 13% (10-90%: 10-18), bathroom 18% (up to 56%
    in showers), July living room 69%. 364 showers. No washes: the 063 profile has no laundry behaviour. With the
    ventilation unit off: 16%. Measured winter means: 36.6% (households 19.5-58.5%, Choi & Jung 2008), 40-60% (Kim et
    al. 2014, 68 flats). 063 is low because it is one person in 84 m2, ventilation unit always on, airing twice a day,
    no laundry.
- Outdoor daylight and saturated air (2026-11-21). Outdoor daylight lux = calibrated global irradiance x 110 (before:
  clear noon 25,000 lux x sin altitude, about a quarter of real). The indoor window factors (living room 3%, rooms 2%,
  small 1.2%, none 0.2%) are of the size of simulated daylight factors in Seoul flats (living room 2-5%, bedrooms
  0.5-1.5%, kitchen 0.2%; Lim et al. 2012) and stay. 063: midday living room 151 -> 768 lux (Jan), 277 -> 1,019 lux (Jul),
  room1 about 710, entryway about 90; light switch-ons living room 278 -> 259, entryway 282 -> 249. The browser parity
  test skips daylight. Racks: laundry dries only as fast as the room air takes the water, the rest stays in the clothes
  (before: dropped above saturation); 063, 90 days: about 96 h per rack in the closed laundry room (4 racks).
- Ventilation habits (2026-11-18; agreed: a per-person habit, effect only when SmartThings has no device for it). Flats of
  30+ households since 2006-02 must be able to ventilate 0.5/h (Rules on Building Equipment Standards art. 11, annex 1-5;
  checked through commentary pages, not the statute text). No ventilator / ERV capability among the 328 standard and 182
  extension capabilities (Flobul), so there is no device and no line: `house.py` `envelope.ventilator` 0.5/h, heat and moisture
  recovery 46% when outdoor air is colder than the room and 27% when warmer (field means for winter and summer, Kim, Park &
  Sohn 2005; agreed 2026-11-19: chosen each minute, so spring and autumn switch within a day; using them between seasons
  and for moisture is [assume]; certified lab ratings are higher, Shin et al. 2014), 60% outdoor-air filter on PM2.5 (annex 1-5, KS B 6141),
  the same in every room [assume]. The LLM writes `ventilationRanges` (uses yes/no, when always/home/awake, winter run/off);
  `pipeline/sample_ventilation_person.py` draws `ventilationHabits`. 47.5% of households use the unit (Gallup 2011 for
  Samsung C&T, cited by Lee 2016; reasons for not using it: bill, noise, cold draught). No data on hours of use.
  - Check [ours, one year, 063 with the habit varied]: heating 29.2 (not used) -> 29.7 (always, off in winter) / 35.7
    (awake) / 40.4 (home) / 45.2 (always) kWh/m2 a. Winter room1 CO2 (median of report lines) 903 -> 611 ppm (always),
    PM2.5 21 -> 15. Winter humidity 23-24% either way (looks low; to check). 063 drew always, running in winter. With 27% added (2026-11-19) the run is unchanged:
    in Jul-Aug the 063 living room is always warmer than outdoors (hourly median 32.2 C vs 25.6 C), so 46% applies.
- Balcony and laundry drying (agreed 2026-11-22). The laundry room has no window any more (it was never opened). The five
  plans of 84 m2 and more (3room-A/B, 4room-A/B/C) have a real front balcony, not expanded: 1.5 m deep (balconies within
  1.5 m are left out of the floor-area ratio; Economist 2018-01-28) x living room width taken as sqrt(living area)
  [assume], outer glass 2.2 m high [assume], clear double glazing U 2.4 (integrated 2.407, Yoon, An & Kim 2007), SHGC 0.7,
  0.7 of the sun passing on into the living room, 1.0 air change an hour through its frames [all assume], no heating. The
  living room's windows face the balcony instead of outdoors; the balcony door exchanges air with the living room. Smaller
  plans keep the old balcony (outdoor values copied) -> fixed 2026-11-25, see "No balcony in the small plans". Racks stand on the balcony, else in the living room. The person checks
  a rack 6 h after hanging and every 4 h after that when home and awake (the check writes no line); dry = water left at
  most 5% [assume: stands for touching the clothes]. Not dry: outdoor air between `dryingHabits.airMinC` and `airMaxC`
  and no rain -> the window of the rack's room is opened (balcony outer window: no sensor, no line; living room: logged);
  otherwise a balcony rack is moved into the living room (agreed: option (나)), a living room rack gets heating (colder)
  or cooling (warmer). Windows opened for drying are closed at bedtime, when leaving, in rain and when the rack is taken in.
  The LLM writes `dryingRanges`; `pipeline/sample_drying_person.py` draws `dryingHabits` (no data).
  - Check [ours, one year, 063 in 3room-A, airMinC 11, airMaxC 27]: 29 racks, all taken in, 10-25 h after hanging
    (median 19.6; the spread comes from the check times, sleep and work); 14 moved inside (Nov-Mar, and Jul-Aug above
    27 C); balcony window opened 10 times. Before (closed laundry room, 90 days): about 96 h per rack. Hourly medians:
    January balcony 15.6 C (4.7-33.6) at outdoor -1.1 C, balcony RH 18%; July balcony 33.8 C (29.0-44.7) at outdoor
    25.4 C. Heating 29.5 -> 17.0 kWh/m2 a. Living room Jul 32.8 C, Aug 34.0 C (before the balcony: Jul-Aug 26.6 C): the
    window habit opens the living room window onto the balcony, whose outer window stays closed (open task). No measured
    Korean balcony temperatures found to compare with.
- Balcony outer window (agreed 2026-11-23). SHGC 0.5 over glass and frames, as the room windows (0.7 was glass-only:
  double glazing shading coefficient 0.83, Kim, Moon & Yu 2013, x 0.87; 063 January balcony max 33.9 -> 19.6 C). The outer
  window has an open/closed sensor only, `balcony.window_contact`, in flats with a real balcony (no motor: no Korean home
  network rule, builder article or SmartThings capability for window openers found). For everyone: whenever the living
  room window (onto the balcony) is opened, by the window habit, airing or a rule, the person also opens the outer
  window, and closes it with the living room window (unless laundry on the balcony still needs it); rain closes both.
  The window habit does not handle the outer window itself. Check [ours, 063, one year]: minutes with the inner side open
  and the outer window closed 0 (was 932 before pairing rules too); Jul / Aug living room 26.6 / 27.3 C (before the
  balcony 26.6, with the balcony and a closed outer window 30.3 / 31.0). Not done yet: closing the inner side when the AC
  is switched on (the existing closedForCooling covers the living room window), laundry inside while the AC runs (a
  personal habit), bringing laundry in during heating, opening the outer window when leaving in summer (personal).
- No balcony door (agreed 2026-11-23): doors people walk through carry no sensor (room doors never had one); the
  balcony door is merged with the living room window, the one sliding glass door between living room and balcony in a
  flat with a real balcony. Open, living room and balcony swap air both ways through a door-height opening of half its
  glass (opening_flow, buoyancy only); smaller flats: the living room window opens to outdoors as before.
- Window sensors per household (agreed 2026-11-23). Only the entrance door has a sensor in every flat (home security
  services start there: ADT Caps "캡스홈" base package, Seoul "도어지킴이"; window sensors are an add-on). The profile's
  `windowSensors.rooms` (LLM, from the persona, with a reason; no data on how common) lists the windows with a sensor;
  the other windows keep their state for the physics but write no line and are not counted in wifi connectedDevices.
  check_profile: a PATTERN may only use listed windows. 063: living room only (p63_a checks it). Check [ours, 063, one
  year]: window lines balcony 1,008 / room1 288 / room2 72 -> 0, living room 1,004 unchanged; connectedDevices
  124-125 -> 120-121; temperatures and window combinations unchanged.
- Walking between rooms (agreed 2026-11-23). The person walks the shortest route through the rooms between
  (House.path over CONNECTIONS, plus living room - balcony), each room on the way sensed, 2-4 s and 4-10 steps a room
  [assume], the engine's second moving on with it (then still capped at :59; fixed below); going out walks to the entryway first.
  tools/check_order.py counts order violations in a log. Check [ours, 063, one year]: rooms skipped (M1) 2,888 -> 0,
  two rooms at once (M4) 21 -> 0; steps a day median 3,310 -> 3,124. Left: 0 s stays piling up at :59 when a minute is
  full (820 of 821 at :59: an error of the time handling, not short visits; fixed below), the balcony entered through a closed living room window (M3), lines written
  ahead of the clock (front door on arrival; app tasks outside rules).
- No actions piled up at :59 (agreed 2026-11-23). The engine's second counter within a minute was capped at 59, so when
  a minute held more than 60 s of actions the rest were all stamped :59 (063: 972 minutes a year; e.g. 01-06 07:54:59
  hallway, living room, dining room, living room and floor heating on in one second). Now a new action starts only if
  it fits (15 s plus 4 s a room to walk to its device; rules resume, scheduled reverts and habits wait a minute); an
  action that still runs past :59 goes on into the next minute, which starts after it, its physics lines too
  (Simulator.not_before). Check [ours, 063, one year]: 0 s stays (M2) 821 -> 0; 181 minutes start after an action
  that ran on (median 7 s); no heating / cooling operating state logged before the mode that causes it.
- Sliding door onto the balcony (agreed 2026-11-23). Walking onto the balcony through a closed living room window (the
  sliding glass door) the person opens it and closes it again on the way back in (no pairing with the outer window
  for that); closing both, the outer window is closed first, through the still open door; rain closes the outer
  window first. Check [ours, 063, one year]: balcony crossed through a closed door (M3) 1,108 -> 0. Found with it:
  the person stays where an errand left them (balcony up to 8.7 h after a laundry check, 25 stays over 1 h; laundry
  room 56), so the door opened to go out stays open meanwhile (inner open / outer closed 0 -> 2,584 min); falling
  asleep without walking to a bedroom (laundry room on 12-24). Not fixed yet.
- Layer A, home base (agreed 2026-11-24; blueprint smarthome_llm_blueprint.md, layer A only). The engine had no idea
  where the person is between rules and habits: they stayed where the last action left them. Now the LLM writes
  `homeBaseRanges` (room weights per band: morning 05-09, day 09-18, evening 18-23, night 23-05, weekdays / weekends;
  stayMinutes, errandMinutes, sofaSleepShare) and pipeline/sample_home_base_person.py draws `homeBaseHabits` (no data).
  Each minute (home, awake, no task that put them in a room, minute not full): outside the band's rooms they go back
  after a lognormal stay around errandMinutes; in a home-base room they choose again after one around stayMinutes; a
  stove on in the kitchen or a TV on holds them. Phone use alone does not hold them. A task step after something else
  moved the person walks back to the task's room first; sleep only in a bedroom or on the sofa (a bedtime that starts
  in the living room stays there with sofaSleepShare). On arrival the person's next action starts after the front
  door lines (written up to +10 s). Check [ours, 063, one year, before -> after]: laundry room 179 -> 10 h, balcony 106
  -> 3 h; stays over 1 h laundry 56 -> 1, balcony 25 -> 0; longest balcony 8.7 -> 0.1 h, laundry 9.9 -> 1.7 h (phone
  use there before the fix: 1 h); fell asleep: room1 362 / living 2 / laundry 1 -> room1 352 / living 13 (sofa); order
  checks M1-M9 and P1 all 0; left: app / screen order (F3, F4) and steps in the first minute of an hour (M10).
- Idle-time activities (agreed 2026-11-24). Layer A only chose rooms, so between rules nothing happened in the log
  for hours (four profiles: gaps of 4 h and more with no device action while home and awake 62 / 82 / 192 / 189 a
  year). Now the engine has a pool of 18 activities from the time-use survey's activity classes (Statistics Korea
  2009 middle classes, Kim et al. 2013 appendix 2-3): tv, reading, study, snack, toilet, dishes, cleaning, music,
  video, game, shopping, call, workout, nap, plants, folding, tidying, rest, each with rooms and device / phone
  actions (agent.py IDLE_POOL). The LLM writes `idleActivityRanges` for the ones the persona does (weights per band,
  median minutes, rooms, apps / kinds / dishwasherShare / robotShare); pipeline/sample_idle_person.py draws
  `idleActivityHabits` (no data). One activity at a time, picked by band weight, the one just done x 0.3 [assume]; a
  rule or habit moving the person ends it with its end actions. New extra apps (Netflix, Brawl Stars, KB Star
  Banking) and home workouts (Health Connect EXERCISE_TYPE_YOGA 83, STRENGTH_TRAINING 70, STRETCHING 71). Three TEST
  profiles (tools/make_test_profiles.py: office worker 2room-A, remote worker 3room-B, retiree 4room-B; no patterns).
  Check [ours, one year each, layer A only -> activities; 063 / office / remote / retiree]: gaps >= 4 h 62 / 82 / 192
  / 189 -> 13 / 8 / 70 / 2; awake living-room stays >= 4 h 23 / 46 / 52 / 107 -> 3 / 32 / 7 / 34; order checks
  M1-M9 still 0. Left: a lognormal tail makes some long goes (office TV 5.3 h on 11-04); the office persona does
  most things in the living room; the remote worker's study room is the work routine.
- One app in front at a time; none after the screen is off (agreed 2026-11-24). An app task outside a rule (off checks,
  reverts, heating/cooling from the app) ran all its events at once: the close, up to 10 min ahead, was written with its
  later time while the phone already had no app in front, so the next app came to the foreground with SmartThings never
  sent back (F4) and SmartThings went back after the screen was off (F3). The log's FOREGROUND/BACKGROUND are Android
  ACTIVITY_RESUMED/ACTIVITY_PAUSED (moved to / from the front), not starting or quitting the app. Now open + the task run
  at once (the caller needs the result; the person's next action waits for it), the close runs in time order with what
  the person does next (due_loose: before each action, walk step and chain event); a task in the app still open from such
  a task keeps it open and closes it after itself. Check [measured, 1 year each, 063 / office / remote / retiree]: F4
  37/39/24/6 -> 0, F3 22/26/19/23 -> 0, F2 0/0/1/0 -> 0; SmartThings in front median 11/13/11/11 s -> 12/12/10/15 s
  (retiree: fewer, longer opens, 604 -> 517, as several commands share one open).
- Steps in the first minute of an hour (agreed 2026-11-24). A walk at hh:00-hh:01 went into the past hour's sum (the
  minute step uses t - 1 min) after that hour's HOURLY line was written, and the sum was dropped (no samples): steps lost,
  an hour with moves and 0 steps. Now a walk counts in its own hour. Check [measured, 1 year each]: M10 9/18/18/29 -> 0.
- No balcony in the small plans (agreed 2026-11-25). The four plans under 84 m2 (2room-A/B/C, 3room-C) are expanded and
  have no balcony space (agreed 2026-11-20: "all expanded"). The room list came from the house type alone, so they still
  had a 'balcony' nobody could reach, whose sensors (temperature, humidity, air quality, noise, occupancy) and light wrote
  the outdoor values (office 2room-A: 21,356 lines a year, never occupied). Writing "smaller plans keep the old balcony" on
  2026-11-22 I did not check it against the 11-20 agreement. Now a balcony exists only where room_profiles.json gives it
  glass (glassM2); elsewhere no room, no devices, no way to it from the living room. vocabulary.json: balcony out of the
  2room rooms, a note on 3room-C. check_profile: an error when such a plan's rules use the balcony, a warning when its
  room weights or activities name it.
- One-minute step with a window open (2026-11-25). The room air was one explicit step a minute. With a window open the
  air's time constant is under a minute (office living room 53 s), so the step overshot: 10 min airing at 0.6 C outdoors
  gave 6.0 C after 1 min where the converged answer (600 steps a minute) is 16.3 C. Now the air node is solved exactly over
  the step (surface node eliminated, mass and gains held), the mass uses the step's mean air temperature, air swaps use
  1 - exp(-k dt) (was k dt), and the minute is split into 6 while any window is open. Same airing: 15.7 / 12.4 / 11.0 C
  after 1 / 3 / 10 min vs converged 16.3 / 12.8 / 11.3. Other parts checked by time constant (mass 2.6 h, floor layer
  74 min, air conditioner already in 10 s steps, room-to-room swaps already exact): no change needed. The open-window
  cap (0.8 of the room air a minute) is kept. Check [ours, 1 year each, before -> after; 10-min samples]: office (no
  balcony) living room with the window open at under 5 C outdoors, median 7.2 -> 12.2 C (10.1 K above outdoors); the
  flats with a balcony (window onto the balcony) 20.2 -> 20.2 / 20.4 -> 20.5 / 21.2 -> 21.2 C; lowest room temperature
  of the year 063 -0.3 -> 3.8 C, retiree 0.3 -> 4.0 C. January humidity, cooling humidity, August temperatures within
  0.5 %p / 1.9 %p / 0.5 K of before. Order checks all 0. Run time: office 30 days 15.9 -> 17.1 s.
  Still faster than measured: the temperature difference halves in about 3 min vs about 7 min (Fitzner & Finke 2012).
- Neighbours above and below, all year from measurement (agreed 2026-11-26). Before (2026-11-05): 22 C [our assumption]
  while the outdoor daily mean was below 15 C, otherwise no heat flow at all (the old "same temperature as this flat"
  assumption left over, never decided for summer), so a closed flat kept all its summer heat. Now Yun et al. 2020 table 3
  (8 Seoul apartments, Mar 2016 - Mar 2017, hourly, all hours): winter 20.0 +- 2.1, spring / autumn 23.0 +- 2.5, summer
  26.6 +- 2.0 C (house.py NEIGHBOUR). Joined between seasons by a line through one point per season, set so that each
  season keeps the measured mean [our assumption]; each flat drifts by its own day-to-day AR(1) (0.7) within one SD
  (mean + SD x tanh(0.5 z)) [our assumption], drawn, not simulated. Drawn year: season means 19.8-20.0 / 22.9-23.2 /
  26.6-26.7 C over three seeds. Check [ours, 1 year each, before -> after; living room, kitchen, bedrooms, all hours]:
  remote (closed in summer, no cooling) summer 39.3 -> 30.0 C, 14.6 -> 5.2 K above outdoors (measured 26.6 C, +3.0 K),
  Aug living room max 43.0 -> 33.0 C, spring / autumn 29.0 +- 7.3 (max 45.4) -> 25.2 +- 3.0 C (measured 23.0 +- 2.5);
  063 / office / retiree summer 26.8 / 27.6 / 28.0 C (+2.1 / +2.9 / +3.3 K); winter all hours 22.1 / 21.8 / 20.6 /
  21.7 C (was 0.4-0.7 K warmer; measured 20.0). Heating energy up: 19.3 -> 23.3, 11.0 -> 14.8, 10.1 -> 15.3, 14.3 -> 20.1
  kWh/m2 (063 / office / remote / retiree). Cooling hours down: office 2,687 -> 1,468, retiree 556 -> 259. Order checks
  all 0. Still above the measured summer: remote +5.2 K vs +3.0 (sun, envelope: see the closed-flat variants).
- Python port equals the JS simulator: outdoor values within 1e-12, physics within 1e-15 (`tests/test_port.py`).
- 2026 weather vs climate normals [ours]: monthly max/min temperature within 0.9 C, PM within 1.2 ug/m3, 86 wet days
  vs 79.3, 1,509 mm vs 1,418 mm.
- Cooling and heating work in the physics: Aug living room 30.2 -> 24.0 C in 20 min (cool, setpoint 24);
  Jan 15.0 -> 22.0 C in 30 min (heat, setpoint 22) [ours].
- Phone log only (no separate home log); SMARTTHINGS copies stored without derivable fields, `expand()` restores them
  byte-exact.

## 13. Open tasks

See `docs/open_tasks.md`: calendar events from persona, incoming phone events (messages, calls), method choice for music/health/exercise, JS runner without the phone model, pattern-only cues and
immediate response timing, gap-dependent off probabilities, persona -> daily-life base list.

## References


| Short name | Reference | Used for | Read |
|---|---|---|---|
| De Gids & Phaff 1982 | de Gids W., Phaff H. Ventilation rates and energy consumption due to open windows. Air Infiltration Review 4(1), 1982; equation as quoted in "Calculation methods for single sided natural ventilation - now and ahead" (Aalborg Univ.). https://vbn.aau.dk/ws/files/284948171/Calculation_methods_for_single_sided_natural_ventilation_now_and_ahead.pdf | open-window airflow | review paper |
| Liu 2022 | Liu S. et al. Study on the Dynamic Natural Ventilation Rates of Occupied Residence. E3S Web Conf. 356 (ROOMVENT 2022). https://www.e3s-conferences.org/articles/e3sconf/pdf/2022/23/e3sconf_roomvent2022_03058.pdf | measured airflow with windows open | web summary |
| Lee 2016 (hood) | Lee Y.-G. Characteristics and Management of Particulate Matter from Kitchen Cooking in Apartment Buildings. Air Cleaning Technology 29(1), 2016. https://koreascience.kr/article/JAKO201654942433477.pdf | hood removes 80-90% of cooking PM2.5 | web summary |
| Lee 2017 (hood) | Lee M., Jeong M., Kang M. Characteristics and Management of PM2.5 Emission on Cooking Condition. JCCT 4(1), 2017. https://koreascience.kr/article/JAKO201810256456089.pdf | hood airflow stage 1 0.018 m3/s | web summary |
| Lim 2012 | Lim T. S., Lim H. S., Koo J.-O., Kim G. Assessment of the Daylighting Performance in Residential Building Units of South Korea through RADIANCE simulation. KIEAE J. 12(2), 2012. https://koreascience.kr/article/JAKO201230360544423.pdf | daylight factors per room | web summary |
| Chun & Bae 2005 | Chun C.-Y., Bae N.-R. A Study on Acceptable Thermal Comfort Zone and Resident Behavior of Operating Cooling Devices in Apartments. KJACR 17(5) 477-486, 2005. https://koreascience.kr/article/JAKO200520828120793.page | switch-on / switch-off room temperature | abstract |
| Yun 2020 | Yun et al. Indoor Thermal Environment Long-Term Data Analytics Using IoT Devices in Korean Apartments. IJERPH 2020. https://pmc.ncbi.nlm.nih.gov/articles/PMC7579249 | cooled / not cooled room temperature, summer indoor vs outdoor | web summary |
| Lee 2010 (airing) | Lee Y.-J. Characteristics of Behavior for Ventilation and Maintenance for Ventilation Equipments by Multi-family Housing Residents. J. Korean Housing Assoc. 21(5), 2010. https://koreascience.or.kr/article/JAKO201011949345964.pdf | airing counts, minutes, times | web summary |
| Cho & Choi 2013 | Cho J.-H., Choi Y.-J. The Indoor Thermal and Air Environment of General Apartment Houses during Winter in Cheongju City. KIEAE J. 13(3), 2013. https://kieae.kr/xml/01166/01166.pdf | winter airing | web summary |
| Yoon 2007 | Yoon J.-H., An Y.-S., Kim B.-S. 확장형 발코니 공동주택의 창호종류에 따른 결로 및 온열환경에 관한 연구. KIEAE J. 7(5) 87-92, 2007. https://koreascience.kr/article/JAKO200730360545457.pdf | clear double glazing integrated U 2.407 W/m2K | PDF (section 2.1, table 2) |
| Economist 2018 | The Economist, 2018-01-28, on Korean apartment balconies (URL not kept) | balconies within 1.5 m left out of the floor-area ratio | article, read 2026-11-22 |
| Jo 2011 | Jo D.-K., Yun C.-Y., Kim K.-D., Kang Y.-H. A Detail Survey of Horizontal Global Radiation and Hours of Bright Sunshine for the Installation of Solar Photovoltaic System in Korea. J. Korean Solar Energy Soc. 31(3), 2011. https://koreascience.or.kr/article/JAKO201128451816195.pdf | Seoul monthly horizontal irradiation (table 3) | web summary |
| Lee 2014 | Lee W.-J., Kang E.-C., Lee E.-J., Shin U.-C. A Study on the Calculation of Thermal Consumption Unit of Apartment. KJACR 26(8) 388-393, 2014. https://koreascience.kr/article/JAKO201428854482525.pdf | measured comparison (heating + hot water, built 1991-2008) | web summary |
| Jin 2019 | Jin H. S. et al. Analysis of annual EUIs by end-use in apartment units (2017-2018). E3S Web Conf. 111, 04013 (CLIMA 2019). https://www.e3s-conferences.org/articles/e3sconf/pdf/2019/37/e3sconf_clima2019_04013.pdf | heating / hot water split (71 Seoul flats) | web summary |
| Kim 2005 | Kim S.-M., Park B.-Y., Sohn J.-Y. Evaluation of the Performance and the Energy Consumption Characteristics of Heat Recovery Ventilators in Apartments, 2005. https://koreascience.or.kr/article/JAKO200520828120913.page | ventilator heat recovery 46% | abstract |
| Lee 2016 (vent.) | Lee E.-T. Regulations and Technology Trends of Ventilation Systems in Apartment Housing. Air Cleaning Technology 29(1) 32-42, 2016. https://koreascience.kr/article/JAKO201654942433481.pdf | 47.5% use the unit (Gallup 2011), reasons | web summary |
| Equipment rules art. 11 | Rules on Building Equipment Standards art. 11, annex 1-5 (commentary: nepla.ai, yugacrew.com) | 0.5/h ventilation, 60% filter | commentary pages, not the statute |
| Samsung service dryer | [Samsung dryer] dryer course functions. https://www.samsungsvc.co.kr/solution/1052607 | dryer standard course time (9 kg) | web summary |
| Flobul | Flobul/smartthings-capabilities (GitHub, 2026-05): 548 capability definitions fetched from the SmartThings API (328 standard) | device definition names | repository cloned and read |
| Winbush 2025 | Winbush A., McDuff D., Hernandez J., et al. Smartphone use in a large US adult population: Temporal associations between objective measures of usage and mental well-being. PNAS 122(43) e2427311122, 2025. https://doi.org/10.1073/pnas.2427311122 | unlocks and app time per person | full PDF (user) |
| Appiah 2026 | Appiah K. N., Adu N., Singh D. K. Using Fixed-Effects Panel Models to Assess Within-Person Variation in Smartphone Unlocks from Continuous Sensing. J. Technology in Behavioral Science, 2026. https://doi.org/10.1007/s41347-026-00691-7 | day-to-day variation (StudentLife 2013, 47 students); some internal inconsistencies noted | full PDF (user) |
| arXiv 2609.24477 | Beyond Screen Time: Demonstrating the Value of App Activity Logs to Understand User Behavior Further. arXiv 2609.24477 (2026), https://arxiv.org/html/2609.24477v1 | share of sessions under 40 s (Denmark, 13-17, iOS, 2024) | web page |
| Common Sense 2023 | Common Sense Media. Constant Companion: A Week in the Life of a Young Person's Smartphone Use. 2023. https://www.commonsensemedia.org/sites/default/files/research/report/2023-cs-smartphone-research-report_final-for-web.pdf | pickups (median 51), 4.5 h, notifications (US 11-17, 2022) | web summary |
| Hintze 2014 | Hintze et al., UbiComp 2014 (title and co-authors not checked). https://ins.jku.at/publications/2014/Hintze_2014_UbiComp.pdf | glances (locked use), session lengths | web summary |
| Bohmer 2011 | Bohmer M., Hecht B., Schoning J., Kruger A., Bauer G. Falling Asleep with Angry Birds, Facebook and Kindle. MobileHCI 2011. https://www.brenthecht.com/papers/bhecht_mobilehci2011_sleepbirds.pdf | apps per use, first and next app, app session 71.6 s | web summary |
| Device Analyzer 2017 | How to Measure Sessions of Mobile Device Use? arXiv 1711.09408. https://arxiv.org/pdf/1711.09408 | session definition (unlock to lock), sessions per day | web summary |
| Turner 2019 | Turner L. et al., Royal Society Open Science, 2019 (Cardiff University news): https://www.cardiff.ac.uk/news/view/1462214 | 87 app switches a day (53 people) | news page |
| Rana 2016 | https://www.cl.cam.ac.uk/~acr31/pubs/rana-smartphoneuse.pdf | app starts 38 a day, foreground median 88 min (Norway 2013-14) | web summary |
| Samsung timeout | Samsung UK support: How to stop your Galaxy phone screen going dark or timing out. https://www.samsung.com/uk/support/mobile-devices/how-to-stop-your-galaxy-phone-screen-going-dark-or-timing-out/ | default 30 s, max 10 min | web page |
| Samsung apps | Samsung Korea, preinstalled apps of SM-F966N. https://www.samsung.com/sec/consumer/mobile/Apps/SM-F966NDBEKOD/ | base app list | web page |
| WiseApp 2024-11 | MTN news 2024-12-17. https://news.mtn.co.kr/news-detail/2024121714574174615 | most used apps in Korea by monthly users and time | web page |
| WiseApp 2025 | Electronic Times 2025-12-30. https://m.etnews.com/20251230000083 | KakaoTalk and YouTube per user | web page |
| WiseApp 2025-04 | Newsspace. https://www.newsspace.kr/mobile/article.html?no=6969 | music app shares in Korea | web page |
| WiseApp 2024-05 | Newsis 2024-06-09. https://mobile.newsis.com/view/NISX20240609_0002765600 | app time and launches totals | web page |
| data.ai 2022 | Daum news 2022-05-16. https://v.daum.net/v/20220516134848801 | 5.2 h a day in Korea | web page |
| Gallup 2025 | Gallup Korea, kitchen/environment/health appliances ownership 2025. https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo=1595 | air conditioner 98%, purifier 66%, humidifier 39%, dishwasher 24%, oven 21% | web page |
| Gallup 2023 | Gallup Korea, Market70 2023 (7). https://www.gallup.co.kr/gallupdb/reportContent.asp?seqNo=1439 | washers, dryer 35%, robot vacuum 15%, TV 99%, AI speaker 18% | web page |
| AgentSense | AgentSense: Virtual Sensor Data Generation Using LLM Agents in Simulated Home Environments. AAAI. https://arxiv.org/abs/2506.11773 | related work: synthetic data validated on real HAR data | abstract |
| Tian 2021 | Tian Y., Zhou K., Pelleg D. What and How long: Prediction of Mobile App Engagement. ACM TOIS, 2021. https://arxiv.org/abs/2106.01490 | tap task time: weather-app use 33% / 67% quantiles 6 s / 23 s (section 3.3) | web summary (first 100k chars) |
| Starner 2004 | Starner T. E., Snoeck C. M., Wong B. A., McGuire R. M. Use of Mobile Appointment Scheduling Devices. CHI 2004 extended abstracts. https://faculty.cc.gatech.edu/~thad/p/030_20_DPP/chi04_use_of_mobile_appointment_scheduling_devices.pdf | input task time: PDA appointment total 37.7 s (Table 2) | web summary |
| Palin 2019 | Palin K., Feit A. M., Kim S., Kristensson P. O., Oulasvirta A. How do People Type on Mobile Devices? Observations from a Study with 37,000 Volunteers. MobileHCI 2019. https://www.repository.cam.ac.uk/items/809c909b-9301-4cad-955d-998bdce7e0e0 | input task time: mean 36.2 wpm | abstract |
| Android docs | Emulator console https://developer.android.com/studio/run/emulator-console ; netsim https://developer.android.com/studio/run/emulator-networking-advanced ; Android 10 privacy (clipboard) https://developer.android.com/about/versions/10/privacy/changes | emulator decision | web pages |

Not read (could not open): Ferreira et al. 2014 micro-usage (41.5%, only as cited in arXiv 2609.24477; its threshold not checked);
PMC11303118 (daily smartphone use and sleep, adolescents); Ohme et al. 2021 (iOS Screen Time data donations, abstract only).
