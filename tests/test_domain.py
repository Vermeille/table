import unittest,tempfile,json
from pathlib import Path
import domain as D
class Workflow(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();D.DATA=Path(self.tmp.name);D.init();self.r=D.save_recipe({'id':'test-meal','title':'Test meal','version':0,'servings':2,'ingredients':[{'name':'lentils','quantity':.2,'unit':'kg'}],'method':'Cook lentils.','tags':[],'nutrition':{'kcal':400}})
 def tearDown(self):self.tmp.cleanup()
 def plan(self):return D.update_week('2026-11-02',{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':'test-meal','servings':4}]})
 def test_approval_and_scaling(self):
  w=self.plan()
  with self.assertRaises(ValueError):D.groceries(w['id'],w['version'])
  w=D.approve_week(w['id'],w['version']);w=D.groceries(w['id'],w['version']);self.assertEqual(w['groceries']['items'][0]['quantity'],400);self.assertEqual(w['groceries']['items'][0]['unit'],'g')
  w=D.approve_groceries(w['id'],w['version']);self.assertTrue(w['groceries']['approved'])
 def test_stale_changes_rejected(self):
  w=self.plan()
  with self.assertRaises(ValueError):D.approve_week(w['id'],0)
  self.assertFalse(D.load_week(w['id'])['approved'])
 def test_recipe_snapshot_survives_edit(self):
  w=self.plan();w=D.approve_week(w['id'],w['version']);D.save_recipe({**self.r,'title':'Edited later'})
  self.assertEqual(D.load_week(w['id'])['slots'][0]['recipe']['title'],'Test meal')
  self.assertIn('Edited later',(D.DATA/'cookbook/test-meal.md').read_text())
 def test_edit_invalidates_downstream(self):
  w=self.plan();w=D.approve_week(w['id'],w['version']);w=D.groceries(w['id'],w['version']);w=D.approve_groceries(w['id'],w['version'])
  w=D.update_week(w['id'],{**w,'slots':w['slots']});self.assertFalse(w['approved']);self.assertIsNone(w['groceries']);self.assertIsNone(w['cart'])
 def test_grocery_edit_invalidates_approval(self):
  w=self.plan();w=D.approve_week(w['id'],w['version']);w=D.groceries(w['id'],w['version']);w=D.approve_groceries(w['id'],w['version']);w=D.groceries(w['id'],w['version'],w['groceries']['items']);self.assertFalse(w['groceries']['approved'])
 def test_learning_history_and_restart(self):
  D.learn('cart','Prefer brand A',1);D.init();self.assertEqual(D.read('learning','cart')['text'],'Prefer brand A')
  with D.db() as c:self.assertEqual(c.execute("SELECT count(*) FROM history WHERE kind='learning' AND id='cart'").fetchone()[0],2)
 def test_traversal_rejected(self):
  with self.assertRaises(ValueError):D.save_recipe({**self.r,'id':'../escape'})
 def test_cart_inflight_blocks_edit(self):
  w=self.plan()
  with D.db() as c:w['cart']={'status':'filling'};w=D.put(c,'week',w['id'],w)
  with self.assertRaises(ValueError):D.update_week(w['id'],w)
if __name__=='__main__':unittest.main()
