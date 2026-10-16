import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('export_site', ROOT / 'scripts/export-site.py')
export_site = importlib.util.module_from_spec(spec)
spec.loader.exec_module(export_site)


class DiagnosticsExportTests(unittest.TestCase):
    def test_export_defaults_off_and_requires_explicit_opt_in(self):
        self.assertIn('enabled: false', export_site.diagnostics_config())
        self.assertIn('enabled: true', export_site.diagnostics_config(True))
        self.assertIn('enabled: false', (ROOT / 'engine/web/shell/diagnostics-config.js').read_text())
        html = (ROOT / 'engine/web/shell/index.html').read_text()
        self.assertLess(html.index('src="diagnostics-config.js'), html.index('src="diagnostics.js'))


if __name__ == '__main__':
    unittest.main()
