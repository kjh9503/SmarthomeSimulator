"""Devices, the house layout and each room's true indoor conditions (temperature, humidity, PM2.5, CO2, light, noise).
Ported from smarthome-sim.html; constants and their sources are the same."""
import json
import math
import os

from .weather import outdoor_at, db_sum, WEATHER, WIND, FACADE_DB, solar_at, vertical_irradiance

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
                    tv="TV", floor_heating="Floor heating", robot_vacuum="Robot vacuum", dishwasher="Dishwasher", oven="Oven", stove="Stove", washer="Washer",
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
    "thermostatCoolingSetpoint.coolingSetpoint": 24, "thermostatHeatingSetpoint.heatingSetpoint": 22, "thermostatOperatingState.thermostatOperatingState": "idle",
    "sim.heatingTimer.onTimer": 0, "sim.heatingTimer.offTimer": 0, "humiditySetpoint.humiditySetpoint": 50,
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
    indoorGainC=2, indoorSwing=0.25, indoorMinC=15, solarGainC=3,
    # moisture (2026-11-21): the fixed +3 hPa over outdoor air (moistureOffset, no source) is gone; sources are physical, in g:
    # a person 52 g/h (family of 4: 0.44 pint/h, Minnesota 1988 table; 1.25 L a day, Quirouette, NRC Canada), a shower
    # 0.24 kg per 5 min (same table), indoor laundry drying 2.2-2.9 kg a load (same table) released over rackHours [assume]
    # or more slowly when the room air is saturated.
    # dryer / washer / humidifierMax stay hPa a minute for a 10 m2 room (older values).
    moisture=dict(personGh=52, showerGMin=48, rackKg=(2.2, 2.9), rackHours=(8, 12), dryer=0.035, washer=0.007, humidifierMax=0.04),
    report=dict(temperature=dict(th=0.5, dec=1), humidity=dict(th=2, dec=0), illuminance=dict(th=30, rel=0.1, dec=0),
                pm25=dict(th=3, dec=0), co2=dict(th=50, dec=0), noise=dict(th=3, dec=0)),
    jitter=dict(temperature=0.05, humidity=0.3, illuminance=0.02, pm25=0.5, co2=4, noise=0.8),
    windowLight=dict(large=.03, medium=.02, small=.012, none=.002),
    windowHeat=dict(large=1, medium=.6, small=.3, none=0),
    lightLux=300, lampLux=150, ceilingM=2.3,
    # air purifier: CADR ~8.4 m3/min; the fan percent is the share of full CADR (0 = off); tuned to the 30-74% PM2.5 cut
    # measured in 10 homes (Public Health Research & Practice, 2024)
    purifier=dict(cadrM3min=8.4, mixingEff=0.4),
    pmInfiltration=0.01,
    # heat balance of a room (2026-11-05): ISO 13790 5R1C (air, inner surface, mass; Modelica Buildings ISO13790.Zone5R1C):
    # air-surface 3.45 W/m2K over 4.5 x floor area, surface-mass 9.1 W/m2K over 3.0 x floor area and 260 kJ/m2K per floor area
    # ("heavy", ISO13790.Data.Heavy: concrete flats). U [W/m2K]: wall 0.170, window 1.0 (energy-saving design standard for
    # flats, central region 2; wall: notice 2024-421, window: from 2018-09-01). Infiltration ACH50 3.51 (Yoon 2013, 27 new
    # Korean flats) / 20 (Persily's rule; Sherman's N ~ 20) = 0.18 per hour. Our own assumptions: window area 40 / 25 / 15 %
    # of the floor (large / medium / small), each exterior wall sqrt(floor area) long, SHGC 0.5, daylight 110 lux per W/m2 (not used for heat since 2026-11-20: phi_sol),
    # curtain passes the same share of solar heat as of light, internal gains (W): person 65 (Kim & Byun 2008 sensible),
    # ceiling light 10 W/m2 (ibid., bedroom), TV 100, oven 2000, dryer 300, washer 150, dishwasher 300. Stove: see stove=.
    # Neighbours (2026-11-05): the flat is a middle floor; its floor and ceiling slabs (each the room's floor area) pass heat to
    # the flats below and above at U 0.810 W/m2K (design standard, floor between storeys, notice 2025-738), into the mass node;
    # side neighbours are left out (about 1% of the heat, Lee, Koo & Hong 2016). Their temperature: NEIGHBOUR (measured, all year;
    # until 2026-11-26 22 C below a 15 C outdoor daily mean [our assumption], otherwise no heat flow).
    envelope=dict(uWall=0.170, uWindow=1.0, windowShare=dict(large=0.40, medium=0.25, small=0.15, none=0.0), shgc=0.5,
                  luxPerW=110, ach=3.51 / 20, hIs=3.45, aTotPerFloor=4.5, hMs=9.1, aMassPerFloor=3.0, cMassPerFloor=260000,
                  # floor heating (ondol, 2026-11-05): heat into the slab (mass node) at 52 W/m2 of floor for 40 C supply water and a
                  # 22 C room, wood finish (Jang, Yu & Cho 2007, SAREK winter conference: wood 52.0, vinyl 70.7, tile 79.3 W/m2),
                  # in proportion to (supply - air); supply water 40 C and the thermostat's +-0.5 K band are our own assumptions
                  # The heat goes through a floor layer of its own (2026-11-05): the 40 mm finishing mortar, the "ondol heat-storage
                  # layer" over 70 mm foamed concrete (Mun et al. 2016, KSNVE 26(2)); mortar 2000 kg/m3 x 1000 J/kgK [our
                  # assumption] -> 80 kJ/m2K. Floor to room 11.1 W/m2K (EN 1264, Danfoss guide); pipe to floor 4.72 W/m2K and the
                  # downward share 0.21 so that 40 C supply and a 22 C room give 52 W/m2 up and 10.8 down at a 26.7 C floor
                  # (Jang et al. 2007: wood 52.0 up, 10.8 down, mean surface 26.8 C). Downward heat goes to the flat below.
                  floor=dict(supplyC=40.0, bandK=0.5, cPerM2=80000, hUp=11.1, kPipe=4.72, downShare=10.8 / 52.0),
                  uPartyFloor=0.810,
                  gains=dict(person=65, lightPerM2=10, tv=100, oven=2000, dryer=300, washer=150, dishwasher=300),
                  # stove (2026-11-21): one large burner at full flame while the stove is on [assume], 4.07 kW of gas
                  # (Rinnai RBR-S3000, city gas; seller's table); of a gas range's energy 30% heats the room air and 20%
                  # goes to moisture (Building America benchmark): 1.22 kW sensible, 0.81 kW latent (about 1.2 kg water/h)
                  stove=dict(burnerKW=4.07, sensible=0.30, latent=0.20),
                  # kitchen range hood (2026-11-21): runs while the stove is on when the person's hoodHabits say so (no
                  # SmartThings capability: effect only). Exhaust 0.018 m3/s, stage 1 measured in a Korean flat (Lee,
                  # Jeong & Kang 2017), replaced by outdoor air; removes 85% of the cooking PM2.5 (80-90%, Lee 2016).
                  hood=dict(m3s=0.018, pmCapture=0.85),
                  # ventilation unit (2026-11-18): flats of 30+ households built or remodelled since 2006-02 must be able to
                  # ventilate 0.5 air changes per hour (natural or mechanical; Rules on Building Equipment Standards art. 11,
                  # annex 1-5: the "proper" fan step gives 0.5/h). It runs when the person's ventilationHabits say so; it has
                  # no SmartThings capability, so it is not a device and writes no lines, only its effect on every room.
                  # Heat recovery: total (heat + moisture) recovery measured in Korean flats, 46% in winter and 27% in
                  # summer (Kim, Park & Sohn 2005). Chosen each minute by which air is warmer (agreed 2026-11-19): outdoor
                  # colder than the room -> 46%, outdoor warmer -> 27%; so spring and autumn switch between the two within
                  # a day (the exchanger is passive: heat goes from the warmer stream to the colder). Using the two
                  # seasonal averages in between seasons, and the same factor for moisture, are [assume]. Lab ratings are
                  # higher (certified units 2014: cooling 45-71.4%, mean 52.7; heating 70-87%, mean 73.5; Shin et al.
                  # 2014). Outdoor-air filter 60% (annex 1-5, KS B 6141, counting method), applied to PM2.5 [assume].
                  # open windows (2026-11-20, see k_open): open share of the glass, window height (m) [assume: balcony-type
                  # living room window 2.1 m, room window 1.5 m, small 1.0 m]
                  openShare=0.5, windowHeightM=dict(large=2.1, medium=1.5, small=1.0, none=0.0),
                  # front balcony, not expanded, in flats of 84 m2 and more (agreed 2026-11-22): depth 1.5 m (balconies within
                  # 1.5 m of the building are left out of the floor-area ratio; Economist 2018-01-28) x living room width
                  # (taken as sqrt of its area) [assume]; outer glass 2.2 m high over that width [assume]. Outer glass: clear
                  # double glazing U 2.4 (integrated U of clear double glazing, Yoon, Ahn & Kim 2007). SHGC 0.5 over the whole
                  # glass area with its frames, as the room windows (2026-11-23: glass-only shading coefficient of double
                  # glazing 0.83, Kim, Moon & Yu 2013 table 2, x 0.87 = SHGC 0.72; x frame factor about 0.7 [assume]; 0.7
                  # before gave the balcony 33.9 C in January). 0.7 of the sun passing on into the living room [assume]; air change 1.0 an hour through the balcony frames [assume].
                  # No heating; slabs face the neighbours' balconies (no exchange). luxShare: daylight reaching its sensor.
                  balcony=dict(uGlass=2.4, shgc=0.5, tau=0.7, ach=1.0, glassHeightM=2.2, luxShare=0.35),
                  ventilator=dict(ach=0.5, recoveryHeating=0.46, recoveryCooling=0.27, filter=0.60)),
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
# rated cooling kW by place: rooms and the 4room kitchen 6-pyeong 2.3 kW;
# living room 2room 8-pyeong 3.2 kW (AJ032MB1PBC1), 3room / 4room 18-pyeong 7.2 kW (AJ072MB1PBC1).
# The 2.3 kW unit from one model (2026-11-26; before, the airflow 6.0 / 5.0 / 4.0 came from AJ023MB1PBC1 and the range from
# AC023CN1PBH1, so the maximum 3.7 kW went through 6.0 m3/min and the air left at 5-9 C): Wind-Free 1Way AC023CN1PBH1,
# cooling min / rated / max 0.79 / 2.30 / 3.70 kW, sensible 1.8 kW, airflow high / mid / low 7.2 / 6.6 / 6.3 m3/min.
# Airflow of the 3.2 / 7.2 kW units not found: in proportion to 2.3 kW (3.13 m3/min per kW), and the same range for every
# size [our assumptions].
AC_KW = {"2room": dict(living_room=3.2), "3room": dict(living_room=7.2), "4room": dict(living_room=7.2)}
AC_ROOM_KW, AC_M3MIN_PER_KW, AC_MIN, AC_MAX, AC_FAN_LOW = 2.3, 7.2 / 2.3, 0.79 / 2.30, 3.70 / 2.30, 6.3 / 7.2
AC_OFF_BELOW_K, AC_RESTART_MS = 1.5, 3 * 60000  # compressor off below the setpoint, shortest off time (see Environment)
P_HPA = 1013.25


def w_from_e(e):
    """humidity ratio kg/kg from vapour pressure hPa"""
    return 0.622 * e / (P_HPA - e)


def e_from_w(w):
    return w * P_HPA / (0.622 + w)


def enthalpy(t, w):
    """moist air kJ per kg dry air"""
    return 1.006 * t + w * (2501 + 1.86 * t)


def _t_sat_from_h(h):
    """temperature of saturated air with enthalpy h (kJ/kg)"""
    lo, hi = -40.0, 60.0
    for _ in range(40):
        mid = (lo + hi) / 2
        if enthalpy(mid, w_from_e(sat_vapor(mid))) > h:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


# Cooling coil (2026-11-26): apparatus dew point / bypass factor, the method of EnergyPlus's DX cooling coil (Engineering
# Reference, single-speed DX coil, eqs. 460-466: BF = exp(-A0 / m), h_ADP = h_in - Q / m / (1 - BF),
# SHR = (h(T_in, w_ADP) - h_ADP) / (h_in - h_ADP), dry coil when w_in <= w_ADP). A0 from the catalogue of the same unit family
# (Samsung WindFree 1Way cassette AC026RN1DKG: 2.6 kW total, 1.9 kW sensible, airflow high 7.3 m3/min, at 27 C / 19 C wet
# bulb [the EN 14511 rating point; the sheet says "nominal"]): BF 0.239, A0 0.0803 kg/s per kW of rated capacity, taken
# in proportion to capacity for our units [our assumption]. Check: the same A0 per kW gives the 3.5 kW AC035RN1DKG
# (9.0 m3/min) SHR 0.714, catalogue 2.5 / 3.5 = 0.714. Before: an ideal coil (sensible down to the dew point, then
# saturated), which at high output sent out saturated air at 3-9 C and at rated removed less water than the catalogue
# (2.3 kW at 27 / 19: 0.66 kg/h, SHR 0.80).
COIL_RATED = dict(kw=2.6, sensibleKw=1.9, m3min=7.3, t=27.0, wb=19.0)


def _a0_per_kw():
    R = COIL_RATED
    m = 1.2 * R["m3min"] / 60
    e = sat_vapor(R["wb"]) - 0.00066 * (1 + 0.00115 * R["wb"]) * P_HPA * (R["t"] - R["wb"])  # psychrometer formula
    w = w_from_e(e)
    h = enthalpy(R["t"], w)
    h_out = h - R["kw"] / m
    t_out = R["t"] - R["sensibleKw"] / (m * (1.006 + 1.86 * w))
    w_out = (h_out - 1.006 * t_out) / (2501 + 1.86 * t_out)
    slope = (w_out - w) / (t_out - R["t"])
    f = lambda x: w_from_e(sat_vapor(x)) - w - slope * (x - R["t"])
    lo, hi = -20.0, t_out  # the apparatus dew point: where the line through inlet and outlet meets saturation
    for _ in range(60):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0:
            hi = mid
        else:
            lo = mid
    t_adp = (lo + hi) / 2
    h_adp = enthalpy(t_adp, w_from_e(sat_vapor(t_adp)))
    bf = (h_out - h_adp) / (h - h_adp)
    return -math.log(bf) * m / R["kw"]



def coil_outlet(t_in, e_in, kw, m3min, rated_kw):
    """air through the cooling coil of a unit of rated_kw that removes kw at m3min: (t_out, e_out)"""
    m = 1.2 * m3min / 60  # kg/s
    w_in = w_from_e(e_in)
    h_in = enthalpy(t_in, w_in)
    h_out = h_in - kw / m
    bf = math.exp(-COIL_A0_PER_KW * rated_kw / m)
    h_adp = h_in - kw / m / (1 - bf)
    w_adp = w_from_e(sat_vapor(_t_sat_from_h(h_adp)))
    if w_in <= w_adp:  # dry coil: all sensible
        return (h_out - 2501 * w_in) / (1.006 + 1.86 * w_in), e_in
    shr = min(1.0, (enthalpy(t_in, w_adp) - h_adp) / (h_in - h_adp))
    h_tw = h_in - (1 - shr) * (h_in - h_out)
    w_out = (h_tw - 1.006 * t_in) / (2501 + 1.86 * t_in)
    return (h_out - 2501 * w_out) / (1.006 + 1.86 * w_out), e_from_w(w_out)


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
    """only the starting state of the rooms (Environment.settle); the rooms then follow the heat balance in step"""
    solar = PHYS["solarGainC"] * PHYS["windowHeat"][profile["windowSize"]] * window_sun(profile, out) * out["daylight"] / 80000  # start state only; /80000 since daylight became about 4x (2026-11-21)
    return max(PHYS["indoorMinC"], out["meanTemperature"] + PHYS["indoorGainC"] + PHYS["indoorSwing"] * (out["temperature"] - out["meanTemperature"])) + solar


def sat_vapor(t):
    return 6.112 * math.exp(17.62 * t / (243.12 + t))


COIL_A0_PER_KW = _a0_per_kw()  # needs sat_vapor (above)


def vapor_from_rh(rh, t):
    return rh / 100 * sat_vapor(t)


def g_to_hpa(g, vol):
    """water vapour pressure rise (hPa) from g grams of water in vol m3 of air at about 22 C (1 g/m3 = 1.36 hPa)"""
    return g * 1.36 / vol


def rh_from_vapor(e, t):
    return min(100, max(1, 100 * e / sat_vapor(t)))


class Device:
    __slots__ = ("id", "type", "roomId", "capabilities", "state", "aux", "_caps", "sensor")

    def __init__(self, id, type, room_id, capabilities):
        self.id, self.type, self.roomId, self.capabilities = id, type, room_id, capabilities
        self.sensor = True  # False: a window with no open/close sensor; its state still drives the physics, but writes no line
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
        if cap_name == "sim.heatingTimer":  # our own reservation capability (no SmartThings definition): minutes from now
            if cmd == "setOnTimer":
                return [(cap_name, "onTimer", int(args[0]))]
            if cmd == "setOffTimer":
                return [(cap_name, "offTimer", int(args[0]))]
            if cmd == "cancelTimer":
                return [(cap_name, "onTimer", 0), (cap_name, "offTimer", 0)]
            raise ValueError(f"Unknown command: {cmd}")
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
        # a balcony only where the plan has one (agreed 2026-11-25): the plans of 84 m2 and more have a real front balcony
        # (room_profiles.json glassM2); the smaller ones (2room-A/B/C, 3room-C) are expanded, so there is no balcony space,
        # no sensors or light on it and no way to it. Before, they kept an unreachable 'balcony' whose sensors wrote the
        # outdoor values (office 2room-A: 21,356 lines a year).
        has_balcony = bool(self.profile["rooms"].get("balcony", {}).get("glassM2"))
        self.room_ids = [r for r in ALL_ROOMS if r not in HOUSE_EXCLUDE[self.type] and (r != "balcony" or has_balcony)]
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

    def path(self, a, b):
        """rooms walked through from a to b, both included (CONNECTIONS of the house type, plus living room - balcony);
        [b] when there is no route"""
        if a is None or a == b:
            return [b]
        adj = {}
        links = list(CONNECTIONS[self.type]) + ([("door", "living_room", "balcony")] if "balcony" in self.room_ids else [])
        for c in links:
            x, y = c[1], c[2]
            if x in self.room_ids and y in self.room_ids:
                adj.setdefault(x, []).append(y); adj.setdefault(y, []).append(x)
        prev, todo = {a: None}, [a]
        while todo:
            x = todo.pop(0)
            if x == b:
                break
            for y in adj.get(x, []):
                if y not in prev:
                    prev[y] = x; todo.append(y)
        if b not in prev:
            return [a, b]
        out = [b]
        while out[-1] != a:
            out.append(prev[out[-1]])
        return out[::-1]

    def room_profile(self, r):
        return self.profile["rooms"].get(r, NO_PROFILE)

    def at(self, r, type):
        return self.by_room.get(r, {}).get(type)


WINDOW_SUBSTEPS = 6  # physics steps a minute while any window is open (Environment.step)

# The flats above and below (agreed 2026-11-26): their indoor temperature all year from measurement, drawn rather than
# simulated. Yun et al. 2020 (IJERPH 17(19) 7334, table 3; 8 Seoul apartments, Mar 2016 - Mar 2017, hourly, all hours,
# cooling on and off): winter (Dec-Feb) 20.0 +- 2.1 C, spring / autumn (Mar-May, Sep-Nov) 23.0 +- 2.5 C, summer (Jun-Aug)
# 26.6 +- 2.0 C. Our assumptions: the seasonal mean follows a line through one point per season (mid-January, mid-April,
# mid-July, mid-October), the points set so that each season's mean is the measured one; the SD runs linearly between the
# same points; each flat (above, below) moves by its own day-to-day AR(1) z (correlation 0.7, hour by hour on a line between
# days) and sits at mean + SD x tanh(0.5 z), so it stays within one SD of the seasonal mean (agreed: "move a little within
# the deviation") [no data on how a flat's temperature drifts]. Before (2026-11-05 - 11-26): 22 C [our assumption] while the outdoor daily mean
# was below 15 C, otherwise no heat flow, so a closed flat in summer kept all its heat (remote Aug living room 14 K above
# outdoors).
NEIGHBOUR = dict(seasons=(((12, 1, 2), 20.0, 2.1), ((3, 4, 5), 23.0, 2.5), ((6, 7, 8), 26.6, 2.0), ((9, 10, 11), 23.0, 2.5)),
                 nodeDoy=(14.5, 104.5, 196.5, 287.5), rhoDay=0.7, zScale=0.5)


def _neighbour_nodes():
    """values at nodeDoy so that the piecewise-linear yearly curve has the measured mean in each season"""
    import datetime as _d
    doys = [(_d.date(2025, 1, 1) + _d.timedelta(i)) for i in range(365)]
    X = NEIGHBOUR["nodeDoy"]

    def curve(v, x):
        for i in range(4):
            a, b = X[i], X[(i + 1) % 4] + (365 if i == 3 else 0)
            xx = x + 365 if x < X[0] else x
            if a <= xx < b:
                return v[i] + (v[(i + 1) % 4] - v[i]) * (xx - a) / (b - a)
        return v[0]
    S = NEIGHBOUR["seasons"]
    v = [s[1] for s in S]
    for _ in range(200):
        means = [sum(curve(v, i + 0.5) for i, d in enumerate(doys) if d.month in s[0]) /
                 sum(1 for d in doys if d.month in s[0]) for s in S]
        v = [v[i] + S[i][1] - means[i] for i in range(4)]
    return v, curve


NEIGHBOUR_NODES, _neighbour_curve = _neighbour_nodes()


class Neighbours:
    """indoor temperature of the flats above and below (NEIGHBOUR): a seasonal curve plus a seeded day-to-day drift"""
    ORIGIN = 20454  # day index (local) of 2026-01-01; the drift is drawn forward from it, so any start gives the same days

    def __init__(self, seed=0):
        import random
        self.rng = random.Random(f"neighbours/{seed}")
        r = NEIGHBOUR["rhoDay"]
        self.k = (r, math.sqrt(1 - r * r))
        self.z = [(self.rng.gauss(0, 1), self.rng.gauss(0, 1))]

    def _z(self, day):
        i = max(0, day - self.ORIGIN)
        while len(self.z) <= i + 1:
            r, s = self.k
            a, b = self.z[-1]
            self.z.append((r * a + s * self.rng.gauss(0, 1), r * b + s * self.rng.gauss(0, 1)))
        return self.z[i], self.z[i + 1]

    def temps(self, ms):
        """(above, below) in C at ms"""
        import datetime as _d
        x = (ms + 9 * 3600000) / 86400000
        day = int(x // 1)
        f = x - day
        date = _d.date(1970, 1, 1) + _d.timedelta(day)
        doy = min(364.999, (date - _d.date(date.year, 1, 1)).days + f)
        mean = _neighbour_curve(NEIGHBOUR_NODES, doy)
        sd = _neighbour_curve([s[2] for s in NEIGHBOUR["seasons"]], doy)
        (a0, b0), (a1, b1) = self._z(day)
        g = NEIGHBOUR["zScale"]
        return mean + sd * math.tanh(g * (a0 + (a1 - a0) * f)), mean + sd * math.tanh(g * (b0 + (b1 - b0) * f))



class Environment:
    def __init__(self, house, ms):
        self.house = house
        out = outdoor_at(ms)
        self.rooms = {}
        self.heat_wh = {}  # floor heating heat delivered per room (Wh)
        self.ventilator = False  # the flat's ventilation unit running (set by the agent from ventilationHabits; no device)
        self.hood = False  # the kitchen range hood running (set by the agent from hoodHabits; no device)
        self.shower = None  # (room, until ms): a shower running (agent action person.shower)
        self.racks = []  # laundry drying indoors: dict(room, start, gMin, leftG) (agent, after a wash not dried in the dryer)
        self.real_balcony = "balcony" in house.room_ids  # only plans with a real balcony have one (House.room_ids)
        self.neighbours = Neighbours(0)  # the flats above and below; the Simulator gives it its seed
        self.ac_hold = {}  # room -> compressor state of its air conditioner below the setpoint (dict(on, offAt))
        for r in house.room_ids:
            self.rooms[r] = dict(temperature=22, mass=22, humidity=45, pm25=15, co2=600, illuminance=0, noise=30)
        self.settle(ms)

    def settle(self, ms):
        out = outdoor_at(ms)
        for r, e in self.rooms.items():
            t = free_indoor_temp(out, self.house.room_profile(r))
            vapor = min(sat_vapor(t), vapor_from_rh(out["humidity"], out["temperature"]))
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
            self._swap(a, b, q, dt)
        if self.real_balcony:
            # living room and balcony through the living room window (agreed 2026-11-23: one sliding glass door that is
            # both the window and the way out; no separate balcony door). Open: half the glass, as a door-height opening.
            d = H.at("living_room", "window_contact")
            ea, eb = self.rooms["living_room"], self.rooms["balcony"]
            if d is not None and d.state.get("contactSensor.contact") == "open":
                E = PHYS["envelope"]; lp = H.room_profile("living_room")
                hgt = E["windowHeightM"]["large"]
                width = E["openShare"] * E["windowShare"][lp["windowSize"]] * lp["areaM2"] / hgt
                q = opening_flow(width, hgt, ea["temperature"] - eb["temperature"], (ea["temperature"] + eb["temperature"]) / 2)
            else:
                q = PHYS["door"]["closedM3h"] / 60
            self._swap("living_room", "balcony", q, dt)

    def _swap(self, a, b, q, dt):
        H = self.house
        ea, eb = self.rooms[a], self.rooms[b]
        va, vb = H.room_profile(a)["areaM2"] * PHYS["ceilingM"], H.room_profile(b)["areaM2"] * PHYS["ceilingM"]
        f = math.exp(-q * dt * (1 / va + 1 / vb))
        for k in ("temperature", "vapor", "pm25", "co2"):
            xa, xb = ea[k], eb[k]
            m, d = (va * xa + vb * xb) / (va + vb), (xa - xb) * f
            ea[k], eb[k] = m + d * vb / (va + vb), m - d * va / (va + vb)

    def step(self, ms, dt):
        """advance the physics by dt minutes. With a window open the air of the rooms changes within seconds and the rooms
        swap air quickly, so the minute is split into WINDOW_SUBSTEPS steps (2026-11-25: one step a minute gave 9.3 C
        after 10 min of airing in the office living room, 6 steps 11.0 C, 600 steps 11.3 C)"""
        H = self.house
        n = WINDOW_SUBSTEPS if any(d.type == "window_contact" and d.state.get("contactSensor.contact") == "open"
                                   for d in H.devices.values()) else 1
        for i in range(n):
            self._step(ms, dt / n)

    def _step(self, ms, dt):
        out = outdoor_at(ms)
        H = self.house
        for r in H.room_ids:
            e = self.rooms[r]
            if e.get("vapor") is None:
                e["vapor"] = vapor_from_rh(e["humidity"], e["temperature"])
        self.exchange(dt)
        nb_above, nb_below = self.neighbours.temps(ms)
        RB = self.real_balcony
        if RB:  # the balcony's state at the start of this minute: what the living room's window and frames face
            bal0 = dict(self.rooms["balcony"])
            liv0 = dict(self.rooms["living_room"])
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
            win_open = is_("window_contact", "contactSensor", "contact", "open")
            is_open = win_open
            # what the room's windows and frames face: outdoors, or the balcony for the living room of a flat with one
            side = dict(temperature=bal0["temperature"], vapor=bal0["vapor"], pm25=bal0["pm25"], co2=bal0["co2"]) if RB and r == "living_room" else \
                dict(temperature=out["temperature"], vapor=vapor_from_rh(out["humidity"], out["temperature"]), pm25=out["pm25"], co2=out["co2"])
            wall_share = (0.5 + p["exteriorWalls"]) / 1.5
            E = PHYS["envelope"]
            if r == "balcony":  # outer glass instead of a window; leakier frames
                B = E["balcony"]
                E = dict(E, uWindow=B["uGlass"], shgc=B["shgc"], ach=B["ach"], windowHeightM=dict(E["windowHeightM"], large=B["glassHeightM"]))
            af = p["areaM2"]
            vol = af * PHYS["ceilingM"]
            k_open = 0.0
            if is_open:
                # open window (2026-11-20): single-sided flow, De Gids & Phaff (1982), the basis of EN 16798-7:
                # Q = 1/2 A sqrt(0.001 U10^2 + 0.0035 h dT + 0.01), A = open area, h = window height, dT = |in - out|.
                # Open area = half the glass (one sash of a sliding pair; "half the window", Cho & Choi 2013); the
                # living room window of a flat with a real balcony opens onto the balcony: exchange() swaps that air both
                # ways, so it adds nothing here. Capped at 0.8 of the room air a minute.
                size = p["windowSize"]
                a_open = E["openShare"] * (p.get("glassM2") or E["windowShare"][size] * af) if p["exteriorWalls"] and not (RB and r == "living_room") else 0.0
                h = E["windowHeightM"][size]
                u_m = math.sqrt(0.001 * out["windSpeed"] ** 2 + 0.0035 * h * abs(e["temperature"] - side["temperature"]) + 0.01)
                k_open = min(0.8, 0.5 * a_open * u_m * 60 / vol)  # per minute
            k_inf = E["ach"] / 60  # per minute
            V = E["ventilator"]
            k_vent = V["ach"] / 60 if self.ventilator else 0.0  # outdoor air brought in by the ventilation unit, per minute
            rec = V["recoveryHeating"] if out["temperature"] < e["temperature"] else V["recoveryCooling"]
            if r == "balcony":
                k_vent = 0.0  # the ventilation unit serves the heated rooms
            k_side = k_open + k_inf  # air through the windows and frames (from outdoors, or from the balcony), per minute
            k_out = k_vent * (1 - rec)  # outdoor air from the ventilation unit (heat and moisture), per minute
            if self.hood and r == "kitchen" and is_("stove", "switch", "switch", "on"):
                k_out += E["hood"]["m3s"] * 60 / vol  # range hood exhaust, made up by outdoor air
            k = k_side + k_out
            if e.get("mass") is None:
                e["mass"] = e["temperature"]
            # 5R1C heat balance in one-minute steps: the air node exact over the step (below), the mass node explicit (hours)
            a_win = (p.get("glassM2") or E["windowShare"][p["windowSize"]] * af) if p["exteriorWalls"] else 0.0
            a_wall = max(0.0, p["exteriorWalls"] * math.sqrt(af) * PHYS["ceilingM"] - a_win)
            h_win, h_op = E["uWindow"] * a_win, E["uWall"] * a_wall
            a_tot, a_m = E["aTotPerFloor"] * af, E["aMassPerFloor"] * af
            h_is, h_ms = E["hIs"] * a_tot, E["hMs"] * a_m
            h_em = 1 / (1 / h_op - 1 / h_ms) if h_op > 0 else 0.0
            h_ve = 1206 * vol * k / 60  # W/K (both air paths)
            c_air, c_m = 1206 * vol, E["cMassPerFloor"] * af
            curtain_dev = devs.get("curtain")
            shade = PHYS["curtain"].get(curtain_dev.state.get("windowShade.windowShade"), 0.6) if curtain_dev is not None else 1
            # sun on the window (2026-11-20): vertical irradiance from the sun position and the calibrated horizontal
            # irradiance (weather.solar_at, vertical_irradiance); before, daylight lux / 110 x window_sun, which was a
            # quarter of the measured horizontal irradiation and ignored the sun height
            irr = vertical_irradiance(AZIMUTH[p["window"]], solar_at(ms)) if a_win else 0.0
            phi_sol = E["shgc"] * a_win * irr * shade
            if RB and r == "living_room":  # sun reaches the living room through the balcony glass first
                phi_sol *= E["balcony"]["tau"]
            if r == "balcony":  # sun kept in the balcony: what its glass lets in minus what goes on into the living room
                lp = H.room_profile("living_room")
                passed = PHYS["envelope"]["shgc"] * PHYS["envelope"]["windowShare"][lp["windowSize"]] * lp["areaM2"] * irr * E["balcony"]["tau"]
                phi_sol = max(0.0, phi_sol - passed)
            G = E["gains"]
            phi_int = (G["person"] if occ else 0) + (G["lightPerM2"] * af if light_on else 0)
            tv_dev = devs.get("tv")
            if tv_dev is not None and tv_dev.state.get("switch.switch") == "on":
                phi_int += G["tv"]
            if is_("stove", "switch", "switch", "on"):
                phi_int += E["stove"]["burnerKW"] * E["stove"]["sensible"] * 1000
            if devs.get("oven") is not None and devs["oven"].state.get("mode.mode") != "off":
                phi_int += G["oven"]
            for t in ("dryer", "washer", "dishwasher"):
                if t in OP_STATE and is_(t, OP_STATE[t][0], "machineState", "run"):
                    phi_int += G[t]
            fh = devs.get("floor_heating")
            phi_floor_up = phi_floor_down = 0.0
            if fh is not None:  # the heated floor layer: warmed by the pipes while the valve is open, gives heat to the room
                F = E["floor"]
                if e.get("floor") is None:
                    e["floor"] = e["temperature"]
                pipe = F["kPipe"] * af * (F["supplyC"] - e["floor"]) if fh.state.get("thermostatOperatingState.thermostatOperatingState") == "heating" else 0.0
                phi_floor_up = F["hUp"] * af * (e["floor"] - e["temperature"])
                phi_floor_down = F["downShare"] * max(0.0, phi_floor_up)
                e["floor"] += (pipe - phi_floor_up - phi_floor_down) * dt * 60 / (F["cPerM2"] * af)
                self.heat_wh[r] = self.heat_wh.get(r, 0.0) + pipe * dt / 60  # heat delivered by the pipes
            if r == "balcony":  # heat through the living room's window from the living room (its loss to the balcony)
                lp = H.room_profile("living_room")
                phi_int += PHYS["envelope"]["uWindow"] * PHYS["envelope"]["windowShare"][lp["windowSize"]] * lp["areaM2"] * (liv0["temperature"] - e["temperature"])
            phi_ia = 0.5 * phi_int
            phi_m = a_m / a_tot * (0.5 * phi_int + phi_sol)
            phi_st = (1 - a_m / a_tot - h_win / (E["hMs"] * a_tot)) * (0.5 * phi_int + phi_sol) + phi_floor_up
            t_out, ta, tm = out["temperature"], e["temperature"], e["mass"]
            t_side = side["temperature"]
            sec = dt * 60
            h_side, h_outv = 1206 * vol * k_side / 60, 1206 * vol * k_out / 60
            # air node over the step (2026-11-25): exact for the step, with the mass, the outdoor / side air and the gains
            # held. Before, one explicit Euler step a minute: with a window open the air's time constant is under a minute
            # (office living room 53 s), so the air overshot (10 min airing at 0.6 C outdoors: 6.0 C after 1 min vs 16.2 C
            # stepped 600 times a minute). With the surface node ts = (h_is ta + B) / D eliminated, the air follows
            # c_air dta/dt = b - a ta.
            d_s = h_is + h_ms + h_win
            b_s = h_ms * tm + h_win * t_side + phi_st
            a_air = h_side + h_outv + h_is * (h_ms + h_win) / d_s
            t_inf = (h_side * t_side + h_outv * t_out + h_is * b_s / d_s + phi_ia) / a_air
            x = a_air * sec / c_air
            decay = math.exp(-x)
            e["temperature"] = t_inf + (ta - t_inf) * decay
            ta_mean = t_inf + (ta - t_inf) * ((1 - decay) / x if x > 1e-9 else 1.0)  # mean air temperature over the step
            ts = (h_is * ta_mean + b_s) / d_s
            # the downward share of the floor heating leaves to the flat below; the floor and ceiling slabs exchange heat with
            # the flats below and above (NEIGHBOUR), all year
            phi_nb = E["uPartyFloor"] * af * ((nb_above - tm) + (nb_below - tm)) if r != "balcony" else 0.0
            e["mass"] = tm + (h_ms * (ts - tm) + h_em * (t_side - tm) + phi_m + phi_nb) * sec / c_m
            if e.get("vapor") is None:
                e["vapor"] = vapor_from_rh(e["humidity"], e["temperature"])
            # air swapped over the step: 1 - exp(-k dt), exact for the step (2026-11-25; before k dt capped at 1, which
            # swapped 0.8 of the air in a minute at k = 0.8 / min where the exact share is 0.55)
            e["vapor"] += (side["vapor"] - e["vapor"]) * (1 - math.exp(-k_side * dt))
            e["vapor"] += (vapor_from_rh(out["humidity"], out["temperature"]) - e["vapor"]) * (1 - math.exp(-k_out * dt))
            e["pm25"] += (side["pm25"] - e["pm25"]) * ((1 - math.exp(-k_open * dt)) if is_open else PHYS["pmInfiltration"] * wall_share * dt)
            e["co2"] += (side["co2"] - e["co2"]) * ((1 - math.exp(-k_open * dt)) if is_open else 0.003 * dt)
            if k_vent:
                e["pm25"] += (out["pm25"] * (1 - V["filter"]) - e["pm25"]) * k_vent * dt
                e["co2"] += (out["co2"] - e["co2"]) * k_vent * dt
            if occ:
                e["co2"] += 10 * sf * dt
                e["vapor"] += g_to_hpa(PHYS["moisture"]["personGh"] / 60 * dt, vol)
            hvac = devs.get("heating_cooling_unit")
            mode = hvac.state.get("thermostatMode.thermostatMode") if hvac else None
            if mode != "cool":
                self.ac_hold.pop(r, None)  # switched off or another mode: starts at once next time
            if mode == "cool":
                # capacity-based cooling (2026-11-04): the unit draws room air through its coil at its airflow and removes
                # heat up to its capacity; how much goes to cooling and how much to condensing water follows from the
                # coil (coil_outlet). Control: full output (max) at >= 1 K above the setpoint, in proportion below,
                # never below the inverter's minimum while running. At and below the setpoint the compressor keeps
                # running at its minimum and stops when the room is 1.5 K below it (2026-11-26; LG support: "the
                # compressor and outdoor fan slow down and stay on at low speed; the outdoor unit goes OFF when the room
                # is 1.5-2 C or more below the setpoint", lower bound taken). It restarts when the room is back above the
                # setpoint [our assumption; not stated] and has been off at least 3 min (Samsung support: the outdoor unit
                # may take about 3 min to start, to protect it). Before: off at the setpoint. While off nothing goes
                # through the coil (fan and the water left on the coil not modelled).
                target = hvac.state.get("thermostatCoolingSetpoint.coolingSetpoint")
                hold = self.ac_hold.setdefault(r, dict(on=True, offAt=0))
                rated = AC_KW[H.type].get(r, AC_ROOM_KW)
                m3 = AC_M3MIN_PER_KW * rated
                n = 6  # 10 s sub-steps, so the room does not overshoot the setpoint within a minute
                for _ in range(n):
                    over = e["temperature"] - target
                    if hold["on"] and over <= -AC_OFF_BELOW_K:
                        hold.update(on=False, offAt=ms)
                    elif not hold["on"] and over > 0 and ms - hold["offAt"] >= AC_RESTART_MS:
                        hold["on"] = True
                    if not hold["on"]:
                        break
                    kw = max(AC_MIN, min(1, max(0.0, over)) * AC_MAX) * rated
                    # fan speed follows the output: low (6.3 of 7.2 m3/min, AC023CN1PBH1) at the inverter minimum, high at its
                    # maximum, in proportion between [our assumption, agreed 2026-11-05; airflows from one model 2026-11-26]
                    share = (kw / rated - AC_MIN) / (AC_MAX - AC_MIN)
                    fan = m3 * (AC_FAN_LOW + (1 - AC_FAN_LOW) * max(0.0, min(1.0, share)))
                    t_out, e_out = coil_outlet(e["temperature"], e["vapor"], kw, fan, rated)
                    f = min(1, fan * dt / n / (p["areaM2"] * PHYS["ceilingM"]))  # share of the room's air through the coil
                    w_room = w_from_e(e["vapor"])
                    e["temperature"] += (t_out - e["temperature"]) * f
                    e["vapor"] = e_from_w(w_room + (w_from_e(e_out) - w_room) * f)
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
                hood = self.hood and r == "kitchen"
                e["pm25"] += 0.6 * sf * dt * ((1 - PHYS["envelope"]["hood"]["pmCapture"]) if hood else 1)
                e["co2"] += 5 * sf * dt
                # latent heat as water vapour: g/min = W x 60 / 2450 J/g; 1 g in 1 m3 at about 22 C = 1.36 hPa
                st = PHYS["envelope"]["stove"]
                e["vapor"] += g_to_hpa(st["burnerKW"] * st["latent"] * 1000 * 60 / 2450 * dt, vol)
            if self.shower and self.shower[0] == r and ms < self.shower[1]:
                e["vapor"] += g_to_hpa(PHYS["moisture"]["showerGMin"] * dt, vol)
            for rk in self.racks:
                # laundry dries at its pace (gMin) while the air can take it; in saturated air the water stays in the
                # clothes (rk["leftG"]) and the rack dries later (2026-11-21: was dropped above saturation)
                if rk["room"] == r and rk["start"] <= ms and rk["leftG"] > 0:
                    room_g = max(0.0, (sat_vapor(e["temperature"]) - e["vapor"]) * vol / 1.36)
                    give = min(rk["gMin"] * dt, rk["leftG"], room_g)
                    e["vapor"] += g_to_hpa(give, vol)
                    rk["leftG"] -= give
            dryer_on, washer_on = running("dryer"), running("washer")
            if dryer_on:
                e["vapor"] += PHYS["moisture"]["dryer"] * sf * dt
            if washer_on:
                e["vapor"] += PHYS["moisture"]["washer"] * sf * dt
            if robot_on:
                e["pm25"] += 0.1 * sf * dt
            # vapour above saturation condenses on walls and glass and is dropped (showers: it runs down the drain)
            e["vapor"] = max(0.5, min(sat_vapor(e["temperature"]), e["vapor"]))
            e["humidity"] = rh_from_vapor(e["vapor"], e["temperature"])
            e["pm25"] = max(0, e["pm25"])
            e["co2"] = max(400, e["co2"])
            lux = out["daylight"] * PHYS["windowLight"][p["windowSize"]] * window_sun(p, out)
            if r == "balcony":
                lux = out["daylight"] * E["balcony"]["luxShare"] * window_sun(p, out)
            elif RB and r == "living_room":
                lux *= E["balcony"]["tau"]
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
