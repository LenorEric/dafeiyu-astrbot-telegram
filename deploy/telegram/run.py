"""Fail closed if Telegram access protection cannot initialize."""
import os, runpy
from init import initialize
from pathlib import Path
initialize(Path(os.environ.get('DAFEIYU_DATA_DIR','/AstrBot/data')),Path(os.environ.get('DAFEIYU_PLUGIN_SOURCE','/opt/dafeiyu/plugin')))
from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter
if os.environ.get('BREEZE_API_KEY'):
    import breeze_tts  # register before provider manager startup
from guard import install
install(TelegramPlatformAdapter,os.environ['TELEGRAM_OWNER_ID'],set(filter(None,os.environ.get('TELEGRAM_ALLOWED_GROUPS','').split(','))))
runpy.run_path(str(Path(os.environ.get('DAFEIYU_ASTRBOT_SOURCE','/AstrBot'))/'main.py'),run_name='__main__')
