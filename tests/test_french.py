import unittest,tempfile,copy
from pathlib import Path
import domain as D
import french
class FrenchMigration(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.previous=D.DATA;D.DATA=Path(self.tmp.name);D.init()
  self.recipe=D.save_recipe({'id':'spinach-test','title':'Spinach & ricotta pasta','version':0,'servings':2,'ingredients':[{'name':'spinach','quantity':250,'unit':'g'},{'name':'lemon','quantity':1,'unit':'unit'}],'tags':['vegetarian','quick'],'nutrition':{'kcal':610,'protein_g':28},'method':next(k for k in french.STRINGS if k.startswith('1. Cook pasta, reserving')),'nutrition_note':'Illustrative estimate per serving, not laboratory-verified.'})
 def tearDown(self):D.DATA=self.previous;self.tmp.cleanup()
 def test_existing_recipes_snapshots_groceries_and_approvals(self):
  w=D.update_week('2026-11-02',{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':self.recipe['id'],'servings':3}]});w=D.approve_week(w['id'],w['version']);w=D.groceries(w['id'],w['version']);w=D.approve_groceries(w['id'],w['version']);original=copy.deepcopy(w)
  french.migrate();r=D.read('recipe',self.recipe['id']);w=D.load_week(w['id'])
  self.assertEqual(r['title'],'Pâtes aux épinards et à la ricotta');self.assertTrue(r['method'].startswith('1. Faites cuire'));self.assertEqual(r['ingredients'][0]['name'],'épinards');self.assertEqual(r['ingredients'][1]['unit'],'pièce')
  self.assertEqual(r['nutrition'],self.recipe['nutrition']);self.assertEqual(r['servings'],self.recipe['servings']);self.assertEqual(r['id'],self.recipe['id'])
  self.assertTrue(w['approved']);self.assertTrue(w['groceries']['approved']);self.assertEqual(w['approved_at'],original['approved_at']);self.assertEqual(w['slots'][0]['recipe']['title'],r['title']);self.assertEqual(w['slots'][0]['servings'],3)
  for before,after in zip(original['groceries']['items'],w['groceries']['items']):
   for key in ('id','quantity','checked'):self.assertEqual(before[key],after[key])
  self.assertEqual(w['groceries']['items'][0]['name'],'épinards');self.assertIn('Pâtes aux épinards',(D.DATA/'cookbook/spinach-test.md').read_text())
  version=w['version'];french.migrate();self.assertEqual(D.load_week(w['id'])['version'],version)
 def test_custom_content_is_preserved(self):
  prefs=D.read('preferences','main');D.preferences({**prefs,'planner':'Deux personnes, sans noisettes. Ne pas changer ce texte.'});r=D.save_recipe({**self.recipe,'title':'Ma recette personnelle','method':'Mes étapes personnelles.'});french.migrate();self.assertEqual(D.read('recipe',r['id'])['method'],r['method']);self.assertEqual(D.read('preferences','main')['planner'],'Deux personnes, sans noisettes. Ne pas changer ce texte.')
 def test_active_cart_rolls_back_translation(self):
  w=D.update_week('2026-11-02',{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':self.recipe['id'],'servings':2}]})
  with D.db() as c:w['cart']={'status':'filling'};D.put(c,'week',w['id'],w)
  with self.assertRaises(ValueError):french.migrate()
  self.assertEqual(D.read('recipe',self.recipe['id'])['title'],self.recipe['title']);self.assertIsNone(D.read('migration','french-v1'))
if __name__=='__main__':unittest.main()
