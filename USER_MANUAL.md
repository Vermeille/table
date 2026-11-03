# Using Table

Sign in with the password configured at installation. The right panel is your assistant; on a phone, use **Kitchen assistant**. Changing the assistant does not change the selected week. Chat changes appear in the main app when saved. A running assistant can be stopped, and tool approval or clarification requests appear in the conversation.

## 1. Set your preferences

Open **Preferences**. Describe household size, dietary constraints, foods you like/dislike, time available and desired variety under **Your meals**. Use **Your shopping** for pantry and grocery habits, and **Your products** for brands, pack sizes and substitutions. Save. These are persistent inputs read by the assistants, not a one-off chat message. New preferences guide future runs; already approved plans remain unchanged until you ask to revise them.

## 2. Grow the cookbook

Open **Cookbook**. Search titles/tags and tap a recipe to see ingredients, method and estimated nutrition. **Add recipe** opens a manual editor; ingredient lines use `quantity | unit | name`. Existing recipes can be edited and downloaded as Markdown.

Select the cookbook assistant and try:

- “Add four different pizzas, including two vegetarian ones.”
- “Make a new version of this recipe without sour cream. Keep the original.”
- “Make this recipe healthier, explaining what you changed.”

The assistant writes actual cookbook records through its skill. Nutrition is an estimate, including the bundled sample recipes. Variants have separate IDs so the original remains available.

## 3. Plan a week

In **This week**, choose a week using the arrows or date picker. **Help me plan** prepares a message; press **Send** to run it. Ask for iterations such as “Swap Wednesday for something quicker” or “Less pasta, and use the leftover vegetables.”

Use **Pick a meal** to search your cookbook directly. **Swap** changes an individual meal, servings can be edited, and × removes a slot. You may schedule breakfast, lunch and dinner; dinner is the assistant's default. Tap a planned meal to see its stored recipe.

When satisfied, press **Approve this week**. It saves recipe snapshots with the plan. **Saved weeks** lets you return later. You can re-edit a week; each edit reopens approval and removes downstream groceries and product proposals so they cannot refer to an obsolete plan.

## 4. Review groceries

Open **Shopping** after approving meals. **Ask the shopper** prepares a request to combine ingredients and apply your preferences. Press **Send**. Alternatively **Start with ingredient totals** creates the deterministic scaled list immediately.

Edit ingredient names, quantities or units. Tick items already in your pantry, add missing items, or remove anything unnecessary. Changes are saved immediately and require approval again. Press **Approve groceries** when finished.

## 5. Choose products and fill Chronodrive

First save your Chronodrive account/store in **Connections**. Credentials are entered there, not in chat. Test the connection before starting.

Choose **Find Chronodrive products**, then send the prepared message. The cart assistant searches the real store catalog and proposes exact products, pack quantities and sizing notes. It reads **Your products** and its learned brand preferences. Ask for alternatives before approval: “Use this brand for yoghurt” or “Choose smaller packs so we don’t waste the rest.” Unmatched ingredients must be resolved first.

Press **Approve these products**, then **Fill approved cart**. These are distinct actions: approving products alone does not change the cart. Table permits only the approved product IDs and quantities. It does not clear an existing cart or place an order. Review the assistant's result and open Chronodrive to check totals, availability, collection time and checkout yourself.

If an addition times out, its outcome is unknown. Stop and inspect the real cart; do not resend the request assuming nothing happened. Operation records are retained. Reconciliation currently requires an administrator; this PoC intentionally blocks further automatic additions after an unknown result.

## 6. Teach the assistants

Give concrete feedback: “I always prefer brand X for milk” or “Keep Fridays under 20 minutes.” Ask the assistant to remember it. Each role's skill can store learned guidance in Table and reinstall that guidance in Hermes. Open **Skills & learning** to inspect/edit it or restore an earlier revision. Explicit **Preferences** remain your primary settings; learned guidance supplements them.

## Connections and troubleshooting

On a fresh installation, set the Hermes URL/key, internal Table URL, provider and model, then **Install / update profiles**. Use **Sign in with OpenAI** for Codex subscription access, or enter an API key for OpenAI/API-compatible providers. Reinstalling profiles preserves Table recipes, weeks, preferences and learning.

If an assistant cannot connect, check the configured gateway URL, provider login and private Docker network. The Hermes gateway must reach the internal Table URL. If Stop/clarifications fail after replacing the Hermes container, recreate Table's bridge sidecar. If Chronodrive fails, verify credentials and store ID; its frontend API may have changed. A credentials-saved badge confirms storage, not successful authentication—use **Test connection**.
