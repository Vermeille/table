import os,json,time,urllib.request,http.cookiejar
BASE=os.getenv('QA_BASE','http://127.0.0.1:8080')
cj=http.cookiejar.CookieJar();op=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
def api(path,data=None):
 req=urllib.request.Request(BASE+'/api/'+path,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json'})
 # Internal test uses a manually attached secure cookie below.
 req.add_header('Cookie','table_session='+globals().get('token',''))
 with op.open(req,timeout=40) as r:return json.load(r)
r=op.open(urllib.request.Request(BASE+'/api/login',data=json.dumps({'password':os.environ['TABLE_PASSWORD']}).encode(),headers={'Content-Type':'application/json'}));token=r.headers['Set-Cookie'].split(';')[0].split('=',1)[1]
s=api('state?week=2026-11-09');print(json.dumps({'recipes':len(s['recipes']),'setup_error':s['setup_error']}),flush=True)
r=api('chat',{'role':'cookbook','week':'2026-11-09','message':'Create and save one new pizza recipe called "Roasted pepper pizza" with ID roasted-pepper-pizza, ingredients, tags, estimated per-serving nutrition, and clear cooking steps. Use the cookbook skill CLI to actually save it in Table. Keep the existing recipes.'});print(json.dumps({'submitted':r}),flush=True)
for _ in range(90):
 time.sleep(3);s=api('state?week=2026-11-09');run=next(x for x in s['runs'] if x['id']==r['id'])
 if run['status'] in ('completed','failed','unknown','cancelled'):
  print(json.dumps({'status':run['status'],'output':run['output'],'error':run['error'],'recipe_saved':any(x['id']=='roasted-pepper-pizza' for x in s['recipes'])}),flush=True);break
else:print('Run still active; inspect without resubmission.',flush=True)
