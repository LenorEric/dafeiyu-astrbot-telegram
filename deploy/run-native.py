"""Run AstrBot with the existing local configuration."""
import os
import runpy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / '.runtime/AstrBot'


def main():
    os.umask(0o077)
    env_file = ROOT / 'deploy/.env'
    if env_file.stat().st_mode & 0o077:
        raise SystemExit('请先执行 chmod 600 deploy/.env')
    for line in env_file.read_text().splitlines():
        if line and not line.startswith('#'):
            name, value = line.split('=', 1)
            os.environ[name] = value
    if not (CORE / 'main.py').exists():
        raise SystemExit('AstrBot 尚未安装；请运行 bash deploy/start-local.sh')
    from native_audio import configure_ffmpeg
    print('Native audio ffmpeg ready:', configure_ffmpeg(ROOT / '.venv/bin'), flush=True)
    os.environ.update({
        'ASTRBOT_ROOT': str(ROOT / 'deploy'),
        'DAFEIYU_DATA_DIR': str(ROOT / 'deploy/data'),
        'DAFEIYU_PLUGIN_SOURCE': str(ROOT / 'plugin'),
        'DAFEIYU_ASTRBOT_SOURCE': str(CORE),
        'DAFEIYU_TELEGRAM_GUARD': '1',
        'TZ': 'Asia/Shanghai',
    })
    import time
    if hasattr(time, 'tzset'):
        time.tzset()
    sys.path[:0] = [str(CORE), str(ROOT / 'deploy/telegram')]
    os.chdir(CORE)
    import runtime_bootstrap
    runtime_bootstrap.initialize_runtime_bootstrap()
    runpy.run_path(str(ROOT / 'deploy/telegram/run.py'), run_name='__main__')


if __name__ == '__main__':
    main()
