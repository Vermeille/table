"""Discover drive identifiers from Chronodrive's current public store directory."""
import json,re,time
from html.parser import HTMLParser
from pathlib import Path
import requests
DIRECTORY='https://www.chronodrive.com/magasins-chronodrive'
class StoreParser(HTMLParser):
    def __init__(self):super().__init__();self.stores={};self.current=None
    def handle_starttag(self,tag,attrs):
        if tag!='a':return
        href=dict(attrs).get('href','');match=re.search(r'/magasins-chronodrive/drive-magasin-(\d+)-([^?#]+)',href)
        if match:self.current={'id':match[1],'slug':match[2],'url':'https://www.chronodrive.com'+href,'parts':[]}
    def handle_data(self,data):
        if self.current:self.current['parts'].append(data)
    def handle_endtag(self,tag):
        if tag!='a' or not self.current:return
        item=self.current;label=' '.join(' '.join(item.pop('parts')).split())
        if label.startswith('Drive '):item['name']=label[6:];self.stores[item['id']]={k:item[k] for k in ('id','name','url')}
        self.current=None

def parse_stores(html):
    parser=StoreParser();parser.feed(html)
    return sorted(parser.stores.values(),key=lambda s:s['name'].casefold())

def stores(cache_file=None):
    path=Path(cache_file) if cache_file else None
    if path and path.exists() and time.time()-path.stat().st_mtime<3600:
        cached=json.loads(path.read_text())
        if cached:return cached
    try:
        response=requests.get(DIRECTORY,headers={'User-Agent':'Mozilla/5.0'},timeout=15);response.raise_for_status();result=parse_stores(response.text)
    except requests.RequestException:raise ValueError('Impossible de charger les magasins Chronodrive. Réessayez dans un instant.')
    if not result:raise ValueError('La liste des magasins Chronodrive a changé. Une mise à jour du connecteur est nécessaire.')
    if path:path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(result,ensure_ascii=False));path.chmod(0o600)
    return result

def store_id(value):
    value=str(value).strip()
    if value.isdigit():return value
    match=re.search(r'(?:/drive-magasin-|/store/)(\d+)(?:[-/?#]|$)',value)
    if match:return match[1]
    raise ValueError('Choisissez votre magasin Chronodrive dans la liste. Un nom ou une lettre ne suffit pas.')
