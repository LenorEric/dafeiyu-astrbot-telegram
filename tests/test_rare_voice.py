import importlib.util
import ast
import asyncio
import logging
import os
import random
import traceback
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('voice_layout', ROOT / 'deploy/patches/chat_layout.py')
layout = importlib.util.module_from_spec(spec);spec.loader.exec_module(layout)


class RareVoiceTests(unittest.TestCase):
    def test_only_emotional_candidates_and_global_ten_minute_cooldown(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'cooldown.json'
            gate = layout.RareVoiceGate(state)
            self.assertFalse(gate.reserve(None, now=1000))
            self.assertFalse(state.exists())
            self.assertTrue(gate.reserve('pouting', now=1000))
            # A new instance/session/restart uses the same global reservation.
            other = layout.RareVoiceGate(state)
            self.assertFalse(other.reserve('excited', now=1599))
            self.assertTrue(other.reserve('excited', now=1600))
            # No message-gap requirement, daily quota or random sampling.
            self.assertTrue(other.reserve('shy', now=2200))
            self.assertEqual(state.stat().st_mode & 0o777, 0o600)

    def test_corrupt_cooldown_fails_closed(self):
        with tempfile.TemporaryDirectory() as folder:
            state = Path(folder) / 'cooldown.json';state.write_text('broken')
            self.assertFalse(layout.RareVoiceGate(state).reserve('pouting'))

    def test_control_marker_is_removed_without_adding_dialogue(self):
        self.assertEqual(layout.extract_voice_intent('哼，才没有想你呢！ [[VOICE:pouting]]'), ('哼，才没有想你呢！', 'pouting'))
        self.assertEqual(layout.extract_voice_intent('晚安呀 [[VOICE:requested]]'), ('晚安呀', 'requested'))
        for text in ('普通解释。', '`[[VOICE:shy]]`', '```text\n[[VOICE:excited]]'):
            self.assertEqual(layout.extract_voice_intent(text), (text, None))
        self.assertEqual(layout.extract_voice_intent('普通解释。[[VOICE:neutral]]'), ('普通解释。', None))

    def test_current_user_voice_requests_negation_and_quoted_examples(self):
        for text in ('发条语音', '用语音回复我', '想听你说晚安', '唱首小星星给我听', '唱歌', '把“欢迎回来”读给我听'):
            self.assertEqual(layout.user_voice_request(text), 'voice', text)
        for text in ('别发语音', '不要唱首歌', '只发文字', '用文字回复', '文字就好'):
            self.assertEqual(layout.user_voice_request(text), 'text', text)
        for text in ('如何配置发送语音？', '你说“发条语音”是什么意思', '```\n发条语音\n```', '讨论一下今天的天气'):
            self.assertIsNone(layout.user_voice_request(text), text)
        self.assertEqual(layout.user_voice_request('不要发语音，还是唱首歌吧'), 'voice')


class VoicePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_environment_gate_survives_normalized_tts_settings(self):
        tree = ast.parse((ROOT / 'deploy/patches/stage.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ResultDecorateStage')
        init = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'initialize')
        init.returns = None
        for arg in init.args.args:arg.annotation = None
        config = {
            'platform_settings': {'reply_prefix': '', 'reply_with_mention': False, 'reply_with_quote': False, 'forward_threshold': 1500,
                                  'segmented_reply': {'words_count_threshold': 150, 'enable': True, 'only_llm_result': True, 'regex': '.*', 'content_cleanup_rule': ''}},
            't2i_word_threshold': 150, 't2i_strategy': 'remote', 't2i_active_template': '',
            'provider_tts_settings': {'enable': True, 'provider_id': 'breeze-blue', 'dual_output': False},
            'content_safety': {'also_use_in_response': False}, 'provider_settings': {},
        }
        with tempfile.TemporaryDirectory() as folder:
            ns = dict(os=os, Path=Path, re=__import__('re'), RareVoiceGate=layout.RareVoiceGate,
                      get_astrbot_data_path=lambda: folder, logger=logging.getLogger('voice-test'))
            exec(compile(ast.fix_missing_locations(ast.Module(body=[init], type_ignores=[])), '<tts-init>', 'exec'), ns)
            for flag in ('1', '0'):
                with patch.dict(os.environ, {'DAFEIYU_RARE_VOICE': flag}):
                    stage = NS()
                    await ns['initialize'](stage, NS(astrbot_config=config))
                    self.assertEqual(stage.rare_voice, flag == '1')

    async def test_voice_text_exclusion_cooldown_and_synthesis_failure(self):
        class Plain:
            def __init__(self, text):self.text = text
        class Record:
            def __init__(self, **kw):self.__dict__.update(kw)
        class Image:pass
        tree = ast.parse((ROOT / 'deploy/patches/stage.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'ResultDecorateStage')
        process = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'process')
        process.returns = None
        for arg in process.args.args:arg.annotation = None
        ns = dict(asyncio=asyncio, random=random, traceback=traceback,
                  Plain=Plain, Record=Record, Image=Image,
                  logger=logging.getLogger('voice-test'),
                  make_tts_text=layout.make_tts_text, is_valid_audio_file=layout.is_valid_audio_file,
                  ResultContentType=NS(STREAMING_RESULT='stream', STREAMING_FINISH='finished'),
                  SessionServiceManager=NS(should_process_tts_request=AsyncMock(return_value=True)),
                  star_handlers_registry=NS(get_handlers_by_event_type=lambda *a, **k: []),
                  EventType=NS(OnDecoratingResultEvent='decorate'))
        exec(compile(ast.fix_missing_locations(ast.Module(body=[process], type_ignores=[])), '<tts-stage>', 'exec'), ns)
        with tempfile.TemporaryDirectory() as folder:
            audio = Path(folder) / 'sample.mp3';audio.write_bytes(b'ID3'+b'0'*1024)
            provider = NS(get_audio=AsyncMock(return_value=str(audio)))
            config = {'provider_tts_settings': {'enable': True, 'dual_output': True, 'use_file_service': False}, 'callback_api_base': '', 't2i': False}
            stage = NS(ctx=NS(astrbot_config=config, plugin_manager=NS(context=NS(get_using_tts_provider_async=AsyncMock(return_value=provider)))),
                       content_safe_check_reply=False, reply_prefix='', enable_segmented_reply=False,
                       rare_voice=True, voice_gate=layout.RareVoiceGate(Path(folder)/'cooldown.json'),
                       show_reasoning=False, tts_max_chars=1000, tts_timeout_s=45,
                       reply_with_mention=False, reply_with_quote=False)
            async def run(emotion, requested=False, text_only=False):
                result = NS(chain=[Plain('哼，才没有想你呢！')], result_content_type='llm',
                            is_llm_result=lambda: True, use_t2i_=None)
                event = NS(get_result=lambda: result, plugins_name=None, is_stopped=lambda: False,
                           unified_msg_origin='telegram:GroupMessage:-100',
                           get_extra=lambda key, default=None: {'_fy_voice_emotion': emotion, '_fy_voice_requested': requested, '_fy_voice_text_only': text_only}.get(key, default))
                async for _ in ns['process'](stage, event):pass
                return result
            voiced = await run('pouting')
            self.assertEqual(len(voiced.chain), 1)
            self.assertIsInstance(voiced.chain[0], Record)
            self.assertEqual(voiced.chain[0].text, '')
            cooldown_before = stage.voice_gate.state_path.read_bytes()
            for _ in range(2):
                on_demand = await run(None, requested=True)
                self.assertIsInstance(on_demand.chain[0], Record)
            self.assertEqual(stage.voice_gate.state_path.read_bytes(), cooldown_before)
            text_only = await run('excited', requested=True, text_only=True)
            self.assertIsInstance(text_only.chain[0], Plain)
            second = await run('excited')
            self.assertIsInstance(second.chain[0], Plain)
            self.assertEqual(provider.get_audio.await_count, 3)
            stage.voice_gate = layout.RareVoiceGate(Path(folder)/'different-cooldown.json')
            ordinary = await run(None)
            self.assertIsInstance(ordinary.chain[0], Plain)
            provider.get_audio.side_effect = RuntimeError('synthetic synthesis failure')
            with self.assertLogs('voice-test', level='ERROR'):
                failed = await run('surprised')
            self.assertIsInstance(failed.chain[0], Plain)


if __name__ == '__main__':
    unittest.main()
