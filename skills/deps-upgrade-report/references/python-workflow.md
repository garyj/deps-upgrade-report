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

`uv tree` does not include build backends. For each direct `[build-system].requires` entry, query the package index and determine whether the declared constraint accepts the latest stable release.

An excluded version is evidence of a constraint, not evidence of its purpose. Use `hold` and state `❓ unknown` unless project comments, history, issues, or affected configuration establish the reason.

## Research each outdated direct dependency

1. Find the canonical upstream repository or changelog from project metadata or the package index.
2. Read releases strictly after the current version through the latest stable version.
3. Record concise change summaries and direct `https://` links.
4. Check supported Python versions and relevant dependency requirements.
5. Search the project for affected imports, functions, configuration keys, and APIs.

Treat major version changes as potentially breaking. For `0.x` packages, treat minor changes as potentially breaking until release notes show otherwise. For CalVer packages, use the project's compatibility policy and explicit release-note markers instead of version arithmetic.

For each breaking or held entry, cite exact project paths and lines when the code uses an affected feature. If the effect cannot be established, use `unknown` rather than inventing confidence.

## Write the fragment

Write `<output_dir>/DEPS_UPGRADE_REPORT_PYTHON.json` with:

- `surface`: `python`
- `label`: `Python`
- `manager`: `uv`
- one entry per outdated direct dependency or build-system requirement
- an empty `entries` list when all direct dependencies are current
- command or research failures in `errors`

Sort entries by status priority, then package name. Return the counts, errors, warnings, and absolute fragment path.
