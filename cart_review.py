"""Product coverage and explicit owner-only decisions for unmatched groceries."""
import domain as D

def required(w):return {i['id']:i for i in (w.get('groceries') or {}).get('items',[]) if not i.get('checked')}
def missing(w):
    cart=w.get('cart') or {};covered={m['grocery_id'] for m in cart.get('matches',[])};excluded={x['grocery_id'] for x in cart.get('excluded',[])}
    return sorted(set(required(w))-covered-excluded)

def approve(c, week, version):
    w = D.get(c, 'week', week)
    if not w or not (w.get('groceries') or {}).get('approved') or not (w.get('cart') or {}).get('matches'):
        raise ValueError('Review proposed products first.')
    if missing(w):
        raise ValueError('Choisissez un produit ou une décision explicite pour chaque ingrédient restant avant de valider.')
    if any(not m.get('productId') for m in w['cart']['matches']):
        raise ValueError('Every proposed product needs an ID.')
    if w['cart']['status'] != 'proposed':
        raise ValueError('This cart is not awaiting approval.')
    w['cart']['status'] = 'approved'
    return D.put(c, 'week', week, w, version)

def review(week,version,grocery_id,action,product=None,quantity=None):
    with D.db() as c:
        w=D.get(c,'week',week)
        if not w or w['version']!=version:raise ValueError('La sélection a changé. Rechargez avant de la modifier.')
        if not (w.get('groceries') or {}).get('approved') or not w.get('cart'):raise ValueError('Validez les courses et préparez une sélection de produits.')
        D.editable(w)
        if grocery_id not in required(w):raise ValueError('Cet ingrédient ne fait plus partie des courses à acheter.')
        cart=w['cart'];excluded=[x for x in cart.get('excluded',[]) if x['grocery_id']!=grocery_id]
        if action in ('pantry','skip'):
            excluded.append({'grocery_id':grocery_id,'reason':action});cart['matches']=[m for m in cart['matches'] if m['grocery_id']!=grocery_id]
        elif action=='match':
            if not product or product.get('unavailable') or product.get('stock')=='NO_STOCK' or not product.get('name') or type(quantity) is not int or not 0<quantity<=100:raise ValueError('Choisissez un produit disponible et un nombre de paquets valide.')
            cart['matches']=[m for m in cart['matches'] if m['grocery_id']!=grocery_id]+[{**product,'grocery_id':grocery_id,'quantity':quantity,'note':'Produit et nombre de paquets choisis dans Table.'}]
        elif action!='restore':raise ValueError('Décision inconnue.')
        cart['excluded']=excluded;cart['unmatched']=missing(w);cart['status']='proposed';cart.pop('fill_job_id',None)
        return D.put(c,'week',week,w,version)
