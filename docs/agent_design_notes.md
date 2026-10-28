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

- No minimum interval exists in the engine. Measured [ours]: most short on->off gaps come from one rule (hall light,
  cooking). Collisions between paths: morning window opened and closed by the leaving check within 0.1 min (3 times),
  heating on and off by the leaving check within 60 min (15 times).
- Agreed split: (a) the second action too soon -> a gap-dependent probability, the same for pattern and routine
  actions, never inside a duration the pattern itself sets; (b) the first action unsuited to someone about to leave or
  sleep -> not solved by gap probabilities. Both are open.

## 7. Steps before an operation

Two criteria (agreed): (1) make a preceding step only if it leaves a log line; (2) if there is only one way to do it,
the engine adds it automatically (no probability); if there are several ways, the profile chooses with a probability.

| Operation | Preceding step (log line) | Ways | Decision |
|---|---|---|---|
| home device from the app | SmartThings in front | one | automatic (not built yet) |
| calendar add / change / delete | Calendar in front | one (other apps not considered) | automatic (not built) |
| outgoing call / SMS / photo | Phone / Messages / Camera in front | one | automatic (not built) |
| health entry, exercise, music play/pause | app in front or none (device, watch, earbuds, notification) | several | probability (not built) |
| screenshot, clipboard | some app in front | | the app in front, else a random installed one |
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
Agreed to be problems; not fixed yet: immediate response timing, pattern-only values, apps not opened before app use.

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

- Python port equals the JS simulator: outdoor values within 1e-12, physics within 1e-15 (`tests/test_port.py`).
- 2026 weather vs climate normals [ours]: monthly max/min temperature within 0.9 C, PM within 1.2 ug/m3, 86 wet days
  vs 79.3, 1,509 mm vs 1,418 mm.
- Cooling and heating work in the physics: Aug living room 30.2 -> 24.0 C in 20 min (cool, setpoint 24);
  Jan 15.0 -> 22.0 C in 30 min (heat, setpoint 22) [ours].
- Phone log only (no separate home log); SMARTTHINGS copies stored without derivable fields, `expand()` restores them
  byte-exact.

## 13. Open tasks

See `docs/open_tasks.md`: calendar events from persona, incoming phone events (messages, calls), opening apps
before use, method choice for music/health/exercise, JS runner without the phone model, pattern-only cues and
immediate response timing, gap-dependent off probabilities, persona -> daily-life base list.

## References

| Short name | Reference | Used for | Read |
|---|---|---|---|
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
| Android docs | Emulator console https://developer.android.com/studio/run/emulator-console ; netsim https://developer.android.com/studio/run/emulator-networking-advanced ; Android 10 privacy (clipboard) https://developer.android.com/about/versions/10/privacy/changes | emulator decision | web pages |

Not read (could not open): Ferreira et al. 2014 micro-usage (41.5%, only as cited in arXiv 2609.24477; its threshold not checked);
PMC11303118 (daily smartphone use and sleep, adolescents); Ohme et al. 2021 (iOS Screen Time data donations, abstract only).
