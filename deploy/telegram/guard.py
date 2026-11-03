"""Pinned adapter overlay: authorize before conversion, download or /start."""
import logging
import os
import re
import time

def install(adapter_class, owner_id, allowed_groups):
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
            message = await original_convert(self, update, context, *args, **kwargs)
            if message is None: return None
            from astrbot.core.message.components import Image, Video
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
        if not m or not m.from_user or m.from_user.is_bot:
            return
        if m.chat.type == 'private':
            if str(m.chat.id) != owner_id or str(m.from_user.id) != owner_id: return
        else:
            if str(m.chat.id) not in allowed_groups: return
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
            if not targeted and not (album and key in albums): return
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
