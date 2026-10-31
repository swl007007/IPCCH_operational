"""(Task 10-30 CP4 step 6; adapted from the 10-21 p4 precedent, README text only.) Stage the verified runtime-compatibility candidate as a compact fallback beside the active one (never in place).

Layout mirrors the active ``fallback/october_2026``: candidate ``manifest.json`` + archive, the 30 scope
tables, ``shared/`` references, ``reports/``, ``replay_evidence/`` and ``retained_inventory.json``.
Promotion later swaps it in only after the receipt-bound pointer CAS (``pipeline.py promote``).

usage: stage_fallback.py CANDIDATE_DIR STAGED_DIR EVIDENCE_JSON...
"""

import hashlib
import json
import shutil
import sys
from pathlib import Path

REPORTS = ("delivery.json", "diagnostic_availability.csv", "fewsnet_assembly.json", "fewsnet_diagnostic_declarations.json",
           "fewsnet_normalization_audit.json", "ipcch_assembly.json", "ipcch_diagnostic_declarations.json",
           "inherited_members.json")
README = """# Accepted October 2026 fallback: runtime-compatibility release (candidate {run_id})

Use `scopes/0m/`, `scopes/6m/` and `scopes/12m/` for the final CSVs (targets October 2026, April 2027, October 2027).
`shared/` provides geometry/population references; `reports/` and `replay_evidence/` retain assembly, availability,
inheritance and verification evidence.

* **FEWS NET** predictions were re-scored by the v2 runtime `{image}` with the UNCHANGED packages of suite
  `full-202610-ff389b11af93-02caeb861750` from the same prepared snapshot `fewsnet-retrain-20261022a` as the previous
  release `fews-candidate-20261022a`; `replay_evidence/compat-checks.json` shows every scope table, input and package
  member byte-identical to that release (runtime-compatibility evidence, task 10-30 CP4; no retraining, no evaluation).
* **FEWS confidence** columns are the unchanged frozen October evidence of the earlier release (not error estimates of
  these packages).
* **IPCCH** was not scored: inherited byte-for-byte from the current release's member (`reports/inherited_members.json`).

`manifest.json` is the full candidate manifest; `retained_inventory.json` describes this folder. The previous fallback
is kept beside this one as `october_2026.predecessor-<operation>` after promotion; see the cloud pipeline OPERATIONS
document for recovery.
"""


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def main(candidate: Path, staged: Path, evidence: list[Path]) -> dict:
    staged.mkdir(parents=True, exist_ok=False)
    for name in ("manifest.json", "webapp_model_bundle.tar.gz"):
        shutil.copyfile(candidate / name, staged / name)
    for table in sorted(candidate.glob("scopes/*/*/*.csv")):
        target = staged / table.relative_to(candidate)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(table, target)
    for system in ("fewsnet", "ipcch"):
        for name in ("polygons.geojson", "country_population_reference.csv"):
            target = staged / "shared" / system / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(candidate / system / name, target)
    (staged / "reports").mkdir()
    for name in REPORTS:
        shutil.copyfile(candidate / "reports" / name, staged / "reports" / name)
    (staged / "replay_evidence").mkdir()
    for path in evidence:
        shutil.copyfile(path, staged / "replay_evidence" / Path(path).name)
    delivery = json.loads((candidate / "reports/delivery.json").read_text())
    image = json.loads((candidate / "manifest.json").read_text())["provenance"]["image_uri"]
    (staged / "README.md").write_text(README.format(run_id=delivery["run_id"], image=image))
    files = [{"path": p.relative_to(staged).as_posix(), "size_bytes": p.stat().st_size, "sha256": sha(p)}
             for p in sorted(staged.rglob("*")) if p.is_file()]
    (staged / "retained_inventory.json").write_text(json.dumps(
        {"schema_version": "compact-october-fallback-v1", "files": files}, indent=2, sort_keys=True) + "\n")
    return {"staged": str(staged), "files": len(files), "manifest_sha256": sha(staged / "manifest.json"),
            "archive_sha256": sha(staged / "webapp_model_bundle.tar.gz"),
            "tables": len(list(staged.glob("scopes/*/*/*.csv")))}


if __name__ == "__main__":
    print(json.dumps(main(Path(sys.argv[1]), Path(sys.argv[2]), [Path(p) for p in sys.argv[3:]]), indent=2))
