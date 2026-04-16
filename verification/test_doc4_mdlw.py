"""
Doc 4: Mirror-Descent Ladder Warrant (MDLW 1.0) — Verification Suite

Coverage levels:
  MD-1  Simplex preservation      [FORMULA ONLY]  exp(x)/sum(exp(x)) is on simplex by construction
  MD-2  Bounded payout [0,M]      [FORMULA ONLY]  sum(M*p_k * indicator) <= M since sum(p_k)=1 and indicators in {0,1}
  MD-4  Monotone reward unlock    [FORMULA ONLY]  q_k >= 0 => adding levels can't reduce sum — arithmetic
  MD-5  Relative weight shift     [FORMULA ONLY]  verifies the exp-gradient ratio identity — textbook property
  MD-6  Reserve invariant         [FORMULA ONLY]  N*M >= N*M, tautology
  MD-7  Deterministic settlement  [FORMULA ONLY]  same inputs => same outputs, tests our code determinism
  MD-8  Payout sum = M            [FORMULA ONLY]  sum(M*p_k) = M*sum(p_k) = M*1, arithmetic
  MD-10 No negative payout        [FORMULA ONLY]  q_k >= 0 since p_k >= 0 and M > 0

  GBM barrier pricing             [REAL CHECK]    see test_real_mdlw_pricing.py for closed-form vs MC comparison

Does NOT verify:
  - Whether mirror-descent calibration coefficients are appropriate
  - Whether real market regimes produce sensible issuance vectors
  - Whether the pricing engine produces fair premiums vs market
  - Whether reserve utilization is capital-efficient in practice
"""
import math
import random
import numpy as np
import pytest


# ============================================================
# Mirror-Descent Allocation Engine
# ============================================================

def mirror_descent_update(p: np.ndarray, u: np.ndarray, eta: float) -> np.ndarray:
    """Exponentiated gradient / mirror-descent update on the simplex.
    p_k^(n+1) = p_k^(n) * exp(eta * u_k) / Z
    """
    log_p = np.log(p) + eta * u
    log_p -= log_p.max()  # numerical stability
    p_new = np.exp(log_p)
    p_new /= p_new.sum()
    return p_new


def compute_payoff(q: np.ndarray, hit_set: set) -> float:
    """Payoff = sum of q_k for all k in hit_set."""
    return sum(q[k] for k in hit_set)


def compute_level_scores(state: dict, K: int, psi: np.ndarray,
                         a_lam=0.3, a_sig=0.25, a_d=0.2, a_b=0.15, a_k=0.1) -> np.ndarray:
    """Compute issuance score u_k for each level."""
    u = np.zeros(K)
    for k in range(K):
        u[k] = (a_lam * state["lambda_n"] +
                 a_sig * state["sigma_n"] +
                 a_d * (1 - state["depth_n"]) +
                 a_b * state["B_n"] +
                 a_k * psi[k])
    return u


# ============================================================
# MD-1: Simplex Preservation
# ============================================================

class TestMD1_SimplexPreservation:
    """Mirror-descent update preserves the probability simplex."""

    @pytest.mark.parametrize("K", [5, 6, 10, 20])
    def test_simplex_after_single_update(self, K):
        rng = np.random.default_rng(42)
        p = np.ones(K) / K  # uniform initial
        u = rng.standard_normal(K)
        eta = 0.5

        p_new = mirror_descent_update(p, u, eta)
        assert all(p_new >= 0), f"Negative weights: {p_new}"
        assert abs(p_new.sum() - 1.0) < 1e-12, f"Sum = {p_new.sum()}"

    def test_simplex_after_many_iterations(self):
        """Simplex preserved after 100 consecutive updates."""
        K = 6
        rng = np.random.default_rng(123)
        p = np.ones(K) / K

        for _ in range(100):
            u = rng.standard_normal(K)
            eta = rng.uniform(0.01, 2.0)
            p = mirror_descent_update(p, u, eta)
            assert all(p >= 0), f"Negative weights after iteration"
            assert abs(p.sum() - 1.0) < 1e-10

    def test_simplex_with_extreme_scores(self):
        """Even with very large score differences, simplex is preserved."""
        K = 5
        p = np.ones(K) / K
        u = np.array([100, -100, 50, -50, 0], dtype=float)
        eta = 1.0

        p_new = mirror_descent_update(p, u, eta)
        assert all(p_new >= 0)
        assert abs(p_new.sum() - 1.0) < 1e-10


# ============================================================
# MD-2: Bounded Maximum Payout
# ============================================================

class TestMD2_BoundedPayout:
    """0 <= Pi_T <= M for all possible paths."""

    def test_max_payout_equals_M(self):
        M = 30.0
        K = 6
        p = np.ones(K) / K
        q = M * p  # payouts per level

        # All levels hit => maximum payout
        all_hit = set(range(K))
        payoff = compute_payoff(q, all_hit)
        assert abs(payoff - M) < 1e-10

    def test_no_hit_payout_is_zero(self):
        M = 30.0
        K = 6
        p = np.ones(K) / K
        q = M * p

        payoff = compute_payoff(q, set())
        assert payoff == 0.0

    @pytest.mark.parametrize("seed", range(50))
    def test_random_path_bounded(self, seed):
        """Random hit patterns always yield payout in [0, M]."""
        rng = random.Random(seed)
        M = 25.0
        K = 6
        p = np.array([rng.random() for _ in range(K)])
        p /= p.sum()
        q = M * p

        # Random subset of levels hit
        hit_set = {k for k in range(K) if rng.random() > 0.5}
        payoff = compute_payoff(q, hit_set)
        assert 0 <= payoff <= M + 1e-10


# ============================================================
# MD-4: Monotonicity of Reward Unlocking
# ============================================================

class TestMD4_Monotonicity:
    """Hitting additional levels cannot reduce payoff."""

    def test_subset_monotonicity(self):
        M = 30.0
        K = 6
        rng = np.random.default_rng(42)
        p = rng.dirichlet(np.ones(K))
        q = M * p

        # For all subsets A ⊆ B, payoff(A) <= payoff(B)
        for _ in range(200):
            # Random A
            A = {k for k in range(K) if random.random() > 0.6}
            # B = A + some extra levels
            extra = {k for k in range(K) if k not in A and random.random() > 0.5}
            B = A | extra

            payoff_A = compute_payoff(q, A)
            payoff_B = compute_payoff(q, B)
            assert payoff_A <= payoff_B + 1e-10, (
                f"Monotonicity violated: payoff({A})={payoff_A} > payoff({B})={payoff_B}"
            )

    def test_incremental_level_adds_positive(self):
        """Each additional level adds non-negative reward."""
        M = 20.0
        K = 5
        rng = np.random.default_rng(99)
        p = rng.dirichlet(np.ones(K))
        q = M * p

        for k in range(K):
            assert q[k] >= 0, f"Negative reward at level {k}: {q[k]}"


# ============================================================
# MD-5: Relative Weight Shift Property
# ============================================================

class TestMD5_RelativeWeightShift:
    """p_k^(n+1)/p_l^(n+1) = (p_k^(n)/p_l^(n)) * exp(eta*(u_k - u_l))"""

    def test_relative_shift_exact(self):
        K = 6
        p = np.array([0.1, 0.2, 0.15, 0.25, 0.1, 0.2])
        u = np.array([0.5, -0.3, 0.8, 0.1, -0.5, 0.2])
        eta = 0.7

        p_new = mirror_descent_update(p, u, eta)

        # Check all pairs
        for k in range(K):
            for l in range(K):
                if k == l:
                    continue
                ratio_before = p[k] / p[l]
                ratio_after = p_new[k] / p_new[l]
                expected_ratio = ratio_before * math.exp(eta * (u[k] - u[l]))
                assert abs(ratio_after - expected_ratio) < 1e-10, (
                    f"Pair ({k},{l}): got {ratio_after}, expected {expected_ratio}"
                )

    def test_higher_score_gets_more_weight(self):
        """If u_k > u_l, then p_k/p_l increases after update."""
        K = 5
        p = np.ones(K) / K
        u = np.array([0.0, 0.0, 1.0, 0.0, 0.0])  # level 2 has highest score
        eta = 0.5

        p_new = mirror_descent_update(p, u, eta)
        # Level 2 should have highest weight
        assert p_new[2] == max(p_new), f"Level 2 not highest: {p_new}"


# ============================================================
# MD-6: Reserve Invariant
# ============================================================

class TestMD6_ReserveInvariant:
    """ReserveBalance >= N * M at all times."""

    def test_reserve_covers_all_warrants(self):
        M = 30.0
        for N in [1, 10, 100, 1000]:
            reserve = N * M  # minimum required
            assert reserve >= N * M

    def test_insufficient_reserve_detected(self):
        M = 30.0
        N = 100
        reserve = 2999.0  # < 100 * 30
        assert reserve < N * M, "Should detect insufficient reserve"


# ============================================================
# MD-7: Deterministic Settlement
# ============================================================

class TestMD7_DeterministicSettlement:
    """Same inputs must produce identical outputs."""

    def test_deterministic_payoff(self):
        M = 25.0
        K = 6
        p = np.array([0.15, 0.20, 0.10, 0.25, 0.18, 0.12])
        q = M * p
        hit_set = {0, 2, 4}

        results = [compute_payoff(q, hit_set) for _ in range(100)]
        assert all(r == results[0] for r in results)

    def test_deterministic_mirror_descent(self):
        """Same state => same weight vector."""
        K = 5
        p = np.ones(K) / K
        u = np.array([0.3, -0.1, 0.5, 0.2, -0.4])
        eta = 0.5

        results = [mirror_descent_update(p, u, eta) for _ in range(100)]
        for r in results:
            np.testing.assert_array_almost_equal(r, results[0])


# ============================================================
# MD-8: Payout Sum Equals M
# ============================================================

class TestMD8_PayoutSum:
    """sum(q_k) = M always."""

    @pytest.mark.parametrize("seed", range(20))
    def test_payout_sum(self, seed):
        rng = np.random.default_rng(seed)
        M = rng.uniform(10, 100)
        K = rng.integers(3, 10)
        p = rng.dirichlet(np.ones(K))
        q = M * p
        assert abs(q.sum() - M) < 1e-10

    def test_payout_sum_after_mirror_descent(self):
        """After mirror-descent update, q still sums to M."""
        K = 6
        M = 30.0
        p = np.ones(K) / K
        u = np.array([0.5, -0.3, 0.8, 0.1, -0.5, 0.2])
        eta = 0.5

        p_new = mirror_descent_update(p, u, eta)
        q_new = M * p_new
        assert abs(q_new.sum() - M) < 1e-10


# ============================================================
# MD-10: No Negative Payout
# ============================================================

class TestMD10_NoNegativePayout:
    """No path yields negative payout."""

    def test_all_payoffs_nonneg(self):
        M = 30.0
        K = 6
        rng = np.random.default_rng(42)

        for _ in range(100):
            p = rng.dirichlet(np.ones(K))
            q = M * p
            # Try all 2^K possible hit patterns
            for bits in range(1 << K):
                hit_set = {k for k in range(K) if bits & (1 << k)}
                payoff = compute_payoff(q, hit_set)
                assert payoff >= -1e-15, f"Negative payoff: {payoff}"


# ============================================================
# Integration: GBM first-passage sanity check
# ============================================================

class TestMDLW_GBM_Pricing:
    """Sanity check: GBM first-passage probabilities are reasonable."""

    def test_deeper_levels_less_likely(self):
        """Deeper barrier levels have lower hit probability under GBM."""
        S0 = 100.0
        sigma = 0.8  # annualized vol
        T = 14 / 365  # 14 days
        r = 0.0
        n_sims = 100000
        rng = np.random.default_rng(42)

        d_levels = [0.05, 0.10, 0.15, 0.20, 0.27, 0.35]
        barriers = [S0 * (1 - d) for d in d_levels]

        # Simulate daily GBM paths
        n_steps = 14
        dt = T / n_steps
        hit_counts = [0] * len(d_levels)

        for _ in range(n_sims):
            S = S0
            for step in range(n_steps):
                S *= math.exp((r - 0.5 * sigma ** 2) * dt + sigma * math.sqrt(dt) * rng.standard_normal())
                for k, b in enumerate(barriers):
                    if S <= b:
                        hit_counts[k] += 1
                        break  # only count first hit per sim for this level
                # Actually we need to check all levels
            # Reset and do properly

        # Simpler: just check that hit probability is monotone decreasing
        # by re-simulating properly
        hit_probs = [0.0] * len(d_levels)
        for _ in range(n_sims):
            S = S0
            min_S = S0
            for step in range(n_steps):
                S *= math.exp((r - 0.5 * sigma ** 2) * dt + sigma * math.sqrt(dt) * rng.standard_normal())
                min_S = min(min_S, S)
            for k, b in enumerate(barriers):
                if min_S <= b:
                    hit_probs[k] += 1

        hit_probs = [h / n_sims for h in hit_probs]

        # Deeper levels should have lower (or equal) hit probability
        for i in range(len(hit_probs) - 1):
            assert hit_probs[i] >= hit_probs[i + 1] - 0.01, (
                f"Level {i} prob {hit_probs[i]} < Level {i+1} prob {hit_probs[i+1]}"
            )
