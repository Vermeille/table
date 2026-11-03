# Verification

2026-11-03, deployed at https://table.vermeille.fr.

- Domain/API suite: recipe snapshots, quantity scaling, stale edits, downstream approval invalidation, learning history/reinitialization, path validation, active-cart editing guard, role access, exact owner product approvals, duplicate prevention, unknown outcomes, existing-cart protection and credential redaction. Test retailer calls are mocked in this suite; this does not establish live Chronodrive account compatibility.
- Fresh installation: four profiles created from an empty Hermes home, configured with explicit model/worker parameters, updated with learned guidance, and tested for refusal to overwrite unmanaged/other-installation profiles. No previous OAuth grants or personal config present. This is an isolated provisioning test; live inference requires model authentication afterward.
- Real Hermes cookbook run: saved `roasted-pepper-pizza` with ingredients, method, tags and estimated nutrition through the app skill/CLI.
- Real Hermes planning run: seven dinners saved for 2026-11-09. App approved that plan. Real shopper run then saved 33 combined ingredients, with grocery approval left pending.
- Browser: desktop/mobile recipe browsing and detail, preference persistence, model/retailer settings, mobile chat, meal search/pick/swap, servings, plan approval, ingredient aggregation, pantry checkbox, grocery approval, saved-week reopening and downstream approval reset after editing. No JavaScript errors.
- Live Chronodrive frontend configuration parsing succeeds without login. Account-authenticated search/cart read and real cart additions remain unverified until the owner connects their account and approves exact products. No cart mutations made during these checks.
- Rebuilt and redeployed through Coolify. Recipes and the saved example week persisted across deployment. HTTPS verified with normal certificate validation.
