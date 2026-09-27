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

## Decide the action

- `upgrade` when the workflow uses no affected input, output, permission, or runner feature.
- `migrate` when a workflow or local action must change. Put each edit in `steps` with its path and line.
- `decide` when a person must choose first, such as a self-hosted runner whose version cannot be confirmed, or an open Dependabot pull request that already proposes the same change.
- `hold` only when the project records why the pin must stay.

A branch pin whose movement is `❓ unknown` is a `decide` entry with the unknown stated in `summary`. Actions checked and found current need no entry and no note.

## Write the fragment

Keep each entry within the schema's word limits. Use `current_ref` and `latest_ref` for SHA or branch details.

Sort the remaining facts into the top-level lists:

- `batches`: actions that should move in one workflow edit, such as every action a single job pins.
- `blockers`: facts that change whether an upgrade can proceed, such as a self-hosted runner below the required version.
- `notes`: how the research was done, including sources that failed and what was used instead.
- `errors`: research that could not be completed.

Write `<output_dir>/DEPS_UPGRADE_REPORT_ACTIONS.json` with `surface` `actions`, `label` `GitHub Actions`, and `manager` `github-actions`, one entry per unique `owner/repo` and ref combination with all source locations retained in `locations`, and an empty `entries` list when every action is current. Sort entries by action priority (decide, migrate, hold, upgrade), then action name. Return the counts per action, the batch names, blockers, errors, and the absolute fragment path.
