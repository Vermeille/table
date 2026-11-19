---
name: table-cookbook
description: Search, create, revise and make variants of recipes in the Table cookbook, including structured ingredients and nutrition linked to the Ciqual and selected USDA food records.
---
Use the adjacent table_cli.py. Start with help to get the exact schemas. Use the Table API for durable changes.

- Read an existing recipe with get_recipe before editing. Keep its ID, current version, and unaffected ingredients and metadata. For a variant, copy the relevant fields and save it with a new ID and version 0.
- Each ingredient has a quantity and unit. Match the food_id via search_foods when adding or replacing an ingredient. Choose the raw, dry, cooked or drained entry corresponding to how it is weighed. Recheck the entry when the food or weighing state changes. Leave uncertain matches unresolved.
- Keep food_id, grams_per_unit and weight_reference for unchanged ingredients. Changing quantity scales their grams per serving automatically. For a different food or unit, remove stale conversions. For a new piece or volume, use a matching weight_reference from search_foods when its description fits. Record grams_per_unit only from the owner's measurement or another verified source. Clear fields with null when intentionally discarding an old link or conversion.
- Use preview_recipe_nutrition to check coverage before saving a new or materially revised recipe. Inspect nutrition_report.rows for missing matches, weights or source values. Nutrition per serving is calculated by Table. Never invent totals or present a documented subtotal as a full recipe value.
- Preserve the owner's preferences, freezer information and learned guidance. Use learn for explicit reusable feedback. After saving, report what changed and any unresolved food links or weights.

Rédige toutes les réponses et tout contenu destiné à l’utilisateur en français : recettes, ingrédients, étiquettes, listes et indications apprises. Conserve les noms techniques des actions, champs JSON et identifiants existants.

Pour un plat cuit qui conserve une bonne texture une fois congelé puis réchauffé, indique `freezer_ok: true` et donne un court `freezer_note` en français. La propriété concerne le plat complet. Ne marque pas une salade crue, un plat qui se dégrade fortement à la décongélation, ou une recette dont tu ne connais pas le résultat.
