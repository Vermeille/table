import tempfile
import unittest
from pathlib import Path

import batch
import domain as D


class FreezerPlanning(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.previous = D.DATA
        D.DATA = Path(self.temp.name)
        D.init()
        D.preferences({**D.read('preferences', 'main'), 'batch': {'enabled': True, 'reserve': 4, 'extra_per_day': 4}})
        self.week = '2026-11-16'
        for name, suitable in [('dahl', True), ('chili', True), ('salade', False)]:
            D.save_recipe({'id':name,'title':name,'servings':2,'method':'Préparer le plat.',
                           'ingredients':[{'name':name,'quantity':200,'unit':'g'}], 'freezer_ok':suitable})

    def tearDown(self):
        D.DATA = self.previous
        self.temp.cleanup()

    def slot(self, day, recipe='dahl', quantity=2, meal='dinner', **fields):
        return {'day':day, 'meal':meal, 'recipe_id':recipe, 'servings':quantity, **fields}

    def plan(self, slots, week=None):
        week = week or self.week
        return D.update_week(week, {'version':D.load_week(week)['version'], 'slots':slots})

    def approve(self, plan):
        return D.approve_week(plan['id'], plan['version'])

    def inventory(self, week=None):
        with D.db() as c:
            return batch.inventory(c, week)

    def add(self, quantity, frozen_on='2025-01-01', recipe='dahl', title=None):
        stock = batch.save_lot({'version':self.inventory()['version'], 'quantity':quantity,
                                 'frozen_on':frozen_on, 'recipe_id':recipe, 'title':title})
        return stock['lots'][-1]

    def event(self, plan, slot, action, **fields):
        return batch.record(plan['id'], {'version':plan['version'], 'slot':slot, 'action':action, **fields})

    def test_empty_freezer_builds_stock_on_separate_days_and_counts_batch_once(self):
        plan = self.plan([self.slot(0), self.slot(2), self.slot(4,'chili'), self.slot(6,'salade')])
        self.assertEqual(plan['batch']['0-dinner']['quantity'], 6)
        self.assertEqual(plan['batch']['2-dinner']['source'], 'batch')
        self.assertEqual(plan['batch']['4-dinner']['freeze'], 2)
        self.assertEqual(plan['batch']['6-dinner']['freeze'], 0)
        self.assertEqual({i['name']:i['quantity'] for i in D.aggregate(plan)},
                         {'dahl':600,'chili':400,'salade':200})
        approved = self.approve(plan)
        self.assertEqual(self.inventory()['lots'], [])
        with self.assertRaisesRegex(ValueError, 'pas encore'):
            self.event(approved, '2-dinner', 'take')
        with self.assertRaisesRegex(ValueError, 'prévues'):
            self.event(approved, '0-dinner', 'freeze', quantity=1)
        self.event(approved, '0-dinner', 'freeze', quantity=4)
        self.event(approved, '0-dinner', 'freeze', quantity=4)
        self.assertEqual(self.inventory()['lots'][0]['reserved'], 2)
        self.event(approved, '2-dinner', 'take')
        self.event(approved, '2-dinner', 'take')
        self.assertEqual(self.inventory()['lots'][0]['quantity'], 2)
        self.assertEqual(D.load_week(self.week)['version'], approved['version'])

    def test_stocked_freezer_prefers_older_portions_and_leaves_reserve(self):
        older = self.add(4)
        newer = self.add(4, '2025-03-03')
        plan = self.plan([self.slot(day) for day in range(7)])
        allocations = [allocation for task in plan['batch'].values()
                       if task['source']=='stock' for allocation in task['lots']]
        self.assertEqual(sum(a['quantity'] for a in allocations), 4)
        self.assertEqual({a['id'] for a in allocations}, {older['id']})
        self.assertEqual(sum(t.get('freeze', 0) for t in plan['batch'].values()), 6)
        approved = self.approve(plan)
        self.event(approved, '0-dinner', 'take')
        self.assertEqual(next(lot['quantity'] for lot in self.inventory()['lots'] if lot['id']==newer['id']), 4)

    def test_another_approved_week_cannot_promise_the_same_portions(self):
        lot = self.add(2)
        pinned = [self.slot(0, freezer_lot_id=lot['id'])]
        first = self.plan(pinned)
        second = self.plan(pinned, '2026-11-23')
        self.approve(first)
        with self.assertRaisesRegex(ValueError, 'stock a changé'):
            self.approve(second)
        with self.assertRaisesRegex(ValueError, 'réservées'):
            batch.save_lot({'id':lot['id'],'version':self.inventory()['version'],
                            'quantity':1,'frozen_on':lot['frozen_on']})
        self.plan([self.slot(0,'salade')])
        second = self.approve(second)
        self.assertEqual(second['groceries'], {'items':[], 'approved':False})

    def test_cancelled_meal_releases_stock_and_replanning_keeps_cooked_history(self):
        plan = self.approve(self.plan([self.slot(0), self.slot(2), self.slot(4,'chili')]))
        self.event(plan, '0-dinner', 'freeze', quantity=4)
        self.event(plan, '2-dinner', 'skip')
        self.assertEqual(self.inventory()['lots'][0]['quantity'], 4)
        self.assertEqual(self.inventory()['lots'][0]['reserved'], 0)
        changed = self.plan([self.slot(0), self.slot(2,'salade'), self.slot(4,'chili')])
        self.assertEqual(changed['already_cooked'], ['0-dinner'])
        self.assertNotIn('dahl', {i['name'] for i in D.aggregate(changed)})
        self.assertEqual(self.inventory()['lots'][0]['quantity'], 4)
        with self.assertRaisesRegex(ValueError, 'doit rester'):
            self.plan([self.slot(2,'salade')])

    def test_skipped_cooking_can_be_replanned_without_phantom_stock(self):
        plan = self.approve(self.plan([self.slot(0), self.slot(3)]))
        self.assertEqual(plan['batch']['3-dinner']['source'], 'batch')
        changed = self.plan([self.slot(3)])
        self.assertEqual(changed['batch']['3-dinner']['source'], 'cook')
        self.assertEqual(self.inventory()['lots'], [])
        self.assertGreater(D.aggregate(changed)[0]['quantity'], 0)

    def test_freezer_only_meal_and_disabled_automation(self):
        lot = self.add(2,recipe=None,title='Lasagnes maison')
        plan = self.plan([self.slot(0, lot['recipe']['id'], freezer_lot_id=lot['id'])])
        self.assertEqual(D.aggregate(plan), [])
        prefs = D.read('preferences','main')
        D.preferences({**prefs, 'batch': {**prefs['batch'], 'enabled':False}})
        changed = self.plan([self.slot(0), self.slot(2)])
        self.assertNotIn('batch', changed)
        self.assertEqual(D.aggregate(changed)[0]['quantity'], 400)

    def test_daily_batch_cap_applies_across_lunch_and_dinner(self):
        plan = self.plan([self.slot(0), self.slot(0,'chili',meal='lunch'),
                          self.slot(1,'chili'), self.slot(3), self.slot(5)])
        cooked_on_monday = [t for key,t in plan['batch'].items() if key.startswith('0-')]
        self.assertEqual(sum(t.get('freeze',0) for t in cooked_on_monday), 4)
        self.assertEqual(plan['batch']['5-dinner']['source'], 'cook')
