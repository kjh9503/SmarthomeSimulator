#!/usr/bin/env python3
"""Rebuild vocabulary.json from the simulator (names stay in step with smarthome-sim.html).

usage: python3 extract_vocabulary.py [../browser/smarthome-sim.html]
Needs node. Takes the simulator's script up to its storage/UI part, appends tools_vocab_tail.js (which reads the
simulator's own tables: SPEC, HOUSE_TYPES, PLACES, TRAVEL_MODES, APPS, ...), then merges vocabulary_extra.json
(person actions, extra apps, phone signals, room roles: written by hand).
"""
import json, os, re, subprocess, sys, tempfile
HERE = os.path.dirname(os.path.abspath(__file__))
html = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "browser", "smarthome-sim.html")
js = re.search(r"<script>(.*)</script>", open(html, encoding="utf-8").read(), re.S).group(1)
core = js[:js.index("/* ===== Storage")]
tail = open(os.path.join(HERE, "tools_vocab_tail.js"), encoding="utf-8").read()
with tempfile.TemporaryDirectory() as d:
    src, out = os.path.join(d, "v.js"), os.path.join(d, "v.json")
    open(src, "w", encoding="utf-8").write(core + "\n" + tail)
    subprocess.run(["node", src, out], check=True, env={**os.environ, "TZ": "Asia/Seoul"})
    v = json.load(open(out, encoding="utf-8"))
extra = json.load(open(os.path.join(HERE, "vocabulary_extra.json"), encoding="utf-8"))
for ht in v["houseTypes"].values(): ht.pop("devices", None)
v["houseTypes"]["_deviceIds"] = extra.pop("houseTypes._deviceIds")
v.update(extra)
json.dump(v, open(os.path.join(HERE, "vocabulary.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("vocabulary.json written:", ", ".join(f"{k} {len(x) if hasattr(x, '__len__') else ''}" for k, x in v.items() if not k.startswith("_")))
