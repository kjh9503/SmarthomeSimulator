#!/usr/bin/env python3
"""Write simulator_capabilities.md: a short, readable list of what the simulator has, made from ../vocabulary.json
(so the rewrite prompt always matches the simulator). usage: python3 make_capabilities.py"""
import json, os
HERE = os.path.dirname(os.path.abspath(__file__))
v = json.load(open(os.path.join(HERE, "..", "vocabulary.json"), encoding="utf-8"))
L = []
L.append("## Home (one person, one house)")
hts = {k: x for k, x in v["houseTypes"].items() if not k.startswith("_")}
for k, x in hts.items(): L.append(f"- {k}: rooms {', '.join(x['rooms'])}")
L.append("- room1..room4 can play any role (bedroom, study room, nursery, kids' room, home office); balcony is outdoors.")
L.append("")
L.append("## Home devices (device type: rooms | capability.attribute values | commands)")
for t, d in v["deviceTypes"].items():
    caps = []
    for c in d["capabilities"]:
        for a in c["attributes"]:
            val = "|".join(map(str, a["values"])) if "values" in a else (f"{a['type']}" + (f" {a['unit']}" if a.get("unit") else "") + (f" {a.get('min')}-{a.get('max')}" if a.get("min") is not None else ""))
            caps.append(f"{c['capability']}.{a['name']}={val}")
        if c["commands"]: caps.append("cmd " + ", ".join(f"{m['name']}({', '.join(m['args'])})" for m in c["commands"]))
    extra = f" | washer modes: {', '.join(d['modes'])}" if d.get("modes") else ""
    L.append(f"- {t}: {', '.join(d['rooms'])} | " + "; ".join(caps) + extra)
L.append("")
L.append("## Home device alerts the phone receives (SmartThings app notifications)")
L.append("- " + ", ".join(f"{a['category']} ({a['device']})" for a in v["smartThingsAlerts"]))
L.append("")
L.append("## Places outside home")
cats = {}
for k, p in v["places"].items(): cats.setdefault(p["category"], []).append(k)
for c, ks in cats.items(): L.append(f"- {c}: {', '.join(ks)}")
L.append("- Away = any place other than home. Trips between places take time; travel modes: " + ", ".join(v["travelModes"]))
L.append("")
L.append("## The person's phone")
L.append("- Things the phone receives: messenger/app notifications (any app, any text), calls ringing or missed, incoming SMS, calendar reminders at an event's start, SmartThings alerts above, weather-app notifications (rain expected / rain started / clear), hourly health (steps, distance, kcal, heart rate).")
L.append("- Calendar events: title, start, end, location (any text). Values a pattern depends on (guest count, meeting format, pickup place, document type...) can live in an event title or in a notification's text.")
L.append("- Phone states: screen on/off, charging, battery %, activity (" + ", ".join(v["activities"]) + "), asleep, music playing/paused (phone), Bluetooth (" + ", ".join(v["bluetoothDevices"]) + "), Wi-Fi network, app in the foreground.")
L.append("- Health: measures " + ", ".join(v["healthMeasures"]) + "; exercises " + ", ".join(v["exercises"]) + " (with durationMinutes); SLEEP record with durationMinutes on waking.")
L.append("- Person's phone actions: open/close any app, the app then shows a notification describing the result (navigation started, item added to a checklist, timer started, setting changed); play/pause/stop phone music; add/change/delete calendar events; calls, SMS, photos, screenshots, clipboard; connect/disconnect Bluetooth; plug in/unplug; sleep/wake; start/end exercise; record health measures; control any home device from the SmartThings app.")
L.append("- Apps already installed: " + ", ".join(f"{lab} ({pkg})" for pkg, lab in v["apps"].items()) + ". Other realistic Android apps may be named (give package and label).")
L.append("")
L.append("## Outdoors")
L.append("- Weather: " + ", ".join(v["weather"]["states"]) + "; outdoor " + ", ".join(f"{k} ({u})" for k, u in v["weather"]["outdoorVariables"].items()) + ". Seoul climate.")
open(os.path.join(HERE, "simulator_capabilities.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("simulator_capabilities.md:", len("\n".join(L)), "chars")
