import importlib.util
from pathlib import Path
import unittest
import tempfile
import hashlib
import json

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('export_site', ROOT / 'scripts/export-site.py')
export_site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_site)

manifest_spec = importlib.util.spec_from_file_location('build_manifest', ROOT / 'scripts/write-build-manifest.py')
build_manifest = importlib.util.module_from_spec(manifest_spec)
manifest_spec.loader.exec_module(build_manifest)

config_spec = importlib.util.spec_from_file_location('deployment_config', ROOT / 'scripts/diagnostics-deployment-config.py')
deployment_config = importlib.util.module_from_spec(config_spec)
config_spec.loader.exec_module(deployment_config)


class DiagnosticsExportTests(unittest.TestCase):
    def test_export_defaults_off_and_requires_explicit_opt_in(self):
        self.assertIn('enabled: false', export_site.diagnostics_config())
        self.assertIn('enabled: true', export_site.diagnostics_config(True))
        self.assertIn('enabled: false', (ROOT / 'engine/web/shell/diagnostics-config.js').read_text())
        html = (ROOT / 'engine/web/shell/index.html').read_text()
        self.assertLess(html.index('src="diagnostics-config.js'), html.index('src="diagnostics.js'))

    def test_documented_numeric_build_flag_and_off_are_normalized(self):
        self.assertTrue(build_manifest.cmake_enabled('1'))
        self.assertTrue(build_manifest.cmake_enabled('ON'))
        self.assertFalse(build_manifest.cmake_enabled('OFF'))
        self.assertFalse(build_manifest.cmake_enabled('0'))
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            (build / 'GeneralsMD').mkdir()
            (build / 'GeneralsMD/GeneralsXZH.wasm').write_bytes(b'compiled')
            for value, expected in [('1', True), ('OFF', False)]:
                (build / 'CMakeCache.txt').write_text('GX_WEB_INPUT_DIAGNOSTICS:BOOL=' + value + '\n')
                self.assertEqual(build_manifest.write_manifest(build)['enabled'], expected)

    def test_debug_deployment_only_changes_gate_and_output_path(self):
        base = json.loads((ROOT / 'wrangler.jsonc').read_text())
        self.assertEqual(base['vars']['DIAGNOSTICS_ENABLED'], 'false')
        with self.assertRaises(ValueError):
            deployment_config.debug_config(base, {'diagnosticsCompiled': False, 'diagnosticsEnabled': True}, ROOT / 'release')
        result = deployment_config.debug_config(base, {'diagnosticsCompiled': True, 'diagnosticsEnabled': True}, ROOT / 'release')
        self.assertEqual(result['name'], base['name'])
        self.assertEqual(result['r2_buckets'], base['r2_buckets'])
        self.assertEqual(result['vars']['ACCESS_AUD'], base['vars']['ACCESS_AUD'])
        self.assertEqual(result['vars']['DIAGNOSTICS_ENABLED'], 'true')
        self.assertEqual(base['vars']['DIAGNOSTICS_ENABLED'], 'false')

    def test_enabled_export_rejects_compiled_off_and_stale_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            build = Path(directory)
            (build / 'GeneralsMD').mkdir()
            wasm = build / 'GeneralsMD/GeneralsXZH.wasm'
            wasm.write_bytes(b'test binary')
            manifest = {'enabled': False, 'wasmSha256': hashlib.sha256(wasm.read_bytes()).hexdigest()}
            (build / 'web-diagnostics-build.json').write_text(json.dumps(manifest))
            self.assertFalse(export_site.validate_diagnostics_build(build))
            with self.assertRaises(SystemExit):
                export_site.validate_diagnostics_build(build, True)
            manifest['enabled'] = True
            (build / 'web-diagnostics-build.json').write_text(json.dumps(manifest))
            self.assertTrue(export_site.validate_diagnostics_build(build, True))
            wasm.write_bytes(b'replaced binary')
            with self.assertRaises(SystemExit):
                export_site.validate_diagnostics_build(build, True)

    def test_cloud_runtime_gate_keeps_project_security_and_source_defaults(self):
        base = json.loads((ROOT / 'wrangler.jsonc').read_text())
        for enabled in [False, True]:
            release = {'diagnosticsCompiled': enabled, 'diagnosticsEnabled': enabled}
            result = deployment_config.cloud_runtime_config(base, release)
            expected = json.loads(json.dumps(base))
            expected['vars']['DIAGNOSTICS_ENABLED'] = 'true' if enabled else 'false'
            self.assertEqual(result, expected)
            self.assertEqual(base['vars']['DIAGNOSTICS_ENABLED'], 'false')
        with self.assertRaises(ValueError):
            deployment_config.cloud_runtime_config(base, {'diagnosticsCompiled': False, 'diagnosticsEnabled': True})


if __name__ == '__main__':
    unittest.main()
