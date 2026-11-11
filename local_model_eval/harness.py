"""Read-only OpenCode pilot using task-owned configuration and bounded steps.

Permissions are application controls, not an operating-system security sandbox.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from .client import kill_owned
from .runner import write_json
from .harness_proxy import guarded_endpoint
from .scoring import score


def fingerprints(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def read_evidence(events, project, fixture):
    matched, unexpected = 0, []
    for event in events:
        part = event.get('part', {})
        if event.get('type') != 'tool_use' or part.get('tool') != 'read' or part.get('state', {}).get('status') != 'completed':
            continue
        filename = part['state'].get('input', {}).get('filePath')
        if not isinstance(filename, str):
            unexpected.append('missing filePath evidence')
            continue
        path = (project / filename).resolve()
        if path == fixture.resolve():
            matched += 1
        else:
            unexpected.append(str(path))
    return matched, unexpected


def run_harness(spec, output, timeout=180, executable='opencode'):
    root = output.resolve()
    root.mkdir(parents=True, exist_ok=False)
    project = root / 'fixture'
    project.mkdir()
    fixture = project / 'review_me.py'
    fixture.write_text('def inclusive(low, high):\n    return list(range(low, high))\n')
    (project / 'sentinel.txt').write_text('must remain unchanged\n')
    before = fingerprints(project)
    model = spec['model']
    provider = 'local-pilot'
    config = {
        'model': provider + '/' + model, 'small_model': provider + '/' + model,
        'enabled_providers': [provider], 'autoupdate': False, 'share': 'disabled', 'snapshot': False,
        'plugin': [], 'mcp': {}, 'formatter': False,
        'provider': {provider: {'npm': '@ai-sdk/openai-compatible', 'name': 'Local evaluation',
                     'options': {'baseURL': spec['base_url'], 'apiKey': 'sk-local'},
                     'models': {model: {'name': model, 'limit': {'context': 32768, 'output': 768},
                                       'options': {'temperature': 0, 'reasoning_effort': 'none'}}}}},
        'agent': {'pilot-review': {'mode': 'primary', 'steps': 3, 'model': provider + '/' + model,
                  'prompt': 'You are a read-only reviewer. Read only the requested fixture. Never edit files, run shell, use the web, load skills or delegate. Report only actual contract violations.',
                  'permission': {'*': 'deny', 'read': 'allow', 'external_directory': 'deny'}}},
        'permission': {'*': 'deny', 'read': 'allow', 'external_directory': 'deny'}}
    config_path = root / 'opencode.json'
    write_json(config_path, config)
    env = {k: v for k, v in os.environ.items() if not any(s in k.upper() for s in ('API_KEY', 'AUTH_TOKEN', 'ACCESS_TOKEN'))}
    for name, directory in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache'), ('XDG_STATE_HOME', 'state')]:
        path = root / directory
        path.mkdir()
        env[name] = str(path)
    env.update({'OPENCODE_CONFIG': str(config_path), 'OPENCODE_CONFIG_DIR': str(root / 'config'),
                'OPENCODE_DISABLE_AUTOUPDATE': 'true', 'OPENCODE_DISABLE_MODELS_FETCH': 'true',
                'OPENCODE_DISABLE_DEFAULT_PLUGINS': 'true'})
    prompt = 'Read ' + str(fixture) + ' with the read tool. Contract: inclusive(low,high) includes both integer endpoints when low <= high. Return JSON {"findings":[{"line":integer,"kind":"off_by_one"}]} or an empty list for correct code. Do not change any file.'
    command = [executable, 'run', '--pure', '--title', 'Local model pilot', '--agent', 'pilot-review', '--model', provider + '/' + model,
               '--format', 'json', '--dir', str(project), prompt]
    started = time.monotonic()
    with guarded_endpoint(spec['base_url'], model, timeout, api_key_env=spec.get('api_key_env')) as (endpoint, requests):
        config['provider'][provider]['options']['baseURL'] = endpoint
        write_json(config_path, config)
        with (root / 'stdout.jsonl').open('w') as stdout, (root / 'stderr.log').open('w') as stderr:
            process = subprocess.Popen(command, cwd=project, env=env, stdout=stdout, stderr=stderr, start_new_session=True)
            timed_out = False
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                kill_owned(process)
    events, parse_errors = [], 0
    for line in (root / 'stdout.jsonl').read_text().splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            parse_errors += 1
    successful_reads, unexpected_reads = read_evidence(events, project, fixture)
    final_text = '\n'.join(e.get('part', {}).get('text', '') for e in events if e.get('type') == 'text')
    finding_score = score({'kind': 'review', 'expected': [{'line': 2, 'kind': 'off_by_one'}]}, final_text)
    report = {'model': model, 'engine': spec['name'], 'elapsed': time.monotonic() - started,
              'exit_code': process.returncode, 'timed_out': timed_out, 'steps_configured': 3,
              'fixture_unchanged': before == fingerprints(project), 'json_events': len(events),
              'non_json_lines': parse_errors, 'successful_read_tools': successful_reads, 'unexpected_completed_reads': unexpected_reads, 'finding_score': finding_score,
              'tool_errors': sum(e.get('type') == 'tool_use' and e.get('part', {}).get('state', {}).get('status') == 'error' for e in events),
              'guarded_upstream_requests': requests,
              'isolation': 'separate XDG configuration/data/cache/state; read-only application permission; not OS sandbox',
              'limits': 'proxy enforces <=3 requests and <=768 output tokens/request; harness 3 model steps; wall timeout'}
    write_json(root / 'report.json', report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--engine', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=180)
    args = parser.parse_args()
    if not 0 < args.timeout <= 300:
        parser.error('timeout must be 0..300 seconds')
    engines = json.loads(args.config.read_text())['engines']
    spec = next(s for s in engines if s['name'] == args.engine)
    if spec.get('kind') == 'strata_line':
        parser.error('OpenCode needs an HTTP engine; raw strata line adapter is not an HTTP server')
    report = run_harness(spec, args.output, args.timeout)
    print(json.dumps(report, indent=2))
    return 1 if report['timed_out'] or report['exit_code'] or not report['fixture_unchanged'] or not report['successful_read_tools'] or report['unexpected_completed_reads'] or not report['finding_score']['passed'] else 0
