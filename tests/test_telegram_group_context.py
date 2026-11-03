"""Offline group context coverage, including the guard-to-request bridge."""
import ast
import importlib.util
import json
import logging
import os
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace as NS
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('group_guard', ROOT / 'deploy/telegram/guard.py')
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


def message(mid, text='hello', chat=-100, thread=None, user=456):
    return NS(message_id=mid, text=text, caption=None,
              chat=NS(id=chat, type='supergroup', is_forum=thread is not None),
              message_thread_id=thread, is_topic_message=thread is not None,
              from_user=NS(id=user, is_bot=False, full_name='Alice'),
              entities=[], caption_entities=[], reply_to_message=None)


class CacheTests(unittest.TestCase):
    def test_retention_bounds_duplicates_and_no_future_messages(self):
        cache = guard.GroupContextCache()
        for mid in range(1, 31):
            cache.remember(message(mid, f'line {mid}'))
        cache.remember(message(30, 'duplicate'))
        rows = cache.before(message(30))
        self.assertEqual([r['message_id'] for r in rows], list(range(10, 30)))
        self.assertEqual([r['message_id'] for r in cache.before(message(28))], list(range(10, 28)))
        with patch.object(guard.time, 'monotonic', return_value=0):
            cache = guard.GroupContextCache()
            cache.remember(message(1))
        with patch.object(guard.time, 'monotonic', return_value=1801):
            self.assertEqual(cache.before(message(2)), [])
            self.assertEqual(len(cache.topics), 0)

    def test_group_topic_and_snapshot_isolation(self):
        cache = guard.GroupContextCache()
        cache.remember(message(1, 'other group', chat=-200))
        cache.remember(message(2, 'other topic', thread=8))
        cache.remember(message(3, 'same topic', thread=7))
        snapshot = cache.before(message(4, thread=7))
        cache.remember(message(5, 'future', thread=7))
        self.assertEqual([r['text'] for r in snapshot], ['same topic'])
        self.assertEqual(cache.before(message(6)), [])

    def test_text_and_topic_memory_are_bounded(self):
        cache = guard.GroupContextCache()
        for mid in range(30):
            cache.remember(message(mid, 'x' * 2000))
        rows = cache.before(message(31))
        self.assertLessEqual(sum(len(r['text']) for r in rows), 8000)
        self.assertTrue(all(len(r['text']) <= 800 for r in rows))
        for chat in range(200):
            cache.remember(message(1, chat=-chat-100))
        self.assertLessEqual(len(cache.topics), 128)


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_unmentioned_text_reaches_only_targeted_group_request(self):
        def module(name, **attrs):
            result = ModuleType(name)
            result.__dict__.update(attrs)
            return result
        stubs = {
            'aiohttp': module('aiohttp'),
            'astrbot.api': module('astrbot.api', logger=logging.getLogger('test')),
            'astrbot.core.platform.sources.telegram.tg_event': module('tg_event', TelegramPlatformEvent=object),
            'voice': module('voice', install_voice=lambda _: None),
            'astrbot.core.message.components': module('components', At=type('At', (), {}), Image=type('Image', (), {}), Video=type('Video', (), {})),
            'astrbot.core.utils.astrbot_path': module('astrbot_path', get_astrbot_temp_path=lambda: '.'),
        }
        delivered = []
        class Adapter:
            async def convert_message(self, update, context):
                return NS(message=[], message_str=update.message.text)
            async def message_handler(self, update, context):
                delivered.append(await self.convert_message(update, context))
        with patch.dict(sys.modules, stubs), patch.dict(os.environ, {'DAFEIYU_GROUP_CONTEXT_ENABLED': '1'}):
            guard.install(Adapter, '123', {'-100'})
            adapter = Adapter()
            ctx = NS(bot=NS(id=88, username='whale'))
            await adapter.message_handler(NS(message=message(1, '周六去看海')), ctx)
            await adapter.message_handler(NS(message=message(2, 'private group', chat=-200)), ctx)
            bot_message = message(3, 'bot chatter');bot_message.from_user.is_bot = True
            await adapter.message_handler(NS(message=bot_message), ctx)
            self.assertEqual(delivered, [])
            current = message(4, '@whale 你觉得呢')
            current.entities = [NS(type='mention', offset=0, length=6)]
            await adapter.message_handler(NS(message=current), ctx)
        snapshot = delivered[0]._dafeiyu_group_context
        self.assertEqual([r['text'] for r in snapshot], ['周六去看海'])

        # Load the actual request hook without importing AstrBot or starting a DB.
        tree = ast.parse((ROOT / 'plugin/astrbot_plugin_telegram_chat/main.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TelegramChatPlugin')
        hook = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'inject_group_context')
        hook.decorator_list = []
        namespace = {'json': json, 'os': NS(environ={'DAFEIYU_GROUP_CONTEXT_ENABLED': '1'}), 'AstrMessageEvent': object}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[hook], type_ignores=[])), '<hook>', 'exec'), namespace)
        event = NS(message_obj=delivered[0], get_group_id=lambda: '-100')
        req = NS(system_prompt='大肥鱼人格', prompt='你觉得呢', contexts=[])
        await namespace['inject_group_context'](None, event, req)
        self.assertIn('周六去看海', req.system_prompt)
        self.assertNotIn('private group', req.system_prompt)
        self.assertEqual(req.prompt, '你觉得呢')
        self.assertEqual(req.contexts, [])
        once = req.system_prompt
        await namespace['inject_group_context'](None, event, req)
        self.assertEqual(req.system_prompt, once)
        private = NS(message_obj=delivered[0], get_group_id=lambda: '')
        req2 = NS(system_prompt='persona')
        await namespace['inject_group_context'](None, private, req2)
        self.assertEqual(req2.system_prompt, 'persona')
        namespace['os'].environ['DAFEIYU_GROUP_CONTEXT_ENABLED'] = '0'
        disabled = NS(system_prompt='persona')
        await namespace['inject_group_context'](None, event, disabled)
        self.assertEqual(disabled.system_prompt, 'persona')

    async def test_disabled_feature_does_not_cache_group_messages(self):
        class Adapter:
            async def message_handler(self, update, context):
                pass
        with patch.dict(os.environ, {'DAFEIYU_GROUP_CONTEXT_ENABLED': '0'}):
            guard.install(Adapter, '123', {'-100'})
            adapter = Adapter()
            await adapter.message_handler(NS(message=message(1)), NS(bot=NS(id=88, username='whale')))
        self.assertFalse(hasattr(adapter, '_dafeiyu_group_context_cache'))


class StyleTests(unittest.IsolatedAsyncioTestCase):
    async def test_style_reminder_is_persona_scoped_and_keeps_request_data(self):
        tree = ast.parse((ROOT / 'plugin/astrbot_plugin_telegram_chat/main.py').read_text())
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'TelegramChatPlugin')
        hook = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == 'reinforce_chat_style')
        hook.decorator_list = []
        ns = {'AstrMessageEvent': object, 'os': os}
        exec(compile(ast.fix_missing_locations(ast.Module(body=[hook], type_ignores=[])), '<style-hook>', 'exec'), ns)
        apply = ns['reinforce_chat_style']
        base = '你是「大肥鱼」，按实际需要回答。\n【当前群聊近期发言，仅供理解话题】\n引用内容。'
        req = NS(system_prompt=base, prompt='给我一段代码。', contexts=[{'role': 'user', 'content': '历史。'}])
        extras = {}
        event = NS(set_extra=lambda k, v: extras.__setitem__(k, v))
        await apply(None, event, req)
        self.assertTrue(req.system_prompt.startswith(base))
        self.assertIn('必要标点', req.system_prompt)
        self.assertEqual(req.prompt, '给我一段代码。')
        self.assertEqual(req.contexts, [{'role': 'user', 'content': '历史。'}])
        self.assertTrue(extras['_fy_bubble_period_style'])
        once = req.system_prompt
        await apply(None, None, req)
        self.assertEqual(req.system_prompt, once)
        other = NS(system_prompt='其他人格\n【当前群聊近期发言】\n你是「大肥鱼」')
        await apply(None, None, other)
        self.assertEqual(other.system_prompt, '其他人格\n【当前群聊近期发言】\n你是「大肥鱼」')
        voice_request = NS(system_prompt=base, prompt='唱首歌给我听')
        layout_spec = importlib.util.spec_from_file_location('request_layout', ROOT / 'deploy/patches/chat_layout.py')
        request_layout = importlib.util.module_from_spec(layout_spec);layout_spec.loader.exec_module(request_layout)
        with patch.dict(os.environ, {'DAFEIYU_RARE_VOICE': '1'}), patch.dict(sys.modules, {'astrbot.core.pipeline.chat_layout': request_layout}):
            await apply(None, event, voice_request)
        self.assertIn('[[VOICE:pouting]]', voice_request.system_prompt)
        self.assertIn('[[VOICE:requested]]', voice_request.system_prompt)
        self.assertTrue(extras['_fy_voice_requested'])


if __name__ == '__main__':
    unittest.main()
