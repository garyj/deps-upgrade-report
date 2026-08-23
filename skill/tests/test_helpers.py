from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / 'scripts'


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load {path}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class DetectManagersTests(unittest.TestCase):
    def run_detector(self, root: Path, commands: tuple[str, ...]) -> dict[str, object]:
        bin_dir = root / 'bin'
        bin_dir.mkdir()
        for command in commands:
            (bin_dir / command).symlink_to('/bin/true')
        environment = {**os.environ, 'PATH': str(bin_dir)}
        result = subprocess.run(
            [str(SCRIPTS_DIR / 'detect-managers.py')],
            cwd=root,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )
        return json.loads(result.stdout)

    def test_detects_pnpm_from_declaration_and_lockfile(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'package.json').write_text('{"packageManager":"pnpm@11.16.0"}\n')
            (root / 'pnpm-lock.yaml').touch()

            detected = self.run_detector(root, ('pnpm',))

            self.assertTrue(detected['node'])
            self.assertEqual(detected['node_manager'], 'pnpm')

    def test_rejects_conflicting_lockfiles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'package.json').write_text('{}\n')
            (root / 'package-lock.json').touch()
            (root / 'pnpm-lock.yaml').touch()

            detected = self.run_detector(root, ('npm', 'pnpm'))

            self.assertFalse(detected['node'])
            self.assertEqual(detected['node_manager'], 'conflict')
            error = detected['node_error']
            if not isinstance(error, str):
                self.fail('node_error must be a string')
            self.assertIn('conflicting', error)

    def test_refuses_to_guess_without_a_manager_signal(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'package.json').write_text('{}\n')

            detected = self.run_detector(root, ('npm', 'pnpm'))

            self.assertFalse(detected['node'])
            self.assertEqual(detected['node_manager'], 'unknown')


class ActionsParserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module('list_direct_actions', SCRIPTS_DIR / 'list-direct-actions.py')

    def test_splits_action_repository_from_subpath(self) -> None:
        parsed = self.module.parse_uses('github/codeql-action/init@v3')

        self.assertEqual(
            parsed,
            {'action': 'github/codeql-action', 'subpath': 'init', 'ref': 'v3'},
        )

    def test_classifies_reusable_workflow(self) -> None:
        parsed = self.module.parse_uses('owner/repo/.github/workflows/check.yml@v2')

        self.assertEqual(parsed['action'], 'owner/repo')
        self.assertEqual(parsed['subpath'], '.github/workflows/check.yml')
        self.assertEqual(parsed['type'], 'reusable-workflow')

    def test_recognises_self_repository_reference(self) -> None:
        self.assertEqual(
            self.module.parse_uses('$/tools/check'),
            {'local': '$/tools/check'},
        )


if __name__ == '__main__':
    unittest.main()
