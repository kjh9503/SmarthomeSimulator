#!/usr/bin/env python3
"""Draw one person's laundry drying habit from the range the LLM chose for the persona and write it into the profile.

usage: python3 pipeline/sample_laundry_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `laundryRanges` from the persona (agreed 2026-11-21: dryer or rack is a per-person share):
  "laundryRanges": {
    "washesPerWeek": {"min": 2, "max": 4},      washes a week (whole number); the engine makes the washing routines
    "weekendShare": {"min": 0.4, "max": 0.8},   share of them on weekend mornings (09-12), the rest on weekday evenings (19-22)
    "dryerShare": {"min": 0.5, "max": 0.9}      share of washes put in the dryer (the rest dries on a rack indoors);
  }                                             no dryer: 0 to 0. Shares are drawn in 0.05 steps.
Washing: more than half of respondents (20-50 years old) wash once every two days (Laundrygo "2022 Korean Laundry Report",
Aju News 2022-08-18; a laundry service's survey). The times of day were not found (the slots are the LLM's choice).
Korean households with a dryer: 12% in 2020, 35% in 2023 (Gallup Korea, cited by Herald Economy 2025-11-18). How often
owners still hang laundry was not found: the LLM's choice, recorded in laundryPerson. The engine: agent.py laundry_tick.
"""
import argparse, json, random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["laundryRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 61 + 809)
    def step(r):
        lo, hi = r["min"], r["max"]
        return round(lo + 0.05 * int(rnd.random() * (round((hi - lo) / 0.05) + 1)), 2)
    wk = R["washesPerWeek"]
    n = wk["min"] + int(rnd.random() * (wk["max"] - wk["min"] + 1))
    prof["laundryHabits"] = dict(washesPerWeek=n, weekendShare=step(R["weekendShare"]), dryerShare=step(R["dryerShare"]))
    prof["laundryPerson"] = dict(seed=seed, ranges=R, source="range chosen by the LLM for this persona; dryer ownership 35% in 2023 (Gallup Korea)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["laundryHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
