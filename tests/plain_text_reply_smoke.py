"""Real SDK/plain-text pipeline regression with local HTTP and message fixtures."""
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
TEMP = tempfile.TemporaryDirectory(prefix='plain-text-reply-')
os.environ['ASTRBOT_ROOT'] = TEMP.name
os.environ['DAFEIYU_RARE_VOICE'] = '1'
sys.path[:0] = [str(ROOT / '.runtime/AstrBot'), str(ROOT / 'deploy/telegram')]

from astrbot.core.config.default import DEFAULT_CONFIG
from astrbot.core.message.components import Plain
from astrbot.core.message.message_event_result import MessageEventResult, ResultContentType
from astrbot.core.pipeline.result_decorate.stage import ResultDecorateStage
from astrbot.core.pipeline.respond.stage import RespondStage
from astrbot.core.provider.sources.openai_source import ProviderOpenAIOfficial
from astrbot.core.star.star_handler import star_handlers_registry
from api_log import install as install_api_log, decode_record

spec = importlib.util.spec_from_file_location('telegram_chat_plain_smoke', ROOT / 'plugin/astrbot_plugin_telegram_chat/main.py')
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
    log_path = Path(TEMP.name) / 'logs/model-api.jsonl'
    install_api_log(log_path)
    assert not getattr(ProviderOpenAIOfficial._query, '_dafeiyu_json', False)
    provider = ProviderOpenAIOfficial({
        'id': 'fixture', 'key': ['fixture-key'], 'model': 'deepseek-flash',
        'api_base': 'https://api.deepseek.com/v1', 'provider': 'openai',
        'custom_extra_body': {'thinking': {'type': 'enabled'}, 'reasoning_effort': 'high'},
    }, {})
    await provider.client.close()
    from openai import AsyncOpenAI
    requests = []
    replies = ['我来啦[开心]。先坐会儿。哼，不理你了。[[KEEP_PERIOD]]',
               '你终于来啦！[[VOICE:excited]]']
    raw_text = replies[0]

    def receive(request):
        body = json.loads(request.content)
        assert 'response_format' not in body
        assert body['thinking'] == {'type': 'enabled'} and body['reasoning_effort'] == 'high'
        assert not any('【大肥鱼 JSON 气泡协议' in str(m.get('content', '')) for m in body['messages'])
        requests.append(body)
        return httpx.Response(200, json={
            'id': 'fixture-' + str(len(requests)), 'object': 'chat.completion',
            'created': 1, 'model': 'deepseek-flash',
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': replies.pop(0),
                         'reasoning_content': 'fixture reasoning'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 5, 'total_tokens': 15},
        })

    provider.client = AsyncOpenAI(api_key='fixture-key', base_url='https://api.deepseek.com/v1',
                                 http_client=httpx.AsyncClient(transport=httpx.MockTransport(receive), trust_env=False))
    instance = object.__new__(plugin.TelegramChatPlugin)
    instance.cfg = plugin.DEFAULT_CONFIG.copy()
    instance.face_map = {'开心': '😀'}
    instance.pattern = re.compile(r'\[([^\[\]]{1,8})\]')
    instance._face_history = {}
    persona = (ROOT / 'persona/大肥鱼-人格.md').read_text().split('\n---\n', 1)[1].strip()
    assert 'json' not in persona.lower()
    event = Event()
    req = NS(system_prompt=persona, prompt='你好')
    await instance.reinforce_chat_style(event, req)
    assert 'json' not in req.system_prompt.lower()
    result = await provider.text_chat(prompt=req.prompt, system_prompt=req.system_prompt, request_max_retries=1)
    assert result.completion_text == raw_text and result.reasoning_content == 'fixture reasoning'
    assert not hasattr(result, '_dafeiyu_reply_plan')
    await instance.scrub_drafts(event, result)
    event.result = MessageEventResult()
    event.result.result_content_type = ResultContentType.LLM_RESULT
    event.result.chain = [Plain(result.completion_text)]
    await instance.convert_faces(event)
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
    decorate, respond = ResultDecorateStage(), RespondStage()
    await decorate.initialize(ctx)
    await respond.initialize(ctx)
    with patch.object(star_handlers_registry, 'get_handlers_by_event_type', return_value=[]), \
         patch('astrbot.core.pipeline.respond.stage.call_event_hook', new=AsyncMock(return_value=False)), \
         patch('astrbot.core.pipeline.respond.stage.asyncio.sleep', new=AsyncMock()):
        async for _ in decorate.process(event): pass
        await respond.process(event)
    sent = [''.join(c.text for c in chain if isinstance(c, Plain)) for chain in event.sent]
    assert sent == ['我来啦😀', '先坐会儿', '哼，不理你了。'], sent
    print('PASS no JSON prompt/response_format/adapter; plain text -> emoji -> sentence bubbles -> closing periods')

    e = Event()
    await instance.reinforce_chat_style(e, NS(system_prompt=persona, prompt='你好'))
    voice = await provider.text_chat(prompt='你好', system_prompt=req.system_prompt, request_max_retries=1)
    await instance.scrub_drafts(e, voice)
    assert e.get_extra('_fy_voice_emotion') == 'excited' and '[[VOICE' not in voice.completion_text
    requested = Event()
    await instance.reinforce_chat_style(requested, NS(system_prompt=persona, prompt='发一条语音'))
    assert requested.get_extra('_fy_voice_requested') is True
    print('PASS automatic and requested voice routing restored through plain-text markers')
    records = [decode_record(json.loads(line)) for line in log_path.read_bytes().splitlines()]
    assert len(records) == 2
    first = json.loads(records[0]['response']['body'])
    assert first['choices'][0]['message']['content'] == raw_text
    assert first['usage']['total_tokens'] == 15
    assert all('fixture-key' not in json.dumps(record) for record in records)
    print('PASS complete raw HTTP logs and thinking high preserved')
    await provider.client.close()


if __name__ == '__main__':
    asyncio.run(main())
