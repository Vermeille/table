"""Calculate recipe nutrition from an attributable, local Ciqual snapshot."""
from functools import lru_cache
import json
import math
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).parent
MACROS = ('kcal', 'protein_g', 'carbs_g', 'fat_g')
SOURCE = {'name': 'Anses · Ciqual 2025', 'url': 'https://doi.org/10.57745/RDMHWY'}
MASS = {'mg': .001, 'g': 1, 'kg': 1000}
VOLUME = {'ml': 1, 'cl': 10, 'l': 1000}
OLIVE_DENSITY_SOURCE = 'https://www.fao.org/fao-who-codexalimentarius/sh-proxy/en/?lnk=1&url=https%3A%2F%2Fworkspace.fao.org%2Fsites%2Fcodex%2FStandards%2FCXS+33-1981%2FCXS_033f.pdf'
USDA_SOURCE = {'name': 'USDA · FoodData Central', 'url': 'https://fdc.nal.usda.gov/download-datasets/'}
REFERENCE_WEIGHTS = {
    'lemon_juice': ('2007', 'pièce', 48, '167747', 'Jus d’un citron entier'),
    'half_lemon_juice': ('2007', 'pièce', 24, '167747', 'La moitié du jus d’un citron'),
    'lime_juice': ('2030', 'pièce', 44, '168156', 'Jus d’un citron vert entier'),
    'garlic_clove': ('11000', 'gousse', 3, '169230', 'Une gousse d’ail'),
    'canned_coconut_milk': ('18041', 'ml', 226 / 236.5882, '170173', 'Lait de coco en conserve'),
    'worcestershire': ('fdc-171610', 'ml', 17 / 14.78676, '171610', 'Sauce Worcestershire liquide'),
}


def fdc_url(fdc_id):
    return f'https://fdc.nal.usda.gov/food-details/{fdc_id}/nutrients'

# Reviewed against the ingredients and method of the unmodified starter recipes.
# An unmatched line still appears in shopping and is flagged in the recipe.
SEED_FOODS = {
    'margherita-pizza': [37001, 20260, 19590, 11033, 17270],
    'lemon-chickpea-bowl': [20507, 9681, 20019, 20276, 2007, 17270, 12066],
    'roast-salmon-potatoes': [26036, 4008, 20057, 2007, 17270],
    'red-lentil-dal': [20535, 18041, 20169, 20034, 11074, 11005, 9100, 17270],
    'chicken-pepper-traybake': [36017, 20041, 4008, 20238, 17270, 11049],
    'spinach-ricotta-pasta': [9810, 20059, 19585, 2007, 12120, 17270],
    'black-bean-tacos': [None, None, 13004, 20276, 2030, 11042],
    'mushroom-barley-soup': [20056, 9321, 20009, 20034, 25948, 17270],
    'tomato-butter-beans': [20502, 20169, 20034, 20059, 12066, 17270, 7001],
    'courgette-pea-risotto': [9100, 20020, 20072, 20034, 25948, 12120, 17270],
}
# These aliases specify preparation state where it materially changes the result.
ALIASES = {'lentilles corail seches': '20535', 'lentilles corail cuites': '20589',
           'riz blanc cru': '9100', 'riz blanc cuit': '9104',
           'huile d olive': '17270', 'huile d olive vierge extra': '17270',
           'lait de coco': '18041', 'parmesan': '12120', 'ricotta': '19585'}


def normalized(text):
    without_accents = unicodedata.normalize('NFKD', text.casefold()).encode('ascii', 'ignore').decode()
    return ' '.join(re.findall(r'[a-z0-9]+', without_accents))


def identity(text):
    # Replace punctuation before accent folding so a curly apostrophe stays a word boundary.
    return normalized(text.replace('’', "'").replace('œ', 'oe'))


@lru_cache(maxsize=1)
def foods():
    rows = json.loads((ROOT/'catalog'/'ciqual-2025.json').read_text(encoding='utf-8'))
    catalog = {food_id: {'id': food_id, 'name': name, 'group': group,
                         'per_100g': dict(zip(MACROS, values)), 'source': SOURCE}
               for food_id, name, group, *values in rows}
    supplemental = json.loads((ROOT/'catalog'/'usda-sr-supplement.json').read_text(encoding='utf-8'))
    for row in supplemental:
        food_id = 'fdc-' + row['id']
        nutrients = row['nutrients']
        catalog[food_id] = {'id':food_id, 'name':row['name_fr'], 'group':'SR Legacy',
                            'source':USDA_SOURCE, 'reference_url':fdc_url(row['id']),
                            'per_100g':{'kcal':nutrients['1008'], 'protein_g':nutrients['1003'],
                                       'carbs_g':round(nutrients['1005'] - nutrients['1079'], 2),
                                       'fat_g':nutrients['1004']}}
    return catalog


@lru_cache(maxsize=1)
def food_index():
    return {food_id: identity(food['name']) for food_id, food in foods().items()}


@lru_cache(maxsize=1)
def exact_foods():
    matches = {}
    for food_id, label in food_index().items():
        matches[label] = None if label in matches else food_id
    return {**matches, **ALIASES}


def search(query):
    if not isinstance(query, str) or len(query) > 100:
        raise ValueError('La recherche Ciqual est limitée à 100 caractères.')
    needle = identity(query)
    if not needle or len(needle) < 2:
        return []
    tokens = [word.rstrip('s') if len(word) > 3 else word for word in needle.split()]
    phrase = ' '.join(tokens)
    ranks = []
    for food_id, label in food_index().items():
        words = [word.rstrip('s') if len(word) > 3 else word for word in label.split()]
        stemmed = ' '.join(words)
        if food_id == needle or exact_foods().get(needle) == food_id:
            rank = 0
        elif stemmed.startswith(phrase):
            rank = 1
        elif phrase in stemmed:
            rank = 2
        elif all(any(word.startswith(token) for word in words) for token in tokens):
            rank = 3
        else:
            continue
        ranks.append((rank, len(label), label, food_id))
    return [
        {**foods()[food_id], 'reference_weights': [
            {'weight_reference': key, 'unit': unit, 'grams_per_unit': factor,
             'description': description, 'url': fdc_url(source_id)}
            for key, (ref_food, unit, factor, source_id, description) in REFERENCE_WEIGHTS.items()
            if ref_food == food_id
        ]}
        for _, _, _, food_id in sorted(ranks)[:15]
    ]


@lru_cache(maxsize=1)
def seeds():
    return {recipe['id']: recipe for recipe in json.loads((ROOT/'seed.json').read_text())}


def seed_match(recipe):
    seed = seeds().get(recipe.get('id'))
    if not seed or recipe['id'] not in SEED_FOODS or recipe.get('method') != seed['method']:
        return {}
    signature = lambda ingredients: [(identity(item['name']), item['unit']) for item in ingredients]
    if signature(recipe['ingredients']) != signature(seed['ingredients']):
        return {}
    return {index: str(food_id) for index, food_id in enumerate(SEED_FOODS[recipe['id']]) if food_id}


def finite_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def validate_recipe_quantities(recipe, *, allow_empty=False):
    servings = recipe.get('servings')
    if not finite_number(servings) or not .001 <= servings <= 100:
        raise ValueError('Servings must be between 1 and 100.')
    ingredients = recipe.get('ingredients')
    if not isinstance(ingredients, list) or len(ingredients) > 200 or (not allow_empty and not ingredients):
        raise ValueError('Add ingredients with name, quantity and unit.')


def calculate(recipe, *, enrich=False, previous=None):
    """Resolve sources and units, and compute only nutritionally supported amounts."""
    overrides = seed_match(recipe) if enrich else {}
    previous_by_name = {}
    for item in (previous or {}).get('ingredients', []):
        item_name = identity(item['name'])
        previous_by_name[item_name] = item if item_name not in previous_by_name else None
    rows = []
    ingredients = []
    totals = {key: [0.0, 0.0] for key in MACROS}
    missing = dict.fromkeys(MACROS, 0)
    traces = set()
    sources = {}
    for index, ingredient in enumerate(recipe['ingredients']):
        if not isinstance(ingredient, dict):
            raise ValueError('Chaque ingrédient doit être saisi sur une ligne.')
        name = ingredient.get('name')
        unit = ingredient.get('unit')
        quantity = ingredient.get('quantity')
        if (not isinstance(name, str) or not name.strip() or len(name) > 200
                or not isinstance(unit, str) or len(unit) > 40
                or not finite_number(quantity) or not 0 < quantity <= 1_000_000):
            raise ValueError('Indiquez un nom, une quantité positive et une unité pour chaque ingrédient.')
        name = name.strip()
        unit = unit.strip()
        unit_key = unit.casefold()
        result = {'name': name, 'quantity': quantity, 'unit': unit}
        earlier = previous_by_name.get(identity(name)) or {}
        if 'food_id' in ingredient:
            food_id = ingredient['food_id']
        elif 'food_id' in earlier:
            food_id = earlier['food_id']
        else:
            food_id = overrides.get(index) or exact_foods().get(identity(name))
        if food_id is not None and (not isinstance(food_id, (str, int)) or str(food_id) not in foods()):
            raise ValueError('Sélectionnez une référence valide dans le catalogue.')
        food = foods().get(str(food_id))
        # Preserve an explicit unresolved link. For old unlinked ingredients, keep their original shape.
        if food or 'food_id' in ingredient or 'food_id' in earlier:
            result['food_id'] = food['id'] if food else None
        # An existing reference is still valid when a recipe scales an otherwise unchanged ingredient.
        current_food_id = food['id'] if food else None
        same_food_and_unit = bool(earlier and earlier.get('food_id') == current_food_id
                                  and earlier['unit'].strip().casefold() == unit_key)
        previous_weight = earlier if same_food_and_unit else {}
        factor = ingredient.get('grams_per_unit', previous_weight.get('grams_per_unit'))
        weight_source = None
        reference = None
        reference_key = ingredient.get('weight_reference', previous_weight.get('weight_reference'))
        if unit_key in MASS:
            grams = quantity * MASS[unit_key]
        elif factor is not None:
            if not finite_number(factor) or not 0 < factor <= 1_000_000:
                raise ValueError('Indiquez un poids comestible positif en grammes par unité.')
            result['grams_per_unit'] = factor
            grams = quantity * factor
            weight_source = 'entered'
        elif reference_key is not None:
            match = REFERENCE_WEIGHTS.get(reference_key) if isinstance(reference_key, str) else None
            if not match or not food or match[:2] != (food['id'], unit_key):
                raise ValueError('Le poids de référence ne correspond pas à cet aliment et à cette unité.')
            result['weight_reference'] = reference_key
            grams = quantity * match[2]
            weight_source = 'reference'
            reference = {'name':'Poids indicatif USDA', 'url':fdc_url(match[3])}
        elif food and food['id'] == '17270' and unit_key in VOLUME:
            grams = quantity * VOLUME[unit_key] * .912
            weight_source = 'olive_density'
        else:
            grams = None
        if grams is not None and grams > 1_000_000:
            raise ValueError('La quantité totale d’un ingrédient ne peut dépasser 1 000 kg.')
        values = food['per_100g'] if food and grams is not None else {}
        if food:
            sources[food['source']['name']] = food['source']
        for key in MACROS:
            value = values.get(key)
            if value is None:
                missing[key] += 1
            elif value == 'trace':
                traces.add(key)
            else:
                low, high = value if isinstance(value, list) else (value, value)
                totals[key][0] += grams * low / 100
                totals[key][1] += grams * high / 100
        rows.append({'food': food['name'] if food else None, 'food_id': food['id'] if food else None,
                     'grams': round(grams, 4) if grams is not None else None, 'weight_source': weight_source,
                     'weight_reference': reference, 'food_reference_url': food.get('reference_url') if food else None,
                     'problem': 'food' if not food else 'weight' if grams is None else
                                'data' if any(values.get(key) is None for key in MACROS) else None})
        ingredients.append(result)

    servings = recipe['servings']
    values = {}
    numeric = {}
    subtotals = {}
    for key, (low, high) in totals.items():
        low, high = low / servings, high / servings
        value = {'low': round(low, 5), 'high': round(high, 5), 'trace': key in traces}
        if missing[key]:
            if missing[key] < len(rows):
                subtotals[key] = value
            continue
        has_range = not math.isclose(low, high, abs_tol=1e-9)
        if not has_range and key not in traces:
            numeric[key] = round(low, 1 if key == 'kcal' else 2)
        values[key] = value
    food_sources = list(sources.values()) or [SOURCE]
    report = {'source': food_sources[0], 'sources': food_sources, 'rows': rows, 'values': values, 'subtotals': subtotals, 'missing': missing,
              'calculated': sum(row['problem'] is None for row in rows), 'total': len(rows)}
    return ingredients, numeric, report


def project(recipe):
    """Read legacy snapshots without changing the archived week, batch, or cart."""
    if 'nutrition_report' in recipe or recipe.get('freezer_only'):
        return recipe
    ingredients, numeric, report = calculate(recipe, enrich=True)
    return {**recipe, 'ingredients': ingredients, 'nutrition': numeric, 'nutrition_report': report}


def project_week(week):
    if not week:
        return week
    return {**week, 'slots': [{**slot, 'recipe': project(slot['recipe'])} for slot in week['slots']]}


def migrate():
    import domain as D

    changed = []
    with D.db() as c:
        if D.get(c, 'migration', 'ciqual-2025-v1'):
            return
        keys = c.execute("SELECT id FROM docs WHERE kind='recipe'").fetchall()
        for row in keys:
            recipe = D.get(c, 'recipe', row['id'])
            updated = project(recipe)
            if updated != recipe:
                updated.pop('nutrition_note', None)
                changed.append(D.put(c, 'recipe', recipe['id'], updated, recipe['version']))
        D.put(c, 'migration', 'ciqual-2025-v1', {})
    for recipe in changed:
        D.write_markdown(recipe)
