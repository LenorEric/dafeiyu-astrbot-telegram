"""Real SDK/provider/plugin regression with mock HTTP; no paid API or Telegram calls."""
import asyncio
import copy
import importlib.util
import json
import os
import re
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

import httpx

ROOT = Path(__file__).resolve().parents[1]
TEMP = tempfile.TemporaryDirectory(prefix='structured-reply-')
os.environ['ASTRBOT_ROOT'] = TEMP.name
os.environ['DAFEIYU_RARE_VOICE'] = '1'
sys.path[:0] = [str(ROOT / '.runtime/AstrBot'), str(ROOT / 'deploy/telegram')]

from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.pipeline.structured_reply import JSON_REPLY_PROMPT
from astrbot.core.pipeline.chat_layout import group_bubbles
from astrbot.core.message.components import Plain, Record
from astrbot.core.message.message_event_result import MessageEventResult, ResultContentType
from structured_output import install

spec = importlib.util.spec_from_file_location('telegram_chat_smoke', ROOT / 'plugin/astrbot_plugin_telegram_chat/main.py')
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)


class Event:
    unified_msg_origin = 'telegram:FriendMessage:fixture'
    plugins_name = []
    def __init__(self):
        self.extras = {}
        self.result = None
        self.sent = []
    def set_extra(self, key, value): self.extras[key] = value
    def get_extra(self, key, default=None): return self.extras.get(key, default)
    def get_result(self): return self.result
    def get_group_id(self): return ''
    def get_platform_name(self): return 'telegram'
    def get_sender_name(self): return 'fixture'
    def get_sender_id(self): return 'fixture'
    def is_stopped(self): return False
    def clear_result(self): self.result = None
    def _outline_chain(self, chain): return 'fixture'
    async def send(self, result): self.sent.append(list(result.chain))


async def main():
    install()
    provider = ProviderOpenAIOfficial({
        'id': 'fixture', 'key': ['fixture-key'], 'model': 'deepseek-flash',
        'api_base': 'https://api.deepseek.com/v1', 'provider': 'openai',
        'custom_extra_body': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
    }, {})
    await provider.client.close()
    from openai import AsyncOpenAI
    requests = []
    replies = []

    def receive(request):
        body = json.loads(request.content)
        requests.append(body)
        content = replies.pop(0)
        message = {'role': 'assistant', 'content': content, 'reasoning_content': 'fixture reasoning'}
        if isinstance(content, dict):
            message = {'role': 'assistant', 'reasoning_content': 'fixture reasoning', **content}
        return httpx.Response(200, json={
            'id': 'fixture', 'object': 'chat.completion', 'created': 1, 'model': 'deepseek-flash',
            'choices': [{'index': 0, 'message': message, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        })

    provider.client = AsyncOpenAI(api_key='fixture-key', base_url='https://api.deepseek.com/v1',
                                 http_client=httpx.AsyncClient(transport=httpx.MockTransport(receive), trust_env=False))
    payload = {'model': 'deepseek-flash', 'messages': [{'role': 'system', 'content': JSON_REPLY_PROMPT},
                                                   {'role': 'user', 'content': 'fixture'}]}
    plan = {'v': 1, 'bubbles': [
        {'text': '第一句。第二句。[开心]', 'emotion': 'happy', 'ending': 'omit'},
        {'text': '无标点的独立气泡', 'emotion': 'neutral', 'ending': 'omit'},
        {'text': '不理你了', 'emotion': 'cold', 'ending': 'period'},
        {'text': '解释' * 100 + '。', 'emotion': 'serious', 'ending': 'omit'},
    ], 'voice': 'none'}
    replies.append(json.dumps(plan, ensure_ascii=False))
    response = await provider._query(payload, None)
    assert requests[-1]['response_format'] == {'type': 'json_object'}
    assert requests[-1]['thinking'] == {'type': 'enabled'}
    assert requests[-1]['reasoning_effort'] == 'high'
    assert response.reasoning_content == 'fixture reasoning'
    assert response.raw_completion.choices[0].message.content.startswith('{')
    assert not response.completion_text.startswith('{')

    instance = object.__new__(plugin.TelegramChatPlugin)
    instance.cfg = plugin.DEFAULT_CONFIG.copy()
    instance.face_map = {'开心': '😀'}
    instance.pattern = re.compile(r'\[([^\[\]]{1,8})\]')
    instance._face_history = {}
    event = Event()
    await instance.scrub_drafts(event, response)
    event.result = MessageEventResult()
    event.result.result_content_type = ResultContentType.LLM_RESULT
    event.result.chain = [Plain(response.completion_text)]
    await instance.convert_faces(event)
    bubbles = group_bubbles(event.result.chain, Plain, Record, 3)
    text = [''.join(c.text for c in bubble if isinstance(c, Plain)) for bubble in bubbles]
    assert len(text) == 4, text
    assert text[0] == '第一句。第二句。😀', text
    assert text[1] == '无标点的独立气泡'
    assert text[2] == '不理你了。'
    assert text[3] == '解释' * 100
    print('PASS actual SDK -> JSON decode -> hooks -> emoji -> four explicit bubbles including >150 chars')

    from astrbot.core.config.default import DEFAULT_CONFIG
    from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
    from astrbot.core.pipeline.respond.stage import RespondStage
    from astrbot.core.star.star_handler import star_handlers_registry
    config = copy.deepcopy(DEFAULT_CONFIG)
    config['provider_tts_settings']['enable'] = False
    config['t2i'] = False
    config['content_safety']['also_use_in_response'] = False
    config['platform_settings']['segmented_reply'].update(enable=True, only_llm_result=True,
                                                          words_count_threshold=150)
    config['platform_settings']['reply_with_mention'] = False
    config['platform_settings']['reply_with_quote'] = False
    ctx = NS(astrbot_config=config, plugin_manager=NS(context=NS(
        get_using_tts_provider_async=AsyncMock(return_value=None))))
    decorate = ResultDecorateStage()
    await decorate.initialize(ctx)
    respond = RespondStage()
    await respond.initialize(ctx)
    with patch.object(star_handlers_registry, 'get_handlers_by_event_type', return_value=[]), \
         patch('astrbot.core.pipeline.respond.stage.call_event_hook', new=AsyncMock(return_value=False)), \
         patch('astrbot.core.pipeline.respond.stage.asyncio.sleep', new=AsyncMock()):
        async for _ in decorate.process(event): pass
        await respond.process(event)
    sent = [''.join(c.text for c in chain if isinstance(c, Plain)) for chain in event.sent]
    assert sent == text, sent
    print('PASS real result-decorate/respond stages send exactly the planned bubbles without regex or 150-char override')

    replies.extend(['   ', json.dumps(plan)])
    before = len(requests)
    fixed = await provider._query(payload, None)
    assert len(requests) == before + 2 and fixed._dafeiyu_reply_plan['v'] == 1
    print('PASS whitespace response repairs once')
    replies.extend(['{}', '{}'])
    bad = await provider._query(payload, None)
    assert '格式没整理好' in bad.completion_text and '{' not in bad.completion_text
    print('PASS invalid schema falls back without exposing JSON')
    replies.append('ordinary helper response')
    untouched = await provider._query({'model': 'deepseek-flash', 'messages': [{'role': 'user', 'content': 'caption'}]}, None)
    assert untouched.completion_text == 'ordinary helper response'
    assert 'response_format' not in requests[-1]
    print('PASS unrelated caption/helper call stays plain text')

    replies.append({'content': None, 'tool_calls': [{'id': 'tool-fixture', 'type': 'function',
                    'function': {'name': 'fixture_tool', 'arguments': '{"x":1}'}}]})
    tools = NS(get_func_desc_openai_style=lambda **_: [{'type': 'function', 'function': {
        'name': 'fixture_tool', 'parameters': {'type': 'object', 'properties': {'x': {'type': 'integer'}}}}}])
    tool_result = await provider._query(payload, tools)
    assert tool_result.tools_call_name == ['fixture_tool']
    assert tool_result.tools_call_ids == ['tool-fixture']
    assert not tool_result.completion_text
    print('PASS native tool call name/ID/arguments preserved without displaying JSON')

    for voice, emotion, key in [('requested', 'neutral', '_fy_voice_requested'),
                                ('auto', 'excited', '_fy_voice_emotion')]:
        plan['voice'] = voice
        plan['bubbles'][0]['emotion'] = emotion
        replies.append(json.dumps(plan))
        result = await provider._query(payload, None)
        e = Event()
        await instance.scrub_drafts(e, result)
        assert e.get_extra(key)
        print('PASS structured voice routing:', voice)
    await provider.client.close()


if __name__ == '__main__':
    asyncio.run(main())
