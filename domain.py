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
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,role TEXT,week TEXT,remote TEXT,session TEXT,status TEXT,prompt TEXT,output TEXT DEFAULT '',error TEXT DEFAULT '',created TEXT DEFAULT CURRENT_TIMESTAMP,automated INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS operations(id TEXT PRIMARY KEY,week TEXT,version INTEGER,product TEXT,quantity INTEGER,status TEXT,result TEXT);
        ''')
        if not any(column['name'] == 'automated' for column in c.execute('PRAGMA table_info(runs)')):
            c.execute('ALTER TABLE runs ADD COLUMN automated INTEGER NOT NULL DEFAULT 0')
        for role in ROLES:
            if not get(c,'learning',role):put(c,'learning',role,{'text':''})
        if not get(c,'preferences','main'):put(c,'preferences','main',{'planner':'Prévoir des dîners pour 2 personnes. Privilégier des repas variés et pratiques, et utiliser les restes intelligemment. Demander les éventuelles contraintes alimentaires plutôt que les supposer.','shopper':'Regrouper les ingrédients communs aux repas. Demander avant de supposer qu’un ingrédient est déjà dans les réserves.','cart':'Privilégier le bon rapport qualité-prix et des formats adaptés. Demander avant de remplacer un produit indisponible.'})
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
    import recipe_nutrition as N

    data = dict(data)
    title = data.get('title')
    method = data.get('method')
    if not isinstance(title, str) or not title.strip() or not isinstance(method, str) or not method.strip():
        raise ValueError('A title and recipe method are required.')
    id = valid_id(data.get('id') or re.sub('[^a-z0-9]+','-',title.lower()).strip('-')[:70] or uid())
    N.validate_recipe_quantities(data)
    if not isinstance(data.get('tags', []), list):raise ValueError('Invalid tags or nutrition.')
    data.setdefault('tags', [])
    data.pop('nutrition_note', None)
    data.pop('freezer_only', None)
    with db() as c:
        old = get(c, 'recipe', id)
        if 'planning' not in data and old and 'planning' in old:
            data['planning'] = old['planning']
        if 'planning' in data:
            data['planning'] = recipe_planning(data['planning'])
        if 'freezer_ok' not in data and old:
            # Older clients preserve metadata when the recipe itself is unchanged.
            if all(data.get(field) == old.get(field) for field in ('method', 'ingredients')):
                for field in ('freezer_ok', 'freezer_note'):
                    if field in old: data[field] = old[field]
        if 'freezer_ok' in data and type(data['freezer_ok']) is not bool:
            raise ValueError('Précisez si le plat complet se congèle bien.')
        if data.get('freezer_ok'):
            data['freezer_note'] = str(data.get('freezer_note', '')).strip()[:500]
        else:
            data.pop('freezer_note', None)
        data['ingredients'], data['nutrition'], data['nutrition_report'] = N.calculate({**data, 'id':id}, enrich=True, previous=old)
        r = put(c, 'recipe', id, data, data.get('version', 0))
    write_markdown(r);return r
def recipe_planning(value):
    if not isinstance(value,dict):raise ValueError('Indiquez les informations de préparation de la recette.')
    fields={}
    if 'portable' in value:
        if type(value['portable']) is not bool:raise ValueError('Précisez si le repas peut être emporté.')
        fields['portable']=value['portable']
    for key in ('active_minutes','total_minutes'):
        if key in value and value[key] is not None:
            if type(value[key]) is not int or not 1 <= value[key] <= 1440:raise ValueError('Indiquez un temps de préparation en minutes.')
            fields[key]=value[key]
    if fields.get('total_minutes',1440) < fields.get('active_minutes',0):raise ValueError('Le temps total inclut le temps de préparation active.')
    if 'equipment' in value:
        equipment=value['equipment']
        if not isinstance(equipment,list) or len(equipment)>12 or any(not isinstance(item,str) or len(item)>50 for item in equipment):
            raise ValueError('Indiquez les ustensiles nécessaires sous forme de liste.')
        fields['equipment']=list(dict.fromkeys(item.strip() for item in equipment if item.strip()))
    return fields
def week_id(id):
    d=datetime.date.fromisoformat(id)
    if d.weekday()!=0:raise ValueError('A week starts on Monday.')
    return id
def blank_week(id):return {'id':week_id(id),'version':0,'slots':[],'approved':False,'groceries':None,'cart':None}
def load_week(id):return read('week',week_id(id)) or blank_week(id)
def editable(w):
    if w.get('cart',{} ) and w['cart'].get('status')=='filling':raise ValueError('Cart filling is active. Wait for it to finish before editing this week.')
def compose_week(c, id, data, w, batch_config=None):
    import batch
    diary = batch.kitchen(c, id)
    completed = {key for key, event in diary['entries'].items() if event['action'] != 'skip'}
    originals = {batch.key(slot): slot for slot in w['slots']}
    slots=[]
    for s in data['slots']:
        day=int(s['day']);meal=s.get('meal','dinner');servings=float(s['servings'])
        if day not in range(7) or meal not in ('breakfast','lunch','dinner') or not 0<servings<=100:raise ValueError('Invalid meal slot.')
        if any(x['day']==day and x['meal']==meal for x in slots):raise ValueError('Duplicate meal slot.')
        slot_key = f'{day}-{meal}'
        if slot_key in completed:
            original = originals[slot_key]
            if original['recipe_id'] != s['recipe_id'] or original['servings'] != servings:
                raise ValueError('Ce repas a déjà été enregistré dans le suivi du congélateur.')
            slots.append(original)
            continue
        recipe = batch.find_slot_recipe(c, s)
        if not recipe:raise ValueError('Recipe no longer exists.')
        slot = {'day':day,'meal':meal,'recipe_id':recipe['id'],'servings':servings,'recipe':recipe}
        if s.get('freezer_lot_id'):
            slot['freezer_lot_id'] = s['freezer_lot_id']
        elif s.get('cook_fresh') is True:
            slot['cook_fresh'] = True
        slots.append(slot)
    if not completed <= {batch.key(slot) for slot in slots}:
        raise ValueError('Un repas déjà enregistré doit rester dans le planning.')
    new = {'slots':slots,'approved':False,'groceries':None,'cart':None}
    config = batch_config if batch_config is not None else batch.settings(get(c, 'preferences', 'main'))
    if config['enabled'] or completed or any(slot.get('freezer_lot_id') for slot in slots):
        new['batch'] = batch.build(c, id, slots, config, w, diary['entries'])
        new['batch_settings'] = config
    if completed:
        new['already_cooked'] = [key for key in completed if diary['entries'][key]['action'] == 'freeze']
    return new, diary, completed

def update_week(id,data,*,agent=False):
    with db() as c:
        w=get(c,'week',week_id(id)) or blank_week(id);editable(w)
        if agent and active_automation(c, 'planner'):
            raise ValueError('Utilisez la proposition hebdomadaire pendant la préparation automatique.')
        if w['version']!=data['version']:raise ValueError('The week changed. Reload before saving.')
        batch_config=None
        if w.get('weekly_prepared'):
            import batch
            prefs=get(c,'preferences','main')
            previous=w.get('batch_settings',batch.settings(prefs))
            batch_config={**(batch.settings(prefs) if prefs.get('batch') else previous),
                          'prefer_frozen_days':previous.get('prefer_frozen_days',[])}
        draft, diary, completed = compose_week(c, id, data, w, batch_config)
        if len(completed) != len(diary['entries']):
            diary['entries'] = {key: diary['entries'][key] for key in completed}
            put(c, 'kitchen', id, diary, diary['version'])
        if w.get('weekly_prepared'):
            from weekly import revise
            return revise(c,w,draft)
        return put(c, 'week', id, draft, w['version'])

def approve_week(id,version):
    import batch
    with db() as c:
        w=get(c,'week',id);editable(w or {})
        if not w or not w['slots']:raise ValueError('Add meals before approving this week.')
        if w['approved']:raise ValueError('This week is already approved.')
        if w['version'] != version:raise ValueError('This item changed. Reload before saving.')
        if w.get('batch'):batch.validate_plan(c, w)
        w['approved']=True;w['approved_at']=datetime.datetime.now(datetime.timezone.utc).isoformat()
        if not w.get('weekly_prepared'):
            w['groceries']=None;w['cart']=None
        if not w.get('groceries') and w.get('batch') and not aggregate(w):
            w['groceries']={'items':[], 'approved':False}
        job=get(c,'weekly',id)
        if job and job['status']=='ready' and job['request_id']==w.get('weekly_prepared') and not job.get('seen'):
            put(c,'weekly',id,{**job,'seen':True},job['version'])
        # Recipe snapshots in slots preserve the exact approved recipes.
        return put(c,'week',id,w,version)
def aggregate(w):
    import batch
    items={}
    for s in w['slots']:
        key = batch.key(s)
        task = w.get('batch', {}).get(key, {})
        if task.get('source') in batch.ACTIVE_SOURCES or key in w.get('already_cooked', []):continue
        r=s['recipe'];factor=task.get('quantity', s['servings'])/r['servings']
        sources=(r.get('nutrition_report') or {}).get('rows',[])
        for index,i in enumerate(r['ingredients']):
            unit=i['unit'].strip().lower();n=i['quantity']*factor
            if unit=='kg':unit='g';n*=1000
            if unit=='l':unit='ml';n*=1000
            key=(i['name'].strip().casefold(),unit)
            if key not in items:items[key]={'id':uid(),'name':i['name'],'unit':unit,'quantity':0,'checked':False,'note':''}
            items[key]['quantity']=round(items[key]['quantity']+n,3)
            if unit not in ('g','kg','ml','l','cl'):
                grams=sources[index].get('grams') if index<len(sources) else None
                previous=items[key].get('edible_grams',0)
                items[key]['edible_grams']=round(previous+grams*factor,3) if grams is not None and previous is not None else None
    return list(items.values())
def groceries(id,version,items=None):
    with db() as c:
        w=get(c,'week',id)
        if not w or not w['approved']:raise ValueError('Approve the meal plan first.')
        editable(w)
        originals={i['id']:i for i in (w.get('groceries') or {}).get('items',[])}
        if items is None:items=aggregate(w)
        for i in items:
            if not i.get('name') or not isinstance(i.get('quantity'),(int,float)) or i['quantity']<=0:raise ValueError('Invalid grocery quantity.')
            i.setdefault('id',uid());i.setdefault('unit','');i.setdefault('checked',False);i.setdefault('note','')
            old = originals.get(i['id'])
            if old and i.get('edible_grams') is not None:
                if old['name']!=i['name'] or old['unit']!=i['unit']:
                    i.pop('edible_grams',None)
                elif old.get('edible_grams'):
                    i['edible_grams']=round(old['edible_grams']*i['quantity']/old['quantity'],3)
        preview = w.get('cart') or {}
        if items and preview.get('weekly_preview'):
            required = {i['id']:i for i in items if not i['checked']}
            unchanged = {key for key,item in required.items() if key in originals and all(
                item[field] == originals[key][field] for field in ('name','quantity','unit'))}
            matches = [m for m in preview['matches'] if m['grocery_id'] in unchanged]
            w['cart'] = {**preview, 'matches':matches, 'excluded':[], 'status':'proposed',
                         'unmatched':sorted(set(required) - {m['grocery_id'] for m in matches})}
        else:
            w['cart'] = None
        w['groceries']={'items':items,'approved':False}
        return put(c,'week',id,w,version)
def approve_groceries(id,version):
    with db() as c:
        w=get(c,'week',id)
        if not w or not w['approved'] or not w.get('groceries'):raise ValueError('Prepare groceries first.')
        editable(w);w['groceries']['approved']=True
        if not (w.get('cart') or {}).get('weekly_preview'):
            w['cart']=None
        return put(c,'week',id,w,version)
def active_automation(c, role):
    return bool(c.execute("SELECT 1 FROM runs WHERE role=? AND automated=1 AND status IN ('submitting','running','queued','waiting_for_approval')",(role,)).fetchone())
def preferences(data):
    import batch
    with db() as c:
        saved = get(c, 'preferences', 'main')
        if 'batch' in data:
            data['batch'] = batch.normalize_settings(data['batch'])
        elif saved and 'batch' in saved:
            data['batch'] = saved['batch']
        return put(c,'preferences','main',data,data.get('version'))
def learn(role,text,version=None):
    if role not in ROLES:raise ValueError('Unknown skill.')
    if len(text)>16000:raise ValueError('Keep learned guidance under 16,000 characters.')
    with db() as c:return put(c,'learning',role,{'text':text},version)
