#!/usr/bin/env python3
"""Loopback-only server with WASM MIME, isolation headers and resumable ranges."""
import argparse
import functools
import ipaddress
import json
import threading
import tempfile
from urllib.parse import urlsplit, parse_qs
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1] / 'engine/web/dist'


class Handler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, '.wasm': 'application/wasm',
                      '.js': 'text/javascript', '.data': 'application/octet-stream'}

    diagnostics_lock = threading.Lock()

    def __init__(self, *args, diagnostics_dir=None, **kwargs):
        self.diagnostics_dir = Path(diagnostics_dir).resolve() if diagnostics_dir else None
        super().__init__(*args, **kwargs)

    def diagnostics_json(self, data, status=200):
        body = json.dumps(data).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def diagnostics_local(self):
        # Loopback binding, peer and Host checks prevent LAN access/DNS rebinding.
        port = self.server.server_port
        return (ipaddress.ip_address(self.client_address[0]).is_loopback and
                ipaddress.ip_address(self.server.server_address[0]).is_loopback and
                self.headers.get('Host') in (f'127.0.0.1:{port}', f'localhost:{port}'))

    def do_GET(self):
        url = urlsplit(self.path)
        if url.path == '/api/diagnostics':
            if not self.diagnostics_local():
                return self.diagnostics_json({'error': 'loopback only'}, 403)
            if parse_qs(url.query).get('config') == ['1']:
                return self.diagnostics_json({'enabled': self.diagnostics_dir is not None})
            return self.diagnostics_json({'error': 'method'}, 405)
        super().do_GET()

    def do_POST(self):
        if urlsplit(self.path).path != '/api/diagnostics':
            return self.diagnostics_json({'error': 'method'}, 405)
        if not self.diagnostics_dir:
            return self.diagnostics_json({'error': 'diagnostics disabled'}, 410)
        if not self.diagnostics_local() or self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
            return self.diagnostics_json({'error': 'loopback origin required'}, 403)
        if self.diagnostics_dir.is_relative_to(Path(self.directory).resolve()):
            return self.diagnostics_json({'error': 'collector must be outside static root'}, 503)
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            length = 0
        if not 0 < length <= 48 * 1024:
            return self.diagnostics_json({'error': 'chunk size'}, 413)
        if self.headers.get('Transfer-Encoding') or not self.headers.get('Content-Type', '').startswith('application/json'):
            return self.diagnostics_json({'error': 'content type'}, 403)
        self.connection.settimeout(5)
        try:
            raw = self.rfile.read(length)
            body = json.loads(raw)
            uuid = r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'
            valid = (isinstance(body, dict) and body.get('version') == 1 and
                     all(isinstance(body.get(key), str) and re.fullmatch(uuid, body[key]) for key in ('id', 'session')) and
                     body.get('reason') in ('manual', 'periodic', 'pagehide') and
                     type(body.get('sequence')) is int and 0 <= body['sequence'] <= 9007199254740991 and
                     isinstance(body.get('events'), list) and len(body['events']) <= 256 and
                     all(isinstance(event, dict) and isinstance(event.get('type'), str) and len(event['type']) <= 80 and
                         type(event.get('at')) in (int, float) and -9007199254740991 <= event['at'] <= 9007199254740991 for event in body['events']))
            if not valid:
                return self.diagnostics_json({'error': 'invalid schema'}, 400)
        except (ValueError, TimeoutError):
            return self.diagnostics_json({'error': 'invalid chunk'}, 400)
        with self.diagnostics_lock:
            self.diagnostics_dir.mkdir(parents=True, exist_ok=True)
            path = self.diagnostics_dir / (body['id'] + '.json')
            # Atomic replace does not follow a stale/symlink destination.
            with tempfile.NamedTemporaryFile(dir=self.diagnostics_dir, suffix='.tmp', delete=False) as stream:
                stream.write(raw)
                temp = Path(stream.name)
            temp.replace(path)
            files = sorted(self.diagnostics_dir.glob('*.json'), key=lambda p: p.stat().st_mtime_ns)
            for old in files[:-128]:
                old.unlink()
        return self.diagnostics_json({'ok': True, 'id': body['id'], 'session': body['session']})

    def end_headers(self):
        self.send_header('Cross-Origin-Opener-Policy', 'same-origin')
        self.send_header('Cross-Origin-Embedder-Policy', 'require-corp')
        self.send_header('Cross-Origin-Resource-Policy', 'same-origin')
        self.send_header('Cache-Control', 'no-cache')
        self.send_header('Accept-Ranges', 'bytes')
        super().end_headers()

    def list_directory(self, path):
        self.send_error(403, 'Directory listing disabled')
        return None

    def send_head(self):
        self.byte_range = None
        path = Path(self.translate_path(self.path))
        if not path.resolve().is_relative_to(Path(self.directory).resolve()):
            self.send_error(403)
            return None
        requested = self.headers.get('Range')
        if not requested or not path.is_file():
            return super().send_head()
        size = path.stat().st_size
        match = re.fullmatch(r'bytes=(\d*)-(\d*)', requested)
        if not match or not any(match.groups()):
            return self.invalid_range(size)
        first, last = match.groups()
        if first:
            start, end = int(first), min(int(last), size - 1) if last else size - 1
        else:
            start, end = max(0, size - int(last)), size - 1
        if start > end or start >= size:
            return self.invalid_range(size)
        stream = path.open('rb')
        stream.seek(start)
        self.byte_range = (start, end)
        self.send_response(206)
        self.send_header('Content-Type', self.guess_type(str(path)))
        self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Last-Modified', self.date_time_string(path.stat().st_mtime))
        self.end_headers()
        return stream

    def invalid_range(self, size):
        self.send_response(416)
        self.send_header('Content-Range', f'bytes */{size}')
        self.send_header('Content-Length', '0')
        self.end_headers()
        return None

    def copyfile(self, source, outputfile):
        remaining = self.byte_range[1] - self.byte_range[0] + 1 if self.byte_range else None
        try:
            while remaining is None or remaining > 0:
                data = source.read(min(1024 * 1024, remaining) if remaining is not None else 1024 * 1024)
                if not data:
                    break
                outputfile.write(data)
                if remaining is not None:
                    remaining -= len(data)
        except (BrokenPipeError, ConnectionResetError):
            return  # browser cancelled a download or closed the game


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    parser.add_argument('--directory', type=Path, default=ROOT)
    parser.add_argument('--diagnostics-dir', type=Path, help='TEMPORARY loopback-only collector; max 128 chunks, outside static root')
    args = parser.parse_args()
    root = args.directory.resolve()
    if not (root / 'GeneralsXZH.wasm').is_file():
        parser.error('Engine is not built yet. Run npm run build first.')
    if args.diagnostics_dir and args.diagnostics_dir.resolve().is_relative_to(root):
        parser.error('--diagnostics-dir must be outside the static root')
    server = ThreadingHTTPServer(('127.0.0.1', args.port), functools.partial(Handler, directory=str(root), diagnostics_dir=args.diagnostics_dir))
    print(f'Generals Zero Hour: http://localhost:{args.port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
