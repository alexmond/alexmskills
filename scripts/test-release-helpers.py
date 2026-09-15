#!/usr/bin/env python3
"""Exercise release helpers against disposable marketplace fixtures."""
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent.parent


class ReleaseHelpers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        shutil.copy(ROOT / 'Makefile', self.root)
        shutil.copytree(ROOT / 'scripts', self.root / 'scripts')
        self.catalog = self.root / '.claude-plugin/marketplace.json'
        self.manifest = self.root / 'plugins/example/.claude-plugin/plugin.json'
        self.write(self.catalog, {
            'name': 'fixture', 'owner': {'name': 'Test'},
            'plugins': [{'name': 'example', 'version': '1.0.0',
                         'source': './plugins/example'}],
        })
        self.write(self.manifest, {'name': 'example', 'version': '1.0.0'})
        (self.root / 'plugins/example/skills').mkdir()
        result = self.run_command('python3', 'scripts/gen-codex-manifests.py')
        self.assertEqual(result.returncode, 0, result.stdout)

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def run_command(self, *args):
        return subprocess.run(args, cwd=self.root, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def test_matching_versions_pass(self):
        result = self.run_command('make', 'validate')
        self.assertEqual(result.returncode, 0, result.stdout)

    def test_version_drift_fails_and_later_gates_run(self):
        catalog = json.loads(self.catalog.read_text())
        catalog['plugins'][0]['version'] = '99.99.99'
        self.write(self.catalog, catalog)
        result = self.run_command('make', 'validate')
        self.assertNotEqual(result.returncode, 0, result.stdout)
        self.assertIn("plugin.json version '1.0.0' != marketplace version '99.99.99'", result.stdout)
        self.assertIn('Description budget', result.stdout)
        self.assertIn('Codex packaging', result.stdout)

    def test_successful_bump_updates_both(self):
        result = self.run_command('make', 'bump', 'PLUGIN=example', 'VERSION=1.1.0')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual(json.loads(self.manifest.read_text())['version'], '1.1.0')
        self.assertEqual(json.loads(self.catalog.read_text())['plugins'][0]['version'], '1.1.0')

    def test_failed_bumps_preserve_inputs(self):
        catalog = self.catalog.read_text()
        manifest = self.manifest.read_text()
        cases = [
            ('missing plugin', 'missing', catalog, manifest),
            ('invalid manifest', 'example', catalog, '{'),
            ('invalid catalog', 'example', '{', manifest),
            ('uncatalogued plugin', 'example', '{"plugins": []}', manifest),
            ('duplicate entry', 'example', json.dumps({'plugins':
                json.loads(catalog)['plugins'] * 2}), manifest),
        ]
        for label, name, catalog_text, manifest_text in cases:
            with self.subTest(label=label):
                self.catalog.write_text(catalog_text)
                self.manifest.write_text(manifest_text)
                result = self.run_command('make', 'bump', f'PLUGIN={name}', 'VERSION=1.1.0')
                self.assertNotEqual(result.returncode, 0, result.stdout)
                self.assertNotIn('Bumped ', result.stdout)
                self.assertEqual(self.catalog.read_text(), catalog_text)
                self.assertEqual(self.manifest.read_text(), manifest_text)


if __name__ == '__main__':
    unittest.main()
