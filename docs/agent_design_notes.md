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
