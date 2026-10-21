"""Compares two runs of the same profile (e.g. the JavaScript runner and the Python runner) by their statistics.
usage: python3 tools/compare_runs.py <out_dir_a> <out_dir_b> [label_a] [label_b]"""
import collections
import json
import statistics
import sys


def load(d):
    S = json.load(open(f"{d}/summary.json"))
    src = collections.Counter()
    cmds = collections.Counter()
    sensors = collections.defaultdict(list)
    types = collections.Counter()
    sleep, steps, hr = [], [], []
    for l in open(f"{d}/phone_log.jsonl", encoding="utf-8"):
        e = json.loads(l)
        types[e["type"]] += 1
        p = e.get("payload") or {}
        if e["type"] == "SMARTTHINGS" and p.get("kind") == "state":  # the copy of a home line
            a, ch = p["actor"], p["change"]
            kind = {"user": "command" if a.get("command") else "manual"}.get(a["kind"], a["kind"])
            src[kind] += 1
            if a["kind"] == "user":
                cmds[p["name"]] += 1
            if a["kind"] == "sensor" and a.get("reason") != "presence" and isinstance(ch["value"], (int, float)):
                sensors[(p["roomId"], ch["attribute"])].append(ch["value"])
        if e["type"] == "HEALTH" and e["source"] == "SLEEP":
            sleep.append(e["payload"]["durationMinutes"] / 60)
        if e["type"] == "HEALTH" and e["source"] == "HOURLY":
            steps.append(e["payload"]["steps"])
            hr.append(e["payload"]["averageBpm"])
    return dict(S=S, src=src, cmds=cmds, sensors=sensors, types=types, sleep=sleep, steps=steps, hr=hr)


def main():
    a, b = load(sys.argv[1]), load(sys.argv[2])
    la, lb = (sys.argv[3:5] + ["A", "B"])[:2] if len(sys.argv) > 3 else ("A", "B")
    rows = [("home lines (SMARTTHINGS state copies)", a["S"]["homeLines"], b["S"]["homeLines"]), ("phone events", a["S"]["phoneEvents"], b["S"]["phoneEvents"])]
    for k in sorted(set(a["src"]) | set(b["src"])):
        rows.append((f"home line actor={k}", a["src"][k], b["src"][k]))
    for k in sorted(set(a["types"]) | set(b["types"])):
        rows.append((f"phone type={k}", a["types"][k], b["types"][k]))
    for k in sorted(set(a["cmds"]) | set(b["cmds"])):
        rows.append((f"person actions on {k}", a["cmds"][k], b["cmds"][k]))
    for name in ("sleep", "steps", "hr"):
        rows.append((f"{name} mean", round(statistics.mean(a[name]), 2), round(statistics.mean(b[name]), 2)))
    for key in (("living_room", "fineDustLevel"), ("living_room", "temperature"), ("room1", "carbonDioxide"), ("living_room", "illuminance")):
        rows.append((f"saved {key[0]} {key[1]} mean", round(statistics.mean(a["sensors"][key]), 2), round(statistics.mean(b["sensors"][key]), 2)))
    for bid in sorted(set(a["S"]["behaviours"]) | set(b["S"]["behaviours"])):
        x, y = a["S"]["behaviours"].get(bid, {}), b["S"]["behaviours"].get(bid, {})
        rows.append((f"{bid} followed", x.get("followed"), y.get("followed")))
    for m in ("bedtime", "leaving", "morning"):
        rows.append((f"check {m} turnedOff/leftOn", f'{a["S"]["checks"][m]["turnedOff"]}/{a["S"]["checks"][m]["leftOn"]}',
                     f'{b["S"]["checks"][m]["turnedOff"]}/{b["S"]["checks"][m]["leftOn"]}'))
    rows.append(("cooking median / p90 min", f'{a["S"]["cooking"]["minutesMedian"]}/{a["S"]["cooking"]["minutesP90"]}',
                 f'{b["S"]["cooking"]["minutesMedian"]}/{b["S"]["cooking"]["minutesP90"]}'))
    print(f"| item | {la} | {lb} |\n|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} |")


if __name__ == "__main__":
    main()
