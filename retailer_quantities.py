"""Compare recipe quantities with the retailer's declared pack contents."""
import math
import re

from recipe_nutrition import identity

# Barcode to edible drained weight in grams and its manufacturer or retailer reference.
DRAINED = {
    '3083681085860': (265, 'https://www.bonduelle.fr/legumes/p/pois-chiches-cuits-dans-tres-peu-de-jus/03083681085860'),
    '3083681178333': (260, 'https://www.auchan.fr/bonduelle-pois-chiches-cuits-dans-tres-peu-de-jus/pr-C1830994'),
    '3596710389926': (500, 'https://www.auchan.fr/auchan-haricots-blancs/pr-C1229292'),
    '3254560020962': (500, 'https://www.auchan.fr/auchan-haricots-rouges/pr-C1158229'),
    '3596710451722': (375, 'https://www.auchan.fr/auchan-haricots-rouges/pr-C1162142'),
    '3083681085990': (250, 'https://www.auchan.fr/bonduelle-haricots-rouges-cuits-dans-tres-peu-de-jus/pr-C1163469'),
    '3017800078860': (265, 'https://www.auchan.fr/sultanines-pois-chiches-secs-et-trempes/pr-C1230489'),
}
UNITS = {'g':('g',1),'kg':('g',1000),'ml':('ml',1),'cl':('ml',10),'l':('ml',1000),
         'piece':('pièce',1),'pieces':('pièce',1),'oeuf':('pièce',1),'oeufs':('pièce',1)}
LABEL = re.compile(r'(?:(\d+)\s*[x×]\s*)?(\d+(?:[.,]\d+)?)\s*(kg|g|ml|cl|l|pi[èe]ces?|[oœ]eufs?)', re.I)


def measurement(value, unit):
    dimension = UNITS.get(identity(unit)) if isinstance(unit,str) else None
    if dimension and type(value) in (int,float) and math.isfinite(value) and value > 0:
        return round(value * dimension[1],6), dimension[0]
    return None


def content(product):
    packaging = product.get('packaging') or {}
    measured = measurement(packaging.get('unitMeasure'),packaging.get('unit'))
    if measured:
        return {'amount':measured[0],'unit':measured[1]}
    label = (product.get('labels') or {}).get('unitQuantityLabel') or ''
    matched = LABEL.fullmatch(label.strip())
    if not matched:
        return None
    count, amount, unit = matched.groups()
    measured = measurement(int(count or 1)*float(amount.replace(',','.')),unit)
    return {'amount':measured[0],'unit':measured[1]} if measured else None


def drained(product):
    barcodes = re.findall(r'\b\d{13}\b',' '.join(map(str,product.get('eans') or [])))
    trusted = next((DRAINED[code] for code in barcodes if code in DRAINED),None)
    return {'amount':trusted[0],'unit':'g','url':trusted[1]} if trusted else None


def quantity_for(grocery, product, proposed):
    require_drained = 'egoutt' in identity(grocery['name'])
    size = product.get('drained') if require_drained else product.get('pack')
    if require_drained and not size:
        return None
    needed = measurement(grocery['quantity'],grocery['unit'])
    if size and size['unit']=='g' and (not needed or needed[1]!='g') and grocery.get('edible_grams'):
        needed = (grocery['edible_grams'],'g')
    if not size or not needed or needed[1]!=size['unit']:
        return {'quantity':proposed,'verified_quantity':False,'pack_source':None,'note':'Format à confirmer.'}
    count = math.ceil(needed[0]/size['amount'] - 1e-9)
    if not 0 < count <= 100:
        return None
    qty = lambda value: f'{value:g}'.replace('.',',')
    state = ' égouttés' if require_drained else ''
    return {'quantity':count,'verified_quantity':True,'pack_source':size.get('url'),
            'note':f'{count} × {qty(size["amount"])} {size["unit"]}{state} pour {qty(needed[0])} {needed[1]} nécessaires.'}
