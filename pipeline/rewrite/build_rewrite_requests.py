#!/usr/bin/env python3
"""Assign a house type to every persona (by ratio, reproducible) and write rewrite requests (system + user
messages), a batch of personas per request. No API call is made.

usage: python3 build_rewrite_requests.py ../input/realistic_patterns.txt
         [--ratio 2room=1,3room=1,4room=1] [--seed 7] [--batch 10] [--out requests] [--personas personas.csv]
If --personas exists, its houseType column is used as is; otherwise it is created from --ratio and --seed.
Input columns: 사용자,패턴,유형,요약,비고 (or personaId,patternId,patternType,text,note).
"""
import argparse, csv, io, json, os, random, sys
HERE = os.path.dirname(os.path.abspath(__file__))
COLS = {"사용자": "personaId", "패턴": "patternId", "유형": "patternType", "요약": "text", "비고": "note"}

def read_rows(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        r = {COLS.get(k.strip(), k.strip()): (v or "").strip() for k, v in r.items() if k}
        if r.get("personaId"): rows.append(r)
    return rows

def section(md, name):
    start = md.index(f"## {name}\n") + len(f"## {name}\n")
    end = md.find("\n---------------------------------------------------------------------------------------------------", start)
    return md[start:end if end > 0 else None].strip()

def assign(personas, ratio, seed):
    """house types in the given ratio (largest remainder), then shuffled with the seed"""
    total = sum(ratio.values()); n = len(personas)
    counts = {k: int(n * w / total) for k, w in ratio.items()}
    for k in sorted(ratio, key=lambda k: -(n * ratio[k] / total - counts[k]))[: n - sum(counts.values())]: counts[k] += 1
    pool = [k for k, c in counts.items() for _ in range(c)]
    random.Random(seed).shuffle(pool)
    return dict(zip(personas, pool))

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("patterns"); ap.add_argument("--ratio", default="2room=1,3room=1,4room=1")
    ap.add_argument("--seed", type=int, default=7); ap.add_argument("--batch", type=int, default=10)
    ap.add_argument("--out", default=os.path.join(HERE, "requests")); ap.add_argument("--personas", default=os.path.join(HERE, "personas.csv"))
    a = ap.parse_args()
    rows = read_rows(a.patterns)
    personas = sorted({r["personaId"] for r in rows})
    if os.path.exists(a.personas):
        ht = {r["personaId"]: r["houseType"] for r in csv.DictReader(open(a.personas, encoding="utf-8"))}
        missing = [p for p in personas if ht.get(p) not in ("2room", "3room", "4room")]
        if missing: sys.exit(f"{a.personas}: no valid houseType for {', '.join(missing)}")
        print(f"house types from {a.personas}")
    else:
        ratio = {k: float(v) for k, v in (x.split("=") for x in a.ratio.split(","))}
        ht = assign(personas, ratio, a.seed)
        with open(a.personas, "w", encoding="utf-8", newline="") as f:
            w = csv.writer(f); w.writerow(["personaId", "houseType", "notes"])
            for p in personas: w.writerow([p, ht[p], ""])
        print(f"{a.personas} written (ratio {a.ratio}, seed {a.seed}):", {k: list(ht.values()).count(k) for k in ("2room", "3room", "4room")})
    md = open(os.path.join(HERE, "prompt_pattern_rewrite.md"), encoding="utf-8").read()
    caps = open(os.path.join(HERE, "simulator_capabilities.md"), encoding="utf-8").read().strip()
    ex = open(os.path.join(HERE, "rewrite_examples.json"), encoding="utf-8").read().strip()
    system = section(md, "SYSTEM").replace("{{CAPABILITIES}}", caps).replace("{{EXAMPLES_JSON}}", ex)
    user_t = section(md, "USER")
    os.makedirs(a.out, exist_ok=True)
    for i in range(0, len(personas), a.batch):
        group = personas[i:i + a.batch]
        buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n")
        n = 0
        for r in rows:
            if r["personaId"] in group:
                w.writerow([r["personaId"], ht[r["personaId"]], r["patternId"], r["patternType"], r["text"], r.get("note", "")]); n += 1
        user = user_t.replace("{{PATTERN_ROWS}}", buf.getvalue().strip())
        name = f"rewrite_{group[0]}-{group[-1]}.json"
        json.dump({"personas": group, "rows": n, "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]},
                  open(os.path.join(a.out, name), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        print(f"{name}: {len(group)} persona(s), {n} row(s), about {round((len(system) + len(user)) / 3.5)} tokens")

if __name__ == "__main__":
    main()
