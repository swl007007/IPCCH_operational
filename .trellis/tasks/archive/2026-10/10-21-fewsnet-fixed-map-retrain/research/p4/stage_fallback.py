"""Stage the verified FEWS retrain candidate as a compact fallback beside the active one (never in place).

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
README = """# Accepted October 2026 fallback: FEWS all-history retrain (candidate {run_id})

Use `scopes/0m/`, `scopes/6m/` and `scopes/12m/` for the final CSVs (targets October 2026, April 2027, October 2027).
`shared/` provides geometry/population references; `reports/` and `replay_evidence/` retain assembly, availability,
inheritance and verification evidence.

* **FEWS NET** predictions were scored now by runtime `{image}` with the three all-history packages of suite
  `full-202610-ff389b11af93-02caeb861750` (fixed 17-partition map, 123 features, thresholds .48/.41/.45; trained on the
  v2 FEWS panel, no evaluation run). Inputs: prepared snapshot `fewsnet-retrain-20261022a` over the v2 FEWS source panel
  (`a83f5f4b...`), ACLED/WFP keep.
* **FEWS confidence** columns are copied unchanged from the accepted October delivery `oct-confidence-20261009b`
  (Stage3 research-run proxies of the previous packages, 2021-02..2024-10); only current country outcome columns are
  recomputed. They are not error estimates of the new packages.
* **IPCCH** was not scored: all its tables, inputs, evidence and reports are inherited byte-for-byte from
  `oct-confidence-20261009b` (`reports/inherited_members.json`), with that delivery's original computation provenance.

`manifest.json` is the full candidate manifest (many members live only inside `webapp_model_bundle.tar.gz`);
`retained_inventory.json` describes this folder. `replay_evidence/` holds the download receipt, the operator
verification receipt (inventory, pre-package validation, relocated FEWS-only replay with the bundled runtime, inherited
sources), the release checks (5,718 areas/22 countries, frozen confidence by key, inherited IPCCH identity) and the
cloud run record. The previous confidence-bearing fallback is kept beside this one as
`october_2026.predecessor-<operation>` after promotion; see the cloud pipeline OPERATIONS document for recovery.
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
