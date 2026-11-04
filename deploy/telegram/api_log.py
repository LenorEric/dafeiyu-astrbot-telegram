"""Bounded FIFO of complete DeepSeek HTTP attempts, before presentation parsing."""
import base64
import fcntl
import gzip
import hashlib
import json
import logging
import os
import tempfile
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

LIMIT_BYTES = 1024 * 1024
LOGGER = logging.getLogger('dafeiyu.api_log')
SECRET_HEADERS = {'authorization', 'proxy-authorization', 'cookie', 'set-cookie',
                  'x-api-key', 'api-key', 'xi-api-key'}


def body_fields(raw):
    try:
        return {'body': raw.decode('utf-8'), 'body_encoding': 'utf-8', 'body_bytes': len(raw)}
    except UnicodeDecodeError:
        return {'body': base64.b64encode(raw).decode('ascii'),
                'body_encoding': 'base64', 'body_bytes': len(raw)}


def safe_headers(headers):
    return [[key, '[REDACTED]' if (key.lower() in SECRET_HEADERS
                                  or 'token' in key.lower()
                                  or 'api-key' in key.lower()) else value]
            for key, value in headers.multi_items()]


def safe_url(url):
    parts = urlsplit(str(url))
    query = [(key, '[REDACTED]' if any(s in key.lower() for s in
              ('key', 'token', 'secret', 'password', 'signature', 'credential')) else value)
             for key, value in parse_qsl(parts.query, keep_blank_values=True)]
    return urlunsplit((parts.scheme, parts.netloc.rsplit('@', 1)[-1], parts.path,
                       urlencode(query), parts.fragment))


def decode_record(record):
    """Decode the optional lossless envelope used only for oversized records."""
    if record.get('encoding') != 'gzip+base64':
        return record
    raw = gzip.decompress(base64.b64decode(record['data']))
    if hashlib.sha256(raw).hexdigest() != record['sha256']:
        raise ValueError('API log checksum mismatch')
    return json.loads(raw)


class ApiLogQueue:
    def __init__(self, path, limit=LIMIT_BYTES):
        self.path = Path(path)
        self.limit = limit
        self.lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        try:
            fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            os.close(fd)

    def put(self, record):
        """Atomically insert/update one call, evicting oldest complete records."""
        raw = json.dumps(record, ensure_ascii=False, separators=(',', ':')).encode()
        packed = raw
        if len(raw) + 1 > self.limit:
            compressed = gzip.compress(raw, mtime=0)
            envelope = {'id': record['id'], 'encoding': 'gzip+base64',
                        'sha256': hashlib.sha256(raw).hexdigest(), 'raw_bytes': len(raw),
                        'data': base64.b64encode(compressed).decode('ascii')}
            packed = json.dumps(envelope, separators=(',', ':')).encode()
            if len(packed) + 1 > self.limit:
                # Completeness and a hard size cap cannot both hold for such a call.
                # Never silently clip JSON, or retain only a misleading suffix.
                summary = {'id': record['id'], 'state': 'oversize_not_stored',
                           'started_at': record.get('started_at'),
                           'finished_at': record.get('finished_at'),
                           'raw_bytes': len(raw), 'compressed_record_bytes': len(packed) + 1,
                           'sha256': hashlib.sha256(raw).hexdigest(),
                           'reason': 'Complete record exceeds the hard limit even after lossless compression'}
                packed = json.dumps(summary, separators=(',', ':')).encode()
                LOGGER.warning('API log oversize: id=%s raw_bytes=%d; body not stored', record['id'], len(raw))
        line = packed + b'\n'
        if len(line) > self.limit:
            raise ValueError('API log limit too small for metadata')
        with self.lock:
            fd = os.open(str(self.path) + '.lock', os.O_CREAT | os.O_RDWR, 0o600)
            with os.fdopen(fd, 'a+b') as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                lines = []
                if self.path.exists():
                    with self.path.open('rb') as existing:
                        existing.seek(max(0, self.path.stat().st_size - self.limit))
                        for old in existing.read().splitlines(keepends=True):
                            try:
                                parsed = json.loads(old)
                                if parsed.get('id') != record['id']:
                                    lines.append(old if old.endswith(b'\n') else old + b'\n')
                            except (ValueError, AttributeError):
                                pass
                # Updates are latest observations; retain a pending request until it completes.
                lines.append(line)
                total = sum(map(len, lines))
                while total > self.limit:
                    total -= len(lines.pop(0))
                temp_fd, temp_name = tempfile.mkstemp(prefix='.model-api-', suffix='.tmp', dir=self.path.parent)
                try:
                    with os.fdopen(temp_fd, 'wb') as out:
                        out.writelines(lines)
                        out.flush()
                        os.fsync(out.fileno())
                    os.replace(temp_name, self.path)
                finally:
                    Path(temp_name).unlink(missing_ok=True)


class ResponseTee(httpx.AsyncByteStream):
    def __init__(self, stream, finish):
        self.stream = stream
        self.finish = finish
        self.chunks = bytearray()
        self.finished = False

    async def __aiter__(self):
        try:
            async for chunk in self.stream:
                self.chunks.extend(chunk)
                yield chunk
        except BaseException as exc:
            if not self.finished:
                self.finish(bytes(self.chunks), False, type(exc).__name__)
                self.finished = True
            raise
        else:
            if not self.finished:
                self.finish(bytes(self.chunks), True, None)
                self.finished = True

    async def aclose(self):
        try:
            await self.stream.aclose()
        finally:
            if not self.finished:
                self.finish(bytes(self.chunks), False, 'stream_closed_early')
                self.finished = True


def install(path):
    """Capture every service-side DeepSeek HTTP attempt, including retries/errors."""
    original = httpx.AsyncClient.send
    if getattr(original, '_dafeiyu_api_log', False):
        return
    queue = ApiLogQueue(path)

    def persist(record):
        try:
            queue.put(record)
        except Exception as exc:
            # A disk/logging failure must not become a failed API request.
            LOGGER.warning('API log write failed: id=%s error=%s', record['id'], type(exc).__name__)

    async def send(client, request, *args, **kwargs):
        if request.url.host != 'api.deepseek.com':
            return await original(client, request, *args, **kwargs)
        start = time.monotonic()
        record = {'id': uuid.uuid4().hex, 'started_at': datetime.now(timezone.utc).isoformat(),
                  'state': 'pending', 'request': {'method': request.method,
                  'url': safe_url(request.url), 'headers': safe_headers(request.headers)}}
        try:
            raw_request = await request.aread()
            record['request'].update(body_fields(raw_request))
        except Exception as exc:
            record['request']['body_error'] = type(exc).__name__
        persist(record)
        try:
            response = await original(client, request, *args, **kwargs)
        except BaseException as exc:
            record.update(state='transport_error', error_type=type(exc).__name__,
                          finished_at=datetime.now(timezone.utc).isoformat(),
                          elapsed_ms=round((time.monotonic() - start) * 1000))
            persist(record)
            raise
        record['response'] = {'status_code': response.status_code,
                              'headers': safe_headers(response.headers)}

        def finish(raw_response, complete, error):
            record['response'].update(body_fields(raw_response))
            record['response']['complete'] = complete
            record.update(state='complete' if complete else 'incomplete',
                          finished_at=datetime.now(timezone.utc).isoformat(),
                          elapsed_ms=round((time.monotonic() - start) * 1000))
            if error:
                record['error_type'] = error
            try:
                inspect_body = raw_response
                if (record['response'].get('body_source') == 'httpx_raw_stream'
                        and response.headers.get('content-encoding', '').lower() == 'gzip'):
                    inspect_body = gzip.decompress(raw_response)
                value = json.loads(inspect_body)
                if isinstance(value, dict):
                    record['response_id'] = value.get('id')
            except Exception:
                pass
            persist(record)

        if response.is_stream_consumed:
            record['response']['body_source'] = 'httpx_decoded_content'
            finish(response.content, True, None)
        else:
            # Tee rather than pre-read: streaming latency/cancellation stays intact.
            record['response']['body_source'] = 'httpx_raw_stream'
            response.stream = ResponseTee(response.stream, finish)
            persist(record)
        return response

    send._dafeiyu_api_log = True
    httpx.AsyncClient.send = send
