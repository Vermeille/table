"""App-owned documents and versioned workflow; Hermes is a replaceable worker."""
import os,json,sqlite3,re,uuid,datetime,contextlib
from pathlib import Path
DATA=Path(os.getenv('TABLE_DATA','/table-data'))
ROLES=('cookbook','planner','shopper','cart')
def uid():return uuid.uuid4().hex
@contextlib.contextmanager
def db():
    c=sqlite3.connect(DATA/'table.db',timeout=20);c.row_factory=sqlite3.Row
    try:
        c.execute('PRAGMA foreign_keys=ON');c.execute('BEGIN IMMEDIATE');yield c;c.commit()
    except: c.rollback();raise
    finally:c.close()
def init():
    DATA.mkdir(parents=True,exist_ok=True);(DATA/'cookbook').mkdir(exist_ok=True)
    with db() as c:
        c.executescript('''CREATE TABLE IF NOT EXISTS docs(kind TEXT,id TEXT,version INTEGER,data TEXT,PRIMARY KEY(kind,id));
        CREATE TABLE IF NOT EXISTS history(kind TEXT,id TEXT,version INTEGER,data TEXT,at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,role TEXT,week TEXT,remote TEXT,session TEXT,status TEXT,prompt TEXT,output TEXT DEFAULT '',error TEXT DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,week TEXT,version INTEGER,product TEXT,quantity INTEGER,status TEXT,result TEXT);
        ''')
        for role in ROLES:
            if not get(c,'learning',role):put(c,'learning',role,{'text':''})
        if not get(c,'preferences','main'):put(c,'preferences','main',{'planner':'Plan dinners for 2 people. Prefer varied, practical meals; use leftovers intelligently. Ask about dietary restrictions rather than assuming them.','shopper':'Combine ingredients across meals. Ask before assuming anything is already in the pantry.','cart':'Prefer good value and appropriate pack sizes. Ask before substituting unavailable products.'})
    # Markdown files are a durable projection rebuilt from authoritative versioned documents.
    for r in recipes():write_markdown(r)
def get(c,kind,id):
    r=c.execute('SELECT version,data FROM docs WHERE kind=? AND id=?',(kind,id)).fetchone()
    return {**json.loads(r['data']),'id':id,'version':r['version']} if r else None
def put(c,kind,id,data,expected=None):
    old=get(c,kind,id)
    if expected is not None and (old or {}).get('version',0)!=expected:raise ValueError('This item changed. Reload before saving.')
    v=(old or {}).get('version',0)+1;data={k:v for k,v in data.items() if k not in ('id','version')}
    raw=json.dumps(data,ensure_ascii=False)
    c.execute('INSERT INTO docs VALUES(?,?,?,?) ON CONFLICT(kind,id) DO UPDATE SET version=excluded.version,data=excluded.data',(kind,id,v,raw))
    c.execute('INSERT INTO history(kind,id,version,data) VALUES(?,?,?,?)',(kind,id,v,raw))
    return {**data,'id':id,'version':v}
def read(kind,id):
    with db() as c:return get(c,kind,id)
def listing(kind):
    with db() as c:return [get(c,kind,r[0]) for r in c.execute('SELECT id FROM docs WHERE kind=? ORDER BY id',(kind,)).fetchall()]
def recipes():return listing('recipe')
def valid_id(id):
    if not re.fullmatch('[a-z0-9][a-z0-9-]{0,79}',id):raise ValueError('Use a short lowercase recipe ID, with hyphens.')
    return id
def write_markdown(r):
    p=DATA/'cookbook'/f"{valid_id(r['id'])}.md";tmp=p.with_suffix('.tmp')
    tmp.write_text('---\n'+json.dumps({k:v for k,v in r.items() if k!='method'},ensure_ascii=False,indent=2)+'\n---\n\n'+r['method']+'\n');tmp.replace(p)
def save_recipe(data):
    data=dict(data);id=valid_id(data.get('id') or re.sub('[^a-z0-9]+','-',data['title'].lower()).strip('-')[:70] or uid())
    if not data.get('title') or not data.get('method'):raise ValueError('A title and recipe method are required.')
    if not isinstance(data.get('servings'),(int,float)) or not 0<data['servings']<=100:raise ValueError('Servings must be between 1 and 100.')
    if not isinstance(data.get('ingredients'),list) or not data['ingredients']:raise ValueError('Add ingredients with name, quantity and unit.')
    for i in data['ingredients']:
        if not i.get('name') or not isinstance(i.get('quantity'),(int,float)) or i['quantity']<=0 or not isinstance(i.get('unit'),str):raise ValueError('Every ingredient needs a positive quantity, name and unit.')
    if not isinstance(data.get('tags',[]),list) or not isinstance(data.get('nutrition',{}),dict):raise ValueError('Invalid tags or nutrition.')
    data.setdefault('nutrition',{});data.setdefault('tags',[]);data['nutrition_note']=data.get('nutrition_note','Estimated per serving; verify for dietary decisions.')
    with db() as c:r=put(c,'recipe',id,data,data.get('version',0))
    write_markdown(r);return r
def week_id(id):
    d=datetime.date.fromisoformat(id)
    if d.weekday()!=0:raise ValueError('A week starts on Monday.')
    return id
def blank_week(id):return {'id':week_id(id),'version':0,'slots':[],'approved':False,'groceries':None,'cart':None}
def load_week(id):return read('week',week_id(id)) or blank_week(id)
def editable(w):
    if w.get('cart',{} ) and w['cart'].get('status')=='filling':raise ValueError('Cart filling is active. Wait for it to finish before editing this week.')
def update_week(id,data):
    with db() as c:
        w=get(c,'week',week_id(id)) or blank_week(id);editable(w)
        if w['version']!=data['version']:raise ValueError('The week changed. Reload before saving.')
        slots=[]
        for s in data['slots']:
            day=int(s['day']);meal=s.get('meal','dinner');servings=float(s['servings'])
            if day not in range(7) or meal not in ('breakfast','lunch','dinner') or not 0<servings<=100:raise ValueError('Invalid meal slot.')
            r=get(c,'recipe',s['recipe_id'])
            if not r:raise ValueError('Recipe no longer exists.')
            if any(x['day']==day and x['meal']==meal for x in slots):raise ValueError('Duplicate meal slot.')
            slots.append({'day':day,'meal':meal,'recipe_id':r['id'],'servings':servings,'recipe':r})
        return put(c,'week',id,{'slots':slots,'approved':False,'groceries':None,'cart':None},w['version'])
def approve_week(id,version):
    with db() as c:
        w=get(c,'week',id);editable(w or {})
        if not w or not w['slots']:raise ValueError('Add meals before approving this week.')
        if w['approved']:raise ValueError('This week is already approved.')
        w['approved']=True;w['approved_at']=datetime.datetime.now(datetime.timezone.utc).isoformat();w['groceries']=None;w['cart']=None
        # Recipe snapshots in slots preserve the exact approved recipes.
        return put(c,'week',id,w,version)
def aggregate(w):
    items={}
    for s in w['slots']:
        r=s['recipe'];factor=s['servings']/r['servings']
        for i in r['ingredients']:
            unit=i['unit'].strip().lower();n=i['quantity']*factor
            if unit=='kg':unit='g';n*=1000
            if unit=='l':unit='ml';n*=1000
            key=(i['name'].strip().casefold(),unit)
            if key not in items:items[key]={'id':uid(),'name':i['name'],'unit':unit,'quantity':0,'checked':False,'note':''}
            items[key]['quantity']=round(items[key]['quantity']+n,3)
    return list(items.values())
def groceries(id,version,items=None):
    with db() as c:
        w=get(c,'week',id)
        if not w or not w['approved']:raise ValueError('Approve the meal plan first.')
        editable(w)
        if items is None:items=aggregate(w)
        for i in items:
            if not i.get('name') or not isinstance(i.get('quantity'),(int,float)) or i['quantity']<=0:raise ValueError('Invalid grocery quantity.')
            i.setdefault('id',uid());i.setdefault('unit','');i.setdefault('checked',False);i.setdefault('note','')
        w['groceries']={'items':items,'approved':False};w['cart']=None
        return put(c,'week',id,w,version)
def approve_groceries(id,version):
    with db() as c:
        w=get(c,'week',id)
        if not w or not w['approved'] or not w.get('groceries'):raise ValueError('Prepare groceries first.')
        editable(w);w['groceries']['approved']=True;w['cart']=None
        return put(c,'week',id,w,version)
def preferences(data):
    with db() as c:return put(c,'preferences','main',data,data.get('version'))
def learn(role,text,version=None):
    if role not in ROLES:raise ValueError('Unknown skill.')
    if len(text)>16000:raise ValueError('Keep learned guidance under 16,000 characters.')
    with db() as c:return put(c,'learning',role,{'text':text},version)
