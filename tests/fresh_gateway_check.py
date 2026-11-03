"""Acceptance against an isolated real gateway and empty app data; no provider login cloned."""
import asyncio,json,os,urllib.request,subprocess,sys
from pathlib import Path
cookie=''
def api(path,data=None):
 req=urllib.request.Request('http://127.0.0.1:8080/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Cookie':cookie})
 with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)
req=urllib.request.Request('http://127.0.0.1:8080/api/login',data=json.dumps({'password':os.environ['TABLE_PASSWORD']}).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as r:cookie=r.headers['Set-Cookie'].split(';')[0]
s=api('state');assert not s['setup_error'],s;assert len(s['recipes'])==10
assert not Path('/opt/data/auth.json').exists(),'Fresh gateway must have no copied authentication'
# Exercise owner setup without paying for or pretending to authenticate a model request.
r=api('settings',{'provider':'openai','model':'gpt-4.1-mini','api_key':'acceptance-placeholder-not-a-real-credential'});assert r['installed']
sys.path.insert(0,"/app")
import server
async def check():
 sessions={}
 for role in ('cookbook','planner','shopper','cart'):
  listing=await server.hermes(role,'GET','/api/sessions?title=Bot%20Chat&include_hidden=1')
  existing=next((x for x in listing.get('data',[]) if x.get('title')=='Bot Chat'),None)
  if not existing:
   raw=await server.hermes(role,'POST','/api/sessions',{'title':'Bot Chat','source':'bot_peer_dm'});existing=raw.get('session',raw)
  assert existing['id'];sessions[role]=existing['id']
 return sessions
sessions=asyncio.run(check())
for role in sessions:
 profile=Path('/opt/data/profiles')/('table-'+role)
 cfg=(profile/'config.yaml').read_text();assert 'gpt-4.1-mini' in cfg and 'openai' in cfg
 result=subprocess.run([sys.executable,str(profile/'skills'/('table-'+role)/'table_cli.py'),'context','{}'],capture_output=True,text=True,timeout=30)
 assert result.returncode==0,(role,result.stdout,result.stderr)
 assert len(json.loads(result.stdout)['recipes'])==10
print(json.dumps({'fresh_runtime_uid':os.getuid(),'profiles_routed':len(sessions),'seed_recipes':10,'model_setup_saved':True,'role_callbacks_verified':4,'no_previous_provider_auth':True}),flush=True)
