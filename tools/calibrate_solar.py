#!/usr/bin/env python3
"""Fit weather.SOLAR_CAL so that the monthly mean daily horizontal irradiation of solar_at() equals SEOUL_GHI_KWH
(Jo et al. 2011, Seoul 1982-2009). Averages over the years given (the weather is fixed per date), 10-minute steps,
three passes because SOLAR_CAL is blended between months. Prints the table to paste into weather.py.

usage: python3 tools/calibrate_solar.py [first_year last_year]"""
import sys, os, calendar
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from smarthome_sim import weather as W
from smarthome_sim.timeutil import local_ms, MIN_MS

y0, y1 = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (2024, 2028)


def monthly():
    W._sol.clear()
    tot = [0.0] * 12; days = [0] * 12
    for y in range(y0, y1 + 1):
        for m in range(12):
            days[m] += calendar.monthrange(y, m + 1)[1]
            t, end = local_ms(y, m, 1), local_ms(y, m + 1, 1)
            while t < end:
                tot[m] += W.solar_at(t)["ghi"] * 10 / 60 / 1000  # kWh/m2 in 10 min
                t += 10 * MIN_MS
    return [tot[m] / days[m] for m in range(12)]


cal = [1.0] * 12
for _ in range(3):
    W.SOLAR_CAL[:] = cal
    got = monthly()
    cal = [round(cal[m] * W.SEOUL_GHI_KWH[m] / got[m], 4) for m in range(12)]
W.SOLAR_CAL[:] = cal
got = monthly()
print("SOLAR_CAL =", cal)
print("model kWh/m2/day:", [round(g, 2) for g in got])
print("measured:        ", W.SEOUL_GHI_KWH)
