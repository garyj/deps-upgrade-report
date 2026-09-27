#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import threading
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast


STATE_NAME = 'DEPS_UPGRADE_PLAN.json'
PLAN_NAME = 'DEPS_UPGRADE_PLAN.md'
DECISIONS = {'', 'upgrade', 'skip', 'defer'}
MAX_BODY_BYTES = 4 * 1024 * 1024


class StateError(ValueError):
    pass


class ReviewServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], report: Path, output_dir: Path) -> None:
        super().__init__(address, ReviewHandler)
        self.report = report
        self.state_path = output_dir / STATE_NAME
        self.plan_path = output_dir / PLAN_NAME
        self.finished = False
        self.write_lock = threading.Lock()


def build_server(report: Path, output_dir: Path, port: int = 0) -> ReviewServer:
    return ReviewServer(('127.0.0.1', port), report.resolve(), output_dir.resolve())


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


def validate_state(value: object) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise StateError('state must be an object')
    raw = cast(dict[object, object], value)
    report_id = raw.get('report_id')
    if not isinstance(report_id, str) or not report_id:
        raise StateError('state.report_id must be a string')
    decisions = raw.get('decisions')
    if not isinstance(decisions, dict):
        raise StateError('state.decisions must be an object')
    clean: dict[str, dict[str, str]] = {}
    for key, entry in cast(dict[object, object], decisions).items():
        if not isinstance(key, str) or not isinstance(entry, dict):
            raise StateError('state.decisions entries must be objects keyed by item id')
        item = cast(dict[object, object], entry)
        decision = item.get('decision', '')
        note = item.get('note', '')
        if decision not in DECISIONS or not isinstance(decision, str):
            raise StateError(f'state.decisions[{key}].decision is not supported')
        if not isinstance(note, str):
            raise StateError(f'state.decisions[{key}].note must be a string')
        clean[key] = {'decision': decision, 'note': note}
    return {'report_id': report_id, 'decisions': clean}


def read_state(path: Path) -> dict[str, Any]:
    try:
        return validate_state(json.loads(path.read_text(encoding='utf-8')))
    except (OSError, ValueError):
        return {'report_id': None, 'decisions': {}}


class ReviewHandler(BaseHTTPRequestHandler):
    @property
    def review(self) -> ReviewServer:
        return cast(ReviewServer, self.server)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def send_json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json(status, {'error': message})

    def read_json_body(self) -> object:
        length = int(self.headers.get('Content-Length', '0'))
        if length <= 0:
            raise StateError('request body is empty')
        if length > MAX_BODY_BYTES:
            raise StateError('request body is too large')
        try:
            return json.loads(self.rfile.read(length).decode('utf-8'))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise StateError(f'request body is not JSON: {exc}') from exc

    def do_GET(self) -> None:
        review = self.review
        if self.path in ('/', '/index.html', f'/{review.report.name}'):
            try:
                body = review.report.read_bytes()
            except OSError as exc:
                self.send_error_json(HTTPStatus.NOT_FOUND, f'cannot read report: {exc}')
                return
            self.send_response(HTTPStatus.OK)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == '/api/state':
            state = read_state(review.state_path)
            state['state_file'] = str(review.state_path)
            state['plan_file'] = str(review.plan_path)
            self.send_json(HTTPStatus.OK, state)
            return
        self.send_error_json(HTTPStatus.NOT_FOUND, 'not found')

    def do_PUT(self) -> None:
        review = self.review
        if self.path != '/api/state':
            self.send_error_json(HTTPStatus.NOT_FOUND, 'not found')
            return
        try:
            state = validate_state(self.read_json_body())
        except StateError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        with review.write_lock:
            write_atomic(review.state_path, json.dumps(state, indent=2) + '\n')
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()

    def do_POST(self) -> None:
        review = self.review
        if self.path != '/api/finish':
            self.send_error_json(HTTPStatus.NOT_FOUND, 'not found')
            return
        try:
            body = self.read_json_body()
        except StateError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))
            return
        if not isinstance(body, dict):
            self.send_error_json(HTTPStatus.BAD_REQUEST, 'finish body must be an object')
            return
        payload = cast(dict[object, object], body)
        markdown = payload.get('markdown')
        if not isinstance(markdown, str) or not markdown.strip():
            self.send_error_json(HTTPStatus.BAD_REQUEST, 'finish.markdown must be a non-empty string')
            return
        with review.write_lock:
            write_atomic(review.plan_path, markdown)
            review.finished = True
        self.send_json(HTTPStatus.OK, {'plan': str(review.plan_path)})
        sys.stdout.write(markdown)
        sys.stdout.flush()
        threading.Thread(target=review.shutdown, daemon=True).start()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Serve a rendered report for review and collect decisions.')
    parser.add_argument('--report', type=Path, required=True, help='rendered DEPS_UPGRADE_REPORT.html')
    parser.add_argument('--output-dir', type=Path, help='where the decisions and plan are written (default: next to the report)')
    parser.add_argument('--port', type=int, default=0, help='port on 127.0.0.1 (default: any free port)')
    parser.add_argument('--no-open', action='store_true', help='do not open a browser')
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = cast(Path, args.report).resolve()
    if not report.is_file():
        sys.stderr.write(f'report not found: {report}\n')
        return 2
    output_dir = cast(Path | None, args.output_dir) or report.parent
    server = build_server(report, output_dir, cast(int, args.port))
    url = f'http://127.0.0.1:{server.server_port}/'
    sys.stderr.write(f'Review the report at {url}\n')
    sys.stderr.write(f'Decisions are saved to {server.state_path} as you go. Finish review writes {server.plan_path} and stops this server.\n')
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        sys.stderr.write(f'\nStopped before Finish review. Decisions stay in {server.state_path}; run this command again to resume.\n')
        return 130
    finally:
        server.server_close()
    return 0 if server.finished else 1


if __name__ == '__main__':
    sys.exit(main())
