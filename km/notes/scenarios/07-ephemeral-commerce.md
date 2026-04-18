# 07. Ephemeral commerce (market-per-trade)

**One-liner.** Each transaction spawns its own miniature marketplace of buyer, seller, escrow, and dispute agents that dissolves at settlement.

## What it is

You list a used item. The listing publishes to a commerce channel. Interested buyers' bidding agents subscribe; your seller agent and a winning bidding agent enter a transient negotiation channel. An escrow agent published by a neutral third party joins to hold funds. A shipping-coordinator agent joins to arrange logistics and track the parcel. If a dispute arises, a dispute-resolution agent joins, adjudicated by a third-party arbitration service the parties previously agreed to.

On settlement, the channel closes and all agents exit. No "marketplace platform" owns the transaction infrastructure; the infrastructure was summoned for this trade and dissolved after it. Fees and trust derive from which escrow, shipping, and dispute agents the parties chose. The market for trust providers becomes liquid and competitive.

## Why OAM enables it

- **Multi-party membership.** Buyer and seller have opposed interests and must belong to different principals; impossible in a single-orchestrator tree but natural in a mesh.
- **Typed contracts** define the protocol: `commerce.bid_v1`, `commerce.escrow_v1`, `commerce.dispute_v1`. The "marketplace" becomes a set of contracts, not a company.
- **Federation** lets neutral third parties (escrow providers, arbitrators, logistics) participate as peers rather than tenants of a platform.
- **Discovery catalog** lets each party choose which escrow or dispute agent to trust, which makes the trust layer a competitive market.
- **Channel lifecycle.** The channel for this trade exists only for this trade, with its own ACL, and disappears at settlement.

## Why existing solutions struggle

- Marketplaces today (eBay, Amazon, Uber) are rent-seeking platforms. The trust infrastructure is the moat, and they own it. OAM turns trust infrastructure into a commodity layer underneath the trade.
- Blockchain and smart-contract platforms provide multi-party execution but are single-ledger, expensive, and bound to their chain's trust assumptions. OAM is transport-agnostic and typed at the application-semantic level.
- Closed subagent orchestrators cannot host adversarial parties. Your buyer cannot also be a subagent of my seller's session without breaking the adversarial model.
- P2P commerce protocols (OpenBazaar historically) lacked a live agent model; they were static listings, not summoned participants with behavior and negotiation capacity.
