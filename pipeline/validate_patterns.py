#!/usr/bin/env python3
"""Check structured patterns (the API's output) against pattern.schema.json and vocabulary.json.

usage: python3 validate_patterns.py structured_patterns.json [--vocab vocabulary.json] [--schema pattern.schema.json]
The input is a JSON array of structured patterns (or one object, or JSONL with one pattern per line).
Prints ERROR lines (the engine cannot run the pattern) and WARN lines (it can, but check it). Exit code 1 if any ERROR.
"""
import json, sys, argparse, os

HERE = os.path.dirname(os.path.abspath(__file__))


def load_patterns(path):
    text = open(path, encoding="utf-8").read().strip()
    if text.startswith("["):
        return json.loads(text)
    if text.startswith("{") and "\n{" not in text:
        return [json.loads(text)]
    return [json.loads(l) for l in text.splitlines() if l.strip()]


class Checker:
    def __init__(self, vocab):
        self.v = vocab
        self.apps = set(vocab["apps"]) | {k for k in vocab["extraApps"] if not k.startswith("_")}
        self.out = []

    def err(self, pid, msg): self.out.append(("ERROR", pid, msg))
    def warn(self, pid, msg): self.out.append(("WARN", pid, msg))

    # ---- names ----
    def room(self, p, name, where):
        rooms = self.v["houseTypes"][p["houseType"]]["rooms"]
        real = p["roomRoles"].get(name, name)
        if real not in rooms:
            self.err(p["patternId"], f"{where}: room '{name}' is not a room of {p['houseType']} (rooms: {', '.join(rooms)}) and not in roomRoles")
            return None
        return real

    def device(self, p, ref, where):
        """ref = '<room or role>.<deviceType>' -> (deviceType spec, real room) or None"""
        if not isinstance(ref, str) or "." not in ref:
            self.err(p["patternId"], f"{where}: device '{ref}' is not '<room>.<deviceType>'"); return None
        room, dtype = ref.rsplit(".", 1)
        spec = self.v["deviceTypes"].get(dtype)
        if not spec:
            self.err(p["patternId"], f"{where}: unknown device type '{dtype}'"); return None
        real = self.room(p, room, where)
        if real and real not in spec["rooms"]:
            self.err(p["patternId"], f"{where}: there is no {dtype} in {real} (it exists in: {', '.join(spec['rooms'])})"); return None
        return spec

    def cap_attr(self, p, spec, cap, attr, where):
        c = next((c for c in spec["capabilities"] if c["capability"] == cap), None)
        if not c:
            self.err(p["patternId"], f"{where}: capability '{cap}' not on this device (has: {', '.join(x['capability'] for x in spec['capabilities'])})"); return None, None
        a = next((a for a in c["attributes"] if a["name"] == attr), None) if attr else None
        if attr and not a:
            self.err(p["patternId"], f"{where}: attribute '{attr}' not in {cap} (has: {', '.join(x['name'] for x in c['attributes'])})")
        return c, a

    def value(self, p, a, op, val, where):
        if not a: return
        vals = a.get("values")
        items = val if isinstance(val, list) else [val]
        if vals:
            for x in items:
                if x not in vals: self.err(p["patternId"], f"{where}: value '{x}' not allowed for {a['name']} (allowed: {', '.join(map(str, vals))})")
        elif a["type"] in ("number", "integer"):
            for x in items:
                if not isinstance(x, (int, float)): self.err(p["patternId"], f"{where}: {a['name']} needs a number, got {x!r}")

    def place(self, p, name, where):
        names = name if isinstance(name, list) else [name]
        for n in names:
            if n not in self.v["places"]: self.err(p["patternId"], f"{where}: unknown place '{n}'")

    # ---- parts ----
    def action(self, p, act, where, match=False):
        """match=True: the action is a recent_action pattern; the engine compares only the fields given,
        so a missing 'args' list matches any arguments"""
        do, args = act.get("do"), act.get("args", {})
        if do not in self.v["personActions"]:
            self.err(p["patternId"], f"{where}: unknown action '{do}'"); return
        if do == "home.command":
            spec = self.device(p, args.get("device"), where)
            if spec:
                c, _ = self.cap_attr(p, spec, args.get("capability"), None, where)
                if c:
                    m = next((m for m in c["commands"] if m["name"] == args.get("command")), None)
                    if not m: self.err(p["patternId"], f"{where}: command '{args.get('command')}' not in {c['capability']} (has: {', '.join(x['name'] for x in c['commands']) or 'none'})")
                    elif match and "args" not in args: pass
                    elif len(args.get("args", [])) != len(m["args"]): self.err(p["patternId"], f"{where}: {m['name']} takes {len(m['args'])} argument(s) {m['args']}, got {args.get('args')}")
                    elif m["name"].startswith("set") and m["args"] and c["attributes"]:
                        self.value(p, c["attributes"][0], "==", args["args"][0], where)
            if args.get("channel") not in ("physical", "mobile_app"):
                self.err(p["patternId"], f"{where}: channel must be physical or mobile_app")
        elif do == "home.record":
            spec = self.device(p, args.get("device"), where)
            if spec:
                _, a = self.cap_attr(p, spec, args.get("capability"), args.get("attribute"), where)
                self.value(p, a, "==", args.get("value"), where)
        elif do == "person.travel":
            self.place(p, args.get("to"), where)
            if args.get("mode") not in self.v["travelModes"]: self.err(p["patternId"], f"{where}: unknown travel mode '{args.get('mode')}'")
        elif do == "person.moveRoom":
            self.room(p, args.get("room"), where)
        elif do in ("phone.openApp", "phone.appNotice", "phone.uninstall"):
            if args.get("package") not in self.apps: self.err(p["patternId"], f"{where}: unknown app '{args.get('package')}' (add it to extraApps if needed)")
        elif do == "phone.useApps":
            pid = p["patternId"]
            for k in ("first", "next"):
                w = args.get(k)
                if w is None and k == "next":
                    continue
                if not isinstance(w, dict) or not w:
                    self.err(pid, f"{where}: {k} must be a non-empty {{package: weight}} object"); continue
                for pkg, x in w.items():
                    if pkg not in self.apps: self.err(pid, f"{where}: {k}: unknown app '{pkg}' (add it to extraApps if needed)")
                    if not isinstance(x, (int, float)) or x < 0: self.err(pid, f"{where}: {k}: weight of {pkg} must be a number >= 0")
            c = args.get("continue", 0.32)
            if not isinstance(c, (int, float)) or not 0 <= c < 1: self.err(pid, f"{where}: continue must be a number in [0, 1)")
            ck = args.get("check")
            if ck is not None:
                if not isinstance(ck, dict): self.err(pid, f"{where}: check must be an object")
                else:
                    sh = ck.get("share", 0)
                    if not isinstance(sh, (int, float)) or not 0 <= sh <= 1: self.err(pid, f"{where}: check.share must be in [0, 1]")
                    for pkg in (ck.get("first") or {}):
                        if pkg not in self.apps: self.err(pid, f"{where}: check.first: unknown app '{pkg}'")
                    d = ck.get("seconds")
                    if d is not None and (not isinstance(d, dict) or not isinstance(d.get("median"), (int, float)) or d["median"] <= 0):
                        self.err(pid, f"{where}: check.seconds must be {{median > 0, sigma >= 0}}")
            for key, d in (args.get("seconds") or {}).items():
                if key != "default" and key not in self.apps: self.err(pid, f"{where}: seconds: unknown app '{key}'")
                if not isinstance(d, dict) or not isinstance(d.get("median"), (int, float)) or d["median"] <= 0 or not isinstance(d.get("sigma"), (int, float)) or d["sigma"] < 0:
                    self.err(pid, f"{where}: seconds.{key} must be {{median > 0, sigma >= 0}}")
        elif do in ("phone.btConnect", "phone.btDisconnect"):
            if args.get("name") not in self.v["bluetoothDevices"]: self.err(p["patternId"], f"{where}: unknown bluetooth device '{args.get('name')}'")
        elif do == "phone.setActivity":
            if args.get("activity") not in ("WALKING", "RUNNING", "ON_BICYCLE", "STILL"): self.err(p["patternId"], f"{where}: activity '{args.get('activity')}' cannot be set directly")
        elif do == "phone.exerciseStart":
            if args.get("kind") not in self.v["exercises"]: self.err(p["patternId"], f"{where}: unknown exercise '{args.get('kind')}'")
        elif do == "phone.measure":
            if args.get("source") not in self.v["healthMeasures"]: self.err(p["patternId"], f"{where}: unknown health measure '{args.get('source')}'")
        elif do == "phone.media":
            if args.get("state") not in ("PLAYING", "PAUSED", "STOPPED"): self.err(p["patternId"], f"{where}: media state must be PLAYING, PAUSED or STOPPED")
        if "revert" in act:
            self.action(p, act["revert"]["action"], where + ".revert")
        for i, c in enumerate(act.get("when", [])):
            self.condition(p, c, f"{where}.when[{i}]")

    def condition(self, p, c, where):
        k = c.get("kind")
        if k == "place": self.place(p, c["place"], where)
        elif k == "room": self.room(p, c["room"], where)
        elif k == "device":
            spec = self.device(p, c["device"], where)
            if spec:
                _, a = self.cap_attr(p, spec, c["capability"], c["attribute"], where)
                self.value(p, a, c["op"], c["value"], where)
        elif k == "weather":
            for x in (c["value"] if isinstance(c["value"], list) else [c["value"]]):
                if x not in self.v["weather"]["states"]: self.err(p["patternId"], f"{where}: unknown weather '{x}'")
        elif k == "outdoor":
            if c["variable"] not in self.v["weather"]["outdoorVariables"]: self.err(p["patternId"], f"{where}: unknown outdoor variable '{c['variable']}'")
        elif k == "phone_event":
            if c["type"] not in self.v["phoneEventTypes"]: self.err(p["patternId"], f"{where}: unknown phone event type '{c['type']}'")
        elif k == "health":
            if c["field"] not in self.v["healthRecords"][c["record"]]: self.err(p["patternId"], f"{where}: {c['record']} has no field '{c['field']}'")
        elif k == "recent_action":
            self.action(p, c["action"], where + ".action", match=True)

    def event(self, p, e, where):
        s = e.get("source")
        if s == "home":
            spec = self.v["deviceTypes"].get(e["deviceType"])
            if not spec: self.err(p["patternId"], f"{where}: unknown device type '{e['deviceType']}'"); return
            if e.get("room"): self.device(p, f"{e['room']}.{e['deviceType']}", where)
            _, a = self.cap_attr(p, spec, e["capability"], e["attribute"], where)
            self.value(p, a, "==", e["value"], where)
        elif s == "phone":
            if e["type"] not in self.v["phoneEventTypes"]: self.err(p["patternId"], f"{where}: unknown phone event type '{e['type']}'")
            if e.get("category") and e["category"] not in [x["category"] for x in self.v["smartThingsAlerts"]]:
                self.err(p["patternId"], f"{where}: unknown SmartThings alert category '{e['category']}'")
        elif s == "person":
            if e.get("place"): self.place(p, e["place"], where)
            if e.get("room"): self.room(p, e["room"], where)
        elif s == "weather":
            for x in [e.get("from"), e.get("to")]:
                if x and x not in self.v["weather"]["states"]: self.err(p["patternId"], f"{where}: unknown weather '{x}'")

    def pattern(self, p):
        pid = p.get("patternId", "?")
        if p.get("houseType") not in self.v["houseTypes"]:
            self.err(pid, f"houseType '{p.get('houseType')}' unknown"); return
        for role, room in p.get("roomRoles", {}).items():
            if room not in self.v["houseTypes"][p["houseType"]]["rooms"]: self.err(pid, f"roomRoles.{role} = '{room}' is not a room of {p['houseType']}")
        t = p["trigger"]
        if t["kind"] == "event": self.event(p, t["event"], "trigger")
        for i, c in enumerate(p["conditions"]): self.condition(p, c, f"conditions[{i}]")
        for i, a in enumerate(p["actions"]): self.action(p, a, f"actions[{i}]")
        if p.get("shift"):
            for i, a in enumerate(p["shift"]["before"]): self.action(p, a, f"shift.before[{i}]")
        for i, pr in enumerate(p.get("prerequisites", [])):
            sp = pr.get("spec", {})
            if sp.get("place"): self.place(p, sp["place"], f"prerequisites[{i}]")
            if sp.get("travelMode") and sp["travelMode"] not in self.v["travelModes"]: self.err(pid, f"prerequisites[{i}]: unknown travel mode '{sp['travelMode']}'")
            if sp.get("device"): self.device(p, sp["device"], f"prerequisites[{i}]")
            if sp.get("action"): self.action(p, sp["action"], f"prerequisites[{i}].action")
        # consistency warnings
        if (p["patternType"] == "preference_shift") != bool(p.get("shift")):
            self.warn(pid, "shift must be set for preference_shift and null otherwise")
        away = any(c.get("kind") == "place" and ((c["op"] == "is_not" and c["place"] == "home") or (c["op"] == "is" and c["place"] != "home")) for c in p["conditions"])
        moves = any(a["do"] == "person.travel" for a in p["actions"])
        if away and not moves:
            for i, a in enumerate(p["actions"]):
                if a["do"] in ("home.command", "home.record") and a["args"].get("channel") != "mobile_app":
                    self.warn(pid, f"actions[{i}]: the person is away but acts on a home device by hand (use channel mobile_app)")
        for c in p["conditions"]:
            if c.get("kind") == "calendar" and not any(pr["kind"] == "calendar" and c["titleContains"].lower() in pr["spec"].get("title", "").lower() for pr in p.get("prerequisites", [])):
                self.warn(pid, f"calendar condition '{c['titleContains']}' has no calendar prerequisite that creates such events")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns")
    ap.add_argument("--vocab", default=os.path.join(HERE, "vocabulary.json"))
    ap.add_argument("--schema", default=os.path.join(HERE, "pattern.schema.json"))
    a = ap.parse_args()
    vocab = json.load(open(a.vocab, encoding="utf-8"))
    schema = json.load(open(a.schema, encoding="utf-8"))
    pats = load_patterns(a.patterns)
    chk = Checker(vocab)
    try:
        import jsonschema
        validator = jsonschema.Draft202012Validator(schema)
    except ImportError:
        validator = None
        print("WARN - jsonschema is not installed (pip install jsonschema); only the vocabulary checks run")
    for p in pats:
        pid = p.get("patternId", "?") if isinstance(p, dict) else "?"
        if validator:
            errs = sorted(validator.iter_errors(p), key=lambda e: list(e.absolute_path))
            for e in errs: chk.err(pid, f"schema: {'/'.join(map(str, e.absolute_path)) or '(top)'}: {e.message[:200]}")
            if errs: continue
        chk.pattern(p)
    for level, pid, msg in chk.out: print(f"{level} {pid}: {msg}")
    n_err = sum(1 for x in chk.out if x[0] == "ERROR")
    print(f"{len(pats)} pattern(s), {n_err} error(s), {sum(1 for x in chk.out if x[0] == 'WARN')} warning(s)")
    sys.exit(1 if n_err else 0)


if __name__ == "__main__":
    main()
