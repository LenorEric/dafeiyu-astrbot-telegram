import asyncio
import base64
import gzip
import json
import os
import sys
import subprocess
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'deploy/telegram'))
import api_log


class QueueTests(unittest.TestCase):
    def test_fifo_hard_limit_keeps_whole_records(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model-api.jsonl'
            queue = api_log.ApiLogQueue(path, 4096)
            for i in range(30):
                queue.put({'id': str(i), 'state': 'complete', 'text': '完整内容' * 30})
            records = [json.loads(line) for line in path.read_bytes().splitlines()]
            self.assertLessEqual(path.stat().st_size, 4096)
            self.assertLess(len(records), 30)
            self.assertEqual(records[-1]['id'], '29')
            self.assertEqual([int(r['id']) for r in records], list(range(30 - len(records), 30)))
            self.assertTrue(all(r['text'] == '完整内容' * 30 for r in records))
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_large_compressible_record_is_lossless(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'api.jsonl'
            record = {'id': 'large', 'request': {'body': '人格。' * 3000},
                      'response': {'body': 'reasoning' * 3000}}
            api_log.ApiLogQueue(path, 4096).put(record)
            packed = json.loads(path.read_text())
            self.assertEqual(packed['encoding'], 'gzip+base64')
            self.assertEqual(api_log.decode_record(packed), record)
            self.assertLessEqual(path.stat().st_size, 4096)

    def test_incompressible_oversize_is_explicit_not_silently_clipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'api.jsonl'
            with self.assertLogs('dafeiyu.api_log', level='WARNING'):
                api_log.ApiLogQueue(path, 4096).put({'id': 'huge', 'body': os.urandom(20000).hex()})
            record = json.loads(path.read_text())
            self.assertEqual(record['state'], 'oversize_not_stored')
            self.assertNotIn('body', record)
            self.assertLessEqual(path.stat().st_size, 4096)

    def test_pending_update_and_concurrent_writers(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'api.jsonl'
            queue = api_log.ApiLogQueue(path)
            queue.put({'id': 'same', 'state': 'pending'})
            queue.put({'id': 'same', 'state': 'complete'})
            def write(i):
                api_log.ApiLogQueue(path).put({'id': str(i), 'state': 'complete'})
            with ThreadPoolExecutor(max_workers=6) as pool:
                list(pool.map(write, range(20)))
            records = [json.loads(line) for line in path.read_bytes().splitlines()]
            self.assertEqual(len(records), 21)
            self.assertEqual([r for r in records if r['id'] == 'same'], [{'id': 'same', 'state': 'complete'}])
            self.assertLessEqual(path.stat().st_size, api_log.LIMIT_BYTES)
            self.assertFalse(list(path.parent.glob('*.tmp')))


class Stream(httpx.AsyncByteStream):
    def __init__(self, chunks):
        self.chunks = chunks
        self.yielded = 0
        self.closed = False
    async def __aiter__(self):
        for chunk in self.chunks:
            self.yielded += 1
            yield chunk
    async def aclose(self): self.closed = True


class CaptureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'logs/api.jsonl'
        self.original = httpx.AsyncClient.send
        api_log.install(self.path)

    def tearDown(self):
        httpx.AsyncClient.send = self.original
        self.tmp.cleanup()

    def records(self):
        return [api_log.decode_record(json.loads(line))
                for line in self.path.read_bytes().splitlines()] if self.path.exists() else []

    async def test_complete_bodies_headers_reasoning_and_usage(self):
        payload = {'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': '真实输入'}]}
        raw = json.dumps({'id': 'api-id', 'choices': [{'message': {'content': '{}',
                         'reasoning_content': 'full reasoning'}, 'finish_reason': 'stop'}],
                         'usage': {'total_tokens': 123}}, ensure_ascii=False).encode()
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, content=raw, headers={'set-cookie': 'secret-cookie'}))) as client:
            response = await client.post('https://api.deepseek.com/v1/chat/completions', json=payload,
                                         headers={'Authorization': 'Bearer secret-key', 'x-api-key': 'secret-key-2'})
        record, = self.records()
        self.assertEqual(json.loads(record['request']['body']), payload)
        self.assertEqual(record['response']['body'].encode(), raw)
        self.assertEqual(response.content, raw)
        self.assertEqual(record['response_id'], 'api-id')
        self.assertNotIn('secret-key', self.path.read_text())
        self.assertNotIn('secret-cookie', self.path.read_text())
        self.assertEqual(record['state'], 'complete')

    async def test_http_error_and_retry_attempts_are_both_retained(self):
        count = 0
        def handler(_):
            nonlocal count
            count += 1
            return httpx.Response(429 if count == 1 else 200, json={'attempt': count})
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await client.post('https://api.deepseek.com/v1/chat/completions', json={'test': 1})
            await client.post('https://api.deepseek.com/v1/chat/completions', json={'test': 1})
        self.assertEqual([r['response']['status_code'] for r in self.records()], [429, 200])

    async def test_transport_failure_retains_request(self):
        def handler(request): raise httpx.ReadTimeout('fixture', request=request)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with self.assertRaises(httpx.ReadTimeout):
                await client.post('https://api.deepseek.com/v1/chat/completions', content='whole request')
        record, = self.records()
        self.assertEqual(record['request']['body'], 'whole request')
        self.assertEqual(record['state'], 'transport_error')
        self.assertEqual(record['error_type'], 'ReadTimeout')

    async def test_streaming_is_not_prefetched_and_full_bytes_are_retained(self):
        source = Stream([b'data: one\n\n', b'data: two\n\n'])
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=source))) as client:
            async with client.stream('POST', 'https://api.deepseek.com/v1/chat/completions', json={'stream': True}) as response:
                self.assertEqual(source.yielded, 0)
                self.assertEqual(self.records()[0]['state'], 'pending')
                self.assertEqual(await response.aread(), b'data: one\n\ndata: two\n\n')
        record, = self.records()
        self.assertEqual(record['response']['body'], 'data: one\n\ndata: two\n\n')
        self.assertTrue(record['response']['complete'])
        self.assertTrue(source.closed)

    async def test_early_stream_close_is_labeled_incomplete(self):
        source = Stream([b'first', b'second'])
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, stream=source))) as client:
            async with client.stream('POST', 'https://api.deepseek.com/v1/chat/completions') as response:
                async for _ in response.aiter_bytes(): break
        record, = self.records()
        self.assertEqual(record['state'], 'incomplete')
        self.assertFalse(record['response']['complete'])
        self.assertEqual(record['response']['body'], 'first')

    async def test_compressed_response_preserves_transport_and_client_content(self):
        raw = b'{"id":"compressed","thinking":"all reasoning","usage":{"total_tokens":42}}'
        compressed = gzip.compress(raw)
        source = Stream([compressed])
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda _: httpx.Response(200, stream=source, headers={'content-encoding': 'gzip'}))) as client:
            async with client.stream('POST', 'https://api.deepseek.com/v1/chat/completions') as response:
                self.assertEqual(await response.aread(), raw)
        record, = self.records()
        self.assertEqual(gzip.decompress(base64.b64decode(record['response']['body'])), raw)
        self.assertEqual(record['response_id'], 'compressed')
        script = Path(__file__).resolve().parents[1] / 'deploy/read-api-log.py'
        result = subprocess.run([sys.executable, str(script), '--path', str(self.path),
                                 '--part', 'response'], capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), json.loads(raw))

    async def test_unrelated_traffic_is_not_recorded(self):
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text='ok'))) as client:
            await client.post('https://api.telegram.org/bot-fixture/getUpdates')
        self.assertEqual(self.records(), [])

    async def test_log_write_failure_does_not_break_model_call(self):
        with patch.object(api_log.ApiLogQueue, 'put', side_effect=OSError('fixture')), \
             self.assertLogs('dafeiyu.api_log', level='WARNING'):
            async with httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, text='ok'))) as client:
                response = await client.post('https://api.deepseek.com/v1/chat/completions')
        self.assertEqual(response.text, 'ok')


if __name__ == '__main__':
    unittest.main()
