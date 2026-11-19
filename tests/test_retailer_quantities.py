import unittest

from retailer_quantities import content, drained, quantity_for


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
