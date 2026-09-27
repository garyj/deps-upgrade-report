# Node workflow

Use the manager reported by `detect-managers.py`. Read `report-schema.md` before writing the fragment.

## Gather outdated dependencies

For npm:

```bash
npm outdated --json
```

For pnpm:

```bash
pnpm outdated --format json
```

Add `--recursive` for a pnpm workspace when the report should cover every workspace package. Keep each workspace package as a distinct group so duplicate dependency names are not collapsed across packages.

Capture stdout, stderr, and the exit status separately. A non-zero result can mean outdated packages or a real command failure. Accept the result only when stdout parses as the expected JSON. If it does not, write the command error into the fragment and stop Node research.

Do not run npm in a pnpm project or pnpm in an npm project. Do not install, update, or regenerate a lockfile.

## Filter and group direct dependencies

Run:

```bash
<skill_dir>/scripts/list-direct-deps-node.py
```

Keep only packages declared in `dependencies`, `devDependencies`, `peerDependencies`, or `optionalDependencies`. For workspaces, include the workspace package name in the group label.

## Research each outdated direct dependency

1. Query package metadata with the selected manager.
2. Prefer the upstream repository's releases or changelog.
3. Read the releases strictly after the current version through the latest stable version.
4. Check the latest version's Node engine, package-manager engine, and peer dependencies against `package.json` and the other direct dependencies.
5. Search the project for affected imports, exports, configuration, and APIs.
6. Find the project's own build and test commands, such as `package.json` scripts or a Makefile target, and use them in `steps` and `verify`.

Treat a major version change as potentially breaking. For a `0.x` package, treat a minor change as potentially breaking until release notes show otherwise.

## Decide the action

- `upgrade` when release notes and project usage show no required change.
- `migrate` when the project must change code, configuration, or its Node version. Put each change in `steps` and cite the path and line in `locations`.
- `decide` when a person must choose first: a constraint with no recorded reason, a licence change, a peer-dependency conflict with another direct dependency. Name the decision in `summary`.
- `hold` only when the project records why the package must stay. Say what would lift it in `steps`.

A caret or tilde range that excludes latest is a step ("change `^29.0.0` to `^30.0.1` in `package.json`"), not a hold. Set `target` below latest when the safe move stops short, such as the last release inside the current range.

## Write the fragment

Keep each entry within the schema's word limits. `changes` lists only releases that matter to this project.

Sort the remaining facts into the top-level lists:

- `batches`: packages that must move in one change, such as a test runner and its environment package. Order the batches as they should be applied.
- `blockers`: facts that change whether an upgrade can proceed, such as an engine requirement the build image does not meet.
- `notes`: how the research was done, including sources that failed and what was used instead.
- `errors`: research that could not be completed.

Write `<output_dir>/DEPS_UPGRADE_REPORT_NODE.json` with `surface` `node`, `label` `Node`, and `manager` `npm` or `pnpm`, one entry per outdated direct dependency, and an empty `entries` list when all direct dependencies are current. Sort entries by action priority (decide, migrate, hold, upgrade), then package name. Return the counts per action, the batch names, blockers, errors, and the absolute fragment path.
