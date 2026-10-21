"""Outdoor conditions in Seoul: monthly normals shaped by a per-date weather (clear / cloudy / rain / snow),
daily PM2.5 variation, rain washout, wind, daylight and outdoor noise.
Ported line by line from smarthome-sim.html (same constants and sources); every value is fixed per date and minute
(no random numbers), so outdoor_at() gives the same numbers as the browser simulator."""
import math
from .timeutil import (DAY_MS, MIN_MS, i32, u32, js_round, day_index, ymd, hours, local_ms, month_days, utc_day_fields)

# Seoul monthly climate normals 1991-2020 (Wikipedia "Seoul" climate table): [mean daily max C, mean daily min C, mean RH %]
SEOUL_NORMALS = [
    [2.1, -5.5, 56.2], [5.1, -3.2, 54.6], [11.0, 1.9, 54.6], [17.9, 8.0, 54.8], [23.6, 13.5, 59.7], [27.6, 18.7, 65.7],
    [29.0, 22.3, 76.2], [30.0, 22.9, 73.5], [26.2, 17.7, 66.4], [20.2, 10.6, 61.8], [11.9, 3.5, 60.4], [4.2, -3.4, 57.8],
]
# Seoul outdoor PM2.5 (ug/m3), city average by month, mean of 2022-2025 (Seoul Air Quality Information, cleanair.seoul.go.kr)
SEOUL_PM25_MONTHLY = [26.75, 25.0, 25.75, 21.75, 17.5, 16.25, 14.5, 13.0, 10.0, 12.75, 19.25, 19.5]
# Seoul urban CO2 (ppm): mean of the 2023 annual averages at four stations (Seoul Research Institute of Public Health and Environment)
SEOUL_CO2_PPM = 450.9
PM25_DAILY_SIGMA = 0.55  # simulator's choice
SEOUL_LAT, SEOUL_LON = 37.57, 126.98
# Seoul 1991-2020 normals (Wikipedia "Climate of Seoul", from KMA): days with >= 1 mm, days with snow, % of possible sunshine, mm
SEOUL_PRECIP_DAYS = [3.3, 3.4, 4.7, 6.5, 6.8, 7.6, 13.3, 11.8, 6.5, 4.8, 6.4, 4.2]
SEOUL_SNOW_DAYS = [7.1, 5.1, 2.8, 0.2, 0, 0, 0, 0, 0, 0, 2.3, 6.4]
SEOUL_SUNSHINE_PCT = [52.3, 53.6, 51.0, 51.9, 48.4, 41.2, 26.8, 36.2, 47.2, 57.1, 50.2, 51.1]
SEOUL_PRECIP_MM = [16.8, 28.2, 36.9, 72.9, 103.6, 129.5, 414.4, 348.2, 141.5, 52.2, 51.1, 22.6]
# rain washing PM out (Kim et al., Seoul 1999-2008, PM10): drop = 4.83 ln(mm) + 3.385 ug/m3, as a share of 66 ug/m3
WASHOUT = dict(a=4.83, b=3.385, dryPM10=66, maxShare=0.6, recoverHours=6)
# rain noise (Kobe University 2015): 53.1 dB at 40 mm/h, +12.8 dB per 10-fold rain rate
RAIN_NOISE = dict(at40=53.1, perDecade=12.8)
FACADE_DB = dict(open=15, closed=30)  # outdoor sound through an open / shut window (simulator's choice)
# wind (m/s): KMA annual mean 2.3, September 1.9, March/April 2.7; cosine through those (simulator's choice)
WIND = dict(mean=2.3, amp=0.4, peakPos=2.5, daySigma=0.35, diurnal=0.3)
WEATHER = dict(
    sun=dict(clear=1, cloudy=0.4, rain=0.15, snow=0.2),
    swing=dict(clear=1, cloudy=0.6, rain=0.35, snow=0.35),
    sunshine=dict(clear=0.9, cloudy=0.15),
    wetRH=92, snowMaxC=2, episodeHours=[2, 8], blockHours=6, blendMin=15, windOpen=[0.5, 0.5], rainSigma=0.8,
)


def hash01(n):
    n0 = n
    n = i32(i32(n0) ^ 61) ^ (u32(n0) >> 16)
    n = i32(n)
    n = i32(n + i32(n << 3))
    n = i32(n ^ (u32(n) >> 4))
    n = i32(n * 0x27d4eb2d)
    n = i32(n ^ (u32(n) >> 15))
    return u32(n) / 4294967296


def day_gauss(d):
    u1 = hash01(d * 2 + 1) or 1e-9
    u2 = hash01(d * 2 + 2)
    return math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def raw_day_factor(d):
    z = (day_gauss(d - 1) + 2 * day_gauss(d) + day_gauss(d + 1)) / math.sqrt(6)
    return math.exp(PM25_DAILY_SIGMA * z - PM25_DAILY_SIGMA ** 2 / 2)


_month_norm = {}


def day_factor(d):
    y, m, _ = utc_day_fields(d)
    key = y * 12 + m
    if key not in _month_norm:
        first = _utc_day(y, m, 1)  # Date.UTC(y, m, 1) / 86400000
        n = month_days(y, m)
        _month_norm[key] = sum(raw_day_factor(first + i) for i in range(n)) / n
    return raw_day_factor(d) / _month_norm[key]


def _utc_day(y, m0, d):
    from .timeutil import _dt, _EPOCH_ORD
    y += m0 // 12
    m0 %= 12
    return _dt.date(y, m0 + 1, 1).toordinal() - _EPOCH_ORD + d - 1


def pm_factor_at(ms):
    x = day_index(ms) + hours(ms) / 24 - 0.5
    i = math.floor(x)
    f = x - i
    return day_factor(i) * (1 - f) + day_factor(i + 1) * f


def _month_pos(ms):
    y, m, d, _ = ymd(day_index(ms))
    return m + (d - 0.5) / month_days(y, m) - 0.5


def season_at(ms):
    pos = _month_pos(ms)
    i = math.floor(pos)
    f = pos - i
    ia, ib = (i + 12) % 12, (i + 13) % 12
    a = SEOUL_NORMALS[ia] + [SEOUL_PM25_MONTHLY[ia]]
    b = SEOUL_NORMALS[ib] + [SEOUL_PM25_MONTHLY[ib]]
    return [v + (b[k] - v) * f for k, v in enumerate(a)]


def sun_at(ms):
    y = ymd(day_index(ms))[0]
    start = local_ms(y, 0, 0)
    n = math.floor((ms - start) / DAY_MS)
    decl = 23.44 * math.sin(2 * math.pi * (284 + n) / 365) * math.pi / 180
    lat = SEOUL_LAT * math.pi / 180
    day_len = 2 * math.acos(-math.tan(lat) * math.tan(decl)) * 180 / math.pi / 15
    noon = 12 + (135 - SEOUL_LON) / 15
    return noon - day_len / 2, noon + day_len / 2, day_len, math.sin(math.pi / 2 - lat + decl)


def month_blend(ms, table):
    pos = _month_pos(ms)
    i = math.floor(pos)
    f = pos - i
    return table[(i + 12) % 12] * (1 - f) + table[(i + 13) % 12] * f


def _month_days_ms(ms):
    y, m, _, _ = ymd(day_index(ms))
    return month_days(y, m)


def day_noon(d):
    y, m, dd = utc_day_fields(d)
    return local_ms(y, m, dd, 12)


def w_hash(d, k):
    return hash01(5000000 + d * 16 + k)


def pair_uniform(a, b):
    x = (a + b) / 2
    return 2 * x * x if x <= 0.5 else 1 - 2 * (1 - x) ** 2


def cloudy_share(ms):
    n = _month_days_ms(ms)
    wet = min(1, max(month_blend(ms, SEOUL_PRECIP_DAYS), month_blend(ms, SEOUL_SNOW_DAYS)) / n)
    mean_spell = 1.5 * (WEATHER["episodeHours"][0] + WEATHER["episodeHours"][1]) / 2
    wet_sun = WEATHER["sunshine"]["cloudy"] * (1 - mean_spell / 24)
    S = month_blend(ms, SEOUL_SUNSHINE_PCT) / 100
    dry = (S - wet * wet_sun) / (1 - wet)
    return min(1, max(0, (WEATHER["sunshine"]["clear"] - dry) / (WEATHER["sunshine"]["clear"] - WEATHER["sunshine"]["cloudy"])))


def _mean_spell_h():
    s = n = 0
    a, b = WEATHER["episodeHours"]
    for i in range(240):
        for j in range(61):
            s += min(24 - (i + 0.5) / 10, a + (b - a) * j / 60)
            n += 1
    return s / n


MEAN_SPELL_H = _mean_spell_h()


def wet_chance(ms):
    return min(1, max(month_blend(ms, SEOUL_PRECIP_DAYS), month_blend(ms, SEOUL_SNOW_DAYS)) / _month_days_ms(ms))


_wet_days = {}


def expected_wet_days(ms):
    y, m, _, _ = ymd(day_index(ms))
    key = y * 12 + m
    if key not in _wet_days:
        _wet_days[key] = sum(wet_chance(local_ms(y, m, d, 12)) for d in range(1, month_days(y, m) + 1))
    return _wet_days[key]


_day_weather = {}


def day_weather(d):
    w = _day_weather.get(d)
    if w is not None:
        return w
    noon = day_noon(d)
    precip = month_blend(noon, SEOUL_PRECIP_DAYS)
    snow = month_blend(noon, SEOUL_SNOW_DAYS)
    events = max(precip, snow)
    wet = w_hash(d, 0) < wet_chance(noon)
    kind = "snow" if wet and w_hash(d, 1) < (snow / events if events else 0) else "rain"
    spells = []
    if wet:
        c = 1 if w_hash(d, 2) < 0.5 else 2
        for i in range(c):
            start = 24 * w_hash(d, 3 + 2 * i)
            ln = WEATHER["episodeHours"][0] + (WEATHER["episodeHours"][1] - WEATHER["episodeHours"][0]) * w_hash(d, 4 + 2 * i)
            u1 = w_hash(d, 20 + 2 * i) or 1e-9
            z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * w_hash(d, 21 + 2 * i))
            mean_rate = SEOUL_PRECIP_MM[ymd(day_index(noon))[1]] / (expected_wet_days(noon) * 1.5 * MEAN_SPELL_H)
            spells.append((start, min(24, start + ln), mean_rate * math.exp(WEATHER["rainSigma"] * z - WEATHER["rainSigma"] ** 2 / 2)))
    pc = cloudy_share(noon)
    u_day = w_hash(d, 8)
    blocks = [wet or pair_uniform(u_day, w_hash(d, 9 + b)) < pc for b in range(24 // WEATHER["blockHours"])]
    u1 = w_hash(d, 14) or 1e-9
    z = math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * w_hash(d, 15))
    w = dict(wet=wet, kind=kind, spells=spells, blocks=blocks, wind=math.exp(WIND["daySigma"] * z - WIND["daySigma"] ** 2 / 2))
    if len(_day_weather) > 4000:
        _day_weather.clear()
    _day_weather[d] = w
    return w


def base_outdoor(ms):
    h = hours(ms)
    c = math.cos(2 * math.pi * (h - 15) / 24)
    tmax, tmin, rh, pm25 = season_at(ms)
    return dict(h=h, c=c, tmax=tmax, tmin=tmin, rh=rh, pm25=pm25, mean=(tmax + tmin) / 2, half=(tmax - tmin) / 2,
                temperature=(tmax + tmin) / 2 + (tmax - tmin) / 2 * c, humidity=rh - 12 * c)


def weather_state_at(ms):
    d = day_index(ms)
    h = hours(ms)
    w = day_weather(d)
    if any(a <= h < b for a, b, _ in w["spells"]):
        return "rain" if w["kind"] == "snow" and base_outdoor(ms)["temperature"] > WEATHER["snowMaxC"] else w["kind"]
    return "cloudy" if w["blocks"][math.floor(h / WEATHER["blockHours"])] else "clear"


def precip_at(ms):
    h = hours(ms)
    for a, b, rate in day_weather(day_index(ms))["spells"]:
        if a <= h < b:
            return rate
    return 0


def washout_at(ms):
    d = day_index(ms)
    h = hours(ms)
    best = 0
    for dd, hh in ((d, h), (d - 1, h + 24)):
        for a, b, rate in day_weather(dd)["spells"]:
            if hh < a:
                continue
            mm = rate * (min(hh, b) - a)
            if mm < 1e-3:
                continue
            share = min(WASHOUT["maxShare"], max(0, (WASHOUT["a"] * math.log(mm) + WASHOUT["b"]) / WASHOUT["dryPM10"]))
            if hh > b:
                share *= math.exp(-(hh - b) / WASHOUT["recoverHours"])
            best = max(best, share)
    return best


_fx = {}


def weather_fx(ms):
    key = ms // MIN_MS
    fx = _fx.get(key)
    if fx is not None:
        return fx
    sun = swing = wet = 0
    for k in (-3, -2, -1, 0, 1, 2, 3):
        st = weather_state_at(key * MIN_MS + int(k * WEATHER["blendMin"] / 3 * MIN_MS))
        sun += WEATHER["sun"][st]
        swing += WEATHER["swing"][st]
        wet += 1 if st in ("rain", "snow") else 0
    fx = dict(sun=sun / 7, swing=swing / 7, wet=wet / 7)
    if len(_fx) > 20000:
        _fx.clear()
    _fx[key] = fx
    return fx


_norm = {}


def weather_norm_for(ms):
    y, m, _, _ = ymd(day_index(ms))
    key = y * 12 + m
    if key in _norm:
        return _norm[key]
    swing = n = pm_keep = 0
    samples = []
    t, end = local_ms(y, m, 1), local_ms(y, m + 1, 1)
    while t < end:
        fx = weather_fx(t)
        swing += fx["swing"]
        n += 1
        samples.append((base_outdoor(t), fx))
        pm_keep += 1 - washout_at(t)
        t += 30 * MIN_MS
    sw = 1 / (swing / n)
    t_base = t_w = h_base = h_w = dry = 0
    for b, fx in samples:
        t_base += b["temperature"]
        t_w += b["mean"] + b["half"] * b["c"] * fx["swing"] * sw
        h_base += b["humidity"]
        h_w += b["humidity"] + (WEATHER["wetRH"] - b["humidity"]) * fx["wet"]
        dry += 1 - fx["wet"]
    norm = dict(swing=sw, tShift=(t_base - t_w) / n, hDryShift=(h_base - h_w) / dry if dry else 0, pmScale=n / pm_keep)
    _norm[key] = norm
    return norm


def db_sum(levels):
    return 10 * math.log10(sum(10 ** (L / 10) for L in levels))


_out = {}


def outdoor_at(ms):
    """outdoor conditions at a moment (the same for every second of a minute)"""
    key = ms // MIN_MS
    o = _out.get(key)
    if o is not None:
        return o
    ms = key * MIN_MS
    b = base_outdoor(ms)
    h = b["h"]
    rise, sset, day_len, noon_h = sun_at(ms)
    fx = weather_fx(ms)
    nm = weather_norm_for(ms)
    state = weather_state_at(ms)
    dw = day_weather(day_index(ms))
    temperature = b["mean"] + b["half"] * b["c"] * fx["swing"] * nm["swing"] + nm["tShift"]
    humidity = min(100, max(10, b["humidity"] + (WEATHER["wetRH"] - b["humidity"]) * fx["wet"] + nm["hDryShift"] * (1 - fx["wet"])))
    wind = max(0, (WIND["mean"] + WIND["amp"] * math.cos(2 * math.pi * (_month_pos(ms) - WIND["peakPos"]) / 12)) * dw["wind"] * (1 + WIND["diurnal"] * b["c"]))
    precip = precip_at(ms)
    rain_db = RAIN_NOISE["at40"] + RAIN_NOISE["perDecade"] * math.log10(precip / 40) if state == "rain" and precip > 0 else None
    base_noise = 50 if 7 <= h < 22 else 38
    up = rise < h < sset
    o = dict(temperature=temperature, humidity=humidity,
             pm25=b["pm25"] * pm_factor_at(ms) * nm["pmScale"] * (1 - washout_at(ms)), co2=SEOUL_CO2_PPM,
             daylight=25000 * noon_h * math.sin(math.pi * (h - rise) / day_len) * fx["sun"] if up else 0,
             noise=base_noise if rain_db is None else db_sum([base_noise, rain_db]), meanTemperature=b["mean"] + nm["tShift"],
             weather=state, windSpeed=js_round(wind * 10) / 10, precipitation=js_round(precip * 10) / 10,
             sunAz=90 + 180 * (h - rise) / day_len if up else None)
    if len(_out) > 200000:
        _out.clear()
    _out[key] = o
    return o
