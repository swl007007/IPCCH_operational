# spec-kit-spec-reference-loader

A [Spec Kit](https://github.com/github/spec-kit) extension that reads the `## References` section from the current feature spec and loads the listed files into LLM context. Only fires on commands where the spec already exists.

## Problem

Feature specs often reference external documents — API references, integration guides, decision records — but spec-kit lifecycle commands don't automatically load those files. The LLM agent plans and implements without access to the reference material that the spec author intended to be consulted.

## Solution

The Spec Reference Loader extension parses the `## References` section of the current feature's `spec.md` and loads every listed file into context before lifecycle commands execute.

## Installation

```bash
# From release
specify extension add spec-reference-loader --from https://github.com/KevinBrown5280/spec-kit-spec-reference-loader/archive/refs/tags/v1.0.0.zip

# From main branch
specify extension add spec-reference-loader --from https://github.com/KevinBrown5280/spec-kit-spec-reference-loader/archive/refs/heads/main.zip

# Development mode (local clone)
specify extension add --dev /path/to/spec-kit-spec-reference-loader
```

## Commands

| Command | Description | Modifies Files? |
|---------|-------------|-----------------|
| `speckit.spec-reference-loader.load` | Load reference docs listed in the feature spec's `## References` section | No — read-only |

## How It Works

1. **Find the spec**: Locates the feature spec at the path provided by the calling context (e.g., `specs/NNN-<feature>/spec.md`). If no spec exists yet, outputs a message and skips.

2. **Parse references**: Reads the spec's `## References` section and extracts file paths from markdown list items:
   ```markdown
   ## References

   - docs/reference/api-reference.md
   - docs/reference/integration-guide.md
   ```

3. **Load each file**: For each file path found, reads the contents and outputs:
   ```
   ## Reference: {filename}

   {file contents}
   ```

4. **Summarize**: After all files, outputs:
   ```
   Spec references loaded: {count} files
   ```

## Hooks

The extension fires automatically before these lifecycle commands:

| Hook | Command | Description |
|------|---------|-------------|
| `before_plan` | `speckit.spec-reference-loader.load` | Load references before planning |
| `before_tasks` | `speckit.spec-reference-loader.load` | Load references before task generation |
| `before_implement` | `speckit.spec-reference-loader.load` | Load references before implementation |
| `before_clarify` | `speckit.spec-reference-loader.load` | Load references before clarification |
| `before_checklist` | `speckit.spec-reference-loader.load` | Load references before checklist generation |
| `before_analyze` | `speckit.spec-reference-loader.load` | Load references before analysis |

**Does NOT fire on `before_specify`** — the spec doesn't exist yet at that point. A companion memory-loader extension can provide sufficient context for spec authoring.

## Design Decisions

- **Read-only** — never modifies any files
- **Spec-gated** — only fires when a spec already exists; skips silently otherwise
- **Complementary** — handles feature-specific references; pairs well with a memory-loader extension for project governance context
- **Graceful degradation** — missing files or missing `## References` section are handled with warnings, not errors

## Requirements

- Spec Kit >= 0.6.0

## License

MIT
