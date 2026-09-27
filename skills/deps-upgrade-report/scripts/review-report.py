#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "fastapi>=0.115,<1",
#   "uvicorn>=0.30,<1",
# ]
# ///
import argparse
import json
import os
import re
import socket
import sys
import tempfile
import threading
import webbrowser
from collections.abc import Callable
from pathlib import Path
from typing import Any, Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ValidationError


STATE_NAME = 'DEPS_UPGRADE_PLAN.json'
PLAN_NAME = 'DEPS_UPGRADE_PLAN.md'
PLAN_DATA = re.compile(r'<script id="plan-data" type="application/json">(.*?)</script>', re.DOTALL)
INSTRUCTIONS = [
    'Apply the batches in order, then the remaining items. Finish a batch before starting the next.',
    "Run each item's verification before moving on. Stop and report at the first failure.",
    "Commands were proposed by the report, not executed. Check them against the project's own tooling first.",
    "Use the project's package manager for manifests and lockfiles; do not hand-edit lockfiles.",
    'Leave skipped, deferred, and undecided packages untouched, and every package in an incomplete batch.',
]


class Decision(BaseModel):
    decision: Literal['', 'upgrade', 'skip', 'defer'] = ''
    note: str = ''


class State(BaseModel):
    report_id: str
    decisions: dict[str, Decision]


def read_plan(report: Path) -> dict[str, Any]:
    match = PLAN_DATA.search(report.read_text(encoding='utf-8'))
    if match is None:
        raise ValueError(f'{report} has no plan data; render it with render-report.py')
    return json.loads(match.group(1))


def read_state(path: Path, report_id: str) -> State:
    try:
        state = State.model_validate_json(path.read_text(encoding='utf-8'))
    except (OSError, ValidationError):
        return State(report_id=report_id, decisions={})
    return state if state.report_id == report_id else State(report_id=report_id, decisions={})


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


def build_markdown(plan: dict[str, Any], state: State) -> str:
    items: dict[str, dict[str, Any]] = plan['items']

    def decision(item_id: str) -> Decision:
        return state.decisions.get(item_id, Decision())

    def block(item_id: str, accepted: bool) -> list[str]:
        item = items[item_id]
        heading = f'{item["name"]} {item["current"]} -> {item["target"]} ({item["action"]}, {item["surface_label"]})'
        lines = [f'- [ ] {heading}' if accepted else f'- {heading}']
        if note := decision(item_id).note.strip():
            lines.append(f'  - Note: {note}')
        if accepted:
            if item['current_ref'] or item['latest_ref']:
                lines.append(f'  - Refs: {item["current_ref"] or "❓ unknown"} -> {item["latest_ref"] or "❓ unknown"}')
            if item['steps']:
                lines.append('  - Steps:')
                lines += [f'    {number}. {step}' for number, step in enumerate(item['steps'], 1)]
            if item['verify']:
                lines.append('  - Verify:')
                lines += [f'    - {check}' for check in item['verify']]
            if item['changelog_url']:
                lines.append(f'  - Release notes: {item["changelog_url"]}')
        return lines

    by_decision: dict[str, list[str]] = {'upgrade': [], 'skip': [], 'defer': [], '': []}
    for item_id in items:
        by_decision[decision(item_id).decision].append(item_id)

    out = [
        f'# Dependency upgrade plan: {plan["project_name"]}',
        '',
        f'Source: DEPS_UPGRADE_REPORT.html generated {plan["generated"]} for {plan["project_root"]}.',
        f'Decisions: {len(by_decision["upgrade"])} upgrade, {len(by_decision["skip"])} skip, '
        f'{len(by_decision["defer"])} defer, {len(by_decision[""])} undecided.',
    ]
    if plan['blockers']:
        out += ['', '## Check before you start', '', 'Confirm each of these first. Stop and report if one blocks an accepted upgrade.', '']
        out += [f'- {blocker}' for blocker in plan['blockers']]
    if plan['errors']:
        out += ['', '## Incomplete research', '', 'The report could not finish this research. Upgrades it affects may carry unreported risk.', '']
        out += [f'- {error}' for error in plan['errors']]
    out += ['', '## Instructions for the executing agent', '', *[f'- {line}' for line in INSTRUCTIONS]]
    incomplete: list[dict[str, Any]] = []
    for batch in plan['batches']:
        accepted = [item_id for item_id in batch['ids'] if decision(item_id).decision == 'upgrade']
        if not accepted:
            continue
        if len(accepted) < len(batch['ids']):
            incomplete.append(batch)
            continue
        out += ['', f'## Batch {batch["number"]}: {batch["name"]} ({batch["surface_label"]})', '', f'Reason: {batch["reason"]}', '']
        for item_id in accepted:
            out += block(item_id, True)
    for section in plan['sections']:
        accepted = [item_id for item_id in section['ids'] if decision(item_id).decision == 'upgrade']
        if accepted:
            out += ['', f'## {section["label"]}', '']
            for item_id in accepted:
                out += block(item_id, True)
    if incomplete:
        out += ['', '## Incomplete batches', '', 'Not executed: a batch moves together, and not every package in these was accepted.', '']
        for batch in incomplete:
            members = ', '.join(f'{items[item_id]["name"]} ({decision(item_id).decision or "undecided"})' for item_id in batch['ids'])
            out.append(f'- Batch {batch["number"]}: {batch["name"]} ({batch["surface_label"]}): {members}')
    for key, title in (('skip', 'Skipped'), ('defer', 'Deferred'), ('', 'Undecided')):
        if by_decision[key]:
            out += ['', f'## {title}', '']
            for item_id in by_decision[key]:
                out += block(item_id, False)
    return '\n'.join(out) + '\n'


def create_app(report: Path, output_dir: Path, on_finish: Callable[[], None]) -> FastAPI:
    plan = read_plan(report)
    state_path = output_dir / STATE_NAME
    plan_path = output_dir / PLAN_NAME
    lock = threading.Lock()
    app = FastAPI(openapi_url=None)

    def page() -> str:
        return report.read_text(encoding='utf-8')

    def get_state() -> dict[str, Any]:
        state = read_state(state_path, plan['report_id'])
        return {'decisions': state.model_dump()['decisions'], 'state_file': str(state_path)}

    def put_state(decisions: dict[str, Decision]) -> Response:
        unknown = sorted(set(decisions) - set(plan['items']))
        if unknown:
            raise HTTPException(400, f'unknown item ids: {", ".join(unknown)}')
        with lock:
            state = State(report_id=plan['report_id'], decisions=decisions)
            write_atomic(state_path, state.model_dump_json(indent=2) + '\n')
        return Response(status_code=204)

    def finish() -> dict[str, str]:
        with lock:
            markdown = build_markdown(plan, read_state(state_path, plan['report_id']))
            write_atomic(plan_path, markdown)
        sys.stdout.write(markdown)
        sys.stdout.flush()
        on_finish()
        return {'plan': str(plan_path)}

    app.add_api_route('/', page, response_class=HTMLResponse)
    app.add_api_route('/api/state', get_state)
    app.add_api_route('/api/state', put_state, methods=['PUT'], status_code=204)
    app.add_api_route('/api/finish', finish, methods=['POST'])
    return app


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Serve a rendered report for review and collect decisions.')
    parser.add_argument('--report', type=Path, required=True, help='rendered DEPS_UPGRADE_REPORT.html')
    parser.add_argument('--output-dir', type=Path, help='where the decisions and plan are written (default: next to the report)')
    parser.add_argument('--port', type=int, default=0, help='port on 127.0.0.1 (default: any free port)')
    parser.add_argument('--no-open', action='store_true', help='do not open a browser')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report: Path = args.report.resolve()
    if not report.is_file():
        sys.stderr.write(f'report not found: {report}\n')
        return 2
    output_dir: Path = (args.output_dir or report.parent).resolve()
    finished = threading.Event()

    def stop() -> None:
        finished.set()
        server.should_exit = True

    try:
        app = create_app(report, output_dir, stop)
    except ValueError as exc:
        sys.stderr.write(f'{exc}\n')
        return 2
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', args.port))
    sock.listen()
    server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}/'
    sys.stderr.write(f'Review the report at {url}\n')
    sys.stderr.write(f'Decisions are saved to {output_dir / STATE_NAME} as you go. '
                     f'Finish review writes {output_dir / PLAN_NAME} and stops this server.\n')
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.run(sockets=[sock])
    except KeyboardInterrupt:
        pass
    if finished.is_set():
        return 0
    sys.stderr.write(f'Stopped before Finish review. Decisions stay in {output_dir / STATE_NAME}; run this command again to resume.\n')
    return 130


if __name__ == '__main__':
    sys.exit(main())
