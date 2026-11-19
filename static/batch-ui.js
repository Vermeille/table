const batchDefaults = {enabled: false, reserve: 4, extra_per_day: 4};
const portionLabel = n => `${n} portion${n === 1 ? '' : 's'}`;
const slotKey = slot => `${slot.day}-${slot.meal}`;
const kitchenEvent = slot => S.kitchen?.entries[slotKey(slot)];
const slotTask = slot => S.week.batch?.[slotKey(slot)];
const weekDay = slot => fmt(local(dayDate(slot.day)), {weekday:'long'});
const stockLots = () => S.freezer?.lots || [];
const freezingGuide = 'https://www.anses.fr/fr/article/comment-bien-conserver-ses-aliments-ne-pas-interrompre-chaine-du-froid';

function batchSettingsFields() {
    const settings = {...batchDefaults, ...S.preferences.batch};
    return `<section class="panel batch-settings"><h2>Cuisine en lots</h2>
        <label class="check-row"><input name="batch_enabled" type="checkbox" ${settings.enabled ? 'checked' : ''}>
            Prévoir des portions à congeler et des repas à ressortir</label>
        <div class="row batch-settings-options">
            <label>Réserve souhaitée (portions)<input name="batch_reserve" type="number" min="0" max="100" value="${settings.reserve}" required></label>
            <label>Maximum à congeler par jour de cuisson<input name="batch_extra" type="number" min="1" max="24" value="${settings.extra_per_day}" required></label>
        </div>
        <small>Table utilise une partie du stock et répartit les nouvelles portions sur plusieurs jours si possible.</small>
    </section>`;
}

function readPreferences(form) {
    return {
        version: S.preferences.version,
        planner: form.elements.planner.value,
        shopper: form.elements.shopper.value,
        cart: form.elements.cart.value,
        batch: {
            enabled: form.elements.batch_enabled.checked,
            reserve: +form.elements.batch_reserve.value,
            extra_per_day: +form.elements.batch_extra.value,
        },
    };
}

function batchAgenda() {
    const {batch, slots, approved} = S.week;
    const enabled = S.preferences.batch?.enabled;
    if (!enabled && !batch) return '';
    const mealOrder = {breakfast: 0, lunch: 1, dinner: 2};
    const entries = [...slots].sort((a,b) => a.day-b.day || mealOrder[a.meal]-mealOrder[b.meal])
        .map(slot => ({slot, task:slotTask(slot), event:kitchenEvent(slot)}));
    const cookDays = new Set(entries.filter(({task, event}) => task?.source === 'cook' && !event).map(({slot}) => slot.day));
    const frozen = entries.filter(({task, event}) => ['stock', 'batch'].includes(task?.source) && event?.action !== 'skip');
    const batches = entries.filter(({task, event}) => task?.freeze && !event);
    const extras = batches.reduce((sum, item) => sum + item.task.freeze, 0);
    const confirmed = stockLots().reduce((sum, lot) => sum + lot.quantity, 0);
    const toUse = frozen.filter(item => !item.event).reduce((sum, item) => sum + item.slot.servings, 0);
    const projected = Math.max(0, confirmed + extras - toUse);
    const schedule = batches.map(({slot, task}) => {
        const later = frozen.filter(({task: use}) => use.from_slot === slotKey(slot)).map(({slot:meal}) => weekDay(meal));
        return `<li><strong>${esc(weekDay(slot))} · ${esc(slot.recipe.title)}</strong>
            <span>Cuisiner ${portionLabel(task.quantity)} et en congeler ${task.freeze}${later.length ? ` · à ressortir ${esc(later.join(', '))}` : ''}</span>
            ${slot.recipe.freezer_note ? `<small>${esc(slot.recipe.freezer_note)}</small>` : ''}</li>`;
    }).join('');
    const canAdapt = slots.length && enabled && S.week.cart?.status !== 'filling' && (!approved || !batch || entries.some(({event}) => event?.action === 'skip'));
    return `<section class="batch-agenda">
        <div class="row between"><h2>Cuisine en lots</h2><button class="small" data-view="freezer">Voir le congélateur</button></div>
        ${batch && slots.length ? `<div class="batch-metrics"><span><b>${cookDays.size}</b> jour${cookDays.size === 1 ? '' : 's'} à cuisiner</span>
            <span><b>${frozen.length}</b> repas du congélateur</span><span><b>${extras}</b> portions à congeler</span></div>
            <p class="batch-forecast">Stock estimé après ces repas · ${portionLabel(projected)}</p>`
            : `<p>${portionLabel(confirmed)} en stock. ${slots.length ? 'Adaptez les repas déjà choisis au congélateur.' : 'L’assistant tient compte de votre stock pour le prochain planning.'}</p>`}
        ${schedule ? `<details class="batch-list"><summary>Voir les cuissons et les portions à congeler</summary><ul>${schedule}</ul></details>` : ''}
        ${canAdapt ? '<button class="small" data-action="refresh-batch">Adapter au congélateur</button>' : ''}
    </section>`;
}

function mealSource(slot) {
    const task = slotTask(slot);
    const event = kitchenEvent(slot);
    if (!task) return '';
    if (event?.action === 'freeze') return `<span class="source-label recorded">${event.quantity ? '✓ ' + portionLabel(event.quantity) + (event.quantity === 1 ? ' congelée' : ' congelées') : '✓ Cuisson enregistrée'}</span>`;
    if (event?.action === 'take') return '<span class="source-label recorded">✓ Sorti du congélateur</span>';
    if (event?.action === 'skip') return '<span class="source-label">Repas annulé</span>';
    const freezer = ['stock', 'batch'].includes(task.source);
    const source = freezer ? 'Du congélateur' : task.freeze ? 'À cuisiner en lot' : 'À cuisiner';
    return `<span class="source-label ${freezer ? 'frozen' : task.freeze ? 'batch-cook' : ''}">${source}</span>
        ${task.freeze ? `<small class="meal-batch-detail">${portionLabel(task.quantity)} à préparer · ${task.freeze} à congeler</small>` : ''}
        ${task.source === 'batch' ? `<small class="meal-batch-detail">Lot du ${esc(weekDay({day:+task.from_slot.split('-')[0]}))}</small>` : ''}`;
}

function mealKitchenControls(slot) {
    const task = slotTask(slot);
    if (!task || kitchenEvent(slot)) return '';
    const flex = task.freeze || ['stock', 'batch'].includes(task.source);
    if (S.week.approved && flex) {
        return `<button class="small" data-kitchen-slot="${slotKey(slot)}">${task.freeze ? 'Confirmer la congélation' : 'Sortir les portions'}</button>`;
    }
    if (!S.week.approved && S.week.batch_settings?.enabled && !slot.freezer_lot_id && (flex || slot.cook_fresh)) {
        return `<button class="small" data-fresh-slot="${slotKey(slot)}">${slot.cook_fresh ? 'Autoriser les lots' : 'Cuisiner à part'}</button>`;
    }
    return '';
}

function kitchenDialog(key) {
    const slot = S.week.slots.find(item => slotKey(item) === key);
    const task = slotTask(slot);
    if (!task) return;
    const freeze = !!task.freeze;
    const ready = !freeze && task.lots.every(allocation =>
        stockLots().some(lot => lot.id === allocation.id && lot.quantity >= allocation.quantity));
    const planWeek = S.week.id;
    const version = S.week.version;
    const label = freeze ? 'Enregistrer les portions congelées' : 'Confirmer la sortie';
    modal(`<h2>${esc(slot.recipe.title)}</h2>
        <p>${freeze ? `La cuisson prévoit ${portionLabel(task.quantity)}. Combien en avez-vous mises au congélateur ?`
            : ready ? `Sortez ${portionLabel(slot.servings)} pour le repas de ${esc(weekDay(slot))}. Pour une décongélation au réfrigérateur, prévoyez de les y transférer à l’avance.`
                : 'Le lot n’a pas encore été enregistré au congélateur. Confirmez la cuisson ou modifiez ce repas.'}</p>
        <form id="kitchen-form">
            ${freeze ? `<label for="frozen-quantity">Portions réellement congelées</label><input id="frozen-quantity" type="number" min="0" max="100" value="${task.freeze}" required>` : ''}
            <div class="row batch-form-actions">
                <button class="primary" ${freeze || ready ? '' : 'disabled'}>${label}</button>
                ${freeze ? '' : '<button type="button" id="skip-kitchen">Repas annulé</button>'}
            </div>
        </form>
        <p class="batch-form-tip"><a href="${freezingGuide}" target="_blank" rel="noreferrer">Conseils de congélation et décongélation de l’Anses ↗</a></p>`);
    async function record(action) {
        await api(`week/${planWeek}/kitchen`, {version, slot:key, action, ...(freeze ? {quantity:+$('#frozen-quantity').value} : {})});
        $('#modal').close();
        await refresh();
    }
    $('#kitchen-form').onsubmit = event => {
        event.preventDefault();
        safe(() => record(freeze ? 'freeze' : 'take'));
    };
    if ($('#skip-kitchen')) $('#skip-kitchen').onclick = () => safe(() => record('skip'));
}

function freezerView() {
    const lots = [...stockLots()].sort((a, b) => a.frozen_on.localeCompare(b.frozen_on) || a.recipe.title.localeCompare(b.recipe.title, 'fr'));
    const portions = lots.reduce((sum, lot) => sum + lot.quantity, 0);
    const reserved = lots.reduce((sum, lot) => sum + lot.reserved, 0);
    return `<div class="topline"><div><h1>Congélateur</h1><p class="muted">${portionLabel(portions)} en stock · ${reserved} réservées</p></div>
        <button class="primary" data-freezer-edit="">+ Ajouter un plat</button></div>
        ${S.preferences.batch?.enabled ? '' : '<p class="notice">Activez la cuisine en lots pour que l’assistant planifie avec votre stock. <button class="small" data-view="preferences">Ouvrir les préférences</button></p>'}
        ${lots.length ? `<div class="freezer-grid">${lots.map(lot => `<article class="panel freezer-lot">
            <div class="row between"><h2>${esc(lot.recipe.title)}</h2><button class="small" data-freezer-edit="${esc(lot.id)}" aria-label="Modifier ${esc(lot.recipe.title)}">Modifier</button></div>
            <strong>${portionLabel(lot.quantity)} · ${lot.quantity - lot.reserved} disponibles</strong>
            <p class="muted">Congelé le ${fmt(lot.frozen_on, {day:'numeric',month:'long',year:'numeric'})}</p>
            ${lot.note ? `<p>${esc(lot.note)}</p>` : ''}
            ${lot.claims.length ? `<details><summary>${portionLabel(lot.reserved)} réservées</summary>
                ${lot.claims.map(claim => `<button class="small" data-week="${esc(claim.week)}">Semaine du ${fmt(claim.week)} · ${claim.quantity} portions</button>`).join('')}</details>` : ''}
        </article>`).join('')}</div>` : '<section class="panel"><h2>Le congélateur est vide</h2><p>Ajoutez vos plats déjà congelés. Les portions préparées depuis le planning apparaîtront ici après confirmation.</p></section>'}
        <p class="batch-form-tip"><a href="${freezingGuide}" target="_blank" rel="noreferrer">Conseils de conservation de l’Anses ↗</a></p>`;
}

function editFreezer(lotId) {
    const lot = stockLots().find(item => item.id === lotId);
    const version = S.freezer.version;
    modal(`<h2>${lot ? esc(lot.recipe.title) : 'Ajouter un plat congelé'}</h2>
        <form id="freezer-form">
            ${lot ? '' : `<label for="freezer-recipe">Recette du carnet (facultatif)</label>
                <select id="freezer-recipe" name="recipe_id"><option value="">Saisir un autre plat</option>
                  ${[...S.recipes].sort((a,b)=>a.title.localeCompare(b.title,'fr')).map(recipe =>
                      `<option value="${esc(recipe.id)}">${esc(recipe.title)}</option>`).join('')}</select>
                <label for="freezer-name">Nom du plat</label><input id="freezer-name" name="title" maxlength="100" required>`}
            <div class="row batch-settings-options">
                <label>Portions au congélateur<input name="quantity" type="number" min="${lot ? lot.reserved : 1}" max="100" value="${lot?.quantity ?? 2}" required></label>
                <label>Date de congélation<input name="frozen_on" type="date" max="${local(new Date())}" value="${lot?.frozen_on ?? local(new Date())}" required></label>
            </div>
            ${lot ? `<small>${lot.reserved ? `${portionLabel(lot.reserved)} réservées dans le planning.` : 'Saisissez 0 quand le plat est terminé.'}</small>` : ''}
            <label>Note (facultative)<textarea name="note" rows="2" maxlength="500">${esc(lot?.note || '')}</textarea></label>
            <button class="primary">Enregistrer</button>
        </form>`);
    const form = $('#freezer-form');
    if (form.elements.recipe_id) form.elements.recipe_id.onchange = () => {
        form.elements.title.required = !form.elements.recipe_id.value;
        form.elements.title.disabled = !!form.elements.recipe_id.value;
    };
    form.onsubmit = event => {
        event.preventDefault();
        safe(async () => {
            const payload = Object.fromEntries(new FormData(form));
            await api('freezer', {...payload, version, id:lot?.id, quantity:+payload.quantity});
            $('#modal').close();
            await refresh();
        });
    };
}

function selectFrozenMeal(day, meal, servings) {
    const lots = stockLots().filter(lot => lot.available > 0).sort((a, b) => a.frozen_on.localeCompare(b.frozen_on));
    modal(`<h2>Choisir un plat congelé</h2><form id="frozen-meal-form">
        <label>Plat à ressortir<select name="lot" required>${lots.map(lot => `<option value="${esc(lot.id)}">${esc(lot.recipe.title)} · ${portionLabel(lot.available)} · ${fmt(lot.frozen_on)}</option>`).join('')}</select></label>
        <label>Portions pour ce repas<input name="servings" type="number" min="1" max="${lots[0]?.available ?? 1}" value="${Math.max(1, Math.min(servings, lots[0]?.available ?? 1))}" required></label>
        <div class="row batch-form-actions"><button class="primary">Planifier ce repas</button><button type="button" id="back-to-cookbook">Choisir dans le carnet</button></div>
    </form>`);
    $('#back-to-cookbook').onclick = () => pickMeal(day, meal);
    const form = $('#frozen-meal-form');
    form.elements.lot.onchange = () => {
        const lot = lots.find(item => item.id === form.elements.lot.value);
        form.elements.servings.max = lot.available;
        form.elements.servings.value = Math.max(1, Math.min(servings, lot.available));
    };
    form.onsubmit = event => {
        event.preventDefault();
        safe(async () => {
            const lot = lots.find(item => item.id === form.elements.lot.value);
            const slots = S.week.slots.filter(slot => slot.day !== day || slot.meal !== meal);
            await saveSlots([...slots, {day, meal, recipe_id:lot.recipe.id, freezer_lot_id:lot.id, servings:+form.elements.servings.value}]);
            $('#modal').close();
        });
    };
}

function bindBatch() {
    document.querySelectorAll('[data-freezer-edit]').forEach(button => button.onclick = () => editFreezer(button.dataset.freezerEdit));
    document.querySelectorAll('[data-kitchen-slot]').forEach(button => button.onclick = () => kitchenDialog(button.dataset.kitchenSlot));
    document.querySelectorAll('[data-fresh-slot]').forEach(button => button.onclick = () => safe(() => {
        const key = button.dataset.freshSlot;
        return saveSlots(S.week.slots.map(slot => slotKey(slot) === key ? {...slot, cook_fresh:!slot.cook_fresh} : slot));
    }));
}
