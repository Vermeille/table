"""Private authenticated transport to the gateway's loopback-only session owner.

Runs in the Hermes container's network namespace, never on a published host port.
It forwards only /api/ws and still requires a native single-use session ticket.
"""
import asyncio,contextlib,hmac,json,os,socket
from aiohttp import web,ClientSession,WSMsgType

def identify():
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(3);peer.connect('/opt/data/gateway.sock')
        peer.sendall(b'{"protocol":1,"verb":"identify","id":1}\n')
        data=b''
        while b'\n' not in data:
            part=peer.recv(65536)
            if not part or len(data)>131072:raise RuntimeError('Invalid owner identity')
            data+=part
    result=json.loads(data)['result']
    origin=result['api_origin']
    if not origin.startswith('http://127.0.0.1:'):raise RuntimeError('Owner must be loopback')
    return origin

async def websocket(request):
    key=os.getenv('API_SERVER_KEY','')
    if not key or not hmac.compare_digest(request.headers.get('Authorization',''),'Bearer '+key):
        raise web.HTTPUnauthorized()
    protocols=[s.strip() for s in request.headers.get('Sec-WebSocket-Protocol','').split(',') if s.strip()]
    if 'hermes-gateway-v1' not in protocols or not any(s.startswith('hermes-gateway-ticket.') for s in protocols):
        raise web.HTTPForbidden()
    origin=await asyncio.to_thread(identify)
    async with ClientSession() as session:
        async with session.ws_connect(origin.replace('http:','ws:')+'/api/ws',protocols=protocols,max_msg_size=8*1024*1024) as upstream:
            downstream=web.WebSocketResponse(protocols=[upstream.protocol],max_msg_size=8*1024*1024)
            await downstream.prepare(request)
            async def pump(source,target):
                async for message in source:
                    if message.type==WSMsgType.TEXT:await target.send_str(message.data)
                    elif message.type==WSMsgType.BINARY:await target.send_bytes(message.data)
                    elif message.type in (WSMsgType.CLOSE,WSMsgType.CLOSED,WSMsgType.ERROR):break
            tasks=[asyncio.create_task(pump(downstream,upstream)),asyncio.create_task(pump(upstream,downstream))]
            try:await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
            finally:
                for task in tasks:task.cancel()
                await asyncio.gather(*tasks,return_exceptions=True)
                await downstream.close()
    return downstream

app=web.Application()
app.router.add_get('/api/ws',websocket)
async def health(request):
    from urllib.parse import urlsplit
    try:
        origin=urlsplit(await asyncio.to_thread(identify))
        def probe():
            with socket.create_connection(('127.0.0.1',origin.port),timeout=3):pass
        await asyncio.to_thread(probe)
        return web.json_response({'status':'ok'})
    except Exception:return web.json_response({'status':'owner_unavailable'},status=503)
app.router.add_get('/health',health)
web.run_app(app,host='0.0.0.0',port=int(os.getenv("BRIDGE_PORT","8644")),print=None)
