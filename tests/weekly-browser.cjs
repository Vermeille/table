const {chromium} = require('playwright');
const assert = require('node:assert/strict');

(async () => {
    const browser = await chromium.launch({args:['--no-sandbox']});
    try {
        const context = await browser.newContext({viewport:{width:390,height:844},locale:'fr-FR'});
        const page = await context.newPage();
        const errors = [];
        const interactiveRuns = [];
        page.on('pageerror', error => errors.push(error.message));
        page.on('request', request => {
            if (request.url().endsWith('/api/chat')) interactiveRuns.push(request.postDataJSON().role);
        });
        const base = 'http://127.0.0.1:8891';
        const week = '2030-01-07';
        const state = date => page.request.get(base+'/api/state?week='+date).then(r=>r.json());
        const post = (path, data) => page.request.post(base+'/api/'+path,{data});
        const click = name => page.getByRole('button',{name,exact:true}).click();
        const heading = name => page.getByRole('heading',{name,exact:true}).waitFor();
        await page.goto(base+'/?week='+week);
        await page.locator('#password').fill('guided-test');
        await page.getByRole('button',{name:/Entrer/}).click();
        await heading('Planning des repas');

        // The owner wrote a real draft and asks for help with the shopping.
        const ingredients = [
            {name:'Tomates',quantity:620,unit:'g',food_id:'20276'},
            {name:'Saumon',quantity:500,unit:'g',food_id:'26036'},
            {name:'Riz',quantity:100,unit:'g',food_id:'9100'}
        ];
        const recipe = await post('recipes',{id:'weekly-diner-qa',title:'Riz et saumon du mardi',
            servings:2,ingredients,method:'Cuire et servir.'});
        assert.equal(recipe.status(),200,await recipe.text());
        const written = await post('week/'+week+'/save',{version:0,slots:[
            {day:1,meal:'dinner',recipe_id:'weekly-diner-qa',servings:2}
        ]});
        assert.equal(written.status(),200,await written.text());
        await page.reload();
        await heading('Planning des repas');
        await click('Préparer les courses');
        await heading('Votre semaine est prête à relire');
        const ready = await state(week);
        assert.equal(ready.weekly.origin,'existing');
        assert.equal(ready.week.slots[0].day,1);
        assert.equal(ready.weekly.retailer.matched,2);
        assert.equal(ready.weekly.retailer.unmatched,1);
        assert.equal(ready.week.cart.matches.find(m=>m.productId==='already-there').quantity,2);
        assert.equal((await post('week/'+week+'/approve-and-fill',{version:ready.week.version})).status(),409);
        assert.equal((await page.request.get(base+'/api/fixture-receipt').then(r=>r.json())).writes.length,0);
        assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
        await page.screenshot({path:(process.env.QA_RESULTS || '/tmp')+'/weekly-ready-mobile.png',fullPage:true});

        // Keep the other match when marking one ingredient as already in the pantry.
        await click('Valider les repas et voir les courses →');
        await heading('Liste de courses');
        await page.getByRole('checkbox',{name:'Déjà en réserve : Tomates',exact:true}).check();
        await page.getByText('2 à acheter · 1 en réserve',{exact:true}).waitFor();
        await click('Valider les courses et voir les produits →');
        await heading('Sélection Chronodrive');
        assert.deepEqual((await state(week)).week.cart.matches.map(m=>m.productId),['rice']);
        assert(await page.getByRole('button',{name:'Valider et remplir le panier →',exact:true}).isDisabled());
        await click('Choisir un produit');
        await page.locator('#product-results').getByText('Pavés de saumon frais',{exact:true}).waitFor();
        await page.getByLabel('Paquets',{exact:true}).nth(1).fill('2');
        await page.locator('[data-select-product="1"]').click();
        await page.getByText('2 sélections · 3 paquets',{exact:true}).waitFor();
        assert.deepEqual(interactiveRuns,[]);
        await click('Valider et remplir le panier →');
        await heading('Panier Chronodrive');
        await page.getByText('Panier rempli et vérifié',{exact:true}).waitFor({timeout:35000});
        const receipt = await page.request.get(base+'/api/fixture-receipt').then(r=>r.json());
        assert.deepEqual(receipt,{cart:{'already-there':3,rice:1,'salmon-new':2},writes:['rice','salmon-new']});

        // Set a smaller household, fewer slots and a vegan preference through the real form.
        await page.getByText('Menu',{exact:true}).click();
        await page.getByRole('button',{name:'Préférences',exact:true}).click();
        const form=page.locator('#weekly-form');
        await form.getByLabel('Personnes',{exact:true}).fill('1');
        await form.getByLabel('Régime',{exact:true}).selectOption('vegan');
        await form.getByLabel('Dîner',{exact:true}).uncheck();
        for (const day of ['2','3','4','5','6']) await form.locator('[name=days][value="'+day+'"]').uncheck();
        await form.locator('[name=no_cook][value="1"]').check();
        await form.getByLabel('Ingrédients toujours en réserve',{exact:true}).fill('Paprika');
        await click('Enregistrer la préparation');
        await page.getByText('Préparation hebdomadaire enregistrée',{exact:true}).waitFor();
        await page.getByRole('heading',{name:'Notifications sur cet appareil',exact:true}).waitFor();
        await context.waitForEvent('serviceworker', {predicate:worker=>worker.url().includes('service-worker.js'), timeout:1000}).catch(()=>{});
        assert(context.serviceWorkers().some(worker=>worker.url().includes('/service-worker.js')));

        const fresh = '2030-01-14';
        await page.goto(base+'/?week='+fresh);
        await click('Préparer cette semaine');
        await heading('Votre semaine est prête à relire');
        const solo = await state(fresh);
        assert.deepEqual(solo.week.slots.map(s=>[s.day,s.meal,s.servings]),[[0,'lunch',1],[1,'lunch',1]]);
        assert(solo.week.groceries.items.find(item=>item.name==='Paprika')?.checked);
        assert.deepEqual(solo.weekly.quality.no_cook_misses,[]);
        assert.equal(solo.weekly.quality.frozen_meals,1);
        assert.deepEqual(errors,[]);
        console.log('Brouillon, conservation des choix, quantités vérifiées, trois validations, panier de test et préférences sur mobile.');
    } finally {
        await browser.close();
    }
})().catch(error=>{console.error(error);process.exitCode=1});
