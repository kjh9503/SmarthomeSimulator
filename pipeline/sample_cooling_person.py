#!/usr/bin/env python3
"""Draw one person's cooling habits from the ranges the LLM chose for the persona and write them into the profile.

usage: python3 pipeline/sample_cooling_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `coolingRanges` from the persona (agreed 2026-11-20, as for heating: the LLM sets ranges, this script
draws within them, so that people differ):
  "coolingRanges": {
    "uses": {"yes": 4, "no": 1},              uses the air conditioner at all (every room has one in our flats)
    "onAboveC": {"min": 28, "max": 31},        room temperature at which the person switches it on (0.5 C steps)
    "setpointC": {"min": 24, "max": 27},       setpoint (whole degrees)
    "sleep": {"keep": 1, "off": 1},            at bedtime
    "leaving": {"keep": 1, "off": 3},          when leaving home
    "unusedRooms": {"off": 1, "keep": 1}       switches off a cooled room left for 30 min, or not
  }
Figures: Seoul flats switched cooling on at 29.8 C and off at 27.3 C room temperature on average (Chun & Bae 2005);
rooms with cooling on were at 25.2 C (Yun et al. 2020). Nothing found on bedtime / leaving habits: the LLM's choice,
recorded in coolingPerson. The engine: smarthome_sim/agent.py, cooling_*.
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


def draw(rnd, R):
    if pick(rnd, R["uses"]) != "yes":
        return dict(uses=False)
    lo, hi = R["onAboveC"]["min"], R["onAboveC"]["max"]
    on = lo + 0.5 * int(rnd.random() * (round((hi - lo) / 0.5) + 1))
    a, b = R["setpointC"]["min"], min(R["setpointC"]["max"], int(on - 1))
    sp = a + int(rnd.random() * (b - a + 1)) if b >= a else a
    return dict(uses=True, onAboveC=on, setpointC=sp, sleep=pick(rnd, R["sleep"]), leaving=pick(rnd, R["leaving"]),
                unusedRooms=pick(rnd, R["unusedRooms"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["coolingRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 43 + 401)
    prof["coolingHabits"] = draw(rnd, R)
    prof["coolingPerson"] = dict(seed=seed, ranges=R, source="ranges chosen by the LLM for this persona; switch-on 29.8 C (Chun & Bae 2005), cooled rooms 25.2 C (Yun et al. 2020)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["coolingHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
