---
name: deps-upgrade-report
description: Generate one self-contained HTML dependency upgrade plan for uv/Python, npm or pnpm/Node, and pinned GitHub Actions, and optionally collect per-package upgrade, skip, or defer decisions for an agent to execute. Use for outdated dependency checks, upgrade planning, changelog research, breaking-change assessment, or dependency audit reports. The workflow is read-only and does not update dependency files, lockfiles, or workflows.
---

# Dependency upgrade report

Produce one HTML upgrade plan from normalized JSON fragments. Detect the project's supported dependency types, research each detected type, assess its effect on the actual codebase, and render the fragments into one file. When the user wants to decide per package, serve the report and collect the decisions as a Markdown plan another agent can execute.

## Invariants

- Treat the project as read-only. Do not update manifests, lockfiles, workflows, dependencies, or generated clients.
- Respect the declared Node package manager. If package-manager signals conflict, record `❓ unknown` and do not run a Node outdated command.
- State unknown intent or provenance as `❓ unknown`. A version cap or inline SHA comment is evidence, not proof of why a version was chosen.
- Write a fragment even when no upgrades are found. An empty current fragment prevents an older report being mistaken for current output.
- Keep fragments within the schema's word limits. The report is read in one sitting; research detail belongs in `notes` and behind `changelog_url`.
- Use absolute paths in worker prompts and commands.

## Step 1: choose paths

Resolve these paths before starting:

- `project_root`: the repository being assessed
- `skill_dir`: this skill's directory
- `output_dir`: the requested output directory, or `<project_root>/tmp` when none was requested

Create `output_dir`. When it is inside a Git repository, check the actual output path with `git check-ignore`. Warn before writing if Git does not ignore it.

## Step 2: detect dependency types

Run from `project_root`:

```bash
<skill_dir>/scripts/detect-managers.py
```

The JSON result identifies Python, Node, and Actions. Node also includes `node_manager` with `npm`, `pnpm`, `conflict`, or `null`.

If no supported type is detected, tell the user and stop. If Node reports `conflict`, include the reported signals in the final summary and skip Node dependency research.

## Step 3: generate report fragments

For each detected type, read its workflow and `references/report-schema.md`:

- Python: `references/python-workflow.md`
- Node: `references/node-workflow.md`
- GitHub Actions: `references/actions-workflow.md`

When delegation is available, start one worker per detected type without waiting for earlier workers to finish. When it is unavailable, perform the same workflows sequentially. Each worker receives `project_root`, `skill_dir`, `output_dir`, and the detected manager. Each worker writes one of:

- `DEPS_UPGRADE_REPORT_PYTHON.json`
- `DEPS_UPGRADE_REPORT_NODE.json`
- `DEPS_UPGRADE_REPORT_ACTIONS.json`

Workers must return counts per action, batch names, blockers, errors, and the absolute fragment path. A worker that cannot complete its research writes a valid fragment with an `errors` entry instead of pretending the dependency type is current.

## Step 4: render the HTML report

After every worker finishes, run:

```bash
uv run --script <skill_dir>/scripts/render-report.py \
  --project-root <project_root> \
  --output <output_dir>/DEPS_UPGRADE_REPORT.html \
  <fragment paths...>
```

The PEP 723 renderer installs its locked Jinja2 dependency through uv, validates the fragments, and produces one self-contained HTML file. If validation reports a field over its word limit, fix that field in the fragment and render again; do not relax the limit.

The page lists blockers first, then batches in order, then the remaining packages per dependency type, with research notes collapsed at the end. Every package row shows its summary and release notes link; changes, steps, and evidence sit behind an expander. Opened from a `file://` URL it is a read-only report.

## Step 5: collect decisions

Offer the review server when the user wants to decide now or hand the upgrades to an agent:

```bash
uv run --script <skill_dir>/scripts/review-report.py \
  --report <output_dir>/DEPS_UPGRADE_REPORT.html
```

It serves the report on `127.0.0.1`, opens a browser, and adds Upgrade, Skip, and Defer buttons and a note field to every row. Every decision is saved to `<output_dir>/DEPS_UPGRADE_PLAN.json` as it happens. Finish review in the page writes `<output_dir>/DEPS_UPGRADE_PLAN.md`, prints the same Markdown to stdout, and stops the server. Stopping it early keeps the decisions; running it again resumes them. The PEP 723 script installs FastAPI and uvicorn through uv.

When the shell has a time limit, run it in the background and read `DEPS_UPGRADE_PLAN.md` once it exists. When the user only wants the report, skip this step; they can hand the report itself to an agent.

The plan is the hand-off for the upgrade work. Executing it is a separate task; this skill changes nothing in the project.

## Step 6: verify and return

- Confirm the HTML exists and is non-empty.
- Open it in a browser and check the blockers, the first batch, one release notes link, and one expanded package at desktop and narrow widths.
- Confirm external links use `https://` and no local project content is embedded beyond the report evidence.
- Confirm `git status --short` for `project_root` is unchanged except for an explicitly approved output path.

Return the absolute HTML path, counts per action for each dependency type, the batch names, blockers, any incomplete research, and the plan path when a review ran. Do not present a partial report as complete.

End the reply with the commands to open the report and to review it, filled in with the real paths:

```bash
xdg-open <output_dir>/DEPS_UPGRADE_REPORT.html
uv run --script <skill_dir>/scripts/review-report.py --report <output_dir>/DEPS_UPGRADE_REPORT.html
```

Use `open` instead of `xdg-open` on macOS.

## Bundled resources

- `references/report-schema.md` defines the worker fragment contract, including the word limits and the action semantics.
- The three workflow references define type-specific gathering and research.
- `scripts/detect-managers.py` detects supported tools and the Node package manager.
- `scripts/list-direct-deps-python.py`, `scripts/list-direct-deps-node.py`, and `scripts/list-direct-actions.py` extract direct dependency declarations.
- `scripts/render-report.py` validates fragments and renders the final HTML from `assets/report.html.j2`.
- `scripts/review-report.py` serves the report locally, saves decisions, and writes the plan.
