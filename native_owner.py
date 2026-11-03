"""Use Hermes's authenticated native session protocol without owning agent execution."""
import asyncio,contextlib,json,os,socket,sqlite3
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import HTTPException

def bootstrap():
    with socket.socket(socket.AF_UNIX) as peer:
        peer.settimeout(3);peer.connect('/opt/data/gateway.sock')
        peer.sendall(b'{"protocol":1,"verb":"identify","id":1}\n')
        data=b''
        while b'\n' not in data:
            part=peer.recv(65536)
            if not part or len(data)>131072:raise RuntimeError('Invalid owner identity')
            data+=part
    identity=json.loads(data)['result']
    from hermes_cli.gateway_runtime import GatewayEndpoint
    from hermes_cli.gateway_client import _session_ticket
    endpoint=GatewayEndpoint(profile_id='/opt/data',instance_id=identity['instance_id'],
        authority_epoch=identity['authority_epoch'],runtime_protocol=1,api_origin=identity['api_origin'],
        supervisor='external',capabilities=frozenset(identity.get('capabilities',[])),control_home='/opt/data')
    return _session_ticket(Path('/opt/data'),endpoint,scope='host')

@contextlib.asynccontextmanager
async def session(bot):
    from websockets.asyncio.client import connect
    from hermes_cli.gateway_client import GatewayClient
    ticket=await asyncio.to_thread(bootstrap)
    from server import config
    cfg=config()
    hostname=urlsplit(cfg['url']).hostname
    origin=os.getenv('HERMES_OWNER_URL',f'ws://{hostname}:8644/api/ws')
    async with connect(origin,subprotocols=['hermes-gateway-v1','hermes-gateway-ticket.'+ticket],
                       additional_headers={'Authorization':'Bearer '+cfg['api_key']},
                       open_timeout=5,max_size=8*1024*1024,proxy=None) as ws:
        async with GatewayClient(ws) as client:
            snapshot=await client.rpc('session.resume',profile=bot['id'],session_id=bot['session_id'],omit_messages=True)
            yield client,snapshot

async def snapshot(bot):
    async with session(bot) as (_,state):return public_snapshot(state)

def public_snapshot(state):
    # Native snapshots contain internal model history. Never expose that wholesale.
    keys=('session_id','running','authority_epoch','execution_generation','last_sequence','replay_epoch')
    result={k:state.get(k) for k in keys}
    result['prompts']=[{k:p[k] for k in ('kind','prompt_id','execution_generation','choices','command','description','question') if k in p} for p in state.get('prompts',[])]
    return result

async def control(bot,action,body,delivery_id=None):
    async with session(bot) as (client,state):
        if not delivery_id:raise HTTPException(409,'This run has not started in Bot Chat yet. Try again shortly.')
        from gateway.session_bot_mailbox import read_receipt
        home=Path('/opt/data/profiles')/bot['id']
        _,receipt=await read_receipt(home,delivery_id)
        if not receipt or not receipt.get('admission_id'):raise HTTPException(409,'The run cannot yet be controlled. Refresh its status.')
        with sqlite3.connect('file:'+str(home/'state.db')+'?mode=ro',uri=True) as db:
            admission=db.execute('SELECT status,generation FROM session_admissions WHERE admission_id=?',(receipt['admission_id'],)).fetchone()
        if not admission or admission[0]!='started' or admission[1]!=state['execution_generation']:
            raise HTTPException(409,'This run is queued or has already finished. No other bot turn was changed.')
        common={'profile':bot['id'],'session_id':state['session_id'],'execution_generation':state['execution_generation']}
        if action=='stop':return await client.rpc('session.interrupt',**common)
        if action in {'approval','clarify'}:
            prompt=next((p for p in state.get('prompts',[]) if p.get('kind')==action and p.get('prompt_id')==body.get('request_id')),None)
            if not prompt:raise HTTPException(409,'This action is no longer waiting for approval. Refresh the conversation.')
            if body.get('execution_generation')!=prompt['execution_generation']:raise HTTPException(409,'The bot has moved on to another action. Review the new request.')
            if action=='clarify':return await client.rpc('clarify.respond',**common,prompt_id=prompt['prompt_id'],answer=body['answer'])
            return await client.rpc('approval.respond',**common,prompt_id=prompt['prompt_id'],choice=body['choice'])
        raise HTTPException(422,'Unsupported native control')
