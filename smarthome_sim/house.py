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

ALL_ROOMS = ["room1", "room2", "room3", "room4", "living_room", "kitchen", "dining_room", "bathroom", "laundry", "closet", "hallway", "entryway", "balcony"]
HOUSE_EXCLUDE = {"2room": ["room3", "room4", "hallway"], "3room": ["room4"], "4room": []}
ROOM_LABEL = dict(room1="Room 1", room2="Room 2", room3="Room 3", room4="Room 4", living_room="Living room", kitchen="Kitchen",
                  dining_room="Dining room", bathroom="Bathroom", laundry="Laundry", closet="Closet", hallway="Hallway", entryway="Entryway", balcony="Balcony")
DEVICE_LABEL = dict(temperature_sensor="Temperature", humidity_sensor="Humidity", light_sensor="Light level", occupancy_sensor="Occupancy",
                    air_quality_sensor="Air quality", noise_sensor="Noise", door_contact="Door contact", window_contact="Window contact",
                    water_leak_sensor="Water leak", smoke_alarm="Smoke alarm", doorbell="Doorbell", wifi_router="Wi-Fi router", light="Light",
                    lamp="Lamp", heating_cooling_unit="Heating/cooling", humidifier="Humidifier", air_purifier="Air purifier", curtain="Curtain",
                    tv="TV", speaker="Speaker", robot_vacuum="Robot vacuum", dishwasher="Dishwasher", oven="Oven", stove="Stove", washer="Washer",
                    dryer="Dryer", lock="Lock")
# initial values (simulator's choice)
DEFAULTS = {
    "switch.switch": "off", "presenceSensor.presence": "not present", "contactSensor.contact": "closed", "waterSensor.water": "dry",
    "smokeDetector.smoke": "clear", "button.button": None, "lock.lock": "locked", "windowShade.windowShade": "closed",
    "mediaPlayback.playbackStatus": "stopped", "robotCleanerOperatingState.operatingState": "docked", "cycleState.cycleState": "idle",
    "thermostatMode.thermostatMode": "off", "connection.connection": "disconnected", "preheat.preheat": "idle", "errorCode.errorCode": "none",
    "temperatureMeasurement.temperature": 22, "relativeHumidityMeasurement.humidity": 45, "illuminanceMeasurement.illuminance": 300,
    "fineDustSensor.fineDustLevel": 15, "carbonDioxideMeasurement.carbonDioxide": 600, "soundPressureLevel.soundPressureLevel": 35,
    "connectedDevices.connectedDevices": 8, "switchLevel.level": 100, "colorTemperature.colorTemperature": 4000,
    "thermostatCoolingSetpoint.coolingSetpoint": 24, "thermostatHeatingSetpoint.heatingSetpoint": 22, "humiditySetpoint.humiditySetpoint": 50,
    "fanSpeedPercent.percent": 0, "audioVolume.volume": 30, "battery.battery": 100, "remainingTime.remainingTime": 0,
    "temperatureSetpoint.temperatureSetpoint": 180,
}
OUTDOOR_DEFAULTS = {"temperatureMeasurement.temperature": 15, "relativeHumidityMeasurement.humidity": 60, "fineDustSensor.fineDustLevel": 30,
                    "carbonDioxideMeasurement.carbonDioxide": 420}
CMD_VALUE = dict(on="on", off="off", lock="locked", unlock="unlocked", open="open", close="closed", play="playing", stop="stopped",
                 start="running", goHome="seekingCharger", startHeatedDry="running")
PAUSE_VALUE = dict(windowShade="partially_open", playbackStatus="paused", operatingState="paused")
CYCLE_MINUTES = dict(washer=dict(normal=60, quick=30, bedding=90), dishwasher=dict(start=120, startHeatedDry=150))

PHYS = dict(
    stepMs=60000, heartbeatMin=30, maxCatchUpDays=7,
    closedByWalls=[0.0008, 0.0016, 0.0024],
    indoorGainC=2, indoorSwing=0.25, indoorMinC=15, solarGainC=3,
    massToAir=0.05, airToMass=0.002, hvacMaxRate=0.5,
    moistureOffset=3, moisture=dict(person=0.0025, dryer=0.035, washer=0.007, humidifierMax=0.04),
    acCoilC=13, acDryRate=0.03,
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
    pmInfiltration=0.01, mixing=dict(open=0.04, closed=0.005),
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
        if self.type in ("washer", "dryer") and cmd == "start":
            out = [(cap_name, attr, "running"), ("mode", "mode", args[0] if args else None)]
            out.append(("remainingTime", "remainingTime", (args[1] if len(args) > 1 else None) if self.type == "dryer"
                        else CYCLE_MINUTES["washer"].get(args[0] if args else None, 60)))
            return out
        if self.type == "dishwasher" and cmd in ("start", "startHeatedDry"):
            return [(cap_name, attr, "running"), ("remainingTime", "remainingTime", CYCLE_MINUTES["dishwasher"][cmd])]
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
                if r in by_room:
                    by_room[r].append(Device(d["deviceIds"][i], d["device"], r, d["capabilities"]))
        self.devices = {}
        for r in self.room_ids:
            for d in by_room[r]:
                self.devices[d.id] = d
        self.by_room = {r: {d.type: d for d in by_room[r]} for r in self.room_ids}
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

    def step(self, ms, dt):
        out = outdoor_at(ms)
        H = self.house
        mp = mc = mv = vol = 0
        for r in H.room_ids:
            if r == "balcony":
                continue
            e = self.rooms[r]
            a = H.room_profile(r)["areaM2"]
            vol += a
            mp += e["pm25"] * a
            mc += e["co2"] * a
            v = e.get("vapor")
            mv += (v if v is not None else vapor_from_rh(e["humidity"], e["temperature"])) * a
        vol = vol or 1
        mp, mc, mv = mp / vol, mc / vol, mv / vol
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
            k_mix = PHYS["mixing"]["open"] if r in OPEN_PLAN else PHYS["mixing"]["closed"]
            e["pm25"] += (mp - e["pm25"]) * k_mix * dt
            e["co2"] += (mc - e["co2"]) * k_mix * dt
            e["vapor"] += (mv - e["vapor"]) * k_mix * dt
            e["co2"] += (out["co2"] - e["co2"]) * (0.05 if is_open else 0.003) * dt
            if occ:
                e["co2"] += 10 * sf * dt
                e["temperature"] += 0.003 * sf * dt
                e["vapor"] += PHYS["moisture"]["person"] * sf * dt
            hvac = devs.get("heating_cooling_unit")
            mode = hvac.state.get("thermostatMode.thermostatMode") if hvac else None
            if mode == "cool":
                target = hvac.state.get("thermostatCoolingSetpoint.coolingSetpoint")
                coil = sat_vapor(PHYS["acCoilC"])
                if e["temperature"] > target:
                    e["temperature"] -= min(PHYS["hvacMaxRate"] * dt, e["temperature"] - target)
                if e["vapor"] > coil:
                    e["vapor"] -= (e["vapor"] - coil) * PHYS["acDryRate"] * dt
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
                return is_(t, "cycleState", "cycleState", "running")

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
            spk = devs.get("speaker")
            if spk is not None and spk.state.get("mediaPlayback.playbackStatus") == "playing":
                L.append(40 + 0.4 * spk.state.get("audioVolume.volume"))
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
