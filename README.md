# Table

The interface, recipe defaults and user manual are in French. Existing English sample recipes, saved recipe snapshots and grocery labels receive an idempotent text-only translation on upgrade; IDs, ingredient quantities, nutrition and approval state are preserved. Original history is retained. New assistant output is instructed to use French.

A self-hosted meal-planning app backed by Hermes. The app owns the cookbook, preferences, learned guidance, weekly plans, recipe snapshots, approvals and shopping-operation records. Hermes supplies the reasoning and tool execution through four disposable, app-managed profiles. There is no dependency on Hermes Studio, a preconfigured personal profile, or a hosted UI.

Table can prepare next week's draft on a local schedule. The planning profile proposes menus from the cookbook, and Table compares them against household preferences, freezer inventory and the actual cooking tasks. Table calculates consolidated groceries from scheduled batch quantities. The Chronodrive profile can look up products ahead of review. The retailer cart changes when the owner starts an approved fill. Weekly reminders appear in Table and can also be delivered as Web Push notifications on devices that opt in.

## Install against a fresh Hermes gateway

Tested with the Hermes runtime serving this deployment, image `nousresearch/hermes-agent:v0.22.5`. Hermes changes quickly; the profile helper and native Bot Chat API are the compatibility boundary. Table currently needs to run beside Hermes with access to its data volume, not merely a remote API URL: Hermes' execution API does not expose complete profile administration.

1. Install and start a fresh Hermes gateway using its Docker installation. Use the headless `gateway run` command, enable its API gateway (`API_SERVER_ENABLED=true`, `API_SERVER_HOST=0.0.0.0` on the private network) and set `API_SERVER_KEY`. A fresh supervised image can use `HERMES_GATEWAY_BOOTSTRAP_STATE=running`. Hermes must listen on port 8642 on a private Docker network, and serve named profiles. No existing profile configuration or model login is required.
2. Identify its container, network, and Hermes data volume. Data is mounted at `/opt/data`; Table uses its own pinned Hermes runtime from its image, so a separate source volume is not required. Set `HERMES_UID` and `HERMES_GID` to its actual UID/GID (10000 for a fresh image; this existing deployment uses 1000). The installer initializes Table’s own volume for that user; it never changes ownership of Hermes data.
3. Build Table: `docker build -t table:0.1.0 .`.
4. Copy `.env.example` to `.env`, fill the gateway key, Table password, actual Docker resource names, hostname and internal URLs. Both Table and Hermes must resolve `TABLE_INTERNAL_URL`. Default service DNS is `http://table:8080` on the shared network.
5. For Docker Compose, run `./install.sh`; it creates/initializes the app volume and starts the stack. For Coolify, create `table-data`, then deploy `compose.yaml` using Docker Compose or a Coolify Docker Compose service. In Coolify set the `table` service domain to your HTTPS hostname, port 8080. For a custom UID in Coolify, initialize the new Table volume with `docker run --rm --user 0 --entrypoint /opt/hermes/.venv/bin/python -v table-data:/table-data table:0.1.0 /app/volume_init.py 1000:1000`, replacing the UID/GID as appropriate. Plain Docker requires your HTTPS reverse proxy; the compose file intentionally publishes no host ports. For isolated local development only, publish 8080 and set `COOKIE_SECURE=false`.
6. Open the app, sign in with `TABLE_PASSWORD`, then **Connections**. Pick OpenAI/Codex and **Sign in with OpenAI**, or select OpenAI API and enter a model/key. Custom OpenAI-compatible endpoints are supported through the base URL. Click **Install / update profiles**.
7. Confirm you can ask the cookbook assistant to add a recipe. Table creates `table-cookbook`, `table-planner`, `table-shopper` and `table-cart` from scratch with `create_profile(no_alias=True, no_skills=True)`. One Table installation per Hermes gateway is currently supported; its fixed profile IDs are reserved. The installer refuses to overwrite unmanaged profiles or profiles owned by another Table installation. It copies no personal config, memories, channels, recipes, OAuth tokens or existing skills. Codex sign-in uses Hermes' native root authentication mechanism; fresh installations sign in once. Native provider refresh remains Hermes' responsibility.
8. Connect Chronodrive in **Connections**, and select the store from the live directory. Current official store URLs use `drive-magasin-<id>-<name>`; the old `/store/XXXX` instructions were incorrect. **Test connection** reads the existing cart without changing it.

`tests/fresh_install.py` provisions all four profiles into an empty Hermes home, then updates them, without prior authentication. This tests profile installation, not an unauthenticated model inference. Real inference necessarily needs a provider connection configured in step 6.

Run `tests/fresh_gateway.sh table:0.1.0` to test a running fresh gateway and the local scheduler in isolated Docker volumes. It checks that the scheduled draft is available without model credentials and that a Table restart keeps the same draft and run.

The bridge shares the Hermes container network namespace and forwards only native authenticated session WebSockets on private port 8644. It enables Stop, tool approval and clarification UI. If the Hermes container is replaced, recreate the bridge. If another app uses 8644, select another bridge port and set `HERMES_OWNER_URL` on Table to match.

## Architecture

Browser → Table FastAPI → app SQLite and Markdown documents.
Table → Hermes named-profile Bot Chat sessions and Runs API.
Hermes terminal → generated profile skill + `table_cli.py` → role-scoped Table worker API.
Table → isolated Chronodrive client → Chronodrive frontend API.

Table persists application data in `table-data` and generates the Hermes profiles from that configuration. SQLite holds the versioned recipes. Table exports them as individual Markdown files with JSON frontmatter under `cookbook/` and regenerates them at startup. Approved weeks contain recipe snapshots. When an owner edits a prepared menu or its groceries, Table resets the relevant approvals and carries forward product matches for identical ingredients and quantities. New preferences apply to the next run.

Worker credentials authorize different operations per role. No worker endpoint can approve a meal plan, groceries or product selection. The UI alone invokes those owner endpoints. The cart stage requires approval of exact products and pack quantities and an explicit **Fill approved cart** action. The app reserves each operation before dispatch; a timeout remains unknown and prevents more additions until reconciled. There is no checkout, payment, empty-cart or order-placement tool. Existing cart contents are preserved; quantities already present count toward the approved total, and larger existing quantities are never reduced. A skilled agent still has Hermes terminal access: these profiles run within the same trusted Hermes instance, not a security sandbox between mutually hostile tenants.

Self-improvement uses immutable base skill templates in `skills/` plus app-owned versioned learning. Assistants read context, incorporate explicit feedback via `learn`, and Table reprojects their skill. Owners can edit guidance and restore prior revisions in the UI. App upgrades preserve learning. The Chronodrive integration is a regular skill with a CLI, not an MCP server.

## Update, backup, removal

Back up **the whole `table-data` volume**, including `key`, encrypted connection files, SQLite database and cookbook directory; the key is needed to decrypt provider and Chronodrive credentials. Back up Hermes data separately for native chat history and provider authentication. Stop Table briefly for a simple consistent volume backup, or use SQLite's backup API. Do not back up only the `.db` file during writes.

Build the new image and redeploy the service. On startup Table reinstalls its four profiles from its source and persistent app configuration; learned guidance remains. Existing sessions are preserved. Do not update during an active cart fill. A crash during an external cart mutation requires inspecting the real cart; Table never automatically retries uncertain operations.

Removing Table leaves your Hermes instance and other profiles alone. To remove its generated profiles, stop Table first and use Hermes' profile deletion commands for these four IDs only. Never remove the shared Hermes volumes. Keep the Table data volume if you want your cookbook/plans back.

## Chronodrive provenance and limitations

`chronodrive_client.py` is adapted from [y-vex/chronodrive-mcp](https://github.com/y-vex/chronodrive-mcp); its MCP server is not included or used. Source commit is recorded in `CHRONODRIVE_SOURCE`. The client uses the same frontend HTTP APIs as that project, with bounded timeouts and isolated credentials. It requires the owner's account/store. Website changes, authentication challenges or API changes can break it. Search and cart addition cannot be claimed verified until tested with a connected account.

## Checks

`python -m unittest discover -s tests` runs domain tests. Additional Docker-based checks use the mounted Hermes source runtime: `tests/fresh_install.py`, `tests/test_api.py`, real agent scripts, and Playwright `tests/browser.cjs`. Live tests require credentials supplied through environment, never embedded in source.

## Durable cart filling

Hermes proposes products and learns shopping preferences. After exact product approval, Table executes the frozen selection through a persistent app-owned job, independently of chat completion. Progress is stored per SKU, with live cart checks before and after each write. Existing quantities count toward the approved total and larger existing quantities are preserved. Restart recovery checks any in-flight write against the real cart and never blindly repeats an uncertain addition. Stock rejections are reported per item while other approved products continue. The UI exposes progress, pause, resume and review; no checkout is performed. One application process executes the queue.
