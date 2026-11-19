const {chromium} = require('playwright');
const assert = require('node:assert/strict');

(async () => {
    const browser = await chromium.launch({args:['--no-sandbox']});
    const page = await browser.newPage({viewport:{width:1440,height:970},locale:'fr-FR'});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const base = 'http://127.0.0.1:8891';
    const week = '2027-03-08';
    const state = () => page.request.get(base+'/api/state?week='+week).then(r=>r.json());
    const click = name => page.getByRole('button',{name,exact:true}).click();
    const heading = name => page.getByRole('heading',{name,exact:true}).waitFor();
    const saveRecipe = (id, title, ingredient, freezer_ok) => page.request.post(base+'/api/recipes',{data:{
        id,title,servings:2,freezer_ok,method:'Préparer le plat.',
        ingredients:[{name:ingredient,quantity:200,unit:'g'}]
    }});
    await page.goto(base+'/?week='+week);
    await page.locator('#password').fill('guided-test');
    await page.getByRole('button',{name:/Entrer/}).click();
    await heading('Planning des repas');
    await page.locator('.nav [data-view=preferences]').click();
    await page.getByRole('checkbox',{name:/Prévoir des portions à congeler/}).check();
    await click('Enregistrer les préférences');
    await page.getByText('Préférences enregistrées',{exact:true}).waitFor();
    assert.equal((await state()).preferences.batch.enabled,true);
    assert.equal((await saveRecipe('chili-test','Chili doux','Haricots',true)).status(),200);
    assert.equal((await saveRecipe('salade-test','Salade croquante','Laitue',false)).status(),200);
    await page.reload();
    await heading('Planning des repas');

    // Sunday planning with an empty freezer. Cook one batch for two meals.
    for (const [day,id,search] of [[0,'chili-test','Chili doux'],[2,'chili-test','Chili doux'],[5,'salade-test','Salade croquante']]) {
        await page.locator(`[data-add-day="${day}"]`).click();
        await page.locator('#pick-search').fill(search);
        await page.locator(`[data-pick="${id}"]`).click();
        await page.locator('#modal').waitFor({state:'hidden'});
    }
    await page.getByText('Du congélateur',{exact:true}).waitFor();
    await page.getByText('À cuisiner en lot',{exact:true}).waitFor();
    await page.locator('.batch-list summary').click();
    await page.getByText('Cuisiner 6 portions et en congeler 4 · à ressortir mercredi',{exact:true}).waitFor();
    await page.locator('button.meal-title[data-slot="0-dinner"]').click();
    await page.getByText('600 g',{exact:true}).waitFor();
    await click('Fermer');
    await click('Valider les repas et préparer les courses →');
    await heading('Liste de courses');
    await page.locator('[data-grocery-quantity="0"]').waitFor();
    const groceries=(await state()).week.groceries.items;
    assert.deepEqual(Object.fromEntries(groceries.map(i=>[i.name,i.quantity])),{Haricots:600,Laitue:200});
    assert.equal((await state()).freezer.lots.length,0);
    await click('Repas');
    await heading('Planning des repas');
    await click('Sortir les portions');
    assert(await page.getByRole('button',{name:'Confirmer la sortie',exact:true}).isDisabled());
    await click('Fermer');
    await click('Confirmer la congélation');
    await click('Enregistrer les portions congelées');
    await page.getByText('✓ 4 portions congelées',{exact:true}).waitFor();
    await page.locator('.nav [data-view=freezer]').click();
    await heading('Congélateur');
    await page.getByText('4 portions · 2 disponibles',{exact:true}).waitFor();

    // Add an existing homemade dish with no cookbook recipe.
    await click('+ Ajouter un plat');
    await page.getByLabel('Nom du plat',{exact:true}).fill('Soupe maison du dimanche');
    await click('Enregistrer');
    await heading('Soupe maison du dimanche');
    await page.reload();
    await heading('Congélateur');

    // Serve the scheduled freezer meal on a phone. Inventory follows the confirmed action.
    await page.setViewportSize({width:390,height:844});
    await page.locator('.nav [data-view=week]').click();
    await heading('Planning des repas');
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    await click('Sortir les portions');
    await click('Confirmer la sortie');
    await page.getByText('✓ Sorti du congélateur',{exact:true}).waitFor();
    assert.equal((await state()).freezer.lots.find(lot=>lot.recipe.id==='chili-test').quantity,2);
    assert.equal((await state()).week.groceries.items.find(i=>i.name==='Haricots').quantity,600);
    await page.screenshot({path:(process.env.QA_RESULTS || '/tmp')+'/table-batch-plan.png',fullPage:true});

    // Plan the unlinked dish next week. A freezer-only week has an empty shopping draft.
    const next = '2027-03-15';
    await page.goto(base+'/?week='+next);
    await heading('Planning des repas');
    await page.locator('[data-add-day="0"]').click();
    await click('Choisir dans le congélateur');
    await page.locator('#frozen-meal-form select').selectOption({label:await page.locator('#frozen-meal-form option').filter({hasText:'Soupe maison du dimanche'}).textContent()});
    await click('Planifier ce repas');
    await click('Valider les repas et préparer les courses →');
    await page.getByText('Aucun ingrédient à acheter pour ces repas.',{exact:true}).waitFor();
    const onlyFreezer=await page.request.get(base+'/api/state?week='+next).then(r=>r.json());
    assert.deepEqual(onlyFreezer.week.groceries.items,[]);
    assert.equal(onlyFreezer.freezer.lots.find(lot=>lot.recipe.freezer_only).reserved,2);
    assert.deepEqual(errors,[]);
    await browser.close();
    console.log('PASS: enabling batches, empty freezer, one cook for two meals, exact groceries, confirmed portions, mobile stock use, custom freezer dish, next-week reservation, no-grocery handoff.');
})().catch(error=>{console.error(error);process.exit(1)});
