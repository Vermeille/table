const {chromium} = require('playwright');
const assert = require('node:assert/strict');

(async () => {
    const browser = await chromium.launch({args:['--no-sandbox']});
    const page = await browser.newPage({ viewport:{width:1440,height:970},locale:'fr-FR' });
    const errors = [];
    const chats = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
        if (request.url().endsWith('/api/chat')) chats.push(request.postDataJSON().role);
    });
    const base = 'http://127.0.0.1:8891';
    const week = '2027-03-08';
    const output = process.env.QA_RESULTS || '/tmp';
    const screenshot = (file, fullPage = false) => page.screenshot({path:output+'/'+file, fullPage});
    const click = label => page.getByRole('button', {name:label, exact:true}).click();
    const heading = name => page.getByRole('heading', {name, exact:true}).waitFor();
    await page.goto(base + '/?week=' + week);
    await page.locator('#password').fill('guided-test');
    await page.getByRole('button',{name:/Entrer/}).click();
    await heading('Planning des repas');

    // Prepare a known cookbook recipe, then pick it using the actual schedule UI.
    const recipe = await page.request.post(base+'/api/recipes',{data:{
        id:'diner-qa',title:'Dîner saumon et riz',servings:2,method:'Cuire et servir.',
        ingredients:[
            {name:'Tomates',quantity:300,unit:'g'}, {name:'Saumon',quantity:500,unit:'g'},
            {name:'Riz',quantity:100,unit:'g'}, {name:'Huile',quantity:2,unit:'c. à soupe'},
            {name:'Ciboulette',quantity:1,unit:'botte'}
        ]
    }});
    assert.equal(recipe.status(),200);
    await page.reload();
    await page.locator('[data-add-day="0"]').click();
    await page.locator('#pick-search').fill('Dîner saumon');
    await page.locator('[data-pick="diner-qa"]').click();
    await page.getByText('1 repas prévu',{exact:true}).waitFor();
    await screenshot('planning.png');
    await click('Valider les repas et préparer les courses →');
    await heading('Liste de courses');
    await page.getByText('Préparation des courses…',{exact:true}).waitFor();
    await page.getByRole('checkbox',{name:'Déjà en réserve : Huile',exact:true}).check();
    await page.getByText('4 à acheter · 1 en réserve',{exact:true}).waitFor();

    // Edit a quantity and immediately continue without clicking a separate Save.
    await page.locator('[data-grocery-quantity="2"]').fill('160');
    await click('Valider les courses et chercher les produits →');
    await heading('Sélection Chronodrive');
    await page.getByText('Recherche des produits dans votre magasin…',{exact:true}).waitFor();
    const fill = page.getByRole('button',{name:'Valider et remplir le panier →',exact:true});
    await fill.waitFor();
    assert(await fill.isDisabled());
    assert.deepEqual(chats,['shopper','cart']);
    const state = () => page.request.get(base+'/api/state?week='+week).then(r=>r.json());
    assert.equal((await state()).week.groceries.items.find(i=>i.name==='Riz').quantity,160);
    const invalid = await page.request.post(base+'/api/week/'+week+'/approve-and-fill',{data:{version:(await state()).week.version}});
    assert.equal(invalid.status(),409);
    assert.equal((await state()).fill_job,null);
    await click('Ne pas acheter');
    await page.locator('[data-action=approve-and-fill]:enabled').waitFor();

    // Check the sticky approval on a phone after scrolling down the selection.
    await page.setViewportSize({width:390,height:844});
    await page.locator('.product-grid').evaluate(el=>el.scrollIntoView({block:'end'}));
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
    assert((await fill.boundingBox()).y < 844);
    await screenshot('produits-mobile.png', true);
    const version = (await state()).week.version;
    await fill.click();
    await heading('Panier Chronodrive');
    assert.equal((await page.request.post(base+'/api/week/'+week+'/approve-and-fill',{data:{version}})).status(),409);
    await page.reload();
    await heading('Panier Chronodrive');
    assert.equal(new URL(page.url()).searchParams.get('week'),week);
    await page.getByText('2 / 3 produits vérifiés',{exact:true}).waitFor();
    await page.getByText('En rupture de stock',{exact:true}).waitFor();
    await screenshot('panier-partiel.png');
    assert(await page.getByRole('button',{name:'Choisir un remplacement',exact:true}).evaluate(el=>el.classList.contains('primary')));
    await click('Choisir un remplacement');
    await page.getByText('Indisponible dans ce magasin',{exact:true}).waitFor();
    assert(await page.locator('[data-select-product="0"]').isDisabled());
    await page.getByLabel('Paquets',{exact:true}).nth(1).fill('2');
    await page.locator('[data-select-product="1"]').click();
    await heading('Sélection Chronodrive');
    await fill.click();
    await page.getByText('3 / 3 produits vérifiés',{exact:true}).waitFor();
    await page.getByText('Panier rempli et vérifié',{exact:true}).waitFor();
    assert.equal((await page.getByRole('link',{name:/Ouvrir Chronodrive/}).getAttribute('href')),'https://www.chronodrive.com');
    const receipt = await page.request.get(base+'/api/fixture-receipt').then(r=>r.json());
    assert.deepEqual(receipt,{cart:{'already-there':3,rice:1,'salmon-new':2},writes:['salmon-old','rice','salmon-new']});
    assert.deepEqual(errors,[]);
    await screenshot('panier-termine.png');
    await browser.close();
    console.log('PASS: plan picker → approval → automatic grocery draft → rapid edit and approval → automatic product search → missing item resolution → atomic fill → reload → stock failure → replacement → verified cart. Existing quantities preserved. Desktop and 390px mobile.');
})().catch(error => { console.error(error); process.exit(1); });
