---
description: "Load reference docs listed in the feature spec's ## References section"
---

# Load Spec Reference Docs

Read the current feature's `spec.md`, find the `## References` section, and load every file listed there.

## Steps

1. **Find the spec**: Locate the feature spec at the path provided by the
   calling context (e.g., `specs/NNN-<feature>/spec.md`). If no spec exists
   yet (e.g., during `/speckit.specify`), output "No spec found — skipping
   reference loading." and stop.

2. **Parse references**: Read the spec and find the `## References` section.
   Extract every markdown list item that contains a file path. Expected format:

   ```markdown
   ## References

   - docs/reference/api-reference.md
   - docs/reference/integration-guide.md
   ```

   Each line should be a `- path/to/file.md` entry. Ignore blank lines,
   comments, and list items that don't look like file paths.

   If the `## References` section is missing or empty, output
   "No references listed in spec — skipping." and stop.

3. **Load each file**: For each file path found:
   - Read the file contents.
   - If the file cannot be found or read, output a warning and continue
     with the next file.
   - Print a headed section:

   ```
   ## Reference: {filename}

   {file contents}
   ```

4. **Summarize**: After all files, output:

   ```
   Spec references loaded: {count} files
   ```

## Usage Notes

- Fires on `before_plan`, `before_tasks`, `before_implement`, `before_clarify`,
  `before_checklist`, and `before_analyze` — commands where the spec already exists.
- Does NOT fire on `before_specify` (spec doesn't exist yet). The memory-loader
  provides sufficient context for spec authoring.
- Paths are relative to the workspace root.
- This is a read-only operation — do NOT modify any files.
