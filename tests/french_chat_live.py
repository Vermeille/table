"""Read-only acceptance of the deployed assistant's French language instruction."""
import os,json,time,urllib.request
cookie=''
def api(path,data=None):
 req=urllib.request.Request('http://127.0.0.1:8080/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','Cookie':cookie})
 with urllib.request.urlopen(req,timeout=40) as r:return json.load(r)
req=urllib.request.Request('http://127.0.0.1:8080/api/login',data=json.dumps({'password':os.environ['TABLE_PASSWORD']}).encode(),headers={'Content-Type':'application/json'})
with urllib.request.urlopen(req) as r:cookie=r.headers['Set-Cookie'].split(';')[0]
run=api('chat',{'role':'planner','week':'2026-11-09','message':'Summarize the saved meal plan in two sentences, using the app’s language. This is a read-only check: do not change any recipes, plans, groceries, preferences or learned guidance.'});print(json.dumps({'run_id':run['id']}),flush=True)
for _ in range(90):
 time.sleep(2);state=api('state?week=2026-11-09');r=next(r for r in state['runs'] if r['id']==run['id'])
 if r['status'] in ('completed','failed','cancelled','unknown'):
  print(json.dumps({'status':r['status'],'output':r['output'],'error':r['error']},ensure_ascii=False),flush=True)
  assert r['status']=='completed';break
else:print('Run still active; inspect without resubmitting.',flush=True)
