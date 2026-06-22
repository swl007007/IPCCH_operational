# Handover Email Archive

Archived on: 2026-06-22

Purpose: record the requested code, data, and validation handover timeline for
the monthly food-crisis model workflow.

## Archived Request

1. Weilun (June 22-June 24): use a CI/CD pipeline for the model in Google
   Cloud. Push the code needed to run the monthly food crisis model into the
   IFPRI private repo, `main` branch, with a detailed README explaining how to
   run the Python code:
   `https://github.com/IFPRI/MTI-GOOGLE-FOOD-CRISIS-MODEL.git`.
   A separate repo will be created later for model upgrades after the monthly
   workflow is set up.

2. Weilun and Sediqa (June 22-June 24): share the data table and all
   step-by-step documentation for data collection with Sediqa and the requester
   in the MS Teams / SharePoint modeling space:
   `https://cgiar.sharepoint.com/:f:/r/sites/IFPRI-MTI-foodcrisis/Shared%20Documents/1.%20Modeling?csf=1&web=1&e=G4fpyi`.
   On this machine, that Teams/SharePoint space is locally synced at
   `C:\Users\swl00\CGIAR\IFPRI-MTI-foodcrisis - 1. Modeling`.
   Zaki and Sediqa (June 25-June 30) should work with Weilun to learn how to
   collect the data for running the model.

3. Weilun (July 1-July 3): confirm that the whole dataset is updated and ready
   to run the model after Sediqa completes the collection.

## Implications For This Repo

- This local `IPCCH_monthly_operational` repo is a staging and experimental
  workspace, not the final team handover repository.
- Final code deliverables should be curated for
  `IFPRI/MTI-GOOGLE-FOOD-CRISIS-MODEL` and include a README with executable
  monthly workflow instructions.
- Large data tables, source-data collection instructions, and supporting
  documentation should be delivered through the MS Teams / SharePoint location,
  not by committing large files to Git.
- Local agent/runtime files are not part of final handover: `AGENTS.md`,
  `CLAUDE.md`, `.agents/`, `.claude/`, `.codex/`, `docs/superpowers/`,
  `__pycache__/`, and `*.pyc`. This exclusion is also recorded in
  `config/paths_template.ini` `[handover]`.
- WDG-01 in `docs/06_weilun_deliverable_gap_audit.md` should be interpreted as
  a final packaging/merge gap, not as a requirement that this experimental
  local repo must be perfectly clean before further work.
