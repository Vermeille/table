---
name: table-cookbook
description: Search, create, revise and make variants of recipes in the Table cookbook, including ingredients and estimated nutrition.
---
Use the table_cli.py beside this skill with terminal. Run `python PATH/table_cli.py help '{}'` for exact schemas. All durable data belongs to Table; write recipes through the CLI, not your workspace. Read context and search recipes before changes. For a variant use a new ID and version 0; retain the original. For updates pass its current version. Include quantities, servings, tags, method and per-serving estimated nutrition (kcal, protein_g, carbs_g, fat_g); label estimates. Do not invent allergens or verified nutritional claims. After writing, report what was saved. Read preferences and the learned guidance below. If the owner gives reusable feedback, merge it into current learned guidance through learn; record only supported preferences, not guesses.
