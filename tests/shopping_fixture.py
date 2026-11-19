"""Run the actual Table UI/API/queue with deterministic assistant and retailer responses."""
import asyncio
import os
import re
import time
from tempfile import TemporaryDirectory

test_data = TemporaryDirectory(prefix='guided-table-')
os.environ.update(TABLE_DATA=test_data.name, TABLE_PASSWORD='guided-test', COOKIE_SECURE='false')
import uvicorn
import server
import domain as D

jobs = {}
live_cart = {'already-there': 3}
writes = []
products = {
    'already-there': {'productId': 'already-there', 'name': 'Tomates en grappe', 'price': 2.15, 'size': '500 g', 'brand': 'AUCHAN'},
    'salmon-old': {'productId': 'salmon-old', 'name': 'Pavés de saumon', 'price': 12.99, 'size': '500 g', 'brand': 'AUCHAN', 'stock': 'NO_STOCK'},
    'salmon-new': {'productId': 'salmon-new', 'name': 'Pavés de saumon frais', 'price': 6.99, 'size': '250 g', 'brand': 'AUCHAN', 'stock': 'HIGH_STOCK'},
    'rice': {'productId': 'rice', 'name': 'Riz basmati', 'price': 3.20, 'size': '1 kg', 'brand': 'AUCHAN'},
}

async def provision(role):
    server.encrypted_write('chronodrive', {'email': 'qa@example.test', 'password': 'unused', 'store_id': '1047'})

async def hermes(role, method, path, data=None, headers=None):
    if path.startswith('/api/sessions'):
        return {'data': [{'id': f'fixture-{role}', 'title': 'Bot Chat'}]}
    if method == 'POST' and path == '/v1/runs':
        run_id = D.uid()
        week = re.search(r'\d{4}-\d{2}-\d{2}', data['input'])[0]
        jobs[run_id] = (role, week, time.monotonic())
        return {'run_id': run_id}
    role, week, start = jobs[path.rsplit('/', 1)[-1]]
    if time.monotonic() - start < 2:
        return {'status': 'running'}
    w = D.load_week(week)
    if role == 'shopper' and not w.get('groceries'):
        D.groceries(week, w['version'])
    if role == 'cart' and not w.get('cart'):
        product_for = {'Tomates': 'already-there', 'Saumon': 'salmon-old', 'Riz': 'rice'}
        server.propose_cart({'week': week, 'version': w['version'], 'matches': [
            {**products[product_for[item['name']]], 'grocery_id': item['id'], 'quantity': 1}
            for item in w['groceries']['items'] if not item['checked'] and item['name'] in product_for
        ]})
    return {'status': 'completed', 'output': 'Liste enregistrée dans Table.'}

async def chrono(action, data=None):
    if action == 'cart':
        return [{'productId': id, 'quantity': qty} for id, qty in live_cart.items()]
    if action == 'search':
        return [products['salmon-old'], products['salmon-new']]
    if action == 'products':
        return [products[id] for id in data['ids']]
    assert action == 'set_quantity', action
    await asyncio.sleep(4)
    id, quantity = data['productId'], data['quantity']
    writes.append(id)
    if id == 'salmon-old':
        return {'added': False, 'message': 'En rupture de stock'}
    live_cart[id] = quantity
    return {'added': True}

@server.app.get('/api/fixture-receipt')
async def receipt():
    return {'cart': live_cart, 'writes': writes}

server.provision = provision
server.hermes = hermes
server.chrono = chrono
uvicorn.run(server.app, host='127.0.0.1', port=8891)
