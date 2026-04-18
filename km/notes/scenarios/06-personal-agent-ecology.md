# 06. Personal agent ecology

**One-liner.** A user's life events populate and depopulate their personal mesh with agents owned by different third parties.

## What it is

You buy a house. Your mortgage lender's agent joins your mesh and subscribes to your expense channel to verify covenant compliance. Your utility's agent joins to forward usage data. A home-maintenance agent from a startup you chose joins to schedule inspections and track warranty windows. Five years later you sell the house; these agents receive a "closed" event and exit.

You have a child: pediatric-provider, school-enrollment, benefits-recalculator agents join. You relocate internationally: tax-cross-border, visa-compliance, and destination-utility agents appear; home-country agents gracefully transfer or depart. Your "agent household" is a live, shifting population reflecting your actual life. No single vendor owns this population. Each agent is published by the real responsible party (your bank's agent is your bank's, not a chatbot's reimplementation of banking).

## Why OAM enables it

- **Federation** means agents are published by their real owners and authenticated as such. Your bank's agent carries your bank's identity, not a wrapper's.
- **Pub/sub events** let agents react to life events ("home-purchased," "child-born," "relocated"); relevant agents subscribe to what concerns them.
- **Typed contracts** make agents replaceable. Switch banks and a new bank agent with the same contract takes its place, without rewiring.
- **Liveness and death notices** give you honest visibility when a provider's agent goes offline, instead of silent failure during critical moments.
- **Catalog discovery** lets you find agents by capability ("any agent serving `tax.cross_border_v1` in this jurisdiction?") rather than by vendor brand.

## Why existing solutions struggle

- Current personal assistants (Siri, Google Assistant, ChatGPT with memory) are monolithic. One vendor owns the stack and can only imitate other parties' services through scraping or bilateral partnerships, which cannot represent your bank any better than your bank itself can.
- OAuth-based integrations require bilateral agreements between the assistant vendor and each provider. Meshes with typed contracts eliminate the bilateral bottleneck.
- Closed agent orchestrators spawn subagents for the session; they die when the session ends. Your life events need persistent, addressable agents that outlive any conversation and survive device changes.
- Super-agent visions (personal AGI) try to subsume all domains into one brain. Mesh visions distribute the cognition to the actual parties who have authority, data, and legal accountability for each domain.
