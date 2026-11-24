#!/usr/bin/env python3
"""Draw one person's idle-time activities from the ranges the LLM chose for the persona and write them into the profile.

usage: python3 pipeline/sample_idle_person.py profiles/063.json [--seed N] [--out path]

What the person does at home when no rule or habit is doing something (agreed 2026-11-24). The engine has a fixed
pool (agent.py IDLE_POOL: tv, reading, study, snack, toilet, dishes, cleaning, music, video, game, shopping, call,
workout, nap, plants, folding, tidying, rest); the LLM picks the ones this persona does and writes, per activity:
  "idleActivityRanges": {
    "tv": {"weights": {"morning": {"min": 0, "max": 0.5}, "day": {...}, "evening": {...}, "night": {...}},
           "minutes": {"min": 40, "max": 120},     median minutes one go lasts
           "rooms": ["living_room"]},              rooms from the pool's rooms for that activity (role names)
    "dishes":   {..., "dishwasherShare": {"min": 0, "max": 0}},     0: no dishwasher
    "cleaning": {..., "robotShare": {"min": 0.5, "max": 0.8}},      0: no robot vacuum
    "video" / "game" / "shopping": {..., "apps": {"com.google.android.youtube": 3, "com.netflix.mediaclient": 1}},
    "workout":  {..., "kinds": {"Yoga": 1, "Stretching": 2}}
  }
Bands as homeBaseRanges (morning 05-09, day 09-18, evening 18-23, night 23-05). Weights are relative within a band.
No data: the LLM's choice, recorded in idleActivityPerson.
"""
import argparse, json, random

BANDS = ("morning", "day", "evening", "night")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["idleActivityRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 73 + 919)
    uni = lambda r: r["min"] + rnd.random() * (r["max"] - r["min"])
    H = {}
    for act in sorted(R):
        r = R[act]
        h = dict(weights={b: round(uni(r["weights"][b]), 3) for b in BANDS if b in r["weights"]},
                 minutes=round(uni(r["minutes"]), 1), rooms=list(r["rooms"]))
        for k in ("dishwasherShare", "robotShare"):
            if k in r:
                h[k] = round(uni(r[k]), 2)
        for k in ("apps", "kinds"):
            if k in r:
                h[k] = dict(r[k])
        H[act] = h
    prof["idleActivityHabits"] = H
    prof["idleActivityPerson"] = dict(seed=seed, ranges=R, source="ranges chosen by the LLM for this persona (no data found)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(H, ensure_ascii=False)[:300])


if __name__ == "__main__":
    main()
