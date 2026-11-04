"""Opt-in, one-shot capture at the HTTP boundary; never record auth headers."""
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx


def _write(path, value):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as out:
        json.dump(value, out, ensure_ascii=False, indent=2)
        out.write('\n')


def install(data_dir):
    """An arm file authorizes exactly one matching HTTP attempt, including errors."""
    if getattr(httpx.AsyncClient.send, '_dafeiyu_capture', False):
        return
    folder = Path(data_dir) / 'debug_api'
    arm = folder / 'capture-next'
    original = httpx.AsyncClient.send

    async def send(client, request, *args, **kwargs):
        capture = None
        if (request.method == 'POST' and request.url.host == 'api.deepseek.com'
                and request.url.path.rstrip('/') == '/v1/chat/completions'
                and arm.is_file()):
            try:
                raw = request.content
                body = json.loads(raw)
                if body.get('model') == 'deepseek-flash':
                    # unlink is atomic: concurrent callers cannot both claim the arm.
                    arm.unlink()
                    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
                    capture = folder / ('capture-' + stamp)
                    capture.mkdir(mode=0o700)
                    _write(capture / 'request.log', {
                        'captured_at_utc': stamp,
                        'source': 'httpx.AsyncClient.send: actual SDK HTTP request',
                        'method': request.method,
                        'url': str(request.url),
                        'headers': {k: v for k, v in request.headers.items()
                                    if k.lower() in ('content-type', 'accept', 'user-agent')},
                        'authorization': '[REDACTED; authentication headers not collected]',
                        'body': body,
                    })
                    fd = os.open(capture / 'request-body.json',
                                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, 'wb') as out:
                        out.write(raw)
            except (OSError, ValueError, httpx.RequestNotRead):
                # Diagnostics must never interrupt normal bot traffic.
                capture = None
        try:
            response = await original(client, request, *args, **kwargs)
        except BaseException as exc:
            if capture:
                try:
                    _write(capture / 'error.log', {'exception_type': type(exc).__name__})
                except OSError:
                    pass
            raise
        if capture:
            try:
                if not body.get('stream', False):
                    # aread caches bytes; normal SDK parsing still sees the same response.
                    raw_response = await response.aread()
                    fd = os.open(capture / 'response-body.json',
                                 os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    with os.fdopen(fd, 'wb') as out:
                        out.write(raw_response)
                _write(capture / 'response.log', {
                    'status_code': response.status_code,
                    'request_id': response.headers.get('x-request-id'),
                    'body_captured': not body.get('stream', False),
                    'note': 'Streaming responses are not consumed by this diagnostic.',
                })
            except (OSError, httpx.HTTPError):
                pass
        return response

    send._dafeiyu_capture = True
    httpx.AsyncClient.send = send
