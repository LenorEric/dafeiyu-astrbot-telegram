"""Offline smoke against the pinned image, real PTB objects and in-memory Bot API."""
import asyncio, json, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,'/opt/dafeiyu')
sys.path.insert(0,'/opt/dafeiyu/deploy/telegram')
from telegram import Update
from telegram.ext import ExtBot
from telegram.request import BaseRequest
from astrbot.core.platform.sources.telegram.tg_adapter import TelegramPlatformAdapter
from astrbot.api.event import MessageEventResult
from astrbot.core.message.message_event_result import ResultContentType
from astrbot.core.message.components import Plain
from plugin.astrbot_plugin_telegram_chat.main import TelegramChatPlugin, DEFAULT_CONFIG
from plugin.astrbot_plugin_schedule_awareness.main import ScheduleAwarenessPlugin
from plugin.astrbot_plugin_bili_activity.main import BiliActivity
from guard import install

class Request(BaseRequest):
    def __init__(self):self.calls=[]
    @property
    def read_timeout(self):return 5
    async def initialize(self):pass
    async def shutdown(self):pass
    async def do_request(self,url,method,request_data=None,**kwargs):
        action=url.rsplit('/',1)[-1]
        self.calls.append((action, request_data.json_parameters if request_data else {}))
        if action=='sendChatAction':result=True
        elif action=='sendVoice':
            assert any(part[1][:4]==b'OggS' for part in request_data.multipart_data.values())
            result={'message_id':45,'date':1,'chat':{'id':123,'type':'private'},'voice':{'file_id':'voice-id','file_unique_id':'voice-unique','duration':1}}
        elif action=='getMe':result={'id':88,'is_bot':True,'first_name':'Whale','username':'whale'}
        elif action=='getChat':result={'id':-100,'type':'supergroup','title':'Test','is_forum':True}
        elif action=='sendMessage':result={'message_id':44,'date':1,'chat':{'id':123,'type':'private'},'text':'你好🙂'}
        else:raise AssertionError(action)
        return 200,json.dumps({'ok':True,'result':result}).encode()

async def main():
    request=Request();bot=ExtBot('88:offline-fixture',request=request,get_updates_request=Request())
    await bot.initialize()
    adapter=TelegramPlatformAdapter({'id':'telegram','type':'telegram','telegram_token':'88:offline-fixture'}, {}, asyncio.Queue())
    adapter.client=bot
    install(TelegramPlatformAdapter,'123',{'-100'})
    events=[]
    async def handle(message):events.append(adapter.create_event(message))
    adapter.handle_msg=handle
    def update(sender):
        return Update.de_json({'update_id':1,'message':{'message_id':5,'date':1,'chat':{'id':sender,'type':'private'},'from':{'id':sender,'is_bot':False,'first_name':'User'},'text':'你好'}},bot)
    context=SimpleNamespace(bot=bot)
    await adapter.message_handler(update(456),context)
    assert not events
    await adapter.message_handler(update(123),context)
    assert len(events)==1
    event=events[0]
    assert event.unified_msg_origin=='telegram:FriendMessage:123'
    plugin=object.__new__(TelegramChatPlugin)
    plugin.admins=['123'];plugin.cfg=DEFAULT_CONFIG.copy();plugin.face_map={'微笑':'🙂'}
    plugin.pattern=__import__('re').compile(r'\[([^\[\]]{1,8})\]');plugin._face_history={}
    await plugin.inbound_face_to_text(event)
    # Deterministic stand-in for the paid provider; no outbound model calls.
    result=MessageEventResult().message('你好[微笑]')
    result.set_result_content_type(ResultContentType.LLM_RESULT)
    event.set_result(result)
    await plugin.convert_faces(event)
    assert ''.join(c.text for c in event.get_result().chain if isinstance(c,Plain))=='你好🙂'
    await event.send(event.get_result())
    assert any(action=='sendMessage' for action,_ in request.calls)
    topic=Update.de_json({'update_id':2,'message':{'message_id':5,'date':1,
        'chat':{'id':-100,'type':'supergroup','title':'Test','is_forum':True},
        'from':{'id':123,'is_bot':False,'first_name':'Owner'},'message_thread_id':17,
        'is_topic_message':True,'text':'@whale hello','entities':[{'type':'mention','offset':0,'length':6}]}},bot)
    await adapter.message_handler(topic,context)
    assert events[-1].unified_msg_origin=='telegram:GroupMessage:-100#17'
    import tempfile, wave
    from astrbot.core.platform.sources.telegram.tg_event import TelegramPlatformEvent
    with tempfile.TemporaryDirectory() as folder:
        path=Path(folder)/'speech.wav'
        with wave.open(str(path),'wb') as wav:
            wav.setparams((1,2,16000,0,'NONE','not compressed'));wav.writeframes(b'\0\0'*16000)
        await TelegramPlatformEvent._send_voice_with_fallback(bot,str(path),{'chat_id':123})
    assert any(action=='sendVoice' for action,_ in request.calls)
    await bot.shutdown()
    print('PASS: pinned AstrBot + real Telegram Update + access guard + plugin + simulated model + real PTB send via mock Bot API; three plugins import')
asyncio.run(main())
