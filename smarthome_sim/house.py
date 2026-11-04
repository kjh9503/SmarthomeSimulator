"""Devices, the house layout and each room's true indoor conditions (temperature, humidity, PM2.5, CO2, light, noise).
Ported from smarthome-sim.html; constants and their sources are the same."""
import json
import math
import os

from .weather import outdoor_at, db_sum, WEATHER, WIND, FACADE_DB

DATA = os.path.join(os.path.dirname(__file__), "data")
SPEC = [json.loads(l) for l in open(os.path.join(DATA, "device_spec.jsonl"), encoding="utf-8") if l.strip()]
ROOM_PROFILES = json.load(open(os.path.join(DATA, "room_profiles.json"), encoding="utf-8"))
DEFAULT_VARIANT = "3room-A"

ALL_ROOMS = ["room1", "room2", "room3", "room4", "living_room", "kitchen", "dining_room", "bathroom", "master_bathroom", "laundry", "closet", "hallway",
             "entryway", "balcony"]
HOUSE_EXCLUDE = {"2room": ["room3", "room4", "hallway", "master_bathroom"], "3room": ["room4"], "4room": []}
# devices a house type does not have although their room exists: system air conditioning in the living room and every
# room; a separate kitchen unit only in 4room (2room / 3room kitchens are open to the living room and use its unit)
DEVICE_EXCLUDE = {"2room": {("heating_cooling_unit", "kitchen")}, "3room": {("heating_cooling_unit", "kitchen")}, "4room": set()}
ROOM_LABEL = dict(room1="Room 1", room2="Room 2", room3="Room 3", room4="Room 4", living_room="Living room", kitchen="Kitchen",
                  dining_room="Dining room", bathroom="Bathroom", master_bathroom="Master bathroom", laundry="Laundry", closet="Closet", hallway="Hallway", entryway="Entryway", balcony="Balcony")
DEVICE_LABEL = dict(temperature_sensor="Temperature", humidity_sensor="Humidity", light_sensor="Light level", occupancy_sensor="Occupancy",
                    air_quality_sensor="Air quality", noise_sensor="Noise", door_contact="Door contact", window_contact="Window contact",
                    water_leak_sensor="Water leak", smoke_alarm="Smoke alarm", doorbell="Doorbell", wifi_router="Wi-Fi router", light="Light",
                    lamp="Lamp", heating_cooling_unit="Heating/cooling", humidifier="Humidifier", air_purifier="Air purifier", curtain="Curtain",
                    tv="TV", robot_vacuum="Robot vacuum", dishwasher="Dishwasher", oven="Oven", stove="Stove", washer="Washer",
                    dryer="Dryer", lock="Lock")
# initial values (simulator's choice)
DEFAULTS = {
    "switch.switch": "off", "presenceSensor.presence": "not present", "contactSensor.contact": "closed", "waterSensor.water": "dry",
    "smokeDetector.smoke": "clear", "button.button": None, "lock.lock": "locked", "windowShade.windowShade": "closed",
    "mediaPlayback.playbackStatus": "stopped", "robotCleanerOperatingState.operatingState": "docked",
    "thermostatMode.thermostatMode": "off", "connection.connection": "disconnected",
    "washerOperatingState.machineState": "stop", "washerOperatingState.washerJobState": "none",
    "dryerOperatingState.machineState": "stop", "dryerOperatingState.dryerJobState": "none",
    "dishwasherOperatingState.machineState": "stop", "dishwasherOperatingState.dishwasherJobState": "none",
    "ovenOperatingState.machineState": "ready", "ovenOperatingState.ovenJobState": "ready",
    "temperatureMeasurement.temperature": 22, "relativeHumidityMeasurement.humidity": 45, "illuminanceMeasurement.illuminance": 300,
    "fineDustSensor.fineDustLevel": 15, "carbonDioxideMeasurement.carbonDioxide": 600, "soundPressureLevel.soundPressureLevel": 35,
    "connectedDevices.connectedDevices": 8, "switchLevel.level": 100, "colorTemperature.colorTemperature": 4000,
    "thermostatCoolingSetpoint.coolingSetpoint": 24, "thermostatHeatingSetpoint.heatingSetpoint": 22, "humiditySetpoint.humiditySetpoint": 50,
    "fanSpeedPercent.percent": 0, "audioVolume.volume": 30, "battery.battery": 100,
    "temperatureSetpoint.temperatureSetpoint": 180,
}
OUTDOOR_DEFAULTS = {"temperatureMeasurement.temperature": 15, "relativeHumidityMeasurement.humidity": 60, "fineDustSensor.fineDustLevel": 30,
                    "carbonDioxideMeasurement.carbonDioxide": 420}
CMD_VALUE = dict(on="on", off="off", lock="locked", unlock="unlocked", open="open", close="closed", play="playing", stop="stopped",
                 start="running", goHome="seekingCharger")
PAUSE_VALUE = dict(windowShade="partially_open", playbackStatus="paused", operatingState="paused")
CYCLE_MINUTES = dict(washer=dict(normal=60, quick=30, bedding=90), dishwasher=dict(normal=120))
# SmartThings standard operating-state capabilities (live): machineState stop / run / pause, job state, completionTime
OP_STATE = dict(washer=("washerOperatingState", "washerJobState", "wash", "finish"),
                dryer=("dryerOperatingState", "dryerJobState", "drying", "finished"),
                dishwasher=("dishwasherOperatingState", "dishwasherJobState", "wash", "finish"))

PHYS = dict(
    stepMs=60000, heartbeatMin=30, maxCatchUpDays=7,
    closedByWalls=[0.0008, 0.0016, 0.0024],
    indoorGainC=2, indoorSwing=0.25, indoorMinC=15, solarGainC=3,
    massToAir=0.05, airToMass=0.002, hvacMaxRate=0.5,
    moistureOffset=3, moisture=dict(person=0.0025, dryer=0.035, washer=0.007, humidifierMax=0.04),
    report=dict(temperature=dict(th=0.5, dec=1), humidity=dict(th=2, dec=0), illuminance=dict(th=30, rel=0.1, dec=0),
                pm25=dict(th=3, dec=0), co2=dict(th=50, dec=0), noise=dict(th=3, dec=0)),
    jitter=dict(temperature=0.05, humidity=0.3, illuminance=0.02, pm25=0.5, co2=4, noise=0.8),
    windowLight=dict(large=.03, medium=.02, small=.012, none=.002),
    windowOpen=dict(large=.04, medium=.03, small=.02, none=.01),
    windowHeat=dict(large=1, medium=.6, small=.3, none=0),
    lightLux=300, lampLux=150, ceilingM=2.3,
    # air purifier: CADR ~8.4 m3/min; the fan percent is the share of full CADR (0 = off); tuned to the 30-74% PM2.5 cut
    # measured in 10 homes (Public Health Research & Practice, 2024)
    purifier=dict(cadrM3min=8.4, mixingEff=0.4),
    pmInfiltration=0.01,
    # air between rooms (2026-11-04). Open door / open plan: buoyancy flow through an opening, one direction
    # Q = Cd/3 * W * H * sqrt(g * H * dT / T) (Brown & Solvason 1962), Cd = 0.0835 * (dT/T)^-0.313 measured through a
    # doorway (Riffat 1989, ASHRAE Trans. 95(2); a doorway between floors), dT held within the measured 0.5-13 K (below 0.5 K
    # the exchange does not fall to zero: Lidwell 1977). Closed door: 0.1 m3/h (NIST 2017, closed interior door with undercut,
    # yearly mean 0.12 m3/h). Door 0.9 x 2.1 m; open-plan widths in CONNECTIONS are our own assumption, height = ceiling.
    door=dict(widthM=0.9, heightM=2.1, closedM3h=0.1, dTmin=0.5, dTmax=13),
    curtain=dict(closed=.15, partially_open=.6, opening=.6, closing=.6, open=1, unknown=.6),
)
SENSOR_ATTRS = dict(
    temperature_sensor=[("temperatureMeasurement", "temperature", "temperature")],
    humidity_sensor=[("relativeHumidityMeasurement", "humidity", "humidity")],
    light_sensor=[("illuminanceMeasurement", "illuminance", "illuminance")],
    air_quality_sensor=[("fineDustSensor", "fineDustLevel", "pm25"), ("carbonDioxideMeasurement", "carbonDioxide", "co2")],
    noise_sensor=[("soundPressureLevel", "soundPressureLevel", "noise")],
)
AZIMUTH = dict(N=0, NE=45, E=90, SE=135, S=180, SW=225, W=270, NW=315)
NO_PROFILE = dict(areaM2=10, window=None, windowSize="none", exteriorWalls=0)
OPEN_PLAN = ["living_room", "kitchen", "dining_room", "hallway", "entryway"]
# how the rooms join (our own layout for a flat-type Korean apartment, 2026-11-04):
# ("open", a, b, width m): open plan, no door; widths are our own assumption (living-kitchen / living-dining 3 m,
#   kitchen-dining 2 m, living-hallway / hallway-entryway / living-entryway 1.2 m)
# ("room", a, room): the room's door, closed while its heating / cooling unit runs (see House.door_closed)
# ("closed", a, b): a door kept closed (bathrooms, closet, laundry)
_COMMON = [("open", "living_room", "kitchen", 3.0), ("open", "living_room", "dining_room", 3.0), ("open", "kitchen", "dining_room", 2.0),
           ("closed", "kitchen", "laundry")]
CONNECTIONS = {
    "2room": _COMMON + [("open", "living_room", "entryway", 1.2), ("room", "living_room", "room1"), ("room", "living_room", "room2"),
                        ("closed", "living_room", "bathroom"), ("closed", "room1", "closet")],
    "3room": _COMMON + [("open", "living_room", "hallway", 1.2), ("open", "hallway", "entryway", 1.2), ("room", "living_room", "room1"),
                        ("room", "hallway", "room2"), ("room", "hallway", "room3"), ("closed", "hallway", "bathroom"),
                        ("closed", "room1", "master_bathroom"), ("closed", "room1", "closet")],
}
CONNECTIONS["4room"] = CONNECTIONS["3room"] + [("room", "hallway", "room4")]


# Air conditioning units (Korean home system air conditioning, Samsung WindFree 1Way, 2026-11-04):
# rated cooling kW by place: rooms and the 4room kitchen 6-pyeong 2.3 kW (AJ023MB1PBC1, airflow 6.0 m3/min high);
# living room 2room 8-pyeong 3.2 kW (AJ032MB1PBC1), 3room / 4room 18-pyeong 7.2 kW (AJ072MB1PBC1).
# Airflow of the 3.2 / 7.2 kW units not found: taken in proportion to 2.3 kW (2.61 m3/min per kW) [our assumption].
# Inverter range min / max = 0.79 / 3.70 of 2.30 kW (single 1Way AC023CN1PBH1), used for every size [our assumption].
AC_KW = {"2room": dict(living_room=3.2), "3room": dict(living_room=7.2), "4room": dict(living_room=7.2)}
AC_ROOM_KW, AC_M3MIN_PER_KW, AC_MIN, AC_MAX = 2.3, 6.0 / 2.3, 0.79 / 2.30, 3.70 / 2.30
P_HPA = 1013.25


def w_from_e(e):
    """humidity ratio kg/kg from vapour pressure hPa"""
    return 0.622 * e / (P_HPA - e)


def e_from_w(w):
    return w * P_HPA / (0.622 + w)


def enthalpy(t, w):
    """moist air kJ per kg dry air"""
    return 1.006 * t + w * (2501 + 1.86 * t)


def coil_outlet(t_in, e_in, kw, m3min):
    """air through a cooling coil that removes kw: (t_out, e_out). Sensible cooling until the air reaches its dew point;
    beyond that the outlet is saturated air with the remaining enthalpy, the excess vapour leaving as condensate
    (ideal coil, no bypass)."""
    rho = 1.2
    m = rho * m3min / 60  # kg/s
    w_in = w_from_e(e_in)
    h_out = enthalpy(t_in, w_in) - kw / m
    t_s = (h_out - w_in * 2501) / (1.006 + 1.86 * w_in)  # outlet with the same moisture
    if e_in <= sat_vapor(t_s):
        return t_s, e_in
    lo, hi = -20.0, t_in
    for _ in range(40):  # saturated outlet: h_sat(t) = h_out
        mid = (lo + hi) / 2
        if enthalpy(mid, w_from_e(sat_vapor(mid))) > h_out:
            hi = mid
        else:
            lo = mid
    t = (lo + hi) / 2
    return t, sat_vapor(t)


def opening_flow(width, height, dt, t_mean):
    """m3 per minute one way through an open door or opening (Brown & Solvason 1962 with Riffat's 1989 Cd)"""
    D = PHYS["door"]
    dt = min(D["dTmax"], max(D["dTmin"], abs(dt)))
    tk = t_mean + 273.15
    cd = 0.0835 * (dt / tk) ** -0.313
    return cd / 3 * width * height * math.sqrt(9.81 * height * dt / tk) * 60


def round_to(v, dec):
    p = 10 ** dec
    return math.floor(v * p + 0.5) / p


def window_sun(profile, out):
    if not profile.get("window") or out["sunAz"] is None:
        return 1
    return 0.35 + 0.65 * max(0, math.cos((out["sunAz"] - AZIMUTH[profile["window"]]) * math.pi / 180))


def free_indoor_temp(out, profile=NO_PROFILE):
    solar = PHYS["solarGainC"] * PHYS["windowHeat"][profile["windowSize"]] * window_sun(profile, out) * out["daylight"] / 20000
    return max(PHYS["indoorMinC"], out["meanTemperature"] + PHYS["indoorGainC"] + PHYS["indoorSwing"] * (out["temperature"] - out["meanTemperature"])) + solar


def sat_vapor(t):
    return 6.112 * math.exp(17.62 * t / (243.12 + t))


def vapor_from_rh(rh, t):
    return rh / 100 * sat_vapor(t)


def rh_from_vapor(e, t):
    return min(100, max(1, 100 * e / sat_vapor(t)))


class Device:
    __slots__ = ("id", "type", "roomId", "capabilities", "state", "aux", "_caps")

    def __init__(self, id, type, room_id, capabilities):
        self.id, self.type, self.roomId, self.capabilities = id, type, room_id, capabilities
        self.state, self.aux = {}, {}
        self._caps = {c["capability"]: c for c in capabilities}
        for c in capabilities:
            for a in c["attributes"]:
                k = f'{c["capability"]}.{a["name"]}'
                v = OUTDOOR_DEFAULTS[k] if room_id == "balcony" and k in OUTDOOR_DEFAULTS else DEFAULTS.get(k, "__undef__")
                if v == "__undef__":
                    v = a["values"][0] if a["type"] == "enum" else None
                if type == "oven" and k == "temperatureMeasurement.temperature":
                    v = 22
                self.state[k] = v

    def cap(self, name):
        return self._caps.get(name)

    def attr_spec(self, cap, attr):
        c = self.cap(cap)
        return next((a for a in c["attributes"] if a["name"] == attr), None) if c else None

    def get(self, cap, attr):
        return self.state.get(f"{cap}.{attr}")

    def set(self, cap, attr, value):
        k = f"{cap}.{attr}"
        prev = self.state.get(k)
        self.state[k] = value
        return dict(capability=cap, attribute=attr, previousValue=prev, value=value, changed=not _same(prev, value))

    def effects(self, cap_name, cmd, args):
        c = self.cap(cap_name)
        attr = c["attributes"][0]["name"]
        if self.type in OP_STATE and cmd == "setMachineState":
            cap, job, running, _ = OP_STATE[self.type]
            st = args[0] if args else None
            was = self.get(cap, "machineState")
            if st == "run":  # start, or resume after a pause (the job carries on)
                return [(cap, "machineState", "run"), (cap, job, running)]
            if st == "pause":
                return [(cap, "machineState", "pause")] if was == "run" else []
            if st == "stop":
                return [(cap, "machineState", "stop"), (cap, job, "none")]
            raise ValueError(f"Unknown machine state: {st}")
        if cmd.startswith("set"):
            return [(cap_name, attr, args[0] if args else None)]
        if cmd == "pause":
            return [(cap_name, attr, PAUSE_VALUE.get(attr))]
        if cmd in CMD_VALUE:
            return [(cap_name, attr, CMD_VALUE[cmd])]
        raise ValueError(f"Unknown command: {cmd}")


def _same(a, b):
    """JavaScript ===: 1 and 1.0 are the same number; True is not 1"""
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return a == b and (type(a) is type(b) or (isinstance(a, (int, float)) and isinstance(b, (int, float))))


class House:
    def __init__(self, variant, spec, ms):
        self.variant = variant
        self.profile = ROOM_PROFILES[variant]
        self.type = self.profile["houseType"]
        self.room_ids = [r for r in ALL_ROOMS if r not in HOUSE_EXCLUDE[self.type]]
        by_room = {r: [] for r in self.room_ids}
        for d in spec:
            for i, r in enumerate(d["rooms"]):
                if r in by_room and (d["device"], r) not in DEVICE_EXCLUDE[self.type]:
                    by_room[r].append(Device(d["deviceIds"][i], d["device"], r, d["capabilities"]))
        self.devices = {}
        for r in self.room_ids:
            for d in by_room[r]:
                self.devices[d.id] = d
        self.by_room = {r: {d.type: d for d in by_room[r]} for r in self.room_ids}
        # door rule (agreed 2026-11-04): a room's door is closed while its heating / cooling unit runs, when the person
        # switched it on at home (it stays closed if they leave); switched on from outside by the app it stays open.
        # Switched off: open. Kitchen and dining room have no door (open plan).
        self.door_closed = {r: False for r in self.room_ids}
        self.env = Environment(self, ms)
        self.sync_sensors()

    def sync_sensors(self):
        for d in self.devices.values():
            for cap, attr, ek in SENSOR_ATTRS.get(d.type, ()):
                v = self.env.rooms[d.roomId][ek]
                d.set(cap, attr, round_to(max(0, min(100, v) if ek == "humidity" else v), PHYS["report"][ek]["dec"]))

    def device(self, id):
        return self.devices.get(id)

    def room_profile(self, r):
        return self.profile["rooms"].get(r, NO_PROFILE)

    def at(self, r, type):
        return self.by_room.get(r, {}).get(type)


class Environment:
    def __init__(self, house, ms):
        self.house = house
        out = outdoor_at(ms)
        self.rooms = {}
        for r in house.room_ids:
            self.rooms[r] = (dict(temperature=out["temperature"], humidity=out["humidity"], pm25=out["pm25"], co2=out["co2"],
                                  illuminance=out["daylight"], noise=out["noise"]) if r == "balcony"
                             else dict(temperature=22, mass=22, humidity=45, pm25=15, co2=600, illuminance=0, noise=30))
        self.settle(ms)

    def settle(self, ms):
        out = outdoor_at(ms)
        for r, e in self.rooms.items():
            if r == "balcony":
                continue
            t = free_indoor_temp(out, self.house.room_profile(r))
            vapor = min(sat_vapor(t), vapor_from_rh(out["humidity"], out["temperature"]) + PHYS["moistureOffset"])
            e.update(temperature=t, mass=t, vapor=vapor, humidity=rh_from_vapor(vapor, t), pm25=out["pm25"], co2=out["co2"])

    def exchange(self, dt):
        """air between joined rooms: each pair swaps Q m3 a minute each way, carrying heat, moisture, PM2.5 and CO2.
        Solved exactly per pair (the difference decays as exp(-Q dt (1/Va + 1/Vb))), so small rooms stay stable."""
        H = self.house
        for c in CONNECTIONS[H.type]:
            kind, a, b = c[0], c[1], c[2]
            if a not in self.rooms or b not in self.rooms:
                continue
            ea, eb = self.rooms[a], self.rooms[b]
            if kind == "open":
                q = opening_flow(c[3], PHYS["ceilingM"], ea["temperature"] - eb["temperature"], (ea["temperature"] + eb["temperature"]) / 2)
            elif kind == "room" and not H.door_closed.get(b):
                D = PHYS["door"]
                q = opening_flow(D["widthM"], D["heightM"], ea["temperature"] - eb["temperature"], (ea["temperature"] + eb["temperature"]) / 2)
            else:
                q = PHYS["door"]["closedM3h"] / 60
            va, vb = H.room_profile(a)["areaM2"] * PHYS["ceilingM"], H.room_profile(b)["areaM2"] * PHYS["ceilingM"]
            f = math.exp(-q * dt * (1 / va + 1 / vb))
            for k in ("temperature", "vapor", "pm25", "co2"):
                xa, xb = ea[k], eb[k]
                m, d = (va * xa + vb * xb) / (va + vb), (xa - xb) * f
                ea[k], eb[k] = m + d * vb / (va + vb), m - d * va / (va + vb)

    def step(self, ms, dt):
        out = outdoor_at(ms)
        H = self.house
        for r in H.room_ids:
            e = self.rooms[r]
            if r != "balcony" and e.get("vapor") is None:
                e["vapor"] = vapor_from_rh(e["humidity"], e["temperature"])
        self.exchange(dt)
        balcony_door = H.at("balcony", "door_contact")
        for r in H.room_ids:
            e = self.rooms[r]
            devs = H.by_room[r]
            p = H.room_profile(r)
            sf = 10 / p["areaM2"]

            def is_(t, cap, attr, v):
                d = devs.get(t)
                return d is not None and d.state.get(f"{cap}.{attr}") == v

            occ = is_("occupancy_sensor", "presenceSensor", "presence", "present")
            light_on = is_("light", "switch", "switch", "on")
            if r == "balcony":
                e.update(temperature=out["temperature"], humidity=out["humidity"], pm25=out["pm25"], co2=out["co2"],
                         illuminance=out["daylight"] + (200 if light_on else 0), noise=db_sum([out["noise"], 45] if occ else [out["noise"]]))
                continue
            win_open = is_("window_contact", "contactSensor", "contact", "open")
            door_open = r == "living_room" and balcony_door is not None and balcony_door.state.get("contactSensor.contact") == "open"
            is_open = win_open or door_open
            wind_k = WEATHER["windOpen"][0] + WEATHER["windOpen"][1] * out["windSpeed"] / WIND["mean"]
            k_open = max(PHYS["windowOpen"][p["windowSize"]] if win_open else 0, PHYS["windowOpen"]["large"] if door_open else 0) * wind_k
            k_closed = PHYS["closedByWalls"][p["exteriorWalls"]]
            wall_share = (0.5 + p["exteriorWalls"]) / 1.5
            k = k_open if is_open else k_closed
            temp_target = out["temperature"] if is_open else free_indoor_temp(out, p)
            if e.get("mass") is None:
                e["mass"] = e["temperature"]
            from_mass = PHYS["massToAir"] * (e["mass"] - e["temperature"]) * dt
            e["mass"] += PHYS["airToMass"] * (e["temperature"] - e["mass"]) * dt
            e["temperature"] += (temp_target - e["temperature"]) * k * dt + from_mass
            if e.get("vapor") is None:
                e["vapor"] = vapor_from_rh(e["humidity"], e["temperature"])
            e["vapor"] += (vapor_from_rh(out["humidity"], out["temperature"]) + (0 if is_open else PHYS["moistureOffset"]) - e["vapor"]) * k * dt
            e["pm25"] += (out["pm25"] - e["pm25"]) * (k_open if is_open else PHYS["pmInfiltration"] * wall_share) * dt
            e["co2"] += (out["co2"] - e["co2"]) * (0.05 if is_open else 0.003) * dt
            if occ:
                e["co2"] += 10 * sf * dt
                e["temperature"] += 0.003 * sf * dt
                e["vapor"] += PHYS["moisture"]["person"] * sf * dt
            hvac = devs.get("heating_cooling_unit")
            mode = hvac.state.get("thermostatMode.thermostatMode") if hvac else None
            if mode == "cool":
                # capacity-based cooling (2026-11-04): the unit draws room air through its coil at its airflow and removes
                # heat up to its capacity; how much goes to cooling and how much to condensing water follows from the
                # coil (coil_outlet). Control: full output (max) at >= 1 K above the setpoint, in proportion below,
                # off at or below the setpoint; never below the inverter's minimum while running.
                target = hvac.state.get("thermostatCoolingSetpoint.coolingSetpoint")
                rated = AC_KW[H.type].get(r, AC_ROOM_KW)
                m3 = AC_M3MIN_PER_KW * rated
                n = 6  # 10 s sub-steps, so the room does not overshoot the setpoint within a minute
                for _ in range(n):
                    over = e["temperature"] - target
                    if over <= 0:
                        break
                    kw = max(AC_MIN, min(1, over) * AC_MAX) * rated
                    # fan speed follows the output: low (4.0 of 6.0 m3/min, AJ023MB1PBC1 high / mid / low 6.0 / 5.0 / 4.0) at the
                    # inverter minimum, high at its maximum, in proportion between [our assumption, agreed 2026-11-05]
                    share = (kw / rated - AC_MIN) / (AC_MAX - AC_MIN)
                    fan = m3 * (4.0 / 6.0 + 2.0 / 6.0 * max(0.0, min(1.0, share)))
                    t_out, e_out = coil_outlet(e["temperature"], e["vapor"], kw, fan)
                    f = min(1, fan * dt / n / (p["areaM2"] * PHYS["ceilingM"]))  # share of the room's air through the coil
                    w_room = w_from_e(e["vapor"])
                    e["temperature"] += (t_out - e["temperature"]) * f
                    e["vapor"] = e_from_w(w_room + (w_from_e(e_out) - w_room) * f)
            elif mode == "heat":
                target = hvac.state.get("thermostatHeatingSetpoint.heatingSetpoint")
                if e["temperature"] < target:
                    e["temperature"] += min(PHYS["hvacMaxRate"] * dt, target - e["temperature"])
            hum = devs.get("humidifier")
            hum_on = hum is not None and hum.state.get("switch.switch") == "on"
            if hum_on:
                target = vapor_from_rh(hum.state.get("humiditySetpoint.humiditySetpoint"), e["temperature"])
                if e["vapor"] < target:
                    e["vapor"] += min(PHYS["moisture"]["humidifierMax"] * sf * dt, target - e["vapor"])
            ap = devs.get("air_purifier")
            ap_share = ((ap.state.get("fanSpeedPercent.percent") or 0) / 100) if ap else 0
            if ap_share > 0:
                P = PHYS["purifier"]
                e["pm25"] -= e["pm25"] * min(0.5, P["mixingEff"] * P["cadrM3min"] * ap_share / (p["areaM2"] * PHYS["ceilingM"])) * dt

            def running(t):
                return t in OP_STATE and is_(t, OP_STATE[t][0], "machineState", "run")

            stove_on = is_("stove", "switch", "switch", "on")
            oven = devs.get("oven")
            oven_on = oven is not None and oven.state.get("mode.mode") != "off"
            robot_on = is_("robot_vacuum", "robotCleanerOperatingState", "operatingState", "running")
            if stove_on:
                e["temperature"] += 0.03 * sf * dt
                e["pm25"] += 0.6 * sf * dt
                e["co2"] += 5 * sf * dt
            if oven_on:
                e["temperature"] += 0.02 * sf * dt
            dryer_on, washer_on = running("dryer"), running("washer")
            if dryer_on:
                e["temperature"] += 0.02 * sf * dt
                e["vapor"] += PHYS["moisture"]["dryer"] * sf * dt
            if washer_on:
                e["vapor"] += PHYS["moisture"]["washer"] * sf * dt
            if robot_on:
                e["pm25"] += 0.1 * sf * dt
            e["vapor"] = max(0.5, min(sat_vapor(e["temperature"]), e["vapor"]))
            e["humidity"] = rh_from_vapor(e["vapor"], e["temperature"])
            e["pm25"] = max(0, e["pm25"])
            e["co2"] = max(400, e["co2"])
            lux = out["daylight"] * PHYS["windowLight"][p["windowSize"]] * window_sun(p, out)
            curtain = devs.get("curtain")
            if curtain is not None:
                lux *= PHYS["curtain"].get(curtain.state.get("windowShade.windowShade"), 0.6)
            fixture = (10 / p["areaM2"]) ** 0.4
            if light_on:
                lux += PHYS["lightLux"] * fixture
            lamp = devs.get("lamp")
            if lamp is not None and lamp.state.get("switch.switch") == "on":
                lux += PHYS["lampLux"] * fixture * lamp.state.get("switchLevel.level") / 100
            e["illuminance"] = lux
            L = [28]
            if p["windowSize"] != "none":
                L.append(out["noise"] - (FACADE_DB["open"] if is_open else FACADE_DB["closed"]))
            if occ:
                L.append(40)
            tv = devs.get("tv")
            if tv is not None and tv.state.get("switch.switch") == "on":
                L.append(55 if tv.state.get("mediaPlayback.playbackStatus") == "playing" else 45)
            if robot_on:
                L.append(65)
            if washer_on:
                L.append(60)
            if dryer_on:
                L.append(58)
            if running("dishwasher"):
                L.append(50)
            if stove_on:
                L.append(42)
            if oven_on:
                L.append(40)
            if ap_share > 0:
                L.append(31 + 17 * ap_share)
            if mode and mode != "off":
                L.append(38)
            if hum_on:
                L.append(33)
            e["noise"] = db_sum(L)
