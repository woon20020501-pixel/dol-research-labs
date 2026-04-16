# Dol Research

![Verification](https://github.com/woon20020501-pixel/dol-research-labs/actions/workflows/verify.yml/badge.svg)

Research artifacts from the Dol team — a consumer-first DeFi yield product built on Pacifica.

## What is Dol

Dol turns perpetual DEX infrastructure into a retail savings product. Users deposit USDC, receive a receipt token, and redeem through a fast, intuitive flow. No funding markets to understand, no venues to pick, no rebalancing to do.

The product is live at [dol-finance.vercel.app](https://dol-finance.vercel.app). The production codebase is at [github.com/woon20020501-pixel/dol](https://github.com/woon20020501-pixel/dol).

---

## Research Documents

### CAD-F: Capital Adequacy Framework

A mathematical framework for capital adequacy across a suite of DeFi yield and option products. Covers market risk (posterior-robust ES, KL-DRO, Huber contamination), operational risk (Panjer-Poisson LDA), feedback dynamics (premium-capital SDE with derivable stability conditions), governance (Sybil-resistant cluster-level concentration), and liquidity solvency (HCR/RCR with circuit-breaker enforcement).

Read: [`CAD-F-whitepaper.md`](./CAD-F-whitepaper.md)

### Phase 2: Quantitative Risk Operating System

The specification for Dol's closed-loop risk operating system. Seven mathematical modules (M1-M7) and eight engineering modules (E1-E8), each with stated properties, falsifiable tests, and phased deployment plans. Includes formal definitions for one-step redemption solvency, water-filling budget feasibility, cluster Sybil invariance, and monotone tail risk reduction.

Read: [`phase2-risk-os.md`](./phase2-risk-os.md)

### MDLW: Mirror-Descent Ladder Warrant

A retail-first structured derivative where users buy warrants that pay incremental rewards as an underlying asset touches predefined downside price levels. A mirror-descent allocation engine distributes a fixed maximum payout budget across ladder levels based on market stress signals at issuance time, then locks the payout structure after purchase. Five mathematical properties verified via automated tests (bounded payout, bounded loss, simplex preservation, monotonicity, deterministic settlement).

Read: [`MDLW-whitepaper.md`](./MDLW-whitepaper.md)

### PolyShard: Threshold Key Management Security

Information-theoretic security analysis for the threshold secret sharing construction used in Dol's treasury key management. Based on Shamir's secret sharing scheme (Shamir, 1979): capturing fewer than t shards reveals zero information about the master secret, regardless of computational power. Includes hand-verifiable and production-scale test vectors (Vector B corrected via automated verification).

Read: [`polyshard-security.md`](./polyshard-security.md)

### PolyVault: Bio-Hybrid Multi-Layer Security

Formal security analysis of the PolyVault system — a six-layer defense-in-depth architecture combining dual post-quantum encryption (McEliece + Kyber), Shamir secret sharing, fuzzy biometric extraction, SPHINCS+ signatures, and Honey Encryption. Each layer's security property is stated as a theorem with proof sketch and automated verification. Statistical tests confirm the Honey Encryption DTE property and fuzzy extractor uniformity empirically.

Read: [`polyvault-security.md`](./polyvault-security.md)

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
       ├── PolyShard
       │     Treasury key management security layer.
       │     Information-theoretic guarantee (not computational).
       │
       └── PolyVault
              Multi-layer encryption + biometric + signing.
              Six defense layers, each with formal security theorem.
```

---

## Verification

Mathematical claims in these documents are tested by an automated verification suite. Run it with:

```
pip install pytest numpy scipy sympy
pytest verification/
```

Resolved findings are documented in [`FINDINGS.md`](./FINDINGS.md).

### Coverage Table

| Claim | Test file | Coverage | Notes |
|-------|-----------|----------|-------|
| PolyShard Vector A: shares + recovery | test_doc1_polyshard.py | **full** | independent polynomial eval, all C(5,3) combos |
| PolyShard Vector B: shares + recovery | test_doc1_polyshard.py | **full** | corrected document error in shares i=2..5 |
| Jacobian derivation from SDE | test_real_jacobian.py | **symbolic** | SymPy: drift -> J -> char poly, matches whitepaper |
| Characteristic polynomial a1, a2, a3 | test_real_jacobian.py | **symbolic** | SymPy det(sI-J) expansion |
| Lyapunov Q matrix | test_real_jacobian.py | **symbolic** | V_dot quadratic form reconstruction |
| Routh-Hurwitz a1\*a2 > a3 | test_real_jacobian.py | **conditional** | holds for all positive params (1000 random samples) |
| Semi-Markov P(72h) = 2.0e-6 | test_real_semimarkov.py | **independent** | convolution integral + 100M Monte Carlo |
| GBM barrier hit probabilities | test_real_mdlw_pricing.py | **independent** | closed-form vs 1M-path MC, all 6 MDLW levels |
| CAD-F capital table arithmetic | test_real_crossdoc.py | **cross-check** | component sums, CAR ratio, invariant checks |
| HCR/RCR monotonicity | test_doc2_dol_phase2.py | formula only | trivially true from ratio structure |
| Water-filling feasibility | test_doc2_dol_phase2.py | algorithm | tests our impl of the algorithm |
| Cluster Sybil invariance | test_doc2_dol_phase2.py | tautology | definitional from aggregation |
| ShieldRate bounds | test_doc2_dol_phase2.py | formula only | fraction in [0,1] by construction |
| MDLW simplex / bounded payout | test_doc4_mdlw.py | formula only | follows from exp-gradient normalization |
| Panjer severity distributions | test_real_panjer.py | partial | severity shape checked, compound ES underspecified |
| Shamir info-theoretic security | test_doc1_polyshard.py | theoretical | re-derives Shamir 1979 |
| Nested-IND-CCA2 (Th1) | test_polyvault_nested_enc.py | implementation | round-trip, tamper detection, layer independence |
| Fuzzy Extractor uniformity (Th3) | test_polyvault_fuzzy.py | **statistical** | chi-squared + bit balance on 10k extracted keys |
| SPHINCS+ EUF-CMA structure (Th4) | test_polyvault_sphincs.py | implementation | Lamport OTS: sign/verify, tamper, preimage |
| Honey Enc. DTE property (Th5) | test_polyvault_honey.py | **statistical** | chi-squared + KS test, 50k wrong-key decryptions |
| PolyVault composition (Th6) | test_polyvault_composition.py | structural | key independence, union bound, full pipeline |

**Coverage levels:** **full** = independent computation that could falsify the claim. **symbolic** = SymPy derivation confirming stated math. **independent** = different method cross-validates result. **cross-check** = compares numbers within/across documents. **conditional** = verifies "if X then Y" but not that actual params satisfy X. **algorithm** = tests our implementation, not the protocol's. **formula only** = trivially true from formula structure. **tautology** = true by definition. **theoretical** = known theorem. **partial** = some parameters underspecified.

### AI Disclosure

Verification scripts in `/verification` were authored with Claude Code assistance. All results are reproducible via `pytest verification/`. Human review has been applied to test design, coverage classification, and findings interpretation.

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
