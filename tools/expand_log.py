"""Restore the full event-formats v3 form of a stored phone log (puts back the SMARTTHINGS fields that other fields determine).
usage: python3 tools/expand_log.py out/063/phone_log.jsonl > phone_log_full.jsonl"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from smarthome_sim.formats import expand
from smarthome_sim.agent import dumps

out = sys.stdout
for line in open(sys.argv[1], encoding="utf-8"):
    out.write(dumps(expand(json.loads(line))) + "\n")
