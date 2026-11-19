const {chromium} = require('playwright');
const assert = require('node:assert/strict');

(async () => {
    const browser = await chromium.launch({args:['--no-sandbox']});
    const page = await browser.newPage({viewport:{width:1420,height:980},locale:'fr-FR'});
    const base = 'http://127.0.0.1:8891';
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const button = name => page.getByRole('button',{name,exact:true});
    const choose = n => page.locator(`[data-ingredient="${n}"]`);
    const fill = (n, field, value) => choose(n).locator(`[data-field="${field}"]`).fill(value);
    const report = () => page.locator('#recipe-nutrition-preview .recipe-nutrition');
    await page.goto(base);
    await page.locator('#password').fill('guided-test');
    await page.getByRole('button',{name:/Entrer/}).click();
    await page.locator('.nav [data-view=cookbook]').click();
    await button('+ Ajouter une recette').click();
    await page.locator('#recipe-title').fill('Lentilles sèches et cuites');
    await page.locator('[name=method]').fill('Cuire les lentilles sèches, puis mélanger avec les lentilles déjà cuites.');
    await fill(0,'name','lentilles corail');
    await fill(0,'quantity','200');
    await choose(0).getByRole('button',{name:'Rechercher un aliment'}).click();
    await choose(0).getByRole('button',{name:/^Lentille corail, sèche/}).click();

    await button('+ Ajouter un ingrédient').click();
    await fill(1,'name','lentilles corail cuites');
    await fill(1,'quantity','100');
    await report().getByText('390',{exact:true}).waitFor();

    await page.setViewportSize({width:390,height:844});
    await button('+ Ajouter un ingrédient').click();
    await fill(2,'name','Lait de coco');
    await fill(2,'quantity','100');
    await fill(2,'unit','ml');
    await choose(2).getByText('Renseigner le poids comestible',{exact:true}).waitFor();
    assert.equal(await report().getByText('—',{exact:true}).count(),4);
    await fill(2,'edible_weight','100');
    await report().getByText('489',{exact:true}).waitFor();
    assert(await page.locator('#modal').evaluate(el=>el.scrollWidth<=el.clientWidth+1));
    await page.screenshot({path:(process.env.QA_RESULTS || '/tmp')+'/table-recipe-editor-mobile.png'});
    await button('Enregistrer la recette').click();
    await page.getByRole('button',{name:/Lentilles sèches et cuites/}).click();
    const modal = page.locator('#modal');
    await modal.getByRole('link',{name:/Anses · Ciqual 2025/}).waitFor();
    await modal.getByText('489',{exact:true}).waitFor();
    await modal.locator('#edit-recipe').click();
    await page.locator('#recipe-form [name=servings]').fill('4');
    await report().getByText('245',{exact:true}).waitFor();
    await button('Enregistrer la recette').click();
    const state=await page.request.get(base+'/api/state').then(r=>r.json());
    const recipe=state.recipes.find(r=>r.title==='Lentilles sèches et cuites');
    assert.equal(recipe.nutrition.kcal,244.5);
    assert.deepEqual(recipe.ingredients.map(i=>i.food_id),['20535','20589','18041']);
    assert.equal(recipe.ingredients[2].grams_per_unit,1);
    const archived = await page.request.post(base+'/api/recipes', {data:{
        title:'Haricots noirs au citron',servings:2,method:'Mélanger.',
        ingredients:[
            {name:'Haricots noirs cuits',quantity:200,unit:'g',food_id:'fdc-173735'},
            {name:'Citron',quantity:1,unit:'pièce',food_id:'2007',weight_reference:'lemon_juice'},
        ],
    }});
    assert.equal(archived.status(),200);
    await page.reload();
    await page.locator('.nav [data-view=cookbook]').click();
    await page.getByRole('button',{name:/Haricots noirs au citron/}).click();
    await modal.getByRole('link',{name:/Poids indicatif USDA/}).waitFor();
    await modal.getByRole('link',{name:/USDA · FoodData Central/}).waitFor();
    await modal.getByRole('link',{name:/Anses · Ciqual 2025/}).waitFor();
    assert.deepEqual(errors,[]);
    await browser.close();
    console.log('PASS: structured editor, dry/cooked search, volume without weight, explicit conversion, recalculated portions, persisted nutrition and mobile layout.');
})().catch(error=>{console.error(error);process.exit(1)});
