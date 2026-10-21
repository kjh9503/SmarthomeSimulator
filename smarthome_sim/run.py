"""Command line: python -m smarthome_sim.run --profile profiles/063.json [--out out/063] [--days N] [--seed N] [--trace]"""
import argparse
import json
import os

from .agent import AgentRunner


def main(argv=None):
    ap = argparse.ArgumentParser(description="Run one persona's agent profile through the smart-home + phone simulator.")
    ap.add_argument("--profile", required=True, help="agent profile JSON (profiles/<personaId>.json)")
    ap.add_argument("--out", help="output folder (default out/<personaId>)")
    ap.add_argument("--days", type=int, help="number of days (default: the profile's simulation.days)")
    ap.add_argument("--seed", type=int, help="random seed (default: the profile's simulation.seed)")
    ap.add_argument("--trace", action="store_true", help="also write trace.jsonl")
    ap.add_argument("--off-rules", help="checks before sleep / leaving / after waking (default: smarthome_sim/off_rules.json)")
    ap.add_argument("--vocabulary", help="vocabulary.json, for apps the profile uses (default: pipeline/vocabulary.json)")
    a = ap.parse_args(argv)
    profile = json.load(open(a.profile, encoding="utf-8"))
    out = a.out or os.path.join("out", profile["personaId"])
    AgentRunner(profile, out, days=a.days, seed=a.seed, trace=a.trace, off_rules=a.off_rules, vocabulary=a.vocabulary).run()


if __name__ == "__main__":
    main()
