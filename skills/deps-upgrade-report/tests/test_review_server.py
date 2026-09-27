from __future__ import annotations

import contextlib
import http.client
import importlib.util
import io
import json
import socket
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Any

import uvicorn

from test_renderer import entry, fragment, load_renderer


SKILL_DIR = Path(__file__).resolve().parents[1]
SERVER_PATH = SKILL_DIR / 'scripts' / 'review-report.py'


def load_server_module():
    spec = importlib.util.spec_from_file_location('review_report', SERVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {SERVER_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReviewServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_server_module()
        cls.renderer = load_renderer()

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.directory.name).resolve()
        data = fragment(
            self.output_dir,
            entries=[
                entry('django'),
                entry('django-stubs', 'upgrade'),
                entry('ruff', 'upgrade'),
                entry('celery', 'decide'),
                entry('black', 'hold'),
            ],
            batches=[{'name': 'Django line', 'packages': ['django', 'django-stubs'], 'reason': 'Stubs track Django.'}],
        )
        validated = self.renderer.validate_fragment(data, Path('python.json'), self.output_dir)
        self.report = self.output_dir / 'DEPS_UPGRADE_REPORT.html'
        self.report.write_text(self.renderer.render_document([validated], self.output_dir), encoding='utf-8')
        self.finished = threading.Event()
        self.server: uvicorn.Server | None = None

    def tearDown(self) -> None:
        if self.server is not None:
            self.server.should_exit = True
            self.thread.join(timeout=5)
        self.directory.cleanup()

    def start(self) -> None:
        def stop() -> None:
            self.finished.set()
            if self.server is not None:
                self.server.should_exit = True

        app = self.module.create_app(self.report, self.output_dir, stop)
        sock = socket.socket()
        sock.bind(('127.0.0.1', 0))
        sock.listen()
        self.port = sock.getsockname()[1]
        server = uvicorn.Server(uvicorn.Config(app, log_level='warning'))
        self.server = server
        self.thread = threading.Thread(target=server.run, kwargs={'sockets': [sock]}, daemon=True)
        self.thread.start()
        deadline = time.monotonic() + 5
        while not server.started and time.monotonic() < deadline:
            time.sleep(0.02)

    def request(self, method: str, path: str, body: object | None = None) -> tuple[int, Any]:
        connection = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        try:
            payload = None if body is None else json.dumps(body).encode('utf-8')
            headers = {'Content-Type': 'application/json'} if payload is not None else {}
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            raw = response.read()
            if response.getheader('Content-Type', '').startswith('application/json') and raw:
                return response.status, json.loads(raw)
            return response.status, raw.decode('utf-8')
        finally:
            connection.close()

    def test_saves_decisions_and_finish_writes_the_plan(self) -> None:
        self.start()
        status, page = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn('Batch 1: Django line', page)

        status, state = self.request('GET', '/api/state')
        self.assertEqual((status, state['decisions']), (200, {}))

        decisions = {
            'python-django': {'decision': 'upgrade', 'note': 'Check the admin first.'},
            'python-ruff': {'decision': 'upgrade', 'note': ''},
            'python-celery': {'decision': 'defer', 'note': ''},
            'python-black': {'decision': 'skip', 'note': ''},
        }
        status, _ = self.request('PUT', '/api/state', decisions)
        self.assertEqual(status, 204)
        status, state = self.request('GET', '/api/state')
        self.assertEqual(state['decisions'], decisions)

        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            status, result = self.request('POST', '/api/finish')
            self.thread.join(timeout=5)

        plan_path = self.output_dir / 'DEPS_UPGRADE_PLAN.md'
        self.assertEqual((status, result['plan']), (200, str(plan_path)))
        markdown = plan_path.read_text(encoding='utf-8')
        self.assertEqual(captured.getvalue(), markdown)
        self.assertTrue(self.finished.is_set())
        self.assertFalse(self.thread.is_alive())

        self.assertIn('Decisions: 2 upgrade, 1 skip, 1 defer, 1 undecided.', markdown)
        batch = markdown.index('## Batch 1: Django line (Python)')
        self.assertIn('Not in this run: django-stubs (undecided).', markdown)
        self.assertLess(batch, markdown.index('- [ ] django 1.0.0 -> 2.0.0 (migrate, Python)'))
        self.assertIn('  - Note: Check the admin first.', markdown)
        self.assertIn('    1. uv lock --upgrade-package example==2.0.0', markdown)
        self.assertIn('  - Release notes: https://example.com/releases', markdown)
        self.assertLess(markdown.index('## Python'), markdown.index('- [ ] ruff'))
        skipped = markdown.index('## Skipped')
        self.assertLess(skipped, markdown.index('- black 1.0.0 -> 2.0.0 (hold, Python)'))
        self.assertLess(markdown.index('## Deferred'), markdown.index('- celery'))
        self.assertLess(markdown.index('## Undecided'), markdown.index('- django-stubs'))
        self.assertEqual(markdown.count('Release notes:'), 2)

    def test_rejects_unknown_items_and_decisions(self) -> None:
        self.start()
        status, error = self.request('PUT', '/api/state', {'python-nope': {'decision': 'upgrade'}})
        self.assertEqual(status, 400)
        self.assertIn('python-nope', error['detail'])

        status, _ = self.request('PUT', '/api/state', {'python-django': {'decision': 'maybe'}})
        self.assertEqual(status, 422)
        self.assertFalse((self.output_dir / 'DEPS_UPGRADE_PLAN.json').exists())

    def test_ignores_decisions_saved_for_another_report(self) -> None:
        stale = {'report_id': 'older run', 'decisions': {'python-django': {'decision': 'upgrade', 'note': ''}}}
        (self.output_dir / 'DEPS_UPGRADE_PLAN.json').write_text(json.dumps(stale), encoding='utf-8')
        self.start()
        status, state = self.request('GET', '/api/state')
        self.assertEqual((status, state['decisions']), (200, {}))


if __name__ == '__main__':
    unittest.main()
