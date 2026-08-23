#!/usr/bin/python3
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path


SUPPORTED_NODE_MANAGERS = {'npm', 'pnpm'}
LOCKFILE_MANAGERS = {
    'package-lock.json': 'npm',
    'npm-shrinkwrap.json': 'npm',
    'pnpm-lock.yaml': 'pnpm',
}


def package_manager_declaration(package_json: Path) -> str | None:
    try:
        data = json.loads(package_json.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f'cannot read {package_json}: {exc}') from exc

    value = data.get('packageManager')
    if not isinstance(value, str) or not value:
        return None
    return value.split('@', 1)[0]


def detect_node(root: Path) -> dict[str, object]:
    package_json = root / 'package.json'
    if not package_json.is_file():
        return {'node': False, 'node_manager': None, 'node_signals': [], 'node_error': None}

    signals: list[str] = []
    managers: set[str] = set()

    try:
        declared = package_manager_declaration(package_json)
    except ValueError as exc:
        return {
            'node': False,
            'node_manager': 'unknown',
            'node_signals': ['package.json'],
            'node_error': str(exc),
        }

    if declared:
        signals.append(f'packageManager={declared}')
        if declared not in SUPPORTED_NODE_MANAGERS:
            return {
                'node': False,
                'node_manager': 'unsupported',
                'node_signals': signals,
                'node_error': f'unsupported package manager declared: {declared}',
            }
        managers.add(declared)

    for filename, manager in LOCKFILE_MANAGERS.items():
        if (root / filename).is_file():
            signals.append(filename)
            managers.add(manager)

    if len(managers) > 1:
        return {
            'node': False,
            'node_manager': 'conflict',
            'node_signals': signals,
            'node_error': 'conflicting Node package-manager signals',
        }

    if not managers:
        return {
            'node': False,
            'node_manager': 'unknown',
            'node_signals': ['package.json'],
            'node_error': 'package.json exists but no supported package-manager signal was found',
        }

    manager = managers.pop()
    if shutil.which(manager) is None:
        return {
            'node': False,
            'node_manager': manager,
            'node_signals': signals,
            'node_error': f'{manager} is required but is not on PATH',
        }

    return {'node': True, 'node_manager': manager, 'node_signals': signals, 'node_error': None}


def has_actions(root: Path) -> bool:
    workflows = root / '.github' / 'workflows'
    if workflows.is_dir() and any(path.suffix in {'.yml', '.yaml'} for path in workflows.iterdir()):
        return True

    actions = root / '.github' / 'actions'
    if actions.is_dir() and any(path.name in {'action.yml', 'action.yaml'} for path in actions.rglob('action.y*ml')):
        return True

    return any((root / name).is_file() for name in ('action.yml', 'action.yaml'))


def detect(root: Path) -> dict[str, object]:
    result: dict[str, object] = {
        'python': (root / 'pyproject.toml').is_file() and shutil.which('uv') is not None,
        'actions': has_actions(root) and shutil.which('gh') is not None,
    }
    result.update(detect_node(root))
    return result


def main() -> int:
    root = Path.cwd()
    json.dump(detect(root), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
