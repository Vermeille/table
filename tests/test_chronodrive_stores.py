import unittest,tempfile
from pathlib import Path
from unittest.mock import patch,Mock
from chronodrive_stores import parse_stores,store_id,stores
class Stores(unittest.TestCase):
 def test_current_directory_and_duplicate_info_links(self):
  html='<a href="/magasins-chronodrive/drive-magasin-1047-la-garde"><span>Drive La Garde</span></a><a href="/magasins-chronodrive/drive-magasin-1047-la-garde">Plus d’info</a><a href="/magasins-chronodrive/drive-magasin-1031-cannes---la-bocca">Drive Cannes - La Bocca</a>'
  result=parse_stores(html);self.assertEqual(len(result),2);self.assertEqual(result[1]['id'],'1047');self.assertEqual(result[1]['name'],'La Garde')
 def test_id_or_current_or_legacy_url(self):
  for value in ('1047',' 1047 ','https://www.chronodrive.com/magasins-chronodrive/drive-magasin-1047-la-garde','https://www.chronodrive.com/store/1047'):self.assertEqual(store_id(value),'1047')
 def test_bad_store_is_rejected_before_network(self):
  for value in ('a','La Garde','',None):
   with self.assertRaises(ValueError):store_id(value)
 def test_directory_cache(self):
  with tempfile.TemporaryDirectory() as d:
   response=Mock();response.text='<a href="/magasins-chronodrive/drive-magasin-1047-la-garde">Drive La Garde</a>'
   with patch('chronodrive_stores.requests.get',return_value=response) as request:
    first=stores(Path(d)/'stores.json');second=stores(Path(d)/'stores.json');self.assertEqual(first,second);request.assert_called_once()
 def test_changed_directory_is_not_silently_accepted(self):
  response=Mock();response.text='<p>No store links</p>'
  with patch('chronodrive_stores.requests.get',return_value=response):
   with self.assertRaises(ValueError):stores()
if __name__=='__main__':unittest.main()
