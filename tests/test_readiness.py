import unittest
from unittest.mock import AsyncMock,patch
from fastapi import HTTPException
import server as s
class Readiness(unittest.IsolatedAsyncioTestCase):
 async def test_waits_for_every_profile_after_transient_route_failure(self):
  counts={role:0 for role in s.D.ROLES}
  async def gateway(role,*args,**kwargs):
   counts[role]+=1
   if role=='planner' and counts[role]==1:raise HTTPException(502,'Hermes returned HTTP 404')
   return {'data':[]}
  with patch.object(s,'hermes',side_effect=gateway),patch.object(s.asyncio,'sleep',new=AsyncMock()):await s.wait_profiles()
  self.assertEqual(counts['planner'],2)
  self.assertTrue(all(counts[r]==1 for r in counts if r!='planner'))
 async def test_unavailable_gateway_never_becomes_ready(self):
  with patch.object(s,'hermes',new=AsyncMock(side_effect=HTTPException(503,'Unavailable'))):
   with self.assertRaises(HTTPException):await s.wait_profiles(timeout=0)
if __name__=='__main__':unittest.main()
