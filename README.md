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

### PolyVault: DeFi Treasury Custody Stack (v3.2)

Six-layer defense-in-depth custody stack re-architected for DeFi treasury use: Argon2id-stretched custodian authentication, AEAD shard lock, honey-encryption passphrase decoy (wraps the passphrase, not the key — uniform keys get no benefit from HE), Shamir threshold over secp256k1 `F_n`, dual-AEAD cold backup across three facilities (→ McEliece ∘ ML-KEM in production), and SPHINCS+ audit signatures. Four decisions pinned to implementation level: cold-backup storage topology, DKG procedure (air-gapped dealer → HSM → Pedersen DKG, tiered by AUM), Argon2id parameters + `shard_blob` wire format v1 (98 bytes fixed), and PassphraseDTE wire-level spec (22-byte `he_blob`, HMAC-SHA256 PRF, 1024-word common corpus + 4096-word algorithmic tail).

Companion documents:

- [`polyvault-security.md`](./polyvault-security.md) — architectural spec
- [`polyvault-dte-spec.md`](./polyvault-dte-spec.md) — DTE wire-level implementation spec
- [`polyvault-ceremony-runbook.md`](./polyvault-ceremony-runbook.md) — Phase 1 air-gapped DKG runbook
- [`polyvault-rust-port-plan.md`](./polyvault-rust-port-plan.md) — implementation sequencing for the Dol Rust runtime
- [`verification/polyvault_defi_sim.py`](./verification/polyvault_defi_sim.py) — 11-test reference oracle (S1 threshold round-trip, S4 DRBG independence, S7 HE over uniform keys is useless, S9 Argon2id slowdown, S10 on-device duress canary, S11 wire-format conformance)

The previous bio-hybrid / individual-user version is preserved in [`archive/polyvault-security-v1.md`](./archive/polyvault-security-v1.md) with its original verification scripts under [`verification/legacy/`](./verification/legacy/). The v1 tests remain valid for their original scope (individual-user custody); they are not part of the v3.2 production path.

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
       └── PolyVault v3.2
              DeFi treasury custody stack: custodian auth (Argon2id + token),
              AEAD shard, HE passphrase decoy, Shamir over secp256k1 F_n,
              3-facility cold backup, SPHINCS+ audit. Four implementation pins.
```

---

## Verification

Mathematical claims in these documents are tested by an automated verification suite. Run it with:

```
pip install pytest numpy scipy sympy pycryptodome argon2-cffi
pytest verification/
```

The PolyVault v3.2 DeFi reference oracle (`verification/polyvault_defi_sim.py`) runs 11 simulations covering every architectural decision; reproduce with:

```
python3 verification/polyvault_defi_sim.py
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
| PolyVault v3.2 threshold round-trip (S1) | polyvault_defi_sim.py | **full** | all C(5,3)=10 combinations sign + audit-verify |
| Sub-threshold zero-info over F_n (S2) | polyvault_defi_sim.py | theoretical | Shamir 1979 on secp256k1 scalar field |
| Stolen-shard lock + HE decoy (S3) | polyvault_defi_sim.py | **empirical** | 200/200 wrong-token AEAD failures; HE decoy rate ≈0.89 |
| DRBG independence across layers (S4) | polyvault_defi_sim.py | **statistical** | pairwise \|r\| < 0.05 on 5000 samples |
| PSS: preserve k*, rotate shards (S5) | polyvault_defi_sim.py | **full** | new polynomial, k* unchanged |
| Full rotation orphans old material (S6) | polyvault_defi_sim.py | **full** | no cross-recovery |
| HE over uniform keys is useless (S7) | polyvault_defi_sim.py | **empirical** | uniform-key wrong-decrypt p≈1; justifies passphrase-only HE |
| End-to-end latency (S8) | polyvault_defi_sim.py | **benchmark** | provision ~40ms, sign ~25ms (single-core crypto only) |
| Slow-KDF brute-force barrier (S9) | polyvault_defi_sim.py | **benchmark** | 3,000× slowdown at sim params; prod ≥20,000× |
| On-device duress canary poisons recon (S10) | polyvault_defi_sim.py | **full** | 1/2/3 duress passphrases all yield k_recovered ≠ k* |
| Wire format v1 conformance (S11) | polyvault_defi_sim.py | **full** | shard_blob 98B + he_blob 22B byte-exact |
| [legacy v1] Nested-IND-CCA2 | legacy/test_polyvault_nested_enc.py | implementation | preserved for historical reference |
| [legacy v1] Fuzzy Extractor uniformity | legacy/test_polyvault_fuzzy.py | statistical | preserved; not part of v3.2 path |
| [legacy v1] SPHINCS+ structure | legacy/test_polyvault_sphincs.py | implementation | preserved |
| [legacy v1] Honey Encryption (plaintext-wrap) | legacy/test_polyvault_honey.py | statistical | preserved; S7 shows this was misapplied |
| [legacy v1] Composition | legacy/test_polyvault_composition.py | structural | preserved |

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
