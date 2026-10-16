import functools
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.request import urlopen, Request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer

spec = importlib.util.spec_from_file_location('serve', Path(__file__).resolve().parents[1] / 'scripts/serve.py')
serve = importlib.util.module_from_spec(spec)
spec.loader.exec_module(serve)


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        Path(cls.tmp.name, 'test.wasm').write_bytes(bytes(range(256)))
        cls.server = ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(serve.Handler, directory=cls.tmp.name))
        cls.worker = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.worker.start()
        cls.url = f'http://127.0.0.1:{cls.server.server_port}/test.wasm'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.worker.join()
        cls.tmp.cleanup()

    def test_wasm_and_isolation(self):
        with urlopen(self.url) as res:
            self.assertEqual(res.headers['Content-Type'], 'application/wasm')
            self.assertEqual(res.headers['Cross-Origin-Opener-Policy'], 'same-origin')
            self.assertEqual(res.headers['Cross-Origin-Embedder-Policy'], 'require-corp')
            self.assertEqual(res.read(), bytes(range(256)))

    def test_resumable_ranges(self):
        for header, expected in [('bytes=10-19', bytes(range(10, 20))),
                                 ('bytes=250-', bytes(range(250, 256))),
                                 ('bytes=-4', bytes(range(252, 256))),
                                 ('bytes=254-999', bytes(range(254, 256)))]:
            with self.subTest(header=header), urlopen(Request(self.url, headers={'Range': header})) as res:
                self.assertEqual(res.status, 206)
                self.assertEqual(res.read(), expected)

    def test_invalid_range(self):
        for header in ['bytes=500-', 'bytes=50-10', 'bytes=-0', 'bytes=0-1,3-4']:
            with self.assertRaises(HTTPError) as err:
                urlopen(Request(self.url, headers={'Range': header}))
            self.assertEqual(err.exception.code, 416)

    def test_head(self):
        with urlopen(Request(self.url, method='HEAD', headers={'Range': 'bytes=10-19'})) as res:
            self.assertEqual(res.headers['Content-Length'], '10')
            self.assertEqual(res.read(), b'')


if __name__ == '__main__':
    unittest.main()
