#!/usr/bin/env bash
# Exercise the installation and scheduled preparation against an isolated Hermes gateway.
set -euo pipefail

table_image=table:0.1.0
if (( $# )); then table_image=$1; fi
fixture_name="table-fresh-$(date +%s)-$$"
fixture_network="$fixture_name-net"
fixture_gateway="$fixture_name-hermes"
fixture_table="$fixture_name-app"
fixture_hermes_volume="$fixture_name-hermes-data"
fixture_table_volume="$fixture_name-table-data"
fixture_key=$(python3 -c 'import secrets; print(secrets.token_urlsafe(48))')
fixture_password=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')

cleanup() {
    docker rm -f "$fixture_table" "$fixture_gateway" >/dev/null 2>&1 || true
    docker volume rm "$fixture_hermes_volume" "$fixture_table_volume" >/dev/null 2>&1 || true
    docker network rm "$fixture_network" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create --internal "$fixture_network" >/dev/null
docker run -d --name "$fixture_gateway" --network "$fixture_network" --network-alias hermes-agent \
    -v "$fixture_hermes_volume:/opt/data" -e HERMES_GATEWAY_BOOTSTRAP_STATE=running \
    -e API_SERVER_ENABLED=true -e API_SERVER_HOST=0.0.0.0 -e API_SERVER_KEY="$fixture_key" \
    nousresearch/hermes-agent:v0.22.5 gateway run >/dev/null

start_table() {
    docker run -d --name "$fixture_table" --network "$fixture_network" --network-alias table \
        -v "$fixture_hermes_volume:/opt/data" -v "$fixture_table_volume:/table-data" \
        -e API_SERVER_KEY="$fixture_key" -e TABLE_PASSWORD="$fixture_password" \
        -e COOKIE_SECURE=false "$table_image" >/dev/null
}

verify_schedule() {
    docker exec -i "$fixture_table" /opt/hermes/.venv/bin/python - "$1" <<'PY'
import json
import os
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.cookiejar import CookieJar
from pathlib import Path

import domain as D

base = 'http://127.0.0.1:8080/api/'
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))

def call(path, data=None):
    request = urllib.request.Request(base+path, json.dumps(data).encode() if data is not None else None,
                                     headers={'Content-Type':'application/json'})
    with client.open(request,timeout=4) as response:
        return json.load(response)

deadline = time.monotonic()+80
while True:
    try:
        health = call('health')
        break
    except OSError:
        if time.monotonic()>=deadline:
            raise
        time.sleep(1)

assert health['setup_error'] is None, health
assert not Path('/opt/data/auth.json').exists()
for role in D.ROLES:
    marker = Path('/opt/data/profiles')/('table-'+role)/'table-managed.json'
    assert json.loads(marker.read_text())['application']=='Table'

if sys.argv[1]=='start':
    call('login', {'password':os.environ['TABLE_PASSWORD']})
    now=datetime.now(timezone.utc)
    week=(now.date()+timedelta(days=7-now.weekday())).isoformat()
    settings=call('state?week='+week)['weekly_settings']
    call('weekly/settings',{**settings,'enabled':True,'timezone':'UTC','day':now.weekday(),
         'at':now.strftime('%H:%M'),'people':1,'days':[0,1],'meals':['dinner'],'no_cook':[1],'cook_days':1})
    deadline=time.monotonic()+100
    while time.monotonic()<deadline:
        job=D.read('weekly',week)
        if job and job['status']=='ready':
            break
        time.sleep(2)
    else:
        raise AssertionError((D.read('weekly',week) or {}).get('status'))
    draft=D.load_week(week)
    assert job['auto'] and job['origin']=='fallback'
    assert len(draft['slots'])==2 and all(slot['servings']==1 for slot in draft['slots'])
    assert job['quality']['no_cook_misses']==[]
    assert not draft['approved'] and not draft['groceries']['approved'] and draft['cart'] is None
    (D.DATA/'fresh-schedule-check.json').write_text(json.dumps(
        {'week':week,'request_id':job['request_id'],'version':job['version']}))
else:
    captured=json.loads((D.DATA/'fresh-schedule-check.json').read_text())
    job=D.read('weekly',captured['week'])
    time.sleep(6)
    assert job and job==D.read('weekly', captured['week'])
    assert (job['request_id'],job['version'])==(captured['request_id'],captured['version'])
    with D.db() as c:
        assert c.execute('SELECT COUNT(*) FROM runs WHERE week=? AND automated=1',(captured['week'],)).fetchone()[0]==1
    print('PASS: fresh Hermes profiles, automatic schedule, offline-ready draft, and no repeat after restart.')
PY
}

start_table
verify_schedule start
docker stop "$fixture_table" >/dev/null
docker rm "$fixture_table" >/dev/null
start_table
verify_schedule restart
