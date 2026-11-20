#!/usr/bin/env python3
"""Draw one person's laundry drying habit from the range the LLM chose for the persona and write it into the profile.

usage: python3 pipeline/sample_laundry_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `laundryRanges` from the persona (agreed 2026-11-21: dryer or rack is a per-person share):
  "laundryRanges": {"dryerShare": {"min": 0.5, "max": 0.9}}   share of washes put in the dryer (drawn in 0.05 steps);
                                                               the rest dries on a rack indoors. No dryer: 0 to 0.
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
    lo, hi = R["dryerShare"]["min"], R["dryerShare"]["max"]
    share = round(lo + 0.05 * int(rnd.random() * (round((hi - lo) / 0.05) + 1)), 2)
    prof["laundryHabits"] = dict(dryerShare=share)
    prof["laundryPerson"] = dict(seed=seed, ranges=R, source="range chosen by the LLM for this persona; dryer ownership 35% in 2023 (Gallup Korea)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["laundryHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
