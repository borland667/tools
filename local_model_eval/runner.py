"""Serial bounded pilot runner; reports are evidence, not automatic model approval."""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import shutil
import subprocess
import time
import uuid

from .client import create_client
from .scoring import score
from .resources import ResourceMonitor


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def memory_snapshot():
    result = {}
    for name, command in [('swap', ['sysctl', '-n', 'vm.swapusage']), ('vm_stat', ['vm_stat'])]:
        try:
            p = subprocess.run(command, capture_output=True, text=True, timeout=2)
            result[name] = p.stdout.strip() if p.returncode == 0 else 'unavailable'
        except (OSError, subprocess.TimeoutExpired):
            result[name] = 'unavailable'
    return result


def file_identity(filename):
    path = Path(filename).resolve()
    stat = path.stat()
    with path.open('rb') as source:
        head = source.read(1024 * 1024)
        source.seek(max(0, stat.st_size - 1024 * 1024))
        tail = source.read(1024 * 1024)
    return {'path': str(path), 'bytes': stat.st_size, 'mtime_ns': stat.st_mtime_ns,
            'sampled_sha256': hashlib.sha256(head + tail).hexdigest(), 'hash_scope': 'first_and_last_1MiB_not_full_file'}


def summary(rows):
    tasks = [r for r in rows if r['stage'] == 'tasks']
    groups = {}
    for r in tasks:
        group = groups.setdefault(r['kind'], {'trials': 0, 'passed': 0, 'failed': 0, 'manual': 0, 'unscored_transport_error': 0})
        group['trials'] += 1
        if 'error' in r:
            group['unscored_transport_error'] += 1
            continue
        value = r.get('score', {}).get('passed', False)
        group['manual' if value is None else 'passed' if value else 'failed'] += 1
    compatibility = {}
    for row in rows:
        if row['stage'] != 'compat':
            continue
        response = row.get('response', {})
        content = response.get('content', '').strip()
        name = row['case']
        if 'error' in row:
            compatibility[name] = {'transport_error': row['error']}
        elif name in {'plain', 'stream'}:
            compatibility[name] = {'exact_answer': content == 'READY', 'reasoning_present': bool(response.get('reasoning'))}
        elif name == 'json':
            try:
                valid = json.loads(content) == {'sum': 42}
            except ValueError:
                valid = False
            compatibility[name] = {'strict_json_correct': valid}
        elif name == 'tool_call':
            compatibility[name] = {'call_count': len(response.get('tool_calls', []))}
        elif name == 'tool_result':
            compatibility[name] = {'exact_answer': content == 'FIXTURE_VALUE_7249', 'contains_value': 'FIXTURE_VALUE_7249' in content}
        elif name == 'cancel_stream':
            compatibility[name] = {'client_disconnected': response.get('client_disconnected'), 'server_abort_verified': response.get('server_abort_verified', False)}
    return {'task_results': groups, 'compatibility': compatibility, 'errors': sum('error' in r for r in rows),
            'median_task_seconds': statistics.median([r['response']['elapsed'] for r in tasks if 'response' in r]) if any('response' in r for r in tasks) else None,
            'limitations': ['small synthetic corpus', 'plans require independent manual rubric review',
                            'no automatic role approval', 'shared host and OS page cache not controlled',
                            'memory snapshots are not per-engine peak GPU memory']}


def run(args):
    config = json.loads(args.config.read_text())
    engines = config.get('engines')
    if not isinstance(engines, list) or not engines:
        raise ValueError('config needs a nonempty engines list')
    names = [s['name'] for s in engines]
    if len(set(names)) != len(names) or any(not name or any(c not in 'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-' for c in name) for name in names):
        raise ValueError('engine names must be unique and contain only letters, digits, underscore or hyphen')
    if args.only and set(args.only) - set(names):
        raise ValueError('unknown engine selection')
    cases_path = Path(__file__).parent / 'fixtures.json'
    cases = json.loads(cases_path.read_text())
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    source_dir = out / 'runner-source'
    source_dir.mkdir()
    source_hashes = {}
    for source in Path(__file__).parent.iterdir():
        if source.suffix in {'.py', '.json'}:
            shutil.copyfile(source, source_dir / source.name)
            source_hashes[source.name] = hashlib.sha256(source.read_bytes()).hexdigest()
    deadline = time.monotonic() + args.max_seconds
    manifest = {'run_id': uuid.uuid4().hex, 'started_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                'platform': platform.platform(), 'python': platform.python_version(), 'trials': args.trials,
                'max_output_tokens': args.max_tokens, 'request_timeout': args.timeout, 'max_seconds': args.max_seconds,
                'corpus_sha256': hashlib.sha256(cases_path.read_bytes()).hexdigest(), 'runner_source_sha256': source_hashes,
                'engines': [], 'memory_before': memory_snapshot()}
    write_json(out / 'manifest.json', manifest)
    for spec in config['engines']:
        if args.only and spec['name'] not in args.only:
            continue
        if time.monotonic() >= deadline:
            manifest['budget_exhausted'] = True
            break
        rows, client, monitor = [], None, None
        identity = {**spec}
        manifest['engines'].append(identity)
        write_json(out / 'manifest.json', manifest)
        try:
            identity['checkpoints'] = [file_identity(p) for p in spec.get('checkpoint_files', [])]
            load_start = time.monotonic()
            client = create_client({**spec, 'load_timeout': min(spec.get('load_timeout', 300), deadline - time.monotonic())}, out)
            monitor = ResourceMonitor(spec, client)
            identity['adapter_start_seconds'] = time.monotonic() - load_start
            if hasattr(client, 'metadata'):
                identity['server_before'] = client.metadata()
            if hasattr(client, 'info'):
                identity['adapter_info'] = client.info

            consecutive_errors = 0

            def request(stage, name, body, cancel_after_first=False, **extra):
                nonlocal consecutive_errors
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError('global pilot budget exhausted')
                item = {'engine': spec['name'], 'stage': stage, 'case': name, 'request': body, **extra}
                started = time.monotonic()
                try:
                    effective = {'temperature': 0, **body, 'max_tokens': min(args.max_tokens, body.get('max_tokens', args.max_tokens))}
                    item['response'] = client.request(effective, min(args.timeout, remaining), cancel_after_first=cancel_after_first)
                    if stage == 'tasks':
                        item['score'] = score(extra['definition'], item['response']['content'])
                        del item['definition']
                    consecutive_errors = 0
                except Exception as exc:
                    item['error'] = type(exc).__name__ + ': ' + str(exc)
                    item.pop('definition', None)
                    consecutive_errors += 1
                item['wall_seconds'] = time.monotonic() - started
                rows.append(item)
                with (out / (spec['name'] + '.jsonl')).open('a') as log:
                    log.write(json.dumps(item, ensure_ascii=False) + '\n')
                print(json.dumps({'engine': spec['name'], 'case': name, 'seconds': round(item['wall_seconds'], 2),
                                  'score': item.get('score'), 'error': item.get('error')}), flush=True)
                if consecutive_errors >= 3:
                    raise RuntimeError('stopped after three consecutive transport/adapter errors; task quality is unscored')
                return item

            if 'compat' in args.stages:
                for name, body in [('plain', {'messages': [{'role': 'user', 'content': 'Return only the word READY.'}]}),
                                   ('stream', {'messages': [{'role': 'user', 'content': 'Return only the word READY.'}], 'stream': True}),
                                   ('json', {'messages': [{'role': 'user', 'content': 'Return exactly a JSON object with sum equal to 42. No Markdown.'}], 'response_format': {'type': 'json_object'}})]:
                    request('compat', name, body)
                request('compat', 'cancel_stream', {'messages': [{'role': 'user', 'content': 'Count from 1 to 200, one number per line.'}], 'stream': True}, cancel_after_first=True)
                tools = [{'type': 'function', 'function': {'name': 'read_fixture', 'description': 'Read the literal fixture value.',
                         'parameters': {'type': 'object', 'properties': {'path': {'type': 'string', 'enum': ['fixture.txt']}}, 'required': ['path'], 'additionalProperties': False}}}]
                messages = [{'role': 'user', 'content': 'Call read_fixture with path fixture.txt. Then return its content exactly. Do not guess the content.'}]
                first = request('compat', 'tool_call', {'messages': messages, 'tools': tools})
                response = first.get('response', {})
                calls = response.get('tool_calls', [])
                if len(calls) == 1:
                    call = calls[0]
                    try:
                        valid = call['function']['name'] == 'read_fixture' and json.loads(call['function']['arguments']) == {'path': 'fixture.txt'}
                    except (ValueError, KeyError):
                        valid = False
                    if valid:
                        request('compat', 'tool_result', {'messages': messages + [{'role': 'assistant', 'content': response['content'] or None, 'tool_calls': calls},
                                {'role': 'tool', 'tool_call_id': call['id'], 'content': 'FIXTURE_VALUE_7249'}], 'tools': tools})
            if 'tasks' in args.stages:
                for trial in range(args.trials):
                    for case in cases:
                        nonce = f'Evaluation {manifest["run_id"]} trial {trial}. '
                        request('tasks', case['id'], {'messages': [{'role': 'user', 'content': nonce + case['prompt']}], 'stream': True},
                                trial=trial, kind=case['kind'], definition=case)
                        if time.monotonic() >= deadline:
                            raise TimeoutError('global pilot budget exhausted')
            if 'reasoning' in args.stages:
                request('reasoning', 'enabled_reasoning_stream', {'messages': [{'role': 'user', 'content':
                        'Compute 17*23 + 19*29. Work it out before giving the final number.'}],
                        'stream': True, 'max_tokens': 256, 'reasoning_effort': 'low',
                        'chat_template_kwargs': {'enable_thinking': True}})
            if 'cancellation' in args.stages:
                request('cancellation', 'cancel_stream', {'messages': [{'role': 'user', 'content':
                        'Count from 1 to 1000, one number per line.'}], 'stream': True, 'max_tokens': 256}, cancel_after_first=True)
            if 'performance' in args.stages:
                for size in args.contexts:
                    for trial in range(args.trials):
                        # Token count is measured by the engine; this is a size target, not an exact token claim.
                        prefix = f'Unique prefix {uuid.uuid4().hex}. '
                        text = prefix + (' alpha beta gamma delta' * max(1, size // 4)) + '\nReturn only CONTEXT_OK.'
                        body = {'messages': [{'role': 'user', 'content': text}], 'max_tokens': 32, 'stream': True}
                        request('performance', f'context_{size}_unique', body, target_tokens=size, trial=trial, cache_condition='unique_prefix_OS_cache_uncontrolled')
                        request('performance', f'context_{size}_repeated', body, target_tokens=size, trial=trial, cache_condition='identical_request_prefix_reuse_possible')
            if 'generation' in args.stages:
                for trial in range(args.trials):
                    request('generation', 'decode_256', {'messages': [{'role': 'user', 'content':
                            f'Run {uuid.uuid4().hex}. List all integers from 1 to 1000, one per line. Start immediately, no explanation.'}],
                            'stream': True, 'max_tokens': 256}, trial=trial)
        except Exception as exc:
            identity['error'] = type(exc).__name__ + ': ' + str(exc)
        finally:
            if client is not None:
                if hasattr(client, 'metadata'):
                    identity['server_after'] = client.metadata()
                client.close()
            if monitor:
                identity['resources'] = monitor.close()
            identity['memory_after'] = memory_snapshot()
            report = summary(rows)
            report['expected_task_trials'] = args.trials * len(cases) if 'tasks' in args.stages else 0
            report['attempted_task_trials'] = sum(r['stage'] == 'tasks' for r in rows)
            report['attempts_complete'] = report['attempted_task_trials'] == report['expected_task_trials'] and 'error' not in identity
            identity['report'] = report
            write_json(out / (spec['name'] + '-summary.json'), report)
            write_json(out / 'manifest.json', manifest)
    return 1 if manifest.get('budget_exhausted') or any('error' in e or e.get('report', {}).get('errors') for e in manifest['engines']) else 0


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--output', required=True, type=Path, help='new directory, outside git or gitignored')
    p.add_argument('--only', nargs='+')
    p.add_argument('--trials', type=int, choices=range(1, 6), default=3)
    p.add_argument('--max-tokens', type=int, default=768)
    p.add_argument('--timeout', type=float, default=120)
    p.add_argument('--max-seconds', type=float, default=2400)
    p.add_argument('--stages', nargs='+', choices=['compat', 'tasks', 'performance', 'generation', 'reasoning', 'cancellation'], default=['compat', 'tasks', 'performance', 'generation', 'reasoning'])
    p.add_argument('--contexts', nargs='+', type=int, default=[128, 8192, 32768])
    args = p.parse_args()
    if not 1 <= args.max_tokens <= 2048 or not 0 < args.timeout <= 600 or not 0 < args.max_seconds <= 3600 or any(not 1 <= n <= 32768 for n in args.contexts):
        p.error('limits: max tokens 1..2048, timeout 0..600s, run 0..3600s, context targets 1..32768')
    try:
        return run(args)
    except (ValueError, KeyError, OSError) as exc:
        p.error(str(exc))
