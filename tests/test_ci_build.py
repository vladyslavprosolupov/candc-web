import contextlib
import importlib.util
import io
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ci_build', ROOT / 'scripts/ci-build.py')
ci_build = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ci_build)


class CiBuildTests(unittest.TestCase):
    def test_warning_storm_stays_in_log_and_success_is_concise(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'build.log'
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = ci_build.build([sys.executable, '-c',
                    'print("[1/2] compile"); print("warning: old code\\n"*10000); print("[2/2] link")'], log)
            self.assertEqual(code, 0)
            self.assertLess(len(output.getvalue()), 1000)
            self.assertGreater(log.stat().st_size, 100000)

    def test_real_failure_code_and_stderr_context_are_preserved(self):
        with tempfile.TemporaryDirectory() as temp:
            log = Path(temp) / 'build.log'
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = ci_build.build([sys.executable, '-c',
                    'import sys; print("fatal error: missing header",file=sys.stderr); sys.exit(7)'], log)
            self.assertEqual(code, 7)
            self.assertIn('fatal error: missing header', output.getvalue())
            self.assertIn('fatal error: missing header', log.read_text())


if __name__ == '__main__':
    unittest.main()
