#!/usr/bin/env python3
"""Check an agent profile (profiles/<personaId>.json) before running it.

usage: python3 check_profile.py profiles/063.json
Checks: agent_profile.schema.json (with pattern.schema.json for trigger / condition / action),
every name against vocabulary.json (same checks as validate_patterns.py, each {"choice": [...]} option checked),
and each kind 'pattern' behaviour's embedded structured pattern with validate_patterns.py's checks.
Exit code 1 if any ERROR.
"""
import json, sys, os, copy, itertools
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from validate_patterns import Checker


def expand(obj):
    """all variants of obj with every {"choice": [...]} replaced by one option"""
    if isinstance(obj, dict):
        if "choice" in obj and set(obj) <= {"choice", "weights"}:
            return [x for opt in obj["choice"] for x in expand(opt)]
        keys = list(obj)
        out = []
        for combo in itertools.product(*[expand(obj[k]) for k in keys]):
            out.append(dict(zip(keys, combo)))
        return out
    if isinstance(obj, list):
        return [list(c) for c in itertools.product(*[expand(x) for x in obj])] if obj else [[]]
    return [obj]


def main():
    path = sys.argv[1]
    prof = json.load(open(path, encoding="utf-8"))
    vocab = json.load(open(os.path.join(HERE, "vocabulary.json"), encoding="utf-8"))
    out = []
    try:
        import jsonschema
        from referencing import Registry, Resource
        ps = json.load(open(os.path.join(HERE, "pattern.schema.json")))
        prs = json.load(open(os.path.join(HERE, "agent_profile.schema.json")))
        reg = Registry().with_resource("pattern.schema.json", Resource.from_contents(ps))
        # choice objects are not in pattern.schema.json: validate the schema on one expansion per behaviour
        flat = copy.deepcopy(prof)
        flat["behaviours"] = [expand(b)[0] for b in prof["behaviours"]]
        for e in jsonschema.Draft202012Validator(prs, registry=reg).iter_errors(flat):
            out.append(("ERROR", "schema", f"{'/'.join(map(str, e.absolute_path)) or '(top)'}: {e.message[:200]}"))
        for b in prof["behaviours"]:
            if b["kind"] == "pattern" and "pattern" in b:
                for e in jsonschema.Draft202012Validator(ps).iter_errors(b["pattern"]):
                    out.append(("ERROR", b["id"], f"pattern schema: {'/'.join(map(str, e.absolute_path))}: {e.message[:200]}"))
    except ImportError:
        out.append(("WARN", "-", "jsonschema / referencing not installed; schema part skipped"))
    chk = Checker(vocab)
    if prof["houseType"] not in vocab["houseTypes"]:
        out.append(("ERROR", "-", f"houseType {prof['houseType']} unknown"))
    elif prof["variant"] not in vocab["houseTypes"][prof["houseType"]]["variants"]:
        out.append(("ERROR", "-", f"variant {prof['variant']} not in {vocab['houseTypes'][prof['houseType']]['variants']}"))
    if prof["start"]["place"] not in vocab["places"]:
        out.append(("ERROR", "start", f"unknown place {prof['start']['place']}"))
    ids = [b["id"] for b in prof["behaviours"]]
    for d in {i for i in ids if ids.count(i) > 1}:
        out.append(("ERROR", d, "duplicate behaviour id"))
    for b in prof["behaviours"]:
        for var in expand({k: b[k] for k in ("trigger", "conditions", "actions")}):
            p = {"patternId": b["id"], "houseType": prof["houseType"], "roomRoles": prof["roomRoles"], "patternType": "temporal_numeric",
                 "trigger": var["trigger"], "conditions": var["conditions"], "actions": var["actions"], "shift": None, "prerequisites": []}
            chk.pattern(p)
        if b["kind"] == "pattern" and "pattern" in b:
            chk.pattern(b["pattern"])
    seen = set()
    for x in chk.out + out:
        if x in seen: continue
        seen.add(x); print(f"{x[0]} {x[1]}: {x[2]}")
    n_err = sum(1 for x in seen if x[0] == "ERROR")
    print(f"{len(prof['behaviours'])} behaviour(s) ({sum(b['kind'] == 'pattern' for b in prof['behaviours'])} pattern), {n_err} error(s), {sum(1 for x in seen if x[0] == 'WARN')} warning(s)")
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
