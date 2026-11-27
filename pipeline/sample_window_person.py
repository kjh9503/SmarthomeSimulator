#!/usr/bin/env python3
"""Draw one person's window habits from the ranges the LLM chose for the persona and write them into the profile.

usage: python3 pipeline/sample_window_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `windowRanges` from the persona (agreed 2026-11-20):
  "windowRanges": {
    "summerOpen": {"yes": 3, "no": 1},             opens the window of a hot room when outdoor air is cooler
    "openAboveC": {"min": 25, "max": 28},           room temperature at which the person opens it (0.5 C steps)
    "sleepOpen": {"yes": 1, "no": 1},              sleeps with it open on warm dry nights
    "airingPerDay": {"0": 20, "1": 50, "2": 30},   airings a day (morning 9-11 and/or evening 17-19)
    "airingMinutes": {"min": 10, "max": 40},        the person's usual airing outside the heating season (whole minutes)
    "winterAiringMinutes": {"min": 5, "max": 10},   in the heating season
    "laundryOpenAboveC": {"min": 26, "max": 30}     optional (2026-11-27): laundry room temperature at which the person
                                                    opens its outer window on going in (0.5 C steps); without it the
                                                    engine uses openAboveC
  }
Figures: airing once a day 49.7%, twice 30.7%; under 20 min 43.0%, 20-40 min 39.6% (spring survey, 154 flats in Seoul and
Gyeonggi, Lee 2010); winter: 75% open 1-2 times a day for under 10 min (20 flats in Cheongju, Cho & Choi 2013). Nothing
found on opening for heat or sleeping with windows open: the LLM's choice, recorded in windowPerson. Each airing lasts the
person's usual minutes x 0.7-1.3. The engine: smarthome_sim/agent.py, window_* and airing_*.
"""
import argparse, json, random


def pick(rnd, weights):
    keys = [k for k, w in weights.items() if w > 0]
    x = rnd.random() * sum(weights[k] for k in keys)
    for k in keys:
        x -= weights[k]
        if x <= 0:
            return k
    return keys[-1]


def whole(rnd, r):
    return r["min"] + int(rnd.random() * (r["max"] - r["min"] + 1))


def draw(rnd, R):
    lo, hi = R["openAboveC"]["min"], R["openAboveC"]["max"]
    h = dict(summerOpen=pick(rnd, R["summerOpen"]) == "yes", openAboveC=lo + 0.5 * int(rnd.random() * (round((hi - lo) / 0.5) + 1)),
                sleepOpen=pick(rnd, R["sleepOpen"]) == "yes", airingPerDay=int(pick(rnd, R["airingPerDay"])),
                airingMinutes=whole(rnd, R["airingMinutes"]), winterAiringMinutes=whole(rnd, R["winterAiringMinutes"]))
    if "laundryOpenAboveC" in R:
        lo, hi = R["laundryOpenAboveC"]["min"], R["laundryOpenAboveC"]["max"]
        h["laundryOpenAboveC"] = lo + 0.5 * int(rnd.random() * (round((hi - lo) / 0.5) + 1))
    return h


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["windowRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 47 + 503)
    prof["windowHabits"] = draw(rnd, R)
    prof["windowPerson"] = dict(seed=seed, ranges=R, source="ranges chosen by the LLM for this persona; airing counts and minutes from Lee 2010 and Cho & Choi 2013")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["windowHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
