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
from .house import PHYS

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOW = ["sun", "mon", "tue", "wed", "thu", "fri", "sat"]
BODY_DO = {"person.travel", "person.moveRoom", "home.record", "person.shower"}
# glances at the lock screen: Hintze et al. 2014 (1,960 Android phones): locked sessions median 56 s, mean 88 s
# -> lognormal sigma = sqrt(2 ln(88/56)) = 0.95; median 22 glances a day, spread over about 16 waking hours
GLANCE = dict(median=56, sigma=0.95)
# minimum minutes a person means to keep a device on: switching on / opening is skipped if a planned departure or
# sleep comes sooner (assumption, agreed 2026-10-29). Lights, lamps, stove: not limited (short use is normal).
PLAN_MIN = dict(window_contact=10, door_contact=10, heating_cooling_unit=30, floor_heating=30, tv=20, air_purifier=20, humidifier=20)
# apps a task is done in; the person opens it, does the task and closes it (agreed 2026-11-03)
APP_FOR = dict(home="com.samsung.android.oneconnect", calendar="com.samsung.android.calendar", sms="com.samsung.android.messaging",
               camera="com.sec.android.app.camera", call="com.samsung.android.dialer")
INPUT_APPS = {"com.samsung.android.app.notes", "com.samsung.android.app.reminder", "com.samsung.android.calendar",
              "com.samsung.android.messaging", "com.kakao.talk"}
# seconds an app stays in front for one task (lognormal). No direct measurement found:
# tap (device control, timer, photo): weather-app dwell terciles 6 s / 23 s (arXiv 2106.01490, US 2017) -> median 12, sigma 1.56
# input (note, checklist, event, SMS): an appointment on a PDA 37.7 s (Starner et al. 2004), typing 36.2 wpm (Palin et al. 2019)
TASK_SECONDS = dict(tap=dict(median=12, sigma=1.56, min=3), input=dict(median=30, sigma=0.7, min=5))
GLANCE_AWAKE_MIN = 16 * 60
# heating habits (profile heatingHabits, drawn by pipeline/sample_heating_person.py; agreed 2026-11-05). Our assumptions:
HEAT_SEASON_MEAN_C = 15.0  # people heat while the outdoor daily mean is below this (as the neighbours in house.py)
HEAT_ON_BELOW_K = 1.0  # the person switches the floor heating on when the room is this far below the comfort temperature
HEAT_UNUSED_MIN = 30  # a heated room left this long is switched off by people who switch off unused rooms
HEAT_ROOM = dict(dining_room="living_room", hallway="living_room", entryway="living_room")  # open plan: the living room's
DEFER_MAX_MIN = 180  # a daily behaviour waits at most this long after its minute
# cooling and window habits (profiles coolingHabits / windowHabits, drawn by pipeline/sample_cooling_person.py and
# pipeline/sample_window_person.py; agreed 2026-11-20). Cooling: awake at home, the room the person is in is cooled when
# it reaches onAboveC (Seoul flats: switched on at 29.8 C, off at 27.3 C on average, Chun & Bae 2005), to setpointC
# (rooms with cooling on: 25.2 C, Yun et al. 2020); its window is closed first. Bedtime / leaving: keep or off; a cooled
# room left COOL_UNUSED_MIN is switched off by people who do that. Windows: in hot rooms, opened when the room reaches
# openAboveC and outdoor air is cooler (no data; the LLM's choice), closed again (after WINDOW_MIN_OPEN_MIN) when the room is WINDOW_CLOSE_BELOW_K
# below openAboveC, when outdoor air is hotter, for cooling, for rain or snow, when leaving, and at bedtime unless the
# person sleeps with it open on warm nights. Airing: 0-2 times a day, morning 9-11 / evening 17-19 (spring survey of 154
# Seoul/Gyeonggi flats: once a day 49.7%, twice 30.7%; mornings 9-11 55.8%, evenings 17-19 33.4%; under 20 min 43.0%,
# 20-40 min 39.6%; Lee 2010), shorter in the heating season (winter: 75% open 1-2 times a day, under 10 min; Cho & Choi
# 2013). With these habits the off rules for cooling units and windows are not used.
COOL_UNUSED_MIN = 30
HOME_BANDS = (("morning", 5, 9), ("day", 9, 18), ("evening", 18, 23), ("night", 23, 5))  # homeBaseHabits bands (local hours)
# What the person does at home when no rule or habit acts (agreed 2026-11-24). Pool from the time-use survey's
# activity classes (Statistics Korea, middle classes of 2009: Kim et al. 2013 appendix 2-3): rooms it may happen in
# (role names) and what it does to devices / the phone. The persona's profile picks which it does and how often and
# long (idleActivityHabits, pipeline/sample_idle_person.py).
IDLE_POOL = dict(
    tv=dict(rooms=("living_room",), dev="tv"),
    reading=dict(rooms=("living_room", "bedroom", "study_room"), dev="lamp"),
    study=dict(rooms=("study_room",), dev="lamp"),
    snack=dict(rooms=("kitchen", "dining_room"), light=True),
    toilet=dict(rooms=("bathroom",), light=True, alwaysLight=True),
    dishes=dict(rooms=("kitchen",), light=True),
    cleaning=dict(rooms=("living_room", "bedroom", "kitchen", "study_room", "dining_room"), multi=True),
    music=dict(rooms=("living_room", "bedroom", "study_room", "kitchen")),
    video=dict(rooms=("bedroom", "living_room"), app=True),
    game=dict(rooms=("bedroom", "living_room"), app=True),
    shopping=dict(rooms=("bedroom", "living_room", "study_room"), app=True),
    call=dict(rooms=("bedroom", "living_room", "study_room", "balcony")),
    workout=dict(rooms=("living_room", "bedroom")),
    nap=dict(rooms=("bedroom", "living_room")),
    plants=dict(rooms=("balcony",)),
    folding=dict(rooms=("bedroom", "living_room")),
    tidying=dict(rooms=("bedroom", "living_room", "study_room")),
    rest=dict(rooms=("bedroom", "living_room")),
)
IDLE_AGAIN = 0.3  # weight of the activity just done, so the same thing is less likely right again [assume, agreed]
IDLE_DARK_LUX = 50  # a short task turns the room light on below this [assume]
SLEEP_ROOMS_EXTRA = ("living_room",)  # besides the bedrooms (room1..4): the sofa (agreed 2026-11-24)
MINUTE_FULL_SEC = 44  # a new action starts only before :45 of the minute (an action takes 3-15 s), else it waits for the
# next minute (agreed 2026-11-23: no actions piled up at :59 when a minute has more to do than 60 s)
WALK_STEPS = [4, 10]  # steps a room walked through [assume: 3-5 m a room, 0.6-0.7 m a step]
DRY_CHECK_FIRST_H, DRY_CHECK_EVERY_H = 6, 4  # first check of a rack after hanging, then every this many hours [assume]
DRY_DONE_SHARE = 0.05  # water left (share of the load's water) at which the laundry counts as dry [assume]
DRY_DEFAULT = dict(airMinC=10, airMaxC=28)  # mild weather for opening windows to dry laundry, without dryingHabits [assume]
LAUNDRY_WAIT_MIN = (5, 40)  # the laundry is dealt with this long after the wash ends, once home and awake [assume]
COOL_ROOM = dict(kitchen="living_room", dining_room="living_room", hallway="living_room", entryway="living_room")  # no unit there: the living room's
WINDOW_CLOSE_BELOW_K = 4.0
WINDOW_MIN_OPEN_MIN = 60  # a window opened for heat stays open at least this long (no data; avoids opening and closing every few minutes)
AIRING_SLOTS = [(9, 11, 55.8), (17, 19, 33.4)]  # local hours and the survey's share for one airing a day
# ventilation habits (profile ventilationHabits, drawn by pipeline/sample_ventilation_person.py; agreed 2026-11-18): the
# flat's ventilation unit (house.py PHYS envelope.ventilator) runs always / while someone is home / while the person is
# home and awake; "winter": "off" stops it while the outdoor daily mean is below HEAT_SEASON_MEAN_C (cold draught is one of
# the reasons people give for not using it). No device and no log lines (no SmartThings capability for it).


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
        self.sim.set_window_sensors((profile.get("windowSensors") or {}).get("rooms"))
        self.sim.jump_to(self.T0)
        self.phone = self.sim.phone
        self.S = self.phone.s
        self.phone.habits.update(profile.get("phoneHabits") or {})
        self.sim.dryer_load = profile.get("dryerLoad")  # the person's laundry habit: shares of small / standard / large loads
        self.phone.rand = self.rnd.random
        self.glance_day, self.glance_idle, self.glance_idle_prev = -1, 0, GLANCE_AWAKE_MIN
        self.roles = profile.get("roomRoles") or {}
        os.makedirs(out_dir, exist_ok=True)
        self.trace_f = open(os.path.join(out_dir, "trace.jsonl"), "w", encoding="utf-8") if trace else None
        # ground truth: one line per run of a kind 'pattern' behaviour whose conditions were true (if + what was done)
        self.gt_f = open(os.path.join(out_dir, "ground_truth.jsonl"), "w", encoding="utf-8")
        self.gt_open = []
        self.gt_ctx = None  # the ground-truth line a person revert outside its rule belongs to
        self.happenings, self.recent_phone, self.recent_weather, self.action_history = [], [], [], []
        self.scheduled, self.tasks = [], []
        self.loose_chains = []  # the rest (closing the app) of app tasks started outside a rule; run_loose_chains
        self.minute_ms, self.sec = self.T0, 0
        self.stats, self.cook_times, self.left_overnight = {}, [], []
        self.check_stats = {k: dict(checked=0, turnedOff=0, leftOn=0) for k in ("bedtime", "leaving", "morning")}
        cm = profile.get("cookingMinutes")
        self.cook_default = cm or dict(dist="lognormal", median=15, sigma=0.6)
        self.plan_skips, self.plan_src = [], None  # switch-ons skipped by the plan rule, for the wrong-skip check
        self.keep_on = set()  # devices switched on with keepOn: left out of the leaving / bedtime checks
        self.heat = profile.get("heatingHabits")  # None: no heating habits (heating only by the profile's rules)
        self.heat_stats = dict(switchedOn=0, setpoint=0, sleepLower=0, sleepOff=0, leaveLower=0, leaveOff=0, keptOn=0, unusedOff=0)
        self.cool = profile.get("coolingHabits")  # None: cooling only by the profile's rules
        self.win = profile.get("windowHabits")  # None: windows only by the profile's rules
        self.cool_stats = dict(switchedOn=0, setpoint=0, sleepOff=0, leaveOff=0, keptOn=0, unusedOff=0)
        self.win_stats = dict(hotOpen=0, closedCool=0, closedHotOutside=0, closedRain=0, closedForCooling=0, airings=0, sleepOpen=0, closedAtCheck=0)
        self.airing_plan = {}  # local day -> list of dict(at, until, done)
        self.win_hot, self.win_airing = {}, set()  # windows the habit opened because of heat (id -> opened at) / for airing
        self.vent = profile.get("ventilationHabits")  # None: no ventilation unit running
        self.hood = profile.get("hoodHabits")  # None: the range hood never runs
        self.hood_session = None  # this cooking's hood decision (None: stove off)
        self.hood_stats = dict(cookings=0, withHood=0)
        self.shower_stats = dict(showers=0)
        self.laundry = dict(washerWas=None, finishedAt=None, dryerSince=False)
        self.laundry_stats = dict(washes=0, dried=0, racks=0)
        self.laundry_h = profile.get("laundryHabits")  # None: no dryer use by habit (racks only)
        self.dry_h = profile.get("dryingHabits")  # None: DRY_DEFAULT
        self.hb = profile.get("homeBaseHabits")  # None: no layer A (the person stays where the last action left them)
        self.hb_room, self.hb_since, self.hb_limit = None, 0, 0
        self.idle = profile.get("idleActivityHabits")  # None: layer A by room weights only (homeBaseHabits bands)
        self.act, self.last_act, self.in_idle = None, None, False
        self.idle_stats = {}
        self.hb_stats = dict(returns=0, moves=0, held=0, sofaSleep=0, backToTaskRoom=0, walkedToBed=0, draws=0, drawsBase=0,
                             drawsErrand=0, drawsSameRoom=0)
        self.dry_window = set()  # living room windows opened for drying
        self.outer_why = set()  # why the balcony's outer window is open: living / dry
        self.passing = False  # the sliding door is opened or closed only to walk through (no pairing)
        self.door_to_close = False  # opened to go out onto the balcony: closed again on the way back in
        self.dry_stats = dict(takenIn=0, balconyWindow=0, livingWindow=0, movedInside=0, heating=0, cooling=0, hoursToDry=[])
        self.vent_minutes = dict(season=0, other=0)
        self.behaviours = []
        for b in profile["behaviours"] + self.shower_behaviours(profile.get("showerHabits")) + self.laundry_behaviours(profile.get("laundryHabits")):
            acts, merged = self.merge_app_steps(b["actions"])
            self.behaviours.append(dict(b, actions=acts, _st={}, _firings=0, _merged=merged,
                                        _phoneUse=any(a["do"] == "phone.useApps" for a in acts)))
        self.day_mult_day, self.day_mult = -1, 1.0
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

    def minute_full(self, a=None):
        """the minute has no room for another action (a: the action, to count the rooms walked to reach its device):
        it waits for the next minute"""
        return self.sec + self.action_sec(a) > 59

    def action_sec(self, a):
        """seconds an action may take at most: 15, plus 4 a room walked to the room of its device (by hand)"""
        if a is None or not isinstance(a, dict):
            return 59 - MINUTE_FULL_SEC
        args = a.get("args") or {}
        room = None
        if a["do"] in ("home.command", "home.record") and args.get("channel") != "mobile_app" and isinstance(args.get("device"), str):
            room = self.real_room(args["device"].rsplit(".", 1)[0])
        elif a["do"] == "person.moveRoom" and isinstance(args.get("room"), str):
            room = self.real_room(args["room"])
        hops = len(self.sim.house.path(self.S["room"], room)) - 1 if room and self.S["place"] == "home" and self.S["room"] else 0
        return 15 + 4 * hops

    def advance_seconds(self):
        self.sec = self.sec + 3 + int(self.rnd.random() * 13)  # past :59 it runs on into the next minute
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
            H.append(("person", dict(what="depart", place=b["trip"]["frm"], at=b["trip"].get("start"))))
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

    def observed(self, c, t):
        """the value a condition looked at, at t (ground truth)"""
        k, S = c["kind"], self.S
        if k == "time":
            return iso_local(t)[11:19]
        if k == "day":
            return ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][((t - local_ms(2024, 0, 1)) // DAY_MS) % 7]
        if k == "month":
            return int(iso_local(t)[5:7])
        if k == "place":
            return "trip" if S["trip"] else S["place"]
        if k == "room":
            return S["room"] if S["place"] == "home" else None
        if k == "device":
            return self.device_value(c["device"], c["capability"], c["attribute"])
        if k == "weather":
            return outdoor_at(t)["weather"]
        if k == "outdoor":
            return outdoor_at(t).get(c["variable"])
        if k == "phone_state":
            return self.phone_field(c["field"])
        if k == "health":
            evs = [e for e in self.recent_phone if e["type"] == "HEALTH" and e["source"] == c["record"]]
            return evs[-1]["payload"].get(c["field"]) if evs else None
        return self.cond(c, t)  # calendar, phone_event, recent_action: true / false

    def gt_start(self, b, t, how):
        return dict(t=iso_local(t), behaviour=b["id"], outcome=None, via=how.get("via"),
                    **{"if": dict(trigger=b["trigger"], conditions=[dict(c, observed=self.observed(c, t)) for c in (b.get("conditions") or [])])},
                    then=[])

    def gt_write(self, gt, outcome):
        gt["outcome"] = outcome
        self.gt_f.write(json.dumps({k: v for k, v in gt.items() if not k.startswith("_")}, ensure_ascii=False, default=str) + "\n")
        if gt in self.gt_open:
            self.gt_open.remove(gt)

    def gt_finish(self, gt, outcome):
        """the rule's own steps are over: write the line now, or when its person reverts are done or dropped"""
        gt["_outcome"] = outcome
        if not gt.get("_pending"):
            self.gt_write(gt, outcome)

    def gt_revert_done(self, it, result, reason=None):
        """a person revert of a pattern ran (done / no_change), or will not run (not_followed: refused, or the leaving /
        bedtime check switched the device off first)"""
        gt, entry = it.get("gt"), it.get("gtRevert")
        if gt is None:
            return
        entry["result"] = result
        if reason:
            entry["reason"] = reason
        gt["_pending"] -= 1
        if not gt["_pending"] and gt.get("_outcome"):
            self.gt_write(gt, gt["_outcome"])

    def gt_add(self, gt, a, result, do=None):
        """a step the person did, for the ground truth: done or no_change; not wait, app closing or the screen"""
        if gt is None or a.get("do") == "wait" or result not in ("done", "no_change"):
            return
        x = dict(t=iso_local(self.now()), do=do or a["do"], args=a.get("args") or {}, result=result)
        if a.get("revert"):
            x["revert"] = a["revert"]
        gt["then"].append(x)

    def gt_step(self, task, a, result, do=None):
        self.gt_add(task.get("gt") if task else self.gt_ctx, a, result, do)

    def all_conds(self, cs, t):
        return all(self.cond(c, t) for c in (cs or []))

    # ----- the person's actions -----
    def go_to(self, room):
        S = self.S
        if S["place"] != "home" or S["trip"] or S["asleep"] or S["room"] == room:
            return
        self.walk(room)
        self.person_changes()

    def walk(self, room):
        """walk to a room through the rooms between (agreed 2026-11-23: no jumping between rooms that are not joined);
        each room on the way is sensed, 2-4 s and 4-10 steps a room, the clock moving on with it"""
        S = self.S
        if S["place"] != "home" or S["trip"] or S["room"] == room:
            return 0
        if self.act and not self.in_idle and room != self.act["room"]:
            self.end_act()  # something else needs the person: the activity ends where it is
        n = 0
        for hop in self.sim.house.path(S["room"], room)[1:]:
            here = S["room"]
            door = self.win_dev("living_room") if {here, hop} == {"living_room", "balcony"} and self.sim.house.env.real_balcony else None
            if door is not None and hop == "balcony" and not self.win_is_open(door):
                # agreed 2026-11-23: the living room window is the sliding glass door onto the balcony; closed, the
                # person opens it to go out and closes it again on the way back in
                self.passing = True
                self.win_set(door, "open")
                self.passing = False
                self.door_to_close = True
            self.sec = self.sec + 2 + int(self.rnd.random() * 3)
            self.sim.clock.set_to(self.minute_ms + self.sec * 1000)
            n += self.phone.move_room(hop, WALK_STEPS)
            if door is not None and hop == "living_room" and self.door_to_close:
                self.door_to_close = False
                if self.win_is_open(door):
                    self.passing = True
                    self.win_set(door, "closed")
                    self.passing = False
        return n

    def exec(self, a, in_task=False, raw=False):
        """one action of the person. An action done in an app (raw=False) becomes an app task: open the app, do it,
        close the app; inside a rule it runs as a chain at its own seconds, elsewhere (checks, reverts) at once"""
        if not raw:
            events = self.app_events(a)
            if events:
                if in_task:
                    self.advance_seconds()
                    return dict(result="pending", block=dict(chain=events))
                self.advance_seconds()
                return self.run_events_now(events)
        args = a.get("args") or {}
        sim, ph, S = self.sim, self.phone, self.S
        if not raw:  # inside an app task the chain has set the time
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
                pair = did == "living_room.window_contact" and sim.house.env.real_balcony and not self.passing
                if pair and args["value"] == "closed":
                    outer = self.outer_win()
                    if outer is not None and self.win_is_open(outer) and not (self.outer_why - {"living"}):
                        # both closed: the outer window first, through the still open sliding door, then the door
                        self.outer_release("living")
                self.go_to(d.roomId)
                out = done(sim.set_value(did, args["capability"], args["attribute"], args["value"]))
                if pair and out["result"] == "done":
                    # agreed 2026-11-23, for everyone: the living room window opens onto the balcony, so whoever opens it
                    # (habit, airing, a rule) opens the balcony's outer window as well, and closes it with it
                    self.outer_open("living") if args["value"] == "open" else self.outer_release("living")
        elif do == "person.travel":
            if S["trip"]:
                out = refused("already travelling")
            elif S["asleep"]:
                out = refused("asleep")
            else:
                if S["place"] == "home":
                    self.off_check("leaving", t)
                self.advance_seconds()
                if S["place"] == "home" and not S["trip"] and args["to"] != "home":
                    self.walk("entryway")  # out through the front door
                n = ph.travel(args["to"], args["mode"])
                if n > 0 or S["trip"]:
                    out = dict(result="done", block=dict(travelTo=args["to"]))
                else:
                    out = dict(result="no_change") if args["to"] == S["place"] else refused(sim.last_refusal or "refused")
        elif do == "person.moveRoom":
            out = done(self.walk(self.real_room(args["room"])))
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
            if self.act:
                self.end_act()
            room = S["room"]
            if S["place"] == "home" and not S["trip"] and room and not (room.startswith("room") or room in SLEEP_ROOMS_EXTRA):
                self.go_to(self.real_room("bedroom"))  # agreed 2026-11-24: nobody falls asleep in the laundry room
                self.hb_stats["walkedToBed"] += 1
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
        elif do == "phone.useApps":
            if S["asleep"] or ph.driving:
                out = refused("asleep" if S["asleep"] else "The person is driving: no phone use until the drive ends")
            elif ph.in_chain:
                out = dict(result="no_change")  # already using the phone
            else:
                plan = self.app_chain(args)
                ev = [[0 if i == 0 else int(plan[i - 1][1] * 1000), "open", p] for i, (p, _) in enumerate(plan)]
                out = dict(result="done", block=dict(chain=ev + [[int(plan[-1][1] * 1000), "close", None]])) if plan else dict(result="no_change")
        elif do == "wait":
            out = dict(result="done", block=dict(until=t + js_round(self.num(args["minutes"])) * MIN_MS))
        elif do == "person.shower":  # engine-made (showerHabits): water vapour in the bathroom while it runs, no line of its own
            if S["place"] != "home" or S["trip"] or S["asleep"] or "bathroom" not in S["room"]:
                out = refused("not in a bathroom")
            else:
                until = t + js_round(self.num(args["minutes"])) * MIN_MS
                self.sim.house.env.shower = (S["room"], until)
                self.shower_stats["showers"] += 1
                out = dict(result="done", block=dict(until=until))
        else:
            out = refused("unknown action " + do)
        if do in ("home.command", "home.record") and out["result"] == "done" and args.get("device"):
            did = self.dev_id(args["device"])
            if a.get("keepOn") and self.is_turn_on(a):
                self.keep_on.add(did)
            elif not self.is_turn_on(a):
                self.keep_on.discard(did)
        if out["result"] in ("done", "no_change"):
            self.action_history.append((t, do, args))
        self.person_changes()
        return out

    # ----- phone use: apps one after another -----
    def app_chain(self, args):
        """[(package, seconds), ...] for one phone use: the first app from 'first', then with probability 'continue'
        a different app from 'next' (default: 'first'), each used for a lognormal number of seconds"""
        inst = set(self.S["installed"])
        ck = args.get("check")
        if ck and self.rnd.random() < float(ck.get("share", 0)):  # a quick check: one app, a few seconds
            cf = {p: w for p, w in (ck.get("first") or args.get("first") or {}).items() if p in inst and w > 0}
            if cf:
                d = ck.get("seconds") or dict(median=10, sigma=0.8)
                return [(self.pick(list(cf), list(cf.values())), max(2, min(300, d["median"] * math.exp(d["sigma"] * self.gauss()))))]
        first = {p: w for p, w in (args.get("first") or {}).items() if p in inst and w > 0}
        nxt = {p: w for p, w in (args.get("next") or args.get("first") or {}).items() if p in inst and w > 0}
        secs = args.get("seconds") or {}
        cont = float(args.get("continue", 0.32))
        cap = int(args.get("maxApps", 15))
        if not first:
            return []
        cur = self.pick(list(first), list(first.values()))
        plan = []
        while True:
            d = secs.get(cur) or secs.get("default") or dict(median=30, sigma=1.5)
            s = d["median"] * math.exp(d["sigma"] * self.gauss())
            plan.append((cur, max(2, min(float(d.get("max", 3600)), s))))
            if len(plan) >= cap or self.rnd.random() >= cont:
                return plan
            cand = {p: w for p, w in nxt.items() if p != cur}
            if not cand:
                return plan
            cur = self.pick(list(cand), list(cand.values()))

    # ----- a person does not switch on what they are about to leave or sleep away from -----
    def revert_device(self, it):
        dv = ((it.get("action") or {}).get("args") or {}).get("device")
        return self.dev_id(dv) if dv else None

    def is_turn_on(self, a):
        args = a.get("args") or {}
        if a["do"] == "home.record":
            return args.get("value") == "open"
        cmd, xs = args.get("command"), args.get("args") or []
        return (cmd in ("on", "open", "start") or (cmd == "setMachineState" and xs[:1] == ["run"]) or (cmd == "setThermostatMode" and bool(xs) and xs[0] in ("cool", "heat"))
                or (cmd == "setPercent" and bool(xs) and isinstance(xs[0], (int, float)) and xs[0] > 0))

    def turn_on_minutes(self, a):
        """PLAN_MIN minutes for an action that switches on / opens a device of those types, else None"""
        args = a.get("args") or {}
        if a["do"] not in ("home.command", "home.record") or not args.get("device"):
            return None
        d = self.sim.house.device(self.dev_id(args["device"]))
        if not d or d.type not in PLAN_MIN:
            return None
        if d.type == "door_contact":
            return None
        if a["do"] == "home.record":
            on = args.get("value") == "open"
        else:
            cmd, xs = args.get("command"), args.get("args") or []
            on = (cmd == "on" or (cmd == "setThermostatMode" and xs and xs[0] in ("cool", "heat"))
                  or (cmd == "setPercent" and xs and isinstance(xs[0], (int, float)) and xs[0] > 0))
        return PLAN_MIN[d.type] if on else None

    def next_plan(self, t, task=None):
        """earliest planned time >= t at which the person leaves home or goes to sleep: today's daily rules (their minute
        is drawn now if their window has not opened yet, the same way the trigger draws it) and running tasks"""
        S, best = self.S, None
        self.plan_src = None
        leaves = lambda acts: any((x["do"] == "person.travel" and S["place"] == "home" and not S["trip"]
                                   and (x.get("args") or {}).get("to") != "home") or x["do"] == "phone.sleep" for x in acts)
        d0 = start_of_day(t)
        this_minute = self.minute_ms  # a rule due in this minute counts, even if its second has passed
        for b in self.behaviours:
            tr = b["trigger"]
            if tr["kind"] != "daily" or not leaves(b["actions"]):
                continue
            st = b["_st"]
            dl = st.get("daily")
            open_day = window_day(tr["window"], t)
            if open_day is not None:  # the window is open: the trigger has drawn its minute (a window past midnight
                if not dl or dl["dk"] != day_key(open_day):  # belongs to the day it started)
                    continue
            elif not dl or dl["dk"] != day_key(d0):
                f, to = hhmm(tr["window"]["from"]), hhmm(tr["window"]["to"])
                if d0 + f * MIN_MS <= t or not day_ok(tr.get("days"), d0) or not month_ok(tr.get("months"), d0):
                    continue  # not today
                ln = (to - f + 1440) % 1440 + 1
                dl = st["daily"] = dict(dk=day_key(d0), day=d0, at=d0 + (f + int(self.rnd.random() * ln)) * MIN_MS,
                                        follow=self.chance(b["probability"]))
            if dl.get("follow") is False:
                continue  # already decided: the person will not follow it today
            if not self.all_conds(b.get("conditions"), dl["at"]):
                continue  # its conditions would be false then (judged now, at that minute): no departure or sleep from it
            if dl["at"] >= this_minute and (best is None or dl["at"] < best):
                best = max(dl["at"], t)
                self.plan_src = dict(kind="daily", rule=b["id"], probability=b.get("probability"))
        for x in self.scheduled:  # event rules with a delay: their time is already set
            if (x["kind"] == "eventCheck" and x["at"] >= this_minute and x.get("follow", True) and leaves(x["b"]["actions"])
                    and self.all_conds(x["b"].get("conditions"), x["at"])):
                if best is None or max(x["at"], t) < best:
                    best = max(x["at"], t)
                    self.plan_src = dict(kind="eventCheck", rule=x["b"]["id"], probability=x["b"].get("probability"))
        for k in self.tasks:
            if k is task or k["finished"] or not leaves(k["actions"][k["i"]:]):
                continue
            at = max(t, k["until"] or t)
            if best is None or at < best:
                best, self.plan_src = at, dict(kind="runningTask", rule=k["b"]["id"])
        if task is not None and leaves(task["actions"][task["i"]:]):
            if best is None or t < best:
                best, self.plan_src = t, dict(kind="sameRule", rule=task["b"]["id"])
        return best

    def leaving_soon(self, a, task):
        if a.get("keepOn"):  # meant to stay on while away or asleep
            return False
        m = self.turn_on_minutes(a)
        if not m:
            return False
        t = self.now()
        p = self.next_plan(t, task)
        skip = p is not None and p - t < m * MIN_MS
        ar = a.get("args") or {}
        dev = self.dev_id(ar["device"]) if ar.get("device") else a["do"]
        last = self.plan_skips[-1] if self.plan_skips else None
        if skip and last is not None and last["device"] == dev and last["plannedAt"] == p and last["confirmedAt"] is None:
            skip_new = False  # the same skip again (the heating habit asks every minute): counted once
        else:
            skip_new = skip
        if skip_new:  # checked later: did the person really leave home or fall asleep within the device's minimum time?
            self.plan_skips.append(dict(t=t, rule=task["b"]["id"] if task else None, device=self.dev_id(ar["device"]) if ar.get("device") else a["do"],
                                        minimum=m, plannedAt=p, source=self.plan_src, confirmedAt=None))
        return skip

    # ----- heating habits -----
    def heat_unit(self, room):
        return self.sim.house.at(HEAT_ROOM.get(room, room), "floor_heating")

    def heat_cmd(self, d, cmd, cap, args):
        here = self.S["place"] == "home" and HEAT_ROOM.get(self.S["room"], self.S["room"]) == d.roomId
        return self.exec(dict(do="home.command", args=dict(device=d.id, capability=cap, command=cmd, args=args,
                                                          channel="physical" if here else "mobile_app")))

    def heating_tick(self, t):
        """awake at home in the heating season: the room the person is in is kept near their comfort temperature: switched
        on when it is HEAT_ON_BELOW_K below it, its setpoint put back to the comfort temperature (after a night or a
        departure that lowered it)"""
        H, S = self.heat, self.S
        if not H or S["place"] != "home" or S["trip"] or S["asleep"] or outdoor_at(t)["meanTemperature"] >= HEAT_SEASON_MEAN_C \
                or self.minute_full():
            return
        d = self.heat_unit(S["room"])
        if d is None:
            return
        comfort, mode = H["comfortC"], d.get("thermostatMode", "thermostatMode")
        sp = d.get("thermostatHeatingSetpoint", "heatingSetpoint")
        if mode == "off" and self.sim.house.env.rooms[d.roomId]["temperature"] < comfort - HEAT_ON_BELOW_K:
            on = dict(do="home.command", args=dict(device=d.id, capability="thermostatMode", command="setThermostatMode", args=["heat"]))
            if self.leaving_soon(on, None):
                return
            if sp != comfort:
                self.heat_cmd(d, "setHeatingSetpoint", "thermostatHeatingSetpoint", [comfort])
            if self.heat_cmd(d, "setThermostatMode", "thermostatMode", ["heat"])["result"] == "done":
                self.heat_stats["switchedOn"] += 1
        elif mode == "heat" and sp != comfort:
            if self.heat_cmd(d, "setHeatingSetpoint", "thermostatHeatingSetpoint", [comfort])["result"] == "done":
                self.heat_stats["setpoint"] += 1

    def heating_moment(self, moment, t):
        """going to bed or leaving home: each heated room as the person's habit says: keep / lower / off (leaving: kept on
        when it is colder outside than keepWhenOutdoorBelowC)"""
        H = self.heat
        if not H:
            return
        rule = H["sleep"] if moment == "bedtime" else H["leaving"]
        act = rule["action"]
        if moment == "leaving" and rule.get("keepWhenOutdoorBelowC") is not None and outdoor_at(t)["temperature"] < rule["keepWhenOutdoorBelowC"]:
            act = "keep"
        for d in self.sim.house.devices.values():
            if d.type != "floor_heating" or d.get("thermostatMode", "thermostatMode") != "heat":
                continue
            key = ("sleep" if moment == "bedtime" else "leave")
            if act == "keep":
                self.heat_stats["keptOn"] += 1
            elif act == "lower":
                target = H["comfortC"] - rule["lowerC"]
                if d.get("thermostatHeatingSetpoint", "heatingSetpoint") > target:
                    if self.heat_cmd(d, "setHeatingSetpoint", "thermostatHeatingSetpoint", [target])["result"] == "done":
                        self.heat_stats[key + "Lower"] += 1
            elif self.heat_cmd(d, "setThermostatMode", "thermostatMode", ["off"])["result"] == "done":
                self.heat_stats[key + "Off"] += 1

    def heating_unused(self, did, t):
        """a heated room left HEAT_UNUSED_MIN ago and not entered since: switched off from the phone"""
        S = self.S
        d = self.sim.house.device(did)
        if d is None or S["place"] != "home" or S["trip"] or S["asleep"] or d.get("thermostatMode", "thermostatMode") != "heat":
            return
        if self.heat_unit(S["room"]) is d:
            return
        if self.heat_cmd(d, "setThermostatMode", "thermostatMode", ["off"])["result"] == "done":
            self.heat_stats["unusedOff"] += 1

    # ----- cooling habits -----
    def cool_unit(self, room):
        d = self.sim.house.at(room, "heating_cooling_unit")
        if d is None and room in COOL_ROOM:
            d = self.sim.house.at(COOL_ROOM[room], "heating_cooling_unit")
        return d

    def cool_cmd(self, d, cmd, cap, args):
        here = self.S["place"] == "home" and self.cool_unit(self.S["room"]) is d
        return self.exec(dict(do="home.command", args=dict(device=d.id, capability=cap, command=cmd, args=args,
                                                          channel="physical" if here else "mobile_app")))

    def cooling_tick(self, t):
        """awake at home: the room the person is in is cooled to setpointC once it reaches onAboveC (its window closed first)"""
        C, S = self.cool, self.S
        if not C or not C.get("uses") or S["place"] != "home" or S["trip"] or S["asleep"] or self.minute_full():
            return
        d = self.cool_unit(S["room"])
        if d is None:
            return
        mode, sp = d.get("thermostatMode", "thermostatMode"), d.get("thermostatCoolingSetpoint", "coolingSetpoint")
        if mode != "cool" and self.sim.house.env.rooms[d.roomId]["temperature"] >= C["onAboveC"]:
            on = dict(do="home.command", args=dict(device=d.id, capability="thermostatMode", command="setThermostatMode", args=["cool"]))
            if self.leaving_soon(on, None):
                return
            w = self.win_dev(d.roomId)
            if w is not None and self.win_is_open(w) and self.win_set(w, "closed")["result"] == "done":
                self.win_stats["closedForCooling"] += 1
            if sp != C["setpointC"]:
                self.cool_cmd(d, "setCoolingSetpoint", "thermostatCoolingSetpoint", [C["setpointC"]])
            if self.cool_cmd(d, "setThermostatMode", "thermostatMode", ["cool"])["result"] == "done":
                self.cool_stats["switchedOn"] += 1
        elif mode == "cool" and sp != C["setpointC"]:
            if self.cool_cmd(d, "setCoolingSetpoint", "thermostatCoolingSetpoint", [C["setpointC"]])["result"] == "done":
                self.cool_stats["setpoint"] += 1

    def cooling_moment(self, moment, t):
        """going to bed or leaving home: each cooling unit that is on, as the habit says (keep / off); a person who does not
        use cooling switches off what a rule switched on"""
        C = self.cool
        if not C:
            return
        act = (C["sleep"] if moment == "bedtime" else C["leaving"]) if C.get("uses") else "off"
        for d in self.sim.house.devices.values():
            if d.type != "heating_cooling_unit" or d.get("thermostatMode", "thermostatMode") != "cool":
                continue
            if act == "keep" or d.id in self.keep_on:
                self.cool_stats["keptOn"] += 1
            elif self.cool_cmd(d, "setThermostatMode", "thermostatMode", ["off"])["result"] == "done":
                self.cool_stats[("sleep" if moment == "bedtime" else "leave") + "Off"] += 1

    def cooling_unused(self, did, t):
        """a cooled room left COOL_UNUSED_MIN ago and not entered since: switched off from the phone"""
        S = self.S
        d = self.sim.house.device(did)
        if d is None or S["place"] != "home" or S["trip"] or S["asleep"] or d.get("thermostatMode", "thermostatMode") != "cool":
            return
        if self.cool_unit(S["room"]) is d or d.id in self.keep_on:
            return
        if self.cool_cmd(d, "setThermostatMode", "thermostatMode", ["off"])["result"] == "done":
            self.cool_stats["unusedOff"] += 1

    # ----- window habits -----
    def win_dev(self, room):
        return self.sim.house.at(room, "window_contact")

    def win_is_open(self, d):
        return d.get("contactSensor", "contact") == "open"

    def win_set(self, d, value):
        out = self.exec(dict(do="home.record", args=dict(device=d.id, capability="contactSensor", attribute="contact", value=value)))
        if out["result"] == "done" and value == "closed":
            self.win_hot.pop(d.id, None)
            self.win_airing.discard(d.id)
            if d.id == "balcony.window_contact":
                self.outer_why.clear()
        return out

    def home_band(self, t):
        h = (t // 3600000 + 9) % 24  # local (KST) hour
        for name, a, b in HOME_BANDS:
            if (a <= h < b) if a < b else (h >= a or h < b):
                return name
        return "day"

    def home_base_tick(self, t):
        """layer A (agreed 2026-11-24): where the person is when no rule or habit is doing anything. In a room outside
        the home-base rooms of the time band (laundry room, balcony...) they go back after errandMinutes; in a home-base
        room they choose again after stayMinutes (homeBaseHabits); a stove on in the kitchen or a TV on holds them"""
        if self.idle:
            return self.idle_tick(t)
        H, S = self.hb, self.S
        if not H or S["place"] != "home" or S["trip"] or S["asleep"] or not S["room"] or self.minute_full():
            return
        if any(not k["finished"] and (k.get("room") or k["travelTo"]) for k in self.tasks):
            return  # a task that put the person in a room (or is travelling) keeps them; phone use alone does not
        room = S["room"]
        days = "weekends" if day_ok("weekends", t) else "weekdays"
        weights = {}
        for role, w in H[days][self.home_band(t)].items():
            r = self.real_room(role)
            if r in self.sim.house.room_ids and w > 0:
                weights[r] = weights.get(r, 0) + w
        if not weights:
            return
        base = room in weights
        if room != self.hb_room:  # entered a room: how long they stay
            med = H["stayMinutes"] if base else H["errandMinutes"]
            self.hb_room, self.hb_since = room, t
            self.hb_limit = max(1.0, med * math.exp(0.5 * self.gauss())) * MIN_MS
        stove = self.sim.house.at("kitchen", "stove")
        tv = self.sim.house.at(room, "tv")
        if (room == "kitchen" and stove is not None and stove.get("switch", "switch") == "on") \
                or (tv is not None and tv.get("switch", "switch") == "on"):
            self.hb_since = t  # cooking or watching: stays
            self.hb_stats["held"] += 1
            return
        if t - self.hb_since < self.hb_limit:
            return
        x, acc, to = self.rnd.random() * sum(weights.values()), 0.0, None
        for r, w in weights.items():
            acc += w
            if x < acc:
                to = r
                break
        to = to or next(iter(weights))
        self.hb_stats["draws"] += 1
        self.hb_stats["drawsBase" if base else "drawsErrand"] += 1
        if to == room:
            self.hb_stats["drawsSameRoom"] += 1
        self.hb_room = None  # draw a new stay where they end up (also when they stay)
        if to != room:
            self.go_to(to)
            self.hb_stats["returns" if not base else "moves"] += 1
            self.person_changes()

    def idle_rooms(self, act):
        rooms = []
        for role in self.idle[act].get("rooms") or IDLE_POOL[act]["rooms"]:
            r = self.real_room(role)
            if r in self.sim.house.room_ids and r not in rooms:
                rooms.append(r)
        return rooms

    def idle_tick(self, t):
        """what the person does at home when no rule or habit acts (agreed 2026-11-24): one activity at a time from
        idleActivityHabits, weighted by the time band, the one just done at IDLE_AGAIN; walk to its room, do its start
        actions, stay its time, do its end actions. A rule or habit moving the person ends it (walk()); a stove on in
        the kitchen or a TV left on by a rule holds them; after an errand outside every activity room they wait
        errandMinutes first."""
        S = self.S
        if S["place"] != "home" or S["trip"] or S["asleep"]:
            self.act = None  # left or asleep: leaving / bedtime checks dealt with the devices
            return
        if not S["room"] or self.minute_full():
            return
        if any(not k["finished"] and (k.get("room") or k["travelTo"]) for k in self.tasks):
            if self.act:
                self.end_act()
            return
        a = self.act
        if a:
            if S["room"] != a["room"]:
                self.act = None
            elif t < a["end"]:
                if a.get("queue") and t >= a["next"]:  # cleaning: on to the next room
                    room = a["queue"].pop(0)
                    self.in_idle = True
                    self.go_to(room)
                    self.in_idle = False
                    a["room"], a["next"] = S["room"], t + (a["end"] - t) / (len(a["queue"]) + 1)
                return
            else:
                self.end_act()
        room = S["room"]
        everywhere = {r for k in self.idle for r in self.idle_rooms(k)}
        if room not in everywhere:  # after an errand (laundry room, entryway...): a moment before the next thing
            if room != self.hb_room:
                med = (self.hb or {}).get("errandMinutes", 3)
                self.hb_room, self.hb_since = room, t
                self.hb_limit = max(1.0, med * math.exp(0.5 * self.gauss())) * MIN_MS
            if t - self.hb_since < self.hb_limit:
                return
        stove, tv = self.sim.house.at("kitchen", "stove"), self.sim.house.at(room, "tv")
        if (room == "kitchen" and stove is not None and stove.get("switch", "switch") == "on") \
                or (tv is not None and tv.get("switch", "switch") == "on"):
            self.hb_stats["held"] += 1
            return
        band = self.home_band(t)
        w = {k: h["weights"].get(band, 0) * (IDLE_AGAIN if k == self.last_act else 1) for k, h in self.idle.items()
             if k in IDLE_POOL and self.idle_rooms(k)}
        tot = sum(w.values())
        if tot <= 0:
            return
        x, acc, act = self.rnd.random() * tot, 0.0, None
        for k, v in w.items():
            acc += v
            if x < acc:
                act = k
                break
        self.start_act(act or next(iter(w)), t)

    def start_act(self, act, t):
        H, P = self.idle[act], IDLE_POOL[act]
        rooms = self.idle_rooms(act)
        room = rooms[int(self.rnd.random() * len(rooms))]
        self.in_idle = True
        self.go_to(room)
        self.in_idle = False
        room = self.S["room"]
        mins = max(2.0, H["minutes"] * math.exp(0.5 * self.gauss()))
        a = dict(id=act, room=room, start=t, end=t + mins * MIN_MS, endActs=[])
        cmd = lambda dev, c, cap="switch", args=None: {"do": "home.command", "args": {
            "device": dev, "capability": cap, "command": c, "args": args or [], "channel": "physical"}}
        H_ = self.sim.house
        if P.get("dev") and H_.at(room, P["dev"]) is not None:
            d = f"{room}.{P['dev']}"
            self.exec(cmd(d, "on"))
            a["endActs"].append(cmd(d, "off"))
        if P.get("light") and H_.at(room, "light") is not None:
            ls = H_.at(room, "light_sensor")
            dark = ls is None or (ls.get("illuminanceMeasurement", "illuminance") or 0) <= IDLE_DARK_LUX
            if (P.get("alwaysLight") or dark) and H_.at(room, "light").get("switch", "switch") != "on":
                self.exec(cmd(f"{room}.light", "on"))
                a["endActs"].append(cmd(f"{room}.light", "off"))
        if act == "dishes" and H_.at("kitchen", "dishwasher") is not None and self.chance(H.get("dishwasherShare", 0)):
            self.exec(cmd("kitchen.dishwasher", "setMachineState", "dishwasherOperatingState", ["run"]))
        if act == "cleaning":
            robot = H_.at("living_room", "robot_vacuum")
            if robot is not None and self.chance(H.get("robotShare", 0)):
                self.exec(cmd("living_room.robot_vacuum", "start", "robotCleanerOperatingState"))
            others = [r for r in rooms if r != room]
            self.rnd.shuffle(others)
            a["queue"] = others[:2]
            a["next"] = t + mins * MIN_MS / (len(a["queue"]) + 1)
        if act == "music":
            self.exec({"do": "phone.media", "args": {"state": "PLAYING", "title": self.rnd.choice(
                ["Daily Mix 1", "Chill Vibes", "K-Pop Hits", "Acoustic Morning", "Focus Flow"]), "artist": "Various"}})
            a["endActs"].append({"do": "phone.media", "args": {"state": "PAUSED"}})
        if P.get("app") and H.get("apps"):
            self.exec({"do": "phone.openApp", "args": {"package": self.wpick(H["apps"])}})
            a["endActs"].append({"do": "phone.closeApp", "args": {}})
        if act == "call":
            self.exec({"do": "phone.call", "args": {"state": "OFFHOOK"}})
            a["endActs"].append({"do": "phone.call", "args": {"state": "IDLE"}})
        if act == "workout" and H.get("kinds"):
            self.exec({"do": "phone.exerciseStart", "args": {"kind": self.wpick(H["kinds"])}})
            a["endActs"].append({"do": "phone.exerciseEnd", "args": {}})
        if act == "nap":
            for dev in ("light", "lamp"):
                if H_.at(room, dev) is not None and H_.at(room, dev).get("switch", "switch") == "on":
                    self.exec(cmd(f"{room}.{dev}", "off"))
        a["room"] = self.S["room"]  # where the start actions left them (a robot button in the living room...)
        self.act = a
        st = self.idle_stats.setdefault(act, dict(times=0, minutes=0.0))
        st["times"] += 1

    def wpick(self, weights):
        ks = list(weights)
        x, acc = self.rnd.random() * sum(weights.values()), 0.0
        for k in ks:
            acc += weights[k]
            if x < acc:
                return k
        return ks[-1]

    def end_act(self):
        """end the current activity where it is: its end actions (TV off, lamp off, app closed...)"""
        a, self.act = self.act, None
        if not a:
            return
        self.last_act = a["id"]
        self.idle_stats[a["id"]]["minutes"] += (self.now() - a["start"]) / MIN_MS
        for x in a["endActs"]:
            self.exec(x)

    def outer_win(self):
        """the balcony's outer window (flats with a real balcony), else None"""
        return self.win_dev("balcony") if self.sim.house.env.real_balcony else None

    def outer_open(self, why):
        """open the balcony's outer window for a reason: living (the living room window is open; agreed 2026-11-23, so the
        balcony does not become a greenhouse feeding the living room) or dry (laundry); the person goes back after"""
        d = self.outer_win()
        if d is None:
            return False
        self.outer_why.add(why)
        if not self.win_is_open(d):
            back = self.S["room"]
            ok = self.win_set(d, "open")["result"] == "done"
            if back:
                self.go_to(back)
            return ok
        return False

    def outer_release(self, why):
        """a reason ends; the outer window is closed when no reason is left"""
        d = self.outer_win()
        self.outer_why.discard(why)
        if d is not None and not self.outer_why and self.win_is_open(d):
            back = self.S["room"]
            self.win_set(d, "closed")
            if back:
                self.go_to(back)

    def window_tick(self, t):
        """awake at home: windows closed for rain; the room's window opened when it is hot inside and cooler outside, closed
        again when cool enough, when outdoor air is hotter or for cooling (only windows the habit opened); airing"""
        W, S = self.win, self.S
        if not W or S["place"] != "home" or S["trip"] or S["asleep"] or self.minute_full():
            return
        out, rooms = outdoor_at(t), self.sim.house.env.rooms
        if out["weather"] in ("rain", "snow"):
            wins = sorted((d for d in self.sim.house.devices.values() if d.type == "window_contact"),
                          key=lambda d: d.id != "balcony.window_contact")  # the outer window before the sliding door
            for d in wins:
                if self.win_is_open(d) and self.win_set(d, "closed")["result"] == "done":
                    self.win_stats["closedRain"] += 1
            return
        d = self.win_dev(S["room"])
        if d is not None and d.id not in self.win_airing and d.id != "balcony.window_contact":  # the outer window follows the living room window, laundry and rain
            temp = rooms[d.roomId]["temperature"]
            unit = self.cool_unit(S["room"])
            cooling = unit is not None and unit.get("thermostatMode", "thermostatMode") == "cool"
            if self.win_is_open(d):
                if cooling and self.win_set(d, "closed")["result"] == "done":
                    self.win_stats["closedForCooling"] += 1
                elif (d.id in self.win_hot and t - self.win_hot[d.id] >= WINDOW_MIN_OPEN_MIN * MIN_MS and temp <= W["openAboveC"] - WINDOW_CLOSE_BELOW_K
                      and self.win_set(d, "closed")["result"] == "done"):
                    self.win_stats["closedCool"] += 1
                elif (d.id in self.win_hot and t - self.win_hot[d.id] >= WINDOW_MIN_OPEN_MIN * MIN_MS and out["temperature"] > temp + 1
                      and self.win_set(d, "closed")["result"] == "done"):
                    self.win_stats["closedHotOutside"] += 1
            elif W.get("summerOpen") and not cooling and temp >= W["openAboveC"] and out["temperature"] < temp - 1:
                a = dict(do="home.record", args=dict(device=d.id, capability="contactSensor", attribute="contact", value="open"))
                if not self.leaving_soon(a, None):
                    if self.win_set(d, "open")["result"] == "done":
                        self.win_hot[d.id] = t
                        self.win_stats["hotOpen"] += 1
        self.airing_tick(t)

    def airing_tick(self, t):
        W = self.win
        day = (t + 9 * 3600000) // DAY_MS  # local day number
        plan = self.airing_plan.get(day)
        if plan is None:
            self.airing_plan = {k: v for k, v in self.airing_plan.items() if k >= day - 1}
            n = int(W.get("airingPerDay", 0))
            slots = AIRING_SLOTS if n >= 2 else ([] if n <= 0 else [AIRING_SLOTS[0] if self.rnd.random() * (AIRING_SLOTS[0][2] + AIRING_SLOTS[1][2]) < AIRING_SLOTS[0][2] else AIRING_SLOTS[1]])
            day0 = day * DAY_MS - 9 * 3600000
            plan = self.airing_plan[day] = [dict(at=day0 + int(self.uni(h0, h1) * 3600000), until=day0 + (h1 + 1) * 3600000, done=False) for h0, h1, _ in slots]
        for it in plan:
            if it["done"] or not (it["at"] <= t <= it["until"]):
                continue
            it["done"] = True
            d = self.win_dev("living_room") or self.win_dev(self.S["room"])
            if d is None or self.win_is_open(d):
                continue
            winter = outdoor_at(t)["meanTemperature"] < HEAT_SEASON_MEAN_C
            typ = W["winterAiringMinutes"] if winter else W["airingMinutes"]
            mins = max(1, js_round(typ * self.uni(0.7, 1.3)))
            if self.win_set(d, "open")["result"] == "done":
                self.win_airing.add(d.id)
                self.win_stats["airings"] += 1
                self.scheduled.append(dict(kind="airingEnd", at=self.now() + mins * MIN_MS, device=d.id))

    def airing_end(self, did, t):
        S = self.S
        d = self.sim.house.device(did)
        if d is None or did not in self.win_airing:
            return
        self.win_airing.discard(did)
        if S["place"] == "home" and not S["trip"] and not S["asleep"] and self.win_is_open(d):
            self.win_set(d, "closed")

    def window_moment(self, moment, t):
        """going to bed or leaving home: every open window closed, except at bedtime on a warm dry night for a person who
        sleeps with it open when the room is warmer than outdoors"""
        W = self.win
        if not W:
            return
        out, rooms = outdoor_at(t), self.sim.house.env.rooms
        outer = self.outer_win()
        for d in list(self.sim.house.devices.values()):
            if d.type != "window_contact" or not self.win_is_open(d) or d is outer:
                continue
            if (moment == "bedtime" and W.get("sleepOpen") and out["meanTemperature"] >= HEAT_SEASON_MEAN_C
                    and out["weather"] not in ("rain", "snow") and rooms[d.roomId]["temperature"] > out["temperature"]):
                self.win_stats["sleepOpen"] += 1
                continue
            if self.win_set(d, "closed")["result"] == "done":
                self.win_stats["closedAtCheck"] += 1
        if outer is not None and self.win_is_open(outer):
            liv = self.win_dev("living_room")
            if liv is not None and self.win_is_open(liv):
                pass  # the living room window stays open for the night: so does the outer window
            elif self.win_set(outer, "closed")["result"] == "done":
                self.win_stats["closedAtCheck"] += 1

    # ----- shower habit and laundry drying (2026-11-21) -----
    def shower_behaviours(self, H):
        """routines made from showerHabits: a morning shower after waking and / or an evening shower; the person goes to the
        bathroom, switches the light on, showers (person.shower: vapour, no line) and switches it off"""
        self.prof_shower = H
        if not H or not H.get("slots"):
            return []
        light = "bathroom.light" if self.sim.house.at("bathroom", "light") is not None else None
        def acts():
            a = [dict(do="person.moveRoom", args=dict(room="bathroom"))]
            if light:
                a.append(dict(do="home.command", args=dict(device=light, capability="switch", command="on", args=[], channel="physical")))
            a.append(dict(do="person.shower", args=dict(minutes=dict(min=H["minutes"]["min"], max=H["minutes"]["max"]))))
            if light:
                a.append(dict(do="home.command", args=dict(device=light, capability="switch", command="off", args=[], channel="physical")))
            return a
        out = []
        if "morning" in H["slots"]:
            out.append(dict(id="habit_shower_morning", kind="routine", description="Shower after waking (showerHabits).",
                            trigger=dict(kind="event", event=dict(source="person", what="wake", place="home"), delayMinutes=dict(min=3, max=20)),
                            conditions=[dict(kind="place", op="is", place="home")], actions=acts(), probability=1, maxPerDay=1))
        if "evening" in H["slots"]:
            out.append(dict(id="habit_shower_evening", kind="routine", description="Shower in the evening (showerHabits).",
                            trigger=dict(kind="daily", window={"from": H.get("eveningFrom", "21:00"), "to": H.get("eveningTo", "23:00")}),
                            conditions=[dict(kind="place", op="is", place="home")], actions=acts(), probability=1, maxPerDay=1))
        return out

    def laundry_behaviours(self, H):
        """routines made from laundryHabits (agreed 2026-11-21): washesPerWeek split into weekend mornings (09-12) and weekday
        evenings (19-22) by the person's weekendShare; the person goes to the laundry room and starts the washer by hand"""
        if not H or not H.get("washesPerWeek"):
            return []
        w = self.sim.house.at("laundry", "washer") or next((d for d in self.sim.house.devices.values() if d.type == "washer"), None)
        if w is None:
            return []
        n = H["washesPerWeek"]
        n_we = n * H.get("weekendShare", 0.5)
        acts = [dict(do="person.moveRoom", args=dict(room=w.roomId)),
                dict(do="home.command", args=dict(device=w.id, capability="washerOperatingState", command="setMachineState", args=["run"], channel="physical"))]
        out = []
        if n_we > 0:
            out.append(dict(id="habit_laundry_weekend", kind="routine", description="Laundry on weekend mornings (laundryHabits).",
                            trigger=dict(kind="daily", window={"from": "09:00", "to": "12:00"}, days="weekends"),
                            conditions=[dict(kind="place", op="is", place="home")], actions=acts, probability=min(1.0, n_we / 2), maxPerDay=1))
        if n - n_we > 0:
            out.append(dict(id="habit_laundry_weekday", kind="routine", description="Laundry on weekday evenings (laundryHabits).",
                            trigger=dict(kind="daily", window={"from": "19:00", "to": "22:00"}, days="weekdays"),
                            conditions=[dict(kind="place", op="is", place="home")], actions=acts, probability=min(1.0, (n - n_we) / 5), maxPerDay=1))
        return out

    def laundry_tick(self, t):
        """after each wash, once the person is home and awake (LAUNDRY_WAIT_MIN after the wash ends at the earliest), the
        laundry goes into the dryer with the person's share (laundryHabits.dryerShare; started by hand, logged) or onto a
        rack indoors: water (moisture.rackKg) released evenly over moisture.rackHours in the laundry room (else the living
        room), no line. A dryer a rule started since the wash counts as the dryer."""
        H, L, env, S = self.sim.house, self.laundry, self.sim.house.env, self.S
        w = H.at("laundry", "washer") or next((d for d in H.devices.values() if d.type == "washer"), None)
        if w is None:
            return
        st = w.get("washerOperatingState", "machineState")
        if L["washerWas"] == "run" and st != "run":
            L["finishedAt"], L["dryerSince"] = t, False
            L["waitMin"] = self.uni(LAUNDRY_WAIT_MIN[0], LAUNDRY_WAIT_MIN[1])
            self.laundry_stats["washes"] += 1
        L["washerWas"] = st
        if L["finishedAt"] is None:
            return
        dr = next((d for d in H.devices.values() if d.type == "dryer"), None)
        if dr is not None and dr.get("dryerOperatingState", "machineState") == "run":
            self.laundry_stats["dried"] += 1
            L["finishedAt"] = None
            return
        if t - L["finishedAt"] < L["waitMin"] * MIN_MS or S["place"] != "home" or S["trip"] or S["asleep"] or self.busy(t):
            return
        L["finishedAt"] = None
        share = (self.laundry_h or {}).get("dryerShare", 0)
        if dr is not None and self.chance(share):
            r = self.exec(dict(do="home.command", args=dict(device=dr.id, capability="dryerOperatingState", command="setMachineState",
                                                           args=["run"], channel="physical")))
            if r["result"] == "done":
                self.laundry_stats["dried"] += 1
                return
        room = "balcony" if env.real_balcony else "living_room"  # agreed 2026-11-22: the balcony, else the living room
        self.exec(dict(do="person.moveRoom", args=dict(room=room)))
        M = PHYS["moisture"]
        hours = self.uni(*M["rackHours"])
        kg = self.uni(*M["rackKg"])
        env.racks = [r for r in env.racks if not r.get("takenIn")] + [dict(room=room, start=t, gMin=kg * 1000 / (hours * 60), leftG=kg * 1000,
                                                                      totalG=kg * 1000, nextCheck=t + DRY_CHECK_FIRST_H * 3600000)]
        self.laundry_stats["racks"] += 1

    def drying_tick(self, t):
        """the person checks a rack DRY_CHECK_FIRST_H after hanging it, then every DRY_CHECK_EVERY_H, when home and awake
        (the check itself writes nothing). Dry (water left at most DRY_DONE_SHARE of the load): taken in. Not dry: with
        mild weather (dryingHabits airMinC..airMaxC, no rain) the window of the rack's room is opened (the balcony's outer
        window: no sensor; the living room's: logged); otherwise a balcony rack is moved into the living room (agreed
        2026-11-22), and in the living room heating (colder than airMinC) or cooling (warmer than airMaxC) is switched on"""
        env, S = self.sim.house.env, self.S
        if not env.racks or S["place"] != "home" or S["trip"] or S["asleep"] or self.busy(t):
            return
        D = self.dry_h or DRY_DEFAULT
        out = outdoor_at(t)
        for rk in env.racks:
            if rk.get("takenIn") or t < rk.get("nextCheck", 0):  # a rack the air has dried still waits for the person
                continue
            rk["nextCheck"] = t + DRY_CHECK_EVERY_H * 3600000
            self.exec(dict(do="person.moveRoom", args=dict(room=rk["room"])))
            if rk["leftG"] <= DRY_DONE_SHARE * rk["totalG"]:
                rk["leftG"], rk["takenIn"] = 0.0, True
                self.dry_stats["takenIn"] += 1
                self.dry_stats["hoursToDry"].append(round((t - rk["start"]) / 3600000, 1))
                self.close_drying_window(rk["room"])
                continue
            mild = D["airMinC"] <= out["temperature"] <= D["airMaxC"] and out["weather"] not in ("rain", "snow")
            if mild:
                if rk["room"] == "balcony":
                    if self.outer_open("dry"):
                        self.dry_stats["balconyWindow"] += 1
                else:
                    w = self.win_dev("living_room")
                    if w is not None and not self.win_is_open(w) and self.win_set(w, "open")["result"] == "done":
                        self.dry_window.add(w.id)
                        self.dry_stats["livingWindow"] += 1
            elif rk["room"] == "balcony":
                self.close_drying_window("balcony")
                rk["room"] = "living_room"
                self.exec(dict(do="person.moveRoom", args=dict(room="living_room")))
                self.dry_stats["movedInside"] += 1
            elif out["temperature"] < D["airMinC"]:
                fh = self.sim.house.at("living_room", "floor_heating")
                if fh is not None and fh.get("thermostatMode", "thermostatMode") != "heat":
                    comfort = (self.heat or {}).get("comfortC", 22)
                    self.heat_cmd(fh, "setHeatingSetpoint", "thermostatHeatingSetpoint", [comfort])
                    if self.heat_cmd(fh, "setThermostatMode", "thermostatMode", ["heat"])["result"] == "done":
                        self.dry_stats["heating"] += 1
            else:
                ac = self.cool_unit("living_room")
                if ac is not None and ac.get("thermostatMode", "thermostatMode") != "cool":
                    sp = (self.cool or {}).get("setpointC", 26)
                    self.cool_cmd(ac, "setCoolingSetpoint", "thermostatCoolingSetpoint", [sp])
                    if self.cool_cmd(ac, "setThermostatMode", "thermostatMode", ["cool"])["result"] == "done":
                        self.dry_stats["cooling"] += 1

    def close_drying_window(self, room):
        self.outer_release("dry")
        for did in list(self.dry_window):
            d = self.sim.house.device(did)
            self.dry_window.discard(did)
            if d is not None and self.win_is_open(d):
                self.win_set(d, "closed")

    def drying_moment(self, moment, t):
        """going to bed or leaving: windows opened for drying are closed"""
        self.close_drying_window("balcony")

    # ----- range hood habit -----
    def hood_tick(self, t):
        """each time the stove is switched on the person runs the range hood with the share of cookings the habit says
        (hoodHabits.useShare); it runs until the stove is off (effect only, no lines)"""
        d = self.sim.house.at("kitchen", "stove")
        on = d is not None and d.get("switch", "switch") == "on"
        if not on:
            self.hood_session = None
            self.sim.house.env.hood = False
            return
        if self.hood_session is None:
            self.hood_session = bool(self.hood) and self.rnd.random() < self.hood.get("useShare", 0)
            self.hood_stats["cookings"] += 1
            self.hood_stats["withHood"] += int(self.hood_session)
        self.sim.house.env.hood = self.hood_session

    # ----- ventilation habits -----
    def ventilation_tick(self, t):
        """the ventilation unit runs or not this minute, as the person's ventilationHabits say (effect only, no lines)"""
        V, S = self.vent, self.S
        on = False
        season = outdoor_at(t)["meanTemperature"] < HEAT_SEASON_MEAN_C
        if V and V.get("uses") and not (season and V.get("winter") == "off"):
            home = S["place"] == "home" and not S["trip"]
            on = V["when"] == "always" or (V["when"] == "home" and home) or (V["when"] == "awake" and home and not S["asleep"])
        self.sim.house.env.ventilator = on
        if on:
            self.vent_minutes["season" if season else "other"] += 1

    def phone_day_mult(self, t):
        """today's factor on the rate of phone-use rules: lognormal with mean 1 and sigma phoneHabits.dailySigma
        (within-person day-to-day variation; Appiah et al. 2026: unlock CV mostly above 25%, examples 16% and 60%)"""
        day = (t - self.T0) // DAY_MS
        if day != self.day_mult_day:
            s = float(self.phone.habits.get("dailySigma", 0) or 0)
            self.day_mult_day = day
            self.day_mult = math.exp(s * self.gauss() - s * s / 2) if s > 0 else 1.0
        return self.day_mult

    def run_chain(self, task):
        """run the timed events of a phone chain (phone.useApps, an app task) that fall inside this minute, at their own
        seconds. events: [[ms after the previous event, kind, payload]], kind open / do / close / closeIf"""
        c = task["chain"]
        end = self.minute_ms + MIN_MS
        last = self.chain_events(c, end, task)
        if last is not None:
            self.sec = max(self.sec, min(59, (last - self.minute_ms) // 1000))
        self.sim.clock.set_to(self.minute_ms + self.sec * 1000)
        if c["i"] >= len(c["events"]):
            task["chain"] = None

    def chain_events(self, c, end, task):
        ph, ev, last = self.phone, c["events"], None
        while c["i"] < len(ev):
            c["at"] = max(c["at"], self.minute_ms + self.sec * 1000)  # never before what already happened this minute
            if c["at"] >= end:
                break
            self.sim.clock.set_to(c["at"])
            last = c["at"]
            _, kind, p = ev[c["i"]]
            final = c["i"] == len(ev) - 1
            if final and not c.get("released"):
                ph.chains -= 1
                c["released"] = True
            if kind == "open":
                if ph.open_app(p) > 0:
                    self.gt_step(task, dict(do="phone.openApp", args=dict(package=p)), "done")
            elif kind == "do":
                r = self.exec(p, raw=True)
                c["result"] = r
                self.after_step(task, p, r)
                if task is None:
                    self.gt_step(None, p, r["result"])
            elif kind == "close" or (kind == "closeIf" and self.S["foreground"] == p):
                ph.close_app()
            elif kind == "closeIf" and final and self.S["screenOn"] and not self.S["foreground"]:
                ph.end_use(c["at"])  # the app went back earlier (another app, by hand): the use ends now that the chain does
            c["i"] += 1
            if c["i"] < len(ev):
                c["at"] += int(ev[c["i"]][0])
        return last

    def run_events_now(self, events):
        """an app task outside a running rule (off checks, reverts, habits): open the app and do the task now (the
        caller needs its result); the person's next action comes after it. Closing the app comes at its own time, run
        by the minute loop (run_loose_chains) - not written ahead with a later time while the person goes on with
        the phone (agreed 2026-11-24: one app in front at a time, none after the screen is off)"""
        k = next((i for i, e in enumerate(events) if e[1] == "do"), len(events) - 1)
        self.phone.chains += 2 if k + 1 < len(events) else 1  # one is released at the do, one when the app is closed
        c = dict(events=events[:k + 1], i=0, at=self.now() + int(events[0][0]))
        last = self.chain_events(c, float("inf"), None)
        if last is not None:
            self.sec = max(self.sec, (last - self.minute_ms) // 1000)  # past :59 it runs on into the next minute
        self.sim.clock.set_to(self.minute_ms + self.sec * 1000)
        if k + 1 < len(events):
            self.loose_chains.append(dict(events=events[k + 1:], i=0, at=(last or self.now()) + int(events[k + 1][0])))
        return c.get("result") or dict(result="done")

    def run_loose_chains(self):
        """the rest of app tasks started outside a rule (closing the app) at their own seconds, this minute"""
        end = self.minute_ms + MIN_MS
        for c in list(self.loose_chains):
            last = self.chain_events(c, end, None)
            if last is not None:
                self.sec = max(self.sec, (last - self.minute_ms) // 1000)
            self.sim.clock.set_to(self.minute_ms + self.sec * 1000)
            if c["i"] >= len(c["events"]):
                self.loose_chains.remove(c)

    # ----- apps that a task needs: the person opens the app, does the task, closes the app -----
    def task_app(self, a):
        """(package, kind) of the app an action is done in, or None. kind: tap / input / call / hangup"""
        do, args = a["do"], a.get("args") or {}
        if do == "home.command" and args.get("channel") == "mobile_app":
            return APP_FOR["home"], "tap"
        if do in ("phone.calendarAdd", "phone.calendarUpdate", "phone.calendarDelete"):
            return APP_FOR["calendar"], "input"
        if do == "phone.sms" and (args.get("direction") or "OUTGOING") == "OUTGOING":
            return APP_FOR["sms"], "input"
        if do == "phone.photo":
            return APP_FOR["camera"], "tap"
        if do == "phone.call":
            return APP_FOR["call"], ("call" if args.get("state") == "OFFHOOK" else "hangup")
        if do == "phone.appNotice" and isinstance(args.get("package"), str):
            p = args["package"]
            return p, args.get("task") or ("input" if p in INPUT_APPS else "tap")
        return None

    def app_events(self, a):
        """the timed events of one app task, or None if the action needs no app (or cannot have one now)"""
        spec = self.task_app(a)
        S = self.S
        if a["do"] in ("phone.screenshot", "phone.copyClipboard") and not S["foreground"]:
            apps = [p for p in S["installed"] if p not in APP_FOR.values()] or list(S["installed"])
            spec = (apps[int(self.rnd.random() * len(apps))], "tap")
        if not spec or S["asleep"] or self.phone.driving or spec[0] not in S["installed"]:
            return None
        pkg, kind = spec
        if kind == "call":
            return [[0, "open", pkg], [int((2 + 4 * self.rnd.random()) * 1000), "do", a]]
        if kind == "hangup":
            return [[0, "do", a], [1000, "closeIf", pkg]]
        d = TASK_SECONDS[kind]
        dwell = max(d["min"], min(600, d["median"] * math.exp(d["sigma"] * self.gauss())))
        delay = min(dwell - 1, 2 + 3 * self.rnd.random()) if kind == "tap" else max(1, dwell - (1 + 2 * self.rnd.random()))
        if S["foreground"] == pkg:  # already in front: the task only (whoever opened the app closes it)
            return [[int(delay * 1000), "do", a]]
        return [[0, "open", pkg], [int(delay * 1000), "do", a], [int((dwell - delay) * 1000), "closeIf", pkg]]

    def merge_app_steps(self, acts):
        """phone.openApp P (+ wait) + a task done in P (+ wait) + phone.closeApp -> the task alone: the engine opens and
        closes the app, with the same timing for every rule (written apart or not)"""
        out, i, n = [], 0, 0
        while i < len(acts):
            a = acts[i]
            if a["do"] == "phone.openApp" and isinstance((a.get("args") or {}).get("package"), str):
                j = i + 1
                while j < len(acts) and acts[j]["do"] == "wait":
                    j += 1
                spec = self.task_app(acts[j]) if j < len(acts) else None
                if spec and spec[0] == a["args"]["package"]:
                    out.append(acts[j])
                    k = j + 1
                    while k < len(acts) and acts[k]["do"] == "wait":
                        k += 1
                    i = k + 1 if k < len(acts) and acts[k]["do"] == "phone.closeApp" else j + 1
                    n += 1
                    continue
            out.append(a)
            i += 1
        return out, n

    def after_step(self, task, a, r):
        """bookkeeping after a step ran: stats, cooking, reverts"""
        if task is None:
            return
        s = self.stat(task["b"]["id"])
        s["steps"][r["result"]] += 1
        if a["do"] != "wait" and r["result"] in ("done", "no_change"):
            task["did"] = True
        if r.get("reason"):
            k = r["reason"][:80]
            s["refusals"][k] = s["refusals"].get(k, 0) + 1
        task["steps"].append([a["do"], r["result"], r["reason"][:80]] if r.get("reason") else [a["do"], r["result"]])
        self.gt_step(task, a, r["result"])
        ar = a.get("args") or {}
        if r["result"] == "done" and a["do"] == "home.command" and self.dev_id(ar["device"]) == "kitchen.stove" and ar.get("command") == "on":
            self.start_cooking(a, task["b"]["id"])
        if a.get("revert") and r["result"] in ("done", "no_change"):
            at = self.now() + js_round(self.num(a["revert"]["afterMinutes"])) * MIN_MS
            it = dict(kind="revert", at=at, byDevice=bool(a["revert"].get("byDevice")), action=self.resolve(a["revert"]["action"]), owner=task["b"]["id"])
            gt = task.get("gt")
            if gt is not None:  # the ground-truth line stays open until this revert ran or was dropped
                it["gt"], it["gtRevert"] = gt, dict(planned=iso_local(at), byDevice=it["byDevice"], action=it["action"], result=None)
                gt.setdefault("reverts", []).append(it["gtRevert"])
                gt["_pending"] = gt.get("_pending", 0) + 1
            self.scheduled.append(it)

    def maybe_glance(self, t):
        """a look at the lock screen (time, notifications) while awake and not using the phone"""
        ph, S = self.phone, self.S
        n = float(ph.habits.get("glancesPerDay", 0))
        day = (t - self.T0) // DAY_MS
        if day != self.glance_day:  # glances fall in the idle waking minutes: rate from yesterday's count of them
            self.glance_idle_prev = self.glance_idle or GLANCE_AWAKE_MIN
            self.glance_day, self.glance_idle = day, 0
        if n <= 0 or S["asleep"] or ph.driving or S["screenOn"] or ph.in_chain or S["foreground"]:
            return
        self.glance_idle += 1
        if self.rnd.random() < n / max(60, self.glance_idle_prev):
            at = max(t + int(self.rnd.random() * 50) * 1000, self.minute_ms + (self.sec + 1) * 1000)
            if at >= t + MIN_MS:
                return
            secs = max(3, min(600, GLANCE["median"] * math.exp(GLANCE["sigma"] * self.gauss())))
            ph.glance(at, secs)

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
            if (self.cool and d.type == "heating_cooling_unit") or (self.win and d.type == "window_contact"):
                continue  # the person's cooling / window habits decide these (cooling_moment, window_moment)
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
        if moment in ("bedtime", "leaving"):
            self.heating_moment(moment, t)
            self.drying_moment(moment, t)
            self.cooling_moment(moment, t)
            self.window_moment(moment, t)
        on = self.on_devices(t, only)
        if only is None:
            self.keep_on &= {d.id for d, _ in on}  # a keepOn device switched off since is an ordinary device again
        for d, rule in on:
            if moment != "morning" and d.id in self.keep_on:  # meant to stay on while away / asleep
                cs["keptOn"] = cs.get("keptOn", 0) + 1
                continue
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
            drop = [x for x in self.scheduled if x["kind"] == "revert" and not x["byDevice"] and not x.get("keep")
                    and self.revert_device(x) not in self.keep_on]
            self.scheduled = [x for x in self.scheduled if x not in drop]
            for x in drop:
                self.gt_revert_done(x, "not_followed", "off_check:" + moment)
        if back and S["room"] != back:
            self.walk(back)
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
        gt = self.gt_start(b, t, how) if b["kind"] == "pattern" else None
        # daily rules and delayed event rules decided whether to follow when their minute was drawn (the plan rule sees it)
        pre = how.get("follow") if how.get("follow") is not None else (how.get("daily") or {}).get("follow")
        if not (pre if pre is not None else self.chance(b["probability"])):
            if gt:
                self.gt_write(gt, "not_followed")
            s["notFollowed"] += 1
            self.trace(dict(t=iso_local(t), behaviour=b["id"], outcome="not_followed", via=how["via"]))
            return "not_followed"
        s["followed"] += 1
        b["_st"]["count"][dk] = cnt + 1
        b["_firings"] += 1
        actions = self.resolve(self.shift_actions(b, t))
        task = dict(b=b, actions=actions, i=0, until=0, travelTo=None, steps=[], start=t, via=how["via"], finished=False, gt=gt)
        if gt:
            self.gt_open.append(gt)
        if any(a["do"] == "phone.sleep" for a in actions):
            self.off_check("bedtime", t)
        self.tasks.append(task)
        self.run_task(task)
        return "followed"

    def run_task(self, task):
        s = self.stat(task["b"]["id"])
        acts = task["actions"]
        while task["i"] < len(acts) or task.get("chain"):
            if task.get("chain"):
                self.run_chain(task)
                if task.get("chain"):
                    return
                continue
            if task["until"] and self.now() < task["until"]:
                return
            if self.minute_full(acts[task["i"]]):
                return
            if task["travelTo"]:
                if self.S["trip"]:
                    return
                task["travelTo"] = None
            task["until"] = 0
            a = acts[task["i"]]
            task["i"] += 1
            S = self.S
            if a["do"] == "person.moveRoom" and self.hb and S["place"] == "home" and S["room"] == "living_room" \
                    and self.real_room((a.get("args") or {}).get("room")) == self.real_room("bedroom") \
                    and any(x["do"] == "phone.sleep" for x in acts[task["i"]:]) and self.chance(self.hb.get("sofaSleepShare", 0)):
                task["room"] = "living_room"  # stays on the sofa and sleeps there (homeBaseHabits.sofaSleepShare)
                self.hb_stats["sofaSleep"] += 1
                task["steps"].append([a["do"], "sofa"])
                continue
            if task.get("room") and a["do"] not in ("person.moveRoom", "person.travel") and S["place"] == "home" \
                    and not S["trip"] and S["room"] != task["room"]:
                # something else moved the person during the task (agreed 2026-11-24): back to the task's room first
                self.go_to(task["room"])
                self.hb_stats["backToTaskRoom"] += 1
            if a.get("probability") is not None and not self.chance(a["probability"]):
                s["steps"]["skipped"] += 1
                task["steps"].append([a["do"], "skipped"])
                continue
            if a.get("when") and not self.all_conds(a["when"], self.now()):
                s["steps"]["skipped"] += 1
                task["steps"].append([a["do"], "skipped_when"])
                continue
            if self.leaving_soon(a, task):
                s["steps"]["skipped"] += 1
                s["skippedPlan"] = s.get("skippedPlan", 0) + 1
                task["steps"].append([a["do"], "skipped_plan"])
                continue
            r = self.exec(a, in_task=True)
            if a["do"] == "person.moveRoom" and r["result"] in ("done", "no_change"):
                task["room"] = self.S["room"]
            blk = r.get("block") or {}
            if r["result"] != "pending":
                self.after_step(task, a, r)
            if a["do"] == "person.travel" and r["result"] == "refused":
                task["i"] = len(acts)
                break
            if blk.get("chain"):
                task["chain"] = dict(events=blk["chain"], i=0, at=self.now() + int(blk["chain"][0][0]))
                self.phone.chains += 1
                continue
            if blk.get("until"):
                task["until"] = blk["until"]
                return
            if blk.get("travelTo"):
                task["travelTo"] = blk["travelTo"]
                return
        task["finished"] = True
        if not task.get("did") and any(x[1] == "skipped_plan" for x in task["steps"]):
            s["followed"] -= 1  # nothing was done (switching on skipped before a departure or sleep): not followed, as the log shows
            s["notFollowed"] += 1
            s["notFollowedPlan"] = s.get("notFollowedPlan", 0) + 1
            self.trace(dict(t=iso_local(task["start"]), behaviour=task["b"]["id"], outcome="not_followed_plan", via=task["via"], steps=task["steps"]))
            if task.get("gt"):
                self.gt_finish(task["gt"], "not_followed_plan")
            return
        if self.S["foreground"] and not self.phone.in_chain and self.S["screenOffAt"] is None and any(a["do"].startswith("phone.") for a in acts):
            self.phone.end_use(self.now(), force=True)  # an app left open: the screen goes off by hand or by time-out
        self.trace(dict(t=iso_local(task["start"]), behaviour=task["b"]["id"], outcome="followed", via=task["via"], steps=task["steps"]))
        if task.get("gt"):
            self.gt_finish(task["gt"], "followed")

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
                if src == "person" and ((h["what"] == "depart" and h.get("place") == "home") or (h["what"] == "fall_asleep" and h.get("place") == "home")):
                    # when it happened: a trip's own start; sleep is seen up to a minute late (person_changes runs per minute)
                    now, grace = (h["at"], 0) if h.get("at") else (self.now(), MIN_MS)
                    for k in self.plan_skips:
                        if k["confirmedAt"] is None and k["t"] <= now <= k["t"] + k["minimum"] * MIN_MS + grace:
                            k["confirmedAt"], k["by"] = now, h["what"]
                if src == "person" and (h["what"] == "wake" or (h["what"] == "arrive" and h.get("place") == "home")):
                    self.keep_on.clear()  # the reason to keep it on (away, asleep) is over: an ordinary device again
                if src == "person" and h["what"] == "wake" and self.S["place"] == "home" and self.left_overnight:
                    self.scheduled.append(dict(kind="morning", at=self.now() + js_round(self.uni(0, self.OFF["morningWithinMinutes"])) * MIN_MS,
                                               devices=self.left_overnight))
                    self.left_overnight = []
                if src == "person" and h["what"] == "enter_room" and self.heat and self.heat.get("unusedRooms") == "off":
                    prev = getattr(self, "heat_prev_room", None)
                    if prev and self.heat_unit(prev) is not None and self.heat_unit(prev) is not self.heat_unit(h["room"]):
                        self.scheduled.append(dict(kind="heatUnused", at=self.now() + HEAT_UNUSED_MIN * MIN_MS, device=self.heat_unit(prev).id))
                if src == "person" and h["what"] == "enter_room" and self.cool and self.cool.get("unusedRooms") == "off":
                    prev = getattr(self, "heat_prev_room", None)
                    if prev and self.cool_unit(prev) is not None and self.cool_unit(prev) is not self.cool_unit(h["room"]):
                        self.scheduled.append(dict(kind="coolUnused", at=self.now() + COOL_UNUSED_MIN * MIN_MS, device=self.cool_unit(prev).id))
                if src == "person" and h["what"] == "enter_room":
                    self.heat_prev_room = h["room"]
                if src == "person" and h["what"] == "fall_asleep":
                    self.left_overnight = [d.id for d, _ in self.on_devices(self.now())]
                for b in self.behaviours:
                    tr = b["trigger"]
                    if tr["kind"] != "event" or not self.event_matches(tr["event"], src, h):
                        continue
                    if tr.get("delayMinutes") is not None:
                        self.scheduled.append(dict(kind="eventCheck", at=self.now() + js_round(self.num(tr["delayMinutes"])) * MIN_MS, b=b,
                                                   follow=self.chance(b["probability"])))  # decided now, so plans can see it
                    else:
                        self.fire(b, self.now(), dict(via="event"))

    # ----- time triggers -----
    @staticmethod
    def is_body(a):
        return a["do"] in BODY_DO or (a["do"] == "home.command" and (a.get("args") or {}).get("channel") != "mobile_app")

    def busy(self, t):
        if self.minute_full():
            return True
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
                    dl = st["daily"] = dict(dk=dk, day=day, at=day + (f + int(self.rnd.random() * ln)) * MIN_MS,
                                            follow=self.chance(b["probability"]))
                if dl["at"] == t:
                    lst.append((b, dict(day=day, via="daily", daily=dl)))
            elif tr["kind"] == "rate":
                if self.chance(tr["perHour"] * (self.phone_day_mult(t) if b["_phoneUse"] else 1) / 60):
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
        while self.scheduled and self.scheduled[0]["at"] < t + MIN_MS:  # due in this minute: at its own second
            first = self.scheduled[0]
            own = max(self.sec, (first["at"] - t) // 1000)  # it starts at its own second at the earliest
            if own + self.action_sec(first.get("action") if first["kind"] == "revert" else None) > 59 \
                    and not (first["kind"] == "revert" and first["byDevice"]) and first["kind"] != "eventCheck":
                for x in self.scheduled:  # everything due this minute that needs the person waits for the next
                    if x["at"] < t + MIN_MS and not (x["kind"] == "revert" and x["byDevice"]) and x["kind"] != "eventCheck":
                        x["at"] = t + MIN_MS
                self.scheduled.sort(key=lambda x: x["at"])
                continue
            it = self.scheduled.pop(0)
            if it["at"] > t:
                self.sec = max(self.sec, min(59, (it["at"] - t) // 1000))
                self.sim.clock.set_to(t + self.sec * 1000)
            if it["kind"] == "revert":
                if it["byDevice"]:
                    self.sim.clock.set_to(it["at"])
                    self.device_revert(it["action"])
                    self.gt_revert_done(it, "done_by_device")
                else:
                    gt = it.get("gt")
                    n0 = len(gt["then"]) if gt else 0
                    self.gt_ctx = gt
                    r = self.exec(it["action"])
                    self.gt_ctx = None
                    if gt is not None:
                        if len(gt["then"]) == n0:  # not an app task: the step itself
                            self.gt_add(gt, it["action"], r["result"])
                        ok = r["result"] in ("done", "no_change")
                        self.gt_revert_done(it, r["result"] if ok else "not_followed", None if ok else (r.get("reason") or r["result"])[:80])
                    s = self.stat(it["owner"])
                    s["steps"][r["result"]] += 1
                    if r.get("reason"):
                        k = "revert: " + r["reason"][:70]
                        s["refusals"][k] = s["refusals"].get(k, 0) + 1
            elif it["kind"] == "eventCheck":
                self.fire(it["b"], t, dict(via="event", follow=it.get("follow")))
            elif it["kind"] == "morning":
                self.off_check("morning", t, it["devices"])
            elif it["kind"] == "heatUnused":
                self.heating_unused(it["device"], t)
            elif it["kind"] == "coolUnused":
                self.cooling_unused(it["device"], t)
            elif it["kind"] == "airingEnd":
                self.airing_end(it["device"], t)
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
            # an action that ran past :59 of the last minute ends in this one: this minute starts after it, its device
            # lines too (agreed 2026-11-23: nothing piled up at :59, nothing written before what already happened)
            self.minute_ms, self.sec = t, max(0, self.sec - 60)
            self.sim.clock.set_to(t + self.sec * 1000)
            self.sim.not_before = t + self.sec * 1000 if self.sec else 0
            self.sim.tick()
            self.sim.not_before = 0
            if self.sim.front_door_until > t + self.sec * 1000:
                # came home this minute: the door lines (open, in, closed) are written up to front_door_until; the
                # person's next action starts after them (agreed 2026-11-24: nothing written before what already happened)
                self.sec = (self.sim.front_door_until - t + 999) // 1000
            self.person_changes()
            w = outdoor_at(t)["weather"]
            self.recent_weather.append((t, w))
            if w != last_w:
                self.happenings.append(("weather", dict(frm=last_w, to=w, **{"from": last_w})))
                last_w = w
            self.process_happenings()
            self.run_loose_chains()
            self.run_scheduled(t)
            self.time_triggers(t)
            self.process_happenings()
            for task in list(self.tasks):
                if not task["finished"]:
                    self.run_task(task)
                    self.process_happenings()
            self.tasks = [k for k in self.tasks if not k["finished"]]
            self.heating_tick(t)
            self.ventilation_tick(t)
            self.hood_tick(t)
            self.laundry_tick(t)
            self.drying_tick(t)
            self.cooling_tick(t)
            self.window_tick(t)
            self.home_base_tick(t)
            self.maybe_glance(t)
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
        with open(os.path.join(self.out_dir, "plan_skips.jsonl"), "w", encoding="utf-8") as f:
            for k in self.plan_skips:
                f.write(json.dumps(dict(k, t=iso_local(k["t"]), plannedAt=iso_local(k["plannedAt"]), wrong=k["confirmedAt"] is None,
                                        confirmedAt=iso_local(k["confirmedAt"]) if k["confirmedAt"] else None), ensure_ascii=False) + "\n")
        n_wrong = sum(1 for k in self.plan_skips if k["confirmedAt"] is None)
        plan_check = dict(skips=len(self.plan_skips), wrong=n_wrong, bySource={})
        for k in self.plan_skips:
            src = k["source"] or {}
            key = src.get("kind", "?") + ("" if src.get("probability") in (None, 1) else ", probability < 1")
            e = plan_check["bySource"].setdefault(key, dict(skips=0, wrong=0))
            e["skips"] += 1
            e["wrong"] += k["confirmedAt"] is None
        for gt in list(self.gt_open):  # still running when the year ended
            for e in gt.get("reverts", []):
                if e["result"] is None:
                    e["result"] = "unfinished"
            self.gt_write(gt, gt.get("_outcome") or "unfinished")
        self.gt_f.close()
        c = sorted(self.cook_times)
        q = lambda f: c[min(len(c) - 1, int(f * len(c)))] if c else None
        summary = dict(personaId=self.P["personaId"], houseId=self.sim.house_id, houseType=self.sim.type, variant=self.P["variant"], startDate=self.P["simulation"]["startDate"], days=self.days,
                       seed=self.seed, homeLines=self.n_home, phoneEvents=self.n_phone,
                       cooking=dict(times=len(c), minutesMedian=q(0.5), minutesP10=q(0.1), minutesP90=q(0.9), minutesMax=c[-1] if c else None),
                       behaviours=self.stats, checks=self.check_stats, planSkips=plan_check, heating=dict(self.heat_stats, kWh=round(sum(self.sim.house.env.heat_wh.values()) / 1000, 1),
                                       kWhPerM2=round(sum(self.sim.house.env.heat_wh.values()) / 1000 / self.sim.house.profile["areaM2"], 1)),
                       cooling=dict(habits=self.cool, **self.cool_stats), windows=dict(habits=self.win, **self.win_stats),
                       hood=dict(habits=self.hood, **self.hood_stats), showers=dict(habits=self.prof_shower, **self.shower_stats),
                       laundry=dict(habits=self.laundry_h, **self.laundry_stats),
                       homeBase=dict(habits=self.hb, **self.hb_stats),
                       idleActivities={k: dict(times=v["times"], hours=round(v["minutes"] / 60, 1)) for k, v in sorted(self.idle_stats.items())},
                       drying=dict(habits=self.dry_h, **{k: v for k, v in self.dry_stats.items() if k != "hoursToDry"},
                                   medianHoursToDry=(sorted(self.dry_stats["hoursToDry"])[len(self.dry_stats["hoursToDry"]) // 2] if self.dry_stats["hoursToDry"] else None)),
                       ventilation=dict(habits=self.vent, hoursInHeatingSeason=round(self.vent_minutes["season"] / 60), hoursOtherwise=round(self.vent_minutes["other"] / 60)),
                       seconds=round(_time.time() - t0))
        with open(os.path.join(self.out_dir, "summary.json"), "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
            f.write("\n")
        self.print(f"done: {self.n_phone} phone events ({self.n_home} of them copies of home lines) -> {self.out_dir}")
        return summary
