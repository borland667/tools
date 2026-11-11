import argparse
from contextlib import contextmanager, redirect_stdout
import io
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from types import SimpleNamespace
import subprocess
import urllib.error
import urllib.request

from local_model_eval.client import HTTPClient, LineClient, NoRedirect
from local_model_eval.runner import run
from local_model_eval.scoring import expression_value, parse_json, score
from local_model_eval.harness_proxy import guarded_endpoint
from local_model_eval.strata_bridge import normalize_token_ids
from local_model_eval.harness import read_evidence
from local_model_eval.resources import ResourceMonitor


CASES = json.loads((Path(__file__).resolve().parents[2] / 'local_model_eval/fixtures.json').read_text())


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"models":[]}')

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
        prompt = body['messages'][-1]['content']
        value = {'findings': []}
        for case in CASES:
            if case['prompt'] in prompt:
                if case['kind'] == 'review':
                    value = {'findings': case['expected']}
                elif case['kind'] == 'repair':
                    value = {'expression': 'max(low,min(x,high))' if case['id'] == 'repair-clamp' else '(total+size-1)//size'}
                elif case['kind'] == 'regression':
                    value = {'cases': [{'value': -1, 'lower': 0, 'upper': 1, 'expected': False}]}
                else:
                    value = {'steps': ['inspect', 'verify'], 'risks': ['compatibility']}
        self.send_response(200)
        self.send_header('Content-Type', 'text/event-stream' if body.get('stream') else 'application/json')
        self.end_headers()
        try:
            if body.get('stream'):
                if prompt == 'split_tools':
                    for part in [
                        {'index': 0, 'id': 'call_1', 'function': {'name': 'read_fixture', 'arguments': '{"path":"'}},
                        {'index': 0, 'function': {'arguments': 'fixture.txt"}'}}
                    ]:
                        self.wfile.write(('data: ' + json.dumps({'choices': [{'delta': {'tool_calls': [part]}}]}) + '\n\n').encode())
                    self.wfile.write(b'data: [DONE]\n\n')
                elif prompt == 'slow':
                    for _ in range(50):
                        self.wfile.write(b'data: {"choices":[{"delta":{"content":"a"}}]}\n\n')
                        self.wfile.flush()
                        time.sleep(0.02)
                else:
                    event = {'choices': [{'delta': {'content': json.dumps(value)}, 'finish_reason': 'stop'}]}
                    if body.get('stream_options', {}).get('include_usage'):
                        event['usage'] = {'prompt_tokens': 4, 'completion_tokens': 6}
                    self.wfile.write(('data: ' + json.dumps(event) + '\n\ndata: [DONE]\n\n').encode())
            else:
                self.wfile.write(json.dumps({'choices': [{'message': {'content': json.dumps(value)}, 'finish_reason': 'stop'}]}).encode())
        except (BrokenPipeError, ConnectionResetError):
            pass


@contextmanager
def server():
    instance = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    try:
        yield 'http://127.0.0.1:' + str(instance.server_port) + '/v1'
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=2)


class ScoringTests(unittest.TestCase):
    def test_tokenizer_mapping_is_not_sent_as_string_keys(self):
        self.assertEqual(normalize_token_ids({'input_ids': [1, 2, 3], 'attention_mask': [1, 1, 1]}), [1, 2, 3])
        self.assertEqual(normalize_token_ids([1, 2]), [1, 2])
        for value in [['input_ids'], [], [[1]], {'input_ids': ['1']}]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                normalize_token_ids(value)

    def test_format_compliance_is_distinct_from_recovered_json(self):
        self.assertEqual(parse_json('{"x":1}')[1], 'strict')
        self.assertEqual(parse_json('```json\n{"x":1}\n```')[1], 'fenced')

    def test_malformed_answers_are_model_failures_and_retain_parse_format(self):
        self.assertFalse(score(CASES[0], '```broken```')['passed'])
        result = score(CASES[0], '```json\n{"findings":"invalid"}\n```')
        self.assertFalse(result['passed'])
        self.assertEqual(result['format'], 'fenced')

    def test_generated_expressions_cannot_access_host_or_allocate_arbitrarily(self):
        self.assertEqual(expression_value('max(low,min(x,high))', {'x': 15, 'low': 0, 'high': 10}), 10)
        for source in ["__import__('os').getcwd()", '(1).__class__', '10**10000', '999999999*999999999']:
            with self.subTest(source=source), self.assertRaises((ValueError, KeyError)):
                expression_value(source, {})

    def test_clean_control_false_positive_and_missed_bug_fail(self):
        clean = next(c for c in CASES if c['id'] == 'review-clean-inclusive')
        bad = json.dumps({'findings': [{'line': 2, 'kind': 'off_by_one'}]})
        self.assertEqual(score(clean, bad)['false_positives'], 1)
        self.assertFalse(score(CASES[0], '{"findings":[]}')['passed'])

    def test_repair_runs_oracle_cases(self):
        case = next(c for c in CASES if c['id'] == 'repair-page-count')
        self.assertTrue(score(case, '{"expression":"(total+size-1)//size"}')['passed'])
        self.assertFalse(score(case, '{"expression":"total//size"}')['passed'])

    def test_regression_inputs_must_be_correct_and_kill_mutant(self):
        case = next(c for c in CASES if c['kind'] == 'regression')
        good = {'cases': [{'value': -1, 'lower': 0, 'upper': 5, 'expected': False}]}
        self.assertTrue(score(case, json.dumps(good))['passed'])
        good['cases'][0]['expected'] = True
        self.assertFalse(score(case, json.dumps(good))['passed'])

    def test_plans_are_not_automatically_marked_correct(self):
        case = next(c for c in CASES if c['kind'] == 'plan')
        result = score(case, '{"steps":[],"risks":[]}')
        self.assertIsNone(result['passed'])
        self.assertTrue(result['manual_review_required'])


class TransportTests(unittest.TestCase):
    def test_unavailable_process_metrics_are_not_zero_memory(self):
        with patch('local_model_eval.resources.subprocess.run', return_value=subprocess.CompletedProcess(['ps'], 1, '', 'denied')):
            monitor = ResourceMonitor({}, SimpleNamespace(process=SimpleNamespace(pid=42)))
            result = monitor.close()
            self.assertIsNone(result['process_tree_peak_rss_kib'])
            self.assertEqual(result['error'], 'RSS sampling unavailable')

    def test_local_request_cannot_redirect_credentials_to_another_service(self):
        req = urllib.request.Request('http://127.0.0.1:8005/v1/chat/completions', headers={'Authorization': 'Bearer fixture-secret'})
        with self.assertRaises(ValueError):
            NoRedirect().redirect_request(req, None, 302, '', {}, 'https://example.com')

    def test_harness_needs_the_actual_fixture_read_not_a_different_file(self):
        root = Path('/tmp/fixture')
        def event(name):
            return {'type': 'tool_use', 'part': {'tool': 'read', 'state': {'status': 'completed', 'input': {'filePath': name}}}}
        count, unexpected = read_evidence([event('sentinel.txt'), event('review_me.py')], root, root/'review_me.py')
        self.assertEqual(count, 1)
        self.assertEqual(len(unexpected), 1)

    def test_invalid_engine_selection_or_duplicate_name_cannot_report_success(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.json'
            args = argparse.Namespace(config=config, output=Path(tmp) / 'results', only=['missing'])
            for engines in [[], [{'name': 'same'}, {'name': 'same'}], [{'name': 'present'}]]:
                config.write_text(json.dumps({'engines': engines}))
                with self.subTest(engines=engines), self.assertRaises(ValueError):
                    run(args)
                self.assertFalse(args.output.exists())

    def test_rejects_remote_endpoints_and_embedded_credentials(self):
        for url in ['https://example.com/v1', 'http://user:secret@localhost/v1', 'http://:secret@localhost/v1']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                HTTPClient({'base_url': url}, '.')

    def test_stream_content_usage_and_client_cancellation(self):
        with server() as url:
            client = HTTPClient({'base_url': url, 'model': 'fake'}, '.')
            result = client.request({'messages': [{'role': 'user', 'content': 'x'}], 'stream': True}, 2)
            self.assertEqual(result['content'], '{"findings": []}')
            self.assertEqual(result['usage']['completion_tokens'], 6)
            result = client.request({'messages': [{'role': 'user', 'content': 'slow'}], 'stream': True}, 2, cancel_after_first=True)
            self.assertTrue(result['client_disconnected'])
            self.assertFalse(result['server_abort_verified'])

    def test_deadline_beats_an_endless_stream_of_progress(self):
        with server() as url:
            client = HTTPClient({'base_url': url, 'model': 'fake'}, '.')
            start = time.monotonic()
            with self.assertRaises(TimeoutError):
                client.request({'messages': [{'role': 'user', 'content': 'slow'}], 'stream': True}, 0.08)
            self.assertLess(time.monotonic() - start, 0.5)

    def test_line_startup_timeout_stops_owned_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            marker = Path(tmp) / 'pid'
            code = 'import os,time;open(' + repr(str(marker)) + ',"w").write(str(os.getpid()));time.sleep(30)'
            with self.assertRaises(TimeoutError):
                LineClient({'name': 'fake', 'command': [sys.executable, '-u', '-c', code], 'load_timeout': 0.2}, tmp)
            pid = int(marker.read_text())
            with self.assertRaises(ProcessLookupError):
                os.kill(pid, 0)

    def test_line_progress_cannot_extend_wall_deadline(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = 'import sys,time,json;print(json.dumps({"event":"ready"}),flush=True);sys.stdin.readline();\nwhile True: print(json.dumps({"event":"token"}),flush=True);time.sleep(.005)'
            client = LineClient({'name': 'progress', 'command': [sys.executable, '-u', '-c', code], 'load_timeout': 2}, tmp)
            try:
                started = time.monotonic()
                with self.assertRaises(TimeoutError):
                    client.request({}, 0.08)
                self.assertLess(time.monotonic() - started, 0.6)
                self.assertIsNotNone(client.process.poll())
            finally:
                client.close()

    def test_split_tool_arguments_are_reassembled(self):
        with server() as url:
            client = HTTPClient({'base_url': url, 'model': 'fake'}, '.')
            result = client.request({'messages': [{'role': 'user', 'content': 'split_tools'}], 'stream': True}, 2)
            call = result['tool_calls'][0]
            self.assertEqual(call['id'], 'call_1')
            self.assertEqual(json.loads(call['function']['arguments']), {'path': 'fixture.txt'})

    def test_harness_proxy_enforces_output_and_request_budget(self):
        with server() as upstream, guarded_endpoint(upstream, 'fake', 3, max_requests=1, max_tokens=16) as (endpoint, records):
            body = {'model': 'fake', 'max_tokens': 100000, 'messages': [{'role': 'user', 'content': 'x'}]}
            def post():
                return urllib.request.urlopen(urllib.request.Request(endpoint + '/chat/completions', json.dumps(body).encode(), {'Content-Type': 'application/json'}), timeout=2)
            with post() as response:
                self.assertEqual(response.status, 200)
                response.read()
            self.assertEqual(records[0]['max_tokens'], 16)
            with self.assertRaises(urllib.error.HTTPError) as exc:
                post()
            self.assertEqual(exc.exception.code, 429)

    def test_three_trials_preserve_all_ten_cases_and_manual_plans(self):
        with server() as url, tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config.json'
            config.write_text(json.dumps({'engines': [{'name': 'fake', 'base_url': url, 'model': 'fake'}]}))
            args = argparse.Namespace(config=config, output=Path(tmp) / 'results', trials=3, max_tokens=128,
                                      timeout=2, max_seconds=20, only=None, stages=['tasks'], contexts=[128])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(run(args), 0)
            report = json.loads((args.output / 'fake-summary.json').read_text())
            self.assertTrue(report['attempts_complete'])
            self.assertEqual(report['attempted_task_trials'], 30)
            self.assertEqual(report['task_results']['review']['passed'], 15)
            self.assertEqual(report['task_results']['plan']['manual'], 6)

    def test_repeated_adapter_errors_stop_and_are_not_model_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = 'import sys,json;print(json.dumps({"event":"ready"}),flush=True)\nfor line in sys.stdin: print(json.dumps({"event":"error","error":"bad request"}),flush=True)'
            config = Path(tmp) / 'config.json'
            config.write_text(json.dumps({'engines': [{'name': 'broken', 'kind': 'strata_line', 'command': [sys.executable, '-u', '-c', code]}]}))
            args = argparse.Namespace(config=config, output=Path(tmp) / 'results', trials=3, max_tokens=128,
                                      timeout=2, max_seconds=10, only=None, stages=['tasks'], contexts=[128])
            with redirect_stdout(io.StringIO()):
                self.assertEqual(run(args), 1)
            report = json.loads((args.output / 'broken-summary.json').read_text())
            self.assertFalse(report['attempts_complete'])
            self.assertEqual(report['attempted_task_trials'], 3)
            self.assertEqual(report['task_results']['review']['failed'], 0)
            self.assertEqual(report['task_results']['review']['unscored_transport_error'], 3)


if __name__ == '__main__':
    unittest.main()
