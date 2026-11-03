import unittest,tempfile
from pathlib import Path
import domain as D
import cart_review as C
from chronodrive_products import normalize,image_url,product_id
class CartReview(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.previous=D.DATA;D.DATA=Path(self.tmp.name);D.init()
  r=D.save_recipe({'id':'test-meal','title':'Repas','servings':2,'method':'Préparer.','ingredients':[{'name':n,'quantity':100,'unit':'g'} for n in ('lentilles','orge','chou')]})
  self.week='2026-11-02';w=D.update_week(self.week,{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':r['id'],'servings':2}]});w=D.approve_week(self.week,w['version']);w=D.groceries(self.week,w['version']);w=D.approve_groceries(self.week,w['version']);self.ids=[i['id'] for i in w['groceries']['items']]
  with D.db() as c:w['cart']={'matches':[{'grocery_id':self.ids[0],'productId':'123','name':'Lentilles','quantity':1}],'unmatched':self.ids[1:],'status':'proposed'};self.w=D.put(c,'week',self.week,w)
 def tearDown(self):D.DATA=self.previous;self.tmp.cleanup()
 def test_explicit_decisions_resolve_missing_without_dropping_selection(self):
  w=C.review(self.week,self.w['version'],self.ids[1],'pantry');w=C.review(self.week,w['version'],self.ids[2],'skip');self.assertEqual(C.missing(w),[]);self.assertEqual(w['cart']['matches'],self.w['cart']['matches']);self.assertTrue(w['approved']);self.assertTrue(w['groceries']['approved']);self.assertEqual(len(w['cart']['excluded']),2)
 def test_restore_and_edit_require_new_approval(self):
  w=C.review(self.week,self.w['version'],self.ids[1],'skip')
  with D.db() as c:w['cart']['status']='approved';w=D.put(c,'week',self.week,w)
  w=C.review(self.week,w['version'],self.ids[1],'restore');self.assertEqual(w['cart']['status'],'proposed');self.assertIn(self.ids[1],C.missing(w));self.assertEqual(w['cart']['excluded'],[])
 def test_stale_decision_does_not_modify(self):
  with self.assertRaises(ValueError):C.review(self.week,self.w['version']-1,self.ids[1],'skip')
  self.assertEqual(D.load_week(self.week),self.w)
 def test_manual_match_preserves_other_items_and_exact_packs(self):
  product={'productId':'456','name':'Orge perlé','image_url':'https://static1.chronodrive.com/img/PM/P/orge.gif','price':2.5}
  w=C.review(self.week,self.w['version'],self.ids[1],'match',product,2);self.assertEqual(len(w['cart']['matches']),2);self.assertEqual(w['cart']['matches'][1]['quantity'],2);self.assertNotIn(self.ids[1],C.missing(w));self.assertIn(self.ids[2],C.missing(w))
 def test_invalid_match_or_inflight_change_is_rejected(self):
  with self.assertRaises(ValueError):C.review(self.week,self.w['version'],self.ids[1],'match',{'productId':'456','name':'Orge'},0)
  with D.db() as c:self.w['cart']['status']='filling';self.w=D.put(c,'week',self.week,self.w)
  with self.assertRaises(ValueError):C.review(self.week,self.w['version'],self.ids[1],'skip')
class ProductImages(unittest.TestCase):
 def test_current_retailer_paths(self):
  p={'id':155595,'labels':{'productLabel':'Lentilles'},'images':{'views':['img/PM/P/0/95/0P_155595.gif']}}
  self.assertEqual(normalize(p)['image_url'],'https://static1.chronodrive.com/img/PM/P/0/95/0P_155595.gif')
 def test_unsafe_image_urls_are_rejected(self):
  for value in ('javascript:alert(1)','https://other.example/img/x.gif','//other.example/img/x.gif','../../private'):
   self.assertIsNone(image_url({'images':{'views':[value]}}))
 def test_thumbnail_fallback_and_missing_image(self):
  self.assertIsNone(image_url({}));self.assertTrue(image_url({'images':{'thumbnails':['img/PM/P/x.gif']}}).endswith('/img/PM/P/x.gif'))
 def test_product_path_validation(self):
  self.assertEqual(product_id('550251_1'),'550251_1')
  with self.assertRaises(ValueError):product_id('../customers/me')
if __name__=='__main__':unittest.main()
