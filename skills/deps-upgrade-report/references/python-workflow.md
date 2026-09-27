# Python workflow

Read `report-schema.md` before writing the fragment. Run every command from the project root.

## Gather outdated dependencies

Run:

```bash
uv tree --outdated --all-groups --depth 1 --locked --format json
```

`--locked` prevents a reporting command from changing `uv.lock`. If the lockfile is absent or stale, write the error into the fragment and stop. Do not repair or regenerate the lockfile.

Run the direct-dependency helper:

```bash
<skill_dir>/scripts/list-direct-deps-python.py
```

Intersect the uv result with direct declarations. Keep the declaration group from the helper. Ignore transitive packages.

## Check build-system requirements

`uv tree` does not include build backends. For each direct `[build-system].requires` entry, query the package index and determine whether the declared constraint accepts the latest stable release. A requirement that already accepts latest needs no entry and no note.

## Research each outdated direct dependency

1. Find the canonical upstream repository or changelog from project metadata or the package index.
2. Read releases strictly after the current version through the latest stable version.
3. Check supported Python versions and relevant dependency requirements.
4. Search the project for affected imports, functions, configuration keys, and APIs.
5. Find the project's own commands for locking, testing, and type checking, such as a Makefile or justfile target, and use them in `steps` and `verify`.

Treat major version changes as potentially breaking. For `0.x` packages, treat minor changes as potentially breaking until release notes show otherwise. For CalVer packages, use the project's compatibility policy and explicit release-note markers instead of version arithmetic.

## Decide the action

- `upgrade` when release notes and project usage show no required change.
- `migrate` when the project must change code, configuration, or infrastructure. Put each change in `steps` and cite the path and line in `locations`.
- `decide` when a person must choose first: a constraint with no recorded reason, a licence change, an unrecorded production version. Name the decision in `summary`.
- `hold` only when the project records why the package must stay, such as a comment on the constraint or a linked issue. Say what would lift it in `steps`.

A declared constraint that excludes latest is a step ("widen `<2` to `<3` in `pyproject.toml`"), not a hold. Set `target` below latest when the safe move stops short, such as the last release of the current major.

## Write the fragment

Keep each entry within the schema's word limits. `changes` lists only releases that matter to this project; link the rest through `changelog_url`.

Sort the remaining facts into the top-level lists:

- `batches`: packages that must move in one change, such as a framework and the plugins that pin its major. Order the batches as they should be applied.
- `blockers`: facts that change whether an upgrade can proceed, such as a required database or Python version the project cannot confirm.
- `notes`: how the research was done, including sources that failed and what was used instead.
- `errors`: research that could not be completed.

Write `<output_dir>/DEPS_UPGRADE_REPORT_PYTHON.json` with `surface` `python`, `label` `Python`, and `manager` `uv`, one entry per outdated direct dependency or build-system requirement, and an empty `entries` list when all direct dependencies are current. Sort entries by action priority (decide, migrate, hold, upgrade), then package name. Return the counts per action, the batch names, blockers, errors, and the absolute fragment path.
