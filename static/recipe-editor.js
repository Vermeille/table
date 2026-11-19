const nutritionLabels = {kcal:'kcal', protein_g:'g de protéines', carbs_g:'g de glucides', fat_g:'g de lipides'};
const massUnits = new Set(['mg', 'g', 'kg']);
const ingredientUnits = ['g', 'kg', 'mg', 'ml', 'cl', 'l', 'pièce', 'c. à café', 'c. à soupe', 'pincée', 'sachet'];
const nutritionFormat = new Intl.NumberFormat('fr-FR', {maximumFractionDigits: 2});
const formatNutrition = n => nutritionFormat.format(n);
const rowIssues = {
    food:'Choisir un aliment',
    weight:'Renseigner le poids comestible',
    data:'Valeurs manquantes dans la source',
};
const oliveDensityUrl = 'https://www.fao.org/fao-who-codexalimentarius/sh-proxy/en/?lnk=1&url=https%3A%2F%2Fworkspace.fao.org%2Fsites%2Fcodex%2FStandards%2FCXS+33-1981%2FCXS_033f.pdf';

function nutritionValue(value, key) {
    if (!value) return '—';
    const factor = key === 'kcal' ? 1 : 10;
    if (value.trace) return '≥ ' + formatNutrition(Math.floor(value.low * factor) / factor);
    if (value.low !== value.high) {
        const low = Math.floor(value.low * factor) / factor;
        const high = Math.ceil(value.high * factor) / factor;
        return `${formatNutrition(low)}–${formatNutrition(high)}`;
    }
    return formatNutrition(Math.round(value.low * factor) / factor);
}

function recipeNutrition(report) {
    if (!report?.total) return '<p class="muted">Renseignez les ingrédients pour calculer la nutrition.</p>';
    const incomplete = report.calculated < report.total;
    const trace = Object.values(report.values).some(value => value.trace);
    const subtotals = Object.entries(report.subtotals || {});
    return `<section class="recipe-nutrition">
        <div class="row between"><strong>Nutrition par portion</strong>
            <div class="row">${(report.sources || [report.source]).map(source =>
                `<a href="${esc(source.url)}" target="_blank" rel="noreferrer">${esc(source.name)} ↗</a>`).join('')}</div></div>
        <div class="nutrition">${Object.entries(nutritionLabels).map(([key, unit]) =>
            `<div><b>${nutritionValue(report.values[key], key)}</b><span>${unit}</span></div>`).join('')}</div>
        ${incomplete ? `<p>${report.calculated}/${report.total} ingrédients entièrement calculés. Les valeurs incomplètes apparaissent avec un tiret.</p>` : ''}
        ${subtotals.length ? `<details class="nutrition-subtotal"><summary>Voir le sous-total des ingrédients documentés</summary>
            <p>${subtotals.map(([key, value]) => `${nutritionValue(value, key)} ${nutritionLabels[key]}`).join(' · ')}</p></details>` : ''}
        ${trace ? '<p>Le signe ≥ indique la valeur connue, à laquelle s’ajoutent des traces non chiffrées.</p>' : ''}
    </section>`;
}

function ingredientNutrition(row, scale = 1) {
    if (!row) return '';
    const weight = row.grams === null ? '' : ` · ${formatNutrition(row.grams * scale)} g comestibles`;
    const conversion = row.weight_source === 'olive_density'
        ? ` <a href="${oliveDensityUrl}" target="_blank" rel="noreferrer">Densité de référence ↗</a>` : '';
    const foodReference = row.food_reference_url ? ` <a href="${esc(row.food_reference_url)}" target="_blank" rel="noreferrer">Fiche USDA ↗</a>` : '';
    const weightReference = row.weight_reference ? ` <a href="${esc(row.weight_reference.url)}" target="_blank" rel="noreferrer">${esc(row.weight_reference.name)} ↗</a>` : '';
    return `${row.food ? `<span>${esc(row.food)}${weight}</span>${conversion}${foodReference}${weightReference}` : ''}
        ${row.problem ? `<span class="ingredient-issue">${rowIssues[row.problem]}</span>` : ''}`;
}

function recipeNutritionCaption(recipe) {
    const report = recipe.nutrition_report;
    const value = report?.values.kcal;
    if (value) return `${nutritionValue(value, 'kcal')} kcal / portion`;
    if (report?.calculated) return `Nutrition à compléter · ${report.calculated}/${report.total} ingrédients`;
    return 'Nutrition à renseigner';
}

function editRecipe(original) {
    const recipe = original || {id:'',version:0,title:'',servings:2,ingredients:[],tags:[],method:''};
    const ingredients = recipe.ingredients.map(item => ({...item}));
    if (!ingredients.length) ingredients.push({name:'',quantity:'',unit:'g'});
    let previewTimer;
    let previewVersion = 0;
    let preview = recipe.nutrition_report;
    const edibleWeight = item => item.grams_per_unit && +item.quantity > 0
        ? Math.round(item.grams_per_unit * item.quantity * 1000) / 1000 : '';
    modal(`<h2>${recipe.id ? 'Modifier la recette' : 'Nouvelle recette'}</h2>
        <form id="recipe-form">
            <label for="recipe-title">Titre</label><input id="recipe-title" name="title" value="${esc(recipe.title)}" required>
            <div class="row recipe-form-row">
                <label>Portions <input name="servings" type="number" min="0.001" max="100" step="any" value="${recipe.servings}" required></label>
                <label>Étiquettes (séparées par des virgules) <input name="tags" value="${esc(recipe.tags.join(', '))}"></label>
            </div>
            <div id="recipe-nutrition-preview" aria-live="polite"></div>
            <h3>Ingrédients</h3>
            <div id="ingredient-rows"></div>
            <datalist id="ingredient-units">${ingredientUnits.map(unit => `<option value="${unit}"></option>`).join('')}</datalist>
            <button type="button" id="add-ingredient">+ Ajouter un ingrédient</button>
            <label>Préparation<textarea name="method" rows="7" required>${esc(recipe.method)}</textarea></label>
            <fieldset class="recipe-freezer-fields"><legend>Congélation</legend>
                <label class="check-row"><input type="checkbox" name="freezer_ok" ${recipe.freezer_ok ? 'checked' : ''}> Le plat complet se congèle bien</label>
                <label>Conseil pour la congélation ou le réchauffage<textarea name="freezer_note" rows="2" maxlength="500">${esc(recipe.freezer_note || '')}</textarea></label>
            </fieldset>
            <div class="recipe-editor-actions"><button class="primary">Enregistrer la recette</button>
                <p id="recipe-save-error" role="alert"></p></div>
        </form>`);
    const form = $('#recipe-form');
    const alive = () => $('#modal').open && $('#recipe-form') === form;

    function paintPreview(report) {
        $('#recipe-nutrition-preview').innerHTML = recipeNutrition(report);
        $('#ingredient-rows').querySelectorAll('[data-ingredient-status]').forEach((element, index) => {
            const row = report?.rows[index];
            element.innerHTML = ingredientNutrition(row);
            const editor = element.closest('[data-ingredient]');
            editor.querySelector('[data-unlink-food]').hidden = !row?.food_id;
            editor.querySelector('[data-food-search]').textContent = row?.food_id ? 'Changer la référence' : 'Rechercher un aliment';
        });
    }

    function validIngredients() {
        return ingredients.length && ingredients.every(item =>
            item.name.trim() && +item.quantity > 0 && item.unit.trim() &&
            (item.grams_per_unit == null || +item.grams_per_unit > 0));
    }

    function requestPreview() {
        clearTimeout(previewTimer);
        const version = ++previewVersion;
        if (!validIngredients() || !form.elements.servings.checkValidity()) {
            paintPreview(null);
            return;
        }
        previewTimer = setTimeout(async () => {
            try {
                const report = await api('nutrition/preview', {servings:+form.elements.servings.value, ingredients});
                if (alive() && version === previewVersion) {
                    preview = report;
                    paintPreview(report);
                }
            } catch (error) {
                if (alive() && version === previewVersion) $('#recipe-nutrition-preview').textContent = error.message;
            }
        }, 180);
    }

    function renderIngredients() {
        $('#ingredient-rows').innerHTML = ingredients.map((item, index) => `<fieldset class="ingredient-edit" data-ingredient="${index}">
            <legend>Ingrédient ${index + 1}</legend>
            <div class="ingredient-fields">
                <label>Aliment<input data-field="name" maxlength="200" value="${esc(item.name)}" required></label>
                <label>Quantité<input data-field="quantity" type="number" min="0.001" max="1000000" step="any" value="${esc(item.quantity)}" required></label>
                <label>Unité<input data-field="unit" list="ingredient-units" maxlength="40" value="${esc(item.unit)}" required></label>
                <button type="button" class="icon" data-remove-ingredient aria-label="Retirer l’ingrédient ${index + 1}" ${ingredients.length === 1 ? 'disabled' : ''}>×</button>
            </div>
            <div class="ingredient-meta">
                <p data-ingredient-status>${ingredientNutrition(preview?.rows[index])}</p>
                <div class="row">
                    <button type="button" class="small" data-food-search>Rechercher un aliment</button>
                    <button type="button" class="small" data-unlink-food hidden>Dissocier</button>
                </div>
                <label class="ingredient-weight" ${massUnits.has(item.unit.trim().toLowerCase()) ? 'hidden' : ''}>
                    Poids comestible total (g)
                    <input data-field="edible_weight" type="number" min="0.001" max="1000000" step="any" value="${edibleWeight(item)}" placeholder="À peser">
                </label>
                <div data-food-results></div>
            </div>
        </fieldset>`).join('');
        document.querySelectorAll('[data-ingredient]').forEach((row, index) => bindIngredient(row, ingredients[index], index));
    }

    function renderAndPreview(focus) {
        preview = null;
        renderIngredients();
        requestPreview();
        focus?.();
    }

    function bindIngredient(row, item, index) {
        row.querySelectorAll('[data-field]').forEach(input => {
            input.oninput = () => {
                const field = input.dataset.field;
                if (field === 'edible_weight') {
                    item.grams_per_unit = input.value && +item.quantity > 0 ? +input.value / +item.quantity : null;
                    if (item.grams_per_unit) delete item.weight_reference;
                    requestPreview();
                    return;
                }
                if (field === 'name' && searchText(item.name.trim()) !== searchText(input.value.trim())) {
                    delete item.food_id;
                    item.grams_per_unit = null;
                    delete item.weight_reference;
                    row.querySelector('[data-field=edible_weight]').value = '';
                }
                if (field === 'unit' && item.unit !== input.value) {
                    item.grams_per_unit = null;
                    delete item.weight_reference;
                    row.querySelector('[data-field=edible_weight]').value = '';
                    row.querySelector('.ingredient-weight').hidden = massUnits.has(input.value.trim().toLowerCase());
                }
                item[field] = input.type === 'number' ? (input.value === '' ? null : +input.value) : input.value;
                if (field === 'quantity') row.querySelector('[data-field=edible_weight]').value = edibleWeight(item);
                requestPreview();
            };
        });
        row.querySelector('[data-remove-ingredient]').onclick = () => {
            ingredients.splice(index, 1);
            renderAndPreview();
        };
        row.querySelector('[data-food-search]').onclick = () => searchForIngredient(row, item, index);
        const unlink = row.querySelector('[data-unlink-food]');
        if (unlink) unlink.onclick = () => {
            item.food_id = null;
            delete item.weight_reference;
            renderAndPreview();
        };
    }

    function searchForIngredient(row, item, index) {
        const container = row.querySelector('[data-food-results]');
        container.innerHTML = `<div class="row food-search">
            <input aria-label="Aliment à rechercher" value="${esc(item.name)}" maxlength="100">
            <button type="button" class="small">Rechercher</button>
            <button type="button" class="small" data-close-search>Fermer</button></div>
            <div class="food-results" aria-live="polite"></div>`;
        const input = container.querySelector('input');
        const results = container.querySelector('.food-results');
        let sequence = 0;
        async function find() {
            const id = ++sequence;
            if (input.value.trim().length < 2) {results.textContent = 'Saisissez au moins deux caractères.'; return;}
            results.textContent = 'Recherche…';
            try {
                const foods = await api('foods?q=' + encodeURIComponent(input.value));
                if (!alive() || !results.isConnected || id !== sequence) return;
                results.innerHTML = foods.length ? foods.map((food, n) => `<button type="button" data-food="${n}">
                    <strong>${esc(food.name)}</strong>
                    <small>${typeof food.per_100g.kcal === 'number' ? formatNutrition(food.per_100g.kcal) + ' kcal / 100 g' : 'Énergie non chiffrée'} · ${esc(food.source?.name || food.group)}</small></button>`
                ).join('') : '<p>Aucun résultat. Essayez un nom plus court ou précisez cru, cuit ou égoutté.</p>';
                results.querySelectorAll('[data-food]').forEach(button => button.onclick = () => {
                    const food = foods[+button.dataset.food];
                    if (item.food_id && item.food_id !== food.id) {
                        item.grams_per_unit = null;
                        delete item.weight_reference;
                    }
                    item.food_id = food.id;
                    if (!item.name.trim()) item.name = food.name;
                    renderAndPreview(() => document.querySelector(`[data-ingredient="${index}"] [data-field=quantity]`).focus());
                });
            } catch (error) {
                if (id === sequence) results.textContent = error.message;
            }
        }
        container.querySelector('button').onclick = find;
        container.querySelector('[data-close-search]').onclick = () => {container.innerHTML = '';};
        input.onkeydown = event => {if (event.key === 'Enter') {event.preventDefault(); find();}};
        input.focus();
        input.select();
        find();
    }

    $('#add-ingredient').onclick = () => {
        ingredients.push({name:'',quantity:'',unit:'g'});
        renderAndPreview(() => $('#ingredient-rows [data-ingredient]:last-child input')?.focus());
    };
    form.elements.servings.oninput = requestPreview;
    form.onsubmit = async event => {
        event.preventDefault();
        const button = form.querySelector('button[type=submit], .recipe-editor-actions button');
        button.disabled = true;
        $('#recipe-save-error').textContent = '';
        try {
            const fields = Object.fromEntries(new FormData(form));
            await api('recipes', {
                id:recipe.id || undefined, version:recipe.version, title:fields.title, method:fields.method,
                servings:+fields.servings, tags:fields.tags.split(',').map(tag => tag.trim()).filter(Boolean),
                freezer_ok:form.elements.freezer_ok.checked, freezer_note:fields.freezer_note, ingredients,
            });
            $('#modal').close();
            await refresh();
            toast('Recette enregistrée');
        } catch (error) {
            if (alive()) $('#recipe-save-error').textContent = error.message;
        } finally {
            button.disabled = false;
        }
    };
    renderIngredients();
    paintPreview(preview);
}
