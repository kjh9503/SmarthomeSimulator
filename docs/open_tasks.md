# Open tasks (agreed to come back to)

## Calendar events from persona and scenario (2026-10-22)

Where we are:
- `phone.calendarAdd` writes exactly what the profile says (title, begin, durationMinutes, location); nothing invents events.
- `begin` is "HH:MM" of the day the step runs, or an epoch ms number: no way to say "next Tuesday 10:30".
- The structuring prompt makes a `calendar` prerequisite for every calendar condition, but the runner does not execute
  prerequisites, so no event is created unless a routine adds it. Profile 063 has no calendar events.
- No persona descriptions exist yet: `pipeline/personas.csv` notes are empty and `input/realistic_patterns.txt` has only
  pattern sentences (119 lines mention calendar / meeting / lecture / deadline / class / shift / appointment / schedule).
  063's "student living alone" is an assumption made while writing the profile.

Agreed direction (user, 2026-10-22): event titles and contents should come from the persona / scenario.
Two kinds of events to produce, both in the persona -> routines LLM step (LLM 3):
1. events a pattern needs: the condition's word in the title, values (guests, duration, type) varying so the condition
   holds on some days and not others;
2. ordinary events from the persona (classes, deadlines, appointments, friends) that hide the pattern's events.

Open questions:
- Is there persona / scenario material, or should an LLM first write a persona from the patterns?
- Engine: allow future dates in `begin` (e.g. weekly class times) and decide whether `calendar` prerequisites run
  directly or are always written as routines.

## Phone screen and app use: what is not done yet (2026-10-28)

Done in the Python engine: `phone.useApps` (apps in a row), screen on when a phone use starts, screen off by hand
(`phoneHabits.manualScreenOff`) or after `screenTimeoutSeconds`, glances at the lock screen (`glancesPerDay`).
Not done yet:
- The JS runner (`tools/js/run_agent.js`) and the browser page do not have `phone.useApps`, the screen model or glances.
- Short app uses: in 063 only 3.7% of app uses are under 5 s; Bohmer et al. 2011 report 49.8% of uses under 5 s
  (their unit is a chain of apps, ours a single app, so the numbers are not the same measure).
- Opening the app before using it (SmartThings before app control, Calendar, Phone, Messages, Camera): agreed, not built.
- Music pause, health entry, exercise: the choice "with the app or without" (agreed to be a probability), not built.
- Glances do not follow notifications yet (there are no incoming notifications, see below).

## Incoming phone events (2026-10-22)

The simulator can post incoming notifications, ringing calls and incoming SMS, but nothing triggers them: the agent's
actions are the person's own actions. KakaoTalk messages have no action of their own (only app use). To decide: make them
agent actions or an outside source like the weather.
