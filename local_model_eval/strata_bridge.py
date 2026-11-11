"""Optional task-owned adapter: JSON lines -> strata-mlx token protocol.

Run with the strata environment's Python (transformers is optional elsewhere).
This is an evaluation adapter, not a production HTTP server or API conformance claim.
"""

import argparse
from collections.abc import Mapping
import json
import queue
import re
import subprocess
import sys
import threading
import time

from .client import kill_owned, read_lines


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def normalize_token_ids(value):
    if isinstance(value, Mapping):
        value = value['input_ids']
    if not isinstance(value, list) or not value or any(type(token) is not int or token < 0 for token in value):
        raise ValueError('tokenizer must return a nonempty flat integer token list')
    return value


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--tokenizer', required=True)
    p.add_argument('--load-timeout', type=float, default=300)
    p.add_argument('engine', nargs=argparse.REMAINDER)
    args = p.parse_args()
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.tokenizer, local_files_only=True, trust_remote_code=False)
    command = args.engine[1:] if args.engine[:1] == ['--'] else args.engine
    started = time.monotonic()
    engine = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                              stderr=sys.stderr, text=True, bufsize=1)
    lines = queue.Queue()
    threading.Thread(target=read_lines, args=(engine.stdout, lines), daemon=True).start()
    requests = queue.Queue()
    lock = threading.Lock()

    def send(line):
        with lock:
            engine.stdin.write(line + '\n')
            engine.stdin.flush()

    def inputs():
        for raw in sys.stdin:
            request = json.loads(raw)
            if request.get('op') == 'stop':
                send('STOP')
            else:
                requests.put(request)
        requests.put(None)

    try:
        info = []
        while True:
            remaining = args.load_timeout - (time.monotonic() - started)
            if remaining <= 0:
                raise TimeoutError('strata readiness deadline exceeded')
            line = lines.get(timeout=remaining)
            if line is None:
                raise RuntimeError('strata exited before READY')
            print(line.rstrip(), file=sys.stderr, flush=True)
            info.append(line.strip())
            if line.startswith(('ERR', 'FATAL')):
                raise RuntimeError(line)
            if line.startswith('READY'):
                break
        emit({'event': 'ready', 'engine_info': info, 'load_seconds': time.monotonic() - started})
        threading.Thread(target=inputs, daemon=True).start()
        while True:
            body = requests.get()
            if body is None:
                break
            try:
                if body.get('tools'):
                    raise ValueError('raw Strata evaluation adapter does not implement native tool/HTTP APIs')
                template = {'add_generation_prompt': True, 'enable_thinking': False, 'tokenize': True}
                ids = normalize_token_ids(tokenizer.apply_chat_template(body['messages'], **template))
                send('GEN ' + str(body.get('max_tokens', 768)) + ' temperature=0 ' + ','.join(map(str, ids)))
                generated, first, raw = [], None, []
                request_start = time.monotonic()
                while True:
                    line = lines.get(timeout=600)
                    if line is None:
                        raise RuntimeError('strata exited during generation')
                    raw.append(line.rstrip())
                    if line.startswith(('ERR', 'FATAL')):
                        raise RuntimeError(line)
                    if line.startswith('T '):
                        generated.append(int(line.split()[1]))
                        if first is None:
                            first = time.monotonic() - request_start
                        emit({'event': 'token'})
                    if line.startswith('DONE '):
                        done = line.split()
                        break
                text = tokenizer.decode(generated, skip_special_tokens=True)
                reasoning = ''
                if '</think>' in text:
                    reasoning, text = text.split('</think>', 1)
                    reasoning = reasoning.removeprefix('<think>').strip()
                elapsed_prompt, elapsed_decode = float(done[3]) / 1000, float(done[4]) / 1000
                tokens = int(done[1])
                emit({'event': 'result', 'result': {'content': re.sub(r'<tool_call>.*?</tool_call>', '', text, flags=re.S).strip(),
                      'reasoning': reasoning, 'tool_calls': [], 'finish_reason': done[5], 'first_event_seconds': first,
                      'first_content_seconds': None, 'server_abort_verified': done[5] == 'cancel',
                      'usage': {'prompt_tokens': len(ids), 'completion_tokens': tokens,
                                'prompt_eval_duration': elapsed_prompt, 'generation_duration': elapsed_decode,
                                'prompt_tokens_per_second': int(done[14]) / elapsed_prompt if elapsed_prompt else None,
                                'generation_tokens_per_second': tokens / elapsed_decode if elapsed_decode else None,
                                'prompt_tokens_read': int(done[14]), 'protocol_done': line.strip()},
                      'raw': raw, 'adapter_limitations': ['no native HTTP', 'JSON format is prompt adherence, not constrained decoding',
                              'native tools/HTTP not tested', 'content TTFT not measured separately from token TTFT']}})
            except Exception as exc:
                emit({'event': 'error', 'error': type(exc).__name__ + ': ' + str(exc)})
    except Exception as exc:
        emit({'event': 'error', 'error': type(exc).__name__ + ': ' + str(exc)})
    finally:
        if engine.poll() is None:
            engine.terminate()
            try:
                engine.wait(timeout=5)
            except subprocess.TimeoutExpired:
                engine.kill()
                engine.wait(timeout=5)


if __name__ == '__main__':
    main()
