"""Run in an isolated container with HERMES_HOME pointing at an empty directory."""
import os,json,subprocess,sys,tempfile
from pathlib import Path
root=Path(tempfile.mkdtemp());home=root/'hermes';home.mkdir();os.environ['HERMES_HOME']=str(home);os.environ['API_SERVER_KEY']='isolated-test-key'
for role in ('cookbook','planner','shopper','cart'):
 p={'id':'table-'+role,'role':role,'title':role,'soul':'App-managed test role.','skill':Path('/app/skills/'+role+'.md').read_text(),'cli':Path('/app/table_cli.py').read_text(),'url':'http://table:8080','token':'test-'+role,'model':{'provider':'openai','model':'gpt-4.1-mini','api_key':'test-model-key'}}
 r=subprocess.run([sys.executable,'/app/profile_worker.py'],input=json.dumps(p),text=True,capture_output=True)
 assert r.returncode==0,(role,r.stderr[-1500:])
 profile=home/'profiles'/('table-'+role);assert profile.exists();assert 'test-'+role in (profile/'skills'/('table-'+role)/'connection.json').read_text();assert 'gpt-4.1-mini' in (profile/'config.yaml').read_text()
 learned='\n\n## Learned guidance\nPrefer brand X\n';p['skill']+=learned
 r=subprocess.run([sys.executable,'/app/profile_worker.py'],input=json.dumps(p),text=True,capture_output=True);assert r.returncode==0,r.stderr
 assert 'Prefer brand X' in (profile/'skills'/('table-'+role)/'SKILL.md').read_text()
# An unrelated pre-existing profile must never be adopted or overwritten.
from hermes_cli.profiles import create_profile
import shutil
shutil.rmtree(home/'profiles'/'table-cookbook')
occupied=create_profile('table-cookbook',no_alias=True,no_skills=True)
q={**p,'id':'table-cookbook','role':'cookbook'}
r=subprocess.run([sys.executable,'/app/profile_worker.py'],input=json.dumps(q),text=True,capture_output=True)
assert r.returncode!=0,'An unmanaged existing profile must not be overwritten'
assert not (occupied/'table-managed.json').exists()
# Existing app profile with a mismatched ownership token is also protected.
p['token']='another-installation'
r=subprocess.run([sys.executable,'/app/profile_worker.py'],input=json.dumps(p),text=True,capture_output=True)
assert r.returncode!=0,'A second installation must not overwrite these profiles'
assert 'Prefer brand X' in (home/'profiles'/'table-cart'/'skills'/'table-cart'/'SKILL.md').read_text()
assert not (home/'auth.json').exists(),'Installer must not depend on pre-existing OAuth'
print('PASS: four profiles created and updated against an empty Hermes home; no cloned configuration or prior authentication.')
