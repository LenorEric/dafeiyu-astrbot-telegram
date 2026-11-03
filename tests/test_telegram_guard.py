"""Access and bootstrap tests require no network or account credentials."""
import asyncio, importlib.util, os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, patch
ROOT=Path(__file__).resolve().parents[1]
def load(name):
 s=importlib.util.spec_from_file_location(name,ROOT/'deploy/telegram'/f'{name}.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
class GuardTests(unittest.IsolatedAsyncioTestCase):
 async def asyncSetUp(self):
  self.calls=[]
  calls=self.calls
  class Adapter:
   async def message_handler(self,u,c): calls.append(u)
  load('guard').install(Adapter,'123',{'-100'})
  self.adapter=Adapter();self.ctx=NS(bot=NS(id=88,username='whale'))
 def update(self, chat=123, user=123, kind='private', text='hello', entities=None,reply=None,size=0):
  return NS(message=NS(chat=NS(id=chat,type=kind),from_user=NS(id=user,is_bot=False),text=text,caption=None,entities=entities or [],caption_entities=[],reply_to_message=reply,voice=NS(file_size=size) if size else None,reply_text=AsyncMock()))
 async def test_private_owner_only(self):
  await self.adapter.message_handler(self.update(user=456),self.ctx)
  await self.adapter.message_handler(self.update(text='/start'),self.ctx)
  self.assertEqual(len(self.calls),1)
 async def test_groups_require_allowlist_and_target(self):
  entity=NS(type='mention',offset=0,length=6)
  for chat,text,entities in [(-999,'@whale',[entity]),(-100,'hello',[]),(-100,'@whale',[entity])]:
   await self.adapter.message_handler(self.update(chat=chat,kind='supergroup',text=text,entities=entities),self.ctx)
  self.assertEqual(len(self.calls),1)
 async def test_reply_wakes_and_large_media_rejected_before_handler(self):
  reply=NS(from_user=NS(id=88))
  await self.adapter.message_handler(self.update(chat=-100,kind='supergroup',reply=reply),self.ctx)
  u=self.update(size=21*1024*1024)
  await self.adapter.message_handler(u,self.ctx)
  self.assertEqual(len(self.calls),1);u.message.reply_text.assert_awaited_once()
class RedactionTests(unittest.TestCase):
 def test_raw_token_and_api_url_are_redacted(self):
  import logging
  class Adapter:
   async def message_handler(self,u,c):pass
  load('guard').install(Adapter,'123',set())
  with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'12345:synthetic-fixture-token'}):
   record=logging.LogRecord('telegram.child',logging.ERROR,'',1,'Rejected token 12345:synthetic-fixture-token at https://api.telegram.org/bot12345:synthetic-fixture-token/getMe',(),None)
   text=logging.Formatter().format(record)
   self.assertNotIn('synthetic-fixture-token',text)

class InitTests(unittest.TestCase):
 def test_idempotent_secure_bootstrap_and_conflict(self):
  import json
  with tempfile.TemporaryDirectory() as folder,patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':'test-only-token','TELEGRAM_OWNER_ID':'123'},clear=True):
   root=Path(folder);data=root/'data';plugins=root/'plugins';plugins.mkdir()
   init=load('init');init.initialize(data,plugins)
   cfg=data/'cmd_config.json';before=cfg.read_bytes();init.initialize(data,plugins)
   self.assertEqual(before,cfg.read_bytes());
   cfg.write_text(before.decode(),encoding="utf-8-sig");init.initialize(data,plugins)
   self.assertEqual(before,cfg.read_bytes());self.assertEqual(cfg.stat().st_mode&0o777,0o600)
   value=json.loads(before);value['platform'][0]['id']='other';cfg.write_text(json.dumps(value))
   with self.assertRaises(ValueError):init.initialize(data,plugins)
if __name__=='__main__':unittest.main()
