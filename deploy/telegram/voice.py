"""Convert local TTS output to a Bot API voice format without retaining artifacts."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
import tempfile

@asynccontextmanager
async def compatible_voice(path):
    source=Path(path)
    if source.suffix.lower() in {'.ogg','.mp3','.m4a'}:
        yield str(source)
        return
    with tempfile.TemporaryDirectory(prefix='telegram-voice-') as folder:
        output=Path(folder)/'voice.ogg'
        process=await asyncio.create_subprocess_exec('ffmpeg','-hide_banner','-loglevel','error','-y',
            '-i',str(source),'-vn','-ac','1','-ar','48000','-c:a','libopus',str(output),
            stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.DEVNULL)
        try:
            await asyncio.wait_for(process.wait(),30)
        except BaseException:
            if process.returncode is None:process.kill()
            await process.wait()
            raise
        if process.returncode or not output.is_file() or output.stat().st_size==0:
            raise ValueError('Unable to encode Telegram voice')
        yield str(output)

def install_voice(event_class):
    if getattr(event_class,'_dafeiyu_voice',False):return
    original=event_class._send_voice_with_fallback
    async def send(client,path,payload,**kwargs):
        async with compatible_voice(path) as encoded:
            await original(client,encoded,payload,**kwargs)
    event_class._send_voice_with_fallback=staticmethod(send)
    event_class._dafeiyu_voice=True
