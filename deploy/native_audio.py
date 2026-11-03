"""Expose bundled ffmpeg to AstrBot and subprocesses without system packages."""
import os
import shutil
from pathlib import Path


def configure_ffmpeg(bin_dir=None):
    bin_dir = Path(bin_dir or Path(__file__).resolve().parents[1] / '.venv/bin')
    bin_dir.mkdir(parents=True, exist_ok=True)
    command = bin_dir / 'ffmpeg'
    if not command.exists():
        import imageio_ffmpeg
        executable = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
        if not executable.is_file() or not os.access(executable, os.X_OK):
            raise RuntimeError('Bundled ffmpeg is unavailable; install deploy/requirements-native.txt')
        # Replace a stale symlink left by a virtualenv/package upgrade.
        if command.is_symlink():
            command.unlink()
        command.symlink_to(executable)
    os.environ['PATH'] = str(bin_dir) + os.pathsep + os.environ.get('PATH', '')
    if not shutil.which('ffmpeg'):
        raise RuntimeError('ffmpeg is not executable')
    return str(command)


if __name__ == '__main__':
    print('Native audio ffmpeg ready:', configure_ffmpeg())
