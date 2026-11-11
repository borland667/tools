"""OpenAI HTTP and task-owned JSON-line transports with wall-clock bounds."""

import json
import os
from pathlib import Path
import queue
import signal
import socket
import subprocess
import threading
import time
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('redirects are disabled for local evaluation endpoints')


def open_local(request, timeout):
    return urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=timeout)


def read_lines(pipe, destination):
    try:
        for line in pipe:
            destination.put(line)
    finally:
        destination.put(None)


def kill_owned(process):
    if process.poll() is None:
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait(timeout=5)


class HTTPClient:
    def __init__(self, spec, output):
        self.spec = spec
        self.base = spec['base_url'].rstrip('/')
        url = urlsplit(self.base)
        if url.scheme != 'http' or url.hostname not in {'localhost', '127.0.0.1', '::1'} or url.username is not None or url.password is not None or url.query or url.fragment:
            raise ValueError('Only credential-free loopback HTTP endpoints are allowed')

    def request(self, body, timeout, cancel_after_first=False):
        payload = {**self.spec.get('request_defaults', {}), **body, 'model': self.spec['model']}
        if payload.get('stream'):
            payload.setdefault('stream_options', {'include_usage': True})
        headers = {'Content-Type': 'application/json'}
        if self.spec.get('api_key_env'):
            headers['Authorization'] = 'Bearer ' + os.environ[self.spec['api_key_env']]
        started = time.monotonic()
        events = queue.Queue()
        state = {}

        def receive():
            try:
                req = urllib.request.Request(self.base + '/chat/completions', json.dumps(payload).encode(), headers)
                with open_local(req, timeout) as response:
                    state['response'] = response
                    if not payload.get('stream'):
                        events.put(('json', json.load(response)))
                    else:
                        for line in response:
                            if line.startswith(b'data:'):
                                data = line[5:].strip()
                                if data == b'[DONE]':
                                    break
                                events.put(('event', json.loads(data)))
                events.put(('end', None))
            except Exception as exc:
                events.put(('error', type(exc).__name__ + ': ' + str(exc)))

        threading.Thread(target=receive, daemon=True).start()
        content, reasoning, tools, raw, usage = '', '', {}, [], {}
        first_content, first_event, finish = None, None, None
        try:
            while True:
                remaining = timeout - (time.monotonic() - started)
                if remaining <= 0:
                    raise TimeoutError('request wall-clock deadline exceeded')
                kind, data = events.get(timeout=remaining)
                elapsed = time.monotonic() - started
                if kind == 'error':
                    raise RuntimeError(data)
                if kind == 'end':
                    break
                raw.append(data)
                if kind == 'json':
                    message = data['choices'][0]['message']
                    content = message.get('content') or ''
                    reasoning = message.get('reasoning_content') or message.get('reasoning') or ''
                    tools = {i: call for i, call in enumerate(message.get('tool_calls', []))}
                    usage, finish = data.get('usage', {}), data['choices'][0].get('finish_reason')
                    continue
                usage = data.get('usage') or usage
                for choice in data.get('choices', []):
                    finish = choice.get('finish_reason') or finish
                    delta = choice.get('delta', {})
                    piece = delta.get('content') or ''
                    thought = delta.get('reasoning_content') or delta.get('reasoning') or ''
                    if (piece or thought or delta.get('tool_calls')) and first_event is None:
                        first_event = elapsed
                    if piece and first_content is None:
                        first_content = elapsed
                    content += piece
                    reasoning += thought
                    for call in delta.get('tool_calls', []):
                        entry = tools.setdefault(call['index'], {'id': '', 'type': 'function', 'function': {'name': '', 'arguments': ''}})
                        entry['id'] += call.get('id', '')
                        for key in ('name', 'arguments'):
                            entry['function'][key] += call.get('function', {}).get(key, '')
                    if cancel_after_first and first_event is not None:
                        return {'content': content, 'reasoning': reasoning, 'client_disconnected': True,
                                'server_abort_verified': False, 'elapsed': elapsed, 'raw': raw}
        except queue.Empty as exc:
            raise TimeoutError('request wall-clock deadline exceeded') from exc
        finally:
            response = state.get('response')
            if response is not None:
                try:
                    response.fp.raw._sock.shutdown(socket.SHUT_RDWR)
                except (AttributeError, OSError):
                    pass
                response.close()
        return {'content': content, 'reasoning': reasoning, 'tool_calls': list(tools.values()),
                'usage': usage, 'finish_reason': finish, 'elapsed': time.monotonic() - started,
                'first_content_seconds': first_content, 'first_event_seconds': first_event, 'raw': raw}

    def close(self):
        pass

    def metadata(self):
        try:
            with open_local(self.base + '/models/status', 3) as response:
                data = json.load(response)
            chosen = next((m for m in data.get('models', []) if m['id'] == self.spec['model']), {})
            return {'loaded_count': data.get('loaded_count'), 'current_model_memory': data.get('current_model_memory'),
                    'target': {k: chosen.get(k) for k in ('id', 'loaded', 'engine_type', 'external_engine', 'actual_size', 'model_path', 'source_path', 'max_context_window')}}
        except Exception as exc:
            return {'unavailable': type(exc).__name__}


class LineClient:
    def __init__(self, spec, output):
        self.spec = spec
        self.log = (Path(output) / (spec['name'] + '-engine.log')).open('w')
        self.process = subprocess.Popen(spec['command'], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                        stderr=self.log, text=True, bufsize=1, start_new_session=True)
        self.lines = queue.Queue()
        threading.Thread(target=read_lines, args=(self.process.stdout, self.lines), daemon=True).start()
        try:
            self.info = self._next(spec.get('load_timeout', 300))
            if self.info.get('event') != 'ready':
                raise RuntimeError(str(self.info))
        except Exception:
            self.close()
            raise

    def _next(self, timeout):
        try:
            line = self.lines.get(timeout=max(0.001, timeout))
        except queue.Empty as exc:
            raise TimeoutError('line transport deadline exceeded') from exc
        if line is None:
            raise RuntimeError('engine adapter exited; inspect engine log')
        return json.loads(line)

    def request(self, body, timeout, cancel_after_first=False):
        start = time.monotonic()
        cancel_sent = False
        self.process.stdin.write(json.dumps(body) + '\n')
        self.process.stdin.flush()
        while True:
            remaining = timeout - (time.monotonic() - start)
            if remaining <= 0:
                self.close()
                raise TimeoutError('line request wall-clock deadline exceeded')
            try:
                event = self._next(remaining)
            except TimeoutError:
                self.close()
                raise
            if event['event'] == 'error':
                raise RuntimeError(event['error'])
            if event['event'] == 'token' and cancel_after_first and not cancel_sent:
                self.process.stdin.write('{"op":"stop"}\n')
                self.process.stdin.flush()
                cancel_sent = True
            if event['event'] == 'result':
                return {**event['result'], 'elapsed': time.monotonic() - start}

    def close(self):
        kill_owned(self.process)
        for resource in (self.process.stdin, self.process.stdout, self.log):
            if not resource.closed:
                resource.close()


def create_client(spec, output):
    return LineClient(spec, output) if spec.get('kind') == 'strata_line' else HTTPClient(spec, output)
