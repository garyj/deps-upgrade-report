from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import cast


SKILL_DIR = Path(__file__).resolve().parents[1]
RENDERER_PATH = SKILL_DIR / 'scripts' / 'render-report.py'


def load_renderer():
    spec = importlib.util.spec_from_file_location('render_report', RENDERER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {RENDERER_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def fragment(project_root: Path, surface: str = 'python') -> dict[str, object]:
    managers = {'python': 'uv', 'node': 'pnpm', 'actions': 'github-actions'}
    labels = {'python': 'Python', 'node': 'Node', 'actions': 'GitHub Actions'}
    return {
        'schema_version': 1,
        'surface': surface,
        'label': labels[surface],
        'manager': managers[surface],
        'generated_at': '2026-08-23T12:34:56+10:00',
        'project_root': str(project_root),
        'entries': [
            {
                'name': '<unsafe-package>',
                'current': '1.0.0',
                'latest': '2.0.0',
                'status': 'breaking',
                'group': 'main',
                'changelog_url': 'https://example.com/releases',
                'changes': ['Removed <legacy> API.'],
                'risk': 'Used by the project.',
                'recommendation': 'Migrate before upgrading.',
                'locations': [{'path': 'src/example.py', 'line': 12}],
            }
        ],
        'warnings': [],
        'errors': [],
    }


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.renderer = load_renderer()

    def test_renders_self_contained_tabbed_report_and_escapes_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            data = fragment(project_root)

            validated = self.renderer.validate_fragment(data, Path('python.json'), project_root)
            document = self.renderer.render_document([validated], project_root)

            self.assertIn('data-tab="overview"', document)
            self.assertIn('data-tab="python"', document)
            self.assertIn('&lt;unsafe-package&gt;', document)
            self.assertNotIn('<unsafe-package>', document)
            self.assertIn('@media print', document)
            self.assertIn(':root[data-theme="dark"]', document)
            self.assertIn('color-scheme: dark', document)
            self.assertIn('data-theme-toggle', document)
            self.assertIn("localStorage.setItem(key, value)", document)
            self.assertIn("addEventListener('beforeprint'", document)
            self.assertNotIn('<link ', document)
            self.assertNotIn('<script src=', document)

    def test_rejects_non_https_changelog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            data = fragment(project_root)
            entries = data['entries']
            if not isinstance(entries, list):
                self.fail('entries must be a list')
            entry = cast(dict[str, object], cast(list[object], entries)[0])
            entry['changelog_url'] = 'http://example.com/releases'

            with self.assertRaisesRegex(self.renderer.FragmentError, 'https://'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

    def test_rejects_duplicate_surfaces(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            first = root / 'first.json'
            second = root / 'second.json'
            first.write_text(json.dumps(fragment(root)))
            second.write_text(json.dumps(fragment(root)))

            with self.assertRaisesRegex(self.renderer.FragmentError, 'duplicate surface'):
                self.renderer.load_fragments([first, second], root)


if __name__ == '__main__':
    unittest.main()
