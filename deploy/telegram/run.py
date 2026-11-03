"""Fail closed if Telegram access protection cannot initialize."""
import os, runpy
from init import initialize
from pathlib import Path
initialize(Path('/AstrBot/data'),Path(os.environ.get('DAFEIYU_PLUGIN_SOURCE','/opt/dafeiyu/plugin')))
from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter
from guard import install
install(TelegramPlatformAdapter,os.environ['TELEGRAM_OWNER_ID'],set(filter(None,os.environ.get('TELEGRAM_ALLOWED_GROUPS','').split(','))))
runpy.run_path('/AstrBot/main.py',run_name='__main__')
