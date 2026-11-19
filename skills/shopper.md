---
name: table-shopper
description: Consolidate an approved Table meal plan into an editable grocery list, applying pantry and shopping preferences.
---
Use the adjacent table_cli.py with terminal. Read help and context for the task's week. Only work from an approved plan. Use grocery_base for deterministic ingredient scaling and unit normalization; keep unlike ingredients separate. Refine for explicit pantry and shopping preferences, retaining recipe quantities. Write via save_groceries with the exact week version and complete items. Each item has name, quantity, unit, note and checked=false; omit items explicitly already in pantry. Do not assume pantry staples. You cannot approve groceries; direct the owner to Approve groceries. Learn only explicit reusable feedback with learn, merging with existing guidance.

Rédige toutes les réponses et tout contenu destiné à l’utilisateur en français : recettes, ingrédients, étiquettes, listes et indications apprises. Conserve les noms techniques des actions, champs JSON et identifiants existants.

En mode cuisine en lots, utilise impérativement les quantités de `grocery_base`. Table a déjà compté les portions supplémentaires à cuisiner et exclu les repas du congélateur. Ne recompte pas les recettes de chaque créneau.
