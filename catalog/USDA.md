# USDA FoodData Central supplemental records

Source: [USDA FoodData Central, SR Legacy, April 2018](https://fdc.nal.usda.gov/download-datasets/).
`usda-sr-supplement.json` contains four records transcribed from `food.csv` and `food_nutrient.csv` in the [official archive](https://fdc.nal.usda.gov/fdc-datasets/FoodData_Central_sr_legacy_food_csv_2018-04.zip). Table retains USDA energy (1008), protein (1003), and fat (1004). For comparison with Ciqual available carbohydrate, it subtracts dietary fiber (1079) from USDA total carbohydrate by difference (1005). Official archive SHA-256: `b80817294b8850530aaedf2e515c02593b1824f763a0ff356e5c2081643e6fd0`. Energy values retain each database's published calculation.

The explicit reference weights in the application use `food_portion.csv` from the same archive:

| Ingredient use | FDC identifier | Reference |
| --- | --- | --- |
| Juice from one lemon | 167747 | 48 g |
| Half the juice from one lemon | 167747 | 24 g (half the reference yield) |
| Juice from one lime | 168156 | 44 g |
| One garlic clove | 169230 | 3 g |
| Coconut milk, canned | 170173 | 226 g per US cup |
| Worcestershire sauce | 171610 | 17 g per US tablespoon |

The volume conversions use [NIST SI conversion factors](https://www.nist.gov/pml/special-publication-811/nist-guide-si-appendix-b9). Table labels these ingredient weights as references. Measured edible weight may replace a reference.
