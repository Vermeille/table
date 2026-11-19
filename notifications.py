"""Weekly review notifications for browsers that have opted in."""
import asyncio
import base64
import hashlib
import json
import logging
import re
import time
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PrivateFormat, NoEncryption, PublicFormat

import domain as D

LOG = logging.getLogger('table.notifications')
PUSH_HOSTS = {'fcm.googleapis.com', 'android.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com'}
NOTICE_TTL = 7 * 24 * 60 * 60
MAX_ATTEMPTS = 5
RETRYABLE = {0, 408, 429}


def b64(value):
    return base64.urlsafe_b64encode(value).decode().rstrip('=')


def key_bytes(value, length):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}={0,2}', value):
        raise ValueError('Les clés de notification sont invalides.')
    raw = base64.urlsafe_b64decode(value.rstrip('=') + '=' * (-len(value.rstrip('=')) % 4))
    if len(raw) != length:
        raise ValueError('Les clés de notification sont invalides.')
    return raw


def endpoint_id(endpoint):
    if not isinstance(endpoint, str) or not 1 <= len(endpoint) <= 4096 or any(char.isspace() for char in endpoint):
        raise ValueError('L’adresse de notification est invalide.')
    url = urlsplit(endpoint)
    if (url.scheme != 'https' or url.hostname not in PUSH_HOSTS
            or url.netloc != url.hostname or not url.path.startswith('/') or url.fragment):
        raise ValueError('Le service de notifications de ce navigateur n’est pas pris en charge.')
    return hashlib.sha256(endpoint.encode()).hexdigest()


def cipher():
    return Fernet((D.DATA/'key').read_bytes())


def keypair():
    with D.db() as c:
        pair = D.get(c, 'push_key', 'main')
        if not pair:
            private = ec.generate_private_key(ec.SECP256R1())
            secret = private.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
            public = private.public_key().public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
            pair = D.put(c, 'push_key', 'main', {'secret':cipher().encrypt(secret).decode(), 'public':b64(public)})
    return pair


def public_key():
    return keypair()['public']


def register(subscription, origin):
    endpoint = subscription.get('endpoint')
    device = endpoint_id(endpoint)
    keys = subscription.get('keys') or {}
    if not isinstance(keys, dict):
        raise ValueError('Les clés de notification sont invalides.')
    public = key_bytes(keys.get('p256dh'), 65)
    ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), public)
    auth = key_bytes(keys.get('auth'), 16)
    url = urlsplit(origin)
    if url.scheme != 'https' or not url.hostname or url.username or url.password:
        raise ValueError('Les notifications demandent une connexion HTTPS.')
    sealed = cipher().encrypt(json.dumps({'endpoint':endpoint, 'keys':{'p256dh':b64(public),'auth':b64(auth)}}).encode())
    with D.db() as c:
        old = D.get(c, 'push_device', device)
        if not old and c.execute("SELECT COUNT(*) FROM docs WHERE kind='push_device'").fetchone()[0] >= 16:
            raise ValueError('Table est déjà connecté à 16 appareils.')
        D.put(c, 'push_device', device, {'subscription':sealed.decode(), 'origin':f'https://{url.netloc}',
                                        'registered':old['registered'] if old else time.time()})
    return device


def remove(c, device_id):
    c.execute("DELETE FROM docs WHERE kind='push_device' AND id=?", (device_id,))
    c.execute("DELETE FROM history WHERE kind='push_device' AND id=?", (device_id,))


def unregister(endpoint):
    with D.db() as c:
        remove(c, endpoint_id(endpoint))


def delivery(c, now):
    period = now - NOTICE_TTL
    jobs = c.execute("""SELECT id FROM docs WHERE kind='weekly'
        AND json_extract(data,'$.status')='ready' AND json_extract(data,'$.seen') IS NOT 1
        AND json_extract(data,'$.finished')>? ORDER BY id DESC""", (period,)).fetchall()
    devices = [D.get(c,'push_device',key) for (key,) in c.execute("SELECT id FROM docs WHERE kind='push_device'")]
    for (week,) in jobs:
        job = D.get(c,'weekly',week)
        for device in devices:
            if job['finished'] < device['registered']:
                continue
            key = f'{week}-{device["id"]}'
            record = D.get(c,'push_delivery',key) or {'attempts':0}
            if record['attempts'] >= MAX_ATTEMPTS or record.get('done') or record.get('next',0) > now:
                continue
            cleared = D.put(c,'push_delivery',key,{'attempts':record['attempts']+1,'next':now+120})
            return cleared, device, week
    return None


def transmit(device, week=None):
    from pywebpush import WebPushException, webpush
    import requests

    class PushSession(requests.Session):
        def request(self, method, url, **kwargs):
            return super().request(method, url, **{**kwargs, 'allow_redirects':False})

    private = b64(cipher().decrypt(keypair()['secret'].encode()))
    info = json.loads(cipher().decrypt(device['subscription'].encode()))
    endpoint_id(info['endpoint'])
    if week:
        message = {'title':'Votre semaine est prête à relire', 'body':'Ouvrez Table pour revoir les repas et les courses.', 'week':week}
    else:
        message = {'title':'Notifications Table activées', 'body':'Cet appareil recevra vos nouveaux plannings.'}
    try:
        with PushSession() as session:
            session.trust_env = False
            response = webpush(info, json.dumps(message,ensure_ascii=False),
                               vapid_private_key=private, vapid_claims={'sub':device['origin']},
                               ttl=NOTICE_TTL if week else 60, timeout=10, requests_session=session,
                               headers={'topic':f'table-{week or "test"}','urgency':'normal'})
            return response.status_code
    except WebPushException as error:
        return error.response.status_code if error.response is not None else 0
    except requests.RequestException:
        return 0


async def test(endpoint):
    device_id = endpoint_id(endpoint)
    device = D.read('push_device',device_id)
    if not device:
        raise ValueError('Activez les notifications sur cet appareil.')
    now = time.time()
    with D.db() as c:
        latest = D.get(c,'push_test',device_id)
        if latest and latest['at']+30 > now:
            raise ValueError('Attendez 30 secondes entre deux essais.')
        D.put(c,'push_test',device_id,{'at':now})
    status = await asyncio.to_thread(transmit,device)
    if not 200 <= status < 300:
        if status in (404,410):
            with D.db() as c:
                remove(c,device_id)
        raise ValueError('Le service de notifications n’a pas accepté le message. Réactivez les notifications puis réessayez.')


async def flush():
    for _ in range(3):
        now = time.time()
        with D.db() as c:
            requested = delivery(c,now)
        if not requested:
            return
        record, device, week = requested
        try:
            status = await asyncio.to_thread(transmit,device,week)
        except Exception as error:
            LOG.warning('Could not send web push (%s)', type(error).__name__)
            status = 0
        with D.db() as c:
            if status in (404,410):
                remove(c,device['id'])
            D.put(c,'push_delivery',record['id'],
                  {**record,'done':not (status in RETRYABLE or status >= 500),
                   'next':now + 30 * 2 ** record['attempts'],'status':status},record['version'])
