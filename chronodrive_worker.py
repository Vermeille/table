"""One isolated client invocation; account secrets arrive over stdin only."""
import os,sys,json
p=json.load(sys.stdin)
for k,v in p['credentials'].items():os.environ['CHRONODRIVE_'+k.upper()]=str(v)
os.environ['CHRONODRIVE_SESSION_FILE']=p['session_file']
try:
    import chronodrive_client as c
    session=c.ensure_session();a=p['action'];d=p.get('data',{})
    if a=='search':
        raw=c.search_products(d['query'],session);result=[]
        for x in raw[:15]:
            labels=x.get('labels') or {};prices=x.get('prices') or {}
            result.append({'productId':str(x.get('id','')),'name':labels.get('productLabel',''),'brand':labels.get('brandLabel',''),'size':labels.get('unitQuantityLabel',''),'price':prices.get('defaultPrice'),'stock':x.get('stock'),'remainingStock':x.get('remainingStock')})
    elif a=='cart':result=c.get_cart(session)
    elif a=='add':result={'added':c.add_item_to_cart(d['productId'],d['quantity'],session)}
    else:raise ValueError('Unsupported action')
    print(json.dumps({'ok':True,'result':result},ensure_ascii=False))
except Exception as e:
    # HTTP errors can contain URLs with identity parameters. No raw exceptions leave this process.
    print(json.dumps({'ok':False,'error':'La requête Chronodrive a échoué ('+type(e).__name__+'). Vérifiez vos identifiants, le magasin ou la disponibilité du service.'}))
    sys.exit(1)
