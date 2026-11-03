"""Idempotent first-run configuration; secrets never printed."""
import json, os, shutil
from pathlib import Path

def initialize(root, plugins):
    token = os.environ.get('TELEGRAM_BOT_TOKEN','').strip()
    owner = os.environ.get('TELEGRAM_OWNER_ID','').strip()
    if not token or not owner.isdecimal() or int(owner)<=0:
        raise ValueError('Set TELEGRAM_BOT_TOKEN and a positive TELEGRAM_OWNER_ID securely')
    groups = list(filter(None, os.environ.get('TELEGRAM_ALLOWED_GROUPS','').split(',')))
    if any(not g.startswith('-') or not g[1:].isdigit() for g in groups):
        raise ValueError('Group IDs must be comma-separated negative integers')
    root.mkdir(parents=True,exist_ok=True)
    p=root/'cmd_config.json'
    cfg=json.loads(p.read_text(encoding="utf-8-sig")) if p.exists() else {}
    desired={'id':'telegram','type':'telegram','enable':True,'telegram_token':token,
             'telegram_command_register':True,'telegram_command_auto_refresh':True,
             'start_message':'你好，我是大肥鱼。发送消息开始聊天。'}
    existing=cfg.get('platform',[])
    if existing and (len(existing)!=1 or existing[0].get('id')!='telegram'):
        raise ValueError('Platform configuration conflict; review existing data directory')
    cfg['platform']=[{**(existing[0] if existing else {}),**desired}]
    cfg['admins_id']=[owner]
    cfg.setdefault('provider',[])
    if not cfg['provider'] and os.environ.get('DEEPSEEK_API_KEY'):
        cfg['provider']=[{'id':'deepseek','type':'openai_chat_completion','enable':True,
                          'key':[os.environ['DEEPSEEK_API_KEY']], 'provider':'openai', 'provider_type':'chat_completion', 'api_base':'https://api.deepseek.com/v1','model':'deepseek-chat'}]
        cfg.setdefault('provider_settings',{})['default_provider_id']='deepseek'
    p.write_text(json.dumps(cfg,ensure_ascii=False,indent=2));p.chmod(0o600)
    for source in plugins.iterdir():
        target=root/'plugins'/source.name
        if not target.exists(): shutil.copytree(source,target)
    folder=root/'plugin_data'/'astrbot_plugin_bili_activity';folder.mkdir(parents=True,exist_ok=True)
    control=folder/'control.json'
    if not control.exists():control.write_text(json.dumps({'owner_id':owner,'owner_scope':f'telegram:FriendMessage:{owner}'}))

if __name__=='__main__': initialize(Path('/AstrBot/data'),Path('/opt/dafeiyu/plugin'))
