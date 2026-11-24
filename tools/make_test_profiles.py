#!/usr/bin/env python3
"""Write three TEST profiles (no hidden patterns) to check engine behaviour across lifestyles (2026-11-24).

usage: python3 tools/make_test_profiles.py   -> profiles/test_office.json, test_remote.json, test_retiree.json

Not benchmark personas: no PATTERNS, routines written by hand (Claude in the LLM's role) in the form of the
prompt's rule templates, reusing 063's routine forms where the life is the same (wake, morning, arrival, dinner,
TV, phone use, bedtime). Habit ranges are written here and drawn by the pipeline samplers afterwards
(tools/make_test_profiles.sh). No data behind any persona choice.
"""
import copy, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
BASE = json.load(open(os.path.join(ROOT, "profiles", "063.json"), encoding="utf-8"))
R = {b["id"]: b for b in BASE["behaviours"]}
rng = lambda a, b: {"min": a, "max": b}
HOME = {"kind": "place", "op": "is", "place": "home"}
AWAKE = {"kind": "phone_state", "field": "asleep", "op": "==", "value": False}


def keep(*ids):
    return [copy.deepcopy(R[i]) for i in ids]


def travel(id_, desc, window, days, frm, to, mode, prob, extra_cond=()):
    b = {"id": id_, "kind": "routine", "description": desc, "trigger": {"kind": "daily", "window": window},
         "conditions": [{"kind": "place", "op": "is" if isinstance(frm, str) else "in", "place": frm}] + list(extra_cond),
         "actions": [{"do": "person.travel", "args": {"to": to, "mode": mode}}], "probability": prob, "maxPerDay": 1}
    if days:
        b["trigger"]["days"] = days
    return b


def wake(id_, window, days):
    b = copy.deepcopy(R["r_wake_weekday"])
    b["id"], b["trigger"]["window"] = id_, window
    if days:
        b["trigger"]["days"] = days
    else:
        b["trigger"].pop("days", None)
    return b


def bedtime(window):
    b = copy.deepcopy(R["r_bedtime"])
    b["trigger"]["window"] = window
    return b


def stay(id_, desc, window, days, room, minutes, prob, device=None):
    """go to a room for a while (work block, reading...), lamp on while there"""
    acts = [{"do": "person.moveRoom", "args": {"room": room}}]
    if device:
        acts.append({"do": "home.command", "args": {"device": device, "capability": "switch", "command": "on", "args": [],
                                                    "channel": "physical"}})
    acts.append({"do": "wait", "args": {"minutes": minutes}})
    if device:
        acts.append({"do": "home.command", "args": {"device": device, "capability": "switch", "command": "off", "args": [],
                                                    "channel": "physical"}})
    b = {"id": id_, "kind": "routine", "description": desc, "trigger": {"kind": "daily", "window": window},
         "conditions": [HOME, AWAKE], "actions": acts, "probability": prob, "maxPerDay": 1}
    if days:
        b["trigger"]["days"] = days
    return b


def common(p):
    for k in ("heatingRanges", "ventilationRanges", "coolingRanges", "windowRanges", "hoodRanges", "showerRanges",
              "laundryRanges", "dryingRanges", "cookingMinutes"):
        p[k] = copy.deepcopy(BASE[k])
    p["simulation"] = {"startDate": "2026-01-01", "days": 365, "seed": p.pop("_seed")}
    p["start"] = {"place": "home", "room": "room1", "asleep": True, "battery": 100}
    return p


def hb(wd, we, stay_, errand, sofa):
    return {"weekdays": wd, "weekends": we, "stayMinutes": stay_, "errandMinutes": errand, "sofaSleepShare": sofa}


office = common({
    "personaId": "test_office", "_seed": 901, "houseType": "2room", "variant": "2room-A",
    "roomRoles": {"bedroom": "room1", "study_room": "room2"}, "phoneUseLevel": "medium",
    "notes": "TEST profile (no patterns): office worker in his 30s living alone, out 08-19 on weekdays, cooks some "
             "evenings, TV, weekend outings. Written by hand to test the engine; no data behind the choices.",
    "windowSensors": {"rooms": [], "reason": "A renter who never bought window sensors."},
    "homeBaseRanges": hb(
        {"morning": {"bedroom": rng(0.5, 0.8), "kitchen": rng(0.1, 0.2), "living_room": rng(0.1, 0.2)},
         "day": {"living_room": rng(0.4, 0.6), "bedroom": rng(0.3, 0.5)},
         "evening": {"living_room": rng(0.5, 0.7), "bedroom": rng(0.2, 0.4), "study_room": rng(0.0, 0.1)},
         "night": {"bedroom": rng(0.7, 0.9), "living_room": rng(0.1, 0.3)}},
        {"morning": {"bedroom": rng(0.6, 0.9), "living_room": rng(0.1, 0.3)},
         "day": {"living_room": rng(0.4, 0.7), "bedroom": rng(0.2, 0.4), "study_room": rng(0.0, 0.2)},
         "evening": {"living_room": rng(0.5, 0.7), "bedroom": rng(0.2, 0.4)},
         "night": {"bedroom": rng(0.7, 0.9), "living_room": rng(0.1, 0.3)}},
        rng(40, 100), rng(1, 4), rng(0.05, 0.15)),
    "behaviours": [wake("r_wake_weekday", {"from": "06:40", "to": "07:20"}, "weekdays"),
                   wake("r_wake_weekend", {"from": "08:30", "to": "10:30"}, "weekends")]
    + keep("r_morning", "r_commute_music", "r_arrive_music_off")
    + [travel("r_to_office", "Weekday trip to the office.", {"from": "07:40", "to": "08:20"}, "weekdays", "home", "office",
              {"choice": ["subway", "bus"], "weights": [0.7, 0.3]}, 0.97, [AWAKE]),
       travel("r_office_home", "Home from the office.", {"from": "18:20", "to": "20:00"}, "weekdays", "office", "home",
              {"choice": ["subway", "bus"], "weights": [0.7, 0.3]}, 1),
       travel("r_friday_out", "Some Fridays: drinks after work.", {"from": "18:00", "to": "18:30"}, ["fri"], "office",
              {"choice": ["restaurant", "bar"]}, "subway", 0.35),
       travel("r_friday_back", "Home late on Friday.", {"from": "21:30", "to": "23:40"}, ["fri"], ["restaurant", "bar"], "home",
              {"choice": ["subway", "taxi"], "weights": [0.6, 0.4]}, 1),
       travel("r_weekend_out", "Weekend outing.", {"from": "11:00", "to": "15:00"}, "weekends", "home",
              {"choice": ["cafe", "mall", "cinema", "friend_home", "gym"], "weights": [3, 2, 1, 2, 2]}, "subway", 0.6, [AWAKE]),
       travel("r_weekend_back", "Home from the weekend outing.", {"from": "16:30", "to": "21:40"}, "weekends",
              ["cafe", "mall", "cinema", "friend_home", "gym"], "home", "subway", 1)]
    + keep("r_arrive_home", "r_curtain_close", "r_dinner", "r_evening_tv", "r_phone_use")
    + [bedtime({"from": "23:30", "to": "00:40"})] + keep("r_bedtime_late")})

remote = common({
    "personaId": "test_remote", "_seed": 902, "houseType": "3room", "variant": "3room-B",
    "roomRoles": {"bedroom": "room1", "study_room": "room2"}, "phoneUseLevel": "medium",
    "notes": "TEST profile (no patterns): software developer in her 30s working from home, works in the study room "
             "on weekdays, lunch in the kitchen, gym some evenings. Written by hand to test the engine; no data.",
    "windowSensors": {"rooms": ["living_room"], "reason": "One sensor on the living-room window from a starter kit."},
    "homeBaseRanges": hb(
        {"morning": {"bedroom": rng(0.4, 0.7), "kitchen": rng(0.1, 0.3), "living_room": rng(0.1, 0.3)},
         "day": {"study_room": rng(0.6, 0.8), "living_room": rng(0.1, 0.3), "kitchen": rng(0.0, 0.1)},
         "evening": {"living_room": rng(0.4, 0.6), "bedroom": rng(0.2, 0.4), "study_room": rng(0.1, 0.2)},
         "night": {"bedroom": rng(0.7, 0.9), "living_room": rng(0.1, 0.3)}},
        {"morning": {"bedroom": rng(0.6, 0.9), "living_room": rng(0.1, 0.3)},
         "day": {"living_room": rng(0.4, 0.6), "bedroom": rng(0.2, 0.4), "study_room": rng(0.1, 0.2)},
         "evening": {"living_room": rng(0.5, 0.7), "bedroom": rng(0.2, 0.4)},
         "night": {"bedroom": rng(0.7, 0.9), "living_room": rng(0.1, 0.3)}},
        rng(30, 90), rng(1, 4), rng(0.0, 0.1)),
    "behaviours": [wake("r_wake_weekday", {"from": "07:30", "to": "08:30"}, "weekdays"),
                   wake("r_wake_weekend", {"from": "08:30", "to": "10:30"}, "weekends")]
    + keep("r_morning")
    + [stay("r_work_morning", "Work in the study room in the morning.", {"from": "09:00", "to": "09:40"}, "weekdays",
            "study_room", rng(150, 190), 0.97, "study_room.lamp"),
       stay("r_lunch", "Lunch in the kitchen and dining room.", {"from": "12:20", "to": "12:50"}, "weekdays",
            "dining_room", rng(25, 50), 0.95),
       stay("r_work_afternoon", "Work in the study room in the afternoon.", {"from": "13:20", "to": "13:50"}, "weekdays",
            "study_room", rng(200, 260), 0.97, "study_room.lamp"),
       travel("r_gym", "Gym some evenings.", {"from": "18:30", "to": "19:10"}, ["mon", "wed", "fri"], "home", "gym", "walk",
              0.6, [AWAKE]),
       travel("r_gym_back", "Home from the gym.", {"from": "19:50", "to": "20:30"}, None, "gym", "home", "walk", 1),
       travel("r_weekend_out", "Weekend outing.", {"from": "11:00", "to": "15:00"}, "weekends", "home",
              {"choice": ["cafe", "park", "mall", "friend_home", "parents_home"], "weights": [3, 2, 2, 2, 1]}, "subway", 0.6,
              [AWAKE]),
       travel("r_weekend_back", "Home from the weekend outing.", {"from": "16:30", "to": "21:40"}, "weekends",
              ["cafe", "park", "mall", "friend_home", "parents_home"], "home", "subway", 1)]
    + keep("r_arrive_home", "r_arrive_music_off", "r_curtain_close", "r_evening_tv", "r_phone_use", "r_bedtime_late")
    + [bedtime({"from": "23:00", "to": "00:30"})]})
d = copy.deepcopy(R["r_dinner"])  # remote: dinner at a time of day, not on arrival
d["trigger"] = {"kind": "daily", "window": {"from": "18:30", "to": "20:00"}}
d["conditions"] = [HOME, AWAKE]
remote["behaviours"].append(d)

retiree = common({
    "personaId": "test_retiree", "_seed": 903, "houseType": "4room", "variant": "4room-B",
    "roomRoles": {"bedroom": "room1", "study_room": "room2"}, "phoneUseLevel": "light",
    "notes": "TEST profile (no patterns): retired man in his late 60s living alone, morning walk in the park, market "
             "some days, much TV, early bed. Written by hand to test the engine; no data behind the choices.",
    "windowSensors": {"rooms": ["living_room", "room1"], "reason": "His son fitted sensors on the living-room and bedroom windows."},
    "homeBaseRanges": hb(
        {"morning": {"bedroom": rng(0.2, 0.4), "living_room": rng(0.4, 0.6), "kitchen": rng(0.1, 0.2)},
         "day": {"living_room": rng(0.5, 0.7), "bedroom": rng(0.1, 0.3), "study_room": rng(0.1, 0.2), "balcony": rng(0.0, 0.1)},
         "evening": {"living_room": rng(0.6, 0.8), "bedroom": rng(0.2, 0.4)},
         "night": {"bedroom": rng(0.8, 1.0), "living_room": rng(0.0, 0.2)}},
        {"morning": {"bedroom": rng(0.2, 0.4), "living_room": rng(0.4, 0.6), "kitchen": rng(0.1, 0.2)},
         "day": {"living_room": rng(0.5, 0.7), "bedroom": rng(0.1, 0.3), "study_room": rng(0.1, 0.2), "balcony": rng(0.0, 0.1)},
         "evening": {"living_room": rng(0.6, 0.8), "bedroom": rng(0.2, 0.4)},
         "night": {"bedroom": rng(0.8, 1.0), "living_room": rng(0.0, 0.2)}},
        rng(40, 120), rng(2, 6), rng(0.1, 0.25)),
    "behaviours": [wake("r_wake", {"from": "05:40", "to": "06:30"}, None)]
    + keep("r_morning")
    + [travel("r_walk", "Morning walk in the park.", {"from": "07:00", "to": "08:00"}, None, "home", "park", "walk", 0.75,
              [AWAKE, {"kind": "weather", "op": "in", "value": ["clear", "cloudy"]}]),
       travel("r_walk_back", "Home from the walk.", {"from": "08:20", "to": "09:10"}, None, "park", "home", "walk", 1),
       travel("r_market", "Market or clinic some late mornings.", {"from": "10:00", "to": "11:30"}, ["tue", "thu", "sat"], "home",
              {"choice": ["market", "grocery_store", "clinic", "bank"], "weights": [4, 3, 1, 1]}, {"choice": ["walk", "bus"]},
              0.6, [AWAKE]),
       travel("r_market_back", "Home from the errand.", {"from": "12:00", "to": "13:00"}, None,
              ["market", "grocery_store", "clinic", "bank"], "home", {"choice": ["walk", "bus"]}, 1),
       travel("r_church", "Sunday service.", {"from": "10:00", "to": "10:30"}, ["sun"], "home", "place_of_worship", "bus", 0.7,
              [AWAKE]),
       travel("r_church_back", "Home from the service.", {"from": "12:30", "to": "13:30"}, ["sun"], "place_of_worship", "home",
              "bus", 1),
       stay("r_lunch", "Lunch in the dining room.", {"from": "12:10", "to": "13:00"}, None, "dining_room", rng(20, 40), 0.9),
       stay("r_reading", "Reading in the study some afternoons.", {"from": "14:00", "to": "16:00"}, None, "study_room",
            rng(40, 90), 0.4, "study_room.lamp")]
    + keep("r_arrive_home", "r_curtain_close", "r_evening_tv", "r_phone_use")
    + [bedtime({"from": "21:40", "to": "22:40"})]})
d = copy.deepcopy(R["r_dinner"])
d["id"], d["trigger"] = "r_dinner", {"kind": "daily", "window": {"from": "17:30", "to": "18:30"}}
d["conditions"] = [HOME, AWAKE]
retiree["behaviours"].append(d)
tv = copy.deepcopy(R["r_evening_tv"])  # a second TV block in the afternoon
tv["id"], tv["trigger"]["window"] = "r_afternoon_tv", {"from": "14:30", "to": "16:00"}
retiree["behaviours"].append(tv)

import sys
sys.path.insert(0, HERE)
from idle_ranges import IDLE
for p in (office, remote, retiree):
    p["idleActivityRanges"] = IDLE[p["personaId"]]
for p in (office, remote, retiree):
    out = os.path.join(ROOT, "profiles", p["personaId"] + ".json")
    json.dump(p, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(out, "a", encoding="utf-8").write("\n")
    print("wrote", out, len(p["behaviours"]), "behaviours")
