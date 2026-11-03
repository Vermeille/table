"""Live acceptance: real agents update app learning; owner restores test guidance afterward."""
import os,json,time,urllib.request,http.cookiejar
BASE=os.getenv('QA_BASE','http://127.0.0.1:8080');cookie=''
def api(path,data=None):
 req=urllib.request.Request(BASE+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Cookie':cookie})
 with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)
req=urllib.request.Request(BASE+'/api/login',data=json.dumps({'password':os.environ['TABLE_PASSWORD']}).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as r:cookie=r.headers['Set-Cookie'].split(';')[0]
state=api('state?week=2026-11-09');original={l['id']:l for l in state['learning']};source=next(r for r in state['recipes'] if r['id']=='roasted-pepper-pizza');pending={};results={};marker='Acceptance verification: read current app preferences before making durable changes.'
for role in ('cookbook','planner','shopper','cart'):
 prompt='Acceptance verification of your self-improving skill: use context to read your current learned guidance and version, then use the learn action to append the exact line "'+marker+'" to the existing text (preserve any existing guidance). This is temporary process guidance for verification, not a personal taste preference. Do not change preferences, meal plans, groceries, or carts. '
 if role=='cookbook':prompt+='Also use your cookbook skill to save a NEW lighter variant of roasted-pepper-pizza with ID roasted-pepper-pizza-lighter, more vegetables, reduced cheese, ingredients, full method and estimated nutrition. Keep the source recipe unchanged. Explain the differences.'
 else:prompt+='Do not create or edit recipes. Report the saved learning version.'
 r=api('chat',{'role':role,'week':'2026-11-09','message':prompt});pending[role]=r['id'];print(json.dumps({'submitted_role':role,'run_id':r['id']}),flush=True)
for _ in range(120):
 time.sleep(3);state=api('state?week=2026-11-09')
 for role,rid in list(pending.items()):
  r=next(x for x in state['runs'] if x['id']==rid)
  if r['status'] in ('completed','failed','unknown','cancelled','interrupted'):
   l=next(x for x in state['learning'] if x['id']==role);results[role]={'status':r['status'],'learned':marker in l['text'],'version':l['version'],'error':r['error']};pending.pop(role);print(json.dumps({'role':role,**results[role]}),flush=True)
 if not pending:break
if pending:raise SystemExit('Runs still active; do not resubmit: '+json.dumps(pending))
# Inspect generated runtime projections before clearing the acceptance-only sentence.
from pathlib import Path
for role in results:
 projected=Path('/opt/data/profiles')/('table-'+role)/'skills'/('table-'+role)/'SKILL.md'
 assert marker in projected.read_text(),role+' learning not projected'
state=api('state?week=2026-11-09');new_source=next(r for r in state['recipes'] if r['id']==source['id']);variant=next((r for r in state['recipes'] if r['id']=='roasted-pepper-pizza-lighter'),None)
assert source==new_source,'Source recipe changed';assert variant and variant['ingredients'] and variant['method'] and variant['nutrition'],'Variant missing'
for l in state['learning']:
 if l['text'].strip()==(original[l['id']]['text']+'\n'+marker).strip():api('learning/'+l['id'],{'text':original[l['id']]['text'],'version':l['version']})
 else:print('Did not restore concurrently modified guidance for '+l['id'],flush=True)
assert all(r['status']=='completed' and r['learned'] for r in results.values()),results
print('PASS: four real role agents persisted learning into Table and runtime skill files; test guidance restored. Real lighter variant saved with original unchanged.',flush=True)
