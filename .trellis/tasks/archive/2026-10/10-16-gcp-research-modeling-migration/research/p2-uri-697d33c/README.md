# URI mapping rehearsal (native 697d33c)

Native code: `d6bff7e` and `e513fff`.

- **Mapping plan on snapshot r1** (`plan-r1.json`): 172 tagged logged models. 56 are mapped (42 distinct specs), 116 existing `runs:/` references are unchanged, and 0 are refused. The original `card.feature_list` tags stay untouched.
- **Applied over HTTP** as admin to a disposable copy of the copied stores (`wsc_track`), served with a copy of the artifact tree: 56 tags written (`apply.json`). Re-applying wrote 0 and found no drift (`apply-again.json`).
- **`check.json` (172/172 "ok") is NOT acceptance.** Its original side resolved the 116 `runs:/` specs through the same target server, so for those it compares target bytes with target bytes (supervisor finding). The fix: resolve the original side from snapshot r1's local artifact root, and keep the cloud side as target-only authenticated downloads. Unit tests (mapping, remote member, cloud-local refusal) are also pending.

## Acceptance (`check-acceptance.json`, native `697d33c`)

**172/172 models match**: 115,658 ordered feature names, 56 of them through mapped tags.
- **Original side:** each `runs:/` part is resolved through snapshot r1's `runs.artifact_uri` to the ORIGINAL local artifact root, and any remaining remote part is refused. Nothing on this side is read from the target.
- **Target side:** authenticated downloads through the rehearsal server (copied stores with a copied artifact tree), as the copied non-admin READ identity, in cloud mode (local roots disabled).
- The original `card.feature_list` tags were verified unchanged in the target.

This is local rehearsal evidence. The same check is to be repeated against the cloud staging service, together with byte checks of standard `runs:/`, `models:/` and `mlflow-artifacts:/` downloads.
