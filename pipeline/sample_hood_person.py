#!/usr/bin/env python3
"""Draw one person's range hood habit from the range the LLM chose for the persona and write it into the profile.

usage: python3 pipeline/sample_hood_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `hoodRanges` from the persona (agreed 2026-11-21: the hood is used on a share of cookings, a per-person
habit):
  "hoodRanges": {"useShare": {"min": 0.3, "max": 0.9}}   share of cookings with the hood on (drawn in 0.05 steps)
No survey of how often Korean households run the hood was found; the range is the LLM's choice, recorded in hoodPerson.
The hood has no SmartThings capability: it writes no lines, only its effect (smarthome_sim/house.py PHYS envelope.hood).
"""
import argparse, json, random


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["hoodRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 53 + 601)
    lo, hi = R["useShare"]["min"], R["useShare"]["max"]
    share = round(lo + 0.05 * int(rnd.random() * (round((hi - lo) / 0.05) + 1)), 2)
    prof["hoodHabits"] = dict(useShare=share)
    prof["hoodPerson"] = dict(seed=seed, ranges=R, source="range chosen by the LLM for this persona (no survey found)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["hoodHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
