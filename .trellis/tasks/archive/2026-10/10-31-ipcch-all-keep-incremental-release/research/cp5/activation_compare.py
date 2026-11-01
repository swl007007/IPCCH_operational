"""Compare the post record's activation dict with the pinned pre-real record (local JSON only; no cloud)."""
import json, sys
pre, post, out = sys.argv[1:4]
def act(d):
    rec = d.get("record") or {}
    return rec.get("activation")
a, b = act(json.load(open(pre))), act(json.load(open(post)))
r = {"pre_activation": a, "post_activation": b, "equal": a is not None and a == b,
     "label": "carried contract activation (not a new activation event)" if a is not None and a == b else "NOT equal"}
open(out, "x").write(json.dumps(r, indent=1, sort_keys=True))
print(json.dumps(r, indent=1, sort_keys=True))
raise SystemExit(0 if r["equal"] else 1)
