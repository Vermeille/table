# Table

A self-hosted meal-planning app backed by Hermes. The app owns the cookbook, preferences, learned guidance, weekly plans, recipe snapshots, approvals and shopping-operation records. Hermes supplies the reasoning and tool execution through four disposable, app-managed profiles. There is no dependency on Hermes Studio, a preconfigured personal profile, or a hosted UI.

## Install against a fresh Hermes gateway

Tested with the Hermes runtime serving this deployment, image `nousresearch/hermes-agent:v0.22.5`. Hermes changes quickly; the profile helper and native Bot Chat API are the compatibility boundary. Table currently needs to run beside Hermes with access to its runtime volumes, not merely a remote API URL: Hermes' execution API does not expose complete profile administration.

1. Install and start a fresh Hermes gateway using its Docker installation. Enable its API gateway and set `API_SERVER_KEY`. Hermes must listen on port 8642 on a private Docker network, and serve named profiles. No existing profile configuration or model login is required.
2. Identify its container, network, Hermes data volume and source volume. The source volume contains `/opt/hermes/.venv`; data is mounted at `/opt/data`. Match its UID/GID (1000 in the tested image).
3. Build Table: `docker build -t table:0.1.0 .`.
4. Copy `.env.example` to `.env`, fill the gateway key, Table password, actual Docker resource names, hostname and internal URLs. Both Table and Hermes must resolve `TABLE_INTERNAL_URL`. Default service DNS is `http://table:8080` on the shared network.
5. Create the app volume: `docker volume create table-data`. Deploy `compose.yaml` using Docker Compose or a Coolify Docker Compose service. In Coolify set the `table` service domain to your HTTPS hostname, port 8080. Plain Docker requires your HTTPS reverse proxy; the compose file intentionally publishes no host ports. For isolated local development only, publish 8080 and set `COOKIE_SECURE=false`.
6. Open the app, sign in with `TABLE_PASSWORD`, then **Connections**. Pick OpenAI/Codex and **Sign in with OpenAI**, or select OpenAI API and enter a model/key. Custom OpenAI-compatible endpoints are supported through the base URL. Click **Install / update profiles**.
7. Confirm you can ask the cookbook assistant to add a recipe. Table creates `table-cookbook`, `table-planner`, `table-shopper` and `table-cart` from scratch with `create_profile(no_alias=True, no_skills=True)`. One Table installation per Hermes gateway is currently supported; its fixed profile IDs are reserved. The installer refuses to overwrite unmanaged profiles or profiles owned by another Table installation. It copies no personal config, memories, channels, recipes, OAuth tokens or existing skills. Codex sign-in uses Hermes' native root authentication mechanism; fresh installations sign in once. Native provider refresh remains Hermes' responsibility.
8. Connect Chronodrive in **Connections**, including the store ID from its website URL. **Test connection** reads the existing cart without changing it.

`tests/fresh_install.py` provisions all four profiles into an empty Hermes home, then updates them, without prior authentication. This tests profile installation, not an unauthenticated model inference. Real inference necessarily needs a provider connection configured in step 6.

The bridge shares the Hermes container network namespace and forwards only native authenticated session WebSockets on private port 8644. It enables Stop, tool approval and clarification UI. If the Hermes container is replaced, recreate the bridge. If another app uses 8644, select another bridge port and set `HERMES_OWNER_URL` on Table to match.

## Architecture

Browser → Table FastAPI → app SQLite and Markdown documents.
Table → Hermes named-profile Bot Chat sessions and Runs API.
Hermes terminal → generated profile skill + `table_cli.py` → role-scoped Table worker API.
Table → isolated Chronodrive client → Chronodrive frontend API.

All application data persists in `table-data`; Hermes profiles are generated projections. Recipes are versioned in SQLite and exported as individual Markdown files with JSON frontmatter under `cookbook/`. The database is authoritative; the Markdown projection is regenerated on startup and downloadable in the UI. Approved weeks contain recipe snapshots, so later cookbook edits do not change historical recipes. Editing a week resets meal approval and removes its downstream grocery/cart proposals. Editing groceries resets grocery approval and product selection. Preference changes apply to the next agent run; they do not silently modify already approved plans.

Worker credentials authorize different operations per role. No worker endpoint can approve a meal plan, groceries or product selection. The UI alone invokes those owner endpoints. The cart stage requires approval of exact products and pack quantities and an explicit **Fill approved cart** action. The app reserves each operation before dispatch; a timeout remains unknown and prevents more additions until reconciled. There is no checkout, payment, empty-cart or order-placement tool. Existing cart contents are preserved; additions of products already present are refused so their quantities cannot be overwritten. A skilled agent still has Hermes terminal access: these profiles run within the same trusted Hermes instance, not a security sandbox between mutually hostile tenants.

Self-improvement uses immutable base skill templates in `skills/` plus app-owned versioned learning. Assistants read context, incorporate explicit feedback via `learn`, and Table reprojects their skill. Owners can edit guidance and restore prior revisions in the UI. App upgrades preserve learning. The Chronodrive integration is a regular skill with a CLI, not an MCP server.

## Update, backup, removal

Back up **the whole `table-data` volume**, including `key`, encrypted connection files, SQLite database and cookbook directory; the key is needed to decrypt provider and Chronodrive credentials. Back up Hermes data separately for native chat history and provider authentication. Stop Table briefly for a simple consistent volume backup, or use SQLite's backup API. Do not back up only the `.db` file during writes.

Build the new image and redeploy the service. On startup Table reinstalls its four profiles from its source and persistent app configuration; learned guidance remains. Existing sessions are preserved. Do not update during an active cart fill. A crash during an external cart mutation requires inspecting the real cart; Table never automatically retries uncertain operations.

Removing Table leaves your Hermes instance and other profiles alone. To remove its generated profiles, stop Table first and use Hermes' profile deletion commands for these four IDs only. Never remove the shared Hermes volumes. Keep the Table data volume if you want your cookbook/plans back.

## Chronodrive provenance and limitations

`chronodrive_client.py` is adapted from [y-vex/chronodrive-mcp](https://github.com/y-vex/chronodrive-mcp); its MCP server is not included or used. Source commit is recorded in `CHRONODRIVE_SOURCE`. The client uses the same frontend HTTP APIs as that project, with bounded timeouts and isolated credentials. It requires the owner's account/store. Website changes, authentication challenges or API changes can break it. Search and cart addition cannot be claimed verified until tested with a connected account.

## Checks

`python -m unittest discover -s tests` runs domain tests. Additional Docker-based checks use the mounted Hermes source runtime: `tests/fresh_install.py`, `tests/test_api.py`, real agent scripts, and Playwright `tests/browser.cjs`. Live tests require credentials supplied through environment, never embedded in source.
