"""Read-only maintenance checkpoint: live predecessor settings/grants, active work and the concrete
gate/apply/restore commands, computed by the same pipeline.py functions the hold will use."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "cloud_pipeline"))
import pipeline as p  # noqa: E402

cfg = p.config(sys.argv[1])
calls = []


def runner(argv):
    calls.append(argv)
    return p.gcloud_json(argv)


predecessor = p.shared_runtime(cfg, runner)
predecessor["grants"] = p._grants(cfg, runner)
source = predecessor.pop("workflow_source")
operation = {"predecessor": predecessor, "directory": "<work_dir>/operations/<operation_id>"}
print(json.dumps({"config": cfg, "predecessor": predecessor, "predecessor_workflow_source": source,
                  "active_work": p.active_work(cfg, runner), "gate_commands": p.gate_commands(cfg, operation),
                  "apply_commands": p._setup_commands(cfg), "restore_commands": p.restore_commands(cfg, operation),
                  "read_only_calls": calls}, indent=1))
