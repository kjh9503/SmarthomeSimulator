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
2a. Balcony: outer window sensor and pairing with the living room window done 2026-11-23 (063 Jul / Aug living room
   26.6 / 27.3 C). Open: AC on -> inner side closed for all; laundry inside while the AC runs (personal); laundry
   brought in during heating; outer window left open when leaving in summer (personal); short airing while heating or
   cooling; glazing of Korean non-expanded balconies (single or
   double) not checked. Balcony parameters (U 2.4 only
   from a source; SHGC 0.5 since 2026-11-23 (0.7 was glass-only and gave 33.9 C in January; now 19.6 C max,
   January median 11.9 K above outdoors, Shanghai / Nanjing closed balconies +5.7 / +6.1 K, glazing not stated); 0.7 sun into the living room, 1.0 air change an hour, area from sqrt(living area), 35%
   daylight at its sensor) are assumptions; January balcony 15.6 C median at -1.1 C outdoors and up to 33.6 C on sunny
   days, no Korean measurements found to compare.
3. Humidifier: `humidifierMode` auto / low / medium / high instead of `humiditySetpoint` (agreed 2026-11-04, not built);
   the effect of each mode on room humidity is still to decide.
4. "Cooling at 100% RH" seen earlier: not reproduced (85-90% at 16 C on three older commits); where it came from is
   unknown. Deferred by the user.
5. The measured summer figures used for comparison (Yun et al. 2020: indoor 26.6 C, outdoor 23.6 C) cover a "summer"
   whose months were not checked, so the comparison with our Jul-Aug may not be like for like.
6. Winter humidity: 063 is at 13% in January (one person in 84 m2, ventilation unit always on, airing twice a day);
   measured winter means are 36.6% (households 19.5-58.5%). Not yet compared with a family-sized household.
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
