"""Full offline AstrBot polling -> model -> Telegram pipeline. Run only in a disposable image."""
import asyncio, json, os, shutil, sys, tempfile
from pathlib import Path
from aiohttp import web
sys.path.insert(0,'/opt/dafeiyu/deploy/telegram')
from init import initialize

async def main():
    calls=[];sent=[];models=[];delivered=False
    async def api(request):
        nonlocal delivered
        action=request.path.rsplit('/',1)[-1]
        calls.append(action)
        if action=='completions':
            models.append(await request.json())
            return web.json_response({'id':'offline','object':'chat.completion','created':1,'model':'deepseek-chat','choices':[{'index':0,'message':{'role':'assistant','content':'离线链路验证成功。'},'finish_reason':'stop'}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}})
        if action=='models':return web.json_response({'object':'list','data':[{'id':'deepseek-chat','object':'model'}]})
        if action=='getMe':result={'id':88,'is_bot':True,'first_name':'Whale','username':'whale'}
        elif action=='getUpdates':
            await asyncio.sleep(.3)
            if delivered:result=[]
            else:
                delivered=True
                result=[{'update_id':n,'message':{'message_id':n,'date':int(__import__('time').time()),'chat':{'id':uid,'type':'private'},'from':{'id':uid,'is_bot':False,'first_name':'Test'},'text':'你好'}} for n,uid in [(1,456),(2,123)]]
        elif action=='sendMessage':
            data=await request.post();sent.append(dict(data))
            result={'message_id':100+len(sent),'date':1,'chat':{'id':int(data['chat_id']),'type':'private'},'text':data['text']}
        else:result=True
        return web.json_response({'ok':True,'result':result})
    app=web.Application();app.router.add_route('*','/{tail:.*}',api)
    runner=web.AppRunner(app);await runner.setup();site=web.TCPSite(runner,'127.0.0.1',0);await site.start()
    port=site._server.sockets[0].getsockname()[1]
    # All credentials are synthetic, and the container has --network none.
    env={**os.environ,'TELEGRAM_BOT_TOKEN':'88:offline-fixture','TELEGRAM_OWNER_ID':'123','DEEPSEEK_API_KEY':'offline-fixture','TELEGRAM_ALLOWED_GROUPS':''}
    os.environ.update({k:env[k] for k in ['TELEGRAM_BOT_TOKEN','TELEGRAM_OWNER_ID','DEEPSEEK_API_KEY']})
    data=Path('/AstrBot/data')
    initialize(data,Path('/opt/dafeiyu/plugin'))
    cfg=json.loads((data/'cmd_config.json').read_text(encoding='utf-8-sig'))
    cfg['platform'][0].update(telegram_api_base_url=f'http://127.0.0.1:{port}/bot',telegram_file_base_url=f'http://127.0.0.1:{port}/file/bot')
    cfg['provider'][0]['api_base']=f'http://127.0.0.1:{port}/v1'
    cfg['dashboard']={'enable':False}
    (data/'cmd_config.json').write_text(json.dumps(cfg))
    log=Path('/tmp/telegram-pipeline-runtime.log')
    with log.open('w') as output:
        process=await asyncio.create_subprocess_exec(sys.executable,'-B','/opt/dafeiyu/deploy/telegram/run.py',cwd='/AstrBot',env=env,stdout=output,stderr=output)
        try:
            for _ in range(240):
                if any('离线链路验证成功' in x.get('text','') for x in sent):break
                if process.returncode is not None:break
                await asyncio.sleep(.5)
            assert len(models)==1, f'Expected one authorized model request, got {len(models)}'
            assert sent and all(x['chat_id']=='123' for x in sent), sent
            assert any('离线链路验证成功' in x.get('text','') for x in sent), 'No pipeline reply'
            print('PASS: full pinned AstrBot startup, long polling, unauthorized-user rejection, real provider pipeline with mock OpenAI API, Telegram send; no external network')
        finally:
            if process.returncode is None:
                process.terminate()
                try:await asyncio.wait_for(process.wait(),10)
                except asyncio.TimeoutError:process.kill();await process.wait()
            await runner.cleanup()
asyncio.run(main())
