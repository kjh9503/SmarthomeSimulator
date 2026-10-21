# Prompt: rewrite patterns so the simulator can produce them (preprocessing)

Step before structuring. Input: rows of `realistic_patterns.txt` (columns 사용자, 패턴, 유형, 요약, 비고 =
personaId, patternId, patternType, text, note) plus each persona's houseType (assigned by build_rewrite_requests.py). Output: the same patterns rewritten so every device, sensor,
place, signal and action in them exists in the simulator, keeping each pattern as close to the original as
possible. The rewritten text then goes into the structuring prompt (../prompt_pattern_structuring.md).
Placeholders `{{...}}` are filled by build_rewrite_requests.py.

---------------------------------------------------------------------------------------------------
## SYSTEM

You edit behaviour patterns for a simulated person. A simulator produces one person's year of smart-home
device logs and phone logs; each person has 1-3 patterns that must be hidden in those logs so that a model can
later learn them. Many patterns were written for devices and data the simulator does not have. Rewrite each
pattern so that it can happen with ONLY what the simulator has (SIMULATOR CAPABILITIES below), while keeping
it as close to the original as possible.

### What to keep
- personaId, patternId and patternType: unchanged.
- The pattern's shape: its trigger (a time window or an event), its conditions, its branches ("if X ... ; if
  Y ...") and, for preference_shift, the old behaviour -> new behaviour.
- Times, days, places (Home, Office, Gym, Campus...), numbers and thresholds, unless a number belongs to
  something that no longer exists.
- Each row gives the persona's houseType. Use only rooms of that house type (2room has no room3, room4 or
  hallway; 3room has no room4) and only devices those rooms have.
- The style: one English sentence (or two for branches), the same voice as the original.

### What to change, and how
Change only what the simulator cannot produce. Prefer the first option that fits:

1. **A home device the simulator lacks** -> the simulator device with the same role, in a room that has it:
   - lights of any kind (ceiling, pendant, wall, mirror, under-cabinet, flood, hallway) -> `light` (on/off only);
     if brightness or colour matters -> `lamp` (level 0-100, colorTemperature 2700-6500 K; warm/amber about
     2700 K, neutral about 4000 K, cool about 5500-6500 K); lamps exist only in living_room and room1-4.
   - motion sensor -> `occupancy_sensor` presence; yard or garden -> `balcony`.
   - heater of any kind (floor, desk, bedroom heater) -> `heating_cooling_unit` heat with heatingSetpoint;
     air conditioner -> heating_cooling_unit cool with coolingSetpoint ("quiet mode" has no value: drop it).
   - dehumidifier -> heating_cooling_unit cool (cooling dries the air in the simulator) or opening a window.
   - ventilation fan, air circulator, drying fan -> `air_purifier` (living_room; fan speed percent 0-100, 0 = off) or
     opening a window (`window_contact`, living_room and room1-4).
   - humidifier settings -> `humidifier` (room1-4) switch + humiditySetpoint.
   - white-noise / sleep-sound / smart speaker -> `speaker` (living_room, room1, room2) play / volume;
     the sound itself (rain, brown noise...) can be named in the phone app that drives it.
   - kettle, coffee or espresso machine, rice cooker, cooktop -> `stove` (on/off) or `oven` (bake/convection,
     temperatureSetpoint, preheat), or the matching phone app if nothing at home fits.
   - door camera, two-way talk, guest access code -> the SmartThings app on the phone (open it; it shows a
     notification) plus the `doorbell` / `lock` / `door_contact` that already exist.
   - washer programs: washer modes are normal, quick, bedding; dryer modes normal, delicate, timeDry;
     dishwasher start or startHeatedDry. Map fabric / load types onto these modes (towels, bedding -> bedding;
     wool, delicates -> quick or dryer delicate; sportswear -> quick...). Only the dryer has errorCode.
2. **A device away from home (laptop dock, monitor, printer, scanner, tablet, pen, keyboard, webcam,
   projector, meeting-room display or sensor, desk fan or heater at the office, headphones)** -> what the
   phone itself can see: a Bluetooth connection (`Galaxy Buds` for headphones and headsets, `Car Audio` for a
   car), joining the place's Wi-Fi, an app opened on the phone and the notification it shows, a calendar
   event, or the place itself. A sensor reading at the office or campus (noise, temperature, occupancy)
   becomes a calendar block, a time window or a phone state.
3. **A value that only lives inside another system** (guest count, meeting format, package location, document
   type, unread e-mail count, queue wait, rain probability, forecast low temperature, spending amount...) ->
   carry it in the text of the event that brings it: a calendar event title ("Family dinner (6 guests)"), a
   notification's text ("Package left in the parcel locker", "Rain expected 70%"), or a message. Say which.
4. **A phone-internal setting or in-app action** (DND, low-power mode, brightness, alarm, timer, checklist or
   note item, playback speed, subtitles, template, zoom, queue order, focus profile) -> keep it as an action in
   a named app: the person opens that app and the app shows a notification describing the result
   ("Low power mode on", "Timer 12:00 started", "Checklist: umbrella added"). Name a realistic Android app;
   if it is not already installed, add it to `newApps` (package and label).
5. **A signal the phone cannot receive** (e.g. a smart kettle reporting waterReady) -> the nearest signal the
   simulator has (a calendar reminder, a SmartThings alert, a home device state, an app opened, a time window).

If a pattern still cannot be made to work without losing what makes it that pattern, write a NEW pattern of
the same patternType, in the same area of life (same place, same time of day, similar devices), and mark it
"replaced".

The `note` column (비고) describes decoy fields in the same log ("the condition is sleep time; the same log also
has beanHopperPercent, waterLevelMl"). Keep its meaning: rewrite the note so the decoys are values that exist
in the simulator (in the same record or event) and the real condition stays named. If there is no note, output "".

Do not make two patterns of the same persona identical. Patterns of different personas may be alike.

### Output
Return exactly one JSON array, one object per input row, in input order, nothing else:
```
{
  "personaId": "<unchanged>",
  "patternId": "<unchanged>",
  "patternType": "<unchanged>",
  "originalText": "<the input text>",
  "text": "<the rewritten pattern, English>",
  "note": "<rewritten note, or \"\">",
  "changeLevel": "unchanged | minor | substituted | replaced",
  "changes": [ { "from": "<original part>", "to": "<what replaced it>", "reason": "<why, short>" } ],
  "newApps": [ { "package": "<android package>", "label": "<app name>" } ]
}
```
changeLevel: unchanged = text kept as is; minor = only names, units or wording adjusted (e.g. illuminanceLux ->
illuminance, Away kept); substituted = a device, signal or value source swapped as above; replaced = a new pattern.
`changes` lists every change (empty only when unchanged). `newApps` lists apps the rewritten text uses that are
not in the installed list (empty if none).

### SIMULATOR CAPABILITIES
{{CAPABILITIES}}

### EXAMPLES (made up; use them for the form)
```json
{{EXAMPLES_JSON}}
```

---------------------------------------------------------------------------------------------------
## USER

Rewrite these rows (CSV header: personaId, houseType, patternId, patternType, text, note):
```csv
{{PATTERN_ROWS}}
```
Return a JSON array with one object per row, in the same order, and nothing else.
