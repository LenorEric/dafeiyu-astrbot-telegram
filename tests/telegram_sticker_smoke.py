"""Real PTB/AstrBot regression, fake Bot API and local sticker download.

Run: .venv/bin/python tests/telegram_sticker_smoke.py
Never contacts Telegram or a paid model.
"""
import asyncio
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / '.runtime/AstrBot'), str(ROOT / 'deploy/telegram')]
TEMP = tempfile.TemporaryDirectory(prefix='telegram-sticker-regression-')
os.environ['ASTRBOT_ROOT'] = TEMP.name

from telegram import Update
from telegram.ext import ExtBot
from telegram.request import BaseRequest
from astrbot.core.message.components import At, Image, Reply
from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter
from astrbot.core.pipeline.waking_check.stage import WakingCheckStage
from astrbot.core.star.session_plugin_manager import SessionPluginManager
from guard import install


class Request(BaseRequest):
    @property
    def read_timeout(self):return 5
    async def initialize(self):pass
    async def shutdown(self):pass
    async def do_request(self, url, method, request_data=None, **kwargs):
        action = url.rsplit('/', 1)[-1]
        if action == 'getMe':
            result = {'id': 88, 'is_bot': True, 'first_name': 'Whale', 'username': 'whale'}
        elif action == 'getFile':
            result = {'file_id': 'sticker', 'file_unique_id': 'unique', 'file_path': 'stickers/test.webp'}
        else:
            raise AssertionError('Unexpected Bot API action: '+action)
        return 200, json.dumps({'ok': True, 'result': result}).encode()


class Download:
    async def __aenter__(self):return self
    async def __aexit__(self, *args):pass
    def raise_for_status(self):pass
    @property
    def content(self):return self
    async def iter_chunked(self, size):yield b'local-sticker-fixture'


class Session:
    def __init__(self, **kwargs):pass
    async def __aenter__(self):return self
    async def __aexit__(self, *args):pass
    def get(self, url):return Download()


def sticker():
    return {'file_id': 'sticker', 'file_unique_id': 'unique', 'width': 64, 'height': 64,
            'is_animated': False, 'is_video': False, 'type': 'regular', 'emoji': '😬'}


async def main():
    bot = ExtBot('88:offline-fixture', request=Request(), get_updates_request=Request())
    await bot.initialize()
    adapter = TelegramPlatformAdapter({'id': 'telegram', 'type': 'telegram', 'telegram_token': '88:offline-fixture'}, {}, asyncio.Queue())
    adapter.client = bot
    install(TelegramPlatformAdapter, '123', {'-100'})
    events = []
    async def receive(message):events.append(adapter.create_event(message))
    adapter.handle_msg = receive
    context = NS(bot=bot)
    wake = object.__new__(WakingCheckStage)
    wake.ctx = NS(astrbot_config={'admins_id': ['123'], 'wake_prefix': ['/']})
    wake.unique_session = False;wake.ignore_bot_self_message = False
    wake.ignore_at_all = False;wake.friend_message_needs_wake_prefix = False
    wake.disable_builtin_commands = False
    wake._umo_auto_name_recorder = NS(schedule=lambda _: None)
    def update(chat=-100, reply_to_bot=True, mention=False, quoted_sticker=False):
        m = {'message_id': 10, 'date': 1,
             'chat': {'id': chat, 'type': 'private' if chat > 0 else 'supergroup'},
             'from': {'id': 123, 'is_bot': False, 'first_name': 'Owner'}}
        if quoted_sticker:
            m.update(text='@whale 看看这个', entities=[{'type': 'mention', 'offset': 0, 'length': 6}])
            m['reply_to_message'] = {'message_id': 2, 'date': 1, 'chat': m['chat'],
                                     'from': {'id': 456, 'is_bot': False, 'first_name': 'Friend'}, 'sticker': sticker()}
        else:
            m['sticker'] = sticker()
            if chat < 0:
                m['reply_to_message'] = {'message_id': 2, 'date': 1, 'chat': m['chat'],
                                         'from': {'id': 88 if reply_to_bot else 456, 'is_bot': reply_to_bot, 'first_name': 'Whale'}, 'text': 'hello'}
        return Update.de_json({'update_id': 1, 'message': m}, bot)
    with patch('aiohttp.ClientSession', Session), patch.object(SessionPluginManager, 'filter_handlers_by_session', AsyncMock(return_value=[])):
        await adapter.message_handler(update(), context)
        event = events[-1]
        quote = next(c for c in event.get_messages() if isinstance(c, Reply))
        assert str(quote.sender_id) == '88'  # Original numeric identity is preserved.
        assert any(isinstance(c, Image) and Path(c.file).is_file() for c in event.get_messages())
        assert any(isinstance(c, At) and c.qq == 'whale' for c in event.get_messages())
        # Reproduce the old mismatch with the same converted image and quote.
        before = adapter.create_event(event.message_obj)
        before.message_obj = __import__('copy').copy(event.message_obj)
        before.message_obj.message = [c for c in event.get_messages() if not isinstance(c, At)]
        await wake.process(before)
        assert not before.is_at_or_wake_command
        await wake.process(event)
        assert event.is_at_or_wake_command and not event.is_stopped()
        print('PASS: reproduced old group sticker reply wake failure; fixed event wakes with local image intact.')
        count = len(events)
        await adapter.message_handler(update(chat=-999), context)
        await adapter.message_handler(update(reply_to_bot=False), context)
        assert len(events) == count
        print('PASS: unlisted group and reply to another user still rejected.')
        await adapter.message_handler(update(chat=123), context)
        assert any(isinstance(c, Image) for c in events[-1].get_messages())
        print('PASS: private sticker handling preserved.')
        await adapter.message_handler(update(quoted_sticker=True), context)
        quoted = next(c for c in events[-1].get_messages() if isinstance(c, Reply))
        assert any(isinstance(c, Image) and Path(c.file).is_file() for c in quoted.chain)
        print('PASS: @ plus reply quoting another user\'s sticker keeps the quoted image.')
    await bot.shutdown()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    finally:
        TEMP.cleanup()
