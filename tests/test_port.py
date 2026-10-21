"""Checks the Python port against numbers produced by the browser simulator (smarthome-sim.html).
Run: python3 -m unittest discover -s tests   (no node needed; the fixtures were made with tools/js_*_fixture.js)"""
import json
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from smarthome_sim import Simulator, outdoor_at
from smarthome_sim.agent import AgentRunner
from smarthome_sim.timeutil import local_ms, MIN_MS

FIX = os.path.join(HERE, "fixtures")


def rel(a, b):
    return abs(a - b) / max(1, abs(a))


class TestAgainstJS(unittest.TestCase):
    def test_outdoor_matches_js(self):
        """outdoor weather, temperature, humidity, PM2.5, daylight, wind, rain and noise at 600 moments of 2026"""
        for t, o in json.load(open(os.path.join(FIX, "outdoor_js.json"))):
            p = outdoor_at(t)
            for k, v in o.items():
                if isinstance(v, (int, float)) and p[k] is not None:
                    self.assertLess(rel(v, p[k]), 1e-9, (t, k, v, p[k]))
                else:
                    self.assertEqual(v, p[k], (t, k))

    def test_physics_matches_js(self):
        """every room's true values every 6 h over a scripted 3 days (windows, stove, purifier, TV, lights, heating,
        cooling, humidifier, washer, dryer, dishwasher, robot vacuum, oven, balcony door, speaker, a person moving)"""
        script = json.load(open(os.path.join(FIX, "physics_script.json")))
        js = json.load(open(os.path.join(FIX, "physics_js.json")))
        T0 = local_ms(2026, 0, 15)
        s = Simulator("3room-A", T0, seed=1)
        s.where_refusal = lambda d: None
        s.jump_to(T0)
        s.phone.move_room("room1")
        ai, got = 0, {}
        for m in range(1, 3 * 1440 + 1):
            while ai < len(script) and script[ai][0] <= m:
                a = script[ai]
                ai += 1
                s.clock.set_to(T0 + a[0] * MIN_MS - MIN_MS + 1000)
                if a[1] == "run":
                    s.run(a[2], a[3], a[4], a[5] if len(a) > 5 else [], "mobile_app")
                elif a[1] == "set":
                    s.set_value(a[2], a[3], a[4], a[5])
                else:
                    s.phone.move_room(a[2])
            s.clock.set_to(T0 + m * MIN_MS)
            s.tick()
            if m % 360 == 0:
                got[m] = json.loads(json.dumps(s.house.env.rooms))
        for m, rooms in js:
            for room, vals in rooms.items():
                for k, v in vals.items():
                    self.assertLess(rel(v, got[m][room][k]), 1e-9, (m, room, k))


class TestRunner(unittest.TestCase):
    def test_same_seed_same_output(self):
        prof = json.load(open(os.path.join(os.path.dirname(HERE), "profiles", "063.json")))
        outs = []
        for _ in range(2):
            d = tempfile.mkdtemp()
            AgentRunner(prof, d, days=2, log=lambda *a: None).run()
            outs.append([open(os.path.join(d, f)).read() for f in ("home_log.jsonl", "phone_log.jsonl")])
        self.assertTrue(outs[0][0] and outs[0][1])
        self.assertEqual(outs[0], outs[1])


if __name__ == "__main__":
    unittest.main()
