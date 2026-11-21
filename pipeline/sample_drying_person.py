#!/usr/bin/env python3
"""Draw one person's laundry-drying habit from the ranges the LLM chose for the persona and write it into the profile.

usage: python3 pipeline/sample_drying_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `dryingRanges` from the persona (agreed 2026-11-22):
  "dryingRanges": {"airMinC": {"min": 5, "max": 12}, "airMaxC": {"min": 26, "max": 30}}
When the person finds laundry on a rack not yet dry, with outdoor air between airMinC and airMaxC (and no rain) the window
of the rack's room is opened; otherwise a balcony rack is moved into the living room, and in the living room heating
(colder) or cooling (warmer) is switched on. No data: the LLM's choice, recorded in dryingPerson (whole degrees).
"""
import argparse, json, random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["dryingRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 67 + 907)
    def whole(r):
        return r["min"] + int(rnd.random() * (r["max"] - r["min"] + 1))
    prof["dryingHabits"] = dict(airMinC=whole(R["airMinC"]), airMaxC=whole(R["airMaxC"]))
    prof["dryingPerson"] = dict(seed=seed, ranges=R, source="ranges chosen by the LLM for this persona (no data found)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["dryingHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
