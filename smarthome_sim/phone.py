"""The person's phone: places and trips, activity, Bluetooth, Wi-Fi, apps, calls, media, calendar, sleep, exercise,
health records and the SMARTTHINGS copy of every saved home log line. Events follow event-formats v3:
type, source, title, text, timestamp, collectedAt, dedupeKey, payload, context {battery, weather, location}.
Ported from smarthome-sim.html (class Phone); all rates are the simulator's choice unless a source is named."""
import bisect
import math

from .timeutil import MIN_MS, fields, hours, local_ms, js_round, parse_iso
from .weather import outdoor_at
from .house import ROOM_LABEL, DEVICE_LABEL

PLACES = {
    "home": dict(label="Home", category="Home", lat=37.5013, lng=127.0396, wifi="Home-WiFi"),
    "office": dict(label="Office", category="Work and study", lat=37.5665, lng=126.9780, wifi="Office-WiFi"),
    "coworking": dict(label="Coworking space", category="Work and study", lat=37.4986, lng=127.0284, wifi="Cowork-Guest"),
    "campus": dict(label="Campus", category="Work and study", lat=37.5596, lng=126.9370, wifi="eduroam"),
    "library": dict(label="Library", category="Work and study", lat=37.5050, lng=127.0050, wifi="Library-Free"),
    "station": dict(label="Train station", category="Transport", lat=37.5547, lng=126.9707, wifi=None),
    "subway_station": dict(label="Subway station", category="Transport", lat=37.4979, lng=127.0276, wifi=None),
    "bus_stop": dict(label="Bus stop", category="Transport", lat=37.5030, lng=127.0410, wifi=None),
    "airport": dict(label="Airport", category="Transport", lat=37.4602, lng=126.4407, wifi="Airport_Free_WiFi"),
    "gas_station": dict(label="Gas station", category="Transport", lat=37.5080, lng=127.0450, wifi=None),
    "parking_lot": dict(label="Parking lot", category="Transport", lat=37.5070, lng=127.0560, wifi=None),
    "cafe": dict(label="Cafe", category="Food and drink", lat=37.5005, lng=127.0365, wifi="Cafe-Guest"),
    "restaurant": dict(label="Restaurant", category="Food and drink", lat=37.5100, lng=127.0600, wifi=None),
    "bakery": dict(label="Bakery", category="Food and drink", lat=37.5019, lng=127.0412, wifi=None),
    "bar": dict(label="Bar", category="Food and drink", lat=37.5340, lng=126.9940, wifi=None),
    "market": dict(label="Market", category="Shopping", lat=37.5700, lng=127.0090, wifi=None),
    "grocery_store": dict(label="Grocery store", category="Shopping", lat=37.5025, lng=127.0420, wifi=None),
    "convenience_store": dict(label="Convenience store", category="Shopping", lat=37.5016, lng=127.0401, wifi=None),
    "mall": dict(label="Shopping mall", category="Shopping", lat=37.5126, lng=127.1025, wifi="Mall-Free-WiFi"),
    "department_store": dict(label="Department store", category="Shopping", lat=37.5085, lng=127.0595, wifi="Store-Guest"),
    "electronics_store": dict(label="Electronics store", category="Shopping", lat=37.5290, lng=126.9640, wifi=None),
    "gym": dict(label="Gym", category="Leisure and sport", lat=37.5045, lng=127.0490, wifi=None),
    "swimming_pool": dict(label="Swimming pool", category="Leisure and sport", lat=37.5060, lng=127.0300, wifi=None),
    "park": dict(label="Park", category="Leisure and sport", lat=37.5196, lng=127.0410, wifi=None),
    "river_park": dict(label="Riverside park", category="Leisure and sport", lat=37.5172, lng=126.9955, wifi=None),
    "hiking_trail": dict(label="Hiking trail", category="Leisure and sport", lat=37.4450, lng=126.9640, wifi=None),
    "cinema": dict(label="Cinema", category="Leisure and sport", lat=37.5113, lng=127.0590, wifi=None),
    "museum": dict(label="Museum", category="Leisure and sport", lat=37.5240, lng=126.9800, wifi="Museum-Free"),
    "stadium": dict(label="Stadium", category="Leisure and sport", lat=37.5155, lng=127.0730, wifi=None),
    "place_of_worship": dict(label="Place of worship", category="Leisure and sport", lat=37.5030, lng=127.0250, wifi=None),
    "hospital": dict(label="Hospital", category="Health and services", lat=37.4881, lng=127.0857, wifi="Hospital-Guest"),
    "clinic": dict(label="Clinic", category="Health and services", lat=37.5010, lng=127.0380, wifi=None),
    "dentist": dict(label="Dentist", category="Health and services", lat=37.5008, lng=127.0372, wifi=None),
    "pharmacy": dict(label="Pharmacy", category="Health and services", lat=37.5012, lng=127.0388, wifi=None),
    "bank": dict(label="Bank", category="Health and services", lat=37.5020, lng=127.0360, wifi=None),
    "post_office": dict(label="Post office", category="Health and services", lat=37.5000, lng=127.0330, wifi=None),
    "hair_salon": dict(label="Hair salon", category="Health and services", lat=37.5040, lng=127.0370, wifi=None),
    "government_office": dict(label="Government office", category="Health and services", lat=37.5172, lng=127.0473, wifi=None),
    "friend_home": dict(label="Friend's home", category="People and stays", lat=37.5500, lng=127.0700, wifi="Friend-WiFi"),
    "parents_home": dict(label="Parents' home", category="People and stays", lat=37.6500, lng=127.0600, wifi="Parents-WiFi"),
    "hotel": dict(label="Hotel", category="People and stays", lat=37.5100, lng=127.0590, wifi="Hotel-Guest"),
    # while travelling the person is "in" the means of transport
    "on_foot": dict(label="On foot", category="On the move", lat=None, lng=None, wifi=None),
    "bicycle": dict(label="Bicycle", category="On the move", lat=None, lng=None, wifi=None),
    "scooter": dict(label="E-scooter", category="On the move", lat=None, lng=None, wifi=None),
    "motorcycle": dict(label="Motorcycle", category="On the move", lat=None, lng=None, wifi=None),
    "car": dict(label="Car (driving)", category="On the move", lat=None, lng=None, wifi=None),
    "car_passenger": dict(label="Car (passenger)", category="On the move", lat=None, lng=None, wifi=None),
    "taxi": dict(label="Taxi", category="On the move", lat=None, lng=None, wifi=None),
    "bus": dict(label="Bus", category="On the move", lat=None, lng=None, wifi=None),
    "subway": dict(label="Subway", category="On the move", lat=None, lng=None, wifi=None),
    "train": dict(label="Train", category="On the move", lat=None, lng=None, wifi=None),
    "airport_rail": dict(label="Airport railroad", category="On the move", lat=None, lng=None, wifi=None),
}
ROAD_FACTOR = 1.3
TRAVEL_MODES = {
    "walk": dict(place="on_foot", activity="WALKING", kmh=4.8, before=[], after=[]),
    "bicycle": dict(place="bicycle", activity="ON_BICYCLE", kmh=15, before=[["walk", 2]], after=[["walk", 2]]),
    "scooter": dict(place="scooter", activity="IN_VEHICLE", kmh=15, before=[["walk", 3]], after=[["walk", 1]]),
    "motorcycle": dict(place="motorcycle", activity="IN_VEHICLE", kmh=30, before=[["walk", 2]], after=[["walk", 2]], drives=True),
    "car": dict(place="car", activity="IN_VEHICLE", kmh=25, before=[["walk", 3]], after=[["walk", 3]], drives=True, bt="Car Audio"),
    "car_passenger": dict(place="car_passenger", activity="IN_VEHICLE", kmh=25, before=[["walk", 3]], after=[["walk", 3]]),
    "taxi": dict(place="taxi", activity="IN_VEHICLE", kmh=25, before=[["wait", 5]], after=[["walk", 1]]),
    "bus": dict(place="bus", activity="IN_VEHICLE", kmh=18, before=[["walk", 5], ["wait", 6]], after=[["walk", 5]]),
    "subway": dict(place="subway", activity="IN_VEHICLE", kmh=30, before=[["walk", 7], ["wait", 4]], after=[["walk", 7]]),
    "train": dict(place="train", activity="IN_VEHICLE", kmh=80, before=[["walk", 10], ["wait", 10]], after=[["walk", 10]]),
    "airport_rail": dict(place="airport_rail", activity="IN_VEHICLE", kmh=60, before=[["walk", 8], ["wait", 6]], after=[["walk", 8]]),
}
APPS = {
    "com.kakao.talk": dict(label="KakaoTalk", uid=10101, mbPerMin=0.3),
    "com.android.chrome": dict(label="Chrome", uid=10123, mbPerMin=1.5),
    "com.google.android.youtube": dict(label="YouTube", uid=10131, mbPerMin=12),
    "com.spotify.music": dict(label="Spotify", uid=10142, mbPerMin=1),
    "com.instagram.android": dict(label="Instagram", uid=10155, mbPerMin=6),
    "com.nhn.android.nmap": dict(label="Naver Map", uid=10163, mbPerMin=1),
    "com.samsung.android.oneconnect": dict(label="SmartThings", uid=10177, mbPerMin=0.2),
}
BT_DEVICES = {"Galaxy Buds": "AA:BB:CC:DD:EE:FF", "Car Audio": "11:AA:22:BB:33:CC"}
ACTIVITIES = dict(IN_VEHICLE=0, ON_BICYCLE=1, STILL=3, WALKING=7, RUNNING=8)
# heart rate: resting 60-100 bpm (AHA via Sleep Foundation); sleep 20-30% lower, lowest in deep sleep, near waking in REM
# (Sleep Foundation); max = 220 - age, moderate 50-60% and vigorous 70-85% of max (MSD Manual). Shape and noise: simulator's choice.
HEART = dict(person=dict(age=35, restingBpm=66), awake=dict(STILL=1.05, IN_VEHICLE=1.08, DRIVING=1.14),
             active=dict(WALKING=0.55, ON_BICYCLE=0.63, RUNNING=0.78),
             sleep=dict(light=0.80, deep=0.71, deepLate=0.75, rem=0.92, cycleMin=90, lightMin=15),
             dayRhythm=0.03, follow=dict(up=0.45, down=0.25), noise=dict(asleep=1.5, awake=2.5, active=4))
CADENCE_SD = 0.08
ROOM_STEPS = [10, 30]
BODY = dict(STILL=dict(steps=0, m=0, kcal=0.3), WALKING=dict(steps=100, m=75, kcal=4), RUNNING=dict(steps=160, m=175, kcal=11),
            ON_BICYCLE=dict(steps=0, m=250, kcal=7), IN_VEHICLE=dict(steps=0, m=0, kcal=0.2), ASLEEP=dict(steps=0, m=0, kcal=0))
EXERCISES = dict(Running=dict(code=56, activity="RUNNING"), Walking=dict(code=79, activity="WALKING"), Cycling=dict(code=8, activity="ON_BICYCLE"))


def _bp(v):
    s, d = (float(x) for x in str(v).split("/"))
    return dict(systolic=s, diastolic=d)


MEASURES = dict(
    WEIGHT=(lambda v: f"{v} kg", lambda v: dict(kilograms=v)),
    BODY_FAT=(lambda v: f"{v}%", lambda v: dict(percentage=v)),
    BLOOD_PRESSURE=(lambda v: f"{v} mmHg", _bp),
    BLOOD_GLUCOSE=(lambda v: f"{v} mg/dL", lambda v: dict(milligramsPerDeciliter=v)),
    BODY_TEMPERATURE=(lambda v: f"{v} C", lambda v: dict(celsius=v)),
    OXYGEN_SATURATION=(lambda v: f"{v}% SpO2", lambda v: dict(percentage=v)),
    RESPIRATORY_RATE=(lambda v: f"{v} rpm", lambda v: dict(ratePerMinute=v)),
    RESTING_HEART_RATE=(lambda v: f"{v} bpm (resting)", lambda v: dict(beatsPerMinute=v)),
    VO2_MAX=(lambda v: f"{v} mL/kg/min", lambda v: dict(vo2MillilitersPerMinuteKilogram=v, measurementMethod=1)),
    HYDRATION=(lambda v: f"{v} mL", lambda v: dict(milliliters=v)),
)
BATTERY = dict(chargePerMin=1.0, screenOnPerMin=0.25, idlePerMin=0.03, mediaPerMin=0.05)
SHEALTH = "com.sec.android.app.shealth"


def room_name(r):
    import re
    return re.sub(r"^room (\d)", r"room \1", ROOM_LABEL.get(r, r).lower())


ST_ALERTS = [
    dict(device="doorbell", attr="button", when=lambda v, p: v == "pushed", category="doorbell", severity="info",
         msg=lambda e, d: "Someone is at the front door"),
    dict(device="smoke_alarm", attr="smoke", when=lambda v, p: v == "detected", category="smoke", severity="critical",
         msg=lambda e, d: f"Smoke detected in {room_name(e['roomId'])}"),
    dict(device="water_leak_sensor", attr="water", when=lambda v, p: v == "wet", category="water_leak", severity="critical",
         msg=lambda e, d: f"Water leak detected in {room_name(e['roomId'])}"),
    dict(device=None, attr="cycleState", when=lambda v, p: v == "finished", category="cycle_finished", severity="info",
         msg=lambda e, d: f"{DEVICE_LABEL.get(e['device'], e['device'])} cycle finished"),
    dict(device="robot_vacuum", attr="operatingState", when=lambda v, p: v == "docked" and p == "seekingCharger",
         category="cleaning_finished", severity="info", msg=lambda e, d: "Cleaning finished, back on the charger"),
    dict(device="oven", attr="preheat", when=lambda v, p: v == "ready", category="preheat_done", severity="info",
         msg=lambda e, d: f"Oven preheated to {_num(d.get('temperatureSetpoint', 'temperatureSetpoint')) if d else '?'} C"),
    dict(device=None, attr="errorCode", when=lambda v, p: v is not None and v != "none" and v != "", category="device_error",
         severity="warning", msg=lambda e, d: f"{DEVICE_LABEL.get(e['device'], e['device'])} error: {e['value']}"),
]


def _num(v):
    return int(v) if isinstance(v, float) and v.is_integer() else v


def km_between(a, b):
    r = lambda x: x * math.pi / 180
    d_la, d_lo = r(b["lat"] - a["lat"]), r(b["lng"] - a["lng"])
    h = math.sin(d_la / 2) ** 2 + math.cos(r(a["lat"])) * math.cos(r(b["lat"])) * math.sin(d_lo / 2) ** 2
    return 6371 * 2 * math.asin(math.sqrt(h))


def heart_target(s, t):
    P, mx = HEART["person"], 220 - HEART["person"]["age"]
    if s["asleep"]:
        m = max(0, (t - s["sleepStart"]) / MIN_MS)
        cycle, pos = math.floor(m / HEART["sleep"]["cycleMin"]), m % HEART["sleep"]["cycleMin"]
        rem = min(10 + 5 * cycle, 30)
        sl = HEART["sleep"]
        f = sl["light"] if pos < sl["lightMin"] else sl["rem"] if pos >= sl["cycleMin"] - rem else sl["deep"] if cycle < 2 else sl["deepLate"]
        return P["restingBpm"] * f
    if s["activity"] in HEART["active"]:
        return mx * HEART["active"][s["activity"]]
    h = hours(t)
    tr = s["trip"]
    driving = bool(tr and 0 <= tr["i"] < len(tr["legs"]) and tr["legs"][tr["i"]].get("drives"))
    return P["restingBpm"] * (HEART["awake"]["DRIVING"] if driving else HEART["awake"].get(s["activity"]) or HEART["awake"]["STILL"]) * \
        (1 + HEART["dayRhythm"] * math.cos(2 * math.pi * (h - 15) / 24))


def hm(ms):
    f = fields(ms)
    return f"{f[3]:02d}:{f[4]:02d}"


def md(ms):
    f = fields(ms)
    return f"{f[1] + 1}/{f[2]}"


def stamp(ms):
    f = fields(ms)
    return f"{f[0]}{f[1] + 1:02d}{f[2]:02d}_{f[3]:02d}{f[4]:02d}{f[5]:02d}"


def month_start(ms):
    f = fields(ms)
    return local_ms(f[0], f[1], 1)


def title_case(a):
    return " ".join(w[0].upper() + w[1:] for w in a.lower().split("_"))


def bssid_for(ssid):
    h = 0
    for c in ssid:
        h = (h * 31 + ord(c)) & 0xFFFFFFFF
    return ":".join(f"{(h >> (i * 5)) & 255:02x}" for i in range(6))


# While asleep or driving only things that happen TO the phone can happen; everything the person does needs them awake.
# 1 = always needs the person awake, a function = depends on the arguments.
NEEDS_AWAKE = dict(travel=1, move_room=1, set_activity=1, bt_connect=1, bt_disconnect=1, power=1, open_app=1, close_app=1, install=1,
                   uninstall=1, media=1, calendar_add=1, calendar_update=1, calendar_delete=1, exercise_start=1, exercise_end=1,
                   measure=1, photo=1, screenshot=1, copy_clipboard=1, control_home=1,
                   screen=lambda on, *a: on is True, call=lambda state, *a: state == "OFFHOOK", sms=lambda d="INCOMING", *a: d == "OUTGOING")


class Phone:
    def __init__(self, sim):
        self.sim = sim
        self.events = []
        self.times = []
        self.s = dict(battery=80, charging=False, screenOn=False, place="home", room=None, wifi="Home-WiFi", bt=[], activity="STILL",
                      asleep=False, sleepStart=None, exercise=None, foreground=None, media=None, call="IDLE",
                      installed=list(APPS), calendar={}, nextEventId=1, notifSeq=100, captureSeq=100000, trip=None,
                      heart=None, heartNoise=0, cadenceNoise=0, bpm=None)
        self.apps = {k: dict(v) for k, v in APPS.items()}
        self.acc = None
        self.last_step_t = None
        self.timeline = []
        self.timeline_t = []
        self.on_emit = None  # hook: called with each event made by emit()

    def now(self):
        return self.sim.clock.now() // 1000 * 1000

    # ----- context -----
    def position(self, t):
        s, tr = self.s, self.s["trip"]
        if not tr:
            p = PLACES[s["place"]]
            return p["lat"], p["lng"]
        f = min(1, max(0, (t - tr["start"]) / ((tr["end"] - tr["start"]) or 1)))
        return (js_round((tr["a"][0] + (tr["b"][0] - tr["a"][0]) * f) * 1e5) / 1e5,
                js_round((tr["a"][1] + (tr["b"][1] - tr["a"][1]) * f) * 1e5) / 1e5)

    def mark(self, t):
        last = self.timeline[-1] if self.timeline else None
        lv = js_round(self.s["battery"])
        lat, lng = self.position(t)
        if not last or last["level"] != lv or last["charging"] != self.s["charging"] or last["place"] != self.s["place"] or last["lat"] != lat or last["lng"] != lng:
            self.timeline.append(dict(t=t, level=lv, charging=self.s["charging"], place=self.s["place"], lat=lat, lng=lng))
            self.timeline_t.append(t)

    def context_at(self, t):
        lat, lng = self.position(t)
        st = dict(level=js_round(self.s["battery"]), charging=self.s["charging"], place=self.s["place"], lat=lat, lng=lng)
        if self.timeline and t < self.timeline_t[-1]:
            i = bisect.bisect_right(self.timeline_t, t) - 1
            st = self.timeline[max(0, i)]
        p = PLACES.get(st["place"], {})
        lat = st["lat"] if st.get("lat") is not None else p.get("lat")
        lng = st["lng"] if st.get("lng") is not None else p.get("lng")
        moving = p.get("lat") is None
        return {"battery": {"level": st["level"], "charging": st["charging"]}, "weather": outdoor_at(t)["weather"],
                "location": {"latitude": lat, "longitude": lng, "accuracy": 25.0 if moving else 12.0}}

    def emit(self, type, source, title, text, payload, dedupe, t=None):
        t = self.now() if t is None else t
        e = {"type": type, "source": source, "title": title, "text": text, "timestamp": t, "collectedAt": t, "dedupeKey": dedupe,
             "payload": payload, "context": self.context_at(t)}
        self._insert([e])
        if self.on_emit:
            self.on_emit(e)
        return e

    def _insert(self, evs):
        for e in evs:
            t = e["timestamp"]
            if not self.times or self.times[-1] <= t:
                self.events.append(e)
                self.times.append(t)
            else:
                i = bisect.bisect_right(self.times, t)
                self.events.insert(i, e)
                self.times.insert(i, t)

    # ----- time passing (once per simulated minute) -----
    def step(self, t):
        s = self.s
        if self.last_step_t is None or t - self.last_step_t > MIN_MS:
            self.acc = None
        self.last_step_t = t
        if s["charging"]:
            s["battery"] = min(100, s["battery"] + BATTERY["chargePerMin"])
        else:
            s["battery"] = max(1, s["battery"] - (BATTERY["screenOnPerMin"] if s["screenOn"] else BATTERY["idlePerMin"])
                               - (BATTERY["mediaPerMin"] if s["media"] and s["media"]["state"] == "PLAYING" else 0))
        self.mark(t)
        mh = (t - MIN_MS) // 3600000 * 3600000
        if self.acc and self.acc["start"] != mh:
            self.flush_hour()
            self.acc = None
        if not self.acc:
            self.acc = dict(start=mh, steps=0, m=0, kcal=0, hr=0, n=0, apps={})
        b = BODY["ASLEEP" if s["asleep"] else s["activity"]]
        A = self.acc
        target = heart_target(s, t)
        base = s["heart"] if s["heart"] is not None else target
        s["heart"] = base + (target - base) * (HEART["follow"]["up"] if target > base else HEART["follow"]["down"])
        sd = HEART["noise"]["asleep"] if s["asleep"] else HEART["noise"]["active"] if s["activity"] in HEART["active"] else HEART["noise"]["awake"]
        g = self.sim.gauss
        s["heartNoise"] = 0.8 * (s["heartNoise"] or 0) + 0.6 * sd * g()
        bpm = max(35, js_round((s["heart"] + s["heartNoise"]) * 10) / 10)
        s["bpm"] = bpm
        k = 1
        if not s["asleep"] and s["activity"] in ("WALKING", "RUNNING"):
            s["cadenceNoise"] = 0.7 * (s["cadenceNoise"] or 0) + 0.7 * CADENCE_SD * g()
            k = min(1.25, max(0.75, 1 + s["cadenceNoise"]))
        A["steps"] += b["steps"] * k
        A["m"] += b["m"] * k
        A["kcal"] += b["kcal"] * k
        A["hr"] += bpm
        A["n"] += 1
        A["hrMin"] = min(A.get("hrMin", bpm), bpm)
        A["hrMax"] = max(A.get("hrMax", bpm), bpm)
        if s["screenOn"] and s["foreground"]:
            A["apps"][s["foreground"]] = A["apps"].get(s["foreground"], 0) + 1
        if s["media"] and s["media"]["state"] == "PLAYING":
            A["apps"]["com.spotify.music"] = A["apps"].get("com.spotify.music", 0) + 1
        if t % 3600000 == 0:
            self.flush_hour()
            self.acc = None
        while s["trip"] and t >= s["trip"]["legs"][s["trip"]["i"]]["end"]:
            self.next_leg(t)
        for ev in s["calendar"].values():
            if not ev["reminded"] and t - MIN_MS < ev["begin"] <= t:
                ev["reminded"] = True
                self.emit("CALENDAR", ev["calendar"], ev["title"], f"Event starting · {hm(ev['begin'])} - {hm(ev['end'])}",
                          dict(eventId=ev["eventId"], action="REMINDER", title=ev["title"], begin=ev["begin"], end=ev["end"], allDay=False,
                               location=ev["location"], calendar=ev["calendar"]), f"CALENDAR:REMINDER:{ev['eventId']}:{ev['begin']}", t)

    def flush_hour(self):
        a = self.acc
        if not a or not a["n"]:
            return
        s0 = a["start"]
        e0 = s0 + 3600000
        steps, m, kcal = js_round(a["steps"]), js_round(a["m"] * 10) / 10, js_round(a["kcal"] * 10) / 10
        bpm = js_round(a["hr"] / a["n"] * 10) / 10
        self.emit("HEALTH", "HOURLY", "HOURLY", f"{steps} steps · {m:.1f} m · {js_round(kcal)} kcal · avg {js_round(bpm)} bpm ({js_round(a['hrMin'])}-{js_round(a['hrMax'])})",
                  dict(steps=steps, meters=m, kilocalories=kcal, averageBpm=bpm, minBpm=js_round(a["hrMin"]), maxBpm=js_round(a["hrMax"]),
                       sampleCount=a["n"], startTime=s0, endTime=e0, origin=SHEALTH), f"HEALTH:HOURLY:{s0}", e0)
        for pkg, mins in a["apps"].items():
            app = self.apps.get(pkg) or dict(label=pkg, uid=10999, mbPerMin=1)
            rx = js_round(mins * app["mbPerMin"] * 1e6)
            tx = js_round(rx * 0.08)
            self.emit("DATA_USAGE", pkg, app["label"], f"down {rx / 1e6:.1f}MB up {tx / 1e6:.1f}MB",
                      dict(uid=app["uid"], packageName=pkg, rxBytes=rx, txBytes=tx, windowStart=s0, windowEnd=e0), f"DATAUSAGE:{app['uid']}:{s0}", e0)

    # ----- the person's actions -----
    def travel(self, dest, mode):
        s = self.s
        M, to, frm = TRAVEL_MODES.get(mode), PLACES.get(dest), PLACES.get(s["place"])
        if s["trip"]:
            self.sim.last_refusal = f"Already travelling to {PLACES[s['trip']['to']]['label']}"
            return 0
        if not M or not to or to["lat"] is None or dest == s["place"]:
            return 0
        t = self.now()
        km = km_between(frm, to) * ROAD_FACTOR
        legs = []
        at = [t]

        def leg(kind, mins, **extra):
            at[0] += max(1, js_round(mins)) * MIN_MS
            legs.append(dict(kind=kind, activity="WALKING" if kind == "walk" else "STILL" if kind == "wait" else M["activity"],
                             place=M["place"] if kind == "ride" else "on_foot", end=at[0], **extra))

        for k, m in M["before"]:
            leg(k, m)
        leg("ride", km / M["kmh"] * 60, bt=M.get("bt"), drives=bool(M.get("drives")))
        for k, m in M["after"]:
            leg(k, m)
        s["trip"] = dict(mode=mode, frm=s["place"], to=dest, start=t, end=at[0], km=js_round(km * 10) / 10, legs=legs, i=-1,
                         a=(frm["lat"], frm["lng"]), b=(to["lat"], to["lng"]))
        n = self.leave(t)
        return n + self.next_leg(t)

    def leave(self, t):
        s = self.s
        n, tw = 0, t
        if s["place"] == "home":
            if s["room"] != "entryway":
                s["room"] = "entryway"
                self.add_steps(ROOM_STEPS[0] + js_round(self.sim.rng.random() * (ROOM_STEPS[1] - ROOM_STEPS[0])))
                n += self.sim.set_presence("entryway", t)
            n += self.sim.use_front_door(t + 2000)
            s["room"] = None
            n += self.sim.set_presence(None, t + (12 + 3) * 1000)
            tw = t + (12 + 8) * 1000
        if s["wifi"]:
            self.net("DISCONNECTED", s["wifi"], tw)
            s["wifi"] = None
            n += 1
        n += self.sim.sync_router(False, tw)
        return n

    def next_leg(self, t):
        s, tr = self.s, self.s["trip"]
        prev = tr["legs"][tr["i"]] if tr["i"] >= 0 else None
        n = 0
        if prev and prev.get("bt"):
            s["bt"] = [x for x in s["bt"] if x != prev["bt"]]
            self.bt("BT_DISCONNECTED", prev["bt"], t)
            n += 1
        if prev and prev["kind"] == "ride" and s["asleep"]:
            n += self.do_wake(t)
        tr["i"] += 1
        if tr["i"] >= len(tr["legs"]):
            return n + self.arrive(t)
        L = tr["legs"][tr["i"]]
        s["place"] = L["place"]
        n += self.activity(L["activity"], t)
        if L.get("bt") and L["bt"] not in s["bt"]:
            s["bt"].append(L["bt"])
            self.bt("BT_CONNECTED", L["bt"], t)
            n += 1
        self.mark(t)
        return n

    def arrive(self, t):
        s = self.s
        dest = s["trip"]["to"]
        n = 0
        s["trip"] = None
        s["place"] = dest
        self.mark(t)
        n += self.activity("STILL", t)
        w = PLACES[dest]["wifi"]
        if w:
            s["wifi"] = w
            self.net("CONNECTED", w, t)
            n += 1
        n += self.sim.sync_router(False, t)
        if dest == "home":
            n += self.sim.use_front_door(t)
            s["room"] = "entryway"
            n += self.sim.set_presence("entryway", t + (5 + 1) * 1000)
        return n

    def teleport(self, place):
        """setup only: put the person somewhere at once, without a trip"""
        s = self.s
        if place not in PLACES or PLACES[place]["lat"] is None or place == s["place"] or s["trip"]:
            return 0
        t = self.now()
        n = self.leave(t)
        s["trip"] = dict(to=place, legs=[], i=0)
        return n + self.arrive(t)

    @property
    def driving(self):
        tr = self.s["trip"]
        return bool(tr and 0 <= tr["i"] < len(tr["legs"]) and tr["legs"][tr["i"]].get("drives"))

    def move_room(self, room):
        s = self.s
        if s["place"] != "home" or s["room"] == room:
            return 0
        if not self.sim.house.at(room, "occupancy_sensor"):
            return 0
        s["room"] = room
        self.add_steps(ROOM_STEPS[0] + js_round(self.sim.rng.random() * (ROOM_STEPS[1] - ROOM_STEPS[0])))
        return self.sim.set_presence(room)

    def add_steps(self, n):
        t = self.now()
        mh = (t - MIN_MS) // 3600000 * 3600000
        if not self.acc:
            self.acc = dict(start=mh, steps=0, m=0, kcal=0, hr=0, n=0, apps={})
        w = BODY["WALKING"]
        self.acc["steps"] += n
        self.acc["m"] += n * w["m"] / w["steps"]
        self.acc["kcal"] += n * w["kcal"] / w["steps"]

    def net(self, state, ssid, t=None):
        t = self.now() if t is None else t
        return self.emit("CONNECTIVITY", "network", "Network connected" if state == "CONNECTED" else "Network disconnected", f"WIFI · {ssid}",
                         dict(state=state, transport="WIFI", validated=state == "CONNECTED", unmetered=True, ssid=ssid, bssid=bssid_for(ssid)),
                         f"CONN:NET:{state}:WIFI:{ssid}:{t}", t)

    def set_activity(self, activity):
        if self.s["trip"]:
            self.sim.last_refusal = "The activity follows the trip while travelling"
            return 0
        if activity == "IN_VEHICLE" and self.s["place"] == "home":
            self.sim.last_refusal = "IN_VEHICLE is not possible at home: riding happens on a trip (Travel)"
            return 0
        return self.activity(activity, self.now())

    def activity(self, activity, t):
        s = self.s
        if activity not in ACTIVITIES or activity == s["activity"]:
            return 0
        boot = month_start(t)
        nanos = (t - boot) * 1000000

        def tr(a, enter):
            self.emit("ACTIVITY", a, title_case(a), "Start" if enter else "End",
                      dict(activity=a, transition="ENTER" if enter else "EXIT", activityType=ACTIVITIES[a], transitionType=0 if enter else 1,
                           elapsedRealtimeNanos=nanos), f"ACTIVITY:{a}:{'ENTER' if enter else 'EXIT'}:{nanos}", t)

        tr(s["activity"], False)
        s["activity"] = activity
        tr(activity, True)
        return 2

    def bt_connect(self, name):
        s = self.s
        if name not in BT_DEVICES or name in s["bt"]:
            return 0
        s["bt"].append(name)
        self.bt("BT_CONNECTED", name)
        return 1

    def bt_disconnect(self, name):
        s = self.s
        if name not in s["bt"]:
            return 0
        s["bt"] = [x for x in s["bt"] if x != name]
        self.bt("BT_DISCONNECTED", name)
        return 1

    def bt(self, state, name, t=None):
        t = self.now() if t is None else t
        return self.emit("CONNECTIVITY", "bluetooth", "Bluetooth connected" if state == "BT_CONNECTED" else "Bluetooth disconnected", name,
                         dict(state=state, deviceName=name, deviceAddress=BT_DEVICES[name]), f"CONN:BT:{state}:{BT_DEVICES[name]}:{t}", t)

    def screen(self, on):
        s = self.s
        if s["screenOn"] == on:
            return 0
        s["screenOn"] = on
        if not on:
            s["foreground"] = None
        st = "SCREEN_ON" if on else "SCREEN_OFF"
        t = self.now()
        self.emit("DEVICE_STATE", "system", "Screen on" if on else "Screen off", st, dict(state=st, action=f"android.intent.action.{st}"), f"DEVICE:{st}:{t}", t)
        return 1

    def power(self, connected):
        s = self.s
        if s["charging"] == connected:
            return 0
        s["charging"] = connected
        t = self.now()
        self.mark(t)
        st = "POWER_CONNECTED" if connected else "POWER_DISCONNECTED"
        self.emit("DEVICE_STATE", "system", "Charging started" if connected else "Charging stopped", st,
                  dict(state=st, action=f"android.intent.action.ACTION_{st}", batteryLevel=js_round(s["battery"])), f"DEVICE:{st}:{t}", t)
        return 1

    def open_app(self, pkg):
        s = self.s
        if pkg not in s["installed"] or s["foreground"] == pkg:
            return 0
        n = self.screen(True)
        t = self.now()
        if s["foreground"]:
            n += self.usage(s["foreground"], "BACKGROUND", t)
        s["foreground"] = pkg
        return n + self.usage(pkg, "FOREGROUND", t)

    def close_app(self):
        s = self.s
        if not s["foreground"]:
            return 0
        p = s["foreground"]
        s["foreground"] = None
        return self.usage(p, "BACKGROUND", self.now())

    def usage(self, pkg, action, t):
        label = (self.apps.get(pkg) or {}).get("label", pkg)
        self.emit("APP_USAGE", pkg, label, action, dict(packageName=pkg, action=action, eventType=1 if action == "FOREGROUND" else 2, timestamp=t,
                                                       className=f"{pkg}.MainActivity"), f"USAGE:{pkg}:{t}:{1 if action == 'FOREGROUND' else 2}", t)
        return 1

    def install(self, pkg, label=None):
        s = self.s
        if pkg in s["installed"]:
            return 0
        s["installed"].append(pkg)
        if pkg not in self.apps:
            self.apps[pkg] = dict(label=label or pkg, uid=10200 + len(s["installed"]), mbPerMin=1)
        return self.lifecycle("INSTALLED", pkg)

    def uninstall(self, pkg):
        s = self.s
        if pkg not in s["installed"]:
            return 0
        s["installed"] = [p for p in s["installed"] if p != pkg]
        if s["foreground"] == pkg:
            s["foreground"] = None
        return self.lifecycle("REMOVED", pkg)

    def lifecycle(self, action, pkg, t=None):
        t = self.now() if t is None else t
        label = (self.apps.get(pkg) or {}).get("label", pkg)
        self.emit("APP_LIFECYCLE", pkg, label, "Installed" if action == "INSTALLED" else "Removed", dict(action=action, packageName=pkg, label=label),
                  f"APP:{action}:{pkg}:{t}", t)
        return 1

    def notify(self, pkg, title, text, category="msg"):
        t = self.now()
        self.s["notifSeq"] += 1
        key = f"0|{pkg}|{self.s['notifSeq']}|null|10001"
        self.emit("NOTIFICATION", pkg, title, text, dict(action="POSTED", packageName=pkg, key=key, postTime=t, isOngoing=False, isClearable=True,
                                                          category=category, channelId="chat" if category == "msg" else "default",
                                                          subText="Chat" if category == "msg" else "", groupKey=pkg), f"NOTIF:{key}:{t}:POSTED", t)
        return 1

    def call(self, state):
        t = self.now()
        text = dict(RINGING="Incoming, ringing", OFFHOOK="In call", IDLE="Call ended")[state]
        self.s["call"] = state
        self.emit("TELEPHONY", "call", "Call", text, dict(kind="CALL", state=state), f"TEL:CALL:{state}:{t // 1000}", t)
        return 1

    def sms(self, direction="INCOMING"):
        t = self.now()
        inc = direction == "INCOMING"
        self.emit("TELEPHONY", "sms", "SMS received" if inc else "SMS sent", "SMS arrived" if inc else "SMS sent", dict(kind="SMS", direction=direction),
                  f"TEL:SMS:{direction}:{t}", t)
        return 1

    def media(self, state, title="Song Title", artist="Artist Name", album="Album Name"):
        s = self.s
        m = s["media"] or dict(title=title, artist=artist, album=album)
        if state == "PLAYING":
            m.update(title=title, artist=artist, album=album)
        if s["media"] and s["media"]["state"] == state and state != "PLAYING":
            return 0
        m["state"] = state
        s["media"] = None if state == "STOPPED" else m
        t = self.now()
        self.emit("MEDIA", "com.spotify.music", m["title"], f"{state} • {m['artist']}",
                  dict(state=state, packageName="com.spotify.music", title=m["title"], artist=m["artist"], album=m["album"]),
                  f"MEDIA:com.spotify.music:{state}:{m['title']}:{t}", t)
        return 1

    def calendar_add(self, title, begin, end, location="", calendar="Personal"):
        s = self.s
        eid = s["nextEventId"]
        s["nextEventId"] += 1
        ev = dict(eventId=eid, title=title, begin=begin, end=end, location=location, calendar=calendar, reminded=begin <= self.now())
        s["calendar"][eid] = ev
        return self.cal("ADD", ev)

    def calendar_update(self, eid, changes):
        ev = self.s["calendar"].get(eid)
        if not ev:
            return 0
        previous = dict(begin=ev["begin"], end=ev["end"])
        ev.update(changes)
        if changes.get("begin") is not None:
            ev["reminded"] = ev["begin"] <= self.now()
        return self.cal("UPDATE", ev, dict(previous=previous))

    def calendar_delete(self, eid):
        ev = self.s["calendar"].pop(eid, None)
        if not ev:
            return 0
        return self.cal("DELETE", ev)

    def cal(self, action, ev, extra=None, t=None):
        t = self.now() if t is None else t
        verb = dict(ADD="Event added", UPDATE="Event changed", DELETE="Event deleted")[action]
        p = dict(eventId=ev["eventId"], action=action, title=ev["title"], begin=ev["begin"], end=ev["end"], allDay=False, location=ev["location"],
                 calendar=ev["calendar"])
        p.update(extra or {})
        self.emit("CALENDAR", ev["calendar"], ev["title"], f"{verb} · {md(ev['begin'])} {hm(ev['begin'])} - {hm(ev['end'])}", p,
                  f"CALENDAR:{action}:{ev['eventId']}:{ev['begin']}:{t}", t)
        return 1

    def sleep(self):
        s = self.s
        if s["asleep"]:
            return 0
        leg = s["trip"]["legs"][s["trip"]["i"]] if s["trip"] and 0 <= s["trip"]["i"] < len(s["trip"]["legs"]) else None
        why = ("exercising" if s["exercise"] else "driving" if self.driving else "walking or waiting on the way" if leg and leg["kind"] != "ride"
               else f"the activity is {s['activity']}" if s["activity"] in ("WALKING", "RUNNING", "ON_BICYCLE")
               else "on a call" if s["call"] == "OFFHOOK" else None)
        if why:
            self.sim.last_refusal = f"The person cannot fall asleep while {why}"
            return 0
        n = self.screen(False)
        s["asleep"] = True
        s["sleepStart"] = self.now()
        return n

    def wake(self):
        return self.do_wake(self.now())

    def do_wake(self, t):
        s = self.s
        if not s["asleep"]:
            return 0
        dur = js_round((t - s["sleepStart"]) / MIN_MS)
        s["asleep"] = False
        self.emit("HEALTH", "SLEEP", "SLEEP", f"{dur} min", dict(durationMinutes=dur, stageCount=max(1, js_round(dur / 52)), startTime=s["sleepStart"],
                                                                  endTime=t, origin=SHEALTH), f"HEALTH:SLEEP:{s['sleepStart']}", t)
        s["sleepStart"] = None
        return 1

    def exercise_start(self, kind):
        s = self.s
        x = EXERCISES.get(kind)
        if not x or s["exercise"]:
            return 0
        if s["trip"]:
            self.sim.last_refusal = "Not while travelling"
            return 0
        s["exercise"] = dict(kind=kind, start=self.now())
        return self.activity(x["activity"], self.now())

    def exercise_end(self):
        s = self.s
        if not s["exercise"]:
            return 0
        t = self.now()
        x = EXERCISES[s["exercise"]["kind"]]
        dur = js_round((t - s["exercise"]["start"]) / MIN_MS)
        self.emit("HEALTH", "EXERCISE", "EXERCISE", f"{s['exercise']['kind']} • {dur} min",
                  dict(exerciseType=x["code"], title=s["exercise"]["kind"], durationMinutes=dur, startTime=s["exercise"]["start"], endTime=t, origin=SHEALTH),
                  f"HEALTH:EXERCISE:{s['exercise']['start']}", t)
        s["exercise"] = None
        return 1 + self.activity("STILL", t)

    def measure(self, source, value):
        m = MEASURES.get(source)
        if not m:
            return 0
        t = self.now()
        pl = dict(m[1](value))
        if source == "HYDRATION":
            pl.update(origin=SHEALTH, startTime=t, endTime=t)
        else:
            pl.update(time=t, origin=SHEALTH)
        self.emit("HEALTH", source, source, m[0](value), pl, f"HEALTH:{source}:{t}", t)
        return 1

    def photo(self):
        t = self.now()
        self.s["captureSeq"] += 1
        cid = self.s["captureSeq"]
        name = f"IMG_{stamp(t)}.jpg"
        self.emit("MEDIA_CAPTURE", "Camera", "Photo taken", f"{name} (4000x3000)",
                  dict(kind="photo", fileName=name, bucket="Camera", relativePath="DCIM/Camera/", mimeType="image/jpeg", width=4000, height=3000,
                       sizeBytes=2400000 + (cid % 97) * 1000, camera="SM-S928N", contentAnalyzed=False), f"MEDIA_CAPTURE:{cid}", t)
        return 1

    def screenshot(self, ocr_text=""):
        t = self.now()
        self.s["captureSeq"] += 1
        cid = self.s["captureSeq"]
        name = f"Screenshot_{stamp(t)}.png"
        p = PLACES[self.s["place"]]
        self.emit("MEDIA_CAPTURE", "Screenshots", "Screenshot captured", f"{ocr_text or name} · Text",
                  dict(kind="screenshot", fileName=name, bucket="Screenshots", relativePath="Pictures/Screenshots/", mimeType="image/png", width=1080,
                       height=2340, sizeBytes=800000 + (cid % 89) * 1000, contentAnalyzed=bool(ocr_text), ocrText=ocr_text,
                       labels=[dict(label="Text", confidence=0.87)] if ocr_text else [], location=dict(lat=p["lat"], lng=p["lng"])), f"MEDIA_CAPTURE:{cid}", t)
        return 1

    def copy_clipboard(self, label="Memo"):
        t = self.now()
        self.emit("CLIPBOARD", "clipboard", "Clipboard copy", "text/plain", dict(mimeTypes=["text/plain"], label=label, copiedAt=t), f"CLIPBOARD:{t}", t)
        return 1

    def control_home(self, device_id, cap, cmd, args=()):
        """a home device from the phone app: the home line says channel "mobile_app" """
        return self.sim.run(device_id, cap, cmd, args, "mobile_app")

    # ----- SMARTTHINGS copies of saved home lines -----
    def copy_home(self, entries):
        if not entries:
            return
        copies = []
        for e in entries:
            copies.append(self.to_smartthings(e))
            for a in ST_ALERTS:
                if (not a["device"] or a["device"] == e["device"]) and a["attr"] == e["attribute"] and a["when"](e["value"], e["previousValue"]):
                    copies.append(self.to_alert(e, a))
        copies.sort(key=lambda c: c["timestamp"])
        self._insert(copies)
        if self.on_copy:
            self.on_copy(entries, copies)

    on_copy = None

    def to_smartthings(self, e):
        t = e["_t"] // 1000 * 1000
        d = self.sim.house.device(e["deviceId"])
        spec = d.attr_spec(e["capability"], e["attribute"]) if d else None
        unit = spec.get("unit") if spec else None
        src = e["source"]
        if src == "command":
            actor = dict(kind="user", channel=e["channel"] or "physical", command=e["command"], args=e["args"])
        elif src == "manual":
            actor = dict(kind="user", channel="physical", command=None, args=[])
        elif src == "event":
            actor = dict(kind="event", channel="physical", command=None, args=[])
        elif src == "sensor":
            actor = dict(kind="sensor", channel=None, command=None, args=[], reason=e["reason"])
        else:
            actor = dict(kind="device", channel=None, command=None, args=[])
            if e["reason"]:
                actor["reason"] = e["reason"]
        main = {}

        def put(cap, attr, value, u):
            main.setdefault(cap, {})[attr] = dict(value=value, unit=u) if u else dict(value=value)

        if d and src != "sensor":
            for c in d.capabilities:
                for a in c["attributes"]:
                    put(c["capability"], a["name"], d.get(c["capability"], a["name"]), a.get("unit"))
        else:
            put(e["capability"], e["attribute"], e["value"], unit)
        dl = DEVICE_LABEL.get(e["device"], e["device"])
        label = f"{ROOM_LABEL.get(e['roomId'], e['roomId'])} {dl.lower()}"
        who = (f"user, {'mobile app' if actor['channel'] == 'mobile_app' else 'at device'}" if actor["kind"] == "user"
               else "sensor report" if actor["kind"] == "sensor" else actor["kind"])
        prev = "-" if e["previousValue"] is None else _txt(e["previousValue"])
        change = dict(capability=e["capability"], attribute=e["attribute"], value=e["value"], previousValue=e["previousValue"])
        if unit:
            change["unit"] = unit
        return {"type": "SMARTTHINGS", "source": e["deviceId"], "title": label,
                "text": f"{dl} · {e['attribute']}: {prev} -> {_txt(e['value'])}{' ' + unit if unit else ''} ({who})",
                "timestamp": t, "collectedAt": t, "dedupeKey": f"ST:{e['deviceId']}:{e['capability']}.{e['attribute']}:{_txt(e['value'])}:{t}",
                "payload": {"kind": "state", "deviceId": e["deviceId"], "name": e["device"], "label": label, "deviceTypeName": dl, "roomId": e["roomId"],
                            "capabilities": [c["capability"] for c in d.capabilities] if d else [e["capability"]], "change": change, "actor": actor,
                            "status": {"components": {"main": main}}},
                "context": self.context_at(t)}

    def to_alert(self, e, a):
        t = e["_t"] // 1000 * 1000
        d = self.sim.house.device(e["deviceId"])
        dl = DEVICE_LABEL.get(e["device"], e["device"])
        label = f"{ROOM_LABEL.get(e['roomId'], e['roomId'])} {dl.lower()}"
        message = a["msg"](e, d)
        return {"type": "SMARTTHINGS", "source": e["deviceId"], "title": label, "text": f"Notification · {message}",
                "timestamp": t, "collectedAt": t, "dedupeKey": f"ST:NOTIFY:{e['deviceId']}:{a['category']}:{t}",
                "payload": {"kind": "notification", "deviceId": e["deviceId"], "name": e["device"], "label": label, "deviceTypeName": dl,
                            "roomId": e["roomId"], "notification": dict(category=a["category"], severity=a["severity"], message=message),
                            "trigger": dict(capability=e["capability"], attribute=e["attribute"], value=e["value"], previousValue=e["previousValue"])},
                "context": self.context_at(t)}

    def prune(self, keep_from):
        i = 0
        while i + 1 < len(self.timeline) and self.timeline[i + 1]["t"] <= keep_from:
            i += 1
        if i:
            del self.timeline[:i]
            del self.timeline_t[:i]


def _txt(v):
    """a value as JavaScript prints it in a template string"""
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def _needs_awake(name, rule):
    f = getattr(Phone, name)

    def wrapped(self, *args, **kw):
        self.sim.last_refusal = None
        if rule == 1 or (callable(rule) and rule(*args)):
            if self.s["asleep"]:
                self.sim.last_refusal = f"The person is asleep: {name} needs them awake (Wake up first)"
                return 0
            if self.driving and name != "travel":
                self.sim.last_refusal = "The person is driving: no phone use until the drive ends"
                return 0
        return f(self, *args, **kw)

    wrapped.__name__ = name
    setattr(Phone, name, wrapped)


for _n, _r in NEEDS_AWAKE.items():
    _needs_awake(_n, _r)
for _n in ("notify", "sleep", "wake"):
    _f = getattr(Phone, _n)

    def _clear(f):
        def w(self, *a, **k):
            self.sim.last_refusal = None
            return f(self, *a, **k)
        w.__name__ = f.__name__
        return w

    setattr(Phone, _n, _clear(_f))
