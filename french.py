"""French defaults and an idempotent text-only migration of existing app documents."""
import copy,json
from pathlib import Path
STRINGS=json.loads((Path(__file__).parent/'locales/data-fr.json').read_text())
def text(value):return STRINGS.get(value,value) if isinstance(value,str) else value
def recipe(value):
    result=copy.deepcopy(value)
    for field in ('title','method','nutrition_note'):
        if field in result:result[field]=text(result[field])
    result['tags']=[text(t) for t in result.get('tags',[])]
    for ingredient in result.get('ingredients',[]):
        ingredient['name']=text(ingredient['name']);ingredient['unit']=text(ingredient['unit'])
    return result
def migrate():
    import domain as D
    changed=[]
    with D.db() as c:
        if D.get(c,'migration','french-v1'):return
        for row in c.execute("SELECT id FROM docs WHERE kind='recipe'").fetchall():
            original=D.get(c,'recipe',row['id']);translated=recipe(original)
            if translated!=original:changed.append(D.put(c,'recipe',original['id'],translated,original['version']))
        for row in c.execute("SELECT id FROM docs WHERE kind='week'").fetchall():
            original=D.get(c,'week',row['id']);translated=copy.deepcopy(original)
            if (original.get('cart') or {}).get('status')=='filling':raise ValueError('Attendez la fin du remplissage du panier avant de passer en français.')
            for slot in translated['slots']:slot['recipe']=recipe(slot['recipe'])
            for item in (translated.get('groceries') or {}).get('items',[]):
                for field in ('name','unit','note'):
                    if field in item:item[field]=text(item[field])
            if translated!=original:D.put(c,'week',original['id'],translated,original['version'])
        prefs=D.get(c,'preferences','main')
        if prefs:
            translated={k:text(v) for k,v in prefs.items()}
            if translated!=prefs:D.put(c,'preferences','main',translated,prefs['version'])
        D.put(c,'migration','french-v1',{'language':'fr-FR'})
    for r in changed:D.write_markdown(r)

ERRORS=json.loads((Path(__file__).parent/'locales/errors-fr.json').read_text())
def error(value):
    if not isinstance(value,str):return value
    if value.startswith('Hermes returned HTTP '):return 'Hermes a renvoyé une erreur HTTP '+value.removeprefix('Hermes returned HTTP ')
    return ERRORS.get(value,value)
