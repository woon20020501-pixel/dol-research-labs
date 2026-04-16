# Mirror-Descent Ladder Warrant 1.0

**Research Design Document — Working Draft v1.0**

> *This is a research design document describing a structured derivative product under development. The product has not been deployed. All parameters are illustrative. Legal classification is subject to jurisdictional review.*

---

## 1. Executive Summary

Mirror-Descent Ladder Warrant 1.0 ("MDLW 1.0") is a retail-first structured derivative designed to make downside path trading intuitive, bounded, and engaging.

The product lets users buy a warrant that pays incremental rewards if the underlying asset touches predefined downside price levels before maturity. The key innovation is that the reward budget is not fixed uniformly across ladder levels. Instead, the protocol uses a mirror-descent allocation engine at issuance time to distribute a fixed maximum payout budget across levels based on observable market stress signals.

This creates a product that is:

- **Simple for users:** "If price reaches more levels, I unlock more rewards."
- **Safe for issuers:** maximum payout per warrant is fully capped and fully collateralized.
- **Innovative in design:** online-learning methods shape payout geometry across issuance series.
- **Operationally robust:** payout structure is fixed after purchase, avoiding live in-series manipulation.

MDLW 1.0 is intentionally designed as **adaptive at issuance, fixed after purchase.** This preserves mathematical tractability, auditability, deterministic settlement, and strong consumer clarity.

---

## 2. Product Vision

### 2.1 Product Thesis

Retail users understand levels, progress bars, locked rewards, and maximum downside far more easily than they understand implied volatility, barrier Greeks, or dynamic hedging.

MDLW 1.0 translates sophisticated quantitative machinery into a user experience that feels like:

- "Current level: 2 / 6"
- "Next level: -3.2%"
- "Locked reward: 9 USDC"
- "Maximum possible reward: 30 USDC"
- "Maximum loss: premium paid"

The complexity remains inside the protocol. The experience remains legible.

### 2.2 Why This Product Exists

Most crypto derivatives are either too complex for retail users, too linear to be exciting, too open-ended in risk, or too hard to explain honestly. MDLW 1.0 addresses that gap by offering bounded risk, bounded issuer liability, path-dependent excitement, clean mobile UI, and auditable issuance logic.

---

## 3. Product Specification

### 3.1 Series Definition

A series S_n is defined by:

```
S_n = (S_0, T, K, d_1...d_K, M, q_1...q_K)
```

- S_0: initial reference price at issuance
- T: maturity timestamp
- K: number of ladder levels
- d_k: fractional downside threshold for level k
- M: maximum total payout budget per warrant
- q_k: incremental payout assigned to level k

### 3.2 Barrier Levels

For each level k:

```
B_k = S_0 * (1 - d_k),    0 < d_1 < d_2 < ... < d_K < 1
```

### 3.3 Level Hit Times

For each level k, define the first-touch time:

```
tau_k = inf{ t in [0, T] : S_t <= B_k }
```

The event {tau_k <= T} means the underlying touched level k before maturity.

### 3.4 Payoff

The final payoff is:

```
Pi_T = sum_{k=1}^{K} q_k * 1{tau_k <= T}
```

Payout accumulates by level reached.

---

## 4. Mirror-Descent Allocation Engine

### 4.1 Purpose

Mirror Descent is used **at issuance time** to determine how the fixed maximum payout budget M is split across ladder levels. It is **not** used to change payout after the user has purchased the warrant. This separation is intentional and fundamental.

### 4.2 Weight Vector

Let the reward weight vector at issuance n be:

```
p^(n) = (p_1^(n), ..., p_K^(n))

p_k^(n) >= 0,    sum_{k=1}^{K} p_k^(n) = 1
```

Then the incremental payouts are:

```
q_k^(n) = M * p_k^(n)
```

### 4.3 Issuance State Vector

At issuance time t_n, define the normalized market state:

```
x_n = (lambda_tilde_n, sigma_tilde_n, depth_tilde_n, B_tilde_n)
```

- lambda_tilde: normalized liquidation stress intensity
- sigma_tilde: normalized volatility
- depth_tilde: normalized market depth score
- B_tilde: normalized basis stress

### 4.4 Level Score Function

Each ladder level k is assigned an issuance score:

```
u_{k,n} = a_lambda * lambda_tilde + a_sigma * sigma_tilde + a_d * (1 - depth_tilde) + a_b * B_tilde + a_k * psi_k
```

Where a_lambda, a_sigma, a_d, a_b, a_k are calibration coefficients and psi_k is the structural bonus assigned to deeper levels.

**Calibration note:** These coefficients are free parameters in V1.0, to be calibrated from observed issuance-to-settlement performance across market regimes. The score function is intentionally linear for auditability; nonlinear extensions are a Phase 2 research item.

### 4.5 Mirror-Descent Update

Given prior issuance weights p^(n), the next issuance weights are:

```
p_k^(n+1) = p_k^(n) * exp(eta * u_{k,n}) / sum_{j=1}^{K} p_j^(n) * exp(eta * u_{j,n})
```

Where eta > 0 is the learning rate. This is an exponentiated-gradient update over the probability simplex (Kivinen & Warmuth, 1997).

---

## 5. Mathematical Guarantees

This section contains only results that are provable now, without requiring production data.

### 5.1 Simplex Preservation

For every issuance n: p_k^(n) >= 0 and sum p_k = 1.

*Proof:* Exponentials are positive, and the denominator normalizes the sum to one.

### 5.2 Bounded Maximum Payout

Since q_k = M * p_k and sum p_k = 1, we have sum q_k = M. Therefore for every path:

```
0 <= Pi_T <= M
```

This is the most important issuer-side guarantee.

### 5.3 Bounded Buyer Loss

The buyer pays the premium upfront with no margin call obligation:

```
L_max_buyer = C_premium
```

### 5.4 Monotonicity of Reward Unlocking

All q_k >= 0, so hitting additional levels cannot reduce payoff. If A is a subset of B (hit-level sets):

```
sum_{k in A} q_k <= sum_{k in B} q_k
```

### 5.5 Relative Weight Shift Property

For two levels k, l:

```
p_k^(n+1) / p_l^(n+1) = (p_k^(n) / p_l^(n)) * exp(eta * (u_{k,n} - u_{l,n}))
```

Hence if u_{k,n} > u_{l,n}, level k receives more relative budget in the next issuance.

---

## 6. Pricing

### 6.1 Risk-Neutral Pricing

The premium is:

```
C_premium = e^{-rT} * E^Q[Pi_T] + fee
         = e^{-rT} * sum_{k=1}^{K} q_k * Q(tau_k <= T) + fee
```

Where Q(tau_k <= T) is the risk-neutral probability that level k is touched before maturity.

### 6.2 Pricing Considerations

Under GBM, first-passage probabilities have closed-form solutions via the reflection principle. Under richer dynamics (jump-diffusion, stochastic volatility), Monte Carlo or PDE methods are required. The pricing engine must produce per-series: premium, expected payout, probability of no-hit, probability of each level hit, probability of full ladder completion, and reserve utilization expectation.

---

## 7. Reserve and Capital Design

### 7.1 Fully Collateralized Issuance

For V1.0, each warrant is issued against a locked reserve equal to the maximum payout budget:

```
R_reserve = M
```

This means the issuer's maximum liability per warrant is fully reserved, and payout insolvency due to model error is structurally prevented.

### 7.2 Reserve Invariant

If N warrants of a given series are outstanding:

```
ReserveBalance >= N * M
```

at all times.

### 7.3 Relationship to CAD-F

MDLW 1.0 is designed to launch outside the pooled capital stack as a fully collateralized series product. After sufficient operational data accumulation, it may be migrated into the broader CAD-F framework (see companion document) as a pooled structured derivative line. This phased approach preserves simplicity at launch while enabling capital efficiency at scale.

---

## 8. Smart Contract Invariants

For every series and every state transition:

**Weight invariants:**
- p_k >= 0
- sum p_k = 1

**Payout invariants:**
- q_k = M * p_k
- sum q_k = M
- 0 <= Pi_T <= M

**Reserve invariant:**
- ReserveBalance >= N * M

**Issuance invariant:**
- No new series may be created without a valid oracle snapshot hash

**Settlement invariant:**
- Settlement is a deterministic function of series parameters, barrier-hit set, and maturity timestamp
- Settlement must not depend on discretionary off-chain input after issuance

---

## 9. What Is Proven vs What Must Be Empirically Validated

### 9.1 Proven now

- Bounded issuer payout (sum q_k = M)
- Bounded buyer loss (max loss = premium)
- Simplex-preserving weight update
- Deterministic settlement
- Reserve sufficiency if invariant is enforced
- Monotonic reward unlocking
- Relative weight shift property

### 9.2 Requires empirical validation

- Calibration of issuance score coefficients
- Realized hit frequencies across market regimes
- User retention and engagement effects
- Pricing fairness and spread competitiveness
- Reserve utilization efficiency

This separation is stated explicitly to distinguish mathematical guarantees from empirical claims.

---

## 10. Open Research Items

- Optimal calibration of issuance-time score function
- Issuance cadence vs regime responsiveness tradeoff
- First-passage pricing under multi-venue stress models
- Dynamic reserve efficiency beyond full collateralization
- Transition path from fixed series to pooled capital support (CAD-F integration)
- User behavior under ladder-gamified derivative UX
- Nonlinear score function extensions with auditability constraints
- Cross-product interaction when multiple MDLW series are live simultaneously

---

## 11. Positioning Statement

Mirror-Descent Ladder Warrant 1.0 is a fully collateralized structured warrant with issuance-time adaptive reward geometry and deterministic post-purchase settlement.

Its core strength is that it makes a mathematically disciplined path-dependent derivative feel intuitive, game-like, and bounded for retail users — without sacrificing reserve safety or auditability.

Legal classification of this product is subject to jurisdictional review. The team does not represent it as insurance, yield guarantee, or investment advice.

---

## References

- Kivinen, J., & Warmuth, M. K. (1997). Exponentiated gradient versus gradient descent for linear predictors. *Information and Computation*, 132(1), 1-63.
- Shalev-Shwartz, S. (2012). Online learning and online convex optimization. *Foundations and Trends in Machine Learning*, 4(2), 107-194.

---

*This document is a research design artifact of the Dol project. It does not constitute financial advice, an offer of securities, or a guarantee of any return.*
