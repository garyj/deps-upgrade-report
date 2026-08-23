#!/usr/bin/python3
# Pinned to /usr/bin/python3 deliberately: $PATH `python3` is often a
# uv-managed interpreter that errors when invoked inside a uv project whose
# requires-python doesn't match. This script only reads pyproject.toml and
# needs nothing from the project's interpreter.
"""List direct Python dependencies grouped by their declaration section.

Reads ./pyproject.toml and prints JSON mapping group -> sorted normalized names:
  - "main"          : [project.dependencies]
  - "optional:<n>"  : [project.optional-dependencies.<n>]
  - "<n>"           : PEP 735 [dependency-groups.<n>]
  - "build-system"  : [build-system].requires (build backends like uv_build,
                      hatchling, and setuptools are absent from `uv tree --outdated`
                      because they aren't in the project venv)

Names are PEP 503 normalized (lowercase, runs of [-_.] -> single dash) so they
match what `uv tree --outdated` emits.
"""
from __future__ import annotations

import json
import re
import sys
import tomllib
from typing import cast

PEP508_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def extract(spec: str) -> str | None:
    m = PEP508_NAME.match(spec.strip())
    return normalize(m.group(1)) if m else None


def table(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    raw_table = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in raw_table):
        return {}
    return cast(dict[str, object], value)


def names_from(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    out: set[str] = set()
    for spec in cast(list[object], value):
        if not isinstance(spec, str):
            continue  # PEP 735 include-group entries are dicts; skip
        n = extract(spec)
        if n:
            out.add(n)
    return sorted(out)


def main() -> int:
    try:
        with open("pyproject.toml", "rb") as f:
            raw: object = tomllib.load(f)
    except FileNotFoundError:
        sys.stderr.write("pyproject.toml not found in cwd\n")
        return 1
    data = table(raw)

    groups: dict[str, list[str]] = {}

    project = table(data.get("project"))
    main = names_from(project.get("dependencies"))
    if main:
        groups["main"] = main

    for name, deps in table(project.get("optional-dependencies")).items():
        names = names_from(deps)
        if names:
            groups[f"optional:{name}"] = names

    for name, deps in table(data.get("dependency-groups")).items():
        names = names_from(deps)
        if names:
            groups[name] = names

    build_system = table(data.get("build-system"))
    build_names = names_from(build_system.get("requires"))
    if build_names:
        groups["build-system"] = build_names

    json.dump(groups, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
