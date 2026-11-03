"""Install only app-owned profiles; never clone an existing user's configuration."""
import json,sys,os,shutil,hashlib
from pathlib import Path
from hermes_cli.profiles import create_profile,write_profile_meta
from hermes_yaml import safe_load,safe_dump
from dotenv import set_key
p=json.load(sys.stdin);id=p['id']
if id not in ('table-cookbook','table-planner','table-shopper','table-cart'):raise ValueError('Not an app-owned profile')
home=Path(os.getenv('HERMES_HOME','/opt/data'))/'profiles'/id
created=not home.exists()
if created:home=create_profile(id,no_alias=True,no_skills=True,description='Table managed meal assistant')
marker=home/'table-managed.json';owner=hashlib.sha256(p['token'].encode()).hexdigest()
if not created:
    if marker.exists():
        if json.loads(marker.read_text()).get('owner')!=owner:raise ValueError('Profile belongs to another Table installation')
    else:
        previous=home/'skills'/('table-'+p['role'])/'connection.json'
        if not previous.exists() or json.loads(previous.read_text()).get('token')!=p['token']:raise ValueError('Refusing to overwrite an unmanaged profile')
marker.write_text(json.dumps({'application':'Table','schema':1,'owner':owner}));marker.chmod(0o600)
(home/'SOUL.md').write_text(p['soul'])
meta=safe_load((home/'profile.yaml').read_text()) or {};meta.setdefault('ui_meta',{})['hermes-bots']={'title':p['title']};(home/'profile.yaml').write_text(safe_dump(meta))
write_profile_meta(home,description='Managed by Table; configure in Table.',display_name=p['title'])
root=home/'skills';target=root/('table-'+p['role']);target.mkdir(parents=True,exist_ok=True)
(target/'SKILL.md').write_text(p['skill']);(target/'table_cli.py').write_text(p['cli'])
(target/'connection.json').write_text(json.dumps({'url':p['url'],'token':p['token']}));(target/'connection.json').chmod(0o600)
cfg={'model':{'provider':p['model']['provider'],'default':p['model']['model']},'skills':{'disabled':[str(x.parent.relative_to(root)) for x in root.rglob('SKILL.md') if x.parent!=target]}}
if p['model'].get('base_url'):cfg['model']['base_url']=p['model']['base_url']
(home/'config.yaml').write_text(safe_dump(cfg))
for k,v in {'API_SERVER_KEY':os.environ['API_SERVER_KEY'],**({'OPENAI_API_KEY':p['model']['api_key']} if p['model'].get('api_key') else {})}.items():set_key(str(home/'.env'),k,v)
(home/'.env').chmod(0o600)
print(json.dumps({'id':id,'installed':True}))
