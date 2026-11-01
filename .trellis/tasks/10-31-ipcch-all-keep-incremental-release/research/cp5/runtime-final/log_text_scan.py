"""Scan every saved execution log entry's text (any severity) for warning/error words (local only)."""
import json, os, re, sys
os.chdir(os.path.dirname(os.path.abspath(__file__)))
logs = json.load(open("outputs/02-exec-logs.json"))
pat = re.compile(r"warn|error|exception|traceback|fail|timed? ?out|retry", re.I)
hits = []
for e in logs:
    t = e.get("textPayload") or json.dumps(e.get("jsonPayload") or {}, default=str)
    if e.get("protoPayload"):
        continue                                              # audit entries (RunJob request/response), not job output
    if pat.search(t):
        hits.append({"ts": e.get("timestamp"), "severity": e.get("severity"), "text": t[:800]})
out = {"entries": len(logs), "audit_entries_skipped": sum(1 for e in logs if e.get("protoPayload")),
       "pattern": pat.pattern, "hits": hits}
open(sys.argv[1], "x").write(json.dumps(out, indent=1))
print(json.dumps({"entries": out["entries"], "hits": len(hits)}))
for h in hits:
    print(h["ts"], h["severity"], h["text"][:400])
