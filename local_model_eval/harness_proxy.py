"""Loopback guard enforcing the harness's model, output and request budgets."""

from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import threading
import time
import urllib.request
from urllib.parse import urlsplit

from .client import open_local


@contextmanager
def guarded_endpoint(base_url, model, timeout, max_requests=3, max_tokens=768, api_key_env=None):
    url = urlsplit(base_url)
    if url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1'} or url.username is not None or url.password is not None or url.query or url.fragment:
        raise ValueError('harness upstream must be credential-free loopback HTTP')
    records, lock = [], threading.Lock()
    deadline = time.monotonic() + timeout

    class Guard(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass

        def do_POST(self):
            if self.path != '/v1/chat/completions':
                self.send_error(404)
                return
            with lock:
                if len(records) >= max_requests or time.monotonic() >= deadline:
                    self.send_error(429, 'pilot request budget exhausted')
                    return
                record = {'number': len(records) + 1}
                records.append(record)
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 1024 * 1024:
                    raise ValueError('request size outside pilot bound')
                body = json.loads(self.rfile.read(length))
                if body.get('model') != model:
                    raise ValueError('unexpected model')
                body.pop('max_completion_tokens', None)
                body.pop('max_output_tokens', None)
                body['max_tokens'] = min(max_tokens, max(1, int(body.get('max_tokens', max_tokens))))
                body['n'] = 1
                record.update({'model': model, 'max_tokens': body['max_tokens'], 'stream': bool(body.get('stream'))})
                record['message_roles'] = [m.get('role') for m in body.get('messages', [])]
                record['input_chars'] = sum(len(str(m.get('content', ''))) for m in body.get('messages', []))
                headers = {'Content-Type': 'application/json'}
                if api_key_env:
                    headers['Authorization'] = 'Bearer ' + os.environ[api_key_env]
                req = urllib.request.Request(base_url.rstrip('/') + '/chat/completions', json.dumps(body).encode(), headers)
                with open_local(req, max(0.1, min(60, deadline - time.monotonic()))) as upstream:
                    self.send_response(200)
                    self.send_header('Content-Type', upstream.headers.get('Content-Type', 'application/json'))
                    self.send_header('Connection', 'close')
                    self.end_headers()
                    while time.monotonic() < deadline:
                        chunk = upstream.read1(4096)
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        self.wfile.flush()
                record['completed'] = True
            except Exception as exc:
                record['error'] = type(exc).__name__
                try:
                    self.send_error(502, 'pilot upstream failed')
                except OSError:
                    pass

    server = ThreadingHTTPServer(('127.0.0.1', 0), Guard)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(server.server_port) + '/v1', records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
