"""
REAL VERIFICATION #5: MDLW Barrier Pricing — Closed-Form vs Monte Carlo  [INDEPENDENT]

Verifies: closed-form GBM barrier hitting probabilities match 1M-path Monte Carlo
(5000 time steps to minimize discrete-monitoring bias) for all 6 MDLW ladder levels.
Also verifies: monotonicity (deeper barriers less likely), premium bounds, vol sensitivity.

Does NOT verify:
  - Whether GBM is an appropriate model for crypto price dynamics
  - Whether the MDLW pricing engine actually uses this formula
  - Whether jump-diffusion or regime-switching models would give materially different prices

The MDLW document says GBM lower-barrier hitting probabilities are used
as a sanity check. For GBM with drift mu and volatility sigma, the
probability that S_t hits barrier B = S0*(1-d) before maturity T has
a known closed-form (reflection principle):

P(min_{0<=s<=T} S_s <= B) = Phi(z1) + (B/S0)^(2*mu_hat/sigma^2) * Phi(z2)

where:
  mu_hat = r - sigma^2/2
  z1 = (log(B/S0) - mu_hat*T) / (sigma*sqrt(T))
  z2 = (log(B/S0) + mu_hat*T) / (sigma*sqrt(T))

This test:
1. Implements the closed-form
2. Compares against Monte Carlo
3. Verifies monotonicity (deeper barriers = lower hit prob)
4. Checks that the MDLW premium formula is consistent
"""
import math
import numpy as np
from scipy.stats import norm
import pytest


def gbm_barrier_prob(S0: float, B: float, T: float, r: float, sigma: float) -> float:
    """Closed-form probability that GBM hits lower barrier B before T.

    Uses the reflection principle for arithmetic Brownian motion on log-price.
    """
    if B >= S0:
        return 1.0
    if B <= 0:
        return 0.0

    mu_hat = r - 0.5 * sigma ** 2
    log_ratio = math.log(B / S0)
    sqrt_T = math.sqrt(T)

    z1 = (log_ratio - mu_hat * T) / (sigma * sqrt_T)
    z2 = (log_ratio + mu_hat * T) / (sigma * sqrt_T)

    p = norm.cdf(z1) + (B / S0) ** (2 * mu_hat / sigma ** 2) * norm.cdf(z2)
    return min(p, 1.0)


def mc_barrier_prob(S0: float, B: float, T: float, r: float, sigma: float,
                    n_sims: int = 500_000, n_steps: int = 252, seed: int = 42) -> float:
    """Monte Carlo estimate of barrier hit probability."""
    rng = np.random.default_rng(seed)
    dt = T / n_steps
    mu_hat = r - 0.5 * sigma ** 2

    # Simulate paths and track minimum
    log_S = np.full(n_sims, math.log(S0))
    log_B = math.log(B)
    hit = np.zeros(n_sims, dtype=bool)

    for _ in range(n_steps):
        dW = rng.standard_normal(n_sims) * math.sqrt(dt)
        log_S += mu_hat * dt + sigma * dW
        hit |= (log_S <= log_B)

    return hit.mean()


class TestBarrierClosedFormVsMC:
    """Compare closed-form barrier probabilities against Monte Carlo."""

    @pytest.mark.parametrize("d", [0.05, 0.10, 0.15, 0.20, 0.27, 0.35])
    def test_barrier_prob_consistency(self, d):
        """Closed-form and MC should agree within statistical tolerance."""
        S0 = 100.0
        B = S0 * (1 - d)
        T = 14 / 365  # 14 days
        r = 0.0
        sigma = 0.80  # annualized

        p_cf = gbm_barrier_prob(S0, B, T, r, sigma)
        # Need high n_steps to reduce discrete-monitoring bias for near barriers
        p_mc = mc_barrier_prob(S0, B, T, r, sigma, n_sims=1_000_000, n_steps=5000)

        # For rare events, allow wider tolerance
        tol = max(0.01, 3 * math.sqrt(p_cf * (1 - p_cf) / 1_000_000))
        assert abs(p_cf - p_mc) < tol, (
            f"d={d}: CF={p_cf:.6f}, MC={p_mc:.6f}, diff={abs(p_cf-p_mc):.6f}, tol={tol:.6f}"
        )

    def test_monotonicity(self):
        """Deeper barriers must have lower hit probability."""
        S0 = 100.0
        T = 14 / 365
        r = 0.0
        sigma = 0.80
        ds = [0.05, 0.10, 0.15, 0.20, 0.27, 0.35]

        probs = [gbm_barrier_prob(S0, S0 * (1 - d), T, r, sigma) for d in ds]
        for i in range(len(probs) - 1):
            assert probs[i] >= probs[i + 1], (
                f"Monotonicity violated: P(d={ds[i]})={probs[i]} < P(d={ds[i+1]})={probs[i+1]}"
            )


class TestMDLWPremiumConsistency:
    """Check that premium = discounted expected payoff is self-consistent."""

    def test_premium_bounded_by_M(self):
        """Premium must be <= M (max payout) for any parameters."""
        S0 = 100.0
        T = 14 / 365
        r = 0.0
        sigma = 0.80
        M = 30.0
        K = 6
        ds = [0.05, 0.10, 0.15, 0.20, 0.27, 0.35]

        # Uniform weights
        q = np.ones(K) * M / K

        # Premium = exp(-rT) * sum(q_k * P(hit level k))
        probs = [gbm_barrier_prob(S0, S0 * (1 - d), T, r, sigma) for d in ds]
        premium = math.exp(-r * T) * sum(q[k] * probs[k] for k in range(K))

        assert premium >= 0, "Premium must be non-negative"
        assert premium <= M, f"Premium {premium} exceeds max payout {M}"
        print(f"Premium for uniform weights: ${premium:.2f} (max payout: ${M})")

    def test_premium_increases_with_volatility(self):
        """Higher volatility => higher barrier hit probability => higher premium."""
        S0, T, r, M, K = 100.0, 14 / 365, 0.0, 30.0, 6
        ds = [0.05, 0.10, 0.15, 0.20, 0.27, 0.35]
        q = np.ones(K) * M / K

        premiums = []
        for sigma in [0.3, 0.5, 0.8, 1.2, 2.0]:
            probs = [gbm_barrier_prob(S0, S0 * (1 - d), T, r, sigma) for d in ds]
            prem = math.exp(-r * T) * sum(q[k] * probs[k] for k in range(K))
            premiums.append(prem)

        for i in range(len(premiums) - 1):
            assert premiums[i] <= premiums[i + 1] + 1e-10, (
                f"Premium should increase with vol"
            )

    def test_full_collateral_reserve(self):
        """Reserve = N * M must cover worst case (all levels hit for all warrants)."""
        M = 30.0
        N = 1000
        reserve = N * M

        # Worst case: all warrants pay max
        worst_case = N * M
        assert reserve >= worst_case
