"""Compares the shape of two runs' phone logs (after expand) (JS runner vs Python runner): for each kind of line, the field paths and value types.
usage: python3 tests/compare_outputs.py <js_out_dir> <py_out_dir>"""
import json, sys, os, collections
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from smarthome_sim.formats import expand


def paths(o, pre=""):
    if isinstance(o, dict):
        out = set()
        for k, v in o.items():
            out |= paths(v, f"{pre}.{k}" if pre else k)
        return out
    t = "null" if o is None else "bool" if isinstance(o, bool) else "num" if isinstance(o, (int, float)) else "str" if isinstance(o, str) else "list"
    return {f"{pre}:{t}"}


def shapes(path, kind):
    S = collections.defaultdict(set)
    n = collections.Counter()
    for l in open(path, encoding="utf-8"):
        e = expand(json.loads(l))
        k = (e["source"], e["device"]) if kind == "home" else (e["type"], (e.get("payload") or {}).get("kind", ""))
        S[k] |= paths(e)
        n[k] += 1
    return S, n


ok = True
for f, kind in (("phone_log.jsonl", "phone"),):
    a, na = shapes(f"{sys.argv[1]}/{f}", kind)
    b, nb = shapes(f"{sys.argv[2]}/{f}", kind)
    for k in sorted(set(a) | set(b), key=str):
        if k not in a or k not in b:
            print(f, k, "only in", "JS" if k in a else "Python", f"({na[k] or nb[k]} lines)")
            continue
        da, db = a[k] - b[k], b[k] - a[k]
        if da or db:
            ok = False
            print(f, k, "JS-only fields:", sorted(da)[:8], "Python-only fields:", sorted(db)[:8])
    print(f, "kinds:", len(a), "vs", len(b), "| lines:", sum(na.values()), "vs", sum(nb.values()))
print("same field shapes" if ok else "differences above")
