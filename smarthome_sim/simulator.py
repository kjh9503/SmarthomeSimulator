"""The smart home: devices, sensor reports, the log saving policy and the person's front door / presence.
Ported from smarthome-sim.html (class Simulator). Times are epoch ms (Korea time)."""
import bisect
import math
import random

from .timeutil import DAY_MS, MIN_MS, iso_local, start_of_day, js_round
from .weather import outdoor_at
from .house import (House, SPEC, ROOM_PROFILES, DEFAULT_VARIANT, PHYS, SENSOR_ATTRS, round_to, vapor_from_rh)
from .phone import Phone, PLACES

DEFAULT_BACKGROUND_PER_DAY = 500
# minutes [before, after] an action whose room's sensor reports are all kept
ACTION_WINDOWS = dict(light=[5, 10], lamp=[5, 10], curtain=[5, 10], tv=[5, 30], speaker=[5, 30], air_purifier=[5, 30],
                      heating_cooling_unit=[10, 60], humidifier=[10, 60], window_contact=[10, 60], door_contact=[10, 60],
                      stove=[10, 60], oven=[10, 60], occupancy_sensor=[10, 60], washer=[5, 30], dryer=[5, 30], dishwasher=[5, 30],
                      robot_vacuum=[5, 30])
DEFAULT_WINDOW = [5, 10]
MAX_AFTER_MIN = 60
# a "big change" versus the last saved value
BIG_CHANGE = dict(
    pm25=dict(bounds=[15, 35, 75], hys=2),                 # PM2.5 forecast grades
    co2=dict(bounds=[1000], hys=50, delta=300),            # 1,000 ppm indoor standard
    humidity=dict(bounds=[40, 60], hys=2, delta=10),       # 40-60% recommended range
    noise=dict(delta=10),                                  # +10 dB sounds twice as loud
    temperature=dict(bounds=[18, 26], hys=0.5, delta=2),   # simulator's choice
    illuminance=dict(bounds=[50], hys=10, rel=0.5, relFloor=50),
)
HAND_RECORDED = ("window_contact", "door_contact")
# front door: unlock, open, close, auto-lock (seconds after the start: simulator's choice)
FRONT_DOOR = dict(autoLock=True, openSec=5, closeSec=10, lockSec=12)
# appliances that switch themselves off after this many minutes on: stove "4시간 연속 사용 시 ... 강제로 꺼집니다"
# (Rinnai RBR-P2500 manual); oven "automatically turn off the oven after 12 hours during baking functions" (GE range manual)
AUTO_OFF_MIN = dict(stove=240, oven=720)
ROOM_LABEL_FOR_REFUSAL = None


def big_change(ek, last, v):
    if last is None:
        return "initial"
    c = BIG_CHANGE[ek]
    if "bounds" in c and any((last <= b and v > b + c["hys"]) or (last > b and v < b - c["hys"]) for b in c["bounds"]):
        return "big_change"
    if c.get("delta") is not None and abs(v - last) >= c["delta"]:
        return "big_change"
    if c.get("rel") is not None and abs(v - last) >= c["rel"] * max(abs(last), c.get("relFloor") or 1):
        return "big_change"
    return None


_ORDER = {"_": 1, ".": 2, "|": 3}


def _locale_key(s):
    """the order of JavaScript localeCompare for these ids: punctuation (_ . |) < digits < letters, case ignored first"""
    return ([_ORDER.get(ch, 10 + ord(ch) - 48 if ch.isdigit() else 100 + ord(ch.lower())) for ch in s], s.swapcase())


class EventLog:
    """the home log, kept in time order"""

    def __init__(self):
        self.entries, self.times = [], []

    def add(self, e, t=None):
        t = t if t is not None else e["_t"]
        if not self.times or self.times[-1] <= t:
            self.entries.append(e)
            self.times.append(t)
            return
        i = bisect.bisect_right(self.times, t)
        self.entries.insert(i, e)
        self.times.insert(i, t)


class Clock:
    def __init__(self, ms=0):
        self.ms = ms

    def now(self):
        return self.ms

    def set_to(self, ms):
        self.ms = ms


class Simulator:
    def __init__(self, variant=DEFAULT_VARIANT, start_ms=0, seed=0, spec=SPEC, background_per_day=DEFAULT_BACKGROUND_PER_DAY):
        self.spec = spec
        self.rng = random.Random(seed)
        self.log = EventLog()
        self.clock = Clock(start_ms)
        self.house_id = "house001"
        self.variant = variant
        self.last_step = None
        self.background_per_day = background_per_day
        self.pending = dict(raw=[], actions=[], openDay=None, rangeStart=None)
        self.last_saved, self.last_raw = {}, {}
        self.last_refusal = None
        self.phone = Phone(self)
        self.house = House(variant, spec, start_ms)
        self.type = ROOM_PROFILES[variant]["houseType"]
        self.sync_router(True)
        devs = list(self.house.devices.values())
        self._auto_off = [d for d in devs if d.type in AUTO_OFF_MIN]
        self._cycle = [d for d in devs if d.cap("cycleState")]
        self._robot = [d for d in devs if d.type == "robot_vacuum"]
        self._oven = [d for d in devs if d.type == "oven"]
        self._sensors = [(d, cap, attr, ek, f"{d.id}|{cap}.{attr}") for d in devs for cap, attr, ek in SENSOR_ATTRS.get(d.type, ())]
        self._sensor_keys = sorted(self._sensors, key=lambda s: _locale_key(s[4]))

    def gauss(self):
        r = self.rng.random
        u = 0
        while not u:
            u = r()
        v = 0
        while not v:
            v = r()
        return math.sqrt(-2 * math.log(u)) * math.cos(2 * math.pi * v)

    # ----- log lines -----
    def sync_router(self, silent=False, time=None):
        h = self.house
        router = next((d for d in h.devices.values() if d.type == "wifi_router"), None)
        if not router:
            return 0
        smart = len(h.devices) - 1
        ch = router.set("connectedDevices", "connectedDevices", smart + (1 if self.phone.s["wifi"] == PLACES["home"]["wifi"] else 0))
        if not ch["changed"] or silent:
            return 0
        self.record(router, ch, "device", None, [], time)
        return 1

    def build(self, device, change, source, command, args, time=None, reason=None, channel=None):
        t = self.clock.now() if time is None else time
        return {"time": iso_local(t), "houseId": self.house_id, "houseType": self.type, "houseVariant": self.variant,
                "weather": outdoor_at(t)["weather"], "deviceId": device.id, "roomId": device.roomId, "device": device.type,
                "capability": change["capability"], "attribute": change["attribute"], "value": change["value"],
                "previousValue": change["previousValue"], "source": source, "command": command, "args": args if args is not None else [],
                "channel": (channel or "physical") if source == "command" else None, "reason": reason, "_t": t}

    def record(self, device, change, source, command, args, time=None, channel=None, reason=None):
        e = self.build(device, change, source, command, args, time, reason, channel)
        self.log.add(e)
        self.phone.copy_home([e])
        if source in ("command", "manual", "event"):
            self.note_action(device, time)
        return e

    def note_action(self, device, time=None):
        t = self.clock.now() if time is None else time
        before, after = ACTION_WINDOWS.get(device.type, DEFAULT_WINDOW)
        rooms = [device.roomId]
        if device.roomId == "balcony" and device.type == "door_contact":
            rooms.append("living_room")
        self.pending["actions"].append(dict(t=t, frm=t - before * MIN_MS, to=t + after * MIN_MS, rooms=rooms))

    def set_presence(self, room_id, time=None):
        t = self.clock.now() if time is None else time
        sensors = [d for d in self.house.devices.values() if d.type == "occupancy_sensor"]
        sensors.sort(key=lambda d: d.roomId == room_id)  # "not present" lines first
        n = 0
        for d in sensors:
            ch = d.set("presenceSensor", "presence", "present" if d.roomId == room_id else "not present")
            if not ch["changed"]:
                continue
            e = self.build(d, ch, "sensor", None, [], t, "presence")
            self.log.add(e)
            self.phone.copy_home([e])
            self.note_action(d, t)
            n += 1
        return n

    def where_refusal(self, d):
        from .house import ROOM_LABEL
        s = self.phone.s
        name = lambda r: ROOM_LABEL.get(r, r)
        if s["asleep"]:
            return "The person is asleep: wake them first (Phone panel, Wake up)"
        if s["place"] != "home":
            where = f'on the way ({PLACES[s["place"]]["label"]})' if s["trip"] else f'at {PLACES[s["place"]]["label"]}'
            return f'The person is {where}, not at home: use Control from "Phone app", or travel home first'
        ok = s["room"] == d.roomId or (d.id == "balcony.door_contact" and s["room"] == "living_room")
        if not ok:
            here = f'in {name(s["room"])}' if s["room"] else "at home, room unknown"
            return f"The person is {here}, not in {name(d.roomId)}: move them there first (Phone panel, Go to room), or use the phone app"
        return None

    def use_front_door(self, t0):
        h = self.house
        lock, door = h.device("entryway.lock"), h.device("entryway.door_contact")
        n = 0

        def put(d, cap, attr, v, source, cmd, sec):
            nonlocal n
            if not d:
                return
            ch = d.set(cap, attr, v)
            if not ch["changed"]:
                return
            self.record(d, ch, source, cmd, [], t0 + sec * 1000, "physical" if source == "command" else None)
            n += 1

        put(lock, "lock", "lock", "unlocked", "command", "unlock", 0)
        put(door, "contactSensor", "contact", "open", "manual", None, FRONT_DOOR["openSec"])
        put(door, "contactSensor", "contact", "closed", "manual", None, FRONT_DOOR["closeSec"])
        if FRONT_DOOR["autoLock"]:
            put(lock, "lock", "lock", "locked", "device", None, FRONT_DOOR["lockSec"])
        return n

    def run(self, device_id, cap, cmd, args=(), channel="physical"):
        """a command: one log line per changed value; a refused command logs nothing and leaves the reason in last_refusal"""
        d = self.house.device(device_id)
        args = list(args)
        self.last_refusal = None
        if channel == "physical":
            why = self.where_refusal(d)
            if why:
                self.last_refusal = why
                return 0
        changes = [ch for ch in (d.set(c, a, v) for c, a, v in d.effects(cap, cmd, args)) if ch["changed"]]
        for ch in changes:
            self.record(d, ch, "command", cmd, args, None, channel)
        if d.type == "robot_vacuum" and cmd == "start":
            d.aux["run"] = 0
        return len(changes)

    def set_value(self, device_id, cap, attr, value):
        """a value set directly: hand-made states (windows, doors), a doorbell push, a manual sensor reading"""
        d = self.house.device(device_id)
        self.last_refusal = None
        if d.type == "occupancy_sensor" and attr == "presence":
            ph = self.phone
            if value == "present":
                if ph.s["place"] != "home":
                    self.last_refusal = f'The person is at {PLACES[ph.s["place"]]["label"]}: they have to travel home first (Phone panel)'
                    return 0
                return ph.move_room(d.roomId)
            if d.roomId == ph.s["room"]:
                if ph.s["asleep"]:
                    self.last_refusal = "The person is asleep in this room: wake them first"
                    return 0
                ph.s["room"] = None
                return self.set_presence(None)
            return 0
        if d.type in HAND_RECORDED:
            why = self.where_refusal(d)
            if why:
                self.last_refusal = why
                return 0
        sensed = next((x for x in SENSOR_ATTRS.get(d.type, ()) if x[0] == cap and x[1] == attr), None)
        if sensed:
            room = self.house.env.rooms[d.roomId]
            room[sensed[2]] = value
            if sensed[2] == "humidity":
                room["vapor"] = vapor_from_rh(value, room["temperature"])
            d.aux.setdefault("lastReport", {})[sensed[2]] = self.clock.now()
            k = f"{d.id}|{cap}.{attr}"
            self.last_raw[k] = value
            self.last_saved[k] = value
        ch = d.set(cap, attr, value)
        if d.type == "doorbell":
            self.record(d, ch, "event", None, [])
            return 1
        if not ch["changed"]:
            return 0
        self.record(d, ch, "manual", None, [])
        return 1

    # ----- time passing -----
    def tick(self):
        """advance the world in 1-minute steps up to the clock"""
        now = self.clock.now()
        if self.last_step is None or now < self.last_step - PHYS["stepMs"]:
            self.last_step = now
            return 0
        n = 0
        p = self.pending
        while self.last_step + PHYS["stepMs"] <= now:
            frm = self.last_step
            self.last_step += PHYS["stepMs"]
            if p["openDay"] is None:
                p["openDay"] = start_of_day(frm)
                p["rangeStart"] = frm
            self.step_once(self.last_step)
            while self.last_step >= p["openDay"] + DAY_MS + MAX_AFTER_MIN * MIN_MS:
                self.close_day(p["openDay"] + DAY_MS)
            n += 1
        return n

    def jump_to(self, ms):
        gap = abs(ms - self.clock.now())
        self.flush()
        self.clock.set_to(ms)
        self.last_step = ms
        if gap > 6 * 3600000:
            self.house.env.settle(ms)
            self.house.sync_sensors()

    def flush(self):
        if self.pending["openDay"] is not None and self.last_step is not None:
            self.close_day(min(self.last_step, self.pending["openDay"] + DAY_MS), True)

    def close_day(self, end_ms, partial=False):
        """choose which of the day's sensor reports to save, add exactly N background lines, write them to the log"""
        p = self.pending
        day_start = p["openDay"]
        range_start = max(p["rangeStart"] if p["rangeStart"] is not None else day_start, day_start)
        today = [r for r in p["raw"] if r["t"] < end_ms]
        later = [r for r in p["raw"] if r["t"] >= end_ms]
        # action windows per room, for a quick "inside a window" check
        win = {}
        for a in p["actions"]:
            for room in a["rooms"]:
                win.setdefault(room, []).append((a["frm"], a["to"]))
        merged = {}
        for room, iv in win.items():
            iv.sort()
            m = []
            for a, b in iv:
                if m and a <= m[-1][1]:
                    m[-1][1] = max(m[-1][1], b)
                else:
                    m.append([a, b])
            merged[room] = ([x[0] for x in m], [x[1] for x in m])

        def in_window(r):
            m = merged.get(r["entry"]["roomId"])
            if not m:
                return False
            i = bisect.bisect_right(m[0], r["t"]) - 1
            return i >= 0 and r["t"] <= m[1][i]

        keys = self._sensor_keys
        N = max(0, int(self.background_per_day or 0))
        A = len(keys)
        span = end_ms - range_start
        events = [(r["t"], 0, i, r) for i, r in enumerate(today)]
        if A and span > 0:
            for i, k in enumerate(keys):
                count = N // A + (1 if i < N % A else 0)
                for j in range(count):
                    events.append((range_start + math.floor(((j + 0.5) / count) * span / MIN_MS) * MIN_MS, 1, len(events), k))
        events.sort(key=lambda x: (x[0], x[1], x[2]))
        saved = []
        for t, kind, _, x in events:
            if kind == 0:
                entry, key, ek = x["entry"], x["key"], x["ek"]
                v = entry["value"]
                self.last_raw[key] = v
                reason = "action_window" if in_window(x) else big_change(ek, self.last_saved.get(key), v)
                if reason:
                    e = dict(entry)
                    e["previousValue"] = self.last_saved.get(key)
                    e["reason"] = reason
                    saved.append(e)
                    self.last_saved[key] = v
            else:
                d, cap, attr, ek, key = x
                v = self.last_raw.get(key)
                if v is None:
                    v = d.get(cap, attr)
                saved.append(self.build(d, dict(capability=cap, attribute=attr, value=v, previousValue=self.last_saved.get(key)),
                                        "sensor", None, [], t, "background"))
                self.last_saved[key] = v
        # write in time order
        L = self.log
        i0 = bisect.bisect_left(L.times, day_start)
        tail = L.entries[i0:] + saved
        tail.sort(key=lambda e: e["_t"])
        del L.entries[i0:]
        del L.times[i0:]
        L.entries.extend(tail)
        L.times.extend(e["_t"] for e in tail)
        self.phone.copy_home(saved)
        p["raw"] = later
        p["actions"] = [a for a in p["actions"] if a["to"] >= end_ms]
        if partial:
            p["openDay"] = p["rangeStart"] = None
        else:
            p["openDay"] = day_start + DAY_MS
            p["rangeStart"] = p["openDay"]
        self.phone.prune(p["openDay"] if p["openDay"] is not None else self.last_step)
        return len(saved)

    def step_once(self, t):
        self.step_devices(t)
        self.house.env.step(t, 1)
        self.report_sensors(t)
        self.phone.step(t)

    def step_devices(self, t):
        for d in self._auto_off:
            c, at, off_v = ("switch", "switch", "off") if d.type == "stove" else ("mode", "mode", "off")
            on = d.get(c, at) != off_v
            d.aux["onMin"] = d.aux.get("onMin", 0) + 1 if on else 0
            if on and d.aux["onMin"] >= AUTO_OFF_MIN[d.type]:
                e = self.build(d, d.set(c, at, off_v), "device", None, [], t, "auto_off")
                self.log.add(e)
                self.phone.copy_home([e])
                d.aux["onMin"] = 0

        def log_if(d, c, a, v, loud):
            ch = d.set(c, a, v)
            if ch["changed"] and loud:
                self.record(d, ch, "device", None, [], t)

        for d in self._cycle:
            if d.get("cycleState", "cycleState") == "running":
                rem = max(0, (d.get("remainingTime", "remainingTime") or 0) - 1)
                log_if(d, "remainingTime", "remainingTime", rem, rem % 5 == 0)
                if rem == 0:
                    log_if(d, "cycleState", "cycleState", "finished", True)
        for d in self._robot:
            st, bat = d.get("robotCleanerOperatingState", "operatingState"), d.get("battery", "battery")
            nb = bat
            if st == "running":
                d.aux["run"] = d.aux.get("run", 0) + 1
                nb = max(0, bat - 1)
                if d.aux["run"] >= 45 or nb <= 15:
                    log_if(d, "robotCleanerOperatingState", "operatingState", "seekingCharger", True)
                    d.aux["seek"] = 0
            elif st == "seekingCharger":
                d.aux["seek"] = d.aux.get("seek", 0) + 1
                if d.aux["seek"] >= 2:
                    log_if(d, "robotCleanerOperatingState", "operatingState", "docked", True)
            elif st == "docked" and bat < 100:
                nb = min(100, bat + 2)
            log_if(d, "battery", "battery", nb, nb // 5 != bat // 5 or nb == 100)
        for d in self._oven:
            target, cur = d.get("temperatureSetpoint", "temperatureSetpoint"), d.get("temperatureMeasurement", "temperature")
            room_t = js_round(self.house.env.rooms[d.roomId]["temperature"])
            if d.get("mode", "mode") != "off":
                nxt = min(target, cur + 8)
                pre = "ready" if nxt >= target - 5 else "preheating"
            else:
                nxt = max(room_t, cur - 3)
                pre = "idle"
            log_if(d, "temperatureMeasurement", "temperature", nxt, False)
            log_if(d, "preheat", "preheat", pre, True)

    def report_sensors(self, t):
        rooms = self.house.env.rooms
        rep, jit = PHYS["report"], PHYS["jitter"]
        hb = PHYS["heartbeatMin"] * MIN_MS
        g = self.gauss
        for d, cap, attr, ek, key in self._sensors:
            e = rooms[d.roomId]
            lr = d.aux.setdefault("lastReport", {})
            cfg, j = rep[ek], jit[ek]
            v = e[ek] + (e[ek] * j if ek == "illuminance" else j) * g()
            v = round_to(max(0, min(100, v) if ek == "humidity" else v), cfg["dec"])
            if cfg["dec"] == 0:
                v = int(v)
            prev, last = d.get(cap, attr), lr.get(ek)
            th = max(cfg["th"], abs(prev or 0) * cfg["rel"]) if cfg.get("rel") else cfg["th"]
            if prev is None or last is None or abs(v - prev) >= th or t - last >= hb:
                entry = self.build(d, d.set(cap, attr, v), "sensor", None, [], t)
                self.pending["raw"].append(dict(t=t, entry=entry, key=key, ek=ek))
                lr[ek] = t
