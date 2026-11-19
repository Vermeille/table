const activeRunStatuses = new Set(['submitting', 'queued', 'running', 'waiting_for_approval']);
const flowLabels = {week: 'Repas', groceries: 'Courses', products: 'Produits', cart: 'Panier'};
const driveLink = '<a class="drive-link" href="https://www.chronodrive.com" target="_blank" rel="noreferrer">Ouvrir Chronodrive ↗</a>';
const euro = new Intl.NumberFormat('fr-FR', {style: 'currency', currency: 'EUR'});
let shoppingStage = null;
let editingGroceries = false;
let flowBusy = '';
let flowError = '';

function currentStage() {
    const {week: w, fill_job: job} = S;
    if (!w.approved) return 'week';
    if (!w.groceries?.approved) return 'groceries';
    if (job || ['filling', 'review'].includes(w.cart?.status)) return 'cart';
    return 'products';
}

function shoppingScreen() {
    if (!S.week.approved) return 'week';
    if (shoppingStage === 'groceries') return 'groceries';
    if (shoppingStage === 'products' && S.week.groceries?.approved) return 'products';
    return currentStage();
}

function workflowNav(selected) {
    const w = S.week;
    const done = {week: w.approved, groceries: w.groceries?.approved,
        products: ['approved', 'filling', 'review'].includes(w.cart?.status),
        cart: S.fill_job?.status === 'completed'};
    const available = {week: true, groceries: w.approved, products: w.groceries?.approved,
        cart: currentStage() === 'cart'};
    return `<nav class="flow-nav" aria-label="Étapes de la semaine">${Object.entries(flowLabels).map(([id, label], index) =>
        `<button data-stage="${id}" ${selected === id ? 'aria-current="step"' : ''} ${available[id] && !flowBusy ? '' : 'disabled'}>
            <span class="flow-index" aria-hidden="true">${done[id] && selected !== id ? '✓' : index + 1}</span><span>${label}</span>
        </button>`).join('')}</nav>`;
}

function flowButton(action, label, {primary = false, disabled = false} = {}) {
    const busyLabel = flowBusy === action ? '<span class="flow-spinner" aria-hidden="true"></span> ' : '';
    return `<button class="${primary ? 'primary' : ''}" data-action="${action}" ${disabled || flowBusy ? 'disabled' : ''}>${busyLabel}${label}</button>`;
}

function flowActions(title, detail, controls) {
    return `<div class="flow-actions">
        <div><strong>${title}</strong>${detail ? `<small>${detail}</small>` : ''}</div>
        <div class="flow-controls">${controls}</div>
    </div>`;
}

function flowAlert() {
    return flowError ? `<p class="notice flow-error" role="alert">${esc(flowError)}</p>` : '';
}

function weekActions() {
    const w = S.week;
    const label = w.slots.length === 1 ? '1 repas prévu' : `${w.slots.length} repas prévus`;
    const next = w.approved
        ? flowButton('continue-shopping', currentStage() === 'cart' ? 'Voir le panier →' : 'Continuer les courses →', {primary: true})
        : flowButton('approve-week', 'Valider les repas et préparer les courses →', {primary: true, disabled: !w.slots.length});
    return workflowNav('week') + flowActions(label, w.approved ? 'Semaine validée' : '', next) + flowAlert();
}

function shopping() {
    const screen = shoppingScreen();
    const titles = {week: 'Les courses', groceries: 'Liste de courses', products: 'Sélection Chronodrive', cart: 'Panier Chronodrive'};
    const body = screen === 'week'
        ? flowActions('Vos repas sont encore en préparation', '', '<button class="primary" data-stage="week">Voir les repas →</button>')
        : screen === 'groceries' ? groceryStage()
        : screen === 'products' ? productStage()
        : cartStage();
    return `<div class="shopping-heading">
        <div class="row between"><p class="flow-date">Semaine du ${fmt(week)} – ${fmt(local(dayDate(6)), {day:'numeric',month:'short'})}</p>
        <button class="small" data-action="toggle-chat" aria-expanded="${chatOpen}">${chatOpen ? 'Fermer la discussion' : '✧ Assistant'}</button></div>
        <h1 id="flow-title" tabindex="-1">${titles[screen]}</h1></div>
        ${workflowNav(screen)}${flowAlert()}${body}`;
}

function latestRun(assistant) {
    return S.runs.find(run => run.role === assistant && run.week === S.week.id);
}

function assistantStatus(assistant, busyText, waitingForResult = true) {
    const run = latestRun(assistant);
    if (!run) return '';
    if (activeRunStatuses.has(run.status)) {
        const approval = run.status === 'waiting_for_approval' || nativePrompts.some(prompt => prompt.run_id === run.id);
        return `<div class="flow-status" role="status">
            ${approval ? '' : '<span class="flow-spinner" aria-hidden="true"></span>'}
            <div><strong>${approval ? 'L’assistant attend votre réponse' : busyText}</strong><small>${approval ? 'Ouvrez la discussion pour continuer.' : 'Cette étape se poursuit si vous quittez la page.'}</small></div>
            ${flowButton(assistant === 'shopper' ? 'shopper-chat' : 'match-chat', 'Voir la discussion')}
        </div>`;
    }
    if (waitingForResult) {
        const text = run.error || (run.status === 'completed'
            ? 'L’assistant n’a pas enregistré de liste. Consultez sa réponse ou relancez la préparation.'
            : 'La préparation est interrompue. Vous pouvez réessayer.');
        return `<p class="notice">${esc(text)} ${flowButton(assistant === 'shopper' ? 'shopper-chat' : 'match-chat', 'Voir la discussion')}</p>`;
    }
    return '';
}

function groceryCount(groceries) {
    const required = groceries.items.filter(item => !item.checked).length;
    return `${required} à acheter · ${groceries.items.length - required} en réserve`;
}

function groceryStage() {
    const g = S.week.groceries;
    const busy = activeRunStatuses.has(latestRun('shopper')?.status);
    const status = assistantStatus('shopper', 'Préparation des courses…', !g);
    if (!g) {
        const controls = flowButton('prepare-groceries', 'Préparer avec l’assistant', {primary: true, disabled: busy})
            + flowButton('grocery-base', 'Calculer les quantités des recettes', {disabled: busy});
        return flowActions('Rassembler les ingrédients', '', controls) + status;
    }
    const required = g.items.filter(item => !item.checked).length;
    const summary = `<span id="grocery-count">${groceryCount(g)}</span>`;
    const edit = !g.approved || editingGroceries;
    let controls;
    if (g.approved) {
        controls = edit ? flowButton('stop-editing-groceries', 'Terminer')
            : flowButton('edit-groceries', 'Modifier la liste', {disabled: S.week.cart?.status === 'filling'})
                + flowButton('go-products', 'Voir les produits →', {primary: true});
    } else {
        const label = !required ? 'Valider les courses' : S.chronodrive_connected === false
            ? 'Valider les courses →' : 'Valider les courses et chercher les produits →';
        controls = flowButton('approve-groceries', label, {primary: true, disabled: busy});
    }
    const header = flowActions(summary, g.approved ? 'Liste validée' : 'Cochez les ingrédients déjà en réserve.', controls);
    if (!edit) {
        return header + `<ul class="grocery-summary">${g.items.map(item =>
            `<li><span>${esc(item.name)}${item.checked ? ' <small>En réserve</small>' : ''}</span><span>${item.quantity} ${esc(item.unit)}</span></li>`).join('')}</ul>`;
    }
    return header + status + (g.approved ? '<p class="notice">Une modification de la liste demandera de valider à nouveau les courses et les produits.</p>' : '')
        + `<section class="panel grocery-panel">
            <div class="grocery" aria-hidden="true"><small>Stock</small><small>Ingrédient</small><small>Qté</small><small>Unité</small></div>
            <div class="shopping-list">${g.items.map((item, i) =>
                `<div class="grocery ${item.checked ? 'checked' : ''}">
                    <input type="checkbox" aria-label="Déjà en réserve : ${esc(item.name)}" data-grocery-check="${i}" ${item.checked ? 'checked' : ''} ${busy || flowBusy ? 'disabled' : ''}>
                    <input aria-label="Ingrédient" data-grocery-name="${i}" value="${esc(item.name)}" ${busy || flowBusy ? 'disabled' : ''}>
                    <input aria-label="Quantité" type="number" min="0.001" step="any" data-grocery-quantity="${i}" value="${item.quantity}" ${busy || flowBusy ? 'disabled' : ''}>
                    <input aria-label="Unité" data-grocery-unit="${i}" value="${esc(item.unit)}" ${busy || flowBusy ? 'disabled' : ''}>
                    <button class="icon" data-grocery-remove="${i}" aria-label="Retirer ${esc(item.name)}" ${busy || flowBusy ? 'disabled' : ''}>×</button>
                </div>${item.note ? `<small class="muted grocery-note">${esc(item.note)}</small>` : ''}`).join('')}</div>
            <div class="row grocery-tools">${flowButton('add-grocery', '+ Ajouter un article', {disabled: busy})}
                ${flowButton('shopper-chat', 'Ajuster avec l’assistant')}${g.approved ? flowButton('stop-editing-groceries', 'Terminer') : ''}</div>
        </section>`;
}

function productStage() {
    const w = S.week;
    const c = w.cart;
    const busy = activeRunStatuses.has(latestRun('cart')?.status);
    const status = assistantStatus('cart', 'Recherche des produits dans votre magasin…', !c);
    const required = w.groceries.items.filter(item => !item.checked);
    if (!required.length) {
        return flowActions('Aucun ingrédient à commander', 'Les courses sont validées.', flowButton('edit-groceries', 'Revoir la liste'));
    }
    if (!c && S.chronodrive_connected === false) {
        return flowActions('Connectez votre compte Chronodrive', 'Choisissez votre magasin pour rechercher les produits.',
            '<button class="primary" data-view="settings">Ouvrir les connexions →</button>');
    }
    if (!c) {
        return flowActions(`${required.length} ingrédient${required.length === 1 ? '' : 's'} à trouver`, '',
            flowButton('find-products', 'Trouver les produits Chronodrive', {primary: true, disabled: busy})) + status;
    }
    return cartPanel(w, busy, status);
}

function productCard(match, ingredient, editable) {
    const price = Number.isFinite(match.price) ? euro.format(match.price) : '';
    return `<article class="product">
        ${productPhoto(match.productId)}
        <div class="product-info">
            ${ingredient ? `<small class="product-source">${esc(ingredient.name)} · ${ingredient.quantity} ${esc(ingredient.unit)}</small>` : ''}
            <strong>${esc(match.name)}</strong>
            <div class="product-format">${[match.brand, match.size].filter(Boolean).map(esc).join(' · ')}</div>
            <div class="product-quantity">${match.quantity} paquet${match.quantity === 1 ? '' : 's'}${price ? ` · ${price} / paquet` : ''}</div>
            ${editable && ingredient ? `<button class="product-change" data-match-grocery="${esc(ingredient.id)}" aria-label="Remplacer ${esc(match.name)}">Remplacer</button>` : ''}
        </div>
    </article>`;
}

function cartPanel(w, busy, status) {
    const c = w.cart;
    const items = Object.fromEntries(w.groceries.items.map(item => [item.id, item]));
    const unresolved = (c.unmatched || []).filter(id => items[id]);
    const packs = c.matches.reduce((sum, item) => sum + item.quantity, 0);
    const subtotal = c.matches.reduce((sum, item) => sum + item.quantity * item.price, 0);
    const estimate = packs && c.matches.every(item => Number.isFinite(item.price)) ? `${euro.format(subtotal)} estimés` : '';
    const summary = `${c.matches.length} sélection${c.matches.length === 1 ? '' : 's'} · ${packs} paquet${packs === 1 ? '' : 's'}`;
    const editable = ['proposed', 'approved'].includes(c.status) && !busy && !flowBusy;
    let next;
    if (c.status === 'proposed') {
        next = flowButton('approve-and-fill', 'Valider et remplir le panier →', {primary: true, disabled: !!unresolved.length || !packs || busy || S.chronodrive_connected === false});
    } else if (c.status === 'approved') {
        next = flowButton('fill-cart', 'Remplir le panier validé →', {primary: true, disabled: busy});
    } else {
        next = (c.status === 'review' ? flowButton('reopen-cart', 'Modifier la sélection') : '')
            + '<button class="primary" data-stage="cart">Voir le panier →</button>';
    }
    const missingCount = unresolved.length;
    const blocker = missingCount ? `${missingCount} ingrédient${missingCount === 1 ? '' : 's'} à traiter` : '';
    return flowActions(summary, [estimate, blocker].filter(Boolean).join(' · '), next) + status
        + (missingCount ? `<section class="panel missing-products"><h2>${blocker}</h2>
            ${unresolved.map(id => `<div class="unmatched-item">
                <div><strong>${esc(items[id].name)}</strong><small>${items[id].quantity} ${esc(items[id].unit)}</small></div>
                <div class="row">
                    <button class="small" data-match-grocery="${esc(id)}" ${editable ? '' : 'disabled'}>Choisir un produit</button>
                    <button class="small" data-cart-decision="pantry" data-grocery-id="${esc(id)}" ${editable ? '' : 'disabled'}>J’en ai déjà</button>
                    <button class="small" data-cart-decision="skip" data-grocery-id="${esc(id)}" ${editable ? '' : 'disabled'}>Ne pas acheter</button>
                </div>
            </div>`).join('')}</section>` : '')
        + `<div class="product-grid">${c.matches.map(match => productCard(match, items[match.grocery_id], editable)).join('')}</div>`
        + ((c.excluded || []).length ? `<details class="cart-exclusions"><summary>${c.excluded.length} ingrédient${c.excluded.length === 1 ? '' : 's'} écarté${c.excluded.length === 1 ? '' : 's'}</summary>
            ${c.excluded.map(item => `<div class="row between"><span>${esc(items[item.grocery_id]?.name || 'Ingrédient')} · ${item.reason === 'pantry' ? 'Déjà en réserve' : 'Non acheté cette fois'}</span>
                ${editable ? `<button class="small" data-cart-decision="restore" data-grocery-id="${esc(item.grocery_id)}">Réintégrer</button>` : ''}</div>`).join('')}</details>` : '')
        + (editable ? `<div class="row product-tools">${flowButton('match-chat', 'Affiner avec l’assistant')}</div>` : '');
}

function cartStage() {
    const job = S.fill_job;
    if (!job) {
        return flowActions('Remplissage précédent à vérifier', '', flowButton('resume-fill', 'Reprendre le remplissage', {primary: true})
            + flowButton('reopen-cart', 'Revoir les produits')) + driveLink;
    }
    const verified = job.items.filter(item => ['verified', 'present'].includes(item.status)).length;
    const active = ['queued', 'running'].includes(job.status);
    const labels = {queued: 'En attente de démarrage', running: 'Remplissage en cours', paused: 'Remplissage en pause',
        partial: 'Quelques articles à vérifier', completed: 'Panier rempli et vérifié'};
    const pending = job.items.find(item => item.status === 'sending');
    const issues = job.items.filter(item => item.error);
    const ingredientFor = item => S.week.cart.matches.find(match => match.productId === item.productId)?.grocery_id;
    const firstRejection = !active && issues.find(item => item.status === 'rejected' && ingredientFor(item));
    const retry = flowButton('resume-fill', 'Reprendre les articles restants', {primary: !firstRejection});
    const replace = firstRejection ? `<button class="primary" data-match-grocery="${esc(ingredientFor(firstRejection))}" ${flowBusy ? 'disabled' : ''}>Choisir un remplacement</button>` : '';
    const controls = active ? flowButton('pause-fill', job.pause_requested ? 'Pause demandée…' : 'Mettre en pause', {disabled: job.pause_requested})
        : job.status === 'completed' ? driveLink
        : replace + retry;
    const review = !active && job.status !== 'completed'
        ? flowButton('reopen-cart', 'Modifier la sélection')
        : '<button data-stage="products">Voir la sélection de produits</button>';
    return flowActions(labels[job.status] || job.status, `${verified} / ${job.items.length} produits vérifiés`, controls)
        + `<section class="fill-progress" aria-label="Progression du panier">
            <progress value="${verified}" max="${job.items.length}" aria-label="Produits vérifiés"></progress>
            ${pending ? `<p>Ajout de ${esc(pending.name)}</p>` : ''}
            ${job.error ? `<p>${esc(job.error)}</p>` : ''}
            ${job.status === 'completed' ? '<p>Vérifiez votre panier chez Chronodrive, puis choisissez votre créneau de retrait.</p>' : ''}
        </section>`
        + (issues.length ? `<section class="panel missing-products"><h2>Articles à vérifier</h2>
            ${issues.map(item => {
                const ingredient = ingredientFor(item);
                return `<article class="fill-error"><strong>${esc(item.name)}</strong><p>${esc(item.error)}</p>
                    <small>${item.actual ?? '–'} / ${item.target ?? item.quantity} paquet(s) dans le panier</small>
                    ${!active && ingredient && item !== firstRejection ? `<p><button class="small" data-match-grocery="${esc(ingredient)}">Remplacer ${esc(item.name)}</button></p>` : ''}
                </article>`;
            }).join('')}</section>` : '')
        + `<div class="row">${review}${!active && job.status !== 'completed' ? driveLink.replace('drive-link', 'drive-text-link') : ''}</div>`;
}

function selectStage(stage) {
    const wasShopping = view === 'shopping';
    view = stage === 'week' ? 'week' : 'shopping';
    shoppingStage = ['groceries', 'products'].includes(stage) ? stage : null;
    editingGroceries = false;
    flowError = '';
    chatOpen = false;
    role = stage === 'week' ? 'planner' : stage === 'groceries' ? 'shopper' : 'cart';
    nativePrompts = [];
    render();
    if (wasShopping || view === 'shopping') {
        window.scrollTo(0, 0);
        $('#flow-title')?.focus({preventScroll: true});
    }
}

async function flowRequest(action, run) {
    if (flowBusy) return;
    flowBusy = action;
    flowError = '';
    render();
    try {
        await run();
    } catch (error) {
        flowError = error.message;
    } finally {
        flowBusy = '';
        await refresh();
    }
}

const groceryPrompt = 'Prépare et enregistre les courses de cette semaine validée. Pars des quantités des recettes, puis applique mes préférences de courses et mes réserves explicites. Conserve les ingrédients nécessaires et laisse la liste à valider dans Table.';
const productPrompt = 'Trouve et enregistre les produits Chronodrive correspondant à mes courses validées. Tiens compte de mes préférences de marques et de formats. Propose les références et les quantités exactes pour que je puisse les valider dans Table.';

function startAssistant(assistant, message) {
    role = assistant;
    nativePrompts = [];
    return api('chat', {role: assistant, week, message});
}

async function shoppingAction(action) {
    switch (action) {
        case 'continue-shopping':
            selectStage(currentStage());
            return;
        case 'go-products':
            selectStage('products');
            return;
        case 'edit-groceries':
            selectStage('groceries');
            editingGroceries = true;
            render();
            return;
        case 'stop-editing-groceries':
            editingGroceries = false;
            render();
            return;
        case 'approve-week':
            await flowRequest(action, async () => {
                await wf('approve');
                selectStage('groceries');
                await startAssistant('shopper', groceryPrompt);
            });
            return;
        case 'prepare-groceries':
            await flowRequest(action, () => startAssistant('shopper', groceryPrompt));
            return;
        case 'approve-groceries':
            if (savingGroceryFields && !await groceryWrites) return;
            await flowRequest(action, async () => {
                await wf('approve-groceries');
                selectStage('products');
                if (S.chronodrive_connected !== false && S.week.groceries.items.some(item => !item.checked)) {
                    await startAssistant('cart', productPrompt);
                }
            });
            return;
        case 'find-products':
            await flowRequest(action, () => startAssistant('cart', productPrompt));
            return;
        case 'approve-and-fill':
        case 'fill-cart':
        case 'resume-fill':
            await flowRequest(action, async () => {
                await wf(action);
                selectStage('cart');
            });
            return;
        case 'pause-fill':
            await flowRequest(action, () => wf(action));
            return;
        case 'reopen-cart':
            await flowRequest(action, async () => {
                await wf(action);
                selectStage('products');
            });
            return;
    }
}
