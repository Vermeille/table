"""Skill transport. Credentials never appear in command arguments or output."""
import json,sys,urllib.request,urllib.error
from pathlib import Path
cfg=json.loads((Path(__file__).parent/'connection.json').read_text())
if len(sys.argv)<2:raise SystemExit('Usage: python table_cli.py ACTION [JSON_OBJECT]; use help for schema')
data=json.loads(sys.argv[2]) if len(sys.argv)>2 else json.load(sys.stdin) if not sys.stdin.isatty() else {}
req=urllib.request.Request(cfg['url']+'/api/worker/'+sys.argv[1],data=json.dumps(data).encode(),headers={'Authorization':'Bearer '+cfg['token'],'Content-Type':'application/json'})
try:
    with urllib.request.urlopen(req,timeout=90) as r:print(r.read().decode())
except urllib.error.HTTPError as e:
    print(e.read().decode());raise SystemExit(1)
