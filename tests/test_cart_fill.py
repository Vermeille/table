import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
import domain as D
import cart_fill as F
class FakeCart:
 def __init__(self):self.q={};self.posts=[];self.reject=set();self.fail_before=set();self.fail_after=set();self.after_post=None
 async def __call__(self,action,data=None):
  if action=='cart':return [{'productId':k,'quantity':v} for k,v in self.q.items()]
  assert action=='set_quantity';id=data['productId'];self.posts.append((id,data['quantity']))
  if id in self.fail_before:raise ValueError('Network timeout')
  if id in self.reject:return {'added':False,'message':'Rupture de stock'}
  self.q[id]=data['quantity']
  if self.after_post:self.after_post(id)
  if id in self.fail_after:raise ValueError('Response lost after write')
  return {'added':True}
class FillJobs(unittest.IsolatedAsyncioTestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.previous=D.DATA;D.DATA=Path(self.tmp.name);D.init();F.LOCK=asyncio.Lock();self.cart=FakeCart();self.week='2026-11-02';self.identity=lambda:'test-account-store';self.count=5
  r=D.save_recipe({'id':'fixture','title':'Repas','servings':2,'method':'Préparer','ingredients':[{'name':'ingrédient','quantity':100,'unit':'g'}]});w=D.update_week(self.week,{'version':0,'slots':[{'day':0,'meal':'dinner','recipe_id':r['id'],'servings':2}]});w=D.approve_week(self.week,w['version']);w=D.groceries(self.week,w['version']);w=D.approve_groceries(self.week,w['version'])
  with D.db() as c:w['cart']={'status':'approved','matches':[{'productId':str(n),'quantity':1+(n%3),'name':'Produit '+str(n),'grocery_id':w['groceries']['items'][0]['id']} for n in range(self.count)],'unmatched':[],'excluded':[]};self.w=D.put(c,'week',self.week,w)
 def tearDown(self):D.DATA=self.previous;self.tmp.cleanup()
 def start(self):return F.start(self.week,self.w['version'],self.identity())
 async def test_all_42_products_finish_without_chat(self):
  self.count=42
  with D.db() as c:
   w=D.get(c,'week',self.week);w['cart']['matches']=[{**w['cart']['matches'][0],'productId':str(n),'name':'Produit '+str(n),'quantity':1+(n%3)} for n in range(self.count)];self.w=D.put(c,'week',self.week,w)
  j=self.start();w=D.load_week(self.week);v=w['version'];result=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(result['status'],'completed');self.assertEqual(len(self.cart.posts),self.count);self.assertEqual(len(self.cart.q),self.count)
  with D.db() as c:self.assertEqual(c.execute('SELECT count(*) FROM operations WHERE status="added"').fetchone()[0],self.count)
  self.assertEqual(D.load_week(self.week)['version'],v+1)
 async def test_existing_quantities_are_preserved_and_not_duplicated(self):
  self.cart.q={'0':1,'1':2,'2':9,'unrelated':7};j=self.start();result=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(result['status'],'completed');self.assertEqual(len(self.cart.posts),self.count-3);self.assertEqual(self.cart.q['2'],9);self.assertEqual(self.cart.q['unrelated'],7)
 async def test_network_error_after_applied_write_is_reconciled(self):
  self.cart.fail_after={'2'};j=self.start();result=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(result['status'],'completed');self.assertEqual(sum(x[0]=='2' for x in self.cart.posts),1)
 async def test_unknown_write_is_not_retried_blindly(self):
  self.cart.fail_before={'1'};j=self.start();r=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(r['status'],'paused');self.assertEqual(len(self.cart.posts),2)
  w=D.load_week(self.week);j=F.start(self.week,w['version'],self.identity(),resume=True);r=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(r['status'],'paused');self.assertEqual(len(self.cart.posts),2)
  self.cart.q['1']=2;w=D.load_week(self.week);j=F.start(self.week,w['version'],self.identity(),resume=True);r=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(r['status'],'completed');self.assertEqual(sum(x[0]=='0' for x in self.cart.posts),1)
 async def test_rejections_are_reported_and_remaining_items_continue(self):
  self.cart.reject={'3'};j=self.start();r=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(r['status'],'partial');self.assertEqual(len(self.cart.posts),self.count);self.assertEqual(r['items'][3]['status'],'rejected');self.assertEqual(len(self.cart.q),self.count-1)
 async def test_crash_after_sending_resumes_from_cart_receipt(self):
  j=self.start();j['status']='running';j['items'][0].update(status='sending',baseline=0,target=1);F.save(j);self.cart.q['0']=1;r=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(r['status'],'completed');self.assertFalse(any(x[0]=='0' for x in self.cart.posts))
 async def test_pause_and_resume_keep_exact_progress(self):
  j=self.start()
  def pause(id):
   if id=='2':F.pause(self.week,D.load_week(self.week)['version'])
  self.cart.after_post=pause;r=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(r['status'],'paused');self.assertEqual(len(self.cart.posts),3);self.cart.after_post=None
  w=D.load_week(self.week);j=F.start(self.week,w['version'],self.identity(),resume=True);r=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(r['status'],'completed');self.assertEqual(len(self.cart.posts),self.count)
 async def test_delayed_cart_visibility_only_retries_reads(self):
  with D.db() as c:
   w=D.get(c,'week',self.week);w['cart']['matches']=w['cart']['matches'][:1];self.w=D.put(c,'week',self.week,w)
  j=self.start();post_seen=False;reads_after=0
  async def delayed(action,data=None):
   nonlocal post_seen,reads_after
   result=await self.cart(action,data)
   if action=='set_quantity':post_seen=True
   elif post_seen:
    reads_after+=1
    if reads_after<3:return []
   return result
  result=await F.execute(j['id'],delayed,self.identity);self.assertEqual(result['status'],'completed');self.assertEqual(len(self.cart.posts),1)
 async def test_changed_account_prevents_any_write(self):
  j=self.start();r=await F.execute(j['id'],self.cart,lambda:'different-account');self.assertEqual(r['status'],'paused');self.assertEqual(self.cart.posts,[])
 async def test_legacy_failure_can_resume_the_unchanged_approved_selection(self):
  with D.db() as c:w=D.get(c,'week',self.week);w['cart']['status']='filling';w=D.put(c,'week',self.week,w);w['cart']['status']='review';w=D.put(c,'week',self.week,w)
  self.cart.q={'0':1,'1':2};j=F.start(self.week,w['version'],self.identity(),resume=True);r=await F.execute(j['id'],self.cart,self.identity);self.assertEqual(r['status'],'completed');self.assertEqual(len(self.cart.posts),self.count-2)
 async def test_chat_completion_does_not_end_a_fill_job(self):
  import server as s
  j=self.start();w=D.load_week(self.week)
  with D.db() as c:c.execute('INSERT INTO runs(id,role,week,remote,status,prompt) VALUES(?,?,?,?,?,?)',('chat-regression','cart',self.week,'remote','running','summary'))
  with patch.object(s,'hermes',new=AsyncMock(return_value={'status':'completed','output':'Je poursuis…'})),patch.object(s.asyncio,'sleep',new=AsyncMock(side_effect=asyncio.CancelledError)):
   with self.assertRaises(asyncio.CancelledError):await s.poll()
  after=D.load_week(self.week);self.assertEqual(after['version'],w['version']);self.assertEqual(after['cart']['status'],'filling');self.assertEqual(F.job_for(after)['id'],j['id'])
if __name__=='__main__':unittest.main()
