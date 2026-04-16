# Dol Research

Research artifacts from the Dol team — a consumer-first DeFi yield product built on Pacifica.

## What is Dol

Dol turns perpetual DEX infrastructure into a retail savings product. Users deposit USDC, receive a receipt token, and redeem through a fast, intuitive flow. No funding markets to understand, no venues to pick, no rebalancing to do.

The product is live at [dol-finance.vercel.app](https://dol-finance.vercel.app). The production codebase is at [github.com/woon20020501-pixel/dol](https://github.com/woon20020501-pixel/dol).

---

## Research Documents

### CAD-F: Capital Adequacy Framework

A mathematical framework for capital adequacy across a suite of DeFi yield and option products. Covers market risk (posterior-robust ES, KL-DRO, Huber contamination), operational risk (Panjer-Poisson LDA), feedback dynamics (premium-capital SDE with provable stability), governance (Sybil-resistant cluster-level concentration), and liquidity solvency (HCR/RCR with circuit-breaker enforcement).

Read: [`CAD-F-whitepaper.md`](./CAD-F-whitepaper.md)

### Phase 2: Quantitative Risk Operating System

The specification for Dol's closed-loop risk operating system. Seven mathematical modules (M1-M7) and eight engineering modules (E1-E8), each with provable properties, falsifiable tests, and phased deployment plans. Includes formal theorems for one-step redemption solvency, water-filling budget feasibility, cluster Sybil invariance, and monotone tail risk reduction.

Read: [`phase2-risk-os.md`](./phase2-risk-os.md)

### MDLW: Mirror-Descent Ladder Warrant

A retail-first structured derivative where users buy warrants that pay incremental rewards as an underlying asset touches predefined downside price levels. A mirror-descent allocation engine distributes a fixed maximum payout budget across ladder levels based on market stress signals at issuance time, then locks the payout structure after purchase. Five provable mathematical guarantees (bounded payout, bounded loss, simplex preservation, monotonicity, deterministic settlement).

Read: [`MDLW-whitepaper.md`](./MDLW-whitepaper.md)

### PolyShard: Threshold Key Management Security

Information-theoretic security proof for the threshold secret sharing construction used in Dol's treasury key management. Proves that capturing fewer than t shards reveals exactly zero information about the master secret (Shamir impermeability), regardless of computational power including quantum. Includes hand-verifiable and production-scale test vectors.

Read: [`polyshard-security.md`](./polyshard-security.md)

---

## How the pieces connect

```
Dol Phase 1 (live)
  └── funding-rate harvester, retail UI, smart contracts
       │
       ├── CAD-F
       │     Capital adequacy for the full product suite.
       │     Market risk + operational risk + governance.
       │
       ├── Phase 2 Risk OS
       │     Closed-loop control: HCR/RCR → state machine → hedge adjustment.
       │     Proof-first modules ship before data-dependent ones.
       │
       ├── MDLW
       │     Structured derivative product line.
       │     Fully collateralized, launches outside pooled capital stack.
       │     Integrates into CAD-F after operational data accumulates.
       │
       └── PolyShard
              Treasury key management security layer.
              Information-theoretic guarantee (not computational).
```

---

## Our vision

Dol is building toward a world where on-chain yield feels as simple as a savings account. Phase 1 delivers the retail UX and the market-neutral engine. The research in this repository maps the path from Phase 1 to a full risk operating system — one where the protocol answers every risk question mathematically, continuously, and verifiably, so the user never has to.

We believe the gap between TradFi-grade risk infrastructure and DeFi-grade user experience is the defining problem for the next generation of on-chain financial products. Dol is our attempt to close it.

## Team

Two people. One quantitative researcher, one engineer. Four languages (Rust, Python, Solidity, TypeScript). One thesis: make DeFi yield accessible to everyone.

## Contact

Find us on the [Pacifica Discord](https://discord.gg/pacifica) or reach out via the production repository.

## License

MIT
