#!/usr/bin/env python3
"""Which kinds of phone-log lines are made only by the hidden pattern(s)?

A kind of line that only a pattern rule makes (for example "air purifier 60 -> 0 %, changed by the device timer")
lets a method find the pattern from that one line without learning the pattern's conditions.

The script runs a profile and records, for every phone-log line, the rule or check that was running when the line
was made. Lines are then grouped into kinds:
  SMARTTHINGS state lines: device type, capability.attribute, new value, actor kind, actor channel, actor reason
  other lines:             type, source, payload action/state (when present)
For each kind it counts lines made by pattern rules and by everything else, and lists kinds made by patterns.

usage (from the repo root):
  python3 tools/pattern_only_lines.py --profile profiles/063.json --out out/063_lines [--days N] [--seed S]
writes <out>/phone_log.jsonl (full format, with an extra "_cause" field per line) and <out>/pattern_line_kinds.csv
"""
import sys, os, json, argparse, collections, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from smarthome_sim.agent import AgentRunner
from smarthome_sim.phone import Phone


def current_cause():
    """walk the call stack outwards and name the first rule / check / scheduled item found"""
    f = sys._getframe(2)
    while f is not None:
        name, loc = f.f_code.co_name, f.f_locals
        if name == "run_task" and isinstance(loc.get("task"), dict):
            return "rule:" + loc["task"]["b"]["id"]
        if name == "off_check":
            return "check:" + loc["moment"]
        if name == "run_scheduled" and isinstance(loc.get("it"), dict):
            it = loc["it"]
            return ("rule:" + it["owner"]) if it.get("owner") else "scheduled:" + it.get("kind", "?")
        if name in ("step_devices", "report_sensors", "close_day", "tick", "step_once"):
            return "simulator"
        f = f.f_back
    return "other"


def tag(fn):
    def wrapped(*a, **k):
        e = fn(*a, **k)
        if isinstance(e, dict):
            e["_cause"] = current_cause()
        return e
    return wrapped


Phone.emit = tag(Phone.emit)
Phone.to_smartthings = tag(Phone.to_smartthings)
Phone.to_alert = tag(Phone.to_alert)


def kind_of(e):
    p = e.get("payload") or {}
    if e["type"] == "SMARTTHINGS" and p.get("kind") == "state":
        dev = p["deviceId"].split(".", 1)[1]
        ch, a = p["change"], p.get("actor") or {}
        return ("SMARTTHINGS state", dev, ch["capability"] + "." + ch["attribute"], json.dumps(ch["value"]),
                a.get("kind"), a.get("channel"), a.get("reason"))
    extra = p.get("action") or p.get("state") or p.get("kind")
    return (e["type"], e.get("source"), json.dumps(extra), "", "", "", "")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--profile", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--days", type=int)
    ap.add_argument("--seed", type=int)
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    patterns = {b["id"] for b in prof["behaviours"] if b["kind"] == "pattern"}
    os.makedirs(o.out, exist_ok=True)
    AgentRunner(prof, o.out, days=o.days, seed=o.seed, full_format=True, log=lambda *x: None).run()

    count = collections.defaultdict(lambda: [0, 0])          # kind -> [pattern lines, other lines]
    by_rule = collections.defaultdict(collections.Counter)    # kind -> cause counts
    for line in open(os.path.join(o.out, "phone_log.jsonl"), encoding="utf-8"):
        e = json.loads(line)
        c = e.get("_cause", "other")
        k = kind_of(e)
        is_pat = c.startswith("rule:") and c[5:] in patterns
        count[k][0 if is_pat else 1] += 1
        by_rule[k][c] += 1
    rows = []
    for k, (pn, on) in count.items():
        if pn:
            rows.append(list(k) + [pn, on, round(pn / (pn + on), 3), "; ".join(f"{c} {n}" for c, n in by_rule[k].most_common(4))])
    rows.sort(key=lambda r: (-r[9], -r[7]))
    path = os.path.join(o.out, "pattern_line_kinds.csv")
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["type", "device_or_source", "attribute", "value", "actor", "channel", "reason",
                    "pattern_lines", "other_lines", "pattern_share", "made_by"])
        w.writerows(rows)
    only = [r for r in rows if r[8] == 0]
    print(f"{len(count)} kinds of lines; {len(rows)} kinds made by a pattern at least once; {len(only)} made only by patterns")
    for r in rows:
        print(f"  share {r[9]:.2f}  pattern {r[7]:>4}  other {r[8]:>6}  {' | '.join(str(x) for x in r[:7] if x not in ('', None))}")
    print("->", path)


if __name__ == "__main__":
    main()
