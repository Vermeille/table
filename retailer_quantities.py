"""Compare recipe quantities with the retailer's declared pack contents."""
import math
import re

from recipe_nutrition import fdc_url, identity

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
COLZA_SOURCE = 'https://www.fao.org/4/y2774e/y2774e04.htm'
MASS_FROM_VOLUME = {
    'huile de colza':(.912,COLZA_SOURCE,('huile','colza')),
    'lait de coco en conserve':(.95,fdc_url('170173'),('lait de coco',)),
}
RECONSTITUTED = {
    '7613036750011': ('bouillon de legumes',12,500,'https://www.auchan.fr/maggi-tablettes-bouillon-kub-legumes-25-de-sel/pr-C1238502'),
    '7613033687983': ('bouillon de boeuf',18,500,'https://www.auchan.fr/maggi-bouillon-kub-de-boeuf/pr-C1227490'),
}


def measurement(value, unit):
    dimension = UNITS.get(identity(unit)) if isinstance(unit,str) else None
    if dimension and type(value) in (int,float) and math.isfinite(value) and value > 0:
        return round(value * dimension[1],6), dimension[0]
    return None


def labelled_measurement(label):
    if not isinstance(label,str):
        return None
    matched = LABEL.fullmatch(label.strip())
    if not matched:
        return None
    count, amount, unit = matched.groups()
    return measurement(int(count or 1)*float(amount.replace(',','.')),unit)


def content(product):
    packaging=product.get('packaging') or {}
    label=(product.get('labels') or {}).get('unitQuantityLabel') or ''
    measured=measurement(packaging.get('unitMeasure'),packaging.get('unit'))
    stated=labelled_measurement(label)
    if measured and stated and measured[1]==stated[1]:
        measured=min(measured,stated)
    else:
        measured=stated or measured
    return {'amount':measured[0],'unit':measured[1]} if measured else None


def barcodes(product):
    return re.findall(r'\b\d{13}\b',' '.join(map(str,product.get('eans') or [])))


def drained(product):
    trusted = next((DRAINED[code] for code in barcodes(product) if code in DRAINED),None)
    return {'amount':trusted[0],'unit':'g','url':trusted[1]} if trusted else None


def pack_options(product):
    other={}
    units=labelled_measurement((product.get('labels') or {}).get('portionLabel') or '')
    if units and units[1]=='pièce':
        other['pieces']={'amount':units[0],'unit':units[1]}
    stock=next((RECONSTITUTED[code] for code in barcodes(product) if code in RECONSTITUTED),None)
    if stock:
        ingredient,cubes,cube_ml,source=stock
        other['prepared']={'ingredient':ingredient,'amount':cubes*cube_ml,'unit':'ml','cube_ml':cube_ml,'url':source}
    return other


def matches_form(grocery, product):
    ingredient=identity(grocery['name'])
    label=identity(product['name'])
    if 'kit' in label.split() and 'kit' not in ingredient.split():
        return False
    if ingredient.startswith('pate a pizza') and not re.search(r'\bpate (?:a )?pizza\b',label):
        return False
    return True


def quantity_for(grocery, product, proposed):
    ingredient=identity(grocery['name'])
    require_drained = 'egoutt' in ingredient or bool(re.search(r'^(?:pois chiches?|.*haricots? (?:rouges?|blancs?)) cuits?\b',ingredient))
    size = product.get('drained') if require_drained else product.get('pack')
    if require_drained and not size:
        return None
    needed = measurement(grocery['quantity'],grocery['unit'])
    options=product.get('pack_options') or {}
    prepared=options.get('prepared')
    if needed and needed[1]=='pièce' and options.get('pieces'):
        size=options['pieces']
    if needed and needed[1]=='ml' and prepared and prepared['ingredient']==ingredient:
        size=prepared
    if size and size['unit']=='g' and (not needed or needed[1]!='g') and grocery.get('edible_grams'):
        needed = (grocery['edible_grams'],'g')
    if size and size['unit']=='g' and not needed and ingredient=='ail' and identity(grocery['unit'])=='gousse':
        needed=(grocery['quantity']*3,'g')
        size={**size,'url':fdc_url('169230')}
    if size and needed and size['unit']=='ml' and needed[1]=='g':
        conversion=MASS_FROM_VOLUME.get(ingredient)
        if conversion and all(term in identity(product['name']) for term in conversion[2]):
            size={'amount':size['amount']*conversion[0],'unit':'g','url':conversion[1],'approximate':True}
    if not size or not needed or needed[1]!=size['unit']:
        return {'quantity':proposed,'verified_quantity':False,'pack_source':None,'note':'Format à confirmer.'}
    count = math.ceil(needed[0]/size['amount'] - 1e-9)
    if not 0 < count <= 100:
        return None
    qty = lambda value: f'{value:g}'.replace('.',',')
    state = ' égouttés' if require_drained else ''
    dose = f' · 1 cube pour {size["cube_ml"]} ml d’eau' if size.get('cube_ml') else ''
    approximate='env. ' if size.get('approximate') else ''
    return {'quantity':count,'verified_quantity':True,'pack_source':size.get('url'),
            'note':f'{count} × {approximate}{qty(size["amount"])} {size["unit"]}{state} pour {qty(needed[0])} {needed[1]} nécessaires{dose}.'}
