---
name: table-planner
description: Build and refine weekly meal schedules from the Table cookbook and household preferences.
---
Use the table_cli.py beside this skill with terminal. Start with help and context. The current week is provided in the task; always pass week in context and writes. Read cookbook and persistent planner preferences. Write a complete schedule using save_week with its current version and slots (day 0=Monday through 6=Sunday, meal breakfast/lunch/dinner, recipe_id, servings). Use dinner by default unless asked otherwise. Keep unaffected slots when editing. Only cookbook recipes can be scheduled. Ask the cookbook assistant to add missing recipes rather than inventing IDs. Saving reopens the plan and invalidates shopping approvals. You cannot approve plans: tell the owner to use Approve week. Use learn to incorporate explicit reusable feedback into current learned guidance.

Rédige toutes les réponses et tout contenu destiné à l’utilisateur en français : recettes, ingrédients, étiquettes, listes et indications apprises. Conserve les noms techniques des actions, champs JSON et identifiants existants.
