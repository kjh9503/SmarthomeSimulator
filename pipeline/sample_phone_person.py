#!/usr/bin/env python3
"""Draw one person's phone-use values from population distributions and write them into an agent profile.

usage: python3 pipeline/sample_phone_person.py profiles/063.json [--level light|medium|heavy] [--seed N] [--out path]

The LLM writes the phone-use rules (phone.useApps: which apps, in which order, at which places and times, their
relative lengths) and the person's level (`phoneUseLevel`: light / medium / heavy). This script then:
1. draws the person's values; the level picks the lower, middle or upper third of each usage distribution:
   - unlocks per hour: lognormal, median 1.71, IQR 1.10-2.49 (sigma 0.606)        Winbush et al. 2025, PNAS
   - app screen minutes per hour: lognormal, median 15.16, IQR 10.8-20.6 (sigma 0.479)   same
   (a day = 24 x the hourly value, as in that paper)
   - share of uses that are quick checks: uniform 0.25-0.55            assumption; mean 0.40 near 41% of sessions
                                                                         under 40 s (arXiv 2609.24477, 2024 data)
   - manual screen-off chance: beta(4.5, 0.5), mean 0.9                 assumption; people differ (Hintze et al. 2014)
   - glances per day: lognormal, median 22, sigma 0.90 (mean 33)        Hintze et al. 2014
   - screen time-out: 15 s 10%, 30 s 50%, 60 s 20%, 120 s 10%, 300 s 7%, 600 s 3%   assumption; default 30 s (Samsung)
   - day-to-day sigma: uniform 0.15-0.55                                 Appiah et al. 2026 (unlock CV 16-60%)
2. rescales the phone-use rules so that the person reaches these values: every rule's perHour by one factor (more
   firings than uses, because a firing while a use is still running is skipped), every app time by one factor.
3. writes phoneHabits and a phonePerson record (drawn values, factors, the rules' original values, sources).
Running it again on the same profile starts again from the original values kept in phonePerson.template.
"""
import argparse, json, math, random, statistics

LEVELS = {"light": (0.0, 1 / 3), "medium": (1 / 3, 2 / 3), "heavy": (2 / 3, 0.97)}
UNLOCKS = dict(median=1.71, sigma=math.log(2.49 / 1.10) / 1.349)
MINUTES = dict(median=15.16, sigma=math.log(20.6 / 10.8) / 1.349)
GLANCES = dict(median=22, sigma=math.sqrt(2 * math.log(33 / 22)))
TIMEOUTS = ([15, 30, 60, 120, 300, 600], [10, 50, 20, 10, 7, 3])
CHECK_SECONDS = dict(median=10, sigma=0.8)  # assumption, checked against "41% of sessions under 40 s"
WAKING_MIN = 980                             # about 16.3 waking hours
MESSENGERS = ("com.kakao.talk", "com.samsung.android.messaging")
SOURCES = {
    "unlocksPerHour, appMinutesPerHour": "Winbush et al. 2025, PNAS 122(43) e2427311122, 10,099 US adults, Android",
    "checkShare": "assumption: uniform 0.25-0.55; 41% of sessions under 40 s in arXiv 2609.24477 (Denmark, 2024)",
    "manualScreenOff": "assumption: beta(4.5, 0.5); Hintze et al. 2014: some always switch off by hand, some almost never",
    "glancesPerDay": "Hintze et al. 2014 (UbiComp): locked sessions median 22, mean 33 a day",
    "screenTimeoutSeconds": "assumption; Galaxy default 30 s (Samsung support)",
    "dailySigma": "Appiah et al. 2026 (J Technol Behav Sci): within-person CV of daily unlocks mostly > 25%, examples 16% and 60%; StudentLife 2013",
}


def lognormal_at(d, u):
    return d["median"] * math.exp(d["sigma"] * statistics.NormalDist().inv_cdf(u))


def mean_ln(d):
    return d["median"] * math.exp(d["sigma"] ** 2 / 2)


def window_hours(w):
    f = int(w["from"][:2]) * 60 + int(w["from"][3:])
    t = int(w["to"][:2]) * 60 + int(w["to"][3:])
    return ((t - f) % 1440 or 1440) / 60


def day_share(days):
    if not days or days == "all":
        return 1.0
    if days == "weekdays":
        return 5 / 7
    if days == "weekends":
        return 2 / 7
    return len(days) / 7


def capped_mean_ln(d, scale=1.0):
    """mean of min(X, cap) for X lognormal(median * scale, sigma); cap = d['max'] or 3600 s, as the engine cuts it"""
    mu, s, c = math.log(d["median"] * scale), d["sigma"], float(d.get("max", 3600))
    if s <= 0:
        return min(c, math.exp(mu))
    N = statistics.NormalDist()
    return math.exp(mu + s * s / 2) * N.cdf((math.log(c) - mu - s * s) / s) + c * (1 - N.cdf((math.log(c) - mu) / s))


def expected_use_seconds(args, scale=1.0):
    """mean seconds of one full (non-check) use of a phone.useApps step, with every app time scaled by `scale`"""
    secs = args.get("seconds") or {}
    dflt = secs.get("default") or dict(median=30, sigma=1.5)
    m = lambda p: capped_mean_ln(secs.get(p) or dflt, scale)
    wmean = lambda w: sum(x * m(p) for p, x in w.items()) / sum(w.values())
    first = args["first"]
    nxt = args.get("next") or first
    c = float(args.get("continue", 0.32))
    cap = int(args.get("maxApps", 15))
    n_apps = (1 - c ** cap) / (1 - c)
    return wmean(first) + (n_apps - 1) * wmean(nxt)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("profile")
    ap.add_argument("--level", choices=list(LEVELS))
    ap.add_argument("--seed", type=int)
    ap.add_argument("--out")
    o = ap.parse_args()
    prof = json.load(open(o.profile, encoding="utf-8"))
    level = o.level or prof.get("phoneUseLevel") or "medium"
    seed = o.seed if o.seed is not None else prof["simulation"]["seed"]
    rnd = random.Random(seed * 31 + 101)

    rules = [b for b in prof["behaviours"] if any(a["do"] == "phone.useApps" for a in b["actions"]) and b["trigger"]["kind"] == "rate"]
    if not rules:
        raise SystemExit("no rate rule with phone.useApps in the profile")
    person = prof.get("phonePerson") or {}
    template = person.get("template") or {b["id"]: dict(perHour=b["trigger"]["perHour"],
                                                        seconds=[a["args"].get("seconds") for a in b["actions"] if a["do"] == "phone.useApps"])
                                          for b in rules}
    for b in rules:  # start from the original values
        b["trigger"]["perHour"] = template[b["id"]]["perHour"]
        for a, s in zip([a for a in b["actions"] if a["do"] == "phone.useApps"], template[b["id"]]["seconds"]):
            a["args"]["seconds"] = json.loads(json.dumps(s))

    lo, hi = LEVELS[level]
    band = lambda: lo + (hi - lo) * rnd.random()
    uph = lognormal_at(UNLOCKS, min(0.97, max(0.01, band())))
    mph = lognormal_at(MINUTES, min(0.97, max(0.01, band())))
    U, M = uph * 24, min(mph * 24, 0.8 * WAKING_MIN)
    share = 0.25 + 0.30 * rnd.random()
    manual = rnd.betavariate(4.5, 0.5)
    glances = max(3.0, min(150.0, lognormal_at(GLANCES, max(0.01, min(0.99, rnd.random())))))
    timeout = rnd.choices(*TIMEOUTS)[0]
    dsig = 0.15 + 0.40 * rnd.random()

    # checks: one app, a few seconds; the rule's own check.first if the LLM wrote one, else mostly the messenger
    mean_check = mean_ln(CHECK_SECONDS)
    fires, e_full = {}, {}
    for b in rules:
        tr = b["trigger"]
        fires[b["id"]] = tr["perHour"] * window_hours(tr["window"]) * day_share(tr.get("days"))
        for a in b["actions"]:
            if a["do"] != "phone.useApps":
                continue
            args = a["args"]
            ck = args.get("check") or {}
            if not ck.get("first"):
                ck["first"] = {p: (8 if p in MESSENGERS else 0.25 * w) for p, w in args["first"].items()}
                if not any(p in MESSENGERS for p in args["first"]):
                    ck["first"]["com.kakao.talk"] = 8
            ck["share"] = round(share, 3)
            ck.setdefault("seconds", dict(CHECK_SECONDS))
            args["check"] = ck
            e_full[b["id"]] = args
    f0 = sum(fires.values())
    e_avg = lambda scale: sum(fires[k] * expected_use_seconds(e_full[k], scale) for k in fires) / f0
    full_target = max(10.0, (M * 60 - U * share * mean_check) / (U * (1 - share)))
    lo_g, hi_g = 0.01, 100.0  # the capped mean grows with the scale: find the scale that reaches the target
    for _ in range(80):
        mid = math.sqrt(lo_g * hi_g)
        lo_g, hi_g = (mid, hi_g) if e_avg(mid) < full_target else (lo_g, mid)
    g = math.sqrt(lo_g * hi_g)
    if e_avg(g) < 0.98 * full_target:
        print(f"warning: app time can reach only {e_avg(g):.0f} of {full_target:.0f} s per use (per-app cap)")
    busy = min(0.85, M / WAKING_MIN)
    k = (U / (1 - busy)) / f0
    for b in rules:
        b["trigger"]["perHour"] = round(b["trigger"]["perHour"] * k, 3)
        b["maxPerDay"] = max(b.get("maxPerDay", 1), int(math.ceil(b["trigger"]["perHour"] * window_hours(b["trigger"]["window"]) * 2)))
        for a in b["actions"]:
            if a["do"] == "phone.useApps":
                for d in a["args"]["seconds"].values():
                    d["median"] = round(d["median"] * g, 1)

    prof["phoneUseLevel"] = level
    prof["phoneHabits"] = dict(screenTimeoutSeconds=timeout, manualScreenOff=round(manual, 3), glancesPerDay=round(glances, 1),
                               dailySigma=round(dsig, 3))
    prof["phonePerson"] = dict(
        level=level, seed=seed,
        drawn=dict(unlocksPerHour=round(uph, 3), unlocksPerDay=round(U, 1), appMinutesPerHour=round(mph, 2), appMinutesPerDay=round(M, 1),
                   checkShare=round(share, 3), manualScreenOff=round(manual, 3), glancesPerDay=round(glances, 1),
                   screenTimeoutSeconds=timeout, dailySigma=round(dsig, 3)),
        factors=dict(rate=round(k, 4), seconds=round(g, 4), expectedBusyShare=round(busy, 3)),
        template=template, sources=SOURCES)
    out = o.out or o.profile
    with open(out, "w", encoding="utf-8") as f:
        json.dump(prof, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"{out}: level {level}, {U:.0f} uses/day ({share:.0%} checks), {M:.0f} app min/day, glances {glances:.0f}, "
          f"time-out {timeout} s, manual off {manual:.2f}, daily sigma {dsig:.2f}; rate x{k:.2f}, app time x{g:.2f}")


if __name__ == "__main__":
    main()
