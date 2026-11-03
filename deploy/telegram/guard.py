"""Pinned adapter overlay: authorize before conversion, download or /start."""
import logging
import os
import re
import time
from collections import OrderedDict, deque
from datetime import datetime


class GroupContextCache:
    """Bounded, in-memory text context; never mixes chats or forum topics."""
    MAX_MESSAGES = 20
    MAX_AGE = 30 * 60
    MAX_TOPICS = 128
    MAX_TEXT = 800
    MAX_TOTAL_TEXT = 8000

    def __init__(self):
        self.topics = OrderedDict()

    @staticmethod
    def key(message):
        thread = getattr(message, 'message_thread_id', None) if getattr(message, 'is_topic_message', False) else None
        if getattr(message.chat, 'is_forum', False) is True and thread == 1:
            thread = None
        return (message.chat.id, thread)

    def prune(self):
        cutoff = time.monotonic() - self.MAX_AGE
        for key, items in list(self.topics.items()):
            while items and items[0][0] <= cutoff:
                items.popleft()
            if not items:
                del self.topics[key]

    def remember(self, message):
        self.prune()
        text = (message.text or message.caption or '').strip()
        if not text:
            return False
        sent_at = getattr(message, 'date', None)
        if isinstance(sent_at, datetime) and time.time() - sent_at.timestamp() > self.MAX_AGE:
            return False
        key = self.key(message)
        # One extra slot retains 20 prior messages when the current one is cached.
        items = self.topics.setdefault(key, deque(maxlen=self.MAX_MESSAGES + 1))
        message_id = getattr(message, 'message_id', None)
        if message_id is not None and any(item[1]['message_id'] == message_id for item in items):
            return False
        items.append((time.monotonic(), {
            'message_id': message_id,
            'sender_id': str(message.from_user.id),
            'sender_name': str(getattr(message.from_user, 'full_name', None) or getattr(message.from_user, 'username', None) or message.from_user.id)[:64],
            'sent_at': sent_at.isoformat() if isinstance(sent_at, datetime) else None,
            'text': text[:self.MAX_TEXT],
        }))
        self.topics.move_to_end(key)
        while len(self.topics) > self.MAX_TOPICS:
            self.topics.popitem(last=False)
        return True

    def before(self, message):
        self.prune()
        current_id = getattr(message, 'message_id', None)
        result = []
        size = 0
        for _, item in reversed(self.topics.get(self.key(message), ())):
            if current_id is not None and item['message_id'] is not None and item['message_id'] >= current_id:
                continue
            if size + len(item['text']) > self.MAX_TOTAL_TEXT:
                break
            result.append(dict(item))
            size += len(item['text'])
            if len(result) >= self.MAX_MESSAGES:
                break
        return list(reversed(result))


def group_cache(adapter):
    cache = getattr(adapter, '_dafeiyu_group_context_cache', None)
    if cache is None:
        cache = adapter._dafeiyu_group_context_cache = GroupContextCache()
    return cache

def install(adapter_class, owner_id, allowed_groups):
    group_context_enabled = os.environ.get('DAFEIYU_GROUP_CONTEXT_ENABLED', '0') == '1'
    context_debug = os.environ.get('DAFEIYU_GROUP_CONTEXT_DEBUG', '0') == '1'
    try:
        from astrbot.api import logger
    except ImportError:
        logger = logging.getLogger(__name__)
    logger.info(f'Telegram group guard: allowed_groups={sorted(allowed_groups)}, context_enabled={group_context_enabled}, context_debug={context_debug}')
    # Redact after formatting, including exception tracebacks and child loggers.
    if not getattr(logging.Formatter, '_dafeiyu_redaction', False):
        original_format = logging.Formatter.format
        def safe_format(self, record):
            text = re.sub(r'(?:file/)?bot\d+:[A-Za-z0-9_-]+', 'bot<redacted>', original_format(self, record))
            token = os.environ.get('TELEGRAM_BOT_TOKEN')
            return text.replace(token, '<redacted>') if token else text
        logging.Formatter.format = safe_format
        logging.Formatter._dafeiyu_redaction = True
    original_convert = getattr(adapter_class, 'convert_message', None)
    if original_convert:
        from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
        from voice import install_voice
        install_voice(TelegramPlatformEvent)
        async def convert(self, update, context, *args, **kwargs):
            raw = update.message
            recent = group_cache(self).before(raw) if group_context_enabled and raw and str(raw.chat.id) in allowed_groups else []
            if context_debug and raw and str(raw.chat.id) in allowed_groups:
                logger.info(f'Telegram group context snapshot: chat_id={raw.chat.id}, message_id={getattr(raw, "message_id", None)}, messages={len(recent)}')
            message = await original_convert(self, update, context, *args, **kwargs)
            if message is None: return None
            if recent:
                message._dafeiyu_group_context = recent
            from astrbot.core.message.components import At, Image, Video
            reply = getattr(raw, 'reply_to_message', None) if raw else None
            if (raw and raw.chat.type != 'private' and reply
                    and reply.from_user and reply.from_user.id == context.bot.id):
                # Telegram self_id is the bot username, while Reply.sender_id
                # is numeric. Text replies have a prefix workaround upstream;
                # stickers/audio/photos do not. Keep the numeric quote identity
                # and add the matching wake component for every reply type.
                if not any(isinstance(c, At) and str(c.qq) == str(message.self_id)
                           for c in message.message):
                    message.message.insert(0, At(qq=message.self_id, name=context.bot.username))
            from astrbot.core.utils.astrbot_path import get_astrbot_temp_path
            from pathlib import Path
            import uuid, aiohttp
            for component in message.message:
                if not isinstance(component, (Image, Video)): continue
                url = getattr(component, 'url', None) or getattr(component, 'file', None)
                if not isinstance(url, str) or not url.startswith(('http://','https://')): continue
                path = Path(get_astrbot_temp_path()) / (uuid.uuid4().hex + ('.mp4' if isinstance(component, Video) else '.img'))
                try:
                    async with aiohttp.ClientSession(trust_env=True, timeout=aiohttp.ClientTimeout(total=60)) as session:
                        async with session.get(url) as response:
                            response.raise_for_status()
                            size=0
                            with path.open('wb') as output:
                                async for chunk in response.content.iter_chunked(65536):
                                    size += len(chunk)
                                    if size > 20*1024*1024: raise ValueError('media limit')
                                    output.write(chunk)
                    component.file = str(path)
                    if hasattr(component, 'url'): component.url = None
                    if hasattr(component, 'path'): component.path = str(path)
                except BaseException:
                    path.unlink(missing_ok=True)
                    raise
            return message
        adapter_class.convert_message = convert
    original_commands = getattr(adapter_class, "collect_commands", lambda self: [])
    def commands(self):
        return [c for c in original_commands(self) if re.fullmatch(r'[a-z0-9_]{1,32}', c.command)][:100]
    adapter_class.collect_commands = commands
    original = adapter_class.message_handler
    async def guarded(self, update, context):
        m = update.message
        if not m or not m.from_user:
            return
        if m.from_user.is_bot:
            if str(m.chat.id) in allowed_groups:
                sender_chat = getattr(m, 'sender_chat', None)
                logger.info(f'Telegram group guard rejected bot sender: chat_id={m.chat.id}, sender_chat_id={getattr(sender_chat, "id", None)}')
            return
        if m.chat.type == 'private':
            if str(m.chat.id) != owner_id or str(m.from_user.id) != owner_id: return
        else:
            if str(m.chat.id) not in allowed_groups:
                logger.info(f'Telegram group guard rejected unlisted chat: chat_id={m.chat.id}')
                return
            text = m.text or m.caption or ''
            name = context.bot.username.lower()
            reply = m.reply_to_message
            targeted = bool(reply and reply.from_user and reply.from_user.id == context.bot.id)
            entities = m.entities or m.caption_entities or []
            for entity in entities:
                value = text.encode('utf-16-le')[entity.offset*2:(entity.offset+entity.length)*2].decode('utf-16-le')
                if entity.type == 'mention' and value.lower() == '@'+name: targeted = True
                if entity.type == 'bot_command' and value.lower().endswith('@'+name): targeted = True
            albums = getattr(self, '_dafeiyu_albums', {})
            now = time.monotonic()
            albums = {k:v for k,v in albums.items() if v > now}
            album = getattr(m, 'media_group_id', None)
            key = (m.chat.id, album)
            if album and targeted:
                if len(albums) >= 1000: albums.clear()
                albums[key] = now + 20
            if group_context_enabled:
                cache = group_cache(self)
                recorded = cache.remember(m)
                if context_debug:
                    logger.info(f'Telegram group context receive: chat_id={m.chat.id}, topic={cache.key(m)[1]}, message_id={getattr(m, "message_id", None)}, targeted={targeted}, cached={recorded}, cache_messages={len(cache.topics.get(cache.key(m), ()))}')
            if not targeted and not (album and key in albums):
                logger.debug(f'Telegram group message cached without waking bot: chat_id={m.chat.id}')
                return
            logger.info(f'Telegram group guard accepted targeted message: chat_id={m.chat.id}, message_id={getattr(m, "message_id", None)}')
            self._dafeiyu_albums = albums
        for field in ('voice','audio','video','video_note','document','animation','sticker'):
            media = getattr(m, field, None)
            if media and getattr(media, 'file_size', 0) and media.file_size > 20*1024*1024:
                await m.reply_text('文件超过 20 MiB 下载上限，请压缩后重发。')
                return
        # Telegram animation is an MP4/GIF video, not a still image.
        if getattr(m, 'animation', None):
            from telegram import Update
            value = update.to_dict()
            value['message']['video'] = value['message'].pop('animation')
            update = Update.de_json(value, context.bot)
        await original(self, update, context)
    adapter_class.message_handler = guarded
    class Redact(logging.Filter):
        def filter(self, record):
            record.msg = re.sub(r'(?:file/)?bot\d+:[A-Za-z0-9_-]+', 'bot<redacted>', record.getMessage())
            record.args = ()
            return True
    # Library HTTP request logs contain token-bearing paths.
    for name in ('httpx','httpcore','telegram','astrbot'):
        logging.getLogger(name).addFilter(Redact())
    logging.getLogger('httpx').setLevel(logging.WARNING)
    logging.getLogger('httpcore').setLevel(logging.WARNING)
