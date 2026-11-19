---
name: table-cookbook
description: Search, create, revise and make variants of recipes in the Table cookbook, including ingredients and estimated nutrition.
---
Use the table_cli.py beside this skill with terminal. Run `python PATH/table_cli.py help '{}'` for exact schemas. All durable data belongs to Table; write recipes through the CLI, not your workspace. Read context and search recipes before changes. For a variant use a new ID and version 0; retain the original. For updates pass its current version. Include quantities, servings, tags, method and per-serving estimated nutrition (kcal, protein_g, carbs_g, fat_g); label estimates. Do not invent allergens or verified nutritional claims. After writing, report what was saved. Read preferences and the learned guidance below. If the owner gives reusable feedback, merge it into current learned guidance through learn; record only supported preferences, not guesses.

Rédige toutes les réponses et tout contenu destiné à l’utilisateur en français : recettes, ingrédients, étiquettes, listes et indications apprises. Conserve les noms techniques des actions, champs JSON et identifiants existants.

Pour un plat cuit qui conserve une bonne texture une fois congelé puis réchauffé, indique `freezer_ok: true` et donne un court `freezer_note` en français. La propriété concerne le plat complet. Ne marque pas une salade crue, un plat qui se dégrade fortement à la décongélation, ou une recette dont tu ne connais pas le résultat.
