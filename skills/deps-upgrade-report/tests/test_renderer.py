from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any, cast


SKILL_DIR = Path(__file__).resolve().parents[1]
RENDERER_PATH = SKILL_DIR / 'scripts' / 'render-report.py'


def load_renderer():
    spec = importlib.util.spec_from_file_location('render_report', RENDERER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {RENDERER_PATH}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def entry(name: str, action: str = 'migrate', **overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        'name': name,
        'current': '1.0.0',
        'latest': '2.0.0',
        'action': action,
        'group': 'main',
        'summary': 'Migrate before upgrading.',
        'changes': ['Removed <legacy> API.'],
        'risk': 'Used by the project.',
        'steps': ['uv lock --upgrade-package example==2.0.0', 'Replace the <legacy> call.'],
        'verify': ['uv run pytest'],
        'changelog_url': 'https://example.com/releases',
        'locations': [{'path': 'src/example.py', 'line': 12}],
    }
    data.update(overrides)
    return data


def fragment(project_root: Path, surface: str = 'python', **overrides: Any) -> dict[str, Any]:
    managers = {'python': 'uv', 'node': 'pnpm', 'actions': 'github-actions'}
    labels = {'python': 'Python', 'node': 'Node', 'actions': 'GitHub Actions'}
    data: dict[str, Any] = {
        'schema_version': 2,
        'surface': surface,
        'label': labels[surface],
        'manager': managers[surface],
        'generated_at': '2026-08-23T12:34:56+10:00',
        'project_root': str(project_root),
        'entries': [entry('<unsafe-package>')],
        'batches': [],
        'blockers': [],
        'notes': [],
        'errors': [],
    }
    data.update(overrides)
    return data


def first_entry(data: dict[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], cast(list[Any], data['entries'])[0])


class RendererTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.renderer = load_renderer()

    def render(self, *fragments: dict[str, Any], project_root: Path) -> str:
        validated = [
            self.renderer.validate_fragment(data, Path(f'{data["surface"]}.json'), project_root)
            for data in fragments
        ]
        return self.renderer.render_document(validated, project_root)

    def test_renders_self_contained_review_page_and_escapes_content(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            data = fragment(
                project_root,
                entries=[entry('<unsafe-package>'), entry('helper', 'upgrade', target='1.5.0')],
                batches=[{'name': 'Core <move>', 'packages': ['<unsafe-package>'], 'reason': 'Moves together.'}],
                blockers=['Production database version is ❓ unknown.'],
                notes=['Changelog page returned 404; used GitHub releases.'],
            )

            document = self.render(data, project_root=project_root)

            self.assertIn('data-report-id=', document)
            self.assertIn('Batch 1: Core &lt;move&gt;', document)
            self.assertIn('data-decide="upgrade"', document)
            self.assertIn('data-decide="skip"', document)
            self.assertIn('data-decide="defer"', document)
            self.assertIn('Check before you start', document)
            self.assertIn('Python research notes (1)', document)
            self.assertIn('&lt;unsafe-package&gt;', document)
            self.assertNotIn('<unsafe-package>', document)
            self.assertIn('latest 2.0.0', document)
            self.assertIn('id="plan-data"', document)
            self.assertIn('@media print', document)
            self.assertIn(':root[data-theme="dark"]', document)
            self.assertIn('data-theme-toggle', document)
            self.assertIn("'/api/finish'", document)
            self.assertNotIn('<link ', document)
            self.assertNotIn('<script src=', document)

    def test_plan_data_orders_batches_then_remaining_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            python = fragment(
                project_root,
                entries=[entry('django'), entry('pytest', 'upgrade'), entry('ruff', 'decide')],
                batches=[{'name': 'Django line', 'packages': ['django', 'pytest'], 'reason': 'Same release train.'}],
            )
            node = fragment(project_root, 'node', entries=[entry('vite', 'upgrade')])

            validated = [
                self.renderer.validate_fragment(node, Path('node.json'), project_root),
                self.renderer.validate_fragment(python, Path('python.json'), project_root),
            ]
            validated.sort(key=lambda item: self.renderer.SURFACE_ORDER[item['surface']])
            report_fragments = [
                {**item, 'counts': self.renderer.action_counts(item['entries']), 'remaining': [
                    candidate for candidate in item['entries']
                    if candidate['name'] not in {member['name'] for batch in item['batches'] for member in batch['entries']}
                ]}
                for item in validated
            ]
            plan = self.renderer.plan_data(report_fragments, project_root, '2026-08-23T12:34:56+10:00', 'id')

            self.assertEqual([batch['number'] for batch in plan['batches']], [1])
            self.assertEqual(plan['batches'][0]['ids'], ['python-django', 'python-pytest'])
            self.assertEqual([section['ids'] for section in plan['sections']], [['python-ruff'], ['node-vite']])
            self.assertEqual(plan['items']['python-ruff']['action'], 'decide')

    def test_target_defaults_to_latest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            validated = self.renderer.validate_fragment(fragment(project_root), Path('python.json'), project_root)
            self.assertEqual(validated['entries'][0]['target'], '2.0.0')

    def test_rejects_non_https_changelog(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            data = fragment(project_root)
            first_entry(data)['changelog_url'] = 'http://example.com/releases'

            with self.assertRaisesRegex(self.renderer.FragmentError, 'https://'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

    def test_rejects_unsupported_action_and_old_schema(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            data = fragment(project_root)
            first_entry(data)['action'] = 'breaking'
            with self.assertRaisesRegex(self.renderer.FragmentError, 'action is not supported'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

            old = fragment(project_root, schema_version=1)
            with self.assertRaisesRegex(self.renderer.FragmentError, 'schema_version must be 2'):
                self.renderer.validate_fragment(old, Path('python.json'), project_root)

    def test_rejects_prose_over_word_limits(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            data = fragment(project_root)
            first_entry(data)['summary'] = ' '.join(['word'] * 31)
            with self.assertRaisesRegex(self.renderer.FragmentError, r'summary exceeds 30 words'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

            data = fragment(project_root)
            first_entry(data)['changes'] = ['one', 'two', 'three', 'four', 'five']
            with self.assertRaisesRegex(self.renderer.FragmentError, r'changes exceeds 4 items'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

            data = fragment(project_root)
            first_entry(data)['steps'] = [' '.join(['word'] * 41)]
            with self.assertRaisesRegex(self.renderer.FragmentError, r'steps\[0\] exceeds 40 words'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

            data = fragment(project_root, blockers=[' '.join(['word'] * 61)])
            with self.assertRaisesRegex(self.renderer.FragmentError, r'blockers\[0\] exceeds 60 words'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

    def test_rejects_batches_that_do_not_match_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            data = fragment(project_root, batches=[{'name': 'Core', 'packages': ['ghost'], 'reason': 'Because.'}])
            with self.assertRaisesRegex(self.renderer.FragmentError, 'unknown entry: ghost'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

            data = fragment(
                project_root,
                batches=[
                    {'name': 'Core', 'packages': ['<unsafe-package>'], 'reason': 'Because.'},
                    {'name': 'Again', 'packages': ['<unsafe-package>'], 'reason': 'Because.'},
                ],
            )
            with self.assertRaisesRegex(self.renderer.FragmentError, 'repeats <unsafe-package>'):
                self.renderer.validate_fragment(data, Path('python.json'), project_root)

    def test_rejects_duplicate_entry_names(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            project_root = Path(directory).resolve()
            data = fragment(project_root, entries=[entry('django'), entry('django')])
            with self.assertRaisesRegex(self.renderer.FragmentError, 'duplicate entry name django'):
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
