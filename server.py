import asyncio,contextlib,json,os,secrets,hmac,time,sys,subprocess,logging
from pathlib import Path
from datetime import date,timedelta
from fastapi import FastAPI,Request,HTTPException
from fastapi.responses import JSONResponse,FileResponse
from fastapi.staticfiles import StaticFiles
import httpx
from cryptography.fernet import Fernet
import domain as D
import cart_review
import cart_fill
from french import error as french_error
ROOT=Path(__file__).parent;LOG=logging.getLogger('table');TOKENS={};SESSIONS={};PROVISION_LOCK=asyncio.Lock()
PASSWORD=os.getenv('TABLE_PASSWORD') or os.getenv('STUDIO_PASSWORD','')
HELP={
 'context':'{week?: YYYY-MM-DD}: recipes, preferences, learning, selected week',
 'get_recipe':'{id}', 'search_recipes':'{query}',
 'save_recipe':'cookbook: {id,version (0 for new),title,servings,ingredients:[{name,quantity,unit}],tags:[],nutrition:{kcal,protein_g,carbs_g,fat_g},method, nutrition_note?}',
 'save_week':'planner: {week,version,slots:[{day:0..6,meal:dinner|lunch|breakfast,recipe_id,servings}]}',
 'grocery_base':'shopper: {week}: exact scaled ingredients for approved plan',
 'save_groceries':'shopper: {week,version,items:[{id?,name,quantity,unit,note,checked}]}',
 'search_products':'cart: {query}: real Chronodrive search', 'get_cart':'cart: {}',
 'propose_cart':'cart: {week,version,matches:[{grocery_id,productId,name,brand,size,quantity,price,note}]}',
 'fill_status':'cart: {week}: read the durable app-managed cart fill; the owner starts or resumes it in the UI',
 'learn':'{text,version}: replace learned skill guidance after merging current explicit preferences'}
def encrypted_read(name):
    p=D.DATA/(name+'.enc')
    return json.loads(Fernet((D.DATA/'key').read_bytes()).decrypt(p.read_bytes())) if p.exists() else None
def encrypted_write(name,data):
    p=D.DATA/(name+'.enc');p.write_bytes(Fernet((D.DATA/'key').read_bytes()).encrypt(json.dumps(data).encode()));p.chmod(0o600)
def model():return encrypted_read('model') or {'provider':'openai-codex','model':'gpt-5.6-luna','base_url':'','api_key':''}
def config():return encrypted_read('connection') or {'url':os.getenv('HERMES_URL','http://hermes-agent:8642'),'app_url':os.getenv('TABLE_INTERNAL_URL','http://table:8080'),'api_key':os.getenv('API_SERVER_KEY','')}
async def provision(role):
    async with PROVISION_LOCK:
        learning=D.read('learning',role)['text'];skill=(ROOT/'skills'/f'{role}.md').read_text()+'\n\n## Indications apprises\n\n'+(learning or 'Aucune préférence apprise pour le moment.')
        cfg=config();payload={'id':'table-'+role,'role':role,'title':'Table · '+{'cookbook':'Recettes','planner':'Planning','shopper':'Courses','cart':'Chronodrive'}[role],'soul':f'You are Table’s {role} assistant. Use the table-{role} skill for all durable operations. The Table app owns recipes, preferences, plans and approvals. Never edit app data directly. Read the skill now; use its CLI. Owner approval happens only in the app. Do not call checkout or place orders. Communique toujours en français. Rédige les titres, ingrédients, étapes, étiquettes et nouvelles indications apprises en français. Conserve les identifiants techniques existants.','skill':skill,'cli':(ROOT/'table_cli.py').read_text(),'url':cfg['app_url'],'token':TOKENS[role],'model':model()}
        env={**os.environ,'API_SERVER_KEY':cfg['api_key']}
        proc=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'profile_worker.py'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE,env=env)
        out,err=await proc.communicate(json.dumps(payload).encode())
        if proc.returncode:LOG.error('Profile installation failed for %s: %s',role,err.decode()[-1500:]);raise HTTPException(503,'Hermes profile installation failed. Check shared Hermes volumes and server logs.')
async def hermes(role,method,path,data=None,headers=None):
    cfg=config()
    try:
        async with httpx.AsyncClient(timeout=30) as c:r=await c.request(method,cfg['url'].rstrip('/')+'/p/table-'+role+path,json=data,headers={'Authorization':'Bearer '+cfg['api_key'],**(headers or {})})
        if not r.is_success:raise HTTPException(502,f'Hermes returned HTTP {r.status_code}.')
        return r.json()
    except httpx.HTTPError:raise HTTPException(503,'Cannot reach Hermes. Check the connection settings.')
async def wait_profiles(timeout=60):
    # A fresh gateway discovers newly created profiles asynchronously. Do not
    # expose a ready installer while /p/<profile> still returns 404.
    pending=set(D.ROLES);deadline=time.monotonic()+timeout
    while pending:
        roles=sorted(pending)
        results=await asyncio.gather(*(hermes(role,'GET','/api/sessions?limit=1') for role in roles),return_exceptions=True)
        pending={role for role,result in zip(roles,results) if isinstance(result,Exception)}
        if not pending:return
        if time.monotonic()>=deadline:raise HTTPException(503,'Hermes has not made all Table profiles available yet. Check the gateway and reinstall profiles from Connections.')
        await asyncio.sleep(1)
async def poll():
    while True:
        with D.db() as c:runs=[dict(r) for r in c.execute("SELECT * FROM runs WHERE status IN ('running','queued','waiting_for_approval')")]
        for r in runs:
            try:
                remote=await hermes(r['role'],'GET','/v1/runs/'+r['remote']);output=remote.get('output','');status=remote.get('status','running')
                if not isinstance(output,str):output=json.dumps(output)
                with D.db() as c:c.execute('UPDATE runs SET status=?,output=?,error=? WHERE id=?',(status,output,str(remote.get('error') or ''),r['id']))
            except HTTPException:pass
            except Exception:LOG.exception('Run polling')
        await asyncio.sleep(2)
@contextlib.asynccontextmanager
async def lifespan(app):
    global TOKENS
    D.init();D.DATA.chmod(0o700)
    if not (D.DATA/'key').exists():(D.DATA/'key').write_bytes(Fernet.generate_key());(D.DATA/'key').chmod(0o600)
    with D.db() as c:c.execute("UPDATE runs SET status='unknown',error='L’envoi a été interrompu. Vérifiez la discussion Hermes avant de réessayer.' WHERE status='submitting'")
    TOKENS=encrypted_read('tokens') or {role:secrets.token_urlsafe(40) for role in D.ROLES};encrypted_write('tokens',TOKENS)
    for r in D.recipes():D.write_markdown(r)
    if not D.recipes():
        for recipe in json.loads((ROOT/'seed.json').read_text()):D.save_recipe(recipe)
    from french import migrate
    migrate()
    try:
        for role in D.ROLES:await provision(role)
        await wait_profiles()
        app.state.provision_error=None
    except Exception as e:app.state.provision_error=french_error(str(getattr(e,'detail',e)));LOG.warning('Setup needed: %s',app.state.provision_error)
    task=asyncio.create_task(poll());fill_task=asyncio.create_task(cart_fill.loop(chrono,cart_identity));yield;task.cancel();fill_task.cancel()
    await asyncio.gather(task,fill_task,return_exceptions=True)
app=FastAPI(lifespan=lifespan)
@app.middleware('http')
async def auth(request,call_next):
    p=request.url.path
    if request.method in ('POST','PUT','DELETE') and request.headers.get('Origin') and request.headers['Origin']!=str(request.base_url).rstrip('/'):
        # Proxy base_url may have forwarded HTTPS; compare host plus HTTPS from the public browser.
        from urllib.parse import urlsplit
        if urlsplit(request.headers['Origin']).netloc!=request.headers.get('host'):return JSONResponse({'detail':'Origine de la demande non autorisée'},403)
    if p.startswith('/api/') and p not in ('/api/health','/api/login') and not p.startswith('/api/worker/'):
        token=request.cookies.get('table_session','')
        if SESSIONS.get(token,0)<time.time():return JSONResponse({'detail':'Connectez-vous à Table'},401)
    try:return await call_next(request)
    except ValueError as e:return JSONResponse({'detail':french_error(str(e))},409)
@app.exception_handler(HTTPException)
async def http_error(req,e):return JSONResponse({'detail':french_error(e.detail)},status_code=e.status_code,headers=e.headers)
@app.exception_handler(ValueError)
async def invalid(req,e):return JSONResponse({'detail':french_error(str(e))},409)
@app.get('/api/health')
def health():return {'status':'ok','setup_error':getattr(app.state,'provision_error',None)}
@app.post('/api/login')
async def login(req:Request):
    data=await req.json()
    if not PASSWORD or not hmac.compare_digest(str(data.get('password','')),PASSWORD):raise HTTPException(401,'Incorrect password')
    token=secrets.token_urlsafe(40);SESSIONS[token]=time.time()+86400*14;r=JSONResponse({'ok':True});r.set_cookie('table_session',token,httponly=True,samesite='strict',secure=os.getenv('COOKIE_SECURE','true')=='true',max_age=86400*14);return r
@app.post('/api/logout')
def logout(req:Request):
    SESSIONS.pop(req.cookies.get('table_session',''),None);r=JSONResponse({'ok':True});r.delete_cookie('table_session');return r
@app.get('/api/state')
def state(week:str=''):
    today=date.today();week=week or (today-timedelta(days=today.weekday())).isoformat()
    with D.db() as c:
        runs=[dict(r) for r in c.execute('SELECT * FROM runs ORDER BY created DESC LIMIT 60')]
        current=D.get(c,'week',D.week_id(week)) or D.blank_week(week)
        fill=D.get(c,'fill',(current.get('cart') or {}).get('fill_job_id',''))
    return {'recipes':D.recipes(),'week':current,'weeks':[{'id':w['id'],'approved':w['approved'],'count':len(w['slots'])} for w in D.listing('week')],'preferences':D.read('preferences','main'),'learning':D.listing('learning'),'runs':runs,'fill_job':fill,'setup_error':getattr(app.state,'provision_error',None)}
@app.post('/api/recipes')
async def recipe_save(req:Request):return D.save_recipe(await req.json())
@app.get('/api/recipes/{id}/markdown')
def markdown(id:str):
    D.valid_id(id);p=D.DATA/'cookbook'/(id+'.md')
    if not p.exists():raise HTTPException(404,'Recipe not found')
    return FileResponse(p,media_type='text/markdown',filename=id+'.md')
@app.post('/api/week/{week}/save')
async def save_week(week,req:Request):return D.update_week(week,await req.json())
@app.post('/api/week/{week}/cart-item')
async def cart_item(week,req:Request):
    p=await req.json();product=None
    if p['action']=='match':
        from chronodrive_products import product_id
        id=product_id(p['productId']);items=await chrono('products',{'ids':[id]});product=next((x for x in items if x['productId']==id),None)
    return cart_review.review(week,p['version'],p['grocery_id'],p['action'],product,p.get('quantity'))
@app.post('/api/week/{week}/{action}')
async def workflow(week,action,req:Request):
    p=await req.json();v=p['version']
    if action=='approve':return D.approve_week(week,v)
    if action=='groceries':return D.groceries(week,v,p.get('items'))
    if action=='approve-groceries':return D.approve_groceries(week,v)
    if action=='approve-cart':
        with D.db() as c:
            w=D.get(c,'week',week)
            if not w or not (w.get('groceries') or {}).get('approved') or not (w.get('cart') or {}).get('matches'):raise ValueError('Review proposed products first.')
            if cart_review.missing(w):raise ValueError('Choisissez un produit ou une décision explicite pour chaque ingrédient restant avant de valider.')
            if any(not m.get('productId') for m in w['cart']['matches']):raise ValueError('Every proposed product needs an ID.')
            if w['cart'].get('status')!='proposed':raise ValueError('This cart is not awaiting approval.')
            w['cart']['status']='approved';return D.put(c,'week',week,w,v)
    if action in ('fill-cart','resume-fill'):
        return cart_fill.start(week,v,cart_identity(),resume=action=='resume-fill')
    if action=='pause-fill':return cart_fill.pause(week,v)
    if action=='reopen-cart':
        with D.db() as c:
            w=D.get(c,'week',week)
            if not w:raise ValueError('Panier introuvable.')
            D.editable(w);w['cart']['status']='proposed';w['cart'].pop('fill_job_id',None)
            return D.put(c,'week',week,w,v)
    if action=='reconcile-cart':
        with D.db() as c:
            w=D.get(c,'week',week)
            if w['version']!=v:raise ValueError('Reload first.')
            if any(r['status'] in ('running','queued','waiting_for_approval','submitting') for r in c.execute("SELECT status FROM runs WHERE role='cart' AND week=?",(week,))):raise ValueError('The cart assistant is still running.')
            w['cart']['status']='review';return D.put(c,'week',week,w,v)
    raise HTTPException(404,'Unknown action')
@app.post('/api/preferences')
async def prefs(req:Request):return D.preferences(await req.json())
@app.post('/api/learning/{role}')
async def learning(role,req:Request):
    p=await req.json();r=D.learn(role,p['text'],p['version']);await provision(role);return r
@app.get('/api/learning/{role}/history')
def history(role):
    with D.db() as c:return [dict(r) for r in c.execute("SELECT version,data,at FROM history WHERE kind='learning' AND id=? ORDER BY version DESC",(role,))]
@app.get('/api/settings')
def settings():
    m=model();cfg=config();cred=encrypted_read('chronodrive')
    return {'provider':m['provider'],'model':m['model'],'base_url':m.get('base_url',''),'has_api_key':bool(m.get('api_key')),'hermes_url':cfg['url'],'app_url':cfg['app_url'],'chronodrive':{'connected':bool(cred),'email':(cred or {}).get('email',''),'store_id':(cred or {}).get('store_id','')}}
@app.post('/api/settings')
async def setup(req:Request):
    p=await req.json();m=model();cfg=config()
    if 'provider' in p:
        if p['provider'] not in ('openai','openai-codex'):raise ValueError('Choose OpenAI API or OpenAI/Codex sign-in.')
        m.update({k:p[k] for k in ('provider','model','base_url') if k in p})
        if p.get('api_key'):m['api_key']=p['api_key']
        encrypted_write('model',m)
    for k in ('hermes_url','app_url','gateway_key'):
        if p.get(k):cfg[{'hermes_url':'url','app_url':'app_url','gateway_key':'api_key'}[k]]=p[k]
    encrypted_write('connection',cfg)
    for role in D.ROLES:await provision(role)
    await wait_profiles()
    app.state.provision_error=None;return {'installed':True}
@app.post('/api/codex/start')
async def codex_start():
    from hermes_cli.web_routers.oauth import _start_codex_device_code
    return await _start_codex_device_code('default')
@app.get('/api/codex/status/{id}')
async def codex_status(id):
    from hermes_cli.web_server_oauth import _oauth_sessions,_oauth_sessions_lock
    with _oauth_sessions_lock:
        s=_oauth_sessions.get(id)
        if not s:raise HTTPException(404,'Sign-in expired. Start again.')
        return {'status':s.get('status'),'error':s.get('error_message')}
@app.get('/api/chronodrive/search')
async def search_chronodrive(query:str):
    if not query.strip() or len(query)>200:raise ValueError('Saisissez un produit à rechercher.')
    return await chrono('search',{'query':query.strip()})
@app.post('/api/chronodrive/products')
async def chronodrive_products(req:Request):
    from chronodrive_products import product_id
    ids=(await req.json()).get('ids',[])
    if not isinstance(ids,list) or len(ids)>60:raise ValueError('Demandez au maximum 60 produits.')
    return await chrono('products',{'ids':[product_id(x) for x in ids]})
@app.get('/api/chronodrive/stores')
async def chronodrive_stores():
    from chronodrive_stores import stores
    return await asyncio.to_thread(stores,D.DATA/'chronodrive'/'stores.json')
@app.post('/api/chronodrive/test')
async def chronodrive_test():
    items=await chrono('cart');return {'connected':True,'items':items}
@app.post('/api/chronodrive')
async def chronodrive_setup(req:Request):
    if any(j['status'] in cart_fill.ACTIVE for j in cart_fill.jobs()):raise ValueError('Mettez le remplissage en pause avant de changer de compte ou de magasin.')
    p=await req.json();old=encrypted_read('chronodrive') or {}
    for k in ('email','password','store_id'):
        if p.get(k):old[k]=p[k]
    if not all(old.get(k) for k in ('email','password','store_id')):raise ValueError('Email, password and store ID are required.')
    from chronodrive_stores import store_id,stores
    old['store_id']=store_id(old['store_id'])
    directory=await asyncio.to_thread(stores,D.DATA/'chronodrive'/'stores.json')
    if old['store_id'] not in {x['id'] for x in directory}:raise ValueError('Ce magasin Chronodrive n’est pas disponible dans la liste actuelle.')
    encrypted_write('chronodrive',old)
    cache=D.DATA/'chronodrive'/'session.json'
    if cache.exists():cache.unlink()
    return {'saved':True}
def cart_identity():
    import hashlib
    cred=encrypted_read('chronodrive') or {}
    return hashlib.sha256(json.dumps({'email':cred.get('email'),'store_id':cred.get('store_id')},sort_keys=True).encode()).hexdigest()
async def chrono(action,data=None):
    cred=encrypted_read('chronodrive')
    if not cred:raise ValueError('Connect Chronodrive in Settings first.')
    proc=await asyncio.create_subprocess_exec(sys.executable,str(ROOT/'chronodrive_worker.py'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.PIPE)
    try:out,_=await asyncio.wait_for(proc.communicate(json.dumps({'credentials':cred,'session_file':str(D.DATA/'chronodrive'/'session.json'),'action':action,'data':data or {}}).encode()),85)
    except asyncio.CancelledError:
        proc.terminate();await proc.wait();raise
    except asyncio.TimeoutError:proc.kill();await proc.wait();raise ValueError('Chronodrive timed out. Check the cart before retrying any changes.')
    try:r=json.loads(out)
    except Exception:raise ValueError('Chronodrive client failed. No automatic retry was made.')
    if not r['ok']:raise ValueError(r['error'])
    return r['result']
async def submit(role,week,prompt):
    if role not in D.ROLES:raise ValueError('Unknown assistant')
    with D.db() as c:
        if c.execute("SELECT 1 FROM runs WHERE role=? AND status IN ('submitting','running','queued','waiting_for_approval')",(role,)).fetchone():raise ValueError('This assistant is already working. Wait for its answer.')
        rid=D.uid();c.execute('INSERT INTO runs(id,role,week,status,prompt) VALUES(?,?,?,?,?)',(rid,role,week,'submitting',prompt))
    try:
        listing=await hermes(role,'GET','/api/sessions?title=Bot%20Chat&include_hidden=1');s=next((s for s in listing.get('data',[]) if s.get('title')=='Bot Chat'),None)
        if not s:
            raw=await hermes(role,'POST','/api/sessions',{'title':'Bot Chat','source':'bot_peer_dm'});s=raw.get('session',raw)
        text=f'Semaine sélectionnée : {week}. Réponds en français et rédige tout nouveau contenu en français. Use your table-{role} skill and its CLI for all changes. Owner request: '+prompt
        if len(text)>16000:raise ValueError('Please shorten this request.')
        r=await hermes(role,'POST','/v1/runs',{'session_id':s['id'],'input':text},{'Idempotency-Key':'table-'+rid})
        with D.db() as c:c.execute('UPDATE runs SET status=?,remote=?,session=? WHERE id=?',('running',r['run_id'],s['id'],rid))
    except Exception as e:
        with D.db() as c:c.execute("UPDATE runs SET status='unknown',error=? WHERE id=?",('Impossible de confirmer l’envoi. Vérifiez la discussion Hermes avant de réessayer.',rid))
        raise
    return {'id':rid,'status':'running'}
@app.post('/api/chat')
async def chat(req:Request):
    p=await req.json();return await submit(p['role'],D.week_id(p['week']),p['message'])
@app.get('/api/runs/{id}/native')
async def native(id):
    from native_owner import snapshot
    with D.db() as c:r=c.execute('SELECT * FROM runs WHERE id=?',(id,)).fetchone()
    if not r:raise HTTPException(404,'Run not found')
    return await snapshot({'id':'table-'+r['role'],'session_id':r['session']})
@app.post('/api/runs/{id}/{action}')
async def control(id,action,req:Request):
    from native_owner import control
    with D.db() as c:r=c.execute('SELECT * FROM runs WHERE id=?',(id,)).fetchone()
    if not r:raise HTTPException(404,'Run not found')
    remote=await hermes(r['role'],'GET','/v1/runs/'+r['remote'])
    return await control({'id':'table-'+r['role'],'session_id':r['session']},action,await req.json(),remote.get('delivery_id'))
@app.post('/api/worker/{action}')
async def worker(action,req:Request):
    token=req.headers.get('Authorization','').removeprefix('Bearer ');role=next((r for r,t in TOKENS.items() if hmac.compare_digest(token,t)),None)
    if not role:raise HTTPException(401,'Invalid worker credential')
    p=await req.json()
    allowed={'cookbook':{'save_recipe'},'planner':{'save_week'},'shopper':{'grocery_base','save_groceries'},'cart':{'search_products','get_cart','propose_cart','cart_add','fill_status'}}
    common={'help','context','get_recipe','search_recipes','learn'}
    if action not in common|allowed[role]:raise HTTPException(403,'This assistant cannot perform that action')
    if action=='help':return {k:v for k,v in HELP.items() if k in common|allowed[role]}
    if action=='context':return {'recipes':D.recipes(),'preferences':D.read('preferences','main'),'learning':D.read('learning',role),'week':D.load_week(p['week']) if p.get('week') else None}
    if action=='get_recipe':return D.read('recipe',p['id'])
    if action=='search_recipes':return [r for r in D.recipes() if p['query'].casefold() in json.dumps(r,ensure_ascii=False).casefold()]
    if action=='save_recipe':return D.save_recipe(p)
    if action=='save_week':return D.update_week(p['week'],p)
    if action=='grocery_base':
        w=D.load_week(p['week'])
        if not w['approved']:raise ValueError('Approve the plan first.')
        return {'week_version':w['version'],'items':D.aggregate(w)}
    if action=='save_groceries':return D.groceries(p['week'],p['version'],p['items'])
    if action=='learn':
        result=D.learn(role,p['text'],p['version']);await provision(role);return result
    if action=='search_products':return await chrono('search',p)
    if action=='get_cart':return await chrono('cart')
    if action=='fill_status':return cart_fill.job_for(D.load_week(p['week']))
    if action=='propose_cart':return propose_cart(p)
    if action=='cart_add':return await cart_add(p)
def propose_cart(p):
    with D.db() as c:
        w=D.get(c,'week',p['week'])
        if not w or not (w.get('groceries') or {}).get('approved'):raise ValueError('Approve groceries before choosing products.')
        D.editable(w);excluded=(w.get('cart') or {}).get('excluded',[]);excluded_ids={x['grocery_id'] for x in excluded};items=set(cart_review.required(w))-excluded_ids;covered=set()
        for m in p['matches']:
            if m.get('grocery_id') not in items or not m.get('productId') or type(m.get('quantity')) is not int or not 0<m['quantity']<=100:raise ValueError('Invalid product match or pack quantity.')
            covered.add(m['grocery_id'])
        w['cart']={'matches':p['matches'],'unmatched':sorted(items-covered),'excluded':excluded,'status':'proposed'};return D.put(c,'week',p['week'],w,p['version'])
async def cart_add(p):
    # Reserve before dispatch. Unknown outcomes are never replayed automatically.
    with D.db() as c:
        w=D.get(c,'week',p['week'])
        if not w or w['version']!=p['version'] or not (w.get('groceries') or {}).get('approved') or (w.get('cart') or {}).get('status')!='filling':raise ValueError('No active owner-approved cart fill for this version.')
        if c.execute("SELECT 1 FROM operations WHERE week=? AND status='unknown'",(p['week'],)).fetchone():raise ValueError('A previous cart operation needs reconciliation. Inspect Chronodrive before continuing.')
        if w['cart'].get('fill_job_id'):raise ValueError('Le remplissage est géré par Table. Consultez sa progression ; ne lancez pas des ajouts individuels.')
        matches=[m for m in w['cart']['matches'] if m['productId']==p['productId']]
        qty=sum(m['quantity'] for m in matches)
        if not matches or p['quantity']!=qty:raise ValueError('Product or quantity does not match the approved cart.')
        if c.execute('SELECT 1 FROM operations WHERE week=? AND product=? AND version=?',(p['week'],p['productId'],p['version'])).fetchone():raise ValueError('This product was already attempted. Inspect the cart; do not retry automatically.')
    existing=await chrono('cart')
    if not isinstance(existing,list):raise ValueError('Cannot verify existing cart contents. No product was added.')
    if any(str(i.get('productId'))==p['productId'] for i in existing):raise ValueError('This product is already in your cart. Review its quantity in Chronodrive before requesting another addition; the app will not overwrite it.')
    with D.db() as c:
        current=D.get(c,'week',p['week'])
        if not current or current['version']!=p['version'] or (current.get('cart') or {}).get('status')!='filling':raise ValueError('Cart approval changed during verification.')
        if c.execute("SELECT 1 FROM operations WHERE week=? AND (status='unknown' OR (product=? AND version=?))",(p['week'],p['productId'],p['version'])).fetchone():raise ValueError('A cart operation was already attempted or needs reconciliation.')
        op=D.uid();c.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?)',(op,p['week'],p['version'],p['productId'],qty,'unknown',''))
    try:
        result=await chrono('add',p);status='added' if result.get('added') else 'failed'
        with D.db() as c:c.execute('UPDATE operations SET status=?,result=? WHERE id=?',(status,json.dumps(result),op))
        return result
    except Exception:raise ValueError('Cart update outcome is unknown. Inspect Chronodrive before making any further changes.')
@app.get('/api/cart/{week}/operations')
def operations(week):
    with D.db() as c:return [dict(x) for x in c.execute('SELECT * FROM operations WHERE week=?',(week,))]
app.mount('/static',StaticFiles(directory=ROOT/'static'),name='static')
@app.get('/')
def index():return FileResponse(ROOT/'static'/'index.html')
