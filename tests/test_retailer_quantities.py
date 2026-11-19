import unittest

from retailer_quantities import content, drained, matches_form, pack_options, quantity_for


class RetailerQuantities(unittest.TestCase):
    def test_mass_and_multipack_calculate_whole_packs(self):
        pack=content({'labels':{'unitQuantityLabel':'3 x 125 g'}})
        self.assertEqual(pack,{'amount':375,'unit':'g'})
        grocery={'name':'Riz complet','quantity':740,'unit':'g'}
        self.assertEqual(quantity_for(grocery,{'pack':pack},1)['quantity'],2)
        self.assertEqual(quantity_for({**grocery,'quantity':750},{'pack':pack},7)['quantity'],2)
        self.assertEqual(quantity_for({**grocery,'quantity':751},{'pack':pack},1)['quantity'],3)

    def test_drained_requirement_does_not_use_total_or_dry_weight(self):
        pack={'amount':500,'unit':'g'}
        grocery={'name':'Pois chiches en conserve, poids égoutté','quantity':420,'unit':'g'}
        self.assertIsNone(quantity_for(grocery,{'pack':pack},1))
        reference=drained({'eans':['3083681085860','3083681085860']})
        result=quantity_for(grocery,{'pack':pack,'drained':reference},1)
        self.assertEqual(result['quantity'],2)
        self.assertEqual(result['pack_source'],reference['url'])

    def test_units_match_or_ask_for_review(self):
        grocery={'name':'Huile d’olive','quantity':56,'unit':'ml'}
        pack=content({'packaging':{'unitMeasure':.75,'unit':'L'}})
        self.assertTrue(quantity_for(grocery,{'pack':pack},3)['verified_quantity'])
        self.assertEqual(quantity_for(grocery,{'pack':pack},3)['quantity'],1)
        self.assertFalse(quantity_for({**grocery,'unit':'g'}, {'pack':pack},3)['verified_quantity'])

    def test_known_volume_conversion_is_identified_as_approximate(self):
        grocery={'name':'Huile de colza','quantity':945,'unit':'g'}
        product={'name':'Huile de colza vierge','pack':{'amount':1000,'unit':'ml'}}
        result=quantity_for(grocery,product,1)
        self.assertEqual(result['quantity'],2)
        self.assertIn('env.',result['note'])
        self.assertTrue(result['pack_source'].startswith('https://www.fao.org/'))
        self.assertFalse(quantity_for(grocery,{**product,'name':'Huile de tournesol'},1)['verified_quantity'])

    def test_uses_consumer_package_size_when_retailer_measure_fields_disagree(self):
        raw={'labels':{'unitQuantityLabel':'250 g'},'packaging':{'unitMeasure':.3,'unit':'kg'}}
        self.assertEqual(content(raw),{'amount':250,'unit':'g'})
        grocery={'name':'Concombre','quantity':510,'unit':'g'}
        self.assertEqual(quantity_for(grocery,{'pack':content(raw)},1)['quantity'],3)

    def test_portions_and_reconstituted_volume_have_independent_sizes(self):
        wraps={'pack':{'amount':350,'unit':'g'}, 'pack_options':pack_options({'labels':{'portionLabel':'6 pièces'}})}
        result=quantity_for({'name':'Wraps','quantity':7,'unit':'pièce'},wraps,1)
        self.assertEqual(result['quantity'],2)
        stock={'pack':{'amount':120,'unit':'g'}, 'pack_options':pack_options({'eans':['7613036750011']})}
        result=quantity_for({'name':'Bouillon de légumes','quantity':2200,'unit':'ml'},stock,4)
        self.assertEqual(result['quantity'],1)
        self.assertIn('1 cube pour 500 ml',result['note'])
        self.assertFalse(quantity_for({'name':'Bouillon de bœuf','quantity':125,'unit':'ml'},stock,1)['verified_quantity'])

    def test_dough_requires_plain_dough_instead_of_a_kit(self):
        grocery={'name':'Pâte à pizza','quantity':500,'unit':'g'}
        self.assertFalse(matches_form(grocery,{'name':'Kit pour pizza rectangulaire'}))
        self.assertTrue(matches_form(grocery,{'name':'Pâte à pizza rectangulaire à dérouler'}))
