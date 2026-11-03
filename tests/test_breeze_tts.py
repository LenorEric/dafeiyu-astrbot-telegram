import importlib.util
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
from unittest.mock import patch

import httpx

ROOT = Path(__file__).resolve().parents[1]


class BreezeTests(unittest.IsolatedAsyncioTestCase):
    async def test_authenticated_audio_and_failed_response_cleanup(self):
        class Base:
            def __init__(self, *args): pass
            def set_model(self, value): self.model = value
            def get_model(self): return self.model
        def module(name, **attrs):
            m = ModuleType(name);m.__dict__.update(attrs);return m
        with tempfile.TemporaryDirectory() as folder:
            stubs = {
                'astrbot.core.provider.entities': module('entities', ProviderType=NS(TEXT_TO_SPEECH='tts')),
                'astrbot.core.provider.provider': module('provider', TTSProvider=Base),
                'astrbot.core.provider.register': module('register', register_provider_adapter=lambda *a, **k: lambda cls: cls),
                'astrbot.core.utils.astrbot_path': module('path', get_astrbot_temp_path=lambda: folder),
            }
            with patch.dict(sys.modules, stubs):
                spec = importlib.util.spec_from_file_location('breeze_provider', ROOT / 'deploy/telegram/breeze_tts.py')
                mod = importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
            provider = mod.BreezeBlueTTS({'voice_id': 'fixture', 'instructions': '标准普通话，清亮甜软'}, {})
            requests = []
            def response(request):
                requests.append(request)
                return httpx.Response(200, headers={'content-type': 'audio/mpeg'}, content=b'ID3'+b'0'*1024)
            client_type = httpx.AsyncClient
            def client(*args, **kwargs):
                return client_type(*args, **kwargs, transport=httpx.MockTransport(response))
            with patch.dict(os.environ, {'BREEZE_API_KEY': 'test-key'}), patch.object(mod.httpx, 'AsyncClient', client):
                audio = Path(await provider.get_audio('哼，才没有想你呢！'))
            self.assertTrue(audio.exists())
            self.assertEqual(audio.stat().st_mode & 0o777, 0o600)
            self.assertEqual(requests[0].headers['xi-api-key'], 'test-key')
            self.assertIn('instructions', requests[0].read().decode())
            self.assertEqual(requests[0].url.params['output_format'], 'mp3')
            audio.unlink()
            def response(request):
                return httpx.Response(401, json={'detail': 'rejected'})
            with patch.dict(os.environ, {'BREEZE_API_KEY': 'test-key'}), patch.object(mod.httpx, 'AsyncClient', client):
                with self.assertRaisesRegex(RuntimeError, 'HTTP 401'):
                    await provider.get_audio('测试')
            self.assertEqual(list(Path(folder).iterdir()), [])


if __name__ == '__main__':
    unittest.main()
