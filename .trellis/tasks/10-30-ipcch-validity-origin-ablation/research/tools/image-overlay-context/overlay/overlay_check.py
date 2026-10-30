"""In-image overlay check (task 10-27): run as uid 65534, no network, before push. Exit 0 and one JSON line on success."""
import hashlib, json, os, platform, sys
from importlib.metadata import version
sys.dont_write_bytecode = True
sha = lambda p: hashlib.sha256(open(p, "rb").read()).hexdigest()
m = json.load(open("/app/overlay/overlay-manifest.json"))
base = json.load(open("/app/overlay/base-context-manifest.json"))
problems = []
if sha("/app/overlay/base-context-manifest.json") != m["base_context_manifest_sha256"]:
    problems.append("overlay copy of the BASE manifest differs from its pin")
if sha("/app/context-manifest.json") != m["base_context_manifest_sha256"]:
    problems.append("inherited /app/context-manifest.json is not the BASE manifest")
expected = {k[len("research_cloud/"):]: v for k, v in base["files"].items() if k.startswith("research_cloud/")}
for path, rec in m["overlaid_files"].items():
    rel = path[len("research_cloud/"):]
    if expected.get(rel) != rec["base_sha256"]:
        problems.append(f"BASE manifest hash of {path} is not the declared base hash")
    expected[rel] = rec["overlay_sha256"]
found = {}
for d, dirs, files in os.walk("/app/research_cloud"):
    dirs[:] = [x for x in dirs if x != "__pycache__"]
    for f in files:
        if not f.endswith(".pyc"):
            p = os.path.join(d, f)
            found[os.path.relpath(p, "/app/research_cloud")] = sha(p)
extra, missing = sorted(set(found) - set(expected)), sorted(set(expected) - set(found))
changed = sorted(k for k in set(found) & set(expected) if found[k] != expected[k])
if extra or missing or changed:
    problems.append(f"research_cloud tree differs from BASE+overlay: extra {extra[:5]} missing {missing[:5]} changed {changed[:5]}")
derived_vs_base = sorted(k for k in found if base["files"].get("research_cloud/" + k) != found[k])
if derived_vs_base != [p[len("research_cloud/"):] for p in m["overlaid_files"]]:
    problems.append(f"derived-vs-BASE differences {derived_vs_base} are not exactly the overlaid files")
rt = {"python": platform.python_version(), "packages": {}}
for name in m["expected_runtime"]["packages"]:
    rt["packages"][name] = version(name)
if rt != m["expected_runtime"]:
    problems.append(f"runtime {rt} differs from {m['expected_runtime']}")
if os.environ.get("IPCCH_SOURCE_COMMIT") != m["source_commit_env"]:
    problems.append("IPCCH_SOURCE_COMMIT is not the declared composite identifier")
sys.path.insert(0, "/app")
from research_cloud.training import ipcch_validity_pooled as vp
if (getattr(vp, "CORRECTED_INPUT_KIND", None) != "gpp_input_replacement" or vp.HPT_ARM != m["arm"]
        or getattr(vp, "ORIGIN_KIND", None) != "original_label_fit_ablation" or vp.FIT_LABELS != ("all", "original_only")):
    problems.append("the imported adapter is not the overlaid corrected-input module")
if problems:
    raise SystemExit("overlay check failed: " + "; ".join(problems))
print(json.dumps({"overlay_check": "ok", "files": len(found), "derived_vs_base": derived_vs_base, "runtime": rt,
                  "source_commit": os.environ["IPCCH_SOURCE_COMMIT"]}, sort_keys=True))
