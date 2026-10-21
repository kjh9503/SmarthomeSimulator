# JavaScript runner vs Python runner: profile 063, 365 days

Made with `python3 tools/compare_runs.py` on 2026-10-21. JS seed 63 and JS seed 64 show how much two runs of the same
profile differ by chance; the Python run (seed 63, Python random numbers) should fall in the same range.

| item | JS seed 63 | JS seed 64 | Python seed 63 |
|---|---|---|---|
| home lines | 303451 | 298742 | 302151 |
| phone events | 360438 | 355899 | 359464 |
| home source=command | 3924 | 3807 | 3968 |
| home source=device | 2359 | 2008 | 2270 |
| home source=manual | 1428 | 1382 | 1438 |
| home source=sensor | 295740 | 291545 | 294475 |
| phone type=ACTIVITY | 6134 | 6106 | 6304 |
| phone type=APP_USAGE | 27094 | 27262 | 27080 |
| phone type=CONNECTIVITY | 1608 | 1624 | 1648 |
| phone type=DATA_USAGE | 11096 | 11118 | 11203 |
| phone type=DEVICE_STATE | 1459 | 1458 | 1458 |
| phone type=HEALTH | 9139 | 9133 | 9144 |
| phone type=MEDIA | 412 | 424 | 436 |
| phone type=SMARTTHINGS | 303496 | 298774 | 302191 |
| person actions on air_purifier | 54 | 54 | 54 |
| person actions on curtain | 440 | 401 | 428 |
| person actions on dishwasher | 90 | 64 | 80 |
| person actions on door_contact | 1208 | 1184 | 1244 |
| person actions on lamp | 208 | 178 | 196 |
| person actions on light | 1716 | 1712 | 1764 |
| person actions on lock | 604 | 592 | 622 |
| person actions on stove | 496 | 482 | 492 |
| person actions on tv | 316 | 324 | 332 |
| person actions on window_contact | 220 | 198 | 194 |
| sleep mean | 7.84 | 7.85 | 7.81 |
| steps mean | 187.02 | 185.7 | 192.1 |
| hr mean | 65.33 | 65.29 | 65.38 |
| saved living_room fineDustLevel mean | 19.08 | 18.95 | 18.99 |
| saved living_room temperature mean | 19.7 | 19.77 | 19.62 |
| saved room1 carbonDioxide mean | 1151.49 | 1158.07 | 1142.04 |
| saved living_room illuminance mean | 110.09 | 115.53 | 112.64 |
| p63_a followed | 26 | 24 | 26 |
| r_arrive_home followed | 282 | 277 | 296 |
| r_arrive_music_off followed | 206 | 212 | 218 |
| r_bedtime followed | 363 | 360 | 362 |
| r_bedtime_late followed | 4 | 6 | 4 |
| r_campus_home followed | 190 | 184 | 201 |
| r_campus_to_library followed | 33 | 41 | 28 |
| r_commute_music followed | 206 | 212 | 218 |
| r_curtain_close followed | 220 | 200 | 214 |
| r_dinner followed | 129 | 106 | 133 |
| r_evening_tv followed | 158 | 162 | 166 |
| r_friday_back followed | 9 | 11 | 14 |
| r_friday_out followed | 9 | 11 | 14 |
| r_library_home followed | 34 | 41 | 28 |
| r_morning followed | 335 | 325 | 327 |
| r_phone_use followed | 14259 | 14274 | 14142 |
| r_purifier_weekend followed | 14 | 15 | 14 |
| r_study_evening followed | 104 | 89 | 98 |
| r_sunday_run followed | 14 | 8 | 19 |
| r_to_campus followed | 232 | 236 | 243 |
| r_wake_weekday followed | 261 | 261 | 261 |
| r_wake_weekend followed | 104 | 104 | 104 |
| r_weekend_back followed | 55 | 52 | 49 |
| r_weekend_out followed | 56 | 52 | 49 |
| r_window_evening_cold followed | 7 | 7 | 15 |
| r_window_evening_warm followed | 50 | 53 | 45 |
| r_window_morning followed | 53 | 39 | 37 |
| check bedtime turnedOff/leftOn | 112/5 | 112/7 | 125/4 |
| check leaving turnedOff/leftOn | 20/0 | 22/0 | 13/0 |
| check morning turnedOff/leftOn | 4/0 | 4/2 | 3/1 |
| cooking median / p90 min | 9/26 | 8/19 | 9/27 |
