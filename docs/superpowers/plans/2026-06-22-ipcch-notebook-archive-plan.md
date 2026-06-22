# IPCCH Notebook Archive Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Archive original production notebooks after confirming converted `.py` workflow entry points cover the same notebook code cells.

**Architecture:** Keep converted `.py` scripts in their operational source folders. Move original `.ipynb` files to `archive/notebooks/` with source-folder subdirectories, then update operator-facing documentation to point to archived references.

**Tech Stack:** Jupyter notebook JSON, Python 3 verification scripts, Markdown documentation, Git file moves.

---

### Task 1: Archive Production Notebooks

**Files:**
- Move: `ACLED/00_add_ACLED_IPCCH.ipynb` to `archive/notebooks/ACLED/00_add_ACLED_IPCCH.ipynb`
- Move: `FAO_price/00_add_FAO_ipcch_update.ipynb` to `archive/notebooks/FAO_price/00_add_FAO_ipcch_update.ipynb`
- Move: `WB_indicator/00_add_WBG_ch.ipynb` to `archive/notebooks/WB_indicator/00_add_WBG_ch.ipynb`
- Move: `WFP_indicator/00_add_WFP_ch.ipynb` to `archive/notebooks/WFP_indicator/00_add_WFP_ch.ipynb`
- Move: `Final_harmonise/*.ipynb` to `archive/notebooks/Final_harmonise/`
- Create: `archive/notebooks/MANIFEST.md`

- [ ] **Step 1:** Create archive subdirectories.
- [ ] **Step 2:** Move the eight production notebooks.
- [ ] **Step 3:** Create a manifest mapping each archived notebook to its operational `.py`.

### Task 2: Update References and Verify Coverage

**Files:**
- Modify: `CLAUDE.md`
- Modify: `docs/03_workflow_runbook.md`
- Modify: `docs/superpowers/specs/2026-06-22-ipcch-handover-design.md`
- Modify: `docs/superpowers/plans/2026-06-22-ipcch-handover-implementation.md`

- [ ] **Step 1:** Update operator-facing notebook references to `archive/notebooks/...`.
- [ ] **Step 2:** Verify every archived notebook has a matching operational `.py`.
- [ ] **Step 3:** Verify notebook code-cell counts match converted script `# %%` block counts.
- [ ] **Step 4:** Run `py_compile` for converted scripts.
