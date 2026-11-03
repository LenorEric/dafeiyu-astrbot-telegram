"""Breeze Blue TTS adapter; API credentials remain in the environment."""
import os
import tempfile
from pathlib import Path

import httpx

from astrbot.core.provider.entities import ProviderType
from astrbot.core.provider.provider import TTSProvider
from astrbot.core.provider.register import register_provider_adapter
from astrbot.core.utils.astrbot_path import get_astrbot_temp_path


@register_provider_adapter(
    'breeze_blue_tts', 'Breeze Blue TTS',
    provider_type=ProviderType.TEXT_TO_SPEECH,
    default_config_tmpl={'id': 'breeze-blue', 'type': 'breeze_blue_tts',
                         'enable': False, 'model': 'breeze-tts-2',
                         'voice_id': 'voc_8yud7hz7c9q2', 'instructions': '',
                         'api_key_env': 'BREEZE_API_KEY', 'timeout': 45},
)
class BreezeBlueTTS(TTSProvider):
    def __init__(self, provider_config, provider_settings):
        super().__init__(provider_config, provider_settings)
        self.set_model(provider_config.get('model', 'breeze-tts-2'))
        self.voice_id = provider_config['voice_id']
        self.instructions = provider_config.get('instructions', '')
        self.key_env = provider_config.get('api_key_env', 'BREEZE_API_KEY')
        self.timeout = float(provider_config.get('timeout', 45))

    async def get_audio(self, text):
        key = os.environ.get(self.key_env, '')
        if not key:
            raise RuntimeError('Breeze API key is not configured')
        payload = {'text': text, 'model_id': self.get_model(),
                   'language_code': 'zh', 'instructions': self.instructions,
                   'voice_settings': {'guidance_scale': 4.0}}
        folder = Path(get_astrbot_temp_path());folder.mkdir(parents=True, exist_ok=True)
        fd, filename = tempfile.mkstemp(prefix='breeze_', suffix='.mp3', dir=folder)
        os.chmod(filename, 0o600)
        try:
            with os.fdopen(fd, 'wb') as output:
                async with httpx.AsyncClient(timeout=self.timeout, trust_env=True) as client:
                    async with client.stream(
                        'POST', f'https://api.breeze.blue/v1/text-to-speech/{self.voice_id}',
                        params={'output_format': 'mp3'}, json=payload,
                        headers={'xi-api-key': key, 'User-Agent': 'dafeiyu/1.0'},
                    ) as response:
                        if response.status_code != 200:
                            raise RuntimeError(f'Breeze synthesis returned HTTP {response.status_code}')
                        if not response.headers.get('content-type', '').startswith('audio/'):
                            raise RuntimeError('Breeze returned a non-audio response')
                        size = 0
                        async for chunk in response.aiter_bytes():
                            size += len(chunk)
                            if size > 20 * 1024 * 1024:
                                raise RuntimeError('Breeze audio exceeds Telegram media limit')
                            output.write(chunk)
            path = Path(filename)
            with path.open('rb') as source:
                header = source.read(3)
            if path.stat().st_size < 512 or not (header == b'ID3' or header[:1] == b'\xff'):
                raise RuntimeError('Breeze did not return a valid MP3')
            return filename
        except BaseException:
            Path(filename).unlink(missing_ok=True)
            raise
