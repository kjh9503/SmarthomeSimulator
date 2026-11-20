#!/usr/bin/env python3
"""Draw one person's shower habit from the weights the LLM chose for the persona and write it into the profile.

usage: python3 pipeline/sample_shower_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `showerRanges` from the persona (agreed 2026-11-21):
  "showerRanges": {
    "perDay": {"0": 1, "1": 8, "2": 2},        showers a day
    "when": {"morning": 2, "evening": 1},      for one a day: after waking or in the evening (two a day: both)
    "minutes": {"min": 8, "max": 15}           the person's usual length (drawn in whole minutes, then +-2 each time)
  }
No Korean data on shower counts, times or lengths was found: the LLM's choice, recorded in showerPerson. The engine makes
routines from the habit (smarthome_sim/agent.py shower_behaviours): to the bathroom, light on, shower (0.24 kg of water
vapour per 5 min, house.py moisture.showerGMin), light off.
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["showerRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 59 + 701)
    n = int(pick(rnd, R["perDay"]))
    slots = [] if n == 0 else (["morning", "evening"] if n >= 2 else [pick(rnd, R["when"])])
    m = R["minutes"]["min"] + int(rnd.random() * (R["minutes"]["max"] - R["minutes"]["min"] + 1))
    prof["showerHabits"] = dict(slots=slots, minutes=dict(min=max(1, m - 2), max=m + 2))
    prof["showerPerson"] = dict(seed=seed, ranges=R, source="weights chosen by the LLM for this persona (no Korean data found)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["showerHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
