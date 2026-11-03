exec(open('/tmp/table-live-check.py').read().split("s=api('state?")[0])
week='2026-11-09'
s=api('state?week='+week)
if s['week']['version']==0:
 r=api('chat',{'role':'planner','week':week,'message':'Create and save a seven-dinner plan for this week from the cookbook. Use 2 servings each. Vary the meals, including at least two vegetarian dinners. Read preferences and use your skill CLI to save the schedule; do not approve it.'});print(json.dumps({'planner_submitted':r}),flush=True)
 for _ in range(100):
  time.sleep(3);s=api('state?week='+week);run=next(x for x in s['runs'] if x['id']==r['id'])
  if run['status'] in ('completed','failed','unknown','cancelled'):
   print(json.dumps({'planner_status':run['status'],'output':run['output'],'error':run['error'],'slots':len(s['week']['slots'])}),flush=True);break
 else:raise SystemExit('Planner still active; no duplicate submission.')
w=api('state?week='+week)['week'];assert len(w['slots'])==7,w
if not w['approved']:w=api('week/'+week+'/approve',{'version':w['version']})
r=api('chat',{'role':'shopper','week':week,'message':'Prepare and save groceries for the approved meal plan. Start from grocery_base and apply my preferences. Keep all ingredients unless my preferences explicitly say they are in the pantry. Do not approve groceries.'});print(json.dumps({'shopper_submitted':r}),flush=True)
for _ in range(100):
 time.sleep(3);s=api('state?week='+week);run=next(x for x in s['runs'] if x['id']==r['id'])
 if run['status'] in ('completed','failed','unknown','cancelled'):
  print(json.dumps({'shopper_status':run['status'],'output':run['output'],'error':run['error'],'groceries_saved':bool(s['week']['groceries'])}),flush=True);break
else:raise SystemExit('Shopper still active; no duplicate submission.')
assert s['week']['groceries'] and not s['week']['groceries']['approved']
print('PASS: real planner → app approval → real shopper → pending grocery approval.',flush=True)
