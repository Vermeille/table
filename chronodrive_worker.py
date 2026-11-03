"""One isolated client invocation; account secrets arrive over stdin only."""
import os,sys,json
p=json.load(sys.stdin)
for k,v in p['credentials'].items():os.environ['CHRONODRIVE_'+k.upper()]=str(v)
os.environ['CHRONODRIVE_SESSION_FILE']=p['session_file']
try:
    import chronodrive_client as c
    session=c.ensure_session();a=p['action'];d=p.get('data',{})
    from chronodrive_products import normalize,product_id
    if a=='search':result=[normalize(x) for x in c.search_products(d['query'],session)[:15]]
    elif a=='products':
        import time
        from pathlib import Path
        from concurrent.futures import ThreadPoolExecutor
        ids=list(dict.fromkeys(product_id(x) for x in d['ids']))
        if len(ids)>60:raise ValueError('Trop de produits demandés.')
        folder=Path(p['session_file']).parent/'products';folder.mkdir(exist_ok=True)
        def detail(id):
            cache=folder/(c.SITE_ID+'-'+id+'.json')
            try:
                if cache.exists() and time.time()-cache.stat().st_mtime<3600:return json.loads(cache.read_text())
                item=normalize(c.product_details(id,session));item['productId']=id;cache.write_text(json.dumps(item,ensure_ascii=False));cache.chmod(0o600);return item
            except Exception:return {'productId':id,'image_url':None,'unavailable':True}
        with ThreadPoolExecutor(max_workers=6) as pool:result=list(pool.map(detail,ids))
    elif a=='cart':result=c.get_cart(session)
    elif a=='add':result={'added':c.add_item_to_cart(d['productId'],d['quantity'],session)}
    else:raise ValueError('Unsupported action')
    print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
except Exception as e:
    # HTTP errors can contain URLs with identity parameters. No raw exceptions leave this process.
    print(json.dumps({'ok':False,'error':'La requête Chronodrive a échoué ('+type(e).__name__+'). Vérifiez vos identifiants, le magasin ou la disponibilité du service.'}))
    sys.exit(1)
