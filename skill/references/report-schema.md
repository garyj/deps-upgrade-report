# Report fragment schema

Each worker writes one UTF-8 JSON object. The renderer validates required fields before producing HTML.

## Top-level fields

```json
{
  "schema_version": 1,
  "surface": "python",
  "label": "Python",
  "manager": "uv",
  "generated_at": "2026-08-23T12:34:56+10:00",
  "project_root": "/absolute/project/path",
  "entries": [],
  "warnings": [],
  "errors": []
}
```

Allowed surfaces are `python`, `node`, and `actions`. Managers are `uv`, `npm`, `pnpm`, and `github-actions`.

`generated_at` must include a timezone. `warnings` and `errors` are arrays of plain strings. An incomplete worker puts its failure in `errors`; it does not claim that dependencies are current.

## Entry fields

```json
{
  "name": "django",
  "current": "6.0.2",
  "latest": "6.0.4",
  "status": "safe",
  "group": "main",
  "changelog_url": "https://docs.djangoproject.com/en/6.0/releases/",
  "changes": [
    "Fixed an ORM regression affecting generated fields."
  ],
  "risk": "No affected API usage found in the project.",
  "recommendation": "Upgrade and run the Django test suite.",
  "locations": [
    {"path": "pyproject.toml", "line": 12}
  ]
}
```

Required entry fields are `name`, `current`, `latest`, `status`, `group`, `changelog_url`, `changes`, `risk`, `recommendation`, and `locations`.

Allowed statuses are:

- `breaking`: confirmed or plausible breaking change that needs migration work or focused testing
- `hold`: a declared constraint excludes latest, with its purpose stated only when evidence establishes it
- `unknown`: missing release notes, unresolved provenance, or incomplete compatibility evidence
- `safe`: no breaking change found after checking release notes and project usage

Optional `current_ref` and `latest_ref` fields preserve SHAs, branches, or exact action tags. `locations` contains repository-relative paths and positive line numbers. Use an empty list only when no declaration or affected usage can be located.

Keep `changes` concise. Summarize release notes instead of copying long passages. Every non-empty `changelog_url` must use `https://`.
