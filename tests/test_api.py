import os,tempfile,unittest,json,asyncio
from pathlib import Path
from unittest.mock import AsyncMock,patch
os.environ['TABLE_DATA']=tempfile.mkdtemp();os.environ['TABLE_PASSWORD']='test-password';os.environ['COOKIE_SECURE']='false'
import domain as D
import server as s
from fastapi.testclient import TestClient
class API(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.proj=patch.object(s,'provision',new=AsyncMock());cls.proj.start();cls.ready=patch.object(s,'wait_profiles',new=AsyncMock());cls.ready.start();cls.client=TestClient(s.app);cls.client.__enter__();cls.client.post('/api/login',json={'password':'test-password'})
 @classmethod
 def tearDownClass(cls):cls.client.__exit__(None,None,None);cls.proj.stop();cls.ready.stop()
 def worker(self,role,action,data):return self.client.post('/api/worker/'+action,json=data,headers={'Authorization':'Bearer '+s.TOKENS[role]})
 def test_role_restrictions_and_auth(self):
  self.assertEqual(self.client.post('/api/worker/context',json={}).status_code,401)
  self.assertEqual(self.worker('planner','save_recipe',{}).status_code,403)
  self.assertEqual(self.worker('cart','approve-groceries',{}).status_code,403)
  self.assertEqual(self.worker('shopper','save_week',{}).status_code,403)
  self.assertEqual(self.worker('cookbook','help',{}).status_code,200)
 def test_cart_requires_exact_owner_approval(self):
  week='2026-12-07';r=D.recipes()[0];w=D.update_week(week,{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':r['id'],'servings':2}]});w=D.approve_week(week,w['version']);w=D.groceries(week,w['version']);w=D.approve_groceries(week,w['version'])
  matches=[{'grocery_id':i['id'],'productId':'product-'+str(n),'name':i['name'],'quantity':1,'brand':'test','size':'pack','price':1,'note':'test'} for n,i in enumerate(w['groceries']['items'])]
  p={'week':week,'version':w['version'],'productId':'product-0','quantity':1}
  with patch.object(s,'chrono',new=AsyncMock(side_effect=lambda action,data=None: [] if action=='cart' else {'added':True})) as chrono:
   self.assertEqual(self.worker('cart','cart_add',p).status_code,409);chrono.assert_not_called()
   w=self.worker('cart','propose_cart',{'week':week,'version':w['version'],'matches':matches}).json()
   self.assertEqual(self.worker('cart','cart_add',{**p,'version':w['version']}).status_code,409)
   w=self.client.post('api/week/'+week+'/approve-cart',json={'version':w['version']}).json()
   with D.db() as c:w['cart']['status']='filling';w=D.put(c,'week',week,w)
   p['version']=w['version'];self.assertEqual(self.worker('cart','cart_add',{**p,'quantity':2}).status_code,409);chrono.assert_not_called()
   self.assertEqual(self.worker('cart','cart_add',p).status_code,200);self.assertEqual(chrono.await_count,2)
   self.assertEqual(self.worker('cart','cart_add',p).status_code,409);self.assertEqual(chrono.await_count,2)
 def test_unknown_outcome_blocks_further_additions(self):
  week='2026-12-14';r=D.recipes()[0];w=D.update_week(week,{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':r['id'],'servings':2}]});w=D.approve_week(week,w['version']);w=D.groceries(week,w['version']);w=D.approve_groceries(week,w['version'])
  with D.db() as c:w['cart']={'status':'filling','matches':[{'productId':'a','quantity':1},{'productId':'b','quantity':1}]};w=D.put(c,'week',week,w)
  async def timeout_add(action,data=None):
   if action=='cart':return []
   raise ValueError('timeout')
  with patch.object(s,'chrono',new=AsyncMock(side_effect=timeout_add)) as chrono:
   self.assertEqual(self.worker('cart','cart_add',{'week':week,'version':w['version'],'productId':'a','quantity':1}).status_code,409)
   self.assertEqual(self.worker('cart','cart_add',{'week':week,'version':w['version'],'productId':'b','quantity':1}).status_code,409);self.assertEqual(chrono.await_count,2)
 def test_partial_product_selection_cannot_be_approved(self):
  week='2026-12-21';r=D.recipes()[0];w=D.update_week(week,{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':r['id'],'servings':2}]});w=D.approve_week(week,w['version']);w=D.groceries(week,w['version']);w=D.approve_groceries(week,w['version']);w=s.propose_cart({'week':week,'version':w['version'],'matches':[]});self.assertEqual(self.client.post('/api/week/'+week+'/approve-cart',json={'version':w['version']}).status_code,409)
 def test_existing_cart_product_is_not_overwritten(self):
  week='2026-12-28';r=D.recipes()[0];w=D.update_week(week,{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':r['id'],'servings':2}]});w=D.approve_week(week,w['version']);w=D.groceries(week,w['version']);w=D.approve_groceries(week,w['version'])
  with D.db() as c:w['cart']={'status':'filling','matches':[{'productId':'already-there','quantity':1}]};w=D.put(c,'week',week,w)
  with patch.object(s,'chrono',new=AsyncMock(return_value=[{'productId':'already-there','quantity':3}])) as chrono:
   self.assertEqual(self.worker('cart','cart_add',{'week':week,'version':w['version'],'productId':'already-there','quantity':1}).status_code,409)
   chrono.assert_awaited_once_with('cart')
  with D.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM operations WHERE week=?',(week,)).fetchone()[0],0)
 def test_provider_and_retailer_secrets_not_returned(self):
  s.encrypted_write('model',{'provider':'openai','model':'test','api_key':'never-return-key','base_url':''});s.encrypted_write('chronodrive',{'email':'a@b.test','password':'never-return-password','store_id':'1'});raw=self.client.get('/api/settings').text;self.assertNotIn('never-return',raw)
if __name__=='__main__':unittest.main()
