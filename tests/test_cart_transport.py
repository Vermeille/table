import unittest,tempfile,json,os,importlib.util
from pathlib import Path
from unittest.mock import patch,Mock
import requests
class QuantityTransport(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();root=Path(self.tmp.name);(root/'frontend_config.json').write_text(json.dumps({'customer':'test','cart':'test','search':'test','client_id':'test'}))
  with patch.dict(os.environ,{'CHRONODRIVE_EMAIL':'test@example.invalid','CHRONODRIVE_PASSWORD':'test','CHRONODRIVE_STORE_ID':'1047','CHRONODRIVE_SESSION_FILE':str(root/'session.json')}):
   spec=importlib.util.spec_from_file_location('isolated_chrono_client',Path(__file__).resolve().parents[1]/'chronodrive_client.py');self.client=importlib.util.module_from_spec(spec);spec.loader.exec_module(self.client)
  self.session={'cart_id':'test','bearer':'test'}
 def tearDown(self):self.tmp.cleanup()
 def response(self,status,body=None):
  response=Mock();response.status_code=status;response.json.return_value=body or {}
  if status>=400:response.raise_for_status.side_effect=requests.HTTPError('response error')
  return response
 def test_success_sets_exact_target_quantity(self):
  with patch.object(self.client.requests,'post',return_value=self.response(200,{'content':[{'returnType':'SUCCESS'}]})) as post:
   result=self.client.set_item_quantity('155595',3,self.session);self.assertTrue(result['added']);self.assertEqual(post.call_args.kwargs['json']['content'][0]['quantity'],3)
 def test_definite_rejections_and_rate_limits_are_distinguished(self):
  for status in (400,404,409,422,429):
   with patch.object(self.client.requests,'post',return_value=self.response(status)):
    result=self.client.set_item_quantity('155595',1,self.session);self.assertFalse(result['added']);self.assertEqual(result['retry_later'],status==429)
 def test_server_errors_remain_uncertain(self):
  with patch.object(self.client.requests,'post',return_value=self.response(500)):
   with self.assertRaises(requests.HTTPError):self.client.set_item_quantity('155595',1,self.session)
 def test_business_rejection_is_not_silently_successful(self):
  with patch.object(self.client.requests,'post',return_value=self.response(200,{'content':[{'returnType':'OUT_OF_STOCK'}]})):
   result=self.client.set_item_quantity('155595',1,self.session);self.assertFalse(result['added']);self.assertIn('OUT_OF_STOCK',result['message'])
if __name__=='__main__':unittest.main()
