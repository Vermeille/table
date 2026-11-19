"""Canonical retailer metadata, including public product-photo URLs."""
import re
from urllib.parse import urlsplit,urljoin
from retailer_quantities import content,drained

def product_id(value):
    value=str(value)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}',value):raise ValueError('Identifiant de produit incorrect.')
    return value

def image_url(product):
    images=product.get('images') or {}
    for key in ('views','thumbnails','zooms'):
        for path in images.get(key,[]) or []:
            if not isinstance(path,str):continue
            url=urljoin('https://static1.chronodrive.com/',path)
            parsed=urlsplit(url)
            if parsed.scheme=='https' and parsed.hostname=='static1.chronodrive.com' and parsed.path.startswith('/img/') and not parsed.username and not parsed.password:return url
    return None

def normalize(product):
    labels=product.get('labels') or {};prices=product.get('prices') or {}
    return {'productId':str(product.get('id','')),'name':labels.get('productLabel','').strip(),'brand':labels.get('brandLabel','').strip(),'size':labels.get('unitQuantityLabel',''),'price':prices.get('defaultPrice'),'stock':product.get('stock'),'remainingStock':product.get('remainingStock'),'image_url':image_url(product),'pack':content(product),'drained':drained(product)}
