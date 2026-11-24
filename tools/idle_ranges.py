"""idleActivityRanges written in the LLM's role for 063 and the TEST profiles (2026-11-24; no data behind them)."""


def r(a, b):
    return {"min": a, "max": b}


def act(m, d, e, n, minutes, rooms, **extra):
    """weights per band (morning, day, evening, night) as (min, max), minutes as (min, max)"""
    out = {"weights": {"morning": r(*m), "day": r(*d), "evening": r(*e), "night": r(*n)}, "minutes": r(*minutes), "rooms": rooms}
    for k, v in extra.items():
        out[k] = r(*v) if isinstance(v, tuple) else v
    return out


Z = (0, 0)
COMMON = dict(  # every persona goes to the toilet, has a snack, tidies up, rests
    toilet=act((0.15, 0.25), (0.1, 0.2), (0.1, 0.2), (0.1, 0.2), (3, 8), ["bathroom"]),
    snack=act((0.05, 0.1), (0.05, 0.15), (0.05, 0.15), (0.05, 0.1), (5, 15), ["kitchen", "dining_room"]),
    tidying=act((0.02, 0.06), (0.03, 0.08), (0.02, 0.06), Z, (10, 25), ["bedroom", "living_room"]),
    rest=act((0.05, 0.15), (0.05, 0.15), (0.05, 0.15), (0.05, 0.1), (15, 40), ["bedroom", "living_room"]),
    folding=act(Z, (0.02, 0.05), (0.02, 0.05), Z, (10, 20), ["bedroom", "living_room"]),
)

IDLE = {
    "063": dict(COMMON,  # student, heavy phone
        video=act((0.05, 0.1), (0.15, 0.25), (0.15, 0.25), (0.2, 0.3), (20, 50), ["bedroom", "living_room"],
                  apps={"com.google.android.youtube": 3, "com.netflix.mediaclient": 1}),
        game=act(Z, (0.05, 0.1), (0.05, 0.1), (0.05, 0.15), (15, 40), ["bedroom"], apps={"com.supercell.brawlstars": 1}),
        study=act(Z, (0.1, 0.2), (0.05, 0.15), (0.02, 0.05), (40, 90), ["study_room"]),
        tv=act(Z, (0.03, 0.08), (0.05, 0.12), (0.02, 0.05), (40, 90), ["living_room"]),
        music=act((0.02, 0.05), (0.03, 0.08), (0.03, 0.08), (0.02, 0.05), (15, 40), ["bedroom", "study_room"]),
        call=act(Z, (0.02, 0.05), (0.03, 0.06), (0.01, 0.03), (5, 20), ["bedroom", "living_room"]),
        shopping=act(Z, (0.02, 0.04), (0.02, 0.05), (0.02, 0.04), (5, 15), ["bedroom"], apps={"com.coupang.mobile": 1}),
        dishes=act(Z, (0.02, 0.05), (0.03, 0.06), Z, (8, 15), ["kitchen"], dishwasherShare=(0, 0)),
        cleaning=act(Z, (0.02, 0.05), (0.01, 0.03), Z, (15, 30), ["living_room", "bedroom", "kitchen"], robotShare=(0, 0)),
        nap=act(Z, (0.02, 0.06), Z, Z, (20, 60), ["bedroom"]),
        plants=act((0.0, 0.02), (0.0, 0.02), Z, Z, (5, 10), ["balcony"])),
    "test_office": dict(COMMON,
        tv=act((0.02, 0.05), (0.1, 0.2), (0.25, 0.4), (0.05, 0.1), (60, 120), ["living_room"]),
        video=act((0.03, 0.06), (0.05, 0.1), (0.05, 0.12), (0.1, 0.2), (20, 50), ["bedroom"],
                  apps={"com.netflix.mediaclient": 2, "com.google.android.youtube": 2}),
        workout=act(Z, (0.02, 0.05), (0.03, 0.06), Z, (20, 40), ["living_room"], kinds={"StrengthTraining": 2, "Stretching": 1}),
        music=act((0.03, 0.06), (0.03, 0.06), (0.02, 0.05), Z, (15, 40), ["kitchen", "living_room"]),
        call=act(Z, (0.02, 0.05), (0.03, 0.06), (0.01, 0.03), (5, 20), ["living_room", "bedroom"]),
        shopping=act(Z, (0.02, 0.05), (0.03, 0.06), (0.02, 0.04), (5, 15), ["living_room", "bedroom"],
                     apps={"com.coupang.mobile": 3, "com.kbstar.kbbank": 1}),
        dishes=act(Z, (0.03, 0.06), (0.04, 0.08), Z, (10, 20), ["kitchen"], dishwasherShare=(0, 0)),
        cleaning=act(Z, (0.04, 0.08), (0.01, 0.03), Z, (20, 40), ["living_room", "bedroom", "kitchen"], robotShare=(0, 0)),
        nap=act(Z, (0.03, 0.08), Z, Z, (30, 90), ["bedroom", "living_room"]),
        reading=act(Z, (0.02, 0.05), (0.02, 0.05), (0.02, 0.05), (20, 40), ["bedroom"])),
    "test_remote": dict(COMMON,
        reading=act((0.02, 0.05), (0.03, 0.08), (0.08, 0.15), (0.05, 0.1), (25, 60), ["living_room", "bedroom"]),
        video=act(Z, (0.05, 0.1), (0.1, 0.2), (0.1, 0.2), (25, 60), ["living_room", "bedroom"],
                  apps={"com.netflix.mediaclient": 3, "com.google.android.youtube": 1}),
        tv=act(Z, (0.03, 0.06), (0.05, 0.1), (0.02, 0.05), (40, 90), ["living_room"]),
        workout=act((0.05, 0.1), (0.02, 0.05), (0.03, 0.06), Z, (20, 40), ["living_room"], kinds={"Yoga": 2, "Stretching": 1}),
        music=act((0.03, 0.06), (0.05, 0.1), (0.03, 0.06), Z, (20, 60), ["kitchen", "study_room", "living_room"]),
        call=act(Z, (0.03, 0.06), (0.03, 0.06), Z, (5, 25), ["living_room", "balcony", "study_room"]),
        shopping=act(Z, (0.02, 0.05), (0.02, 0.05), (0.01, 0.03), (5, 15), ["living_room"], apps={"com.coupang.mobile": 2, "com.kbstar.kbbank": 1}),
        dishes=act((0.02, 0.05), (0.03, 0.06), (0.04, 0.08), Z, (8, 15), ["kitchen"], dishwasherShare=(0.6, 0.9)),
        cleaning=act((0.02, 0.04), (0.03, 0.06), (0.01, 0.02), Z, (15, 30), ["living_room", "bedroom", "kitchen", "study_room"],
                     robotShare=(0.6, 0.9)),
        plants=act((0.02, 0.04), (0.02, 0.04), Z, Z, (5, 15), ["balcony"]),
        nap=act(Z, (0.01, 0.03), Z, Z, (15, 30), ["bedroom"])),
    "test_retiree": dict(COMMON,
        tv=act((0.15, 0.25), (0.25, 0.4), (0.3, 0.45), (0.05, 0.1), (60, 120), ["living_room"]),
        reading=act((0.05, 0.1), (0.05, 0.1), (0.03, 0.06), (0.02, 0.05), (20, 50), ["living_room", "study_room"]),
        plants=act((0.04, 0.08), (0.04, 0.08), Z, Z, (10, 25), ["balcony"]),
        nap=act(Z, (0.08, 0.15), (0.02, 0.05), Z, (30, 75), ["living_room", "bedroom"]),
        call=act((0.02, 0.04), (0.03, 0.06), (0.03, 0.06), Z, (10, 30), ["living_room"]),
        dishes=act((0.03, 0.06), (0.04, 0.08), (0.04, 0.08), Z, (10, 20), ["kitchen"], dishwasherShare=(0, 0)),
        cleaning=act((0.03, 0.06), (0.03, 0.06), Z, Z, (20, 45), ["living_room", "bedroom", "kitchen", "dining_room"], robotShare=(0, 0)),
        workout=act((0.03, 0.06), (0.01, 0.03), Z, Z, (10, 25), ["living_room"], kinds={"Stretching": 1}),
        music=act((0.02, 0.05), (0.02, 0.05), Z, Z, (20, 60), ["living_room", "kitchen"])),
}
