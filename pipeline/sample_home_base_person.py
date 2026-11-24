#!/usr/bin/env python3
"""Draw one person's home-base habit from the ranges the LLM chose for the persona and write it into the profile.

usage: python3 pipeline/sample_home_base_person.py profiles/063.json [--seed N] [--out path]

Where the person is when no rule or habit is doing something (agreed 2026-11-24, layer A). The LLM writes, from the
persona, `homeBaseRanges`:
  "homeBaseRanges": {
    "weekdays": {"morning": {"bedroom": {"min": 0.5, "max": 0.8}, "living_room": {...}}, "day": {...},
                 "evening": {...}, "night": {...}},
    "weekends": {...},
    "stayMinutes": {"min": 30, "max": 90},      median time in a home-base room before choosing again
    "errandMinutes": {"min": 1, "max": 4},      median time left in any other room (laundry, balcony...) after an errand
    "sofaSleepShare": {"min": 0, "max": 0.1}    share of bedtimes, starting in the living room, slept on the sofa
  }
Bands: morning 05-09, day 09-18, evening 18-23, night 23-05. Rooms are role names (bedroom, study_room, living_room,
kitchen, dining_room) or room ids. No data: the LLM's choice, recorded in homeBasePerson.
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
    R = prof["homeBaseRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 71 + 911)
    uni = lambda r: r["min"] + rnd.random() * (r["max"] - r["min"])
    H = {}
    for days in ("weekdays", "weekends"):
        H[days] = {}
        for band in BANDS:
            w = {room: uni(r) for room, r in R[days][band].items()}
            tot = sum(w.values()) or 1.0
            H[days][band] = {room: round(v / tot, 3) for room, v in w.items()}
    H["stayMinutes"] = round(uni(R["stayMinutes"]))
    H["errandMinutes"] = round(uni(R["errandMinutes"]), 1)
    H["sofaSleepShare"] = round(uni(R["sofaSleepShare"]), 2)
    prof["homeBaseHabits"] = H
    prof["homeBasePerson"] = dict(seed=seed, ranges=R, source="ranges chosen by the LLM for this persona (no data found)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(H, ensure_ascii=False))


if __name__ == "__main__":
    main()
