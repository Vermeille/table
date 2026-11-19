import asyncio
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import batch
import domain as D
import weekly


class WeeklyPreparation(unittest.TestCase):
    week = '2030-01-07'
    now = datetime(2026, 11, 19, 12, tzinfo=timezone.utc)

    def setUp(self):
        previous = D.DATA
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        self.addCleanup(setattr, D, 'DATA', previous)
        D.DATA = Path(data.name)
        D.init()
        weekly.install_pack()
        prefs = D.read('preferences', 'main')
        D.preferences({**prefs, 'batch': {'enabled':True, 'reserve':4, 'extra_per_day':4}})

    def configure(self, **overrides):
        with D.db() as c:
            config = weekly.settings(c)
        return weekly.save_settings({**config, **overrides})

    def tick(self, submit=None, connected=False, now=None):
        asyncio.run(weekly.tick(submit or AsyncMock(), lambda:connected, now=now or self.now))

    def complete_run(self, field, result='completed'):
        job = D.read('weekly', self.week)
        role = 'planner' if field == 'plan_run' else 'cart'
        with D.db() as c:
            c.execute('INSERT INTO runs(id,role,week,status,prompt,automated) VALUES(?,?,?,?,?,1)',
                      (job[field],role,self.week,result,'Fixture'))
        return job

    def test_scheduled_for_next_monday_at_local_time_across_dst(self):
        config = self.configure(enabled=True)
        for before, after, week in (
            (datetime(2027,3,26,16,59,tzinfo=timezone.utc), datetime(2027,3,26,17,tzinfo=timezone.utc),'2027-03-29'),
            (datetime(2027,4,2,15,59,tzinfo=timezone.utc), datetime(2027,4,2,16,tzinfo=timezone.utc),'2027-04-05'),
        ):
            self.assertIsNone(weekly.due_week(before,config))
            self.assertEqual(weekly.due_week(after,config),week)

    def test_does_not_duplicate_or_replace_a_hand_written_menu_after_restart(self):
        self.configure(enabled=True)
        week = '2026-11-23'
        original = D.update_week(week, {'version':0,'slots':[
            {'day':0,'meal':'lunch','recipe_id':'lieu-tomate-haricots-boulgour','servings':3}
        ]})
        now = datetime(2026,11,20,17,10,tzinfo=timezone.utc)
        self.tick(now=now)
        self.tick(now=now)
        self.tick(now=now)
        ready = D.read('weekly',week)
        self.tick(now=now)
        draft = D.load_week(week)
        self.assertEqual(ready,D.read('weekly',week))
        self.assertEqual(ready['status'],'ready')
        self.assertEqual(ready['origin'],'existing')
        self.assertEqual(original['slots'],draft['slots'])
        self.assertFalse(draft['approved'])
        self.assertFalse(draft['groceries']['approved'])
        self.assertFalse(weekly.mark_seen(week).get('error'))

    def test_empty_freezer_household_repeats_batch_meals_and_consolidates_quantities(self):
        config = self.configure(people=2, daily_kcal=1800, no_cook=[2,4], exclude=['fruits'], pantry=['Paprika'])
        weekly.owner_request(self.week,0)
        self.tick()
        self.complete_run('plan_run','failed')
        self.tick()
        self.tick()
        ready = D.read('weekly',self.week)
        draft = D.load_week(self.week)
        quality = ready['quality']
        self.assertEqual(ready['origin'],'fallback')
        self.assertEqual(ready['status'],'ready')
        self.assertEqual(len(draft['slots']),14)
        self.assertEqual({slot['servings'] for slot in draft['slots']},{2})
        self.assertFalse(quality['portable_misses'])
        self.assertFalse(quality['no_cook_misses'])
        self.assertLessEqual(len(quality['cook_days']),4)
        self.assertGreaterEqual(quality['frozen_meals'],5)
        self.assertGreaterEqual(quality['nutrition_known'],12)
        self.assertTrue(all(weekly.allowed(slot['recipe'],config) for slot in draft['slots']))
        grocery = next(i for i in draft['groceries']['items'] if i['name']=='Paprika')
        expected = sum(task['quantity']/slot['recipe']['servings']*i['quantity']
                       for slot in draft['slots'] for task in [draft['batch'][batch.key(slot)]]
                       if task['source']=='cook' for i in slot['recipe']['ingredients'] if i['name']=='Paprika')
        self.assertEqual(grocery['quantity'],expected)
        self.assertTrue(grocery['checked'])
        self.assertFalse(draft['groceries']['approved'])

    def test_scope_and_diet_validation_leave_owner_edits_intact(self):
        self.configure(people=1, meals=['lunch'], days=[0,1,2], diet='vegan', exclude=['Aubergines'])
        weekly.owner_request(self.week,0)
        self.tick()
        job = D.read('weekly', self.week)
        menus = [
            {'slots':[{'day':day,'meal':'lunch','servings':1,'recipe_id':id} for day in range(3)]}
            for id in ('saumon-tomate-poireaux-quinoa','pates-ragout-aubergine-haricots','quinoa-pois-chiches-amandes')
        ]
        report = weekly.propose(self.week,job['request_id'],menus)
        self.assertIn('error',report['reviews'][0])
        self.assertIn('error',report['reviews'][1])
        self.assertNotIn('error',report['reviews'][2])
        self.assertFalse(D.load_week(self.week)['slots'])
        update = D.update_week(self.week,{'version':0,'slots':menus[0]['slots'][:1]})
        with self.assertRaises(ValueError):
            weekly.propose(self.week,job['request_id'],menus[2:])
        self.tick()
        self.assertEqual(D.load_week(self.week),update)
        self.assertEqual(D.read('weekly',self.week)['status'],'superseded')

    def test_cart_preview_survives_grocery_approval_and_leaves_missing_rows_unresolved(self):
        self.configure(people=2, meals=['dinner'], days=[0])
        w = D.update_week(self.week,{'version':0,'slots':[
            {'day':0,'meal':'dinner','recipe_id':'soupe-pois-casses-poireaux','servings':2}]})
        weekly.owner_request(self.week,w['version'])
        self.tick(connected=True)
        self.tick(connected=True)
        job = self.complete_run('cart_run')
        prepared = D.load_week(self.week)
        first,second,*_ = prepared['groceries']['items']
        matches = [{'productId':f'good-{index}','grocery_id':item['id'],'quantity':1,'name':item['name']}
                   for index,item in enumerate((first,second))]
        products=[{'productId':m['productId'],'name':m['name'],'pack':{'amount':1000,'unit':'g'}, 'stock':'HIGH_STOCK'}
                  for m in matches]
        weekly.propose_products(self.week,job['request_id'],matches,products,'retailer-test')
        self.tick(connected=True)
        prepared = D.load_week(self.week)
        self.assertEqual(prepared['cart']['status'],'proposed')
        self.assertTrue(prepared['cart']['weekly_preview'])
        self.assertFalse(prepared['approved'])
        self.assertFalse(prepared['groceries']['approved'])
        approved = D.approve_week(self.week,prepared['version'])
        items = [{**i, 'checked':i['id']==first['id']} for i in approved['groceries']['items']]
        edited = D.groceries(self.week,approved['version'],items)
        self.assertEqual([m['productId'] for m in edited['cart']['matches']],[matches[1]['productId']])
        reviewed = D.approve_groceries(self.week, edited['version'])
        self.assertEqual(reviewed['cart']['matches'],edited['cart']['matches'])
        self.assertTrue(reviewed['cart']['unmatched'])

    def test_pack_has_calculated_macros_per_portion_and_does_not_overwrite_edits(self):
        recipes = D.recipes()
        self.assertEqual(len(recipes),12)
        for recipe in recipes:
            self.assertEqual(recipe['nutrition_report']['calculated'],len(recipe['ingredients']),recipe['id'])
            self.assertTrue(recipe['freezer_ok'])
            self.assertGreater(recipe['nutrition']['protein_g'],25)
            self.assertGreater(recipe['nutrition']['kcal'],700)
            self.assertLess(recipe['nutrition']['kcal'],900)
        prior = D.save_recipe({**recipes[0],'title':'Mon plat personnalisé'})
        weekly.install_pack()
        self.assertEqual(D.read('recipe',prior['id']),prior)
