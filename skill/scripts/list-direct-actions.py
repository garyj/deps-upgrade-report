#!/usr/bin/python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


USES_RE = re.compile(r"^\s*-?\s*uses:\s*['\"]?([^'\"\s#]+)['\"]?\s*(?:#\s*(.*))?$")


def parse_uses(value: str) -> dict[str, str] | None:
    if value.startswith('docker://'):
        return None
    if value.startswith(('./', '$/')):
        return {'local': value}
    if '@' not in value:
        return None

    target, ref = value.rsplit('@', 1)
    parts = target.split('/')
    if len(parts) < 2:
        return None

    action = '/'.join(parts[:2])
    subpath = '/'.join(parts[2:])
    entry = {'action': action, 'ref': ref}
    if subpath:
        entry['subpath'] = subpath
        if subpath.startswith('.github/workflows/') and subpath.endswith(('.yml', '.yaml')):
            entry['type'] = 'reusable-workflow'
    return entry


def resolve_local(root: Path, value: str) -> Path | None:
    relative = value[2:] or '.'
    candidate = (root / relative).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None

    if candidate.suffix in {'.yml', '.yaml'}:
        return candidate if candidate.is_file() else None
    for name in ('action.yml', 'action.yaml'):
        action_file = candidate / name
        if action_file.is_file():
            return action_file
    return None


def scan_file(path: Path) -> tuple[list[dict[str, object]], list[str]]:
    entries: list[dict[str, object]] = []
    local_refs: list[str] = []
    seen: set[tuple[str, str, str]] = set()

    try:
        text = path.read_text()
    except OSError as exc:
        raise ValueError(f'failed to read {path}: {exc}') from exc

    for line_number, line in enumerate(text.splitlines(), start=1):
        match = USES_RE.match(line)
        if not match:
            continue
        parsed = parse_uses(match.group(1))
        if not parsed:
            continue
        if 'local' in parsed:
            local_refs.append(parsed['local'])
            continue

        key = (parsed['action'], parsed.get('subpath', ''), parsed['ref'])
        if key in seen:
            continue
        seen.add(key)
        entry: dict[str, object] = {**parsed, 'line': line_number}
        if match.group(2):
            entry['comment'] = match.group(2).strip()
        entries.append(entry)

    return entries, local_refs


def initial_files(root: Path) -> list[Path]:
    files: set[Path] = set()
    workflows = root / '.github' / 'workflows'
    if workflows.is_dir():
        files.update(path for path in workflows.iterdir() if path.suffix in {'.yml', '.yaml'})

    actions = root / '.github' / 'actions'
    if actions.is_dir():
        files.update(path for path in actions.rglob('action.yml'))
        files.update(path for path in actions.rglob('action.yaml'))

    for name in ('action.yml', 'action.yaml'):
        path = root / name
        if path.is_file():
            files.add(path)
    return sorted(files)


def main() -> int:
    root = Path.cwd().resolve()
    queue = initial_files(root)
    if not queue:
        sys.stderr.write('no workflow or action definition files found in cwd\n')
        return 1

    output: dict[str, list[dict[str, object]]] = {}
    scanned: set[Path] = set()
    while queue:
        path = queue.pop(0).resolve()
        if path in scanned:
            continue
        scanned.add(path)

        relative = path.relative_to(root).as_posix()
        try:
            entries, local_refs = scan_file(path)
        except ValueError as exc:
            sys.stderr.write(f'{exc}\n')
            return 2
        if entries:
            output[relative] = entries

        for reference in local_refs:
            resolved = resolve_local(root, reference)
            if resolved is None:
                sys.stderr.write(f'{relative}: could not resolve local action {reference!r}\n')
            elif resolved not in scanned:
                queue.append(resolved)

    json.dump(output, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write('\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
