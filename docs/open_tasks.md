# Open tasks (agreed to come back to)

Rewritten 2026-11-21: finished items removed (their record is in docs/agent_design_notes*.md, section 12).

## House physics

1. Outdoor daylight lux (done 2026-11-21): now the calibrated global irradiance x 110 lux per W/m2 instead of
   25,000 lux x sin altitude (about a quarter of real). Indoor light keeps the window factors (living room 3%, rooms 2%,
   ...), which match the simulated daylight factors of Seoul flats (living room 2-5%, bedrooms 0.5-1.5%, kitchen 0.2%;
   Lim et al. 2012). 063: midday living room 151 -> 768 lux (Jan), 277 -> 1019 lux (Jul); room1 about 710 lux; entryway
   about 90 lux; light switch-ons per year changed little (living room 278 -> 259, entryway 282 -> 249). Open: the
   110 lux per W/m2 factor has no checked source; the kitchen (small window, 1.2%) is above the simulated 0.2%.
2. Vapour above saturation (done 2026-11-21 for racks): laundry on a rack now dries only as fast as the room air takes
   the water; the rest stays in the clothes. Showers and other sources still drop what the air cannot hold (it
   condenses and runs off). Racks moved to a real balcony (flats of 84 m2 and more) or the living room, with checks and
   drying actions (done 2026-11-22; 063: 29 racks taken in 10-25 h after hanging, was about 96 h).
2b. Contact sensors (2026-11-23): balcony door sensor removed (no sensor on doors people walk through, as room doors;
   physics kept) and merged with the living room window: in a flat with a real balcony that window is the one sliding
   glass door onto the balcony; open, it swaps air both ways with the balcony as a door-height opening of half its glass
   (Brown & Solvason, buoyancy only). 063 Jul / Aug living room 27.8 / 28.6 C (26.6 / 27.3 with the earlier one-way
   window flow). Window sensors per household done the same day: profile windowSensors {rooms, reason}, chosen by the LLM;
   other windows open and close without a line (physics unchanged); entry door for everyone. 063: living room only.
2c. Order of things in the log (2026-11-23, tools/check_order.py): rooms skipped fixed (walking). Open, agreed order:
   (2) balcony entered / left through a closed living room window: fixed (sliding door opened and closed); found:
   idle time filled with activities from a pool (2026-11-24); open: long lognormal tails (TV 5.3 h), activity
   weights have no data (time-use microdata from MDIS would give episode lengths);
   the person stays where an errand left them and falls asleep wherever they are: fixed by layer A (home base,
   2026-11-24); layers B-D of the blueprint wait for layer A's results (open: background rules vs ground truth, one
   shared random stream);
   (3) lines written ahead of the engine clock: front door on arrival fixed 2026-11-24; app tasks outside
   rules (F2 / F3 / F4); (4) steps of moves in the first minute of an hour go to the hour before (M10, phone.py
   (t - MIN_MS)). 0 s stays were not short visits: 1,001 of 1,166 were the engine sending the person to the balcony and back in the
   same second, and after walking 820 of 821 were actions piled up at :59; both fixed (walking, carry-over). Falling
   asleep in the living room (1 a year) is not an error (agreed).
2a. Balcony: outer window sensor and pairing with the living room window done 2026-11-23 (063 Jul / Aug living room
   26.6 / 27.3 C). Open: AC on -> inner side closed for all; laundry inside while the AC runs (personal); laundry
   brought in during heating; outer window left open when leaving in summer (personal); short airing while heating or
   cooling; glazing of Korean non-expanded balconies (single or
   double) not checked. Balcony parameters (U 2.4 only
   from a source; SHGC 0.5 since 2026-11-23 (0.7 was glass-only and gave 33.9 C in January; now 19.6 C max,
   January median 11.9 K above outdoors, Shanghai / Nanjing closed balconies +5.7 / +6.1 K, glazing not stated); 0.7 sun into the living room, 1.0 air change an hour, area from sqrt(living area), 35%
   daylight at its sensor) are assumptions. January checked 2026-11-26, not an error: where the balcony sits between the
   room and outdoors, (balcony - outdoor) / (room - outdoor), ours 0.43-0.49 (Jan median; 21-10 h 0.42-0.47, p10-p90
   0.34-0.59). Seo et al. 2007 (KJACR 19(5), Uiwang, 2005-01-24/25 21:00-10:30, empty flat, bedroom heated to 24 C,
   outdoor -2 to 2 C): balcony air about 8-10 C read from fig. 6, balcony surfaces 10.1-13.7 C, balcony MRT 12.1 C
   (table 5, 6) -> about 0.35-0.5; Shanghai closed balcony 0.46 (Frontiers 2022, table 5). The earlier "+5.7 / +6.1 K"
   comparison in kelvin was not like for like (their outdoor 5-6 C, rooms 11-18 C).
3. Humidifier: `humidifierMode` auto / low / medium / high instead of `humiditySetpoint` (agreed 2026-11-04, not built);
   the effect of each mode on room humidity is still to decide.
4. "Cooling at 100% RH" seen earlier: not reproduced (85-90% at 16 C on three older commits); where it came from is
   unknown. Deferred by the user.
5. (resolved 2026-11-25) Yun et al. 2020's "summer" is June-August.
6. Winter humidity (2026-11-26): physics part closed. Ours Jan living room 14-17% vs measured 35-50%. With 4-6 kg/day of
   moisture (ours about 1.7) the physics reaches the measured range (office: 4 kg with the ventilation unit off 40.8%,
   6 kg with it 42.5%). Not a one-person effect (one-room student flats, mostly one person: 54.3% mean, Choi & Kim 2010;
   occupant number no effect on moisture excess, Vinha et al. 2018). Moved to the persona list: cooking times (0.7-0.8 a
   day vs three meals, 871 g a day, Choi et al. 2020), dryer share 55-85% so racks 0.14-0.32 kg/day (indoor drying 1.22
   kg/day a person measured, Zemitis et al. 2016), ventilation unit use (063 always on). Open without measured data:
   hand dishwashing, floor mopping, plants (BS 5250 values only); re-evaporation from bathroom surfaces after a shower
   (the air's excess is deleted, 404-464 g/day; adding it all back is about +1-3 %p by interpolation, not run).
6c. Summer remote +5.2 K over outdoors (Jun-Aug; 063 / office / retiree +2.0 / +2.5 / +3.3; Yun et al. 2020 +3.0 with
   AC and windows in use). Checked 2026-11-26: remote never cools, never opens a window for heat, airs 0 times a day and is
   home 93% (habits drawn by tools/make_test_profiles.py) -> persona list (combination of habits). Physics: no measurement
   of a closed flat without AC found. Ham, Lee & Kim 2024 (Sustainability 16(22) 9831; Chuncheon, Gwangju, heatwave
   days 2022, windows not controlled): non-AC pre-2000 flats 29.5-32.3 C, mean 30.3, outdoor daily mean 28.0-29.3 ->
   about +1-2 K; ours on our 10 hottest days (outdoor mean 26.5): 063 (windows open 55%, no AC) +1.4 K, remote (closed)
   +4.2 K. Found on the way: our 2026 weather had no day at 33 C or above -> fixed 2026-11-26 (day-to-day anomaly; design
   notes "Weather: day-to-day temperature"); remote on the 10 days at 33 C: +0.5 K over the outdoor mean.
6b. (checked 2026-11-26, not an error) Open-window cooling "faster than measured" compared a 14 m2 living room with a
   window half open (2.8 m2, about 48 /h, at the 0.8 a minute cap) with Fitzner & Finke 2012's 180 m3 office (6.3 m2
   open, 12.5 /h). Our physics on their room (80 m2, six 0.71 x 1.48 m sashes, 21 C flat, 6.9 C outdoors): CO2
   difference halves in 4 min (measured about 3), air change 15 -> 7 /h falling as the room cools (measured 10-14 /h,
   about constant), temperature difference 13.9 -> 8.1 K in 14 min, not halved (measured halved in about 7 min); the
   formula gives about 18 /h at their 14 K. Open: how wide people open windows (we open half the glass every time;
   habitual openings measured 0.8-3 /h: Beijing bedrooms over 3 cm, Liu et al. 2022; Finnish rooms, Kayo & Suzuki 2023;
   Danish bedrooms at night, Fan et al. 2022).
7. Device reservations (timers) for air conditioner, purifier, TV: not built, no SmartThings definition found; 7 items
   listed in the conversation of 2026-11-04.
8. Wifi router `connectedDevices` is our own attribute name: to be marked in the docs (agreed, not done).

## Person behaviour

9. Laundry happens about half as often as drawn (063: 2 a week drawn, 57 washes a year): a wash slot (weekend morning,
   weekday evening) is skipped when the person is not home, not moved to another day.
10. Music pause, health entry, exercise: the choice "with the app or without" (agreed to be a probability), not built.
11. Phone use statistics differ from the literature: one-app uses about 83% (Bohmer et al. 2011: 68.2%), uses under 5 s
    about 9% (49.8%); app time reaches 94-97% of the drawn target. Not changed.
12. App tap task time has a long tail (median 12 s, up to the 600 s cap): check whether it looks right.

## Making the data (LLM steps)

13. Calendar events: to come from the persona / scenario (agreed 2026-10-22); there is no persona material yet
    (`pipeline/personas.csv` notes are empty). `phone.calendarAdd` cannot say "next Tuesday 10:30"; prerequisites in the
    structured patterns are not executed.
14. Incoming phone events: the simulator can post notifications, ringing calls and SMS, but nothing triggers them.
    To decide: agent actions or an outside source like the weather.
15. Time-of-day and seasonal probabilities: sources not looked for yet (deferred in October).
16. 063 is a partial profile (written to test one pattern): everyday behaviour was missing (cooling, laundry), now partly
    covered by the habits. A full LLM-written profile has not been tried end to end.

## On hold

- Browser JS simulator (`browser/smarthome-sim.html`): not maintained until the user asks; it still has the old appliance
  capabilities, and its daylight no longer matches (the parity test skips daylight).
- Master bathroom: no rule in 063 uses it (only sensor lines).
- Very short uses from a profile's own distributions; a second action too soon from another path; reverts of one rule
  acting on a device another rule changed since.
- Wrong skips from deferred departures (agreed not a problem, 2026-11-04).
