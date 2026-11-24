#!/usr/bin/env python3
"""Check a simulated log for things a real home has to do in order (agreed 2026-11-23).

usage: python3 tools/check_order.py <phone_log.jsonl> <houseType: 2room|3room|4room> [--examples N]

Rules (each counted separately; the log is read in file order, lines of the same second in file order):
  M1  the person moves only between joined rooms (smarthome_sim/house.py CONNECTIONS, plus living room - balcony):
      consecutive occupancy 'present' rooms must be joined; a jump means they crossed rooms without being sensed.
  M2  the person stays a moment in a room they walk into: 'present' in a room and 'present' in the next room in the
      same second (0 s) is not possible on foot. Counted per room.
  M3  balcony: entering or leaving it while the living room window (the sliding door) is logged closed.
  M4  in one room at a time: two rooms 'present' together past the second they changed in.
  M5  at home and awake the person is somewhere: Home-WiFi connected, not in a SLEEP interval, no room 'present' for
      more than 10 minutes.
  M6  coming home: the first room 'present' after Home-WiFi reconnects is the entryway, after the front door opened.
  M7  the front door opens with the person in the entryway (or outside).
  M8  asleep (HEALTH SLEEP startTime..endTime): no move between rooms and no physical action; asleep in a bedroom or on the living-room sofa.
  M9  walking takes time: a stay of 1 s in a room before the next (0 s is M2).
  M10 moving between rooms takes steps: an hour with moves at home but 0 steps (HEALTH HOURLY).
  M11 at home (Home-WiFi connected) the phone does not report IN_VEHICLE / ON_BICYCLE / RUNNING.
  L0  the log is in time order.
  P1  a physical action (actor channel 'physical') on a device happens in the device's room: the last 'present' room
      must be the device's room. Entry door / lock: entryway.
  H1  away (Home-WiFi disconnected after leaving): no physical action and no occupancy 'present' at home.
  D1  front door: unlocked before it opens; closed before it locks.
  A1  dryer: started only after a washer cycle finished and not yet dried; washer: not started while running.
  F1  phone: an app comes to the foreground only while the screen is on.
  F4  one app in the foreground at a time: another app comes to the foreground only after the last one went back.
  F3  an app in the foreground goes to the background at the latest when the screen turns off.
  F2  a SmartThings command from the app (actor channel 'mobile_app') only while the SmartThings app is in the foreground.
Not checkable from the log alone: doors without sensors, hanging or taking in laundry.
"""
import argparse, collections, datetime as dt, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from smarthome_sim.house import CONNECTIONS

K = dt.timezone(dt.timedelta(hours=9))
ST_APP = "com.samsung.android.oneconnect"


def hhmmss(ms):
    return dt.datetime.fromtimestamp(ms / 1000, K).strftime("%m-%d %H:%M:%S")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("houseType")
    ap.add_argument("--examples", type=int, default=3)
    ap.add_argument("--rule", help="print every example of this rule")
    o = ap.parse_args()
    adj = collections.defaultdict(set)
    for c in CONNECTIONS[o.houseType] + [("door", "living_room", "balcony")]:
        adj[c[1]].add(c[2]); adj[c[2]].add(c[1])
    count, ex = collections.Counter(), collections.defaultdict(list)
    detail = collections.defaultdict(collections.Counter)

    def bad(rule, t, text, key=None):
        count[rule] += 1
        if key is not None:
            detail[rule][key] += 1
        if len(ex[rule]) < o.examples or rule == o.rule:
            ex[rule].append(f"{hhmmss(t)} {text}")

    sleeps, steps = [], {}
    for line in open(o.log, encoding="utf-8"):  # first pass: sleep intervals and hourly steps
        j = json.loads(line)
        if j["type"] == "HEALTH":
            p = j["payload"]
            if j["source"] == "SLEEP":
                sleeps.append((p["startTime"], p["endTime"]))
            elif j["source"] == "HOURLY":
                steps[p["startTime"]] = p["steps"]
    sleeps.sort()
    si = 0

    def asleep_at(t):
        nonlocal si
        while si < len(sleeps) and sleeps[si][1] < t:
            si += 1
        return si < len(sleeps) and sleeps[si][0] <= t <= sleeps[si][1]

    moves_in_hour = collections.Counter()
    present, last_t, multi_flagged = set(), None, False
    empty_since, empty_flagged = None, False
    came_home, door_open_since_home = False, False
    sj = 0
    room, room_t = None, None
    living_win = None  # None: the living room window writes no line
    away = False
    lock, door = None, None
    washer_run, to_dry, dryer_run = False, 0, False
    screen, fg = None, set()
    for line in open(o.log, encoding="utf-8"):
        j = json.loads(line)
        t, typ, p = j["timestamp"], j["type"], j.get("payload", {})
        if last_t is not None and t < last_t:
            bad("L0", t, f"{typ} {j.get('title')} after a line at {hhmmss(last_t)}")
        if last_t is not None and t > last_t:
            if len(present) > 1 and not multi_flagged:
                bad("M4", last_t, f"present in {', '.join(sorted(present))}")
                multi_flagged = True
            if not away and not present and empty_since is not None and not empty_flagged \
                    and t - empty_since > 600000 and not asleep_at(t):
                bad("M5", empty_since, f"home, awake, in no room until {hhmmss(t)}")
                empty_flagged = True
        last_t = max(last_t or t, t)
        while sj < len(sleeps) and sleeps[sj][0] <= t:  # the room 'present' when a sleep starts
            if room is not None and room not in ("room1", "room2", "room3", "room4", "living_room"):  # the sofa is allowed
                bad("M8", sleeps[sj][0], f"falls asleep in {room}", key=f"asleep in {room}")
            sj += 1
        if typ == "CONNECTIVITY" and p.get("ssid") == "Home-WiFi":
            was_away = away
            away = p.get("state") != "CONNECTED"
            if was_away and not away:
                came_home, door_open_since_home = True, False
                empty_since, empty_flagged = t, False
            continue
        if typ == "ACTIVITY" and p.get("transition") == "ENTER" and p.get("activity") in ("IN_VEHICLE", "ON_BICYCLE", "RUNNING") and not away:
            bad("M11", t, f"{p['activity']} while at home (Home-WiFi connected)", key=p["activity"])
            continue
        if typ == "DEVICE_STATE":
            if p.get("state") in ("SCREEN_ON", "SCREEN_OFF"):
                screen = p["state"] == "SCREEN_ON"
                if not screen:
                    for a in sorted(fg):
                        bad("F3", t, f"{a} still in the foreground when the screen turned off", key=a)
                    fg.clear()
            continue
        if typ == "APP_USAGE":
            if p.get("action") == "FOREGROUND":
                if screen is False:
                    bad("F1", t, f"{j['title']} foreground with the screen off")
                others = fg - {p.get("packageName")}
                if others:
                    bad("F4", t, f"{j['title']} foreground while {', '.join(sorted(others))} still is", key=", ".join(sorted(others)))
                fg.add(p.get("packageName"))
            else:
                fg.discard(p.get("packageName"))
                if screen is False:
                    bad("F3", t, f"{j['title']} goes to the background after the screen turned off")
            continue
        if typ != "SMARTTHINGS" or p.get("kind") != "state":
            continue
        did, chg = p["deviceId"], p.get("change") or {}
        droom, dtype = did.split(".")[0], did.split(".")[-1]
        actor = p.get("actor") or {}
        val = chg.get("value")
        if dtype == "occupancy_sensor":
            if val != "present":
                present.discard(droom)
                if not present:
                    empty_since, empty_flagged = t, False
                continue
            present.add(droom)
            multi_flagged = False
            if came_home:
                if droom != "entryway" or not door_open_since_home:
                    bad("M6", t, f"first room after coming home: {droom}, front door opened before: {door_open_since_home}")
                came_home = False
            if room is not None and droom != room:
                moves_in_hour[t // 3600000 * 3600000] += 1
                if room_t is not None and t - room_t in (1000,):
                    bad("M9", t, f"in {room} for 1 s, then {droom}", key=room)
                if asleep_at(t):
                    bad("M8", t, f"moves {room} -> {droom} while asleep", key="move while asleep")
            if away:
                bad("H1", t, f"{droom} present while away")
            if room is not None and droom != room:
                if droom not in adj[room]:
                    bad("M1", t, f"{room} -> {droom}", key=f"{room} -> {droom}")
                if room_t == t:
                    bad("M2", t, f"in {room} for 0 s, then {droom}", key=room)
                if "balcony" in (room, droom) and living_win == "closed":
                    bad("M3", t, f"{room} -> {droom} with the living room window closed")
            room, room_t = droom, t
            continue
        if did == "living_room.window_contact":
            living_win = val
        if actor.get("channel") == "physical" and asleep_at(t):
            bad("M8", t, f"{did} {val} (physical) while asleep", key="physical action while asleep")
        if actor.get("channel") == "physical":
            where = "entryway" if dtype in ("lock", "door_contact") else droom
            if away:
                bad("H1", t, f"{did} {val} (physical) while away")
            elif room != where:
                bad("P1", t, f"{did} {val} (physical) while in {room}", key=f"{dtype} in {room}")
        if actor.get("channel") == "mobile_app" and ST_APP not in fg:
            bad("F2", t, f"{did} {chg.get('attribute')}={val} from the app with SmartThings not in the foreground")
        if did == "entryway.lock":
            if val == "locked" and door == "open":
                bad("D1", t, "locked with the door open")
            lock = val
        elif did == "entryway.door_contact":
            if val == "open" and lock == "locked":
                bad("D1", t, "door opened while locked")
            if val == "open":
                door_open_since_home = True
                if room not in (None, "entryway") and len(present) and "entryway" not in present:
                    bad("M7", t, f"front door opens with the person in {room}", key=room)
            door = val
        elif dtype == "washer" and chg.get("attribute") == "machineState":
            if val == "run":
                if washer_run:
                    bad("A1", t, "washer started while running")
                washer_run = True
            elif val == "stop" and washer_run:
                washer_run, to_dry = False, to_dry + 1
        elif dtype == "dryer" and chg.get("attribute") == "machineState":
            if val == "run":
                if dryer_run:
                    bad("A1", t, "dryer started while running")
                if to_dry <= 0:
                    bad("A1", t, "dryer started with no washed load waiting")
                to_dry, dryer_run = 0, True
            elif val == "stop":
                dryer_run = False
    for h, n in moves_in_hour.items():
        if steps.get(h, 1) == 0:
            bad("M10", h, f"{n} move(s) between rooms in the hour, 0 steps")
    print(f"log: {o.log}\nhouse: {o.houseType}\n")
    for r in ("L0", "M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8", "M9", "M10", "M11", "P1", "H1", "D1", "A1", "F1", "F4", "F3", "F2"):
        print(f"{r}: {count[r]}")
        for k, v in detail[r].most_common(8):
            print(f"      {v:6d}  {k}")
        for e in ex[r]:
            print(f"      e.g. {e}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
