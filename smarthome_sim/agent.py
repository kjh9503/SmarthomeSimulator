"""Agent runner: drives one simulated person through the simulator for N days following an agent profile, and writes
the home log and the phone log. Python port of agent/engine/run_agent.js (same rules; see README.md).

    python -m smarthome_sim.run --profile profiles/063.json --out out/063
"""
import json
import math
import os
import random
import time as _time

from .simulator import Simulator
from .phone import ST_ALERTS
from .timeutil import (DAY_MS, MIN_MS, fields, local_ms, start_of_day, iso_local, js_round)
from .weather import outdoor_at
from .formats import compact

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOW = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
BODY_DO = {"person.travel", "person.moveRoom", "home.record"}
DEFER_MAX_MIN = 180  # a daily behaviour waits at most this long after its minute


def _norm(v):
    """numbers as JavaScript prints them (22.0 -> 22), internal keys dropped"""
    if isinstance(v, float):
        return int(v) if v.is_integer() else v
    if isinstance(v, dict):
        return {k: _norm(x) for k, x in v.items() if k != "_t"}
    if isinstance(v, (list, tuple)):
        return [_norm(x) for x in v]
    return v


def dumps(e):
    return json.dumps(_norm(e), ensure_ascii=False, separators=(",", ":"))


def hhmm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def minute_of_day(t):
    f = fields(t)
    return f[3] * 60 + f[4]


def day_key(t):
    f = fields(t)
    return f"{f[0]:04d}-{f[1] + 1:02d}-{f[2]:02d}"


def day_ok(days, t):
    if not days or days == "all":
        return True
    w = DOW[fields(t)[6]]
    if days == "weekdays":
        return w not in ("sat", "sun")
    if days == "weekends":
        return w in ("sat", "sun")
    return w in days


def month_ok(months, t):
    return not months or fields(t)[1] + 1 in months


def window_day(win, t):
    """the day a time window belongs to (a window past midnight belongs to the day it starts), or None outside it"""
    f, to, m, d0 = hhmm(win["from"]), hhmm(win["to"]), minute_of_day(t), start_of_day(t)
    if f <= to:
        return d0 if f <= m <= to else None
    if m >= f:
        return d0
    if m <= to:
        return start_of_day(d0 - 12 * 3600000)
    return None


def _same(a, b):
    if a is b or a == b and type(a) is type(b):
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return False
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return a == b
    return a is not None and b is not None and str(a) == str(b)


def cmp(a, op, b):
    try:
        if op == "==":
            return _same(a, b)
        if op == "!=":
            return not _same(a, b)
        if op == "<":
            return a is not None and a < b
        if op == "<=":
            return a is not None and a <= b
        if op == ">":
            return a is not None and a > b
        if op == ">=":
            return a is not None and a >= b
        if op == "in":
            return isinstance(b, list) and a in b
        if op == "not_in":
            return isinstance(b, list) and a not in b
        if op == "contains":
            return b in a if isinstance(a, list) else str(b) in str(a if a is not None else "")
    except TypeError:
        return False
    return False


def subset(a, b):
    if isinstance(a, dict):
        return isinstance(b, dict) and all(subset(v, b.get(k)) for k, v in a.items())
    return json.dumps(a) == json.dumps(b)


class AgentRunner:
    def __init__(self, profile, out_dir, days=None, seed=None, trace=False, off_rules=None, vocabulary=None, log=print, home_log=False, full_format=False):
        self.P = profile
        self.out_dir = out_dir
        self.days = int(days or profile["simulation"]["days"])
        self.seed = int(seed if seed is not None else profile["simulation"]["seed"])
        self.OFF = json.load(open(off_rules or os.path.join(HERE, "off_rules.json"), encoding="utf-8"))
        vp = vocabulary or os.path.join(REPO, "pipeline", "vocabulary.json")
        self.VOCAB = json.load(open(vp, encoding="utf-8")) if os.path.exists(vp) else None
        self.print = log
        self.full_format = full_format  # False: SMARTTHINGS copies stored without the fields other fields determine (formats.py)
        self.write_home = home_log  # the home lines also reach the phone log as SMARTTHINGS copies; home_log.jsonl only on request
        self.rnd = random.Random(self.seed * 104729 + 7)  # the person's choices
        y0, m0, d0 = (int(x) for x in profile["simulation"]["startDate"].split("-"))
        self.T0 = local_ms(y0, m0 - 1, d0)
        self.TEND = local_ms(y0, m0 - 1, d0 + self.days)
        self.sim = Simulator(profile["variant"], self.T0, seed=self.seed * 7919 + 1)  # the simulator's own noise
        self.sim.jump_to(self.T0)
        self.phone = self.sim.phone
        self.S = self.phone.s
        self.roles = profile.get("roomRoles") or {}
        os.makedirs(out_dir, exist_ok=True)
        self.trace_f = open(os.path.join(out_dir, "trace.jsonl"), "w", encoding="utf-8") if trace else None
        self.happenings, self.recent_phone, self.recent_weather, self.action_history = [], [], [], []
        self.scheduled, self.tasks = [], []
        self.minute_ms, self.sec = self.T0, 0
        self.stats, self.cook_times, self.left_overnight = {}, [], []
        self.check_stats = {k: dict(checked=0, turnedOff=0, leftOn=0) for k in ("bedtime", "leaving", "morning")}
        cm = profile.get("cookingMinutes")
        self.cook_default = cm or dict(dist="lognormal", median=15, sigma=0.6)
        self.behaviours = [dict(b, _st={}, _firings=0) for b in profile["behaviours"]]
        self._setup_start()
        self._hooks()
        self.prev_person = self._snap()

    # ----- helpers -----
    def uni(self, a, b):
        return a + (b - a) * self.rnd.random()

    def chance(self, p):
        return self.rnd.random() < p

    def num(self, x):
        return self.uni(x["min"], x["max"]) if isinstance(x, dict) and "min" in x else float(x)

    def pick(self, opts, w):
        if not w:
            return opts[int(self.rnd.random() * len(opts))]
        r = self.rnd.random() * sum(w)
        for o, x in zip(opts, w):
            r -= x
            if r <= 0:
                return o
        return opts[-1]

    def resolve(self, v):
        if isinstance(v, list):
            return [self.resolve(x) for x in v]
        if isinstance(v, dict):
            if isinstance(v.get("choice"), list) and set(v) <= {"choice", "weights"}:
                return self.resolve(self.pick(v["choice"], v.get("weights")))
            return {k: self.resolve(x) for k, x in v.items()}
        return v

    def real_room(self, r):
        return self.roles.get(r, r)

    def dev_id(self, ref):
        i = ref.rfind(".")
        return f"{self.real_room(ref[:i])}.{ref[i + 1:]}"

    def now(self):
        return self.sim.clock.now()

    def advance_seconds(self):
        self.sec = min(59, self.sec + 3 + int(self.rnd.random() * 13))
        self.sim.clock.set_to(self.minute_ms + self.sec * 1000)

    def trace(self, o):
        if self.trace_f:
            self.trace_f.write(dumps(o) + "\n")

    def stat(self, bid):
        return self.stats.setdefault(bid, dict(triggered=0, conditionsTrue=0, followed=0, notFollowed=0,
                                               steps=dict(done=0, no_change=0, skipped=0, refused=0), refusals={}))

    # ----- set-up -----
    def _setup_start(self):
        st, S, ph = self.P.get("start") or dict(place="home"), self.S, self.phone
        if st["place"] != "home":
            ph.teleport(st["place"])
        elif st.get("room"):
            ph.move_room(self.real_room(st["room"]))
        if st.get("battery") is not None:
            S["battery"] = st["battery"]
        if st.get("asleep"):
            S["asleep"], S["sleepStart"], S["screenOn"] = True, self.T0, False
        # apps the profile uses that are not installed: present from the start (no install event)
        import re
        for p in sorted(set(re.findall(r'"((?:com|us|net|org|kr|jp)\.[a-z0-9_.]+)"', json.dumps(self.P), re.I))):
            if p in S["installed"] or not self.VOCAB:
                continue
            ex = (self.VOCAB.get("extraApps") or {}).get(p)
            if ex or p in (self.VOCAB.get("apps") or {}):
                S["installed"].append(p)
                if isinstance(ex, dict):  # fixed label / uid / data rate from vocabulary_extra.json
                    app = dict(label=ex.get("label") or p, uid=ex.get("uid") or 10200 + len(S["installed"]), mbPerMin=ex.get("mbPerMin", 1))
                else:  # older form "package": "label" (e.g. added by rewrite/apply_rewrites.py)
                    app = dict(label=ex or p, uid=10200 + len(S["installed"]), mbPerMin=1)
                self.phone.apps.setdefault(p, app)

    def _hooks(self):
        sim, ph = self.sim, self.phone
        add = sim.log.add

        def log_add(e, t=None):
            add(e, t)
            if e["_t"] >= self.now() - 2 * MIN_MS:
                self.happenings.append(("home", e))

        sim.log.add = log_add

        def on_emit(e):
            self.recent_phone.append(e)
            self.happenings.append(("phone", e))

        ph.on_emit = on_emit

        def on_copy(entries, copies):
            # SMARTTHINGS copies go straight into the phone's list: show the fresh ones to the triggers too
            fresh = {id(e) for e in entries if e["_t"] >= self.now() - 2 * MIN_MS}
            if not fresh:
                return
            for c in copies:
                self.recent_phone.append(c)
                self.happenings.append(("phone", c))

        ph.on_copy = on_copy

    def _snap(self):
        S = self.S
        tr = S["trip"]
        return dict(place=S["place"], trip=dict(frm=tr.get("frm"), to=tr["to"]) if tr else None, room=S["room"], asleep=S["asleep"])

    def person_changes(self):
        a, b = self.prev_person, self._snap()
        self.prev_person = b
        H = self.happenings
        if not a["trip"] and b["trip"]:
            H.append(("person", dict(what="depart", place=b["trip"]["frm"])))
        if a["trip"] and not b["trip"]:
            H.append(("person", dict(what="arrive", place=b["place"])))
        if b["room"] and b["room"] != a["room"]:
            H.append(("person", dict(what="enter_room", room=b["room"], place="home")))
        if a["asleep"] and not b["asleep"]:
            H.append(("person", dict(what="wake", place=b["place"])))
        if not a["asleep"] and b["asleep"]:
            H.append(("person", dict(what="fall_asleep", place=b["place"])))

    # ----- conditions -----
    def device_value(self, ref, cap, attr):
        d = self.sim.house.device(self.dev_id(ref))
        if not d:
            return None
        if d.type == "light_sensor" and attr == "illuminance":  # brightness is seen: the room's actual light level
            return self.sim.house.env.rooms[d.roomId]["illuminance"]
        return d.get(cap, attr)

    def phone_field(self, f):
        S = self.S
        return dict(screenOn=S["screenOn"], charging=S["charging"], battery=js_round(S["battery"]), activity=S["activity"], asleep=S["asleep"],
                    bluetooth=list(S["bt"]), wifi=S["wifi"], foregroundApp=S["foreground"]).get(f) if f != "media.state" else \
            (S["media"]["state"] if S["media"] else "STOPPED")

    def calendar_cond(self, c, t):
        evs = [e for e in self.S["calendar"].values() if c["titleContains"].lower() in str(e["title"]).lower()]
        ds = start_of_day(t)
        de = ds + DAY_MS
        rel = c["relation"]
        if rel == "starts_within":
            return any(t < e["begin"] <= t + (c.get("minutes") or 0) * MIN_MS for e in evs)
        if rel == "ongoing":
            return any(e["begin"] <= t < e["end"] for e in evs)
        if rel == "today":
            return any(ds <= e["begin"] < de for e in evs)
        if rel == "none_today":
            return not any(ds <= e["begin"] < de for e in evs)
        if rel == "starts_before":
            return any(ds <= e["begin"] < de and minute_of_day(e["begin"]) <= hhmm(c["time"]) for e in evs)
        return False

    @staticmethod
    def match_phone_event(e, c):
        p = e.get("payload") or {}
        if c.get("type") and e["type"] != c["type"]:
            return False
        if c.get("eventSource") and e["source"] != c["eventSource"]:
            return False
        if c.get("action") and p.get("action") != c["action"]:
            return False
        if c.get("category") and p.get("category", (p.get("notification") or {}).get("category")) != c["category"]:
            return False
        if c.get("textContains") and c["textContains"].lower() not in str(e.get("text") or "").lower():
            return False
        if c.get("titleContains") and c["titleContains"].lower() not in str(e.get("title") or "").lower():
            return False
        if c.get("field") and not cmp(p.get(c["field"]), c.get("op"), c.get("value")):
            return False
        return True

    def cond(self, c, t):
        k = c["kind"]
        S = self.S
        if k == "time":
            return window_day(c["window"], t) is not None
        if k == "day":
            return day_ok(c["days"], t)
        if k == "month":
            return month_ok(c["months"], t)
        if k == "place":
            ps = c["place"] if isinstance(c["place"], list) else [c["place"]]
            if c["op"] == "is_not":
                return S["place"] not in ps or bool(S["trip"])
            return S["place"] in ps and not S["trip"]
        if k == "room":
            return S["place"] == "home" and S["room"] == self.real_room(c["room"])
        if k == "device":
            return cmp(self.device_value(c["device"], c["capability"], c["attribute"]), c["op"], c["value"])
        if k == "weather":
            if c.get("withinMinutes"):
                return any(wt >= t - c["withinMinutes"] * MIN_MS and cmp(w, c["op"], c["value"]) for wt, w in self.recent_weather)
            return cmp(outdoor_at(t)["weather"], c["op"], c["value"])
        if k == "outdoor":
            return cmp(outdoor_at(t).get(c["variable"]), c["op"], c["value"])
        if k == "calendar":
            return self.calendar_cond(c, t)
        if k == "phone_event":
            hit = any(e["timestamp"] >= t - c["withinMinutes"] * MIN_MS and self.match_phone_event(e, c) for e in self.recent_phone)
            return not hit if c.get("negate") else hit
        if k == "phone_state":
            return cmp(self.phone_field(c["field"]), c["op"], c["value"])
        if k == "health":
            evs = [e for e in self.recent_phone if e["type"] == "HEALTH" and e["source"] == c["record"]
                   and (not c.get("withinMinutes") or e["timestamp"] >= t - c["withinMinutes"] * MIN_MS)]
            return bool(evs) and cmp(evs[-1]["payload"].get(c["field"]), c["op"], c["value"])
        if k == "recent_action":
            hit = any(at >= t - c["withinMinutes"] * MIN_MS and d == c["action"]["do"] and subset(c["action"].get("args") or {}, a)
                      for at, d, a in self.action_history)
            return not hit if c.get("negate") else hit
        raise ValueError("unknown condition kind " + k)

    def all_conds(self, cs, t):
        return all(self.cond(c, t) for c in (cs or []))

    # ----- the person's actions -----
    def go_to(self, room):
        S = self.S
        if S["place"] != "home" or S["trip"] or S["asleep"] or S["room"] == room:
            return
        self.phone.move_room(room)
        self.person_changes()

    def exec(self, a):
        args = a.get("args") or {}
        sim, ph, S = self.sim, self.phone, self.S
        self.advance_seconds()
        t = self.now()

        def done(n):
            if n > 0:
                return dict(result="done")
            return dict(result="refused", reason=sim.last_refusal) if sim.last_refusal else dict(result="no_change")

        def refused(reason):
            return dict(result="refused", reason=reason)

        def awake():
            return refused("asleep") if S["asleep"] else refused("driving") if ph.driving else None

        do = a["do"]
        if do == "home.command":
            did = self.dev_id(args["device"])
            d = sim.house.device(did)
            if not d:
                out = refused("no such device " + did)
            elif args.get("channel") == "mobile_app":
                out = done(ph.control_home(did, args["capability"], args["command"], args.get("args") or []))
            else:
                self.go_to(d.roomId)
                out = done(sim.run(did, args["capability"], args["command"], args.get("args") or [], "physical"))
        elif do == "home.record":
            did = self.dev_id(args["device"])
            d = sim.house.device(did)
            if not d:
                out = refused("no such device " + did)
            else:
                if not (d.id == "balcony.door_contact" and S["room"] == "living_room"):
                    self.go_to(d.roomId)
                out = done(sim.set_value(did, args["capability"], args["attribute"], args["value"]))
        elif do == "person.travel":
            if S["trip"]:
                out = refused("already travelling")
            elif S["asleep"]:
                out = refused("asleep")
            else:
                if S["place"] == "home":
                    self.off_check("leaving", t)
                self.advance_seconds()
                n = ph.travel(args["to"], args["mode"])
                if n > 0 or S["trip"]:
                    out = dict(result="done", block=dict(travelTo=args["to"]))
                else:
                    out = dict(result="no_change") if args["to"] == S["place"] else refused(sim.last_refusal or "refused")
        elif do == "person.moveRoom":
            out = done(ph.move_room(self.real_room(args["room"])))
        elif do == "phone.screen":
            out = done(ph.screen(args.get("on") in (True, "true")))
        elif do == "phone.openApp":
            out = done(ph.open_app(args["package"]))
        elif do == "phone.closeApp":
            out = done(ph.close_app())
        elif do == "phone.install":
            out = done(ph.install(args["package"], args.get("label")))
        elif do == "phone.uninstall":
            out = done(ph.uninstall(args["package"]))
        elif do == "phone.power":
            out = done(ph.power(args.get("connected") in (True, "true")))
        elif do == "phone.btConnect":
            out = done(ph.bt_connect(args["name"]))
        elif do == "phone.btDisconnect":
            out = done(ph.bt_disconnect(args["name"]))
        elif do == "phone.media":
            out = done(ph.media(args["state"], args.get("title") or "Song Title", args.get("artist") or "Artist Name", args.get("album") or "Album Name"))
        elif do == "phone.call":
            out = done(ph.call(args["state"]))
        elif do == "phone.sms":
            out = done(ph.sms(args.get("direction") or "OUTGOING"))
        elif do == "phone.calendarAdd":
            out = awake()
            if not out:
                b = args.get("begin")
                if isinstance(b, str) and len(b) == 5 and b[2] == ":":
                    b = start_of_day(t) + hhmm(b) * MIN_MS
                else:
                    b = int(b) if b else t
                out = done(ph.calendar_add(args["title"], b, b + int(self.num(args.get("durationMinutes") or 60)) * MIN_MS, args.get("location") or ""))
        elif do in ("phone.calendarUpdate", "phone.calendarDelete"):
            evs = [e for e in S["calendar"].values() if str(args.get("titleContains")).lower() in str(e["title"]).lower()]
            if not evs:
                out = dict(result="no_change")
            elif do == "phone.calendarUpdate":
                sh = int(self.num(args.get("shiftMinutes") or 0) * MIN_MS)
                out = done(sum(ph.calendar_update(e["eventId"], dict(begin=e["begin"] + sh, end=e["end"] + sh)) for e in evs))
            else:
                out = done(sum(ph.calendar_delete(e["eventId"]) for e in evs))
        elif do == "phone.sleep":
            out = done(ph.sleep())
        elif do == "phone.wake":
            out = done(ph.wake())
        elif do == "phone.setActivity":
            out = done(ph.set_activity(args["activity"]))
        elif do == "phone.exerciseStart":
            out = done(ph.exercise_start(args["kind"]))
        elif do == "phone.exerciseEnd":
            out = done(ph.exercise_end())
        elif do == "phone.measure":
            out = done(ph.measure(args["source"], args["value"]))
        elif do == "phone.photo":
            out = done(ph.photo())
        elif do == "phone.screenshot":
            out = done(ph.screenshot(args.get("ocrText") or ""))
        elif do == "phone.copyClipboard":
            out = done(ph.copy_clipboard(args.get("label") or "Memo"))
        elif do == "phone.appNotice":
            out = awake() or done(ph.notify(args["package"], args.get("title") or "", args.get("text") or "", "status"))
        elif do == "wait":
            out = dict(result="done", block=dict(until=t + js_round(self.num(args["minutes"])) * MIN_MS))
        else:
            out = refused("unknown action " + do)
        if out["result"] in ("done", "no_change"):
            self.action_history.append((t, do, args))
        self.person_changes()
        return out

    # ----- reverts, cooking -----
    def device_revert(self, a):
        args = a.get("args") or {}
        d = self.sim.house.device(self.dev_id(args["device"]))
        if not d:
            return 0
        t, n = self.now(), 0
        for c, at, v in d.effects(args["capability"], args["command"], args.get("args") or []):
            ch = d.set(c, at, v)
            if not ch["changed"]:
                continue
            e = self.sim.build(d, ch, "device", None, [], t, "timer")
            self.sim.log.add(e)
            self.phone.copy_home([e])
            self.sim.note_action(d, t)
            n += 1
        return n

    def gauss(self):
        r = self.rnd.random
        u = 0
        while not u:
            u = r()
        v = 0
        while not v:
            v = r()
        return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)

    def cook_minutes(self, c):
        c = c or self.cook_default
        if c["dist"] == "lognormal":
            m = c["median"] * math.exp(c["sigma"] * self.gauss())
        elif c["dist"] == "shifted_exp":
            m = (c.get("min") or 0) - c["mean"] * math.log(1 - self.rnd.random())
        else:
            m = -c["mean"] * math.log(1 - self.rnd.random())
        return max(1, js_round(m))

    def start_cooking(self, a, owner):
        mins = self.cook_minutes(a.get("cookingMinutes"))
        self.cook_times.append(mins)
        self.scheduled.append(dict(kind="revert", at=self.now() + mins * MIN_MS, byDevice=False, keep=True, owner=owner,
                                   action=dict(do="home.command", args=dict(device="kitchen.stove", capability="switch", command="off", args=[], channel="physical"))))

    # ----- checks before sleep, before leaving, after waking -----
    def rule_state(self, rule, d, t):
        if rule["deviceType"] != d.type or (rule.get("rooms") and d.roomId not in rule["rooms"]) or (rule.get("months") and not month_ok(rule["months"], t)):
            return False
        on = rule["isOn"]
        return cmp(d.get(on["capability"], on["attribute"]), on["op"], on["value"])

    def on_devices(self, t, only=None):
        out = []
        for d in self.sim.house.devices.values():
            if only is not None and d.id not in only:
                continue
            rule = next((r for r in self.OFF["rules"] if self.rule_state(r, d, t)), None)
            if rule:
                out.append((d, rule))
        for i in range(len(out) - 1, 0, -1):
            j = int(self.rnd.random() * (i + 1))
            out[i], out[j] = out[j], out[i]
        return out

    def off_check(self, moment, t, only=None):
        S = self.S
        if S["place"] != "home" or S["trip"] or S["asleep"]:
            return []
        back, left, cs = S["room"], [], self.check_stats[moment]
        for d, rule in self.on_devices(t, only):
            cs["checked"] += 1
            if not self.chance(rule["p"][moment]):
                left.append(d.id)
                cs["leftOn"] += 1
                continue
            o = rule["off"]
            a = (dict(do="home.record", args=dict(device=d.id, capability=o["capability"], attribute=o["attribute"], value=o["value"]))
                 if o["do"] == "home.record" else
                 dict(do="home.command", args=dict(device=d.id, capability=o["capability"], command=o["command"], args=o["args"], channel=o["channel"])))
            r = self.exec(a)
            if r["result"] == "done":
                cs["turnedOff"] += 1
            else:
                left.append(d.id)
                cs["leftOn"] += 1
            self.trace(dict(t=iso_local(self.now()), check=moment, device=d.id, result=r["result"], reason=r.get("reason")))
        if moment != "morning":  # the check takes over what the person meant to switch off later
            self.scheduled = [x for x in self.scheduled if not (x["kind"] == "revert" and not x["byDevice"] and not x.get("keep"))]
        if back and S["room"] != back:
            self.phone.move_room(back)
            self.person_changes()
        return left

    # ----- behaviours -----
    def shift_actions(self, b, t):
        sh = b.get("shift") or (b.get("pattern") or {}).get("shift")
        if not sh or not sh.get("before"):
            return b["actions"]
        at = sh.get("at") or {}
        tr = sh.get("transitionDays") or 0
        if at.get("monthDay"):
            mm, dd = (int(x) for x in at["monthDay"].split("-"))
            days = (t - local_ms(fields(t)[0], mm - 1, dd)) / DAY_MS
            p = 0 if days < 0 else min(1, days / tr) if tr else 1
        elif at.get("afterFirings") is not None:
            k = b["_firings"] - at["afterFirings"]
            p = 0 if k < 0 else min(1, k / tr) if tr else 1
        else:
            p = 1
        return b["actions"] if self.chance(p) else sh["before"]

    def fire(self, b, t, how):
        s = self.stat(b["id"])
        s["triggered"] += 1
        day = how.get("day") if how.get("day") is not None else start_of_day(t)
        dk = day_key(day)
        cnt = b["_st"].setdefault("count", {}).get(dk, 0)
        if cnt >= (b.get("maxPerDay") or 1):
            s["triggered"] -= 1
            s["overMaxPerDay"] = s.get("overMaxPerDay", 0) + 1
            return "max"
        if not self.all_conds(b.get("conditions"), t):
            return "conditions_false"
        s["conditionsTrue"] += 1
        if not self.chance(b["probability"]):
            s["notFollowed"] += 1
            self.trace(dict(t=iso_local(t), behaviour=b["id"], outcome="not_followed", via=how["via"]))
            return "not_followed"
        s["followed"] += 1
        b["_st"]["count"][dk] = cnt + 1
        b["_firings"] += 1
        actions = self.resolve(self.shift_actions(b, t))
        task = dict(b=b, actions=actions, i=0, until=0, travelTo=None, steps=[], start=t, via=how["via"], finished=False)
        if any(a["do"] == "phone.sleep" for a in actions):
            self.off_check("bedtime", t)
        self.tasks.append(task)
        self.run_task(task)
        return "followed"

    def run_task(self, task):
        s = self.stat(task["b"]["id"])
        acts = task["actions"]
        while task["i"] < len(acts):
            if task["until"] and self.now() < task["until"]:
                return
            if task["travelTo"]:
                if self.S["trip"]:
                    return
                task["travelTo"] = None
            task["until"] = 0
            a = acts[task["i"]]
            task["i"] += 1
            if a.get("probability") is not None and not self.chance(a["probability"]):
                s["steps"]["skipped"] += 1
                task["steps"].append([a["do"], "skipped"])
                continue
            if a.get("when") and not self.all_conds(a["when"], self.now()):
                s["steps"]["skipped"] += 1
                task["steps"].append([a["do"], "skipped_when"])
                continue
            r = self.exec(a)
            s["steps"][r["result"]] += 1
            if r.get("reason"):
                k = r["reason"][:80]
                s["refusals"][k] = s["refusals"].get(k, 0) + 1
            task["steps"].append([a["do"], r["result"], r["reason"][:80]] if r.get("reason") else [a["do"], r["result"]])
            ar = a.get("args") or {}
            if r["result"] == "done" and a["do"] == "home.command" and self.dev_id(ar["device"]) == "kitchen.stove" and ar.get("command") == "on":
                self.start_cooking(a, task["b"]["id"])
            if a.get("revert") and r["result"] in ("done", "no_change"):
                self.scheduled.append(dict(kind="revert", at=self.now() + js_round(self.num(a["revert"]["afterMinutes"])) * MIN_MS,
                                           byDevice=bool(a["revert"].get("byDevice")), action=self.resolve(a["revert"]["action"]), owner=task["b"]["id"]))
            if a["do"] == "person.travel" and r["result"] == "refused":
                task["i"] = len(acts)
                break
            blk = r.get("block") or {}
            if blk.get("until"):
                task["until"] = blk["until"]
                return
            if blk.get("travelTo"):
                task["travelTo"] = blk["travelTo"]
                return
        task["finished"] = True
        self.trace(dict(t=iso_local(task["start"]), behaviour=task["b"]["id"], outcome="followed", via=task["via"], steps=task["steps"]))

    # ----- event triggers -----
    def event_matches(self, ev, src, h):
        if ev["source"] != src:
            return False
        if src == "home":
            e = h
            if e["device"] != ev["deviceType"] or e["capability"] != ev["capability"] or e["attribute"] != ev["attribute"]:
                return False
            if ev.get("room") and e["roomId"] != self.real_room(ev["room"]):
                return False
            if not cmp(e["value"], "==", ev["value"]):
                return False
            return "previousValue" not in ev or cmp(e["previousValue"], "==", ev["previousValue"])
        if src == "phone":
            return self.match_phone_event(h, ev)
        if src == "person":
            return h["what"] == ev["what"] and (not ev.get("place") or ev["place"] == h.get("place")) and \
                (not ev.get("room") or self.real_room(ev["room"]) == h.get("room"))
        if src == "weather":
            return h["to"] == ev["to"] and (not ev.get("from") or ev["from"] == h["from"])
        return False

    def process_happenings(self):
        guard = 0
        while self.happenings and guard < 50:
            guard += 1
            batch, self.happenings = self.happenings, []
            for src, h in batch:
                if src == "person" and h["what"] == "wake" and self.S["place"] == "home" and self.left_overnight:
                    self.scheduled.append(dict(kind="morning", at=self.now() + js_round(self.uni(0, self.OFF["morningWithinMinutes"])) * MIN_MS,
                                               devices=self.left_overnight))
                    self.left_overnight = []
                if src == "person" and h["what"] == "fall_asleep":
                    self.left_overnight = [d.id for d, _ in self.on_devices(self.now())]
                for b in self.behaviours:
                    tr = b["trigger"]
                    if tr["kind"] != "event" or not self.event_matches(tr["event"], src, h):
                        continue
                    if tr.get("delayMinutes") is not None:
                        self.scheduled.append(dict(kind="eventCheck", at=self.now() + js_round(self.num(tr["delayMinutes"])) * MIN_MS, b=b))
                    else:
                        self.fire(b, self.now(), dict(via="event"))

    # ----- time triggers -----
    @staticmethod
    def is_body(a):
        return a["do"] in BODY_DO or (a["do"] == "home.command" and (a.get("args") or {}).get("channel") != "mobile_app")

    def busy(self, t):
        for k in self.tasks:
            if k["finished"]:
                continue
            if k["travelTo"]:
                return True
            if any(self.is_body(a) for a in k["actions"][k["i"]:]) and not (k["until"] and k["until"] - t >= 15 * MIN_MS):
                return True
        return False

    def time_triggers(self, t):
        lst = []
        for b in self.behaviours:
            tr = b["trigger"]
            if tr["kind"] == "event":
                continue
            st = b["_st"]
            dl = st.get("daily")
            deferred = tr["kind"] == "daily" and dl and dl["at"] == t and dl.get("deferred")
            day = dl["day"] if deferred else window_day(tr["window"], t)
            if day is None:
                if tr["kind"] == "time_window":
                    st["tw"] = None
                continue
            if not day_ok(tr.get("days"), day) or not month_ok(tr.get("months"), day):
                continue
            dk = day_key(day)
            if tr["kind"] == "time_window":
                w = st.get("tw")
                if not w or w["dk"] != dk:
                    w = st["tw"] = dict(dk=dk, last=False, stop=False)
                if w["stop"]:
                    continue
                now_ok = self.all_conds(b.get("conditions"), t)
                if now_ok and not w["last"]:
                    lst.append((b, dict(day=day, via="time_window", w=w)))
                w["last"] = now_ok
            elif tr["kind"] == "daily":
                if not dl or dl["dk"] != dk:
                    f, to = hhmm(tr["window"]["from"]), hhmm(tr["window"]["to"])
                    ln = (to - f + 1440) % 1440 + 1
                    dl = st["daily"] = dict(dk=dk, day=day, at=day + (f + int(self.rnd.random() * ln)) * MIN_MS)
                if dl["at"] == t:
                    lst.append((b, dict(day=day, via="daily", daily=dl)))
            elif tr["kind"] == "rate":
                if self.chance(tr["perHour"] / 60):
                    lst.append((b, dict(day=day, via="rate")))
        lst.sort(key=lambda x: -(x[0].get("priority") or 0))
        for b, how in lst:
            if any(self.is_body(a) for a in b["actions"]) and self.busy(t):  # the person is in the middle of something
                if how.get("daily") is not None:
                    dl = how["daily"]
                    dl.setdefault("first", t)
                    if t - dl["first"] < DEFER_MAX_MIN * MIN_MS:
                        dl["at"] = t + MIN_MS
                        dl["deferred"] = True
                elif how.get("w") is not None:
                    how["w"]["last"] = False
                s = self.stat(b["id"])
                s["deferred"] = s.get("deferred", 0) + 1
                continue
            r = self.fire(b, t, how)
            if how.get("w") is not None and r in ("not_followed", "max"):
                how["w"]["stop"] = True

    def run_scheduled(self, t):
        self.scheduled.sort(key=lambda x: x["at"])
        while self.scheduled and self.scheduled[0]["at"] <= t:
            it = self.scheduled.pop(0)
            if it["kind"] == "revert":
                if it["byDevice"]:
                    self.sim.clock.set_to(it["at"])
                    self.device_revert(it["action"])
                else:
                    r = self.exec(it["action"])
                    s = self.stat(it["owner"])
                    s["steps"][r["result"]] += 1
                    if r.get("reason"):
                        k = "revert: " + r["reason"][:70]
                        s["refusals"][k] = s["refusals"].get(k, 0) + 1
            elif it["kind"] == "eventCheck":
                self.fire(it["b"], t, dict(via="event"))
            elif it["kind"] == "morning":
                self.off_check("morning", t, it["devices"])
            self.person_changes()
            self.process_happenings()

    # ----- output -----
    def write_out(self, cutoff):
        L = self.sim.log
        i = 0
        while i < len(L.times) and L.times[i] < cutoff:
            i += 1
        if i:
            if self.home_f:
                self.home_f.write("".join(dumps(e) + "\n" for e in L.entries[:i]))
            self.n_home += i
            del L.entries[:i]
            del L.times[:i]
        P = self.phone
        j = 0
        while j < len(P.times) and P.times[j] < cutoff:
            j += 1
        if j:
            self.phone_f.write("".join(dumps(e if self.full_format else compact(e)) + "\n" for e in P.events[:j]))
            self.n_phone += j
            del P.events[:j]
            del P.times[:j]

    # ----- main loop -----
    def run(self):
        self.home_f = open(os.path.join(self.out_dir, "home_log.jsonl"), "w", encoding="utf-8") if self.write_home else None
        self.phone_f = open(os.path.join(self.out_dir, "phone_log.jsonl"), "w", encoding="utf-8")
        self.n_home = self.n_phone = 0
        t0 = _time.time()
        last_w = outdoor_at(self.T0)["weather"]
        t = self.T0 + MIN_MS
        while t <= self.TEND:
            self.minute_ms, self.sec = t, 0
            self.sim.clock.set_to(t)
            self.sim.tick()
            self.person_changes()
            w = outdoor_at(t)["weather"]
            self.recent_weather.append((t, w))
            if w != last_w:
                self.happenings.append(("weather", dict(frm=last_w, to=w, **{"from": last_w})))
                last_w = w
            self.process_happenings()
            self.run_scheduled(t)
            self.time_triggers(t)
            self.process_happenings()
            for task in list(self.tasks):
                if not task["finished"]:
                    self.run_task(task)
                    self.process_happenings()
            self.tasks = [k for k in self.tasks if not k["finished"]]
            self.sim.clock.set_to(t)
            if t % (6 * 3600000) == 0:
                self.recent_phone = [e for e in self.recent_phone if e["timestamp"] >= t - DAY_MS]
                self.recent_weather = [x for x in self.recent_weather if x[0] >= t - DAY_MS]
                self.action_history = [x for x in self.action_history if x[0] >= t - 7 * DAY_MS]
            if (t - self.T0) % DAY_MS == 0:
                self.write_out(t - 2 * DAY_MS)
                d = (t - self.T0) // DAY_MS
                if d % 30 == 0 or d == self.days:
                    self.print(f"day {d}/{self.days} ({day_key(t - MIN_MS)}) home {self.n_home} phone {self.n_phone} lines, {_time.time() - t0:.0f} s")
            t += MIN_MS
        self.sim.flush()
        self.write_out(float("inf"))
        if self.home_f:
            self.home_f.close()
        self.phone_f.close()
        if self.trace_f:
            self.trace_f.close()
        c = sorted(self.cook_times)
        q = lambda f: c[min(len(c) - 1, int(f * len(c)))] if c else None
        summary = dict(personaId=self.P["personaId"], houseId=self.sim.house_id, houseType=self.sim.type, variant=self.P["variant"], startDate=self.P["simulation"]["startDate"], days=self.days,
                       seed=self.seed, homeLines=self.n_home, phoneEvents=self.n_phone,
                       cooking=dict(times=len(c), minutesMedian=q(0.5), minutesP10=q(0.1), minutesP90=q(0.9), minutesMax=c[-1] if c else None),
                       behaviours=self.stats, checks=self.check_stats, seconds=round(_time.time() - t0))
        with open(os.path.join(self.out_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
            f.write("\n")
        self.print(f"done: {self.n_phone} phone events ({self.n_home} of them copies of home lines) -> {self.out_dir}")
        return summary
