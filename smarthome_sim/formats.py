"""Stored form of the phone log.

The SMARTTHINGS copies of home lines (payload.kind "state") are stored without the fields that the same event's other
fields determine ("(가)" in the design notes): source, title, text, collectedAt, dedupeKey, payload.name, payload.label,
payload.deviceTypeName, payload.roomId, payload.capabilities, change.unit, and for sensor reports payload.status and the
empty actor fields (channel, command, args). Nothing else is dropped. expand() puts them back exactly
(tools/expand_log.py; checked by tests/test_port.py).

Other phone events (and SMARTTHINGS alerts, payload.kind "notification") are stored as they are."""
import json
import os

from .house import ROOM_LABEL, DEVICE_LABEL

_SPEC = [json.loads(l) for l in open(os.path.join(os.path.dirname(__file__), "data", "device_spec.jsonl"), encoding="utf-8") if l.strip()]
CAPS = {d["device"]: [c["capability"] for c in d["capabilities"]] for d in _SPEC}
UNITS = {(d["device"], c["capability"], a["name"]): a.get("unit") for d in _SPEC for c in d["capabilities"] for a in c["attributes"]}


def _txt(v):
    """a value as JavaScript prints it in a template string"""
    if v is True:
        return "true"
    if v is False:
        return "false"
    if v is None:
        return "null"
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def compact(e):
    """the stored form of one phone event (a new dict; the input is not changed)"""
    p = e.get("payload")
    if e.get("type") != "SMARTTHINGS" or not p or p.get("kind") != "state":
        return e
    ch = {k: v for k, v in p["change"].items() if k != "unit"}
    a = p["actor"]
    if a["kind"] == "sensor":
        actor = {"kind": "sensor", "reason": a.get("reason")}
    else:
        actor = a
    q = {"kind": "state", "deviceId": p["deviceId"], "change": ch, "actor": actor}
    if a["kind"] != "sensor":
        q["status"] = p["status"]
    return {"type": e["type"], "timestamp": e["timestamp"], "payload": q, "context": e["context"]}


def expand(e):
    """the full event-formats v3 form of one stored phone event"""
    p = e.get("payload")
    if e.get("type") != "SMARTTHINGS" or not p or p.get("kind") != "state" or "source" in e:
        return e
    did = p["deviceId"]
    room, dtype = did.split(".", 1)
    ch = p["change"]
    cap, attr = ch["capability"], ch["attribute"]
    unit = UNITS.get((dtype, cap, attr))
    a = p["actor"]
    if a["kind"] == "sensor":
        actor = {"kind": "sensor", "channel": None, "command": None, "args": [], "reason": a.get("reason")}
        status = {"components": {"main": {cap: {attr: ({"value": ch["value"], "unit": unit} if unit else {"value": ch["value"]})}}}}
    else:
        actor = a
        status = p["status"]
    dl = DEVICE_LABEL.get(dtype, dtype)
    label = f"{ROOM_LABEL.get(room, room)} {dl.lower()}"
    who = (f"user, {'mobile app' if actor.get('channel') == 'mobile_app' else 'at device'}" if actor["kind"] == "user"
           else "sensor report" if actor["kind"] == "sensor" else actor["kind"])
    prev = "-" if ch.get("previousValue") is None else _txt(ch["previousValue"])
    t = e["timestamp"]
    change = {"capability": cap, "attribute": attr, "value": ch["value"], "previousValue": ch.get("previousValue")}
    if unit:
        change["unit"] = unit
    return {"type": "SMARTTHINGS", "source": did, "title": label,
            "text": f"{dl} · {attr}: {prev} -> {_txt(ch['value'])}{' ' + unit if unit else ''} ({who})",
            "timestamp": t, "collectedAt": t, "dedupeKey": f"ST:{did}:{cap}.{attr}:{_txt(ch['value'])}:{t}",
            "payload": {"kind": "state", "deviceId": did, "name": dtype, "label": label, "deviceTypeName": dl, "roomId": room,
                        "capabilities": CAPS.get(dtype, [cap]), "change": change, "actor": actor, "status": status},
            "context": e["context"]}
