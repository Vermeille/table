const weeklyDays = ['Lun.', 'Mar.', 'Mer.', 'Jeu.', 'Ven.', 'Sam.', 'Dim.'];
const weeklyActivity = {
    queued: ['La semaine est en file d’attente', 'Vous pouvez fermer Table et revenir plus tard.'],
    planning: ['Table prépare vos repas', 'La préparation tient compte de vos habitudes et du congélateur.'],
    shopping: ['Table rassemble les courses', 'Les quantités suivent les portions et les plats déjà au congélateur.'],
    matching: ['Table cherche vos produits', 'Vous pourrez vérifier la sélection avant de remplir votre panier.']
};

function weeklyNotice() {
    const notice = S.weekly_notice;
    if (!notice || (view === 'week' && notice.id === week)) return '';
    return `<div class="weekly-banner" role="status">
        <div><strong>Votre semaine du ${fmt(notice.id)} est prête à relire</strong>
        <p>Le menu et les courses sont disponibles.</p></div>
        <button data-review-week="${notice.id}">Ouvrir le planning →</button>
    </div>`;
}

function weeklyOverview() {
    const job = S.weekly;
    const active = weeklyActivity[job?.status];
    const canPrepare = !S.week.approved && !active;
    const intro = !S.week.slots.length && !active;
    if (active) return `<div class="weekly-banner weekly-progress" role="status">
        <span class="flow-spinner" aria-hidden="true"></span>
        <div><strong>${active[0]}</strong><p>${active[1]}</p></div>
    </div>`;
    if (job?.status === 'ready' && S.week.weekly_prepared) {
        const q = job.quality;
        const warnings = q?.warnings || [];
        const stats = q?.cook_days ? [
            [q.cook_days.length, q.cook_days.length === 1 ? 'jour de cuisine' : 'jours de cuisine'],
            [q.frozen_meals, 'repas à réchauffer'],
            [S.week.groceries?.items.filter(i => !i.checked).length ?? 0, 'ingrédients à acheter']
        ] : [];
        const selected = S.week.cart?.weekly_preview ? S.week.cart.matches.length : 0;
        const unmatched = S.week.cart?.unmatched?.length ?? S.week.groceries?.items.filter(item => !item.checked).length ?? 0;
        const summary = selected ? (unmatched ? `${selected} produit${selected===1?'':'s'} déjà choisi${selected===1?'':'s'}. ${unmatched} ingrédient${unmatched===1?'':'s'} à vérifier.`
            : 'Les courses et la sélection Chronodrive sont préparées.') : 'Les quantités des courses sont calculées.';
        return `<section class="weekly-summary" aria-labelledby="weekly-summary-title">
            <h2 id="weekly-summary-title">Votre semaine est prête à relire</h2>
            <p>${summary} ${job.origin === 'fallback' ? 'Table a utilisé les règles du planning pour préparer ce menu.' : ''}</p>
            ${stats.length ? `<dl class="weekly-stats">${stats.map(([value, title]) =>
                `<div><dt>${title}</dt><dd>${value}</dd></div>`).join('')}</dl>` : ''}
            ${q?.active_minutes ? `<p>Environ ${q.active_minutes} min de préparation active sur la semaine.</p>` : ''}
            ${Number.isInteger(q?.nutrition_known) ? `<p>Calories calculées pour ${q.nutrition_known} repas sur ${S.week.slots.length}.</p>` : ''}
            ${job.error ? `<p class="notice">${esc(job.error)}</p>` : ''}
            ${!S.week.approved && unmatched > 0 && S.chronodrive_connected ? '<button class="small weekly-retry" data-action="weekly-retry-products">Relancer les produits à trouver</button>' : ''}
            ${warnings.length ? `<details class="weekly-warnings"><summary>${warnings.length === 1 ? '1 point à vérifier' : warnings.length + ' points à vérifier'}</summary>
                <ul>${warnings.map(warning => `<li>${esc(warning)}</li>`).join('')}</ul></details>` : ''}
        </section>`;
    }
    if (!canPrepare) return '';
    if (intro) return `<section class="weekly-summary weekly-start">
        <div><h2>Préparer ma semaine</h2>
        <p>Table propose les repas et le plan de cuisson, calcule les courses et cherche les produits à votre magasin.</p>
        ${job?.error ? `<p class="notice">${esc(job.error)}</p>` : ''}</div>
        <div class="weekly-actions">
            <button class="primary" data-action="weekly-prepare">Préparer cette semaine</button>
            <button data-view="preferences">Régler mes habitudes</button>
        </div>
    </section>`;
    return `<div class="weekly-banner">
        <div><strong>Vos repas sont choisis</strong><p>Vous pouvez préparer les courses et les produits pour ce menu.</p>
        ${job?.status === 'needs_attention' ? `<p class="notice">${esc(job.error)}</p>` : ''}</div>
        <button data-action="weekly-prepare">Préparer les courses</button>
    </div>`;
}

function dayOptions(field, selection) {
    return weeklyDays.map((name, day) =>
        `<label class="weekly-chip"><input name="${field}" type="checkbox" value="${day}" ${selection.includes(day) ? 'checked' : ''}> ${name}</label>`).join('');
}

function weeklyForm() {
    const s = S.weekly_settings;
    if (!s) return '';
    const date = S.weekly_next ? new Intl.DateTimeFormat('fr-FR', {
        weekday: 'long', day: 'numeric', month: 'long', hour: 'numeric', minute: '2-digit', timeZone:s.timezone
    }).format(new Date(S.weekly_next)) : '';
    return `<form class="panel weekly-form" id="weekly-form">
        <h2>Préparation automatique</h2>
        <p class="muted">${date ? 'Prochaine préparation le ' + date + '.' :
            'Choisissez quand recevoir le brouillon de la semaine suivante.'}</p>
        <label class="weekly-check"><input type="checkbox" name="enabled" ${s.enabled ? 'checked' : ''}> Préparer ma semaine automatiquement</label>
        <div class="weekly-fields">
            <label>Jour de préparation<select name="day" aria-label="Jour de préparation">${['Lundi','Mardi','Mercredi','Jeudi','Vendredi','Samedi','Dimanche'].map((day,i) =>
                `<option value="${i}" ${s.day === i ? 'selected' : ''}>${day}</option>`).join('')}</select></label>
            <label>Heure locale<input name="at" type="time" value="${esc(s.at)}" required></label>
            <label>Personnes<input name="people" type="number" min="1" max="12" value="${s.people}" required></label>
            <label>Jours de cuisine souhaités<input name="cook_days" type="number" min="1" max="7" value="${s.cook_days}" required></label>
            <label>Régime<select name="diet" aria-label="Régime">${Object.entries({any:'Tout',vegetarian:'Végétarien',vegan:'Végétalien'}).map(([key,name]) =>
                `<option value="${key}" ${s.diet === key ? 'selected' : ''}>${name}</option>`).join('')}</select></label>
            <label>Objectif kcal par personne et par jour<input name="daily_kcal" type="number" min="500" max="5000" value="${s.daily_kcal ?? ''}" placeholder="Facultatif"></label>
        </div>
        <fieldset><legend>Repas à planifier</legend><div class="weekly-chips">
            ${['lunch','dinner'].map(key => `<label class="weekly-chip"><input type="checkbox" name="meals" value="${key}" ${s.meals.includes(key) ? 'checked' : ''}> ${mealName(key)}</label>`).join('')}
        </div></fieldset>
        <fieldset><legend>Jours à planifier</legend><div class="weekly-chips">${dayOptions('days', s.days)}</div></fieldset>
        <fieldset><legend>Déjeuners à emporter</legend><div class="weekly-chips">${dayOptions('portable', s.portable)}</div></fieldset>
        <fieldset><legend>Jours sans cuisine</legend><div class="weekly-chips">${dayOptions('no_cook', s.no_cook)}</div></fieldset>
        <label>Aliments à éviter<input name="exclude" value="${esc(s.exclude.join(', '))}" placeholder="Par exemple moutarde, céleri"></label>
        <label>Ingrédients toujours en réserve<input name="pantry" value="${esc(s.pantry.join(', '))}" placeholder="Par exemple sel, huile d’olive"></label>
        <p class="muted">Séparez les aliments par des virgules. Vérifiez les étiquettes du magasin pour vos allergies.</p>
        <button class="primary">Enregistrer la préparation</button>
    </form>`;
}

function bindWeekly() {
    const form = $('#weekly-form');
    if ($('#notification-device')) {
        paintNotificationDevice();
        if (!pushRegistration || !pushKey) readNotificationDevice().then(paintNotificationDevice, () => {
            const area = $('#notification-device');
            if (area) area.textContent = 'Les notifications sur cet appareil sont indisponibles.';
        });
    }
    if (form) form.onsubmit = event => {
        event.preventDefault();
        safe(async () => {
            const data = new FormData(form);
            const list = name => data.getAll(name).map(Number);
            const foods = name => data.get(name).split(',').map(value => value.trim()).filter(Boolean);
            const current = S.weekly_settings;
            await api('weekly/settings', {
                version:current.version, enabled:data.has('enabled'), timezone:current.timezone,
                day:Number(data.get('day')), at:data.get('at'), people:Number(data.get('people')),
                cook_days:Number(data.get('cook_days')), daily_kcal:Number(data.get('daily_kcal')) || null,
                diet:data.get('diet'), meals:data.getAll('meals'), days:list('days'),
                portable:list('portable'), no_cook:list('no_cook'), exclude:foods('exclude'), pantry:foods('pantry')
            });
            await refresh();
            toast('Préparation hebdomadaire enregistrée');
        });
    };
    document.querySelectorAll('[data-review-week]').forEach(button => button.onclick = () => safe(async () => {
        week = button.dataset.reviewWeek;
        view = 'week';
        role = 'planner';
        flowError = '';
        await api(`weekly/${week}/seen`, {});
        await refresh();
        $('#flow-title')?.focus();
    }));
}

async function weeklyAction(name) {
    if (name === 'weekly-prepare' || name === 'weekly-retry-products') {
        await flowRequest(name, async () => {
            await api(`weekly/${week}/${name === 'weekly-prepare' ? 'prepare' : 'retry-products'}`, {version:S.week.version});
            await refresh();
        });
    }
}

let pushRegistration;
let pushKey;
let pushedDevice;
let pushLoading = false;
const canUsePush = () => 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window;

function notificationSettings() {
    return `<section class="panel" id="notification-settings" aria-labelledby="notification-title">
        <h2 id="notification-title">Notifications sur cet appareil</h2>
        <p class="muted">Recevez un rappel dès que le menu de la semaine est prêt. Sur iPhone et iPad, ajoutez Table à l’écran d’accueil puis ouvrez l’app depuis son icône.</p>
        <div id="notification-device"></div>
    </section>`;
}

function paintNotificationDevice() {
    const area = $('#notification-device');
    if (!area) return;
    if (!canUsePush()) {
        area.innerHTML = '<p>Ce navigateur affiche les rappels dans Table.</p>';
        return;
    }
    if (Notification.permission === 'denied') {
        area.innerHTML = '<p>Les notifications sont bloquées. Vous pouvez les autoriser dans les réglages de ce site.</p>';
        return;
    }
    area.innerHTML = pushedDevice ? `<div class="row">
        <button type="button" data-notification="test">Envoyer un essai</button>
        <button type="button" data-notification="off">Désactiver sur cet appareil</button>
    </div>` : `<button type="button" data-notification="on" ${pushRegistration && pushKey ? '' : 'disabled'}>Activer sur cet appareil</button>`;
    area.querySelectorAll('[data-notification]').forEach(button => button.onclick = () => safe(async () => {
        button.disabled = true;
        try {
            if (button.dataset.notification === 'on') {
                // The browser needs this call during the user gesture that grants permission.
                const subscription = await pushRegistration.pushManager.subscribe({
                    userVisibleOnly:true, applicationServerKey:pushKey
                });
                try {
                    await api('notifications/subscribe', subscription.toJSON());
                } catch (error) {
                    await subscription.unsubscribe();
                    throw error;
                }
                pushedDevice = subscription;
                toast('Notifications activées sur cet appareil');
            } else if (button.dataset.notification === 'off') {
                await api('notifications/unsubscribe', {endpoint:pushedDevice.endpoint});
                await pushedDevice.unsubscribe();
                pushedDevice = null;
                toast('Notifications désactivées sur cet appareil');
            } else {
                await api('notifications/test', {endpoint:pushedDevice.endpoint});
                toast('Notification d’essai envoyée');
            }
        } finally {
            paintNotificationDevice();
        }
    }));
}

async function readNotificationDevice() {
    if (!canUsePush()) return;
    if (pushLoading) return pushLoading;
    pushLoading = (async () => {
        const [, {public_key:key}] = await Promise.all([
            navigator.serviceWorker.register('/service-worker.js'), api('notifications/key')
        ]);
        const encoded=key.replace(/-/g,'+').replace(/_/g,'/') + '='.repeat((4-key.length%4)%4);
        pushKey=Uint8Array.from(atob(encoded),c => c.charCodeAt(0));
        pushRegistration = await navigator.serviceWorker.ready;
        pushedDevice = await pushRegistration.pushManager.getSubscription();
    })();
    try {
        await pushLoading;
    } finally {
        pushLoading = false;
    }
}
