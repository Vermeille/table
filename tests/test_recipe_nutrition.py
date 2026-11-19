import tempfile
import unittest
from pathlib import Path

import domain as D
import recipe_nutrition as N


class CiqualNutrition(unittest.TestCase):
    def test_catalog_and_raw_cooked_search(self):
        self.assertEqual(sum(not id.startswith('fdc-') for id in N.foods()), 3484)
        dry, cooked, *_ = N.search('lentilles corail')
        self.assertEqual({dry['id'], cooked['id']}, {'20535', '20589'})
        self.assertEqual(N.search('lentilles corail sèches')[0]['id'], '20535')

    def test_two_forms_and_portion_scaling_use_source_values(self):
        ingredients = [
            {'name':'Lentilles corail sèches', 'quantity':.2, 'unit':'kg'},
            {'name':'Lentilles corail cuites', 'quantity':100, 'unit':'g'},
        ]
        rows, values, report = N.calculate({'servings':2, 'ingredients':ingredients})
        self.assertEqual([row['food_id'] for row in rows], ['20535', '20589'])
        self.assertEqual(values, {'kcal':389.5,'protein_g':33.0,'carbs_g':52.4,'fat_g':1.05})
        self.assertEqual(report['calculated'],2)

    def test_volume_and_piece_require_edible_weight(self):
        ingredients = [{'name':'Lait de coco', 'quantity':100, 'unit':'ml'}]
        _, values, report = N.calculate({'servings':2, 'ingredients':ingredients})
        self.assertEqual(values, {})
        self.assertEqual(report['rows'][0]['problem'], 'weight')
        ingredients[0]['grams_per_unit'] = 1.01
        _, values, report = N.calculate({'servings':2, 'ingredients':ingredients})
        self.assertEqual(report['rows'][0]['grams'], 101)
        self.assertAlmostEqual(report['values']['kcal']['low'], 100.495)
        ingredients = [{'name':'avocat', 'quantity':2, 'unit':'pièce','food_id':'13004','grams_per_unit':105}]
        _, values, report = N.calculate({'servings':4, 'ingredients':ingredients})
        self.assertEqual(report['rows'][0]['grams'], 210)
        self.assertIn('kcal', values)

    def test_partial_subtotal_stays_separate_from_recipe_totals(self):
        ingredients = [{'name':'Lentilles corail sèches','quantity':100,'unit':'g'},
                       {'name':'Lait de coco','quantity':100,'unit':'ml'}]
        _, values, report = N.calculate({'servings':2,'ingredients':ingredients})
        self.assertEqual(values, {})
        self.assertEqual(report['values'], {})
        self.assertEqual(report['subtotals']['kcal']['low'], 164)

    def test_usda_cooked_black_beans_use_available_carbohydrate(self):
        _, values, report = N.calculate({'servings':2,'ingredients':[
            {'name':'haricots noirs cuits','quantity':200,'unit':'g','food_id':'fdc-173735'}]})
        self.assertEqual(values, {'kcal':132,'protein_g':8.86,'carbs_g':15.01,'fat_g':.54})
        self.assertEqual(report['sources'], [N.USDA_SOURCE])
        self.assertTrue(report['rows'][0]['food_reference_url'].endswith('/173735/nutrients'))

    def test_documented_reference_weight_can_be_replaced_by_measurement(self):
        ingredient = {'name':'citron','quantity':1,'unit':'pièce','food_id':'2007','weight_reference':'half_lemon_juice'}
        _, _, report = N.calculate({'servings':2,'ingredients':[ingredient]})
        self.assertEqual(report['rows'][0]['grams'], 24)
        self.assertEqual(report['rows'][0]['weight_source'], 'reference')
        ingredients, _, report = N.calculate({'servings':2,'ingredients':[{**ingredient,'grams_per_unit':15}]})
        self.assertEqual(report['rows'][0]['grams'], 15)
        self.assertEqual(report['rows'][0]['weight_source'], 'entered')
        self.assertNotIn('weight_reference', ingredients[0])
        with self.assertRaisesRegex(ValueError, 'ne correspond pas'):
            N.calculate({'servings':2,'ingredients':[{**ingredient,'food_id':'13125'}]})

    def test_qualitative_and_bounded_values_are_not_replaced_with_zero(self):
        ingredients = [{'name':'huile d’olive', 'quantity':20, 'unit':'ml'},
                       {'name':'Citron vert','quantity':100,'unit':'g','food_id':'13067'}]
        _, values, report = N.calculate({'servings':1, 'ingredients':ingredients})
        self.assertEqual(report['rows'][0]['weight_source'], 'olive_density')
        self.assertNotIn('carbs_g', values)
        self.assertTrue(report['values']['carbs_g']['trace'])
        self.assertAlmostEqual(report['values']['fat_g']['high'] - report['values']['fat_g']['low'], .3)
        _, values, report = N.calculate({'servings':1, 'ingredients':[{'name':'ricotta','quantity':50,'unit':'g'}]})
        self.assertTrue(report['missing'])
        self.assertNotEqual(len(values), len(N.MACROS))

    def test_recipe_save_rejects_fabricated_source_and_ignores_supplied_totals(self):
        prior = D.DATA
        with tempfile.TemporaryDirectory() as directory:
            D.DATA = Path(directory)
            try:
                D.init()
                recipe = D.save_recipe({'id':'test-dal','title':'Dahl','method':'Cuire.', 'servings':2,
                    'ingredients':[{'name':'lentilles corail sèches','quantity':200,'unit':'g'}],
                    'nutrition':{'kcal':12},'nutrition_report':{'bogus':True}})
                self.assertEqual(recipe['nutrition']['kcal'],328)
                self.assertEqual(recipe['nutrition_report']['calculated'],1)
                self.assertIn('20535',(D.DATA/'cookbook/test-dal.md').read_text())
                with self.assertRaisesRegex(ValueError,'référence valide'):
                    D.save_recipe({**recipe,'ingredients':[{'name':'Lentilles','quantity':200,'unit':'g','food_id':'fake'}]})
            finally:
                D.DATA = prior

    def test_archived_snapshot_projection_is_read_only(self):
        old = {'id':'old','recipe_id':'old','servings':2,
            'nutrition':{'kcal':800},'ingredients':[{'name':'lentilles corail sèches','quantity':100,'unit':'g'}]}
        projected = N.project_week({'slots':[{'recipe':old}]})
        self.assertEqual(projected['slots'][0]['recipe']['nutrition']['kcal'],164)
        self.assertEqual(old['nutrition']['kcal'],800)
        self.assertNotIn('food_id',old['ingredients'][0])
