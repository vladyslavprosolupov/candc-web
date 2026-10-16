import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('bootstrap', ROOT / 'scripts/bootstrap.py')
bootstrap = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bootstrap)


class BootstrapTests(unittest.TestCase):
    def test_reconstructs_added_files_and_preserves_developer_edits(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            upstream = root / 'upstream'
            subprocess.run(['git', 'init', upstream], check=True, capture_output=True)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(upstream), *args], text=True).strip()
            (upstream / 'existing.txt').write_text('upstream\n')
            git('add', '.')
            git('-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-m', 'baseline')
            baseline = git('rev-parse', 'HEAD')
            (upstream / 'new.txt').write_text('new source\n')
            git('add', '.')
            patch = root / 'source.patch'
            patch.write_text(git('diff', '--cached', '--binary') + '\n')
            version = {'origin': str(upstream), 'upstreamCommit': baseline,
                       'sourcePatch': 'source.patch', 'sourceTree': git('write-tree')}
            bootstrap.prepare_engine(root, version)
            self.assertEqual((root / 'engine/new.txt').read_text(), 'new source\n')
            self.assertIn('new.txt', bootstrap.git(root / 'engine', 'ls-files'))
            bootstrap.prepare_engine(root, version)
            (root / 'engine/existing.txt').write_text('developer changes\n')
            with self.assertRaises(ValueError):
                bootstrap.prepare_engine(root, version)
            self.assertEqual((root / 'engine/existing.txt').read_text(), 'developer changes\n')

    def test_fonts_require_archive_and_individual_hashes_without_path_extraction(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            archive = root / 'fonts.tar.gz'
            data = b'open font fixture'
            with tarfile.open(archive, 'w:gz') as tar:
                member = tarfile.TarInfo('../../outside/Font.ttf')
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
            config = {'sha256': bootstrap.sha256(archive), 'files': {
                'arial.ttf': {'source': 'Font.ttf', 'sha256': hashlib.sha256(data).hexdigest()}}}
            destination = root / 'fonts'
            bootstrap.install_fonts(archive, destination, config)
            self.assertEqual((destination / 'arial.ttf').read_bytes(), data)
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['fonts', 'fonts.tar.gz'])
            config['files']['arial.ttf']['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                bootstrap.install_fonts(archive, destination, config)
            config['sha256'] = '0' * 64
            with self.assertRaises(ValueError):
                bootstrap.install_fonts(archive, destination, config)


if __name__ == '__main__':
    unittest.main()
