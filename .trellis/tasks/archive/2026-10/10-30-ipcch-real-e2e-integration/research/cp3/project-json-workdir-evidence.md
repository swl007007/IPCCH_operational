# Operator project.json: work_dir kept; v2 section added (CP3)

## Why `work_dir` was not repointed
The CP0 note flagged `work_dir` as possibly wrong. Read-only evidence shows the current value is the correct legacy state.

| operator-state | initialized destination image | matches project.json | baseline |
|---|---|---|---|
| `food-crisis-test-fews-retrain-20261022/operator-state` (current `work_dir`) | `runtime@sha256:487a2315…` | yes | `b77cb29b…` (Oct 22, post FEWS retrain; run `fews-candidate-20261022a`) |
| `food-crisis-test/operator-state` | `runtime@sha256:7e6133f3…` | no | `95111230…` (Oct 15) |

Repointing would make every legacy command fail `load_initialized` ("initialized state belongs to a different destination") and would drop the current legacy baseline. v2 submissions keep their state separately under `work_dir/runs-v2/`.

## Change applied
- **Backup:** `project.json.bak-cp3-20261031T015130Z`, sha `8eddc1bc…`, identical to the prior file.
- **Edit:** a single additive `v2` section; the new file is sha `de801c35…`.
- **Checks after the edit:**
  - every non-v2 field is unchanged, compared with diff;
  - `pipeline.config` loads;
  - `load_initialized` still accepts baseline `b77cb29b…`.

## Pending (CP4)
- The shared envelope, environment manifest and country reference objects are not uploaded yet.
- The smoke bucket is a proposal only.
- `image_uri` is still the legacy runtime and must be replaced after the CP4 build.
