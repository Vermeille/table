"""Freezer inventory, reservations and batch quantities for Table's weekly plans."""
from collections import Counter, defaultdict
from datetime import date

import domain as D

MEAL_ORDER = {'breakfast': 0, 'lunch': 1, 'dinner': 2}
DEFAULT_SETTINGS = {'enabled': False, 'reserve': 4, 'extra_per_day': 4}

# Seed recipes whose complete cooked dish holds up well in the freezer.
SEED_NOTES = {
    'red-lentil-dal': 'Congeler le dahl cuit en portions individuelles. Mélanger pendant le réchauffage.',
    'tomato-butter-beans': 'Congeler les haricots avec leur sauce tomate en portions individuelles.',
    'mushroom-barley-soup': 'Congeler la soupe en portions. L’orge s’attendrit et épaissit le bouillon.',
}
ACTIVE_SOURCES = {'stock', 'batch'}


def mark_seed_recipes(seeds):
    """Apply curated defaults only to untouched recipes, preserving existing snapshots."""
    changed = []
    with D.db() as c:
        if D.get(c, 'migration', 'freezer-seed-v1'):
            return
        for seed in seeds:
            note = SEED_NOTES.get(seed['id'])
            recipe = D.get(c, 'recipe', seed['id'])
            if (note and recipe and 'freezer_ok' not in recipe
                    and recipe['method'] == seed['method']
                    and [{field: item[field] for field in ('name', 'quantity', 'unit')} for item in recipe['ingredients']] == seed['ingredients']):
                recipe.update(freezer_ok=True, freezer_note=note)
                changed.append(D.put(c, 'recipe', recipe['id'], recipe, recipe['version']))
        D.put(c, 'migration', 'freezer-seed-v1', {})
    for recipe in changed:
        D.write_markdown(recipe)


def settings(preferences):
    saved = (preferences or {}).get('batch')
    return {**DEFAULT_SETTINGS, **(saved if isinstance(saved, dict) else {})}


def normalize_settings(raw):
    if not isinstance(raw, dict) or type(raw.get('enabled')) is not bool:
        raise ValueError('Choisissez si la cuisine en lots est activée.')
    return {'enabled': raw['enabled'],
            'reserve': portions(raw.get('reserve', 4), maximum=100),
            'extra_per_day': portions(raw.get('extra_per_day', 4), minimum=1, maximum=24)}


def portions(value, minimum=0, maximum=100):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'Indiquez un nombre entier de portions entre {minimum} et {maximum}.')
    return value


def key(slot):
    return f"{slot['day']}-{slot['meal']}"


def ordered(slots):
    return sorted(slots, key=lambda slot: (slot['day'], MEAL_ORDER[slot['meal']]))


def freezer(c):
    return D.get(c, 'freezer', 'main') or {'id': 'main', 'version': 0, 'lots': []}


def kitchen(c, week):
    return D.get(c, 'kitchen', week) or {'id': week, 'version': 0, 'entries': {}}


def reservations(c, exclude_week=None):
    """Outstanding claims on confirmed inventory, including lots not yet cooked."""
    result = defaultdict(list)
    rows = c.execute("""SELECT id FROM docs WHERE kind='week'
        AND json_extract(data, '$.approved') AND json_type(data, '$.batch')='object'
        ORDER BY id""").fetchall()
    for row in rows:
        week = row['id']
        if week == exclude_week:
            continue
        plan = D.get(c, 'week', week)
        entries = kitchen(c, week)['entries']
        for slot in ordered(plan['slots']):
            slot_key = key(slot)
            if slot_key in entries:
                continue
            task = plan['batch'].get(slot_key, {})
            for allocation in task.get('lots', []):
                result[allocation['id']].append({
                    'week': week, 'slot': slot_key, 'quantity': allocation['quantity'],
                })
    return result


def inventory(c, week=None):
    stock = freezer(c)
    claims = reservations(c)
    return {**stock, 'lots': [
        {**lot, 'reserved': sum(claim['quantity'] for claim in claims[lot['id']]),
         'available': max(0, lot['quantity'] - sum(claim['quantity'] for claim in claims[lot['id']]
                                                 if claim['week'] != week)),
         'claims': claims[lot['id']]}
        for lot in stock['lots'] if lot['quantity'] > 0
    ]}


def planning_context(c, week, config=None):
    config = config if config is not None else settings(D.get(c, 'preferences', 'main'))
    stock = inventory(c, week)
    total = sum(lot['available'] for lot in stock['lots'])
    automatic = min(total // 2, max(0, total - (config['reserve'] + 1) // 2)) if config['enabled'] else 0
    return {'settings': config, 'available_portions': total, 'automatic_portions': automatic,
            'lots': [{'id': lot['id'], 'recipe': lot['recipe'], 'available': lot['available'],
                      'frozen_on': lot['frozen_on']} for lot in stock['lots'] if lot['available']],
            'recorded_actions': kitchen(c, week)['entries'] if week else {}}


def lot_date(value):
    try:
        day = date.fromisoformat(value)
    except (ValueError, TypeError):
        raise ValueError('Indiquez la date de congélation.') from None
    if day > date.today():
        raise ValueError('La date de congélation doit être aujourd’hui ou passée.')
    return day.isoformat()


def save_lot(data):
    with D.db() as c:
        stock = freezer(c)
        if data.get('version') != stock['version']:
            raise ValueError('Le congélateur a changé. Actualisez avant de le modifier.')
        lot_id = data.get('id')
        quantity = portions(data.get('quantity'), minimum=0 if lot_id else 1)
        frozen_on = lot_date(data.get('frozen_on'))
        note = str(data.get('note', '')).strip()[:500]
        if lot_id:
            lot = next((item for item in stock['lots'] if item['id'] == lot_id), None)
            if not lot:
                raise ValueError('Ce lot est introuvable.')
            claims = reservations(c)[lot_id]
            reserved = sum(claim['quantity'] for claim in claims)
            if quantity < reserved:
                raise ValueError(f'{reserved} portions sont réservées. Retirez d’abord ces repas du planning ou indiquez qu’ils sont annulés.')
            lot.update(quantity=quantity, frozen_on=frozen_on, note=note)
        else:
            recipe_id = data.get('recipe_id')
            recipe = D.get(c, 'recipe', recipe_id) if recipe_id else None
            if recipe_id and not recipe:
                raise ValueError('Cette recette est introuvable.')
            if not recipe:
                title = str(data.get('title', '')).strip()
                if not title or len(title) > 100:
                    raise ValueError('Donnez un nom au plat (100 caractères maximum).')
                recipe = {'id': 'freezer-' + D.uid(), 'title': title, 'servings': 1, 'tags': [],
                          'nutrition': {}, 'ingredients': [], 'method': '', 'freezer_only': True}
            stock['lots'].append({'id': D.uid(), 'recipe': recipe, 'quantity': quantity,
                                  'frozen_on': frozen_on, 'note': note})
        D.put(c, 'freezer', 'main', {'lots': [item for item in stock['lots'] if item['quantity'] > 0]},
              stock['version'])
        return inventory(c)


def find_slot_recipe(c, slot):
    manual = slot.get('freezer_lot_id')
    if manual:
        lot = next((lot for lot in freezer(c)['lots'] if lot['id'] == manual), None)
        if not lot:
            raise ValueError('Ce lot n’est plus au congélateur. Choisissez un autre repas.')
        return lot['recipe']
    recipe_id = slot.get('recipe_id')
    if not isinstance(recipe_id, str):
        raise ValueError('Choisissez une recette ou un plat du congélateur.')
    recipe = D.get(c, 'recipe', recipe_id)
    if not recipe and recipe_id.startswith('freezer-'):
        lot = next((lot for lot in freezer(c)['lots'] if lot['recipe']['id'] == recipe_id), None)
        return lot['recipe'] if lot else None
    return recipe


def whole_servings(slot):
    return int(slot['servings']) if slot['servings'] == int(slot['servings']) else 0


def build(c, week, slots, config, previous, activity):
    """Apply inventory to the selected menu, then batch repeated suitable dishes."""
    stock = sorted(inventory(c, week)['lots'], key=lambda lot: (lot['frozen_on'], lot['id']))
    claims = {lot['id']: lot['available'] for lot in stock}
    by_id = {lot['id']: lot for lot in stock}
    stock_total = sum(claims.values())
    # Use at most half of available stock automatically. Keep at least half of the target.
    budget = min(stock_total // 2, max(0, stock_total - (config['reserve'] + 1) // 2))
    tasks = {}
    ordered_slots = ordered(slots)
    candidates = []

    for slot in ordered_slots:
        slot_key = key(slot)
        if slot_key in activity and activity[slot_key]['action'] != 'skip':
            task = previous['batch'][slot_key]
            tasks[slot_key] = task
        elif slot.get('freezer_lot_id'):
            lot_id = slot['freezer_lot_id']
            quantity = whole_servings(slot)
            if not quantity or claims.get(lot_id, 0) < quantity:
                raise ValueError('Ce lot ne contient pas assez de portions disponibles pour ce repas.')
            tasks[slot_key] = {'source': 'stock', 'lots': [{'id': lot_id, 'quantity': quantity}]}
            claims[lot_id] -= quantity
            budget = min(budget, max(0, sum(claims.values()) - (config['reserve'] + 1) // 2))
        else:
            candidates.append(slot)

    # Match the existing menu first. Mix containers from the same recipe version when needed.
    # Prefer using older lots while giving each cooking day a chance to stay light.
    frozen_days = {slot['day'] for slot in ordered_slots if tasks.get(key(slot), {}).get('source') == 'stock'}
    preferred = set(config.get('prefer_frozen_days',[]))
    if config['enabled']:
        for lot in stock:
            if claims[lot['id']] <= 0:
                continue
            alternatives = [part for part in stock
                            if part['recipe']['id'] == lot['recipe']['id']
                            and part['recipe'].get('version') == lot['recipe'].get('version')]
            if alternatives[0]['id'] != lot['id'] and claims[alternatives[0]['id']] > 0:
                continue
            eligible = [slot for slot in candidates if slot['recipe_id'] == lot['recipe']['id']
                        and not slot.get('cook_fresh') and key(slot) not in tasks]
            eligible.sort(key=lambda slot: (slot['day'] not in preferred, slot['day'] in frozen_days,
                                            slot['day'], MEAL_ORDER[slot['meal']]))
            for slot in eligible:
                quantity = whole_servings(slot)
                if not quantity or quantity > budget or quantity > sum(claims[part['id']] for part in alternatives):
                    continue
                allocations = []
                left = quantity
                for part in alternatives:
                    used = min(left, claims[part['id']])
                    if used:
                        allocations.append({'id': part['id'], 'quantity': used})
                        claims[part['id']] -= used
                        left -= used
                slot['recipe'] = by_id[allocations[0]['id']]['recipe']
                tasks[key(slot)] = {'source': 'stock', 'lots': allocations}
                budget -= quantity
                frozen_days.add(slot['day'])

    extra_used = Counter()
    for slot in candidates:
        slot_key = key(slot)
        if slot_key in tasks:
            continue
        if slot['recipe'].get('freezer_only'):
            raise ValueError('Ce plat existe seulement au congélateur et dépasse le stock disponible pour la proposition. Choisissez un autre repas ou réservez ce lot explicitement.')
        extra = 0
        if config['enabled'] and slot['recipe'].get('freezer_ok') is True and not slot.get('cook_fresh'):
            lot_id = D.uid()
            for later in candidates:
                later_key = key(later)
                if (later['day'] <= slot['day'] or later['recipe_id'] != slot['recipe_id']
                        or later.get('cook_fresh') or later_key in tasks):
                    continue
                quantity = whole_servings(later)
                if quantity and extra_used[slot['day']] + extra + quantity <= config['extra_per_day']:
                    tasks[later_key] = {'source': 'batch', 'from_slot': slot_key,
                                        'lots': [{'id': lot_id, 'quantity': quantity}]}
                    extra += quantity
        if extra:
            extra_used[slot['day']] += extra
        tasks[slot_key] = {'source': 'cook', 'quantity': slot['servings'] + extra, 'freeze': extra}
        if extra:
            tasks[slot_key]['lot_id'] = lot_id

    # Restock only the gap. Add at most one meal's worth per cooking day, across days if needed.
    if config['enabled']:
        deficit = max(0, config['reserve'] - sum(claims.values()))
        topped_up_days = set()
        for slot in candidates:
            task = tasks[key(slot)]
            if (not deficit or task['source'] != 'cook' or slot['day'] in topped_up_days
                    or slot.get('cook_fresh') or slot['recipe'].get('freezer_ok') is not True):
                continue
            extra = min(deficit, whole_servings(slot), config['extra_per_day'] - extra_used[slot['day']])
            if extra:
                task['freeze'] += extra
                task['quantity'] += extra
                if 'lot_id' not in task:
                    task['lot_id'] = D.uid()
                extra_used[slot['day']] += extra
                topped_up_days.add(slot['day'])
                deficit -= extra
    return tasks


def validate_plan(c, w):
    activity = kitchen(c, w['id'])['entries']
    available = {lot['id']: lot['available'] for lot in inventory(c, w['id'])['lots']}
    for slot in ordered(w['slots']):
        slot_key = key(slot)
        task = w.get('batch', {}).get(slot_key, {})
        if slot_key in activity:
            continue
        if task.get('source') == 'cook' and task.get('freeze'):
            available[task['lot_id']] = task['freeze']
        for allocation in task.get('lots', []):
            lot_id = allocation['id']
            if available.get(lot_id, 0) < allocation['quantity']:
                raise ValueError('Le stock a changé. Utilisez « Adapter au congélateur » ou remplacez le repas concerné.')
            available[lot_id] -= allocation['quantity']


def record(week, data):
    """Owner records what actually happened. Plan approval never mutates stock."""
    with D.db() as c:
        w = D.get(c, 'week', D.week_id(week))
        diary = kitchen(c, week)
        if not w or not w['approved'] or w['version'] != data.get('version'):
            raise ValueError('Validez le planning à jour avant de confirmer une action.')
        slot_key = data.get('slot')
        action = data.get('action')
        entries = diary['entries']
        if slot_key in entries:
            if entries[slot_key]['action'] == action:
                return diary
            raise ValueError('Une action a déjà été enregistrée pour ce repas.')
        task = w.get('batch', {}).get(slot_key)
        if not task:
            raise ValueError('Cette action de cuisine est introuvable.')
        stock = freezer(c)
        event = {'action': action, 'date': date.today().isoformat()}
        if action == 'freeze' and task['source'] == 'cook' and task.get('freeze'):
            slot = next(slot for slot in w['slots'] if key(slot) == slot_key)
            quantity = portions(data.get('quantity', task['freeze']))
            lot_id = task['lot_id']
            needed = sum(claim['quantity'] for claim in reservations(c)[lot_id])
            if quantity < needed:
                raise ValueError(f'{needed} portions sont prévues pour des repas suivants. Modifiez ces repas avant de confirmer une quantité inférieure.')
            if quantity:
                stock['lots'].append({'id': lot_id, 'recipe': slot['recipe'], 'quantity': quantity,
                                      'frozen_on': event['date'], 'note': '', 'week': week})
            event['quantity'] = quantity
        elif action in ('take', 'skip') and task['source'] in ACTIVE_SOURCES:
            if action == 'take':
                lots = {lot['id']: lot for lot in stock['lots']}
                for allocation in task['lots']:
                    lot = lots.get(allocation['id'])
                    if not lot or lot['quantity'] < allocation['quantity']:
                        raise ValueError('Les portions ne sont pas encore au congélateur. Confirmez la cuisson ou adaptez le repas.')
                    lot['quantity'] -= allocation['quantity']
            event['quantity'] = sum(allocation['quantity'] for allocation in task['lots'])
        else:
            raise ValueError('Cette action ne correspond pas au repas planifié.')
        if action != 'skip':
            D.put(c, 'freezer', 'main', {'lots': [lot for lot in stock['lots'] if lot['quantity'] > 0]},
                  stock['version'])
        entries[slot_key] = event
        return D.put(c, 'kitchen', week, diary, diary['version'])
