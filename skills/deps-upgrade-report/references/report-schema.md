# Report fragment schema

Each worker writes one UTF-8 JSON object. The renderer validates required fields and word limits before producing HTML. A fragment that exceeds a limit fails validation with the field name; trim that field rather than relaxing the limit.

## Top-level fields

```json
{
  "schema_version": 2,
  "surface": "python",
  "label": "Python",
  "manager": "uv",
  "generated_at": "2026-08-23T12:34:56+10:00",
  "project_root": "/absolute/project/path",
  "entries": [],
  "batches": [],
  "blockers": [],
  "notes": [],
  "errors": []
}
```

Allowed surfaces are `python`, `node`, and `actions`. Managers are `uv`, `npm`, `pnpm`, and `github-actions`. `generated_at` must include a timezone.

The four lists after `entries` hold different kinds of facts. Put each fact in exactly one of them:

- `batches`: groups of packages that must move together. Each is `{"name": "Django 6.1 line", "packages": ["django", "djangorestframework"], "reason": "DRF 3.17 imports a symbol Django 6.1 removed."}`. Every package must name an entry in the same fragment and appear in at most one batch. Order batches in the sequence they should be applied.
- `blockers`: project facts that change whether an upgrade can proceed, such as a production database version that is not recorded, or a licence change that needs sign-off. At most 60 words each. The report shows these first.
- `notes`: how the research was done. A changelog that returned 404, a date that looked wrong, a summary taken from commit subjects. The report collapses these by default.
- `errors`: research that could not be completed. An incomplete worker puts its failure here; it does not claim that dependencies are current.

## Entry fields

```json
{
  "name": "django",
  "current": "6.0.6",
  "latest": "6.1.1",
  "target": "6.1.1",
  "action": "migrate",
  "group": "main",
  "summary": "Move with DRF 3.18 in one batch; production PostgreSQL must be 15 or newer first.",
  "changes": [
    "Drops PostgreSQL 14; needs 15 or newer.",
    "Removes the undocumented cc_delim_re helper that DRF 3.17 imports."
  ],
  "risk": "DRF 3.17.1 fails at import time on Django 6.1. No other affected API usage found.",
  "steps": [
    "uv lock --upgrade-package django==6.1.1 --upgrade-package djangorestframework==3.18.0",
    "Confirm the production PostgreSQL version is 15 or newer before deploying."
  ],
  "verify": [
    "uv run pytest",
    "Open the admin and one API endpoint locally."
  ],
  "changelog_url": "https://docs.djangoproject.com/en/6.1/releases/6.1/",
  "locations": [
    {"path": "pyproject.toml", "line": 12}
  ]
}
```

Required entry fields are `name`, `current`, `latest`, `action`, `group`, `summary`, `changes`, `risk`, `steps`, `verify`, `changelog_url`, and `locations`. `target` is optional and defaults to `latest`; set it when the recommended move stops short of latest, such as taking the last minor of the current major.

Word limits, counted on whitespace:

| Field | Limit |
|---|---|
| `summary` | 30 words |
| `changes` | 4 items of 35 words |
| `risk` | 70 words |
| `steps` | 8 items of 40 words |
| `verify` | 5 items of 30 words |

`summary` says what to do and the one reason that matters. `changes` lists only releases that affect this project. `steps` are ordered; commands are proposals found in the project's own tooling and are not executed. `verify` names the checks that prove the upgrade worked.

Allowed actions:

- `upgrade`: bump and run the checks. No code or configuration change expected.
- `migrate`: the bump needs code, configuration, or infrastructure changes. `steps` says which.
- `decide`: a person must choose before an agent can proceed, such as a licence tier or an unrecorded production version. `summary` names the decision.
- `hold`: evidence in the project explains why the package must stay. `steps` says what would lift the hold.

A declared constraint that excludes `latest` is not a reason to hold. Widening the constraint is a step. Use `hold` only when the project records a reason, and `decide` when the reason is `❓ unknown`.

Optional `current_ref` and `latest_ref` preserve SHAs, branches, or exact action tags. `locations` contains repository-relative paths and positive line numbers. Use an empty list only when no declaration or affected usage can be located. Every non-empty `changelog_url` must use `https://`.
