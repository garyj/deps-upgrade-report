#!/usr/bin/python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import cast


DEPENDENCY_GROUPS = ('dependencies', 'devDependencies', 'peerDependencies', 'optionalDependencies')


def read_package(path: Path, root: Path) -> dict[str, object]:
    try:
        raw: object = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'cannot read {path}: {exc}') from exc
    if not isinstance(raw, dict):
        raise ValueError(f'{path} must contain a JSON object')
    raw_data = cast(dict[object, object], raw)
    if any(not isinstance(key, str) for key in raw_data):
        raise ValueError(f'{path} must contain a JSON object with string keys')
    data = cast(dict[str, object], raw)

    groups: dict[str, list[str]] = {}
    for group in DEPENDENCY_GROUPS:
        values = data.get(group)
        if not isinstance(values, dict):
            continue
        raw_values = cast(dict[object, object], values)
        names = sorted(name for name in raw_values if isinstance(name, str))
        if names:
            groups[group] = names
    relative_parent = path.parent.relative_to(root).as_posix()
    return {
        'name': data.get('name') if isinstance(data.get('name'), str) else relative_parent,
        'path': '.' if relative_parent == '.' else relative_parent,
        'groups': groups,
    }


def pnpm_workspace_package_files(root: Path) -> list[Path]:
    command = ['pnpm', '--recursive', 'list', '--depth', '-1', '--json']
    result = subprocess.run(command, cwd=root, check=False, capture_output=True, text=True)
    if result.returncode != 0:
        message = result.stderr.strip() or f'pnpm exited with {result.returncode}'
        raise ValueError(f'cannot list pnpm workspace packages: {message}')

    try:
        raw: object = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f'pnpm returned invalid workspace JSON: {exc}') from exc
    if not isinstance(raw, list):
        raise ValueError('pnpm workspace JSON must be an array')

    files = {root / 'package.json'}
    for item in cast(list[object], raw):
        if not isinstance(item, dict):
            continue
        raw_project = cast(dict[object, object], item)
        if any(not isinstance(key, str) for key in raw_project):
            continue
        project = cast(dict[str, object], item)
        project_path = project.get('path')
        if isinstance(project_path, str):
            package_file = Path(project_path) / 'package.json'
            if package_file.is_file():
                files.add(package_file.resolve())
    return sorted(files)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--manager', choices=('npm', 'pnpm'), required=True)
    parser.add_argument('--recursive', action='store_true')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path.cwd().resolve()
    package_files = [root / 'package.json']
    if args.recursive:
        if args.manager != 'pnpm':
            sys.stderr.write('recursive workspace discovery is currently supported for pnpm only\n')
            return 2
        try:
            package_files = pnpm_workspace_package_files(root)
        except ValueError as exc:
            sys.stderr.write(f'{exc}\n')
            return 2

    try:
        packages = [read_package(path, root) for path in package_files]
    except ValueError as exc:
        sys.stderr.write(f'{exc}\n')
        return 1

    json.dump({'packages': packages}, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
