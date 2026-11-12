import json
import re
from collections import Counter
from pathlib import Path

repo = Path(__file__).resolve().parents[2]
counts = Counter()
flags = []
tools = Counter()
for f in sorted((repo / "runs/W1-P1").glob("[0-9]*.json")):
    x = json.loads(f.read_text(encoding="utf-8"))
    roles = {}
    pack = set()
    alive = set(x["record"]["players"])
    for e in x["events"]:
        t = e["type"]
        d = e["data"]
        p = d.get("player")
        audience = e.get("visible_to")
        if t == "role_assigned":
            roles[p] = d["role"]
            if audience != [p]:
                flags.append([f.stem, e["seq"], "role audience"])
        if t == "pack_revealed":
            pack = set(d["wolves"])
            if set(audience or []) != pack:
                flags.append([f.stem, e["seq"], "pack audience"])
        if t in ("seer_inspected", "witch_acted") and audience != [p]:
            flags.append([f.stem, e["seq"], "private ability audience"])
        if t == "thought" and audience != []:
            flags.append([f.stem, e["seq"], "thought audience"])
        if t in ("wolf_vote", "wolf_talked") and not set(audience or []).issubset(pack):
            flags.append([f.stem, e["seq"], "wolf audience"])
        if t == "action_accepted":
            tool = d["tool"]
            a = d["arguments"]
            tools[tool] += 1
            field = "text" if "text" in a else "reason"
            if field in a:
                words = len(a[field].split())
                limit = 120 if tool == "speak" else 40
                counts["accepted_texts"] += 1
                counts[f"accepted_{field}_fields"] += 1
                if words > limit:
                    flags.append([f.stem, e["seq"], "accepted overlong text", words, limit])
                for said in re.findall(r"\bI\s+am\s+(p\d+)\b", a[field], re.I):
                    counts["explicit_self_seat_statements"] += 1
                    if said.lower() != p:
                        flags.append([f.stem, e["seq"], "explicit self-seat mismatch", p, said])
            if tool == "vote":
                counts["accepted_day_votes"] += 1
                if a.get("target") is not None and a["target"] not in alive:
                    flags.append([f.stem, e["seq"], "dead or unknown vote target"])
        if t == "player_died":
            alive.discard(p)
out = {
    "checks": dict(counts),
    "accepted_tools": dict(tools),
    "flags": flags,
    "limitations": (
        "Stored event audiences and syntactic identity scan only; "
        "exact sent request snapshots are not logged; "
        "no exhaustive semantic confusion/privacy proof."
    ),
}
dest = repo / "research/W1/P1/speech_privacy.json"
dest.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
print(json.dumps(out, indent=2))
