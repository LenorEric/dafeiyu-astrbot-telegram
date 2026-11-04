"""Install AstrBot inside this project, without Docker."""
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import venv
import zipfile
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.runtime'
CORE = RUNTIME / 'AstrBot'
PYTHON = ROOT / '.venv/bin/python'


def main():
    if sys.version_info < (3, 12):
        raise SystemExit('需要 Python 3.12 或更新版本。')
    RUNTIME.mkdir(exist_ok=True)
    if not (CORE / 'main.py').exists():
        print('下载 AstrBot v4.29.0 源码……', flush=True)
        with tempfile.TemporaryDirectory(dir=RUNTIME) as folder:
            archive = Path(folder) / 'source.zip'
            try:
                with urllib.request.urlopen(
                    'https://codeload.github.com/AstrBotDevs/AstrBot/zip/refs/tags/v4.29.0',
                    timeout=60,
                ) as response, archive.open('wb') as output:
                    shutil.copyfileobj(response, output)
            except (OSError, urllib.error.URLError) as error:
                raise SystemExit(f'无法下载 AstrBot：{error}。请在网络可用的终端重新运行本脚本。') from None
            destination = Path(folder) / 'source'
            with zipfile.ZipFile(archive) as bundle:
                for item in bundle.infolist():
                    path = (destination / item.filename).resolve()
                    if not path.is_relative_to(destination.resolve()):
                        raise SystemExit('源码压缩包包含非法路径。')
                bundle.extractall(destination)
            source = destination / 'AstrBot-4.29.0'
            if not (source / 'main.py').is_file():
                raise SystemExit('下载的源码结构不符合预期。')
            if CORE.exists():
                raise SystemExit('存在不完整的 .runtime/AstrBot，请检查后再继续。')
            shutil.move(str(source), CORE)
    if not PYTHON.exists():
        venv.create(ROOT / '.venv', with_pip=True)
    marker = RUNTIME / 'dependencies-v4.29.0.ready'
    if not marker.exists():
        subprocess.run([
            str(PYTHON), '-m', 'pip', 'install', '-r', str(CORE / 'requirements.txt'),
            '-r', str(ROOT / 'deploy/bili_activity/requirements.txt'),
            '-r', str(ROOT / 'plugin/astrbot_plugin_bili_activity/requirements.txt'),
            'edge-tts', 'imageio-ffmpeg',
        ], check=True)
        marker.touch()
    audio_requirements = ROOT / 'deploy/requirements-native.txt'
    digest = hashlib.sha256(audio_requirements.read_bytes()).hexdigest()
    audio_marker = RUNTIME / 'native-audio-requirements.sha256'
    if not audio_marker.exists() or audio_marker.read_text() != digest:
        subprocess.run([str(PYTHON), '-m', 'pip', '--disable-pip-version-check',
                        'install', '-r', str(audio_requirements)], check=True)
        audio_marker.write_text(digest)
    subprocess.run([str(PYTHON), str(ROOT / 'deploy/native_audio.py')], check=True)
    for name, target in {
        'chat_layout.py': 'astrbot/core/pipeline/chat_layout.py',
        'structured_reply.py': 'astrbot/core/pipeline/structured_reply.py',
        'stage.py': 'astrbot/core/pipeline/result_decorate/stage.py',
        'respond_stage.py': 'astrbot/core/pipeline/respond/stage.py',
        'dashscope_tts.py': 'astrbot/core/provider/sources/dashscope_tts.py',
    }.items():
        shutil.copy2(ROOT / 'deploy/patches' / name, CORE / target)


if __name__ == '__main__':
    main()
