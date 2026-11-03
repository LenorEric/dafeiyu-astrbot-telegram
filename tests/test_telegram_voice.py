import importlib.util, shutil, tempfile, unittest, wave
from pathlib import Path
P=Path(__file__).resolve().parents[1]/'deploy/telegram/voice.py'
spec=importlib.util.spec_from_file_location('telegram_voice',P);voice=importlib.util.module_from_spec(spec);spec.loader.exec_module(voice)
@unittest.skipUnless(shutil.which('ffmpeg'),'FFmpeg required')
class VoiceTests(unittest.IsolatedAsyncioTestCase):
 async def test_wav_to_opus_and_cleanup(self):
  with tempfile.TemporaryDirectory() as folder:
   source=Path(folder)/'speech.wav'
   with wave.open(str(source),'wb') as wav:
    wav.setparams((1,2,16000,0,'NONE','not compressed'));wav.writeframes(b'\0\0'*16000)
   async with voice.compatible_voice(source) as encoded:
    target=Path(encoded);self.assertEqual(target.read_bytes()[:4],b'OggS');self.assertNotEqual(target,source)
   self.assertFalse(target.exists());self.assertTrue(source.exists())
 async def test_invalid_audio_is_rejected(self):
  with tempfile.TemporaryDirectory() as folder:
   source=Path(folder)/'bad.wav';source.write_text('not audio')
   with self.assertRaises(ValueError):
    async with voice.compatible_voice(source):self.fail('invalid audio accepted')
if __name__=='__main__':unittest.main()
