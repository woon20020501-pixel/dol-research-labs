# Dol Phase 2: A Quantitative Risk Operating System for Retail DeFi Yield

**Research Design Document — Draft v0.1**

> *This is a research design document. Phase 1 (Dol funding harvester) is the only live component. Phase 2 modules described here are under development. All metrics and thresholds are subject to calibration.*

---

## Abstract

Dol is a delta-neutral cross-venue funding-rate harvester on Pacifica that pairs a three-tap retail experience with a TradFi-grade quantitative infrastructure. This document specifies Phase 2 of the protocol: a closed-loop **risk operating system** that extends Dol from a single yield engine into an integrated stack of predictive capital allocation, human-readable integrity proofs, actuarial user scoring, and structurally guaranteed redemption.

The system is defined through seven mathematical modules (M1-M7) and eight engineering modules (E1-E8), each with **provable properties, falsifiable tests, and phased deployment plans**. We distinguish strictly between what can be proved today and what requires empirical validation, and we adopt a proof-first ordering: modules that can be formally guaranteed ship before modules that depend on data accumulation.

The central thesis is simple. Retail users of a yield product cannot personally audit oracle redundancy, hedge adequacy, or liquidity solvency. The protocol must do that mathematically, continuously, and verifiably on their behalf. Phase 2 is the architecture that makes that possible.

---

## 1. System Overview

Dol Phase 2 maintains a state vector that summarizes every quantity the protocol needs to make a redemption decision, a hedging decision, or a risk disclosure:

```
x_t = (lambda_t, f_t, B_t, sigma_t, depth_t, CAR_t, RCR_t, HCR_t, D_t, Z_t)
```

| Component | Meaning |
|---|---|
| lambda_t | Hawkes-based liquidation cascade intensity |
| f_t | Perpetual funding rate stress |
| B_t | Cross-venue basis divergence |
| sigma_t | Realized/implied volatility state |
| depth_t | Orderbook liquidity depth score |
| CAR_t | Capital adequacy ratio |
| RCR_t | Redemption coverage ratio |
| HCR_t | Hedge coverage ratio |
| D_t | NAV divergence between runtime and oracle |
| Z_t | Cluster-level trust score |

The protocol exercises three control variables:

```
u_t = (w_t, a_t, q_t)
```

where w_t in [0,1] is the option/insurance coverage ratio, a_t is the auto-pilot action class (Green / Yellow / Red), and q_t is the cluster-level redemption allocation.

---

## 2. Design Principles

**P1. Proof-first ordering.** Modules that can be mathematically guaranteed from definitions alone ship before modules that require accumulated market data.

**P2. Separation of proof and display.** A metric either has a formal guarantee attached to it, or it is a visualization. We never blur the two.

**P3. Cluster-level enforcement.** Any control that a single actor could circumvent by splitting wallets is treated as advisory. Binding enforcement operates on beneficial-owner clusters.

**P4. Bounded authority.** Every score, every allocation, every control output lives inside a hard clip. No single calculated quantity can destabilize the system.

**P5. Phased deployment.** Modules that require model estimation are shipped in three phases: rule-based, local surrogate, learned. Phase 0 produces value immediately.

---

## 3. Module Taxonomy

### Mathematical modules (ship order)

| Module | Name | Status |
|---|---|---|
| M3 | Hedge & Redemption Coverage | Ship first |
| M7 | Water-filling Redemption Queue | Ship first |
| M6 | Cluster Sybil Invariance | Ship first |
| M4 | Monte Carlo Path Bundles | Ship first |
| M2 | Hysteresis Stability | Second wave |
| M1 | Dynamic Hedge Control | Phased |
| M5 | Actuarial SBT | Phased |

### Engineering modules

| Module | Name | Status |
|---|---|---|
| E5 | Proof Layer (HCR/RCR/Merkle) | Ship first |
| E1 | State Estimator | Second wave |
| E2 | Forecast Engine | Second wave |
| E7 | Redemption Layer | Second wave |
| E8 | UI Layer | Second wave |
| E6 | Identity Layer | Third wave |
| E4 | Guardrail Layer | Third wave |
| E3 | MPC Solver | Third wave |

---

## 4. M3: Hedge & Redemption Coverage

### 4.1 Hedge Coverage Ratio (HCR)

For hedge positions k = 1...m with notional H_{k,t} and per-venue haircut phi_k in [0,1]:

```
HCR_t = sum_{k=1}^{m} phi_k * H_{k,t} / L_t^insured
```

The haircut phi_k discounts each hedge leg by venue-specific risk (outage probability, settlement delay, counterparty exposure). L_t^insured is the protected liability.

### 4.2 Redemption Coverage Ratio (RCR)

```
RCR_t = (C_t^cash + V_t^liquid_hedge + rho_t^settle * P_t^option) / D_t^redeem
```

### 4.3 Theorem (One-Step Redemption Solvency)

**Claim.** If RCR_t >= 1, then all modeled redemption demand at time t is fully fundable.

**Proof.** Let A_t = C_t^cash + V_t^liquid_hedge + rho_t^settle * P_t^option and D_t = D_t^redeem. By definition RCR_t = A_t / D_t. The condition RCR_t >= 1 is equivalent to A_t >= D_t, which means total immediately available liquidity meets or exceeds modeled demand. Therefore funded redemption default at time t does not occur under the modeled demand path. QED

### 4.4 Monotonicity Properties

**(H1)** HCR_t is non-decreasing in each H_{k,t} (adding hedge increases coverage).

**(H2)** HCR_t is non-increasing in L_t^insured (issuing more liability decreases coverage).

**(R1)** RCR_t is non-decreasing in C_t^cash, V_t^liquid_hedge, P_t^option.

**(R2)** RCR_t is non-increasing in D_t^redeem.

**(R3)** Decreasing the settlement haircut rho_t^settle conservatively lowers RCR_t, ensuring stress scenarios produce stricter constraints.

### 4.5 Estimation of D_t^redeem

```
D_t^redeem = max(D^floor, Q_0.99({redemptions in last N intervals}))
```

where D^floor is a static worst-case floor. As operational history accumulates, the rolling empirical 99th percentile dominates.

---

## 5. M7: Water-Filling Redemption Queue

### 5.1 Priority Definition

For cluster c with balance B_c and trust score Z_c:

```
p_c = Z_c / B_c^nu,    nu in (0,1)
```

Default nu = 1/2, giving p_c = Z_c / sqrt(B_c).

### 5.2 Water-Filling Algorithm

Given available liquidity L_avail and unresolved cluster set U, repeat:

1. Compute provisional allocation: x_c = R * p_c / sum_{j in U} p_j
2. If x_c >= B_c for any c: finalize L_c = B_c, remove c from U, update R <- R - B_c
3. Otherwise: finalize all remaining L_c = x_c and terminate.

### 5.3 Theorems

**Theorem (Budget Feasibility).** sum_c L_c <= L_avail at termination.

**Proof.** At each step, either L_c = B_c is removed with R decreasing, or remaining clusters share R proportionally with sum x_c = R. Induction gives sum L_c <= L_avail. QED

**Theorem (Individual Feasibility).** 0 <= L_c <= B_c for all c.

**Proof.** Finalized L_c is either B_c (by construction) or x_c < B_c (from termination condition). QED

**Theorem (Priority Monotonicity).** Holding all other clusters fixed, increasing p_c weakly increases L_c.

**Proof.** Higher p_c increases x_c. If x_c was below B_c, it increases. If x_c crosses B_c, L_c jumps to B_c and cannot decrease further. QED

---

## 6. M6: Cluster Sybil Invariance

### 6.1 Impossibility Result

**Proposition.** No concentration metric computed over anonymous wallet balances alone can be Sybil-resistant.

**Proof sketch.** An actor controlling balance s splits across m wallets with balance s/m each. The Herfindahl index H = sum s_i^2 satisfies H_after = s^2/m < s^2 = H_before. Any enforcement based on wallet-level H can be evaded by wallet splitting alone. QED

### 6.2 Cluster-Level Herfindahl

We define beneficial-owner clusters c = 1...m and aggregate balances:

```
u_c = sum_{i in C_c} s_i

H_BO = sum_c u_c^2
```

### 6.3 Theorem (Cluster Invariance)

**Claim.** Wallet splitting within a linked cluster leaves u_c and therefore H_BO unchanged.

**Proof.** If actor splits balance s across m wallets all linked to cluster c, then u_c includes all contributions: u_c^after = u_c^before - s + m(s/m) = u_c^before. Since aggregation is additive, H_BO is unchanged. QED

### 6.4 Honest Limitation Statement

> *Perfect Sybil resistance in a permissionless setting is mathematically impossible without strong identity primitives. Dol's cluster-level enforcement relies on probabilistic linkage inference, which has nonzero false negative rate.*

---

## 7. M4: Monte Carlo Path Bundles

### 7.1 Shield Metric

For Monte Carlo sample paths, the tail bundle is the worst 5% of unhedged paths. The hedge's effectiveness on tail paths:

```
ShieldRate = (1/|B_5%|) * sum_{j in B_5%} 1{Delta_hedge^(j) > 0}
```

This is the fraction of tail paths on which hedging actually improved outcomes.

### 7.2 Properties

- ShieldRate in [0,1] by construction
- For deterministic hedge strategies, ShieldRate is non-decreasing in hedge strength
- Under fixed seed, ShieldRate is reproducible to machine precision

---

## 8. M2: Hysteresis Stability

For hedge expansion/contraction governed by lambda_t:

```
action(lambda_t, w_{t-1}) =
  expand    if lambda_t >= lambda_buy
  contract  if lambda_t <= lambda_sell
  hold      otherwise
```

with lambda_buy > lambda_sell.

**Proposition.** Under i.i.d. perturbations of lambda_t around the critical threshold, total variation sum |w_t - w_{t-1}| is strictly smaller under hysteresis than under a single-threshold policy.

---

## 9. M1: Dynamic Hedge Control (Phased)

The full hedge control problem is a constrained stochastic optimization over the coverage ratio w_t, subject to ES, CAR, and RCR constraints.

### Phase 0: Rule-Based Controller

```
w_t = clip(w_{t-1} + Delta(lambda_t, RCR_t, CAR_t), 0, 1)
```

Deploys immediately. No transition model required.

### Phase 1: Local Surrogate MPC

Local linear approximation to state transitions, updated by rolling regression. Deploys after 3-6 months of production data.

### Phase 2: Stochastic Control / RL

Full Bellman solution or model-free RL. Deployment horizon: 18+ months.

### Well-Posedness (All Phases)

**Theorem.** Under compact constraints and continuous objective, each per-step optimization admits a maximizer.

### Monotone Tail Risk Reduction

**Theorem.** If hedge benefit is monotone (L_t(w) = L_t^0 - g_t(w) with g_t' >= 0), then increasing hedge coverage provably reduces VaR and ES.

---

## 10. M5: Actuarial SBT (Phased)

### Phase 0: Prior-Based Proto-Score

```
Z_c^(0) = a_1 * account_age_c + a_2 * W_c - a_3 * churn_flag_c
```

Observable from day one. Conservative coefficients.

### Phase 1: Bayesian Survival

Gamma-process prior on baseline hazard with empirical Bayes updates.

### Phase 2: Full Cox Proportional Hazards

```
S_c(t | z_c) = exp(-H_0(t) * exp(theta^T z_c))
```

with hierarchical priors across user segments. Requires adequate event coverage.

### Bounded Application

Trust score maps to a premium discount and redemption priority multiplier, both hard-clipped to prevent any single score from dominating system liquidity.

---

## 11. Structural Liquidity Bridge (State Machine)

**Green:** lambda_t < lambda_Y and RCR_t >= 1.20.
*Action:* Minimal hedging. Maximum yield.

**Yellow:** lambda_Y <= lambda_t < lambda_R or 1.00 <= RCR_t < 1.20.
*Action:* Pre-emptive hedge expansion. Gradual w_t increase.

**Red:** lambda_t >= lambda_R or RCR_t < 1.00.
*Action:* Monetize option positions. Activate L-Queue. Pause new issuance.

The state machine is compatible with all proof-first module guarantees: budget feasibility (M7), cluster Sybil invariance (M6), and one-step redemption solvency (M3) hold in every state.

---

## 12. Provable Now vs Data-Dependent Later

### 12.1 Provable from definitions alone

- Auto-Pilot well-posedness (existence of maximizer under compact constraints)
- Hedge coverage monotonicity (HCR monotone in hedge notional)
- Tail risk monotonicity (ES/VaR decrease with increasing hedge coverage)
- Redemption solvency (RCR_t >= 1 implies one-step fundability)
- Cluster Sybil invariance (aggregation is additive under cluster identity)
- Water-filling feasibility (budget and individual constraints preserved)
- Bounded trust score application (clip enforces hard limits)
- Shield rate boundedness ([0,1] by construction)

### 12.2 Requires empirical validation

- Predictive accuracy of Hawkes lambda_t on live liquidation streams
- Survival model calibration (whether Z_c actually predicts ejection)
- Out-of-sample yield/risk improvement from w_t policy vs baseline
- Divergence alert false-positive/false-negative rates
- L-Queue impact on actual user satisfaction during stress

We treat these as two separate document classes. The formal properties are fixed through this specification. The empirical claims will be reported in future studies.

---

## 13. Module Dependency Graph

```
M3 (HCR/RCR) ---+
M4 (Bundles)  ---+--- E5 (Proof Layer) --- E8 (UI)
M6 (Cluster)  ---+         |
                           +--- E1 (State) --- E2 (Forecast) --- M2 (Hysteresis)
M7 (Water-fill) --- E7 (Redemption)            |
                                               +--- M1 (Hedge control, phased)
                                               +--- M5 (SBT, phased)
```

---

## 14. Conclusion

Phase 2 does not add features to Dol. It adds **structure** — a closed-loop risk operating system in which every operational control is bound to a mathematical guarantee, every metric is either proved or displayed (never both), and every user-facing promise corresponds to a testable invariant.

The retail user who opens Dol sees three taps and an APY. That simplicity is sustained by a quantitative infrastructure that most DeFi protocols do not have and most TradFi institutions do not publish. Phase 2 is the public specification of that infrastructure.

---

## References

- Artzner, Delbaen, Eber, Heath (1999). *Coherent measures of risk.*
- Glasserman, Xu (2014). *Robust risk measurement and model risk.*
- Huber (1964). *Robust estimation of a location parameter.*
- Kusuoka (2001). *On law invariant coherent risk measures.*
- Bacry, Muzy (2016). *First- and second-order statistics characterization of Hawkes processes.*
- Embrechts, Kluppelberg, Mikosch (1997). *Modelling extremal events.*

---

*This document is a research design artifact of the Dol project. Not investment advice. Not a security offering.*
