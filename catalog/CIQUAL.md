# Anses. 2025. Table de composition nutritionnelle des aliments Ciqual 2025

Source: [Recherche Data Gouv, DOI 10.57745/RDMHWY](https://doi.org/10.57745/RDMHWY).
Table ships a projection of the 3,484 foods from the [official French workbook](https://entrepot.recherche.data.gouv.fr/api/access/datafile/666260). Published workbook MD5: `0d9758ce23f3f13dd63a005bc1bb4f2c`.

Each row is `[alim_code, French label, subgroup, kcal, protein_g, carbs_g, fat_g]`. Values are per 100 g of edible food. The workbook uses EU 1169/2011 kcal and N × 6.25 protein. A detection limit is stored as `[0, upper]`. The string `trace` records an unquantified trace. Other unavailable values are `null`.

To reproduce the projection, download the source workbook and run `python3 tools/import_ciqual.py <workbook> catalog/ciqual-2025.json`. No remote requests are needed to search or calculate in Table.

For the Ciqual entry for extra virgin olive oil, Table offers a volume conversion of approximately 0.912 g/ml using the [relative density range in Codex CXS 33-1981, annex, section 2.1](https://www.fao.org/fao-who-codexalimentarius/sh-proxy/en/?lnk=1&url=https%3A%2F%2Fworkspace.fao.org%2Fsites%2Fcodex%2FStandards%2FCXS+33-1981%2FCXS_033f.pdf). Other non-mass units need an edible weight supplied by the user.
