"""TEMPORARY production investigation opt-in; remove with its config commit."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class TemporaryProductionDiagnosticsTests(unittest.TestCase):
    def test_only_production_gate_changes_with_identical_auth_and_private_binding(self):
        config = json.loads((ROOT / 'wrangler.jsonc').read_text())
        self.assertEqual(config['name'], 'candc-web')
        self.assertEqual(config['vars']['DIAGNOSTICS_ENABLED'], 'false')
        production = config['env']['production']
        self.assertEqual(production['vars'], dict(config['vars'], DIAGNOSTICS_ENABLED='true'))
        self.assertEqual(production['r2_buckets'], config['r2_buckets'])
        self.assertEqual(config.get('env', {}).get('preview', {}).get('vars', config['vars'])['DIAGNOSTICS_ENABLED'], 'false')


if __name__ == '__main__':
    unittest.main()
