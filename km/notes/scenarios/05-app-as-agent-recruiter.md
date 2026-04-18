# 05. App-as-agent-recruiter

**One-liner.** A thin SaaS product shell summons capability agents into each user's session at runtime; the featureset is assembled per user, not bundled.

## What it is

A personal-finance app ships with a minimal shell: auth, UI, data store, audit log. When a user mentions "rental income," a tax-for-rental-income agent built by a specialist third-party vendor joins the session via the mesh, reads the user's authorized data, and contributes advice. When the user imports a foreign brokerage CSV, a schema-inferencer agent from yet another vendor joins. At month-end, a budget-rollup agent joins briefly and exits.

None of these agents are "integrations" in the 2020s sense. They are independent citizens of a marketplace, discovered by contract match, compensated per invocation, as replaceable as npm packages. The app's value is less its feature set and more its curation of which agents it composes, its data-handling policies, and the trust surface it presents to the user.

## Why OAM enables it

- **Typed contracts** let third-party agents plug in without the app author's coordination. If an agent speaks `tax.rental_income_v1`, it can be summoned for that need.
- **Catalog discovery** lets the app rank candidate agents by reputation, price, latency, and specialization, not just those pre-integrated.
- **Federation** lets third-party agents run in their vendors' environments, preserving their IP while serving the app's users.
- **Queue groups** let popular agents scale horizontally without the app knowing about it.
- **Pub/sub** lets the app publish session events; multiple agents subscribe with their own logic and can collaborate without direct coupling.

## Why existing solutions struggle

- Plugin systems (Slack apps, Zapier, Chrome extensions) require pre-registration, a gallery, manual auth flow per integration. OAM's runtime discovery plus typed contracts collapses this to install-free composition.
- MCP gives LLMs tool access, but MCP servers are typically hosted by the app itself or by a single vendor. They are not independently discoverable citizens of a shared network.
- Closed subagent orchestrators can compose capabilities within a single vendor's system (Claude Code does this well), but cannot recruit third-party vendors' agents mid-session without becoming a centralized gateway, which defeats the decoupling that makes the model interesting.
- The App Store / plugin-marketplace model is pre-integrated and curated. The agent-mesh model is runtime-discovered and priced per call, which is a structurally different economic shape.
