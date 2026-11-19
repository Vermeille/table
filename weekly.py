"""Durable, owner-reviewable preparation of each weekly menu."""
import asyncio
import itertools
import json
import logging
import re
import time
from collections import Counter
from datetime import datetime, time as clock_time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import batch
import cart_review
import domain as D
from chronodrive_products import product_id
from retailer_quantities import quantity_for

LOG = logging.getLogger('table.weekly')
ACTIVE = {'queued', 'planning', 'shopping', 'matching'}
ACTIVE_RUN = {'submitting', 'running', 'queued', 'waiting_for_approval'}
DEFAULTS = {'enabled': False, 'day': 4, 'at': '18:00', 'timezone': 'Europe/Paris',
            'people': 2, 'meals': ['lunch', 'dinner'], 'days': list(range(7)),
            'portable': [0, 1, 3, 4], 'no_cook': [], 'cook_days': 4,
            'diet': 'any', 'exclude': [], 'daily_kcal': None, 'pantry': []}
LIMIT_SECONDS = 8 * 60
LEGUMES = re.compile(r'lentill|pois chich|pois cass|haricot(?:s)? (?:noir|blanc|rouge)')
VEGETABLE = re.compile(r'tomat|chou|poivron|epinard|brocoli|courgette|carotte|poireau|oignon|aubergine|champignon|laitue|concombre|haricot(?:s)? vert')
WHOLE_GRAIN = re.compile(r'complet|boulgour|quinoa|orge perl|avoine')
FISH = re.compile(r'saumon|sardine|lieu noir|cabillaud|maquereau|thon|merlu|truite|poisson|anchois|crevette|crabe|coquillag|calamar|\bmoules?\b|fruits? de mer')
MEAT = re.compile(r'poulet|poule\b|dinde|canard|boeuf|veau|porc|bacon|jambon|viande|agneau|saucisse|worcestershire|gelatine')
DAIRY_EGG = re.compile(r'oeuf|\blait(?! de (?:coco|soja|riz|avoine|amande))|fromage|emmental|ricotta|mozzarella|feta|cheddar|parmesan|yaourt|creme(?! de (?:coco|soja))|\bbeurre(?! de (?:cacahuete|arachide))|\bmiel')
FRUIT = re.compile(r'\b(?:pommes?(?! de terre)|poires?|bananes?|oranges?|citrons?|clementines?|mandarines?|pamplemousses?|fraises?|framboises?|myrtilles?|cerises?|prunes?|abricots?|peches?|raisins?|mangues?|ananas|kiwis?|papayes?|goyaves?|figues?|dattes?|melons?|pasteques?|fruits?(?! de mer))\b')
PORTABLE = {
    'black-bean-tacos': False, 'margherita-pizza': False, 'roasted-pepper-pizza': False,
    'roasted-pepper-pizza-lighter': False, 'roast-salmon-potatoes': False,
    'chicken-pepper-traybake': True, 'enchiladas-poulet-haricots': True,
    'courgette-pea-risotto': True, 'spinach-ricotta-pasta': True, 'red-lentil-dal': True,
    'mushroom-barley-soup': True, 'tomato-butter-beans': True, 'lemon-chickpea-bowl': True,
    'quesadillas-champignons-mais': True, 'chili-con-carne-haricots-rouges': True,
    'tourte-viande-worcestershire': True,
}


def normalized(value):
    from recipe_nutrition import identity
    return identity(value)


def install_pack():
    """Offer batch recipes on both new and existing installs without replacing edits."""
    pack_id = 'batch-repas-complets-v1'
    if D.read('recipe_pack', pack_id):
        return
    recipes = json.loads(Path(__file__).with_name('weekly_recipes.json').read_text())
    for recipe in recipes:
        if not D.read('recipe', recipe['id']):
            try:
                D.save_recipe(recipe)
            except ValueError:
                if not D.read('recipe', recipe['id']):
                    raise
    with D.db() as c:
        if not D.get(c, 'recipe_pack', pack_id):
            D.put(c, 'recipe_pack', pack_id, {'installed':True})


def settings(c):
    return {**DEFAULTS, 'version': 0, **(D.get(c, 'weekly_settings', 'main') or {})}


def integer(value, minimum, maximum, label):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(label)
    return value


def day_list(value):
    if not isinstance(value, list) or any(type(day) is not int or not 0 <= day < 7 for day in value):
        raise ValueError('Choisissez des jours de la semaine.')
    return sorted(set(value))


def labels(value):
    if not isinstance(value, list) or len(value) > 40 or any(not isinstance(i, str) or len(i) > 80 for i in value):
        raise ValueError('La liste doit contenir au maximum 40 aliments.')
    return list(dict.fromkeys(i.strip() for i in value if i.strip()))


def validate_settings(data):
    if type(data.get('enabled')) is not bool:
        raise ValueError('Choisissez si la préparation hebdomadaire est active.')
    tz = data.get('timezone', DEFAULTS['timezone'])
    try:
        ZoneInfo(tz)
    except (ValueError, TypeError, ZoneInfoNotFoundError) as e:
        raise ValueError('Choisissez un fuseau horaire valide.') from e
    at = data.get('at')
    if not isinstance(at, str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', at):
        raise ValueError('Indiquez l’heure de préparation.')
    meals = data.get('meals')
    days = day_list(data.get('days'))
    if not isinstance(meals, list) or not meals or any(meal not in ('lunch', 'dinner') for meal in meals) or not days:
        raise ValueError('Prévoyez au moins un repas dans la semaine.')
    diet = data.get('diet', 'any')
    if diet not in ('any', 'vegetarian', 'vegan'):
        raise ValueError('Choisissez un régime alimentaire.')
    kcal = data.get('daily_kcal')
    return {'enabled':data['enabled'], 'day':integer(data.get('day'), 0, 6, 'Choisissez le jour de préparation.'),
            'at':at, 'timezone':tz, 'people':integer(data.get('people'), 1, 12, 'Indiquez entre 1 et 12 personnes.'),
            'meals':[meal for meal in ('lunch','dinner') if meal in meals], 'days':days,
            'portable':day_list(data.get('portable', [])), 'no_cook':day_list(data.get('no_cook', [])),
            'cook_days':integer(data.get('cook_days'), 1, 7, 'Choisissez de 1 à 7 jours de cuisine.'),
            'diet':diet, 'exclude':labels(data.get('exclude', [])), 'pantry':labels(data.get('pantry', [])),
            'daily_kcal':integer(kcal, 500, 5000, 'Indiquez votre objectif calorique ou laissez-le vide.') if kcal is not None else None}


def save_settings(data):
    config = validate_settings(data)
    with D.db() as c:
        old = settings(c)
        if data.get('version') != old['version']:
            raise ValueError('Les réglages ont changé. Actualisez cette page.')
        return D.put(c, 'weekly_settings', 'main', config, old['version'])


def next_schedule(now, config):
    local = now.astimezone(ZoneInfo(config['timezone']))
    monday = local.date() + timedelta(days=7 - local.weekday())
    preparation_day = monday - timedelta(days=7 - config['day'])
    planned = datetime.combine(preparation_day, clock_time.fromisoformat(config['at']), local.tzinfo)
    return monday.isoformat(), planned


def due_week(now, config):
    week, planned = next_schedule(now, config)
    return week if config['enabled'] and now >= planned else None


def overview(c, week, now):
    config = settings(c)
    upcoming, planned = next_schedule(now, config)
    if now >= planned:
        _, planned = next_schedule(now + timedelta(days=7), config)
    recent = c.execute("""SELECT id FROM docs WHERE kind='weekly' AND id>=?
        AND id<=?
        AND json_extract(data,'$.status')='ready' AND json_extract(data,'$.seen') IS NOT 1
        AND json_extract(data,'$.revision') IS NOT 1
        ORDER BY id DESC LIMIT 1""", ((now.date()-timedelta(days=7)).isoformat(),upcoming)).fetchone()
    return {'weekly':public(D.get(c,'weekly',week)), 'weekly_settings':config,
            'weekly_upcoming':upcoming, 'weekly_next':planned.isoformat() if config['enabled'] else None,
            'weekly_notice':public(D.get(c,'weekly',recent['id'])) if recent else None}


def slot_keys(config):
    return [(day, meal) for day in config['days'] for meal in config['meals']]


def recipe_features(recipe):
    ingredients = [normalized(item['name']) for item in recipe.get('ingredients', [])]
    title = normalized(recipe['title'])
    tags = {normalized(tag) for tag in recipe.get('tags', [])}
    combined = ' · '.join(ingredients)
    meat, fish = bool(MEAT.search(combined)), bool(FISH.search(combined))
    vegetarian = not (meat or fish) and (bool(ingredients) or bool({'vegetarien','vegetalien','vegan'} & tags))
    vegan = vegetarian and not DAIRY_EGG.search(combined) and (bool(ingredients) or bool({'vegetalien','vegan'} & tags))
    planning = recipe.get('planning') or {}
    portable = recipe['id'].startswith(('wrap-','burritos-')) or bool({'a preparer en avance','a emporter'} & tags)
    return {'vegetarian':vegetarian, 'vegan':vegan, 'fish':fish, 'active_minutes':planning.get('active_minutes'),
            'total_minutes':planning.get('total_minutes'), 'equipment':planning.get('equipment',[]),
            'portable':planning.get('portable', PORTABLE.get(recipe['id'],portable)),
            'legumes':bool(LEGUMES.search(combined)), 'vegetables':sum(bool(VEGETABLE.search(item)) for item in ingredients),
            'whole_grain':bool(WHOLE_GRAIN.search(combined)),
            'protein': ('poisson' if fish else 'volaille' if re.search(r'poulet|dinde', combined) else
                        'viande' if meat else 'tofu' if 'tofu' in combined else 'légumineuses' if LEGUMES.search(combined)
                         else 'œufs' if 'oeuf' in combined else 'laitages' if DAIRY_EGG.search(combined) else 'inconnue'),
            'family': next((name for name in ('pizza','burrito','wrap','risotto','soupe') if name in title), recipe['id'])}


def allowed(recipe, config):
    fields = [normalized(recipe['title']), *(normalized(i['name']) for i in recipe.get('ingredients', []))]
    for exclusion in config['exclude']:
        term = normalized(exclusion)
        if term in ('fruit','fruits'):
            if any(FRUIT.search(field) for field in fields):
                return False
            continue
        variants = {term,term.rstrip('s'),term.rstrip('s')+'s'} if term else set()
        if any(f' {alias} ' in f' {field} ' for alias in variants for field in fields):
            return False
    return config['diet'] == 'any' or recipe_features(recipe)[config['diet']]


def assess(plan, config):
    cook = set()
    energy = {}
    portable_misses = []
    repeated = Counter()
    proteins = Counter()
    cooking_minutes = Counter()
    unknown_cooking_time = 0
    frozen = legumes = vegetables = whole_grain = known = 0
    for slot in batch.ordered(plan['slots']):
        recipe = slot['recipe']
        features = recipe_features(recipe)
        if not allowed(recipe, config):
            raise ValueError(f'Plat incompatible avec les exclusions ou le régime : {recipe["title"]}.')
        repeated[features['family']] += 1
        if features['protein'] != 'inconnue':
            proteins[features['protein']] += 1
        legumes += features['legumes']
        vegetables += features['vegetables'] >= 2
        whole_grain += features['whole_grain']
        if slot['meal'] == 'lunch' and slot['day'] in config['portable'] and not features['portable']:
            portable_misses.append(slot['day'])
        task = plan.get('batch', {}).get(batch.key(slot), {})
        if task.get('source') in batch.ACTIVE_SOURCES:
            frozen += 1
        else:
            cook.add(slot['day'])
            active_minutes = features['active_minutes']
            if active_minutes:
                portions=task.get('quantity',slot['servings']) / recipe['servings']
                cooking_minutes[slot['day']] += round(active_minutes * (.55 + .45*portions))
            else:
                unknown_cooking_time += 1
        calories = (recipe.get('nutrition') or {}).get('kcal')
        if calories is not None:
            known += 1
        energy.setdefault(slot['day'], []).append(calories)
    warnings = []
    missing = len(plan['slots']) - known
    over = max(0, len(cook) - config['cook_days'])
    if over: warnings.append(f'{len(cook)} jours de cuisine prévus pour un objectif de {config["cook_days"]}.')
    if missing: warnings.append(f'Calories incomplètes pour {missing} repas.')
    target = config['daily_kcal']
    # Even two planned meals do not establish everything a person will eat that day.
    totals = {day:round(sum(kcals)) for day,kcals in energy.items() if all(kcal is not None for kcal in kcals)}
    light_days = [day for day,kcal in totals.items() if target and len(energy[day]) >= 2 and kcal < target*.75]
    if light_days: warnings.append(f'{len(light_days)} jour(s) sous 75 % de votre objectif avec les seuls repas prévus.')
    if portable_misses:
        warnings.append(f'{len(portable_misses)} déjeuner(s) à emporter à vérifier.')
    banned = sorted(cook & set(config['no_cook']))
    if banned:
        warnings.append(f'{len(banned)} jour(s) de cuisine sans disponibilité prévue.')
    score = (len(banned)*200 + len(portable_misses)*45 + over*10 + len(cook)*4
             + sum(max(0, count-2)**2*2 for count in repeated.values()) + len(light_days)*3
             + missing*1.4 + (sum(cooking_minutes.values())+25*unknown_cooking_time)*.025
             + sum(max(0,minutes-55) for minutes in cooking_minutes.values())*.12
             - min(len(proteins), 4)*3 - min(legumes, 4)*1.5 - vegetables - whole_grain*.8)
    return {'score':round(score,2),'cook_days':sorted(cook),'frozen_meals':frozen,'legume_meals':legumes,
            'vegetable_meals':vegetables,'whole_grain_meals':whole_grain,'protein_sources':list(proteins),
            'active_minutes':sum(cooking_minutes.values()) if not unknown_cooking_time else None,
            'nutrition_known':known,'daily_kcal':totals,'portable_misses':portable_misses,
            'no_cook_misses':banned,'warnings':warnings}


def context(c, job):
    week, config = job['id'], job['settings']
    catalog = [D.get(c, 'recipe', row[0]) for row in c.execute("SELECT id FROM docs WHERE kind='recipe' ORDER BY id")]
    freezer = batch.planning_context(c, week, job['batch_settings'])
    recipes = {recipe['id']:recipe for recipe in catalog}
    recipes.update({lot['recipe']['id']:lot['recipe'] for lot in freezer['lots'] if lot['recipe']['id'] not in recipes})
    previous = D.get(c, 'week', (datetime.fromisoformat(week).date()-timedelta(days=7)).isoformat())
    return {'week':week,'household':config,'preferences':D.get(c,'preferences','main'),
            'learning':D.get(c,'learning','planner')['text'],
            'slots':[{'day':day,'meal':meal,'servings':config['people']} for day,meal in slot_keys(config)],
            'freezer':{'settings':job['batch_settings'],'available_portions':freezer['available_portions'],
                       'automatic_portions':freezer['automatic_portions'],
                       'lots':[{'recipe_id':lot['recipe']['id'],'title':lot['recipe']['title'],
                                'available':lot['available'],'frozen_on':lot['frozen_on']} for lot in freezer['lots']]},
            'last_week':list(dict.fromkeys(slot['recipe_id'] for slot in (previous or {}).get('slots', []))),
            'recipes':[{'id':r['id'],'title':r['title'],'freezer_ok':r.get('freezer_ok',False),
                        'freezer_only':r.get('freezer_only',False),'ingredients':[i['name'] for i in r['ingredients']],
                        'nutrition':r.get('nutrition',{}),**recipe_features(r)}
                       for r in recipes.values() if allowed(r,config)]}


def request(c, week, version=None, auto=False):
    week = D.week_id(week)
    previous = D.get(c,'weekly',week)
    if previous and (auto or previous['status'] in ACTIVE):
        return previous
    w = D.get(c,'week',week) or D.blank_week(week)
    if version is not None and w['version'] != version:
        raise ValueError('La semaine a changé. Actualisez avant de continuer.')
    if w['approved']:
        if auto: return None
        raise ValueError('Cette semaine est déjà validée.')
    config = settings(c)
    prefs = D.get(c,'preferences','main')
    batch_config = batch.settings(prefs)
    if not prefs.get('batch'):
        batch_config['enabled'] = True
    batch_config['prefer_frozen_days'] = config['no_cook']
    job = {'request_id':D.uid(),'status':'queued','base_version':w['version'],
           'settings':{k:config[k] for k in DEFAULTS},'batch_settings':batch_config,
           'origin':'existing' if w['slots'] else 'hermes','created':time.time(),'auto':auto,'error':''}
    # Keep the cook/freezer mode the owner has already chosen.
    return D.put(c,'weekly',week,job,(previous or {}).get('version',0))


def owner_request(week, version):
    with D.db() as c:
        return public(request(c,week,version))


def public(job):
    if not job:
        return None
    fields = ('id','version','status','origin','created','finished','error','quality','retailer','seen','plan_run','cart_run')
    return {field:job[field] for field in fields if field in job}


def ensure_phase(c, week, request_id, phase):
    job = D.get(c,'weekly',D.week_id(week))
    if not job or job['request_id'] != request_id or job['status'] != phase:
        raise ValueError('Cette préparation n’est plus active.')
    w = D.get(c,'week',week) or D.blank_week(week)
    target = job.get('draft_version', job['base_version'])
    if w['version'] != target or w['approved']:
        raise ValueError('Le planning a été modifié pendant la préparation.')
    return job,w


def candidate(c, job, w, slots):
    config = job['settings']
    expected = set(slot_keys(config))
    if (not isinstance(slots,list) or len(slots) != len(expected) or any(
            not isinstance(s,dict) or type(s.get('day')) is not int or
            (s['day'],s.get('meal')) not in expected or type(s.get('servings')) is not int or
            s['servings'] != config['people'] or s.get('freezer_lot_id')
            for s in slots)):
        raise ValueError('Utilisez chaque créneau demandé exactement une fois avec le nombre de personnes prévu.')
    draft, _, _ = D.compose_week(c,job['id'],{'slots':slots},w,job['batch_settings'])
    return draft, assess(draft,config)


def propose(week, request_id, plans):
    if not isinstance(plans,list) or not 1 <= len(plans) <= 6:
        raise ValueError('Envoyez entre une et six propositions distinctes.')
    with D.db() as c:
        job,w = ensure_phase(c,week,request_id,'planning')
        results=[]
        for option in plans:
            try:
                draft, quality = candidate(c,job,w,option['slots'])
            except (ValueError, TypeError, KeyError) as error:
                results.append({'error':str(error)})
                continue
            results.append(quality)
            if not job.get('proposal') or quality['score'] < job['proposal']['quality']['score']:
                job['proposal']={'week':draft,'quality':quality,'note':str(option.get('note',''))[:1000]}
        D.put(c,'weekly',week,job,job['version'])
        return {'accepted':bool(job.get('proposal')),'reviews':results,
                'best':job['proposal']['quality'] if job.get('proposal') else None}


def fallback(c, job, w):
    """Try different cooking days and recipe rotations. A failed AI run must still respect hard exclusions."""
    config = job['settings']
    facts = context(c,job)
    pool = [r for r in facts['recipes'] if not r['freezer_only']]
    if not pool:
        raise ValueError('Aucune recette du carnet ne respecte les exclusions de votre foyer.')
    pool.sort(key=lambda r:(r['id'] in facts['last_week'], not r['nutrition'].get('kcal'),
                            not r['freezer_ok'], not r['legumes'], -r['vegetables'], r['id']))
    slots = slot_keys(config)
    starting_days = [day for day in config['days'] if day not in config['no_cook']] or config['days']
    candidate_days = list(itertools.combinations(starting_days,min(len(starting_days),config['cook_days'])))[:12]
    best = None
    for offset in range(min(len(pool),8)):
        for days in candidate_days:
            chosen=[]
            used=Counter()
            for day,meal in slots:
                portable = meal=='lunch' and day in config['portable']
                eligible = [r for r in pool if not portable or r['portable']] or pool
                if day not in days:
                    reusable=[p for p in chosen if p['day'] < day and p['recipe_id'] in {r['id'] for r in eligible if r['freezer_ok']}
                              and used[p['recipe_id']] < 3]
                else:
                    reusable=[]
                if reusable:
                    recipe_id=min(reusable,key=lambda p:used[p['recipe_id']])['recipe_id']
                else:
                    staggered=eligible[offset%len(eligible):]+eligible[:offset%len(eligible)]
                    recipe_id=min(staggered,key=lambda r:used[r['id']]*4 + (not r['freezer_ok'])*2 + (r['id'] in facts['last_week']))['id']
                chosen.append({'day':day,'meal':meal,'servings':config['people'],'recipe_id':recipe_id});used[recipe_id]+=1
            draft,quality=candidate(c,job,w,chosen)
            if not best or quality['score'] < best['quality']['score']:
                best={'week':draft,'quality':quality,'note':''}
    return best


def grocery_signature(item):
    return (normalized(item['name']), item['unit'].strip().casefold(), item['quantity'],item.get('edible_grams'))


def make_groceries(w, config, originals=()):
    pantry = {normalized(item) for item in config['pantry']}
    items = D.aggregate(w)
    by_signature = {grocery_signature(item):item for item in originals}
    for item in items:
        old = by_signature.get(grocery_signature(item))
        if old:
            item.update({field:old[field] for field in ('id','checked','note')})
        elif normalized(item['name']) in pantry:
            item['checked']=True
            item['note']='Déjà en réserve selon vos réglages.'
    return {'approved':False,'items':items}


def revise(c, old, draft):
    """Keep exact matches when the owner revises a drafted menu."""
    week=old['id']
    previous=D.get(c,'weekly',week)
    if not previous or previous['request_id']!=old.get('weekly_prepared'):
        return D.put(c,'week',week,draft,old['version'])
    if not draft['slots'] or (old.get('cart') or {}).get('fill_job_id'):
        previous.update(status='superseded',error='Le planning a été repris manuellement.')
        D.put(c,'weekly',week,previous,previous['version'])
        return D.put(c,'week',week,draft,old['version'])
    config=previous['settings']
    try:
        quality=assess(draft,config)
    except ValueError as error:
        quality={'warnings':[str(error)]}
    draft['groceries']=make_groceries(draft,config,(old.get('groceries') or {}).get('items',[]))
    prior_cart=old.get('cart') or {}
    required=set(cart_review.required(draft))
    if prior_cart.get('weekly_preview'):
        matches=[m for m in prior_cart['matches'] if m['grocery_id'] in required]
        draft['cart']={**prior_cart,'matches':matches,'unmatched':sorted(required-{m['grocery_id'] for m in matches}),
                       'excluded':[],'status':'proposed'}
    request_id=D.uid()
    draft['weekly_prepared']=request_id
    draft=D.put(c,'week',week,draft,old['version'])
    D.put(c,'weekly',week,{'request_id':request_id,'status':'shopping','origin':'existing','settings':config,
                           'base_version':draft['version'],'draft_version':draft['version'],'quality':quality,
                           'revision':True,'seen':True,'created':time.time(),'error':''},previous['version'])
    return draft


def publish_plan(c, job, w):
    if job['origin']=='existing':
        draft={**w}
        try:
            quality=assess(draft,job['settings'])
        except ValueError as error:
            quality={'warnings':[str(error)]}
        note=''
    else:
        proposal=job.get('proposal')
        quality=(proposal or {}).get('quality',{})
        if (not proposal or quality['no_cook_misses'] or quality['portable_misses'] or
                len(quality['cook_days']) > job['settings']['cook_days']):
            backup=fallback(c,job,w)
            if not proposal or backup['quality']['score'] < quality['score']:
                proposal=backup
                job['origin']='fallback'
        draft,quality,note=proposal['week'],proposal['quality'],proposal['note']
    draft['weekly_prepared']=job['request_id']
    draft['groceries']=make_groceries(draft,job['settings'])
    draft['cart']=None
    draft=D.put(c,'week',job['id'],draft,w['version'])
    job.update(status='shopping',draft_version=draft['version'], quality=quality, note=note)
    job.pop('proposal',None)
    return D.put(c,'weekly',job['id'],job,job['version'])


def validate_matches(matches):
    if not isinstance(matches,list) or len(matches)>60:
        raise ValueError('Proposez au maximum 60 produits à la fois.')
    result = []
    rows = set()
    for match in matches:
        if (not isinstance(match,dict) or not isinstance(match.get('grocery_id'),str) or not match.get('productId')
                or type(match.get('quantity')) is not int or not 0 < match['quantity'] <= 100):
            raise ValueError('Référence ou quantité de paquets invalide.')
        if match['grocery_id'] in rows:
            raise ValueError('Proposez une seule référence par ingrédient.')
        rows.add(match['grocery_id'])
        result.append({'grocery_id':match['grocery_id'],'productId':product_id(match['productId']),
                       'quantity':match['quantity']})
    return result


def save_products(c, job, w, matches, products, identity):
    items = cart_review.required(w)
    canonical = {product['productId']:product for product in products if product.get('name') and
                 not product.get('unavailable') and product.get('stock') not in ('NO_STOCK','DISCONTINUED')}
    previous = w.get('cart') or {}
    selection = {m['grocery_id']:m for m in previous.get('matches',[])
                 if previous.get('retailer_identity')==identity and m['grocery_id'] in items}
    rejected = []
    for match in matches:
        key = match['grocery_id']
        if key not in items:
            raise ValueError('Un ingrédient sélectionné ne figure plus dans les courses.')
        product = canonical.get(match['productId'])
        quantity = quantity_for(items[key],product,match['quantity']) if product else None
        if quantity is None:
            rejected.append(items[key]['name'])
            continue
        if product.get('remainingStock') and quantity['quantity'] > product['remainingStock']:
            rejected.append(items[key]['name'])
            continue
        selection[key] = {**match, **product, **quantity}
    unmatched = sorted(set(items) - set(selection))
    w['cart'] = {'matches':list(selection.values()),'unmatched':unmatched,'excluded':[],
                 'status':'proposed','weekly_preview':True,'retailer_identity':identity}
    w = D.put(c,'week',job['id'],w,w['version'])
    job['draft_version'] = w['version']
    job['retailer'] = {'matched':len(selection),'unmatched':len(unmatched),
                       'quantities_to_verify':sum(not m.get('verified_quantity') for m in selection.values())}
    D.put(c,'weekly',job['id'],job,job['version'])
    return {**job['retailer'], 'rejected':rejected,
            'remaining':[{'id':key,'name':items[key]['name']} for key in unmatched]}


def propose_products(week,request_id,matches,products,identity):
    with D.db() as c:
        job,w = ensure_phase(c,week,request_id,'matching')
        return save_products(c,job,w,matches,products,identity)


def mark_seen(week):
    with D.db() as c:
        job=D.get(c,'weekly',D.week_id(week))
        if job and job['status']=='ready' and not job.get('seen'):
            job['seen']=True
            return public(D.put(c,'weekly',week,job,job['version']))
        return public(job)


def queue_step(c, job, role, status, now):
    key='plan_run' if role=='planner' else 'cart_run'
    busy=c.execute("SELECT 1 FROM runs WHERE role=? AND status IN ('submitting','running','queued','waiting_for_approval')",(role,)).fetchone()
    if busy: return None
    job.update({key:D.uid(),'status':status,'phase_at':now})
    job=D.put(c,'weekly',job['id'],job,job['version'])
    return job


def ready(c,job):
    job.update(status='ready',finished=time.time())
    D.put(c,'weekly',job['id'],job,job['version'])


def plan_prompt(job):
    return f"""Préparation automatique de la semaine du {job['id']}. Requête : {job['request_id']}.
Utilise weekly_context avec week et request_id. Crée deux ou trois menus pratiques et différents, puis appelle propose_weekly avec week, request_id et plans.
Les plats doivent exister dans le carnet. Tous les créneaux et portions du foyer doivent être remplis. Lis les préférences libres.
Privilégie des déjeuners qui se transportent, évite de cuisiner les jours exclus, et regroupe les plats qui peuvent se congeler.
Répète volontairement un même plat à quelques jours d’intervalle pour cuire une seule fois. Utilise les plats réellement présents au congélateur sans vider le stock.
Vise une assiette équilibrée : légumes, une source de protéines, des féculents selon l’appétit. Alterne légumes secs, tofu, volaille et poisson selon le régime. Une entrée ou une pizza seule ne suffisent pas forcément.
Utilise uniquement les valeurs nutritionnelles enregistrées. Évite plusieurs journées trop légères d’affilée. Une valeur inconnue reste inconnue.
Le moteur recalcule les jours de cuisine de chaque option. Lis les retours et corrige si un jour sans cuisine nécessite encore de cuisiner. Enregistre seulement avec propose_weekly. Surtout pas save_week, pas d’approbation et pas de modification des recettes ou réserves."""


def cart_prompt(job):
    return f"""Prépare la sélection Chronodrive en brouillon pour la semaine {job['id']} et la requête {job['request_id']}.
Appelle weekly_groceries avec week et request_id. Utilise les quantités déjà agrégées et ignore les ingrédients cochés. Cherche via search_products_batch, avec des noms courts et simples en français. Réessaie les recherches vides avec un mot-clé plus simple.
Pour un besoin égoutté, sélectionne un article dont le résultat porte le champ drained, vérifié par code-barres. Évite les plats préparés, les sauces et les mélanges aromatisés pour un ingrédient nature. Pour les légumes, privilégie le produit brut du bon type, sans sauce. Pour la viande et le poisson, respecte frais/surgelé et la découpe prévus.
Vérifie le format, unité, poids égoutté si pertinent, et la quantité de paquets pour chaque ingrédient. Respecte les préférences. Si une correspondance est douteuse, laisse l’ingrédient sans choix. N’ajoute rien au panier.
Enregistre le brouillon avec propose_weekly_products (week, request_id, matches). Une seule référence par ingrédient. Donne l’identifiant exact et une quantité entière de paquets. Table compare le format détaillé aux quantités et renvoie les lignes non résolues. Corrige les quelques lignes rejetées si une alternative vérifiée existe, en enregistrant seulement les nouveaux choix. Le propriétaire relira la sélection."""


def advance(c, job, connected, now):
    w=D.get(c,'week',job['id']) or D.blank_week(job['id'])
    if w['approved'] or w['version']!=job.get('draft_version',job['base_version']):
        job.update(status='superseded',error='Le planning a été repris manuellement.')
        D.put(c,'weekly',job['id'],job,job['version'])
        return None
    if job['status']=='queued':
        if job['origin']=='existing':
            publish_plan(c,job,w)
            return None
        queued=queue_step(c,job,'planner','planning',now)
        return (queued,'planner') if queued else None
    if job['status']=='shopping':
        if not connected or not cart_review.missing(w):
            if w.get('cart'):
                selected=w['cart']['matches']
                job['retailer']={'matched':len(selected),'unmatched':len(cart_review.missing(w)),
                                 'quantities_to_verify':sum(not match.get('verified_quantity') for match in selected)}
            ready(c,job)
            return None
        queued=queue_step(c,job,'cart','matching',now)
        return (queued,'cart') if queued else None
    role = 'planner' if job['status']=='planning' else 'cart'
    run_id=job['plan_run' if role=='planner' else 'cart_run']
    run=c.execute("SELECT status FROM runs WHERE id=?",(run_id,)).fetchone()
    if not run:
        busy=c.execute("SELECT 1 FROM runs WHERE role=? AND status IN ('submitting','running','queued','waiting_for_approval')",(role,)).fetchone()
        return (job,role) if not busy else None
    timed_out=now-job['phase_at']>LIMIT_SECONDS
    if run['status'] in ACTIVE_RUN and not timed_out:
        return None
    if role=='planner':
        publish_plan(c,job,w)
    else:
        if not job.get('retailer'):
            job['error']='La recherche de produits reste à faire. Votre menu et vos courses sont prêts.'
        ready(c,job)
    return None


async def tick(submit, connected, now=None):
    now=now or datetime.now(ZoneInfo('UTC'))
    epoch=now.timestamp()
    work=[]
    with D.db() as c:
        due=due_week(now,settings(c))
        if due:
            request(c,due,auto=True)
        keys=c.execute("SELECT id FROM docs WHERE kind='weekly' AND json_extract(data,'$.status') IN ('queued','planning','shopping','matching') ORDER BY id").fetchall()
    for (key,) in keys:
        with D.db() as c:
            job=D.get(c,'weekly',key)
            if not job or job['status'] not in ACTIVE: continue
            try:
                action=advance(c,job,connected(),epoch)
                if action: work.append(action)
            except ValueError as e:
                job.update(status='needs_attention',error=str(e), finished=time.time())
                D.put(c,'weekly',key,job)
    for job,role in work:
        try:
            await submit(role,job['id'],plan_prompt(job) if role=='planner' else cart_prompt(job),
                         run_id=job['plan_run' if role=='planner' else 'cart_run'], automated=True)
        except Exception:
            LOG.info('Weekly %s handoff delayed for %s',role,job['id'])


async def loop(submit, connected, notify=None):
    while True:
        try:
            await tick(submit,connected)
            if notify:
                await notify()
        except Exception:
            LOG.exception('Weekly preparation tick failed')
        await asyncio.sleep(5)
