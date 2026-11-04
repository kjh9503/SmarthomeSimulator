#!/usr/bin/env python3
"""Draw one person's heating habits from the ranges the LLM chose for the persona and write them into the profile.

usage: python3 pipeline/sample_heating_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `heatingRanges` from the persona (agreed 2026-11-05: the LLM sets ranges that fit the persona, this
script draws within them, so that people differ):
  "heatingRanges": {
    "comfortC": {"min": 21, "max": 24},                 setpoint while awake at home (drawn in 0.5 C steps)
    "sleep": {"keep": 1, "lower": 2, "off": 1},          weights of what the person does at bedtime
    "sleepLowerC": {"min": 1, "max": 3},                 by how much, if "lower" (whole degrees)
    "leaving": {"keep": 1, "lower": 1, "off": 2},        weights of what the person does when leaving home
    "leavingLowerC": {"min": 2, "max": 5},
    "keepWhenOutdoorBelowC": {"min": -8, "max": 0},      optional: leaves the heating as it is when colder than this
    "unusedRooms": {"off": 2, "keep": 1}                 switches off a room left for 30 min, or not
  }
The engine (smarthome_sim/agent.py, heating_*) then keeps the room the person is in near comfortC, applies the sleep
and leaving habits, and switches unused rooms off. No population data was found for these habits: every weight and
range is the LLM's choice for the persona, recorded in heatingPerson.
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
    lo, hi = R["comfortC"]["min"], R["comfortC"]["max"]
    comfort = lo + 0.5 * int(rnd.random() * (round((hi - lo) / 0.5) + 1))
    sleep = dict(action=pick(rnd, R["sleep"]))
    if sleep["action"] == "lower":
        a, b = R["sleepLowerC"]["min"], R["sleepLowerC"]["max"]
        sleep["lowerC"] = a + int(rnd.random() * (b - a + 1))
    leaving = dict(action=pick(rnd, R["leaving"]))
    if leaving["action"] == "lower":
        a, b = R["leavingLowerC"]["min"], R["leavingLowerC"]["max"]
        leaving["lowerC"] = a + int(rnd.random() * (b - a + 1))
    if leaving["action"] != "keep" and R.get("keepWhenOutdoorBelowC"):
        a, b = R["keepWhenOutdoorBelowC"]["min"], R["keepWhenOutdoorBelowC"]["max"]
        leaving["keepWhenOutdoorBelowC"] = a + int(rnd.random() * (b - a + 1))
    return dict(comfortC=comfort, sleep=sleep, leaving=leaving, unusedRooms=pick(rnd, R["unusedRooms"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["heatingRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 37 + 211)
    prof["heatingHabits"] = draw(rnd, R)
    prof["heatingPerson"] = dict(seed=seed, ranges=R, source="ranges and weights chosen by the LLM for this persona (no population data)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["heatingHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
