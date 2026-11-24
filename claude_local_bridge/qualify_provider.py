#!/usr/bin/env python3
"""Exercise gateway routes through the bridge with synthetic, inert tool results."""

import argparse
import concurrent.futures
import copy
import json
import secrets
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


def request(base_url, path, payload=None, timeout=60):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        base_url.rstrip('/') + path,
        data=data,
        headers={'content-type': 'application/json', 'anthropic-version': '2023-06-01'},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        if 'text/event-stream' not in response.headers.get('content-type', ''):
            return json.load(response)
        return read_stream(response)


def read_stream(response):
    message = None
    blocks = {}
    inputs = {}
    stopped = False
    for line in response:
        if not line.startswith(b'data: '):
            continue
        event = json.loads(line[6:])
        kind = event.get('type')
        if kind == 'error':
            raise ValueError(f"SSE error: {event.get('error')}")
        if kind == 'message_start':
            message = event['message']
        elif kind == 'content_block_start':
            blocks[event['index']] = event['content_block']
        elif kind == 'content_block_delta':
            index = event['index']
            delta = event['delta']
            if delta['type'] == 'input_json_delta':
                inputs[index] = inputs.get(index, '') + delta['partial_json']
            elif delta['type'] in ('text_delta', 'thinking_delta', 'signature_delta'):
                key = {'text_delta': 'text', 'thinking_delta': 'thinking', 'signature_delta': 'signature'}[delta['type']]
                blocks[index][key] = (blocks[index].get(key) or '') + delta[key]
        elif kind == 'message_delta' and message is not None:
            message.update(event['delta'])
            message.setdefault('usage', {}).update(event.get('usage', {}))
        elif kind == 'message_stop':
            stopped = True
    if message is None or not stopped:
        raise ValueError('incomplete SSE message')
    for index, value in inputs.items():
        blocks[index]['input'] = json.loads(value)
    message['content'] = [blocks[index] for index in sorted(blocks)]
    return message


def qualify(base_url, route, timeout, stream_tools=False):
    started = time.monotonic()
    record = {'route': route, 'checks': {}, 'responses': {}}
    tool = {
        'name': 'lookup_receipt',
        'description': 'Look up the receipt. Call once, then report the returned confirmation verbatim.',
        'input_schema': {
            'type': 'object', 'properties': {'receipt_id': {'type': 'string'}},
            'required': ['receipt_id'], 'additionalProperties': False,
        },
    }
    base = {
        'model': route, 'max_tokens': 1024,
        'system': [{'type': 'text', 'text': 'Use the requested tool once. After its result, report its confirmation without further calls.', 'cache_control': {'type': 'ephemeral'}}],
        'messages': [{'role': 'user', 'content': 'Call lookup_receipt with receipt_id test-42. Report its confirmation.'}],
    }
    validation = copy.deepcopy(base)
    validation.update(max_tokens=1, messages=[{'role': 'user', 'content': [{'type': 'text', 'text': 'Hi', 'cache_control': {'type': 'ephemeral'}}]}])
    for name, path, payload in [
        ('validation', '/v1/messages', validation),
        ('count_tokens', '/v1/messages/count_tokens', {k: v for k, v in base.items() if k != 'max_tokens'}),
    ]:
        try:
            response = request(base_url, path, payload, timeout)
            record['responses'][name] = response
            record['checks'][name] = (response.get('type') == 'message' if name == 'validation'
                                      else type(response.get('input_tokens')) is int and response['input_tokens'] > 0)
        except (urllib.error.URLError, ValueError, TimeoutError, OSError) as error:
            record['checks'][name] = False
            record.setdefault('stage_errors', {})[name] = error.read().decode()[:2000] if isinstance(error, urllib.error.HTTPError) else str(error)
    try:
        payload = base | {'tools': [tool], 'tool_choice': {'type': 'auto'}, 'stream': stream_tools}
        response = request(base_url, '/v1/messages', payload, timeout)
        record['responses']['tool_call'] = response
        calls = [block for block in response.get('content', []) if block.get('type') == 'tool_use']
        valid = len(calls) == 1 and calls[0].get('id') and calls[0].get('name') == tool['name'] and calls[0].get('input') == {'receipt_id': 'test-42'} and response.get('stop_reason') == 'tool_use'
        record['checks']['tool_call'] = bool(valid)
        if not valid:
            raise ValueError('expected one structured lookup_receipt(test-42) tool call')
        marker = 'KQ-' + secrets.token_hex(8)
        continuation = copy.deepcopy(payload)
        continuation['stream'] = True
        continuation['messages'] += [
            {'role': 'assistant', 'content': response['content']},
            {'role': 'user', 'content': [{'type': 'tool_result', 'tool_use_id': calls[0]['id'], 'content': json.dumps({'confirmation': marker})}]},
        ]
        response = request(base_url, '/v1/messages', continuation, timeout)
        record['responses']['continuation'] = response
        text = '\n'.join(block.get('text', '') for block in response.get('content', []) if block.get('type') == 'text')
        record['checks']['streamed_continuation'] = marker in text and response.get('stop_reason') == 'end_turn' and not any(block.get('type') == 'tool_use' for block in response.get('content', []))
    except (urllib.error.URLError, ValueError, TimeoutError, OSError, KeyError, TypeError) as error:
        record['error'] = error.read().decode()[:2000] if isinstance(error, urllib.error.HTTPError) else str(error)
    record['passed'] = all(record['checks'].get(check) is True for check in ('validation', 'count_tokens', 'tool_call', 'streamed_continuation'))
    record['seconds'] = round(time.monotonic() - started, 2)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--base-url', default='http://127.0.0.1:1245')
    parser.add_argument('--model', action='append', help='Exact upstream model ID; repeat to select several.')
    parser.add_argument('--all-models', action='store_true', help='Spend API tokens testing every discovered gateway model.')
    parser.add_argument('--provider', choices=['aggregator-anthropic', 'aggregator-openai'], action='append')
    parser.add_argument('--stream-tools', action='store_true', help='Also request the initial tool call as SSE.')
    parser.add_argument('--workers', type=int, choices=range(1, 5), default=3)
    parser.add_argument('--timeout', type=float, default=60)
    parser.add_argument('--output', type=Path, required=True, help='JSON report path (use an ignored tmp/ directory).')
    args = parser.parse_args()
    if not args.model and not args.all_models:
        parser.error('select --model or explicitly opt into --all-models')
    providers = args.provider or ['aggregator-anthropic', 'aggregator-openai']
    catalog = request(args.base_url, '/v1/models', timeout=args.timeout)
    routes = sorted({model['id'] for model in catalog['data'] if any(model['id'].startswith(provider + '/') for provider in providers) and (args.all_models or model.get('upstream_model_id') in args.model or model['id'].split('/', 1)[1] in args.model)})
    if not routes:
        parser.error('no matching gateway routes discovered')
    results = []
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = [pool.submit(qualify, args.base_url, route, args.timeout, args.stream_tools) for route in routes]
        for future in concurrent.futures.as_completed(futures):
            record = future.result()
            results.append(record)
            print(json.dumps({key: record[key] for key in ('route', 'checks', 'passed', 'seconds')}), flush=True)
            report = {'created_at': datetime.now(timezone.utc).isoformat(), 'base_url': args.base_url, 'stream_tools': args.stream_tools, 'results': sorted(results, key=lambda item: item['route'])}
            temporary = args.output.with_suffix(args.output.suffix + '.tmp')
            temporary.write_text(json.dumps(report, indent=2) + '\n')
            temporary.replace(args.output)
    return 0 if all(record['passed'] for record in results) else 1


if __name__ == '__main__':
    raise SystemExit(main())
