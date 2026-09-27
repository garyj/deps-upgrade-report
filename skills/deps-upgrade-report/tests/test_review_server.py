from __future__ import annotations

import contextlib
import http.client
import importlib.util
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from typing import Any


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

    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.output_dir = Path(self.directory.name).resolve()
        self.report = self.output_dir / 'DEPS_UPGRADE_REPORT.html'
        self.report.write_text('<!doctype html><title>report</title><p>hello</p>', encoding='utf-8')
        self.server = self.module.build_server(self.report, self.output_dir)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        if self.thread.is_alive():
            self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        self.directory.cleanup()

    def request(self, method: str, path: str, body: object | None = None) -> tuple[int, bytes]:
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=5)
        try:
            payload = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode('utf-8'))
            headers = {'Content-Type': 'application/json'} if payload is not None else {}
            connection.request(method, path, body=payload, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def request_json(self, method: str, path: str, body: object | None = None) -> tuple[int, dict[str, Any]]:
        status, raw = self.request(method, path, body)
        return status, json.loads(raw) if raw else {}

    def test_serves_report_and_round_trips_state(self) -> None:
        status, body = self.request('GET', '/')
        self.assertEqual(status, 200)
        self.assertIn(b'<p>hello</p>', body)

        status, state = self.request_json('GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(state['decisions'], {})
        self.assertIsNone(state['report_id'])
        self.assertEqual(state['state_file'], str(self.output_dir / 'DEPS_UPGRADE_PLAN.json'))

        saved = {'report_id': 'proj|2026', 'decisions': {'python-django': {'decision': 'upgrade', 'note': 'go'}}}
        status, _ = self.request('PUT', '/api/state', saved)
        self.assertEqual(status, 204)
        self.assertEqual(json.loads((self.output_dir / 'DEPS_UPGRADE_PLAN.json').read_text()), saved)

        status, state = self.request_json('GET', '/api/state')
        self.assertEqual(status, 200)
        self.assertEqual(state['report_id'], 'proj|2026')
        self.assertEqual(state['decisions'], saved['decisions'])

    def test_rejects_invalid_state(self) -> None:
        status, error = self.request_json('PUT', '/api/state', b'not json')
        self.assertEqual(status, 400)
        self.assertIn('not JSON', error['error'])

        status, error = self.request_json('PUT', '/api/state', {'report_id': 'x', 'decisions': {'a': {'decision': 'maybe'}}})
        self.assertEqual(status, 400)
        self.assertIn('decision is not supported', error['error'])
        self.assertFalse((self.output_dir / 'DEPS_UPGRADE_PLAN.json').exists())

        status, _ = self.request_json('GET', '/nope')
        self.assertEqual(status, 404)

    def test_finish_writes_plan_prints_it_and_stops(self) -> None:
        markdown = '# Plan\n\n- [ ] django 1 -> 2\n'
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured):
            status, result = self.request_json('POST', '/api/finish', {'report_id': 'proj|2026', 'markdown': markdown})
            self.thread.join(timeout=5)

        self.assertEqual(status, 200)
        self.assertEqual(result['plan'], str(self.output_dir / 'DEPS_UPGRADE_PLAN.md'))
        self.assertEqual((self.output_dir / 'DEPS_UPGRADE_PLAN.md').read_text(encoding='utf-8'), markdown)
        self.assertEqual(captured.getvalue(), markdown)
        self.assertFalse(self.thread.is_alive())
        self.assertTrue(self.server.finished)

    def test_finish_requires_markdown(self) -> None:
        status, error = self.request_json('POST', '/api/finish', {'report_id': 'proj|2026'})
        self.assertEqual(status, 400)
        self.assertIn('markdown', error['error'])
        self.assertTrue(self.thread.is_alive())


if __name__ == '__main__':
    unittest.main()
