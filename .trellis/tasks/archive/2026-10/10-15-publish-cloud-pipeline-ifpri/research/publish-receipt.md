# Publish receipt — 2026-10-15

- Target: `https://github.com/IFPRI/MTID-FSP-FOOD-CRISIS-MODEL-INPUT` (PRIVATE, default branch `main`; was empty before push)
- Source: `swl007007/IPCCH_operational` @ `be49ff4fe3c7aa7f3c4a3baa023bcc2a86b66df7`, exported with `git archive HEAD:cloud_pipeline` (committed LF blobs; local CRLF working-tree noise not included)
- Pushed commit: `807f1a6912965cb537861c56d3982909caa16fc1` (single commit), pushed over HTTPS with the `gh` credential (WSL SSH key rejected)
- Tree: 156 files = 154 source files + `.gitignore` + `.gitattributes`; `README.md` gains the "Data not in this repository" section (handover archive SHA-256 `42d4e9079f0da815249a57670c8910361c981b10231eb2948ce60912b388606a`). Full blob list: `pushed-tree.txt`.

## Checks

| Check | Result |
|---|---|
| `py_compile` on 108 `.py` files | pass |
| Files > 50 MB | none (largest 10.1 MB test fixture) |
| Secret regex scan + service-account JSON scan | no hits |
| New `.gitignore` excludes no tracked file | pass (156 tracked after `git add -A`) |
| Remote `main` SHA == local | pass |
| Remote commit count | 1 |
| Remote blob list/hashes == local export | pass (156/156) |
| Export vs source `HEAD:cloud_pipeline` blobs | identical except README (intended) and the two new files |

pytest was not run (operator choice in grill).
