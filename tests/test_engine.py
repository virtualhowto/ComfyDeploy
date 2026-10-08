import json
import tempfile
import unittest
from pathlib import Path

from comfydeploy.engine import apply, load_manifest, plan, render, resolve
from comfydeploy.web import ControlPlane

M = {'schema_version': 1, 'components': {'a': {'type': 'service'}, 'b': {'type': 'service', 'requires': ['a']}}}


class EngineTests(unittest.TestCase):
    def test_dependency_order(self): self.assertEqual(resolve(M, ['b']), ['a', 'b'])

    def test_cycle(self):
        with self.assertRaises(ValueError): resolve({'components': {'a': {'requires': ['b']}, 'b': {'requires': ['a']}}}, ['a'])

    def test_render_contains_studio(self):
        with tempfile.TemporaryDirectory() as d:
            files = render(plan(M, ['b'], d))
            self.assertIn('studio:', files['compose.yaml'])
            self.assertIn('studio-config/config.json', files)

    def test_requires_approval(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): apply(plan(M, ['a'], d), M)

    def test_manifest(self):
        m = load_manifest()
        self.assertIn('studio', m['components'])
        self.assertIn('video', {p['id'] for p in m['packs']})

    def test_backend_render(self):
        m = load_manifest()
        with tempfile.TemporaryDirectory() as d:
            p = plan(m, ['studio', 'comfyui'], d)
            f = render(p)
            self.assertIn('gpus: all', f['compose.yaml'])
            self.assertIn('Dockerfile.comfyui', f)

    def test_reuse_backend(self):
        m = load_manifest()
        with tempfile.TemporaryDirectory() as d:
            p = plan(m, ['studio', 'comfyui'], d, {'reuse_backend': True})
            self.assertFalse(p['install_backend'])
            self.assertNotIn('gpus: all', render(p)['compose.yaml'])

    def test_plan_rejects_traversal(self):
        bad = {'components': {'x': {'type': 'model', 'url': 'https://huggingface.co/a', 'destination': '../oops'}}}
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError): plan(bad, ['x'], d)

    def test_control_plane_catalog_and_plan(self):
        with tempfile.TemporaryDirectory() as d:
            cp = ControlPlane(root=d)
            p = cp.make_plan({'packs': ['base', 'image'], 'options': {'install_backend': True}})
            self.assertIn('qwen-image', p['resolved'])
            self.assertTrue(p['install_backend'])
            with self.assertRaises(ValueError): cp.make_plan({'packs': ['unknown']})

    def test_control_plane_requires_approval(self):
        with tempfile.TemporaryDirectory() as d:
            cp = ControlPlane(root=d)
            with self.assertRaises(ValueError): cp.start_job({'packs': ['base']})

    def test_external_url_validation(self):
        with tempfile.TemporaryDirectory() as d:
            cp = ControlPlane(root=d)
            with self.assertRaises(ValueError): cp.make_plan({'options': {'llm_url': 'file:///etc/passwd'}})


if __name__ == '__main__': unittest.main()
