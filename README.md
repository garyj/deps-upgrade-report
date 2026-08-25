# Dependency upgrade report

A read-only agent skill that finds outdated direct dependencies, researches the relevant releases, checks how upgrades affect the codebase, and produces one self-contained HTML report.

## Why this exists

Client projects sometimes sit untouched for months. Coming back to a stack of Dependabot PRs makes it hard to see the overall job before starting.

This skill gives you one report to scan first. It shows what is outdated, what may break, what should be held, and where the project uses the affected dependency. You can then plan the upgrade work without opening every dependency PR individually.

## What it checks

- Python dependencies managed by uv
- Node dependencies managed by npm or pnpm
- Pinned GitHub Actions in workflows, reusable workflows, and local or composite actions

The skill detects the dependency types present in the project and can research them in parallel when the agent supports delegation. It does not change manifests, lockfiles, installed packages, or workflows.

## The report

The generated HTML file has an overview and separate tabs for Python, Node, and GitHub Actions. Entries include release-note links, breaking-change assessments, recommendations, and project locations.

The report works directly from a `file://` URL, needs no web server, and includes light and dark modes. The selected colour mode is remembered locally.

## Requirements

- An agent that supports `SKILL.md` skills and shell commands
- uv with support for `uv tree --format json`
- npm or pnpm when the project has Node dependencies
- GitHub CLI when the project has GitHub Actions
- Internet access for package metadata, changelogs, and release notes

The HTML renderer declares Jinja2 through PEP 723. uv installs it in an isolated environment and uses the adjacent script lockfile.

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

## Development

Run the tests:

```bash
uv run --with jinja2 python -m unittest discover -s skills/deps-upgrade-report/tests -v
```

Run strict type checking:

```bash
uv run --with jinja2 pyright
```

## License

MIT. See [LICENSE](LICENSE).
