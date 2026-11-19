import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
import requests

import domain as D
import notifications as push


class WeeklyNotifications(unittest.TestCase):
    def setUp(self):
        original = D.DATA
        data = tempfile.TemporaryDirectory()
        self.addCleanup(data.cleanup)
        self.addCleanup(setattr, D, 'DATA', original)
        D.DATA = Path(data.name)
        D.init()
        (D.DATA/'key').write_bytes(Fernet.generate_key())
        key = ec.generate_private_key(ec.SECP256R1()).public_key().public_bytes(Encoding.X962,PublicFormat.UncompressedPoint)
        self.subscription = {
            'endpoint':'https://updates.push.services.mozilla.com/wpush/v2/test-capability',
            'keys':{'p256dh':push.b64(key),'auth':push.b64(b'test-auth-secret')}
        }

    def test_keys_persist_and_invalid_endpoint_cannot_send(self):
        initial = push.public_key()
        self.assertEqual(initial,push.public_key())
        self.assertEqual(len(push.key_bytes(initial,65)),65)
        for bad in ('http://fcm.googleapis.com/a', 'https://fcm.googleapis.com.evil.test/a',
                    'https://fcm.googleapis.com@evil.test/a','https://fcm.googleapis.com:8080/a',
                    'https://web.push.apple.com.evil.test/a'):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                push.register({**self.subscription,'endpoint':bad},'https://table.test')
        self.assertEqual(D.listing('push_device'),[])
        self.assertNotIn(initial,D.read('push_key','main')['secret'])
        self.assertEqual(len(push.endpoint_id('https://web.push.apple.com/a')),64)
        self.assertEqual(len(push.endpoint_id('https://example.web.push.apple.com/a')),64)

    def test_ready_delivery_encrypts_payload_and_is_sent_once_per_device(self):
        key = push.register(self.subscription,'https://table.test')
        self.assertNotIn(self.subscription['endpoint'],D.read('push_device',key)['subscription'])
        week = '2030-01-07'
        with D.db() as c:
            D.put(c,'weekly',week,{'status':'ready','finished':time.time()+1})
        sent = []
        def capture(session, prepared, **kwargs):
            sent.append((prepared,kwargs))
            response = requests.Response()
            response.status_code = 201
            response._content = b''
            return response
        with patch.object(requests.Session,'send',capture):
            asyncio.run(push.flush())
            asyncio.run(push.flush())
        self.assertEqual(len(sent),1)
        request, options = sent[0]
        self.assertEqual(request.url,self.subscription['endpoint'])
        self.assertFalse(options['allow_redirects'])
        self.assertTrue(request.headers['Authorization'].lower().startswith('vapid '))
        self.assertEqual(request.headers['Content-Encoding'],'aes128gcm')
        self.assertEqual(request.headers['Topic'],'table-'+week)
        self.assertNotIn(b'repas',request.body)
        self.assertTrue(D.read('push_delivery',f'{week}-{key}')['done'])
        push.unregister(self.subscription['endpoint'])
        self.assertIsNone(D.read('push_device',key))

    def test_expired_browser_removed(self):
        key = push.register(self.subscription,'https://table.test')
        with D.db() as c:
            D.put(c,'weekly','2030-01-07',{'status':'ready','finished':time.time()+1})
        with patch.object(push,'transmit',return_value=410):
            asyncio.run(push.flush())
        self.assertIsNone(D.read('push_device',key))
