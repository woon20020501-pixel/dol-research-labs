# Dol Research

Research artifacts from the Dol team — a consumer-first DeFi yield product built on Pacifica.

## What is Dol

Dol turns perpetual DEX infrastructure into a retail savings product. Users deposit USDC, receive a receipt token, and redeem through a fast, intuitive flow. No funding markets to understand, no venues to pick, no rebalancing to do.

The product is live at [dol-finance.vercel.app](https://dol-finance.vercel.app). The production codebase is at [github.com/woon20020501-pixel/dol](https://github.com/woon20020501-pixel/dol).

## What this repository contains

### CAD-F: Capital Adequacy Framework

A research design document specifying the mathematical framework for capital adequacy across a suite of DeFi yield and option products.

The framework addresses:

- **Market risk** — product-specific Expected Shortfall under posterior parameter uncertainty, with EVT tail splicing for extreme scenarios
- **Model uncertainty** — two layers: KL-divergence robust optimization for small perturbations, and Knightian epsilon-contamination for discrete model-class breaks
- **Operational risk** — actuarial loss distribution across five risk categories (oracle, smart contract, exchange, regulatory, key management)
- **Feedback dynamics** — a three-variable premium-capital SDE with provable local stability (Routh-Hurwitz) and sufficient conditions for Lyapunov decay
- **Governance** — Sybil-resistant concentration controls at the beneficial-owner cluster level, not the wallet level
- **Liquidity solvency** — Hedge Coverage Ratio and Redemption Coverage Ratio with circuit-breaker enforcement

**Status:** Research design document. The underlying yield product (Dol Phase 1) is live. The four option products described in CAD-F are under design and have not been deployed.

Read the full document: [`CAD-F-whitepaper.md`](./CAD-F-whitepaper.md)

### MDLW: Mirror-Descent Ladder Warrant

A retail-first structured derivative that pays incremental rewards when an underlying asset touches predefined downside price levels before maturity.

The key design innovation: a mirror-descent allocation engine distributes a fixed maximum payout budget across ladder levels based on market stress signals **at issuance time**, then **locks the payout structure after purchase**. This separation preserves consumer clarity (the user knows exactly what they bought) while allowing the protocol to adapt across issuance series.

The framework provides five mathematical guarantees provable without production data:

- **Bounded issuer payout** — total payout per warrant is capped at M by construction
- **Bounded buyer loss** — maximum loss equals premium paid, no margin calls
- **Simplex-preserving weights** — the mirror-descent update stays on the probability simplex
- **Monotonic reward unlocking** — hitting more levels never reduces payoff
- **Deterministic settlement** — settlement depends only on series parameters and barrier-hit set

Read the full document: [`MDLW-whitepaper.md`](./MDLW-whitepaper.md)

## Our vision

Dol is building toward a world where on-chain yield feels as simple as a savings account. Phase 1 delivers the retail UX and the market-neutral engine. The research in this repository maps the path from Phase 1 to a full risk operating system — one where the protocol answers every risk question mathematically, continuously, and verifiably, so the user never has to.

We believe the gap between TradFi-grade risk infrastructure and DeFi-grade user experience is the defining problem for the next generation of on-chain financial products. Dol is our attempt to close it.

## Team

Two people. One quantitative researcher, one engineer. Four languages (Rust, Python, Solidity, TypeScript). One thesis: make DeFi yield accessible to everyone.

## Contact

Find us on the [Pacifica Discord](https://discord.gg/pacifica) or reach out via the production repository.

## License

MIT
