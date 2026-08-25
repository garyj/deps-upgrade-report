#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "jinja2>=3.1,<4",
# ]
# ///
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import tempfile
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape


SURFACE_ORDER = {'python': 0, 'node': 1, 'actions': 2}
ALLOWED_MANAGERS = {'uv', 'npm', 'pnpm', 'github-actions'}
STATUS_ORDER = {'breaking': 0, 'hold': 1, 'unknown': 2, 'safe': 3}
TEMPLATE_DIR = Path(__file__).resolve().parents[1] / 'assets'
REQUIRED_ENTRY_FIELDS = {
    'name',
    'current',
    'latest',
    'status',
    'group',
    'changelog_url',
    'changes',
    'risk',
    'recommendation',
    'locations',
}


class FragmentError(ValueError):
    pass


def require_object(value: object, context: str) -> dict[str, object]:
    if not isinstance(value, dict):
        raise FragmentError(f'{context} must be an object')
    raw_object = cast(dict[object, object], value)
    if any(not isinstance(key, str) for key in raw_object):
        raise FragmentError(f'{context} must be an object with string keys')
    return cast(dict[str, object], value)


def require_string(value: Any, context: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise FragmentError(f'{context} must be a string')
    return value


def require_string_list(value: object, context: str) -> list[str]:
    if not isinstance(value, list):
        raise FragmentError(f'{context} must be an array of strings')
    items = cast(list[object], value)
    if any(not isinstance(item, str) for item in items):
        raise FragmentError(f'{context} must be an array of strings')
    return cast(list[str], items)


def validate_location(value: object, context: str) -> dict[str, object]:
    location = require_object(value, context)
    path = require_string(location.get('path'), f'{context}.path')
    line = location.get('line')
    if not isinstance(line, int) or isinstance(line, bool) or line < 1:
        raise FragmentError(f'{context}.line must be a positive integer')
    return {'path': path, 'line': line}


def validate_entry(value: object, context: str) -> dict[str, Any]:
    raw_entry = require_object(value, context)
    missing = REQUIRED_ENTRY_FIELDS - raw_entry.keys()
    if missing:
        raise FragmentError(f'{context} is missing: {", ".join(sorted(missing))}')

    entry: dict[str, Any] = dict(raw_entry)
    for field in ('name', 'current', 'latest', 'group', 'risk', 'recommendation'):
        entry[field] = require_string(entry[field], f'{context}.{field}')
    entry['changelog_url'] = require_string(
        entry['changelog_url'],
        f'{context}.changelog_url',
        allow_empty=True,
    )
    if entry['changelog_url'] and not entry['changelog_url'].startswith('https://'):
        raise FragmentError(f'{context}.changelog_url must use https://')

    status = require_string(entry['status'], f'{context}.status')
    if status not in STATUS_ORDER:
        raise FragmentError(f'{context}.status is not supported: {status}')

    entry['changes'] = require_string_list(entry['changes'], f'{context}.changes')
    locations: object = entry['locations']
    if not isinstance(locations, list):
        raise FragmentError(f'{context}.locations must be an array')
    entry['locations'] = [
        validate_location(location, f'{context}.locations[{index}]')
        for index, location in enumerate(cast(list[object], locations))
    ]

    for field in ('current_ref', 'latest_ref'):
        if field in entry:
            entry[field] = require_string(entry[field], f'{context}.{field}')
    return entry


def validate_fragment(value: object, source: Path, project_root: Path) -> dict[str, Any]:
    raw_fragment = require_object(value, f'{source}: root')
    if raw_fragment.get('schema_version') != 1:
        raise FragmentError(f'{source}: schema_version must be 1')

    surface = require_string(raw_fragment.get('surface'), f'{source}: surface')
    if surface not in SURFACE_ORDER:
        raise FragmentError(f'{source}: unsupported surface {surface}')
    manager = require_string(raw_fragment.get('manager'), f'{source}: manager')
    if manager not in ALLOWED_MANAGERS:
        raise FragmentError(f'{source}: unsupported manager {manager}')
    label = require_string(raw_fragment.get('label'), f'{source}: label')

    generated_at = require_string(raw_fragment.get('generated_at'), f'{source}: generated_at')
    try:
        timestamp = datetime.fromisoformat(generated_at)
    except ValueError as exc:
        raise FragmentError(f'{source}: generated_at is not ISO 8601') from exc
    if timestamp.tzinfo is None:
        raise FragmentError(f'{source}: generated_at must include a timezone')

    fragment_root = Path(require_string(raw_fragment.get('project_root'), f'{source}: project_root')).resolve()
    if fragment_root != project_root:
        raise FragmentError(f'{source}: project_root does not match {project_root}')

    raw_entries = raw_fragment.get('entries')
    if not isinstance(raw_entries, list):
        raise FragmentError(f'{source}: entries must be an array')
    entries = [
        validate_entry(entry, f'{source}: entries[{index}]')
        for index, entry in enumerate(cast(list[object], raw_entries))
    ]
    entries.sort(key=lambda entry: (STATUS_ORDER[entry['status']], entry['name'].casefold()))

    return {
        'schema_version': 1,
        'surface': surface,
        'label': label,
        'manager': manager,
        'generated_at': generated_at,
        'project_root': str(fragment_root),
        'entries': entries,
        'warnings': require_string_list(raw_fragment.get('warnings'), f'{source}: warnings'),
        'errors': require_string_list(raw_fragment.get('errors'), f'{source}: errors'),
    }


def load_fragments(paths: list[Path], project_root: Path) -> list[dict[str, Any]]:
    fragments: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        try:
            raw: object = json.loads(path.read_text())
        except OSError as exc:
            raise FragmentError(f'cannot read {path}: {exc}') from exc
        except json.JSONDecodeError as exc:
            raise FragmentError(f'{path}: invalid JSON: {exc}') from exc
        fragment = validate_fragment(raw, path, project_root)
        if fragment['surface'] in seen:
            raise FragmentError(f'duplicate surface: {fragment["surface"]}')
        seen.add(fragment['surface'])
        fragments.append(fragment)
    return sorted(fragments, key=lambda fragment: SURFACE_ORDER[fragment['surface']])


def slug(value: str) -> str:
    cleaned = re.sub(r'[^a-z0-9]+', '-', value.casefold()).strip('-')
    return cleaned or 'item'


def status_counts(entries: list[dict[str, Any]]) -> dict[str, int]:
    counts = Counter(entry['status'] for entry in entries)
    return {status: counts[status] for status in STATUS_ORDER}


def render_document(fragments: list[dict[str, Any]], project_root: Path) -> str:
    report_fragments: list[dict[str, Any]] = []
    total: Counter[str] = Counter()
    for fragment in fragments:
        counts = status_counts(fragment['entries'])
        total.update(counts)
        report_fragments.append({**fragment, 'counts': counts})

    environment = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(('html', 'xml', 'j2')),
        undefined=StrictUndefined,
    )
    environment.filters['slug'] = slug
    template = environment.get_template('report.html.j2')
    return template.render(
        project_name=project_root.name,
        project_root=project_root,
        generated=max(fragment['generated_at'] for fragment in fragments),
        fragments=report_fragments,
        overview={
            'outdated': sum(len(fragment['entries']) for fragment in fragments),
            'breaking': total['breaking'],
            'hold': total['hold'],
            'errors': sum(len(fragment['errors']) for fragment in fragments),
        },
    )


def write_atomic(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary_name = tempfile.mkstemp(prefix=f'.{path.name}.', dir=path.parent, text=True)
    try:
        with os.fdopen(handle, 'w', encoding='utf-8') as temporary:
            temporary.write(content)
        Path(temporary_name).replace(path)
    except BaseException:
        Path(temporary_name).unlink(missing_ok=True)
        raise


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--project-root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('fragments', nargs='+', type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = args.project_root.resolve()
    try:
        fragments = load_fragments(args.fragments, project_root)
        document = render_document(fragments, project_root)
        write_atomic(args.output.resolve(), document)
    except FragmentError as exc:
        sys.stderr.write(f'{exc}\n')
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
