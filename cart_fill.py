"""Durable executor for an owner's exact approved cart; independent of chat turns."""
import asyncio,copy,hashlib,json,time
import domain as D
import cart_review
LOCK=asyncio.Lock()
ACTIVE={'queued','running'}
def fingerprint(w):
    products={}
    for m in (w.get('cart') or {}).get('matches',[]):products[m['productId']]=products.get(m['productId'],0)+m['quantity']
    body={'products':products,'excluded':(w.get('cart') or {}).get('excluded',[]),'groceries':w.get('groceries'),'slots':w.get('slots'),'approved':w.get('approved')}
    return hashlib.sha256(json.dumps(body,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def jobs():return D.listing('fill')
def job_for(w):return D.read('fill',(w.get('cart') or {}).get('fill_job_id',''))
def legacy_approval(c,w):
    target=fingerprint(w)
    for r in c.execute("SELECT version,data FROM history WHERE kind='week' AND id=? ORDER BY version DESC",(w['id'],)):
        old=json.loads(r['data'])
        if fingerprint(old)!=target:break
        status=(old.get('cart') or {}).get('status')
        if status=='approved':return r['version']
        if status not in ('review','filling'):break
    return None
def start(week,version,identity,resume=False):
    with D.db() as c:
        w=D.get(c,'week',week)
        if not w or w['version']!=version:raise ValueError('La sélection a changé. Rechargez avant de remplir le panier.')
        cart=w.get('cart') or {}
        if not w.get('approved') or not (w.get('groceries') or {}).get('approved') or not cart.get('matches') or cart_review.missing(w):raise ValueError('Validez d’abord la sélection complète des produits.')
        if any((D.get(c,'fill',r[0]) or {}).get('status') in ACTIVE for r in c.execute("SELECT id FROM docs WHERE kind='fill'").fetchall()):raise ValueError('Un remplissage est déjà en cours. Consultez sa progression.')
        existing=D.get(c,'fill',cart.get('fill_job_id',''))
        if resume and existing:
            if cart.get('status')!='review' or existing['status'] not in ('paused','partial'):raise ValueError('Ce remplissage ne peut pas être repris.')
            if existing['fingerprint']!=fingerprint(w) or existing['identity']!=identity:raise ValueError('La sélection ou le compte a changé. Validez une nouvelle sélection.')
            job=existing;job['pause_requested']=False;job['error']=''
            for item in job['items']:
                if item['status']=='rejected':item['status']='pending';item['error']=''
        else:
            approval=version if cart.get('status')=='approved' else legacy_approval(c,w) if resume and cart.get('status')=='review' else None
            if approval is None:raise ValueError('Validez les produits avant de lancer le remplissage.')
            grouped={}
            for m in cart['matches']:
                id=m['productId']
                if id not in grouped:grouped[id]={'productId':id,'name':m.get('name',id),'quantity':0,'status':'pending','baseline':None,'target':None,'error':''}
                grouped[id]['quantity']+=m['quantity']
            job={'id':D.uid(),'week':week,'approval_version':approval,'fingerprint':fingerprint(w),'identity':identity,'items':list(grouped.values()),'created':time.time(),'pause_requested':False,'error':''}
        job['status']='queued';cart['status']='filling';cart['fill_job_id']=job['id'];w=D.put(c,'week',week,w,version);job['week_version']=w['version'];job=D.put(c,'fill',job['id'],job)
        return job

def quantities(cart):
    if not isinstance(cart,list):raise ValueError('Impossible de vérifier les quantités du panier.')
    result={}
    for item in cart:
        q=item.get('quantity',0)
        if not isinstance(q,(int,float)) or q<0:raise ValueError('Quantité du panier invalide.')
        result[str(item['productId'])]=result.get(str(item['productId']),0)+q
    return result

def save(job):
    with D.db() as c:
        current=D.get(c,'fill',job['id'])
        if current:job['pause_requested']=current.get('pause_requested',False)
        return D.put(c,'fill',job['id'],job)
def finish(job,status,error=''):
    job['status']=status;job['error']=error;job['updated']=time.time()
    with D.db() as c:
        current=D.get(c,'fill',job['id']);job['pause_requested']=(current or {}).get('pause_requested',False)
        job=D.put(c,'fill',job['id'],job);w=D.get(c,'week',job['week'])
        if w and (w.get('cart') or {}).get('fill_job_id')==job['id'] and w['cart']['status']=='filling':w['cart']['status']='review';D.put(c,'week',w['id'],w)
    return job

def valid(job,identity):
    w=D.read('week',job['week'])
    if not w or (w.get('cart') or {}).get('fill_job_id')!=job['id'] or w['version']!=job['week_version'] or w['cart']['status']!='filling' or fingerprint(w)!=job['fingerprint'] or identity()!=job['identity']:raise ValueError('La sélection, le compte ou l’autorisation a changé. Aucun autre ajout ne sera effectué.')
    current=D.read('fill',job['id'])
    return not current.get('pause_requested',False)

async def execute(id,transport,identity):
    async with LOCK:
        job=D.read('fill',id)
        if not job or job['status'] not in ACTIVE:return job
        job['status']='running';save(job)
        try:
            for item in job['items']:
                if not valid(job,identity):return finish(job,'paused','Remplissage mis en pause. Les produits vérifiés restent enregistrés.')
                if item['status'] in ('verified','present','rejected'):continue
                live=quantities(await transport('cart'));actual=live.get(item['productId'],0)
                if item['target'] is None:item['baseline']=actual;item['target']=max(actual,item['quantity']);save(job)
                if actual>=item['target']:
                    item['status']='present' if item['status']=='pending' else 'verified';item['actual']=actual;item['error']='';save(job);continue
                if item['status'] in ('sending','unknown'):
                    item['status']='unknown';item['error']='Résultat incertain : vérifiez ce produit dans Chronodrive avant toute nouvelle tentative.';save(job)
                    return finish(job,'paused',item['error'])
                if actual!=item['baseline']:
                    item['status']='conflict';item['error']='La quantité a été modifiée dans Chronodrive. Vérifiez-la avant de continuer.';save(job);return finish(job,'paused',item['error'])
                if not valid(job,identity):return finish(job,'paused','Pause demandée avant le prochain ajout.')
                item['status']='sending';item['error']='';save(job)
                with D.db() as c:
                    operation=D.uid();c.execute('INSERT INTO operations VALUES(?,?,?,?,?,?,?)',(operation,job['week'],job['week_version'],item['productId'],item['target'],'unknown',json.dumps({'job_id':job['id']})))
                response=None;failure=None
                try:response=await transport('set_quantity',{'productId':item['productId'],'quantity':item['target']})
                except Exception as e:failure=str(e)
                verified_read=False
                for attempt in range(3):
                    try:
                        after=quantities(await transport('cart'));actual=after.get(item['productId'],0);verified_read=True
                        if actual>=item['target'] or (response is not None and not response.get('added')):break
                    except Exception:verified_read=False
                    if attempt<2:await asyncio.sleep(0.3*(2**attempt))
                if not verified_read:
                    item['status']='unknown';item['error']='Impossible de confirmer le dernier ajout. Vérifiez le panier avant de reprendre.';save(job);return finish(job,'paused',item['error'])
                item['actual']=actual
                if actual==item['target']:item['status']='verified';item['error']='';op_status='added'
                elif actual>item['target']:item['status']='conflict';item['error']='La quantité constatée dépasse la quantité visée. Vérifiez ce produit avant de continuer.';op_status='unknown'
                elif response is not None and not response.get('added'):
                    item['status']='rejected';item['error']=response.get('message') or 'Chronodrive a refusé cet article (stock ou quantité disponible).';op_status='failed'
                else:
                    item['status']='unknown';item['error']='Le résultat de cet ajout est incertain. Aucun nouvel essai automatique.';op_status='unknown'
                with D.db() as c:c.execute('UPDATE operations SET status=?,result=? WHERE id=?',(op_status,json.dumps({'job_id':job['id'],'actual':actual,'target':item['target'],'response':response,'error':failure},ensure_ascii=False),operation))
                save(job)
                if item['status'] in ('unknown','conflict') or (response or {}).get('retry_later'):return finish(job,'paused',item['error'])
            final=quantities(await transport('cart'))
            for item in job['items']:
                if item['status'] in ('verified','present') and final.get(item['productId'],0)<item['target']:item['status']='conflict';item['error']='Cet article a été retiré ou modifié dans Chronodrive après vérification.'
            complete=all(i['status'] in ('verified','present') for i in job['items'])
            return finish(job,'completed' if complete else 'partial','' if complete else 'Certains produits restent à vérifier ; consultez les détails ci-dessous.')
        except asyncio.CancelledError:raise
        except Exception as e:return finish(job,'paused',str(e))

async def loop(transport,identity):
    while True:
        for job in jobs():
            if job['status'] in ACTIVE:await execute(job['id'],transport,identity)
        await asyncio.sleep(1)
def pause(week,version):
    with D.db() as c:
        w=D.get(c,'week',week)
        if not w or w['version']!=version:raise ValueError('Rechargez le panier avant de le mettre en pause.')
        job=D.get(c,'fill',(w.get('cart') or {}).get('fill_job_id',''))
        if not job or job['status'] not in ACTIVE:raise ValueError('Aucun remplissage actif.')
        job['pause_requested']=True;return D.put(c,'fill',job['id'],job)
