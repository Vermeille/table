"""Evaluate a replacement against the actual cooking and freezer schedule."""
import batch
import domain as D
import weekly


def related_keys(week, key, entries):
    tasks=week.get('batch') or {}
    anchor=tasks.get(key,{}).get('from_slot',key)
    together=[anchor,*(other for other,task in tasks.items() if task.get('from_slot')==anchor)]
    if len(together)<2 or any(entries.get(k,{}).get('action') not in (None,'skip') for k in together):
        return [key]
    return together


def suggestions(week, key, whole_batch=False):
    with D.db() as c:
        w=D.get(c,'week',D.week_id(week))
        slots=w['slots'] if w else []
        old=next((slot for slot in slots if batch.key(slot)==key),None)
        if not old:
            raise ValueError('Ce repas ne figure plus dans le planning.')
        D.editable(w)
        original=w.get('batch') or {}
        entries=batch.kitchen(c,week)['entries']
        together=related_keys(w,key,entries)
        targets=together if whole_batch else [key]
        settings=weekly.settings(c)
        job=D.get(c,'weekly',week)
        if job and w.get('weekly_prepared')==job['request_id']:
            settings=job['settings']
        preferences=D.get(c,'preferences','main')
        config=batch.settings(preferences) if preferences.get('batch') else w.get('batch_settings',batch.settings(preferences))
        config={**config,'prefer_frozen_days':settings['no_cook']}
        cooking_days={slot['day'] for slot in slots if original.get(batch.key(slot),{}).get('source') not in batch.ACTIVE_SOURCES}
        required_portable=any(slot['meal']=='lunch' and slot['day'] in settings['portable']
                              for slot in slots if batch.key(slot) in targets)
        options=[]
        for (id,) in c.execute("SELECT id FROM docs WHERE kind='recipe'"):
            recipe=D.get(c,'recipe',id)
            if id==old['recipe_id'] or not weekly.allowed(recipe,settings):
                continue
            features=weekly.recipe_features(recipe)
            if required_portable and not features['portable']:
                continue
            plan=[{'day':slot['day'],'meal':slot['meal'],'servings':slot['servings'],'recipe_id':id}
                  if batch.key(slot) in targets else slot for slot in slots]
            try:
                draft,_,_=D.compose_week(c,week,{'slots':plan},w,config)
            except ValueError:
                continue
            new_days={slot['day'] for slot in draft['slots']
                      if draft.get('batch',{}).get(batch.key(slot),{}).get('source') not in batch.ACTIVE_SOURCES}
            added=new_days-cooking_days
            already_planned=sum(slot['recipe_id']==id for slot in slots)
            nutrition=recipe.get('nutrition') or {}
            calories=nutrition.get('kcal')
            before=(old['recipe'].get('nutrition') or {}).get('kcal')
            calorie_distance=abs(calories-before) if calories is not None and before is not None else 300
            rank=(len(added & set(settings['no_cook'])),len(added),already_planned,len(new_days),
                  calorie_distance,features['active_minutes'] or 25,recipe['title'])
            options.append((rank,{'recipe_id':id,'title':recipe['title'],'kcal':calories,
                                  'active_minutes':features['active_minutes'],'added_days':sorted(added),
                                  'portable':features['portable']}))
        return {'week_version':w['version'],'targets':targets,'related':together,
                'suggestions':[choice for _,choice in sorted(options,key=lambda result:result[0])[:3]]}
