# Node workflow

Use the manager reported by `detect-managers.sh`. Read `report-schema.md` before writing the fragment.

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
4. Record concise change summaries and direct `https://` links.
5. If no changelog is available, record that fact and link to the package registry page.

Check the latest version's Node engine, package-manager engine, and peer dependencies. Compare them with `package.json` and the other direct dependencies. Record a blocking warning when the new requirements conflict.

Treat a major version change as potentially breaking. For a `0.x` package, treat a minor change as potentially breaking until release notes show otherwise. Search the project for affected imports, exports, configuration, and APIs. Cite exact project paths and lines when code uses an affected feature.

Do not infer why a package constraint exists. If a declared constraint excludes latest and no source explains it, set the status to `hold` and state `❓ unknown` for the reason.

## Write the fragment

Write `<output_dir>/DEPS_UPGRADE_REPORT_NODE.json` with:

- `surface`: `node`
- `label`: `Node`
- `manager`: `npm` or `pnpm`
- one entry per outdated direct dependency
- an empty `entries` list when all direct dependencies are current
- command or research failures in `errors`

Sort entries by status priority, then package name. Return the counts, errors, warnings, and absolute fragment path.
