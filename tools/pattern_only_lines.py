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
writes <out>/phone_log.jsonl (full format, with an extra "_cause" field per line), <out>/pattern_line_kinds.csv and
<out>/pattern_sequence_kinds.csv: devices that are on when the person leaves home or goes to sleep, grouped by
moment, device type, how long they have been on and keepOn, with the number switched on by patterns and by others
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
Phone.to_alert = tag(Phone.to_alert)

LAST = {}        # deviceId -> (time switched on, cause) while on
SEQUENCES = []   # (moment, device type, minutes since on, kept on, cause) for devices on when leaving / going to sleep
ON_TYPES = {"window_contact", "door_contact", "heating_cooling_unit", "tv", "air_purifier", "humidifier", "light", "lamp", "speaker"}


def is_on_value(attr, v):
    return v in ("on", "open", "cool", "heat", "playing") or (attr == "percent" and isinstance(v, (int, float)) and v > 0)


_to_st = tag(Phone.to_smartthings)


def to_st(self, e):
    c = _to_st(self, e)
    dev = f"{e.get('roomId')}.{e.get('device')}" if e.get("roomId") and e.get("device") else None  # home line: device = type
    if dev and e["device"] in ON_TYPES and e.get("attribute") in ("switch", "contact", "thermostatMode", "percent", "playbackStatus"):
        if is_on_value(e["attribute"], e.get("value")):
            LAST.setdefault(dev, (c["timestamp"], c["_cause"]))
        else:
            LAST.pop(dev, None)
    return c


Phone.to_smartthings = to_st
_off_check = AgentRunner.off_check


def off_check(self, moment, t, only=None):
    if moment in ("leaving", "bedtime") and not self.S["asleep"] and self.S["place"] == "home":
        for dev, (t_on, cause) in LAST.items():
            m = (t - t_on) / 60000
            SEQUENCES.append((moment, dev.split(".", 1)[1], "<10 min" if m < 10 else "10-30 min" if m < 30 else "30-120 min" if m < 120 else ">120 min",
                              dev in self.keep_on, cause))
    return _off_check(self, moment, t, only)


AgentRunner.off_check = off_check


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

    seq = collections.defaultdict(lambda: [0, 0])
    for moment, dtype, since, kept, c in SEQUENCES:
        is_pat = c.startswith("rule:") and c[5:] in patterns
        seq[(moment, dtype, since, "kept on" if kept else "-")][0 if is_pat else 1] += 1
    path2 = os.path.join(o.out, "pattern_sequence_kinds.csv")
    with open(path2, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["moment", "device_type", "on_for", "keepOn", "pattern", "other", "pattern_share"])
        for k, (pn, on) in sorted(seq.items()):
            w.writerow(list(k) + [pn, on, round(pn / (pn + on), 3)])
    pat = [(k, v) for k, v in seq.items() if v[0]]
    print(f"devices on at leaving / bedtime: {sum(sum(v) for v in seq.values())} cases in {len(seq)} kinds; "
          f"{len(pat)} kinds with pattern cases, {sum(1 for k, v in pat if v[1] == 0)} only from patterns")
    for k, (pn, on) in sorted(pat, key=lambda x: -x[1][0] / sum(x[1])):
        print(f"  share {pn / (pn + on):.2f}  pattern {pn:>4}  other {on:>5}  {' | '.join(k)}")
    print("->", path2)


if __name__ == "__main__":
    main()
