#!/usr/bin/env python3
"""Draw one person's ventilation habits from the weights the LLM chose for the persona and write them into the profile.

usage: python3 pipeline/sample_ventilation_person.py profiles/063.json [--seed N] [--out path]

The LLM writes `ventilationRanges` from the persona (agreed 2026-11-18: as for heating, the LLM sets weights that fit the
persona, this script draws within them, so that people differ):
  "ventilationRanges": {
    "uses": {"yes": 1, "no": 1},                       runs the flat's ventilation unit at all
    "when": {"always": 1, "home": 2, "awake": 2},      if so: all day / while someone is home / while home and awake
    "winter": {"run": 2, "off": 1}                     keeps it running in the heating season, or stops it then
  }
One figure exists: 47.5% of households in new flats use the unit (2011 Gallup survey for Samsung C&T, cited by Lee 2016,
Air Cleaning Technology 29(1)); reasons for not using it: electricity bill, noise, cold draught in winter. Nothing was found
on hours of use, so "when" and "winter" are the LLM's choice for the persona, recorded in ventilationPerson.
The engine (smarthome_sim/agent.py, ventilation_tick) runs the unit from the drawn habits; it writes no log lines.
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
    uses = pick(rnd, R["uses"]) == "yes"
    if not uses:
        return dict(uses=False)
    return dict(uses=True, when=pick(rnd, R["when"]), winter=pick(rnd, R["winter"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    R = prof["ventilationRanges"]
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 41 + 307)
    prof["ventilationHabits"] = draw(rnd, R)
    prof["ventilationPerson"] = dict(seed=seed, ranges=R, source="weights chosen by the LLM for this persona; share of users in new flats 47.5% (Gallup 2011, cited by Lee 2016)")
    json.dump(prof, open(o.out or o.profile, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    open(o.out or o.profile, "a", encoding="utf-8").write("\n")
    print(json.dumps(prof["ventilationHabits"], ensure_ascii=False))


if __name__ == "__main__":
    main()
