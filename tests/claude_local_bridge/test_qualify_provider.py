import importlib.util
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest


spec = importlib.util.spec_from_file_location(
    'qualify_aggregator', Path(__file__).resolve().parents[2] / 'claude_local_bridge/qualify_aggregator.py'
)
qualifier = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualifier)


def stream(*events):
    return io.BytesIO(b''.join(b'data: ' + json.dumps(event).encode() + b'\n\n' for event in events))


def test_stream_reconstructs_split_tool_arguments():
    result = qualifier.read_stream(stream(
        {'type': 'message_start', 'message': {'type': 'message', 'content': []}},
        {'type': 'content_block_start', 'index': 0, 'content_block': {'type': 'tool_use', 'id': 'call_1', 'name': 'lookup', 'input': {}}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'input_json_delta', 'partial_json': '{"id":'}},
        {'type': 'content_block_delta', 'index': 0, 'delta': {'type': 'input_json_delta', 'partial_json': '42}'}},
        {'type': 'message_delta', 'delta': {'stop_reason': 'tool_use'}},
        {'type': 'message_stop'},
    ))
    assert result['content'][0]['input'] == {'id': 42}
    assert result['stop_reason'] == 'tool_use'


@pytest.mark.parametrize('events', [
    [{'type': 'message_start', 'message': {}}],
    [{'type': 'error', 'error': {'message': 'upstream failed'}}],
])
def test_stream_requires_completion_and_rejects_sse_errors(events):
    with pytest.raises(ValueError):
        qualifier.read_stream(stream(*events))


@pytest.mark.parametrize('honest', [True, False])
def test_qualification_requires_real_tool_arguments_and_independent_result(honest):
    def fake_request(base, path, payload, timeout):
        if path.endswith('count_tokens'):
            return {'input_tokens': 42}
        if payload['max_tokens'] == 1:
            return {'type': 'message'}
        if len(payload['messages']) == 1:
            return {'content': [{'type': 'tool_use', 'id': 'call_1', 'name': 'lookup_receipt', 'input': {'receipt_id': 'test-42'}}], 'stop_reason': 'tool_use'}
        confirmation = json.loads(payload['messages'][-1]['content'][0]['content'])['confirmation']
        return {'content': [{'type': 'text', 'text': confirmation if honest else 'invented success'}], 'stop_reason': 'end_turn'}

    with patch.object(qualifier, 'request', side_effect=fake_request):
        result = qualifier.qualify('http://localhost', 'aggregator/test', 1)
    assert result['passed'] is honest


def test_plain_text_claim_is_not_a_tool_call():
    with patch.object(qualifier, 'request', side_effect=[
        {'type': 'message'}, {'input_tokens': 42},
        {'content': [{'type': 'text', 'text': 'I called the tool.'}], 'stop_reason': 'end_turn'},
    ]):
        result = qualifier.qualify('http://localhost', 'aggregator/test', 1)
    assert result['passed'] is False
    assert result['checks']['tool_call'] is False
