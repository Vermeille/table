const roleName=r=>({cookbook:'Assistant recettes',planner:'Assistant planning',shopper:'Assistant courses',cart:'Assistant Chronodrive'}[r]||r);
const mealName=m=>({breakfast:'Petit-déjeuner',lunch:'Déjeuner',dinner:'Dîner'}[m]||m);
const statusName=s=>({running:'En cours',queued:'En attente',submitting:'Envoi en cours',waiting_for_approval:'À valider',completed:'Terminé',failed:'Échec',unknown:'À vérifier',cancelled:'Annulé',interrupted:'Interrompu',proposed:'À vérifier',approved:'Validé',filling:'Remplissage en cours',review:'À contrôler'}[s]||s);
const searchText=t=>String(t).normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
const $=s=>document.querySelector(s),esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const locationState = new URLSearchParams(location.search);
const initialWeek = locationState.get('week');
let S=null,view=['shopping', 'freezer'].includes(locationState.get('view')) ? locationState.get('view') : 'week',role=view === 'shopping' ? 'cart' : 'planner',week=/^\d{4}-\d{2}-\d{2}$/.test(initialWeek || '') && monday(new Date(initialWeek+'T12:00:00')) === initialWeek ? initialWeek : monday(),query='',chatOpen=false,settingsCache=null,storeOptions=[],lastRuns='',nativePrompts=[],polling=false;
const productDetails=Object.create(null);let imagesLoading=false;
function monday(d=new Date()){d=new Date(d);d.setDate(d.getDate()-(d.getDay()+6)%7);return local(d)}function local(d){return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`}function fmt(d,opts={month:'long',day:'numeric'}){return new Date(d+'T12:00:00').toLocaleDateString('fr-FR',opts)}function dayDate(n){let d=new Date(week+'T12:00:00');d.setDate(d.getDate()+n);return d}function toast(t){$('#toast').textContent=t;$('#toast').style.display='block';setTimeout(()=>$('#toast').style.display='none',6500)}
async function api(path,data){let r=await fetch('/api/'+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json'},body:data===undefined?undefined:JSON.stringify(data)});let j=await r.json();if(r.status===401){login();throw Error(j.detail)}if(!r.ok)throw Error(j.detail||'La demande a échoué');return j}
function login(){S=null;$('#app').innerHTML=`<form class="login" id="login"><div class="eyebrow">Votre cuisine, bien organisée</div><h1>Table<span style="color:var(--accent)">.</span></h1><p class="muted">Les bons repas commencent par un peu d’organisation.</p><label for="password">Mot de passe</label><input id="password" type="password" autocomplete="current-password" required autofocus><button class="primary">Entrer →</button><p id="login-error" role="alert"></p></form>`;$('#login').onsubmit=async e=>{e.preventDefault();try{await api('login',{password:$('#password').value});await refresh()}catch(e){$('#login-error').textContent=e.message}}}
let stateRequest = 0;
let renderedState = '';
let groceryWrites = Promise.resolve(true);
let savingGroceryFields = 0;
const chatDrafts = new Map();
async function refresh(renderAll = true) {
    const id = ++stateRequest;
    const requestedWeek = week;
    const state = await api('state?week=' + requestedWeek);
    if (id !== stateRequest || requestedWeek !== week) return;
    S = state;
    if (renderAll) render();
    else updateChat();
}
function overview() {
    return JSON.stringify([S.week, S.fill_job, S.recipes, S.learning, S.chronodrive_connected, S.freezer, S.kitchen, S.preferences,
        S.runs.filter(run => run.week === week).map(run => [run.id, run.status])]);
}
function emoji(r){let t=(r.title+' '+r.tags.join(' ')).toLowerCase(),kind=/pizza/.test(t)?'pizza':/fish|salmon|poisson|saumon/.test(t)?'fish':/pasta|spaghetti|risotto|pâtes/.test(t)?'pasta':/chicken|poulet/.test(t)?'chicken':'greens';let shapes={pizza:'<path d="M19 48L32 12L51 46Z" fill="#dd9f55"/><path d="M23 43L33 19L46 43Z" fill="#e0bc67"/><circle cx="33" cy="29" r="3" fill="#b9573e"/><circle cx="38" cy="39" r="3" fill="#b9573e"/><path d="M26 39q2-7 6-4q-1 5-6 4" fill="#62845e"/>',fish:'<path d="M17 33q13-20 30-3l7-7v18l-7-7q-17 17-30-1" fill="#d68d72"/><path d="M29 24l-5 18m14-17l-6 19" stroke="#f3cbb7" stroke-width="2"/><circle cx="20" cy="32" r="1.5" fill="#384b3e"/>',pasta:'<path d="M20 27q8-12 21-3t-8 10t-8 10t23-5M19 34q-5 12 12 10t11-13t-15 7" fill="none" stroke="#d7ab54" stroke-width="5" stroke-linecap="round"/><path d="M37 23q8-8 12-2q-3 9-12 2" fill="#638360"/>',chicken:'<path d="M23 20q17-9 22 7q2 14-15 18l-9-11q-2-7 2-14" fill="#b57446"/><path d="M29 36l-9 12m-1-4l-4 3m4 1l-1 5" stroke="#e2ceab" stroke-width="5" stroke-linecap="round"/><path d="M42 43q6-8 10-4q-1 9-10 4" fill="#62845e"/>',greens:'<path d="M18 25q12-13 18 3q-2 11-18-3M35 20q13-3 13 11q-10 5-13-11M22 41q-1-15 13-11q8 12-13 11M38 45q-9-8 4-15q13 7-4 15" fill="#7d9c6c"/><circle cx="24" cy="27" r="4" fill="#c8684f"/><circle cx="42" cy="39" r="4" fill="#c8684f"/><circle cx="35" cy="31" r="3" fill="#ddbd7b"/>'};return `<svg width="62" height="62" viewBox="0 0 64 64" aria-hidden="true"><circle cx="32" cy="32" r="27" fill="#fffdf5"/><circle cx="32" cy="32" r="22" fill="none" stroke="#e4e2d4"/>${shapes[kind]}</svg>`}
function render(){if(!S)return;
    renderedState = overview();
    const previousInput = $('#chat-input');
    if (previousInput) chatDrafts.set(previousInput.dataset.draft, previousInput.value);
    const url = new URL(location.href);
    url.searchParams.set('week', week);
    if (['shopping','freezer'].includes(view)) url.searchParams.set('view', view);
    else url.searchParams.delete('view');
    history.replaceState(null, '', url);
    lastRuns='';const nav=[['week','◷','Cette semaine'],['cookbook','▤','Recettes'],['shopping','⌑','Courses'],['freezer','❄','Congélateur'],['saved','▦','Semaines enregistrées'],['preferences','♡','Préférences'],['skills','✧','Savoir-faire & apprentissage'],['settings','⚙','Connexions']];$('#app').innerHTML=`<div class="shell"><aside class="sidebar"><div class="logo">Table<span>.</span></div><div class="tagline">Moins de « qu’est-ce qu’on mange ? »</div><nav class="nav">${nav.map(([v,i,t])=>`<button data-view="${v}" class="${view===v?'active':''}">${i} &nbsp; ${t}</button>`).join('')}</nav><div class="side-bottom">Pour les repas du quotidien.<br>Vos données restent sur votre serveur.<br><button class="small" data-action="logout">Se déconnecter</button></div></aside><div class="workspace ${['shopping','freezer'].includes(view)?'workflow-workspace':''}"><main class="main">${S.setup_error?`<div class="notice">La configuration est à terminer. Ouvrez Connexions pour installer les profils Hermes.<br>${esc(S.setup_error)}</div>`:''}${main()}</main>${chat()}</div></div><button class="mobile-chat ${['shopping','freezer'].includes(view)?'workflow-chat-toggle':''} ${chatOpen?'chat-visible':''}" data-action="toggle-chat" aria-expanded="${chatOpen}">${chatOpen?'Fermer la discussion':'✧ Assistant cuisine'}</button>`;bind();updateChat();
    $('#chat-input').value = chatDrafts.get($('#chat-input').dataset.draft) || '';
    if(view==='shopping' && shoppingScreen()==='products') hydrateProductImages();
}
function main(){if(view==='week')return weekView();if(view==='cookbook')return cookbook();if(view==='shopping')return shopping();if(view==='freezer')return freezerView();if(view==='saved')return saved();if(view==='preferences')return preferences();if(view==='skills')return skills();return settingsView()}
function heading(eyebrow,title,sub,action=''){return `<div class="topline"><div><div class="eyebrow">${eyebrow}</div><h1>${title}</h1><p class="muted">${sub}</p></div>${action}</div>`}
function weekView() {
    const w = S.week;
    return `<div class="topline plan-heading"><h1 id="flow-title" tabindex="-1">Planning des repas</h1>
        <button data-action="plan-chat">✧ M’aider à planifier</button></div>
        <div class="weeknav">
            <button class="icon" data-action="prev-week" aria-label="Semaine précédente">←</button>
            <strong>${fmt(week)} – ${fmt(local(dayDate(6)), {day:'numeric',month:'short'})}</strong>
            <button class="icon" data-action="next-week" aria-label="Semaine suivante">→</button>
            <input aria-label="Choisir une semaine" id="week-picker" type="date" value="${week}">
        </div>` + weekActions() + batchAgenda() + `<div class="weekgrid ${w.batch ? 'batch-weekgrid' : ''}">${Array.from({length: 7}, (_, day) => {
            const slots = w.slots.filter(slot => slot.day === day);
            return `<section class="day"><div class="day-head"><span>${['Lun','Mar','Mer','Jeu','Ven','Sam','Dim'][day]}</span>
                <span class="day-num">${dayDate(day).getDate()}</span></div>${slots.map(meal).join('')}
                ${slots.length < 3 ? `<div class="empty-slot"><button data-add-day="${day}">+ Choisir un repas</button></div>` : ''}</section>`;
        }).join('')}</div>`;
}
function meal(slot) {
    const recipe = slot.recipe;
    const key = slotKey(slot);
    const locked = (kitchenEvent(slot) && kitchenEvent(slot).action !== 'skip') || S.week.cart?.status === 'filling';
    return `<article class="meal">
        <div class="meal-art" data-recipe="${esc(recipe.id)}" data-slot="${key}">${emoji(recipe)}</div>
        <small>${mealName(slot.meal)}</small>
        <button class="meal-title meal-link" data-recipe="${esc(recipe.id)}" data-slot="${key}">${esc(recipe.title)}</button>
        ${mealSource(slot)}
        <div class="meal-footer"><small>Pour</small><input aria-label="Nombre de personnes pour ${esc(recipe.title)}"
            type="number" min="1" max="100" value="${slot.servings}" data-servings="${key}" ${locked ? 'disabled' : ''}></div>
        <div class="row meal-actions">${mealKitchenControls(slot)}
            ${locked ? '' : `<button class="small" data-swap="${key}">Remplacer ↗</button>
                <button class="small" data-remove="${key}" aria-label="Retirer ce repas">×</button>`}
        </div>
    </article>`;
}
function cookbook(){let rs=S.recipes.filter(r=>searchText(r.title+' '+r.tags.join(' ')).includes(searchText(query)));return heading('Des recettes à garder','Votre carnet de recettes.','Vos plats préférés, et ceux qui le deviendront.',`<button class="primary" data-action="new-recipe">+ Ajouter une recette</button>`)+`<input class="search" id="recipe-search" type="search" placeholder="Rechercher une recette ou une étiquette…" value="${esc(query)}"><div class="recipe-grid">${rs.map(r=>`<article class="recipe-card" tabindex="0" role="button" data-recipe="${r.id}"><div class="recipe-cover">${emoji(r)}</div><div class="recipe-body"><h3>${esc(r.title)}</h3><p class="muted" style="font-size:11px">Pour ${r.servings} · ${r.nutrition.kcal?esc(r.nutrition.kcal)+' kcal / personne':'Valeurs nutritionnelles non estimées'}</p><div class="tags">${r.tags.map(t=>`<span class="tag">${esc(t)}</span>`).join('')}</div></div></article>`).join('')}</div>${!rs.length?'<p class="muted">Aucune recette trouvée. Essayez une autre recherche ou demandez à l’assistant d’en créer.</p>':''}`}
function saved(){return heading('Les semaines se suivent','Vos semaines à retrouver.','Vos plannings conservent les recettes telles que vous les avez validées.')+`<div class="saved-list">${S.weeks.length?S.weeks.slice().reverse().map(w=>`<button data-week="${w.id}"><strong>Semaine du ${fmt(w.id)}</strong><span>${w.count} repas · ${w.approved?'Validée':'Brouillon'} →</span></button>`).join(''):'<div class="panel"><p class="muted">Vos semaines apparaîtront ici dès que vous commencerez à les préparer.</p></div>'}</div>`}
function preferences(){return heading('À votre goût','Vos envies, vos habitudes.','Des indications enregistrées que vos assistants consultent à chaque demande.')+`<form id="preferences-form">${[['planner','Vos repas','Goûts, contraintes alimentaires, nombre de personnes, temps disponible et variété.'],['shopper','Vos courses','Réserves à la maison, quantités à acheter et habitudes de courses.'],['cart','Vos produits','Marques préférées, formats, budget, bio et produits de remplacement.']].map(([id,t,h])=>`<div class="panel"><h2>${t}</h2><p class="muted">${h}</p><textarea name="${id}" rows="5">${esc(S.preferences[id])}</textarea></div>`).join('')}${batchSettingsFields()}<button class="primary">Enregistrer les préférences</button></form>`}
function skills(){return heading('Une cuisine qui apprend','De mieux en mieux, chaque semaine.','Chaque assistant conserve ce qu’il apprend de vos retours. Vous pouvez le modifier ou retrouver une version précédente.')+S.learning.map(l=>`<div class="panel skill-card"><div class="row between"><h2>${roleName(l.id)}</h2><span class="version">Version ${l.version}</span></div><p class="muted">Dites à l’assistant ce qui vous a plu, ou écrivez vos indications ici.</p><textarea rows="5" id="learning-${l.id}">${esc(l.text)}</textarea><div class="row" style="margin-top:12px"><button class="primary" data-learning="${l.id}">Enregistrer les indications</button><button data-history="${l.id}">Historique des versions</button></div></div>`).join('')}
function settingsView(){let s=settingsCache;return heading('Tout est connecté','Les connexions de votre cuisine.','Table conserve vos données et installe ses propres profils dans Hermes.')+(!s?'<p class="muted">Chargement des connexions…</p>':`<div class="settings-grid"><form class="panel full" id="connection-form"><h2>Hermes</h2><p class="muted">Compatible avec une nouvelle instance Hermes. Le volume de données partagé est défini à l’installation ; ces réglages permettent de s’y connecter.</p><label>Adresse de l’API Hermes</label><input name="hermes_url" value="${esc(s.hermes_url)}" required><label>Adresse de Table accessible depuis Hermes</label><input name="app_url" value="${esc(s.app_url)}" required><label>Clé de la passerelle (laisser vide pour conserver)</label><input name="gateway_key" type="password" autocomplete="off"><label>Fournisseur</label><select name="provider"><option value="openai-codex" ${s.provider==='openai-codex'?'selected':''}>Abonnement OpenAI / Codex</option><option value="openai" ${s.provider==='openai'?'selected':''}>API OpenAI / service compatible</option></select><label>Modèle</label><input name="model" value="${esc(s.model)}" required><label>Adresse de base de l’API (facultatif)</label><input name="base_url" value="${esc(s.base_url)}"><label>Clé API du modèle (laisser vide pour conserver)</label><input name="api_key" type="password" autocomplete="off"><div class="row" style="margin-top:20px"><button class="primary">Installer / mettre à jour les profils</button><button type="button" data-action="codex-login">Se connecter avec OpenAI ↗</button></div><div id="oauth"></div></form><form class="panel full" id="chrono-form"><div class="row between"><h2>Chronodrive</h2><span class="badge ${s.chronodrive.connected?'':'warm'}">${s.chronodrive.connected?'Identifiants enregistrés':'Non connecté'}</span></div><p class="muted">Connectez votre compte pour rechercher les produits de votre magasin et préparer votre panier. Vos identifiants sont chiffrés dans Table et ne sont pas communiqués à l’assistant.</p><label>Adresse e-mail</label><input type="email" name="email" autocomplete="username" value="${esc(s.chronodrive.email)}" required><label>Mot de passe ${s.chronodrive.connected?'(laisser vide pour conserver)':''}</label><input name="password" type="password" autocomplete="new-password"><label>Votre magasin Chronodrive</label><select name="store_id" required><option value="">Choisissez votre magasin…</option>${storeOptions.map(x=>`<option value="${esc(x.id)}" ${x.id===s.chronodrive.store_id?'selected':''}>${esc(x.name)}</option>`).join('')}</select><p class="muted" style="font-size:11px;margin-top:8px">La liste provient du site Chronodrive. Aucun identifiant à chercher vous-même.</p><div class="row" style="margin-top:20px"><button class="primary">Enregistrer la connexion Chronodrive</button><button type="button" data-action="test-chrono">Tester la connexion</button></div><p class="muted" style="font-size:11px;margin-top:12px">Enregistrer vos identifiants ne modifie pas votre panier. Les produits et les quantités seront à valider séparément. Vous gardez la main sur la commande.</p></form></div>`)}
function chat(){let title={cookbook:'Votre compagnon de recettes',planner:'Un coup de main en cuisine',shopper:'Votre assistant courses',cart:'Votre assistant Chronodrive'}[role];return `<aside class="chat ${chatOpen?'open':''}"><div class="chat-head"><div class="eyebrow">Un coup de main avec Hermes</div><h3>${title}</h3><p class="muted" style="font-size:11px;margin:0">Échangez, ajustez, régalez-vous.</p><select id="chat-role" aria-label="Assistant">${['cookbook','planner','shopper','cart'].map(r=>`<option value="${r}" ${r===role?'selected':''}>${roleName(r)}</option>`).join('')}</select></div><div class="chat-messages" id="chat-messages"></div><form class="chat-compose" id="chat-form"><textarea id="chat-input" data-draft="${week}/${role}" aria-label="Votre message à l’assistant" placeholder="${role==='cookbook'?'Ajoute plusieurs sortes de pizzas…':role==='planner'?'Une semaine plus légère, avec deux repas végétariens…':role==='shopper'?'On a déjà de l’huile d’olive et du riz…':'Je préfère cette marque. Cherche des formats économiques…'}" required maxlength="15000"></textarea><div class="row"><span class="chat-hint">Les modifications sont enregistrées dans Table.</span><button class="primary small" id="send">Envoyer ↗</button></div></form></aside>`}
function updateChat(){let el=$('#chat-messages');if(!el||!S)return;let runs=S.runs.filter(r=>r.role===role&&r.week===week).slice(0,15).reverse();let signature=JSON.stringify(runs)+role+JSON.stringify(nativePrompts);if(signature===lastRuns)return;lastRuns=signature;el.innerHTML=(!runs.length?`<div class="bubble"><span class="who">${roleName(role)}</span>${role==='planner'?'Dites-moi de quelle semaine vous avez envie. Je préparerai un planning à partir de vos recettes et préférences.':role==='cookbook'?'Enrichissons votre carnet. Demandez de nouvelles recettes, une version plus équilibrée ou une variante à votre goût.':role==='shopper'?'Une fois vos repas validés, je rassemblerai les ingrédients en tenant compte de vos préférences de courses.':'Une fois les courses validées, je chercherai les produits de votre magasin Chronodrive pour vous les proposer.'}</div>`:'')+runs.map(r=>`<div class="bubble user"><span class="who">Vous</span>${esc(r.prompt)}</div><div class="bubble"><span class="who">${esc(role)} · ${statusName(r.status)}</span>${esc(r.output||r.error||(r.status==='running'?'Je m’en occupe…':'En attente…'))}${['running','queued','waiting_for_approval'].includes(r.status)?`<p><button class="small" data-stop="${r.id}">Arrêter</button></p>`:''}</div>`).join('')+nativePrompts.map((p,n)=>`<div class="approval"><strong>${p.kind==='clarify'?'Une question pour vous':'Vérifiez cette action'}</strong><pre>${esc(p.question||p.description||p.command)}</pre>${p.kind==='approval'?`<button class="small" data-native="${n}" data-choice="once">Autoriser une fois</button> <button class="small" data-native="${n}" data-choice="deny">Refuser</button>`:`<input id="clarify-${n}" aria-label="Répondre"><button class="small" data-native="${n}">Répondre</button>`}</div>`).join('');el.scrollTop=el.scrollHeight;let active=runs.some(r=>['running','queued','waiting_for_approval','submitting'].includes(r.status));if($('#send'))$('#send').disabled=active;bindChatActions()}
function bindChatActions(){document.querySelectorAll('[data-stop]').forEach(e=>e.onclick=()=>safe(async()=>{await api(`runs/${e.dataset.stop}/stop`,{});toast('Arrêt demandé')}));document.querySelectorAll('[data-native]').forEach(e=>{let p=structuredClone(nativePrompts[+e.dataset.native]);e.onclick=()=>safe(async()=>{await api(`runs/${p.run_id}/${p.kind}`,{request_id:p.prompt_id,execution_generation:p.execution_generation,choice:e.dataset.choice,answer:$('#clarify-'+e.dataset.native)?.value});nativePrompts=[];lastRuns='';updateChat()})})}
async function safe(fn){try{await fn()}catch(e){toast(e.message)}}
function bind(){
    bindBatch();
    document.querySelectorAll('[data-stage]').forEach(button => button.onclick = () => {
        if (!flowBusy) selectStage(button.dataset.stage);
    });document.querySelectorAll('[data-match-grocery]').forEach(e=>e.onclick=()=>chooseProduct(e.dataset.matchGrocery));document.querySelectorAll('[data-cart-decision]').forEach(e=>e.onclick=()=>safe(()=>cartDecision(e.dataset.groceryId,e.dataset.cartDecision)));document.querySelectorAll('[data-view]').forEach(e=>e.onclick=()=>safe(()=>navigate(e.dataset.view)));document.querySelectorAll('[data-action]').forEach(e=>e.onclick=()=>safe(()=>action(e.dataset.action)));document.querySelectorAll('[data-recipe]').forEach(e=>{e.onclick=()=>showRecipe(e.dataset.recipe,e.dataset.slot);e.onkeydown=k=>{if(k.key==='Enter')e.click()}});document.querySelectorAll('[data-week]').forEach(e=>e.onclick=()=>safe(async()=>{week=e.dataset.week;view='week';await refresh()}));document.querySelectorAll('[data-add-day]').forEach(e=>e.onclick=()=>pickMeal(+e.dataset.addDay));document.querySelectorAll('[data-swap]').forEach(e=>e.onclick=()=>{let [d,m]=e.dataset.swap.split('-');pickMeal(+d,m)});document.querySelectorAll('[data-remove]').forEach(e=>e.onclick=()=>safe(async()=>{await saveSlots(S.week.slots.filter(s=>`${s.day}-${s.meal}`!==e.dataset.remove))}));document.querySelectorAll('[data-servings]').forEach(e=>e.onchange=()=>safe(async()=>{let slots=structuredClone(S.week.slots);slots.find(s=>`${s.day}-${s.meal}`===e.dataset.servings).servings=+e.value;await saveSlots(slots)}));
 if($('#week-picker'))$('#week-picker').onchange=e=>safe(async()=>{if(!e.target.value||flowBusy)return;week=monday(new Date(e.target.value+'T12:00:00'));flowError='';await refresh()});if($('#recipe-search'))$('#recipe-search').oninput=e=>{query=e.target.value;let pos=e.target.selectionStart;render();$('#recipe-search').focus();$('#recipe-search').setSelectionRange(pos,pos)};
 if($('#chat-role'))$('#chat-role').onchange=e=>{role=e.target.value;nativePrompts=[];lastRuns='';render()};if($('#chat-form'))$('#chat-form').onsubmit=e=>{e.preventDefault();safe(async()=>{let message=$('#chat-input').value;await api('chat',{role,week,message});$('#chat-input').value='';await refresh(false)})};
 if($('#preferences-form'))$('#preferences-form').onsubmit=e=>{e.preventDefault();safe(async()=>{await api('preferences',readPreferences(e.target));await refresh();toast('Préférences enregistrées')})};document.querySelectorAll('[data-learning]').forEach(e=>e.onclick=()=>safe(async()=>{let id=e.dataset.learning;await api('learning/'+id,{text:$('#learning-'+id).value,version:S.learning.find(l=>l.id===id).version});await refresh();toast('Indications enregistrées et transmises à Hermes')}));document.querySelectorAll('[data-history]').forEach(e=>e.onclick=()=>safe(async()=>{let id=e.dataset.history,h=await api('learning/'+id+'/history');modal(`<h2>${roleName(id)} · historique des versions</h2>${h.map(x=>`<div class="panel"><div class="row between"><strong>Version ${x.version}</strong><small>${esc(x.at)}</small></div><p style="white-space:pre-wrap">${esc(JSON.parse(x.data).text||'Aucune indication')}</p><button data-restore="${x.version}">Restaurer cette version</button></div>`).join('')}`);document.querySelectorAll('[data-restore]').forEach(b=>b.onclick=()=>safe(async()=>{let x=h.find(x=>x.version===+b.dataset.restore);await api('learning/'+id,{text:JSON.parse(x.data).text,version:S.learning.find(l=>l.id===id).version});$('#modal').close();await refresh()}))}));
 for (const field of ['name', 'quantity', 'unit', 'check']) {
     document.querySelectorAll(`[data-grocery-${field}]`).forEach(input => {
         input.onchange = () => {
             const item = S.week.groceries.items[+input.getAttribute('data-grocery-' + field)];
             const value = field === 'check' ? input.checked : field === 'quantity' ? +input.value : input.value;
             if (!input.checkValidity() || (field === 'name' && !value.trim())) {
                 toast('Indiquez un ingrédient et une quantité positive.');
                 input.value = item[field];
                 return;
             }
             if (field === 'check') input.closest('.grocery').classList.toggle('checked', value);
             queueGroceryEdit(item.id, field === 'check' ? 'checked' : field, value);
         };
     });
 }
 document.querySelectorAll('[data-grocery-remove]').forEach(button => button.onclick = () => safe(async () => {
     const id = S.week.groceries.items[+button.dataset.groceryRemove].id;
     if (!await groceryWrites || flowBusy) return;
     await grocerySave(S.week.groceries.items.filter(item => item.id !== id));
 }));
 if($('#connection-form'))$('#connection-form').onsubmit=e=>{e.preventDefault();safe(async()=>{await api('settings',Object.fromEntries(new FormData(e.target)));settingsCache=await api('settings');await refresh();toast('Les quatre profils sont installés')})};if($('#chrono-form'))$('#chrono-form').onsubmit=e=>{e.preventDefault();safe(async()=>{await api('chronodrive',Object.fromEntries(new FormData(e.target)));settingsCache=await api('settings');await refresh();toast('Identifiants Chronodrive enregistrés')})};}
function productPhoto(id){return `<div class="product-image" data-product-id="${esc(id)}" aria-label="Photo du produit"><span aria-hidden="true">▧</span></div>`}
function paintProductImages(){document.querySelectorAll('.product-image[data-product-id]').forEach(el=>{const product=productDetails[el.dataset.productId];if(!product?.image_url||el.querySelector('img'))return;const img=document.createElement('img');img.src=product.image_url;img.alt=product.name||'Produit Chronodrive';img.loading='lazy';img.decoding='async';img.referrerPolicy='no-referrer';img.onerror=()=>{img.remove();el.textContent='▧';el.title='Visuel indisponible'};el.replaceChildren(img)})}
async function hydrateProductImages(){paintProductImages();const ids=[...new Set((S?.week.cart?.matches||[]).map(m=>m.productId))].filter(id=>!(id in productDetails));if(imagesLoading||!ids.length)return;imagesLoading=true;try{for(let n=0;n<ids.length;n+=60){const batch=ids.slice(n,n+60);const products=await api('chronodrive/products',{ids:batch});for(const id of batch)productDetails[id]={};for(const product of products)productDetails[product.productId]=product;paintProductImages()}}catch(e){for(const id of ids)productDetails[id]??={};toast('Les photos sont temporairement indisponibles. La sélection reste consultable.')}finally{imagesLoading=false;if(view==='shopping'&&(S?.week.cart?.matches||[]).some(m=>!(m.productId in productDetails)))hydrateProductImages()}}
async function cartDecision(id, action, extra = {}) {
    const wasCart = shoppingScreen() === 'cart';
    await api(`week/${week}/cart-item`, {version:S.week.version, grocery_id:id, action, ...extra});
    await refresh();
    if (wasCart) selectStage('products');
}
function chooseProduct(id){const item=S.week.groceries.items.find(i=>i.id===id);modal(`<h2>Choisir un produit</h2><p>${esc(item.name)} · ${item.quantity} ${esc(item.unit)} à prévoir</p><form id="product-search-form" class="row"><input id="product-query" aria-label="Rechercher un produit Chronodrive" value="${esc(item.name)}" required><button class="primary">Rechercher</button></form><p id="product-search-status" class="muted"></p><div id="product-results"></div>`);let sequence=0;const find=async()=>{const input=$('#product-query'),request=++sequence;const query=input.value;$('#product-search-status').textContent='Recherche dans votre magasin…';const products=await api('chronodrive/search?query='+encodeURIComponent(query));if(request!==sequence||!$('#modal').open||$('#product-query')!==input)return;$('#product-search-status').textContent=products.length?'Choisissez le nombre de paquets à acheter.':'Aucun produit trouvé. Essayez un autre terme.';$('#product-results').innerHTML=products.map((x,n)=>{productDetails[x.productId]=x;return `<div class="product product-search-result">${productPhoto(x.productId)}<div class="product-info"><strong>${esc(x.name)}</strong><p>${esc(x.brand)} · ${esc(x.size)} · ${esc(x.price??'—')} €</p>${x.stock==='NO_STOCK'?'<p class="muted">Indisponible dans ce magasin</p>':''}<div class="row"><label for="product-quantity-${n}">Paquets</label><input id="product-quantity-${n}" type="number" min="1" max="100" value="1" style="width:75px"><button class="primary small" data-select-product="${n}" ${x.stock==='NO_STOCK'?'disabled':''}>Choisir</button></div></div></div>`}).join('');paintProductImages();document.querySelectorAll('[data-select-product]').forEach(button=>button.onclick=()=>safe(async()=>{const n=+button.dataset.selectProduct;await cartDecision(id,'match',{productId:products[n].productId,quantity:+$('#product-quantity-'+n).value});$('#modal').close()}))};$('#product-search-form').onsubmit=e=>{e.preventDefault();safe(find)};safe(find)}
async function navigate(v){
    if (flowBusy) return;
    if (savingGroceryFields) await groceryWrites;
    if (v === 'shopping') {
        selectStage(currentStage() === 'week' ? 'groceries' : currentStage());
        return;
    }
    flowError = '';
    view=v;if(v==='cookbook')role='cookbook';if(v==='week')role='planner';nativePrompts=[];lastRuns='';if(v==='settings'){settingsCache=await api('settings');try{storeOptions=await api('chronodrive/stores')}catch(e){storeOptions=[];toast(e.message)}}render()}
async function saveSlots(slots) {
    const fields = slots.map(({day, meal, recipe_id, servings, freezer_lot_id, cook_fresh}) =>
        ({day, meal, recipe_id, servings, freezer_lot_id, cook_fresh}));
    await api(`week/${week}/save`, {version:S.week.version, slots:fields});
    await refresh();
}
async function grocerySave(items){await api(`week/${week}/groceries`,{version:S.week.version,items});await refresh()}

function queueGroceryEdit(id, field, value) {
    const editingWeek = week;
    savingGroceryFields++;
    groceryWrites = groceryWrites.then(async () => {
        try {
            if (!S || S.week.id !== editingWeek || week !== editingWeek) return false;
            stateRequest++;
            const w = S.week;
            const items = w.groceries.items.map(item => item.id === id ? {...item, [field]:value} : item);
            const updated = await api(`week/${editingWeek}/groceries`, {version:w.version, items});
            if (S?.week.id !== editingWeek || week !== editingWeek) return false;
            S.week = updated;
            // Update the totals immediately and leave focus in the active field.
            const summary = $('#grocery-count');
            if (summary) summary.textContent = groceryCount(S.week.groceries);
            if (w.groceries.approved && !flowBusy) render();
            return true;
        } catch (error) {
            toast(error.message);
            await refresh().catch(() => {});
            return false;
        } finally {
            savingGroceryFields--;
        }
    });
}
async function wf(action){await api(`week/${week}/${action}`,{version:S.week.version});await refresh()}
async function action(a) {
    if (flowBusy) return;
    if (['continue-shopping', 'go-products', 'edit-groceries', 'stop-editing-groceries', 'approve-week',
         'prepare-groceries', 'approve-groceries', 'find-products', 'approve-and-fill',
         'fill-cart', 'resume-fill', 'pause-fill', 'reopen-cart'].includes(a)) {
        return shoppingAction(a);
    }
    if (a === 'logout') { await api('logout', {}); chatDrafts.clear(); login(); return; }
    if (a === 'toggle-chat') { chatOpen = !chatOpen; render(); return; }
    if (a === 'prev-week' || a === 'next-week') {
        week = local(dayDate(a === 'prev-week' ? -7 : 7));
        flowError = '';
        await refresh();
        return;
    }
    if (a === 'refresh-batch') {
        if (!S.week.approved) return saveSlots(S.week.slots);
        modal('<h2>Adapter le planning au congélateur</h2><p>Cette adaptation demandera de valider de nouveau les repas et les courses.</p><button class="primary" id="apply-batch">Adapter le planning</button>');
        $('#apply-batch').onclick = () => safe(async () => {
            await saveSlots(S.week.slots);
            $('#modal').close();
        });
        return;
    }
    if (a === 'new-recipe') { editRecipe(); return; }
    if (a === 'grocery-base') return flowRequest(a, () => wf('groceries'));
    if (a === 'add-grocery') {
        if (!await groceryWrites || flowBusy) return;
        await grocerySave([...S.week.groceries.items, {
            id: crypto.randomUUID(), name: 'Nouvel article', quantity: 1, unit: 'pièce', checked: false, note: ''
        }]);
        const input = [...document.querySelectorAll('[data-grocery-name]')].at(-1);
        input?.focus();
        input?.select();
        return;
    }
    if (['plan-chat', 'shopper-chat', 'match-chat'].includes(a)) {
        role = {'plan-chat':'planner', 'shopper-chat':'shopper', 'match-chat':'cart'}[a];
        chatOpen = true;
        nativePrompts = [];
        render();
        if (a === 'plan-chat' && !$('#chat-input').value) {
            $('#chat-input').value = S.preferences.batch?.enabled
                ? 'Prépare sept dîners avec mes préférences et mon stock. Répartis les jours de cuisine et propose des plats à congeler pour les repas suivants.'
                : 'Prépare sept dîners pour cette semaine à partir de mes préférences et de mes recettes.';
        }
        if (!activeRunStatuses.has(latestRun(role)?.status)) $('#chat-input').focus();
        return;
    }
    if(a==='test-chrono'){let r=await api('chronodrive/test',{});toast('Connecté à Chronodrive · '+r.items.length+' produits dans votre panier');return}if(a==='codex-login'){let r=await api('codex/start',{});$('#oauth').innerHTML=`<div class="notice" style="margin-top:15px">Saisissez <strong>${esc(r.user_code)}</strong> sur <a target="_blank" rel="noreferrer" href="${esc(r.verification_url)}">Connexion OpenAI ↗</a><p id="oauth-status">En attente de connexion…</p></div>`;let timer=setInterval(async()=>{try{let s=await api('codex/status/'+r.session_id);if(s.status==='approved'){clearInterval(timer);$('#oauth-status').textContent='Connexion réussie. Sélectionnez OpenAI/Codex et installez les profils.'}else if(s.status==='error'){clearInterval(timer);$('#oauth-status').textContent=s.error||'La connexion a échoué'}}catch(e){clearInterval(timer);toast(e.message)}},5000);setTimeout(()=>clearInterval(timer),900000)}}
function modal(html){$('#modal').innerHTML=`<div class="row between" style="margin-bottom:20px"><span class="eyebrow" style="margin:0">Table · votre cuisine</span><button id="close-modal" aria-label="Fermer">×</button></div>`+html;$('#close-modal').onclick=()=>$('#modal').close();if(!$('#modal').open)$('#modal').showModal()}
function pickMeal(day,meal){let used=S.week.slots.filter(s=>s.day===day).map(s=>s.meal);meal=meal||['dinner','lunch','breakfast'].find(m=>!used.includes(m));modal(`<h2>${used.includes(meal)?'Remplacer ce repas :':'Choisir un repas :'} ${mealName(meal)}</h2>${stockLots().some(lot=>lot.available>0)?'<button class="small freezer-pick" id="pick-frozen">Choisir dans le congélateur</button>':''}<input id="pick-search" class="search" placeholder="Rechercher dans vos recettes…" autofocus><div id="pick-results"></div>`);let results=()=>{$('#pick-results').innerHTML=S.recipes.filter(r=>searchText(r.title+' '+r.tags.join(' ')).includes(searchText($('#pick-search').value))).map(r=>`<button style="display:block;width:100%;text-align:left;margin:7px 0" data-pick="${r.id}">${emoji(r)} &nbsp; ${esc(r.title)} <small class="muted">· pour ${r.servings}</small></button>`).join('');document.querySelectorAll('[data-pick]').forEach(e=>e.onclick=()=>safe(async()=>{let old=S.week.slots.find(s=>s.day===day&&s.meal===meal),r=S.recipes.find(r=>r.id===e.dataset.pick);await saveSlots([...S.week.slots.filter(s=>!(s.day===day&&s.meal===meal)),{day,meal,recipe_id:r.id,servings:old?.servings||r.servings}]);$('#modal').close()}))};$('#pick-search').oninput=results;
    if ($('#pick-frozen')) $('#pick-frozen').onclick = () => selectFrozenMeal(day, meal, S.week.slots.find(slot=>slot.day===day&&slot.meal===meal)?.servings || 2);
    results()
}
function showRecipe(id, key) {
    const slot = key ? S.week.slots.find(slot => slotKey(slot) === key) : null;
    const recipe = slot?.recipe || S.recipes.find(item => item.id === id);
    if (!recipe) return;
    const task = slot ? slotTask(slot) : null;
    const event = slot ? kitchenEvent(slot) : null;
    const frozen = ['stock', 'batch'].includes(task?.source);
    const cook = event?.action === 'freeze' ? slot.servings + event.quantity
        : task?.quantity ?? slot?.servings ?? recipe.servings;
    const quantity = new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 3});
    const planNote = frozen ? `<p class="recipe-freezer"><strong>Du congélateur</strong> · ${portionLabel(slot.servings)} pour ce repas</p>`
        : task?.freeze ? `<p class="recipe-freezer"><strong>${portionLabel(cook)} à cuisiner</strong> · ${slot.servings} pour ce repas et ${event?.quantity ?? task.freeze} à congeler</p>` : '';
    if (recipe.freezer_only) {
        modal(`<h2>${esc(recipe.title)}</h2>${planNote}<p>Plat déjà préparé dans votre congélateur.</p>`);
        return;
    }
    const ingredients = `<h2>Les ingrédients</h2><ul class="ingredients">${recipe.ingredients.map(item =>
        `<li><strong>${quantity.format(item.quantity * cook / recipe.servings)} ${esc(item.unit)}</strong> &nbsp; ${esc(item.name)}</li>`
    ).join('')}</ul><h2>En cuisine</h2><div class="recipe-detail">${esc(recipe.method)}</div>`;
    modal(`<div class="eyebrow">${recipe.tags.map(esc).join(' · ')}</div><h1>${esc(recipe.title)}</h1>
        <p class="muted">Pour ${quantity.format(cook)}${slot ? ' · Recette enregistrée avec cette semaine' : ''}</p>${planNote}
        <div class="nutrition">${[['kcal','kcal'],['protein_g','g de protéines'],['carbs_g','g de glucides'],['fat_g','g de lipides']]
            .map(([k,unit]) => `<div><b>${esc(recipe.nutrition[k] ?? '—')}</b><span>${unit} / personne</span></div>`).join('')}</div>
        <p class="muted" style="font-size:11px">${esc(recipe.nutrition_note)}</p>
        ${recipe.freezer_ok ? `<p class="recipe-freezer"><strong>Adaptée à la congélation</strong>${recipe.freezer_note ? ' · ' + esc(recipe.freezer_note) : ''}</p>` : ''}
        ${frozen ? `<details class="batch-list"><summary>Voir la recette du plat</summary>${ingredients}</details>` : ingredients}
        <div class="row batch-form-actions">
            <button id="edit-recipe">Modifier la recette du carnet</button>
            <a href="/api/recipes/${esc(recipe.id)}/markdown" download>Télécharger en Markdown</a>
            <button id="discuss-recipe">✧ Imaginer une variante</button>
        </div>`);
    $('#edit-recipe').onclick = () => editRecipe(S.recipes.find(item => item.id === recipe.id));
    $('#discuss-recipe').onclick = () => {
        $('#modal').close();
        role = 'cookbook';
        chatOpen = true;
        lastRuns = '';
        render();
        $('#chat-input').value = `J’aimerais une variante de « ${recipe.title} ». `;
        $('#chat-input').focus();
    };
}
function editRecipe(r){r=r||{id:'',version:0,title:'',servings:2,ingredients:[],tags:[],nutrition:{},method:''};modal(`<h2>${r.id?'Modifier la recette':'Une nouvelle recette à aimer'}</h2><form id="recipe-form"><label>Titre</label><input name="title" value="${esc(r.title)}" required style="width:100%"><div class="row"><div><label>Identifiant de la recette</label><input name="id" value="${esc(r.id)}" pattern="[a-z0-9][a-z0-9-]{0,79}" ${r.id?'readonly':''} placeholder="soupe-de-lentilles"></div><div><label>Nombre de personnes</label><input name="servings" type="number" min="1" max="100" value="${r.servings}" required></div></div><label>Ingrédients · une ligne par ingrédient : quantité | unité | nom</label><textarea name="ingredients" rows="6" required placeholder="200 | g | lentilles">${r.ingredients.map(i=>`${i.quantity} | ${i.unit} | ${i.name}`).join('\n')}</textarea><label>Étiquettes · séparées par des virgules</label><input name="tags" value="${esc(r.tags.join(', '))}" style="width:100%"><label>Valeurs estimées par personne · kcal | protéines (g) | glucides (g) | lipides (g)</label><input name="nutrition" value="${['kcal','protein_g','carbs_g','fat_g'].map(k=>r.nutrition[k]??'').join(' | ')}" style="width:100%"><label>Préparation</label><textarea name="method" rows="8" required>${esc(r.method)}</textarea><fieldset class="recipe-freezer-fields"><legend>Congélation</legend><label class="check-row"><input type="checkbox" name="freezer_ok" ${r.freezer_ok?'checked':''}> Le plat complet se congèle bien</label><label>Conseil pour la congélation ou le réchauffage<textarea name="freezer_note" rows="2" maxlength="500">${esc(r.freezer_note||'')}</textarea></label></fieldset><button class="primary" style="margin-top:15px">Enregistrer la recette</button></form>`);$('#recipe-form').onsubmit=e=>{e.preventDefault();safe(async()=>{let f=Object.fromEntries(new FormData(e.target)),n=f.nutrition.split('|').map(x=>x.trim()),nutrition={};['kcal','protein_g','carbs_g','fat_g'].forEach((k,i)=>{if(n[i])nutrition[k]=+n[i]});await api('recipes',{...f,id:f.id||undefined,version:r.version,freezer_ok: e.target.elements.freezer_ok.checked,servings:+f.servings,ingredients:f.ingredients.split('\n').filter(x=>x.trim()).map(x=>{let [q,u,...name]=x.split('|');return {quantity:+q.trim(),unit:(u||'').trim(),name:name.join('|').trim()}}),tags:f.tags.split(',').map(x=>x.trim()).filter(Boolean),nutrition});$('#modal').close();await refresh();toast('Recette enregistrée')})}}
async function tick() {
    if (!S || polling || flowBusy || savingGroceryFields || document.hidden) return;
    polling = true;
    try {
        await refresh(false);
        if (!S || flowBusy || savingGroceryFields) return;
        if (renderedState !== overview() && !$('#modal').open &&
            !document.activeElement?.matches('input,textarea,select')) render();
        const screen = view === 'shopping' ? shoppingScreen() : '';
        const observedRole = screen === 'groceries' && !chatOpen ? 'shopper' : screen === 'products' && !chatOpen ? 'cart' : role;
        const active = S.runs.find(run => run.role === observedRole && run.week === week &&
            ['running', 'waiting_for_approval'].includes(run.status));
        if (active) {
            try {
                const snapshot = await api('runs/' + active.id + '/native');
                if (active.week === week && (active.role === role || (view === 'shopping' && !chatOpen))) {
                    const prompts = (snapshot.prompts || []).map(prompt => ({...prompt, run_id: active.id}));
                    const changed = JSON.stringify(prompts) !== JSON.stringify(nativePrompts);
                    nativePrompts = prompts;
                    if (changed && view === 'shopping' && !chatOpen && !$('#modal').open && !flowBusy) render();
                    else updateChat();
                }
            } catch {}
        } else if (nativePrompts.length) {
            nativePrompts = [];
            lastRuns = '';
            updateChat();
        }
    } catch {} finally {
        polling = false;
    }
}
refresh().catch(()=>{});setInterval(tick,3000);
