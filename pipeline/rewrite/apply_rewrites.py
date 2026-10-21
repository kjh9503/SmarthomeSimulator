#!/usr/bin/env python3
"""Check the rewrite replies and turn them into the input of the structuring step.

usage: python3 apply_rewrites.py ../input/realistic_patterns.txt replies/   (folder of reply files, each a JSON array)
Writes: patterns_rewritten.csv (personaId,patternId,patternType,text,note) for ../build_requests.py,
        rewrite_report.csv (every row: changeLevel, original, rewritten, changes),
        and adds every newApps entry to ../vocabulary_extra.json extraApps (then run ../extract_vocabulary.py).
Stops with a list of problems if a row is missing, repeated, has changed ids or type, or lacks fields.
"""
import csv, glob, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from build_rewrite_requests import read_rows
LEVELS = {"unchanged", "minor", "substituted", "replaced"}

def main():
    src, folder = sys.argv[1], sys.argv[2]
    rows = read_rows(src); want = {(r["personaId"], r["patternId"]): r for r in rows}
    got, problems = {}, []
    for f in sorted(glob.glob(os.path.join(folder, "*.json"))):
        text = open(f, encoding="utf-8").read().strip()
        if text.startswith("```"): text = text.strip("`").split("\n", 1)[1].rsplit("```", 1)[0]
        try: arr = json.loads(text)
        except Exception as e: problems.append(f"{os.path.basename(f)}: not JSON ({e})"); continue
        for o in arr:
            k = (o.get("personaId"), o.get("patternId"))
            if k not in want: problems.append(f"{os.path.basename(f)}: unknown row {k}"); continue
            if k in got: problems.append(f"{k}: appears twice"); continue
            for fld in ("text", "changeLevel", "changes", "note", "newApps"):
                if fld not in o: problems.append(f"{k}: missing '{fld}'")
            if o.get("patternType") != want[k]["patternType"]: problems.append(f"{k}: patternType changed to {o.get('patternType')}")
            if o.get("changeLevel") not in LEVELS: problems.append(f"{k}: changeLevel '{o.get('changeLevel')}'")
            if o.get("changeLevel") != "unchanged" and not o.get("changes"): problems.append(f"{k}: changed but no 'changes' listed")
            if not str(o.get("text", "")).strip(): problems.append(f"{k}: empty text")
            got[k] = o
    for k in want:
        if k not in got: problems.append(f"{k}: missing from the replies")
    if problems:
        print("\n".join(problems)); sys.exit(f"{len(problems)} problem(s); nothing written")
    with open(os.path.join(HERE, "patterns_rewritten.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["personaId", "patternId", "patternType", "text", "note"])
        for k, r in want.items(): w.writerow([k[0], k[1], r["patternType"], got[k]["text"], got[k].get("note", "")])
    with open(os.path.join(HERE, "rewrite_report.csv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["personaId", "patternId", "changeLevel", "originalText", "text", "changes"])
        for k, r in want.items():
            o = got[k]; w.writerow([k[0], k[1], o["changeLevel"], r["text"], o["text"], " | ".join(f"{c.get('from')} -> {c.get('to')} ({c.get('reason')})" for c in o["changes"])])
    extra_path = os.path.join(HERE, "..", "vocabulary_extra.json"); extra = json.load(open(extra_path, encoding="utf-8"))
    added = []
    for o in got.values():
        for app in o.get("newApps", []):
            if app.get("package") and app["package"] not in extra["extraApps"]:
                extra["extraApps"][app["package"]] = app.get("label", app["package"]); added.append(app["package"])
    json.dump(extra, open(extra_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    levels = {l: sum(1 for o in got.values() if o["changeLevel"] == l) for l in LEVELS}
    print(f"{len(got)} rows -> patterns_rewritten.csv, rewrite_report.csv | changeLevel {levels} | {len(added)} new app(s) added to vocabulary_extra.json")
    if added: print("run ../extract_vocabulary.py to rebuild vocabulary.json with the new apps")

if __name__ == "__main__":
    main()
