#!/usr/bin/env python3
"""Fill prompt_pattern_structuring.md with the files and write one API request (system + user message) per persona.
No API call is made. Send each file in requests/ to the model of your choice, save the reply's JSON array as
structured/<personaId>.json, then run validate_patterns.py on it.

usage: python3 build_requests.py patterns.csv personas.csv [--roles room_roles.json] [--out requests]
  patterns.csv : personaId,patternId,patternType,text
  personas.csv : personaId,houseType(2room|3room|4room),notes
  room_roles.json (optional): {"<personaId>": {"study_room": "room2", ...}} from earlier batches, kept stable
"""
import csv, io, json, os, sys, argparse
HERE = os.path.dirname(os.path.abspath(__file__))

def section(md, name):
    start = md.index(f"## {name}\n") + len(f"## {name}\n")
    end = md.find("\n---------------------------------------------------------------------------------------------------", start)
    return md[start:end if end > 0 else None].strip()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns"); ap.add_argument("personas")
    ap.add_argument("--roles", default=None); ap.add_argument("--out", default=os.path.join(HERE, "requests"))
    a = ap.parse_args()
    md = open(os.path.join(HERE, "prompt_pattern_structuring.md"), encoding="utf-8").read()
    vocab = open(os.path.join(HERE, "vocabulary.json"), encoding="utf-8").read().strip()
    schema = open(os.path.join(HERE, "pattern.schema.json"), encoding="utf-8").read().strip()
    examples = open(os.path.join(HERE, "structured_examples.json"), encoding="utf-8").read().strip()
    system = section(md, "SYSTEM").replace("{{VOCABULARY_JSON}}", vocab).replace("{{SCHEMA_JSON}}", schema).replace("{{EXAMPLES_JSON}}", examples)
    user_t = section(md, "USER")
    personas = {r["personaId"]: r for r in csv.DictReader(open(a.personas, encoding="utf-8"))}
    roles = json.load(open(a.roles, encoding="utf-8")) if a.roles else {}
    rows = list(csv.DictReader(open(a.patterns, encoding="utf-8")))
    by = {}
    for r in rows: by.setdefault(r["personaId"], []).append(r)
    os.makedirs(a.out, exist_ok=True)
    for pid, rs in by.items():
        pr = personas.get(pid)
        if not pr or pr.get("houseType") not in ("2room", "3room", "4room"):
            sys.exit(f"persona {pid}: set houseType (2room, 3room or 4room) in {a.personas}")
        buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n")
        for r in rs: w.writerow([r["personaId"], r["patternId"], r["patternType"], r["text"], r.get("note", "")])
        user = (user_t.replace("{{PERSONA_ID}}", pid).replace("{{HOUSE_TYPE}}", pr["houseType"])
                .replace("{{PERSONA_NOTES}}", pr.get("notes") or "").replace("{{ROOM_ROLES_SO_FAR}}", json.dumps(roles.get(pid, {})))
                .replace("{{PATTERN_ROWS}}", buf.getvalue().strip()))
        req = {"personaId": pid, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
        path = os.path.join(a.out, f"{pid}.json")
        json.dump(req, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{path}: {len(rs)} pattern(s), system {len(system)} chars, user {len(user)} chars")

if __name__ == "__main__":
    main()
