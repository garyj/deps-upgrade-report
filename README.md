# Dependency upgrade report

A read-only agent skill that finds outdated direct dependencies, researches the relevant releases, checks how upgrades affect the codebase, and produces one self-contained HTML upgrade plan you can read and hand to an agent.

## Why this exists

Client projects sometimes sit untouched for months. Coming back to a stack of Dependabot PRs makes it hard to see the overall job before starting.

This skill gives you one page to scan first. It shows what is outdated, what needs a migration, what needs a decision, and what must be held, with the project locations that matter. For a bigger catch-up you can decide per package, and the decisions become a Markdown plan another agent can execute.

## What it checks

- Python dependencies managed by uv
- Node dependencies managed by npm or pnpm
- Pinned GitHub Actions in workflows, reusable workflows, and local or composite actions

The skill detects the dependency types present in the project and can research them in parallel when the agent supports delegation. It does not change manifests, lockfiles, installed packages, or workflows.

## The report

The page opens with anything to check before starting, then the batches of packages that must move together, then the remaining packages per dependency type. Each row shows the package, the version to move to, an action (upgrade, migrate, decide, or hold), a one-line summary, and a link to the release notes. Changes, steps, verification, and evidence sit behind an expander. Research notes are collapsed at the end. The page works directly from a `file://` URL and includes light and dark modes.

## The review server

`scripts/review-report.py` serves the same page on `127.0.0.1` and adds Upgrade, Skip, and Defer buttons and a note field to every row. It saves every decision to `DEPS_UPGRADE_PLAN.json` as it happens. Finish review in the page writes `DEPS_UPGRADE_PLAN.md`, prints it to stdout, and stops the server. Stopping early keeps the decisions; running the command again resumes them.

The plan opens with instructions for the executing agent and the blockers to check first. It then lists accepted upgrades by batch with their steps and verification, followed by the skipped, deferred, and undecided packages. A batch runs only when every package in it is accepted; otherwise it is listed as incomplete.

## Requirements

- An agent that supports `SKILL.md` skills and shell commands
- uv with support for `uv tree --format json`
- npm or pnpm when the project has Node dependencies
- GitHub CLI when the project has GitHub Actions
- Internet access for package metadata, changelogs, and release notes

The renderer declares Jinja2 and the review server declares FastAPI and uvicorn through PEP 723. uv installs them in isolated environments and uses the adjacent script lockfiles.

## Install

Install the skill from GitHub:

```bash
npx skills@latest add garyj/deps-upgrade-report
```

The installer prompts for the target agents and whether to install the skill for the current project or globally.

## Use

From a supported project, ask your agent:

```text
Generate a dependency upgrade report for this project.
```

or

```text
/deps-upgrade-report
```

The default output is `tmp/DEPS_UPGRADE_REPORT.html` inside the assessed project. You can request a different output directory.

To decide in the browser and get the plan back on disk:

```bash
uv run --script <skill_dir>/scripts/review-report.py --report tmp/DEPS_UPGRADE_REPORT.html
```

Then hand `tmp/DEPS_UPGRADE_PLAN.md` to an agent to execute.

## Development

Run the tests:

```bash
uv run --with jinja2 --with fastapi --with uvicorn python -m unittest discover -s skills/deps-upgrade-report/tests -v
```

Run strict type checking:

```bash
uv run --with jinja2 --with fastapi --with uvicorn pyright
```

## License

MIT. See [LICENSE](LICENSE).
