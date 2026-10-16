import importlib.util
from pathlib import Path
import struct
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('import_assets', Path(__file__).resolve().parents[1] / 'scripts/import-assets.py')
assets = importlib.util.module_from_spec(spec)
spec.loader.exec_module(assets)


class BigValidationTest(unittest.TestCase):
    def check_archive(self, content):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder, 'test.big')
            path.write_bytes(content)
            return assets.validate_big(path)

    def test_valid_big(self):
        content = b'BIGF' + struct.pack('<I', 30) + struct.pack('>II', 1, 26)
        content += struct.pack('>II', 26, 4) + b'a\0' + b'data'
        self.assertEqual(self.check_archive(content), 1)

    def test_invalid_signature(self):
        with self.assertRaises(ValueError):
            self.check_archive(b'not a BIG archive')

    def test_truncated_entry(self):
        content = b'BIGF' + struct.pack('<I', 30) + struct.pack('>II', 1, 26)
        content += struct.pack('>II', 26, 1000) + b'a\0' + b'data'
        with self.assertRaises(ValueError):
            self.check_archive(content)

    def test_unterminated_name(self):
        content = b'BIGF' + struct.pack('<I', 26) + struct.pack('>II', 1, 26)
        content += struct.pack('>II', 26, 0) + b'ab'
        with self.assertRaises(ValueError):
            self.check_archive(content)
