# GitHub Actions workflow

Read `report-schema.md` before writing the fragment. Run every command from the project root.

## Gather action references

Run:

```bash
<skill_dir>/scripts/list-direct-actions.py
```

The helper scans workflows and reachable local actions. It records the owning `owner/repo`, any sub-action path, the ref, source location, and inline comment. Docker actions are excluded.

Deduplicate research by `owner/repo`, but preserve every sub-action and source location in the report. Reusable workflows are researched against their owning repository.

## Resolve the current ref

Classify each ref as a tag, branch, or full commit SHA.

- Resolve SHA pins through the repository. Treat the inline comment as a hint only.
- For a branch pin, compare the pinned branch head with a defined baseline. If no prior report or commit baseline exists, state `❓ unknown` rather than claiming whether it moved.
- For a major-only tag, report a newer major as outdated. Do not report releases within the same floating major as a required pin change.

## Research releases

Use GitHub releases first, then repository tags and commit comparisons when releases are unavailable. Identify the latest stable tag and read changes strictly after the resolved current version.

Check for:

- major version changes
- removed or renamed inputs and outputs
- runtime changes that require a newer Actions runner
- removed sub-actions or reusable workflow paths
- changed permissions

Search the project's workflows and local action definitions for affected inputs, outputs, permissions, and paths. Cite exact paths and lines.

## Write the fragment

Write `<output_dir>/DEPS_UPGRADE_REPORT_ACTIONS.json` with:

- `surface`: `actions`
- `label`: `GitHub Actions`
- `manager`: `github-actions`
- one entry per unique `owner/repo` and ref combination
- all source locations retained in `locations`
- an empty `entries` list when every action is current
- command or research failures in `errors`

Use `current_ref` and `latest_ref` for SHA or branch details. Sort entries by status priority, then action name. Return the counts, errors, warnings, and absolute fragment path.
