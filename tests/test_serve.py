import functools
import json
import uuid
from contextlib import contextmanager
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


@contextmanager
def diagnostics_server(enabled):
    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp, 'static'); root.mkdir()
        collected = Path(temp, 'collected')
        handler = functools.partial(serve.Handler, directory=str(root), diagnostics_dir=collected if enabled else None)
        server = ThreadingHTTPServer(('127.0.0.1', 0), handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        try:
            yield f'http://127.0.0.1:{server.server_port}', collected
        finally:
            server.shutdown(); server.server_close(); worker.join()


class DiagnosticsServerTest(unittest.TestCase):
    def chunk(self):
        return {'version': 1, 'id': str(uuid.uuid4()), 'session': str(uuid.uuid4()),
                'sequence': 0, 'reason': 'periodic', 'events': [{'at': 1, 'type': 'browser', 'data': {}}]}

    def post(self, origin, body, **headers):
        return Request(origin + '/api/diagnostics', method='POST', data=json.dumps(body).encode(),
                       headers={'Origin': origin, 'Content-Type': 'application/json', **headers})

    def test_default_has_no_collector(self):
        with diagnostics_server(False) as (origin, collected):
            with urlopen(origin + '/api/diagnostics?config=1') as result:
                self.assertEqual(json.load(result), {'enabled': False})
            with self.assertRaises(HTTPError) as error:
                urlopen(self.post(origin, self.chunk()))
            self.assertEqual(error.exception.code, 410)
            self.assertFalse(collected.exists())

    def test_enabled_collector_acknowledges_and_bounds_storage(self):
        with diagnostics_server(True) as (origin, collected):
            with urlopen(origin + '/api/diagnostics?config=1') as result:
                self.assertEqual(json.load(result), {'enabled': True})
            collected.mkdir()
            for index in range(128):
                Path(collected, f'old-{index}.json').write_text('{}')
            body = self.chunk()
            with urlopen(self.post(origin, body)) as result:
                self.assertEqual(json.load(result), {'ok': True, 'id': body['id'], 'session': body['session']})
            self.assertEqual(json.loads(Path(collected, body['id'] + '.json').read_text()), body)
            self.assertEqual(len(list(collected.glob('*.json'))), 128)

    def test_rejects_foreign_hosts_origins_size_and_schema(self):
        with diagnostics_server(True) as (origin, collected):
            cases = [(self.post(origin, self.chunk(), Origin='https://foreign.test'), 403),
                     (self.post(origin, self.chunk(), Host='attacker.test'), 403),
                     (self.post(origin, {**self.chunk(), 'id': '../escape'}), 400),
                     (self.post(origin, {**self.chunk(), 'large': 'x' * 49152}), 413)]
            for request, status in cases:
                with self.assertRaises(HTTPError) as error:
                    urlopen(request)
                self.assertEqual(error.exception.code, status)
            with self.assertRaises(HTTPError) as error:
                urlopen(Request(origin + '/api/diagnostics?config=1', headers={'Host': 'attacker.test'}))
            self.assertEqual(error.exception.code, 403)
            self.assertFalse(collected.exists())


if __name__ == '__main__':
    unittest.main()
