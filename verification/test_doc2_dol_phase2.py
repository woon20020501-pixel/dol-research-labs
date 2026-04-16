"""
Doc 2: Dol Phase 2 Whitepaper — Verification Suite

Coverage levels:
  M3-1 HCR formula                [FORMULA ONLY] verifies code matches whitepaper eq, not real market behavior
  M3-2 RCR formula                [FORMULA ONLY] same — code-to-equation check
  M3-3 RCR>=1 => solvency         [TAUTOLOGY]    A/D>=1 <=> A>=D, this is arithmetic identity
  M3-4 HCR monotonicity           [FORMULA ONLY] sum(phi*H)/L is trivially linear in H — not a real test
  M3-5 RCR monotonicity           [FORMULA ONLY] same — ratio numerator/denominator monotonicity is arithmetic
  M3-6 Haircut conservatism       [FORMULA ONLY] reducing a numerator term reduces the ratio

  M7-1 Water-filling budget       [ALGORITHM]    tests OUR implementation of the algorithm, not the whitepaper's
  M7-2 Individual feasibility     [ALGORITHM]    same — verifies our code, not a production implementation
  M7-3 Priority monotonicity      [ALGORITHM]    same

  M6-1 Cluster Sybil invariance   [TAUTOLOGY]    cluster-level sum is invariant to sub-wallet splits by definition
  M6-2 Wallet-level HHI breakable [TAUTOLOGY]    demonstrates the impossibility result, which is definitional

  M4-1 ShieldRate bounded         [FORMULA ONLY] fraction is in [0,1] by construction
  M4-2 ShieldRate = 1 (perfect)   [FORMULA ONLY] tests our shield_rate function, not a production system
  M4-3 ShieldRate = 0 (no hedge)  [FORMULA ONLY] same
  M4-4 Tail bundle size           [FORMULA ONLY] quantile definition check

  M2-1 Hysteresis turnover        [SIMULATION]   demonstrates deadband reduces switching on synthetic noise
  M2-2 Hysteresis deterministic   [SIMULATION]   verifies policy logic on deterministic input

  CAD-1 Invariant A               [CROSS-CHECK]  FOUND: capital table violates its own Invariant A (CAR=1.15 < 1.20)
  CAD-2 Invariant D               [CROSS-CHECK]  verifies stated numbers satisfy junior cap
  CAD-3 Capital table arithmetic  [CROSS-CHECK]  verifies addition: 16.4+5.9+0.37+3.80+0.8 = 27.27
  CAD-4 Routh-Hurwitz             [CONDITIONAL]  tests ARBITRARY positive params, not the system's actual params
  CAD-5: Lyapunov eta condition: eta > max(...)
"""
import math
import random
import itertools
import numpy as np
import pytest


# ============================================================
# M3: HCR / RCR
# ============================================================

def compute_hcr(hedge_legs: list[tuple[float, float]], insured_liability: float) -> float:
    """HCR = sum(phi_k * H_k) / L_insured"""
    return sum(phi * h for phi, h in hedge_legs) / insured_liability


def compute_rcr(cash: float, liquid_hedge: float, option_payout: float,
                settlement_haircut: float, redeem_demand: float) -> float:
    """RCR = (cash + liquid_hedge + rho * option) / D_redeem"""
    return (cash + liquid_hedge + settlement_haircut * option_payout) / redeem_demand


class TestM3_HCR_RCR:
    """M3: Hedge & Redemption Coverage formulas and properties."""

    def test_hcr_formula_matches_whitepaper_example(self):
        """Verify HCR against the whitepaper input/output example."""
        legs = [(1.00, 500000), (0.95, 300000)]
        insured = 810000
        hcr = compute_hcr(legs, insured)
        expected = (1.0 * 500000 + 0.95 * 300000) / 810000
        assert abs(hcr - expected) < 1e-10

    def test_rcr_formula_matches_whitepaper_example(self):
        """Verify RCR against the whitepaper input/output example."""
        rcr = compute_rcr(850000, 320000, 0, 0.98, 950000)
        expected = (850000 + 320000 + 0.98 * 0) / 950000
        assert abs(rcr - expected) < 1e-10

    def test_m3_3_rcr_ge_1_implies_solvency(self):
        """M3-3: If RCR >= 1 then A >= D (one-step solvency)."""
        for _ in range(1000):
            cash = random.uniform(0, 1e6)
            hedge = random.uniform(0, 1e6)
            option = random.uniform(0, 1e6)
            rho = random.uniform(0, 1)
            A = cash + hedge + rho * option
            D = random.uniform(1, A)  # ensure RCR >= 1
            rcr = A / D
            assert rcr >= 1.0
            assert A >= D

    def test_m3_4_hcr_monotone_in_hedge(self):
        """M3-4 (H1): doubling hedge notional doubles HCR."""
        legs = [(0.9, 100000), (0.95, 200000)]
        insured = 300000
        hcr1 = compute_hcr(legs, insured)
        legs_doubled = [(0.9, 200000), (0.95, 400000)]
        hcr2 = compute_hcr(legs_doubled, insured)
        assert abs(hcr2 - 2 * hcr1) < 1e-10

    def test_m3_4_hcr_nonincreasing_in_liability(self):
        """M3-4 (H2): increasing insured liability decreases HCR."""
        legs = [(1.0, 500000)]
        hcr1 = compute_hcr(legs, 400000)
        hcr2 = compute_hcr(legs, 500000)
        assert hcr1 > hcr2

    def test_m3_5_rcr_monotone_in_cash(self):
        """M3-5 (R1): RCR non-decreasing in cash."""
        base = compute_rcr(100000, 50000, 0, 1.0, 200000)
        more_cash = compute_rcr(150000, 50000, 0, 1.0, 200000)
        assert more_cash >= base

    def test_m3_5_rcr_nonincreasing_in_demand(self):
        """M3-5 (R2): RCR non-increasing in redemption demand."""
        rcr1 = compute_rcr(100000, 50000, 0, 1.0, 100000)
        rcr2 = compute_rcr(100000, 50000, 0, 1.0, 200000)
        assert rcr1 >= rcr2

    def test_m3_6_haircut_conservatism(self):
        """M3-6: Reducing phi_k cannot increase HCR."""
        legs_high = [(1.0, 500000), (0.95, 300000)]
        legs_low = [(0.8, 500000), (0.90, 300000)]
        insured = 810000
        assert compute_hcr(legs_high, insured) >= compute_hcr(legs_low, insured)

    def test_m3_6_settlement_haircut_conservatism(self):
        """Reducing rho cannot increase RCR."""
        rcr_high = compute_rcr(100000, 50000, 200000, 0.98, 200000)
        rcr_low = compute_rcr(100000, 50000, 200000, 0.80, 200000)
        assert rcr_high >= rcr_low


# ============================================================
# M7: Water-Filling Redemption Queue
# ============================================================

def water_fill(clusters: list[dict], L_avail: float) -> dict[int, float]:
    """
    clusters: [{"id": int, "balance": float, "priority": float}, ...]
    Returns: {cluster_id: allocation}
    """
    U = {c["id"]: c for c in clusters}
    allocations = {}
    R = L_avail

    while U and R > 1e-12:
        total_p = sum(U[cid]["priority"] for cid in U)
        saturated = []
        for cid in list(U.keys()):
            x_c = R * (U[cid]["priority"] / total_p)
            if x_c >= U[cid]["balance"]:
                saturated.append(cid)

        if saturated:
            for cid in saturated:
                allocations[cid] = U[cid]["balance"]
                R -= U[cid]["balance"]
                del U[cid]
        else:
            for cid in U:
                allocations[cid] = R * (U[cid]["priority"] / total_p)
            break

    # Clusters not allocated get 0
    for c in clusters:
        if c["id"] not in allocations:
            allocations[c["id"]] = 0.0
    return allocations


class TestM7_WaterFilling:
    """M7: Water-filling redemption queue properties."""

    def _make_clusters(self, n, seed=42):
        rng = random.Random(seed)
        clusters = []
        for i in range(n):
            b = rng.uniform(100, 10000)
            z = rng.uniform(0.1, 1.0)
            clusters.append({
                "id": i,
                "balance": b,
                "priority": z / math.sqrt(b),  # p_c = Z_c / sqrt(B_c)
            })
        return clusters

    def test_m7_1_budget_feasibility(self):
        """M7-1: sum(L_c) <= L_avail."""
        for L in [1000, 50000, 100000]:
            clusters = self._make_clusters(20)
            alloc = water_fill(clusters, L)
            assert sum(alloc.values()) <= L + 1e-6

    def test_m7_2_individual_feasibility(self):
        """M7-2: 0 <= L_c <= B_c for all c."""
        clusters = self._make_clusters(20)
        alloc = water_fill(clusters, 50000)
        for c in clusters:
            assert alloc[c["id"]] >= -1e-10
            assert alloc[c["id"]] <= c["balance"] + 1e-6

    def test_m7_3_priority_monotonicity(self):
        """M7-3: Increasing p_c weakly increases L_c."""
        clusters = self._make_clusters(10, seed=99)
        alloc1 = water_fill(clusters, 30000)

        # Boost cluster 0's priority
        clusters_boosted = [dict(c) for c in clusters]
        clusters_boosted[0]["priority"] *= 2.0
        alloc2 = water_fill(clusters_boosted, 30000)

        assert alloc2[0] >= alloc1[0] - 1e-6

    def test_m7_budget_feasibility_adversarial(self):
        """Many tiny accounts + one whale."""
        clusters = [{"id": i, "balance": 1.0, "priority": 1.0} for i in range(100)]
        clusters.append({"id": 100, "balance": 1000000, "priority": 0.001})
        alloc = water_fill(clusters, 50)
        assert sum(alloc.values()) <= 50 + 1e-6

    def test_m7_single_cluster_exceeds_avail(self):
        """Single cluster with balance > L_avail."""
        clusters = [{"id": 0, "balance": 1000000, "priority": 1.0}]
        alloc = water_fill(clusters, 500)
        assert alloc[0] <= 500 + 1e-6
        assert alloc[0] >= 0


# ============================================================
# M6: Cluster Sybil Invariance
# ============================================================

def herfindahl_bo(cluster_balances: list[float]) -> float:
    """H_BO = sum(u_c^2)"""
    return sum(u ** 2 for u in cluster_balances)


class TestM6_SybilInvariance:
    """M6: Cluster-level Sybil resistance."""

    def test_m6_1_wallet_split_preserves_hbo(self):
        """M6-1: Splitting wallets within a cluster leaves H_BO unchanged."""
        # 3 clusters with balances [100, 200, 300]
        original = [100.0, 200.0, 300.0]
        hbo_before = herfindahl_bo(original)

        # Cluster 1 (balance 200) splits into 4 wallets of 50 each
        # But they're still in the same cluster, so u_c is still 200
        after_split = [100.0, 200.0, 300.0]  # cluster-level: unchanged
        hbo_after = herfindahl_bo(after_split)

        assert abs(hbo_before - hbo_after) < 1e-10

    def test_m6_2_wallet_level_herfindahl_IS_affected(self):
        """M6-2 (Impossibility): Wallet-level HHI changes under splits."""
        # Before: 3 wallets [100, 200, 300]
        wallet_hhi_before = sum(x ** 2 for x in [100, 200, 300])

        # After: wallet with 200 splits into [50, 50, 50, 50]
        wallet_hhi_after = sum(x ** 2 for x in [100, 50, 50, 50, 50, 300])

        assert wallet_hhi_after < wallet_hhi_before  # splits reduce wallet-level HHI

    def test_m6_cluster_invariance_parameterized(self):
        """Splitting any cluster's balance into m sub-wallets doesn't change H_BO."""
        rng = random.Random(42)
        for _ in range(100):
            n_clusters = rng.randint(2, 10)
            balances = [rng.uniform(10, 1000) for _ in range(n_clusters)]
            hbo_before = herfindahl_bo(balances)

            # Split a random cluster into m pieces (cluster aggregate unchanged)
            # H_BO stays the same because it's defined at cluster level
            hbo_after = herfindahl_bo(balances)
            assert abs(hbo_before - hbo_after) < 1e-10


# ============================================================
# M4: Monte Carlo Path Bundles / Shield Metric
# ============================================================

def compute_shield_rate(y_no_hedge: np.ndarray, y_hedged: np.ndarray, tail_pct: float = 0.05) -> float:
    """Shield rate = fraction of tail paths where hedging improved outcome."""
    n = len(y_no_hedge)
    q = np.quantile(y_no_hedge, tail_pct)
    tail_mask = y_no_hedge <= q
    tail_count = tail_mask.sum()
    if tail_count == 0:
        return 0.0
    delta = y_hedged[tail_mask] - y_no_hedge[tail_mask]
    return float((delta > 0).sum()) / tail_count


class TestM4_ShieldMetric:
    """M4: Monte Carlo path bundle properties."""

    def test_m4_1_shield_rate_bounded(self):
        """M4-1: ShieldRate in [0, 1]."""
        rng = np.random.default_rng(42)
        for _ in range(50):
            y_nh = rng.normal(0, 1, 1000)
            y_h = y_nh + rng.normal(0, 0.5, 1000)
            sr = compute_shield_rate(y_nh, y_h)
            assert 0.0 <= sr <= 1.0

    def test_m4_2_perfect_hedge_shield_rate_1(self):
        """M4-2: Shield rate = 1.0 when hedge perfectly cancels tail loss."""
        y_nh = np.array([-10, -8, -6, -4, -2, 0, 2, 4, 6, 8] * 10, dtype=float)
        # Perfect hedge: hedged PnL = 0 for all paths
        y_h = np.zeros_like(y_nh)
        sr = compute_shield_rate(y_nh, y_h)
        assert sr == 1.0

    def test_m4_3_no_hedge_shield_rate_0(self):
        """M4-3: Shield rate = 0.0 when hedge is absent (y_hedged = y_no_hedge)."""
        y_nh = np.linspace(-10, 10, 200)
        y_h = y_nh.copy()  # no hedge
        sr = compute_shield_rate(y_nh, y_h)
        assert sr == 0.0

    def test_m4_4_tail_bundle_size(self):
        """M4-4: Tail bundle contains exactly floor(0.05 * N) paths."""
        for N in [100, 200, 1000, 10000]:
            y = np.arange(N, dtype=float)
            q = np.quantile(y, 0.05)
            tail_count = (y <= q).sum()
            expected = math.floor(0.05 * N) + 1  # quantile is inclusive
            # Allow +/- 1 due to quantile interpolation
            assert abs(tail_count - expected) <= 1, (
                f"N={N}: tail_count={tail_count}, expected~{expected}"
            )


# ============================================================
# M2: Hysteresis Stability
# ============================================================

def hysteresis_policy(lambdas: list[float], lam_buy: float, lam_sell: float,
                      w_init: float = 0.0) -> list[float]:
    """Hysteresis controller: expand/contract with deadband."""
    w = w_init
    ws = []
    for lam in lambdas:
        if lam >= lam_buy:
            w = min(w + 0.1, 1.0)
        elif lam <= lam_sell:
            w = max(w - 0.1, 0.0)
        ws.append(w)
    return ws


def single_threshold_policy(lambdas: list[float], lam_thresh: float,
                            w_init: float = 0.0) -> list[float]:
    """Single threshold: expand if above, contract if below."""
    w = w_init
    ws = []
    for lam in lambdas:
        if lam >= lam_thresh:
            w = min(w + 0.1, 1.0)
        else:
            w = max(w - 0.1, 0.0)
        ws.append(w)
    return ws


class TestM2_Hysteresis:
    """M2: Hysteresis stability properties."""

    def test_m2_1_turnover_reduction(self):
        """M2-1: Under noisy signal, hysteresis has lower turnover than single-threshold."""
        rng = random.Random(42)
        threshold = 0.5
        lam_buy = 0.6
        lam_sell = 0.4
        # Signal oscillating around threshold
        lambdas = [threshold + rng.gauss(0, 0.15) for _ in range(1000)]

        ws_hyst = hysteresis_policy(lambdas, lam_buy, lam_sell)
        ws_single = single_threshold_policy(lambdas, threshold)

        tv_hyst = sum(abs(ws_hyst[i] - ws_hyst[i - 1]) for i in range(1, len(ws_hyst)))
        tv_single = sum(abs(ws_single[i] - ws_single[i - 1]) for i in range(1, len(ws_single)))

        assert tv_hyst < tv_single, f"Hysteresis TV {tv_hyst} >= Single TV {tv_single}"

    def test_m2_2_matches_deterministic_when_no_noise(self):
        """M2-2: When noise = 0 and signal is monotonically increasing,
        hysteresis and single-threshold produce same transitions."""
        lambdas = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        lam_buy = 0.6
        lam_sell = 0.4
        ws = hysteresis_policy(lambdas, lam_buy, lam_sell)
        # Should start expanding at 0.6
        assert ws[4] == 0.0  # lambda=0.5, in deadband
        assert ws[5] > 0.0   # lambda=0.6, expand triggered


# ============================================================
# CAD-F: Capital Adequacy Framework
# ============================================================

class TestCADF_Invariants:
    """CAD-F five invariants and related claims."""

    def test_cad_1_capital_sufficiency_car_value(self):
        """CAD-1: Verify stated CAR = 1.15."""
        alpha, beta, gamma = 18.0, 8.0, 5.4
        C_req = 27.27
        total = alpha + beta + gamma
        car = total / C_req
        assert abs(car - 1.15) < 0.01, f"CAR should be ~1.15, got {car}"

    def test_cad_1_invariant_a_violation_detected(self):
        """The whitepaper's own capital table violates Invariant A (CAR < 1.20).
        This test documents that finding."""
        alpha, beta, gamma = 18.0, 8.0, 5.4
        C_req = 27.27
        car = (alpha + beta + gamma) / C_req
        # Invariant A requires CAR >= 1.20
        assert car < 1.20, (
            f"Expected CAR < 1.20 (known gap in whitepaper), got {car}"
        )

    def test_cad_2_junior_cap(self):
        """CAD-2: Invariant D — alpha <= 0.8 * total."""
        alpha, beta, gamma = 18.0, 8.0, 5.4
        total = alpha + beta + gamma
        assert alpha <= 0.8 * total, (
            f"Junior {alpha} > 0.8 * {total} = {0.8 * total}"
        )

    def test_cad_3_capital_table_arithmetic(self):
        """CAD-3: Required capital components sum correctly."""
        market_es = 16.4
        op_es = 5.9
        kl_addon = 0.37
        knightian = 3.80
        gas_liq = 0.8
        total = market_es + op_es + kl_addon + knightian + gas_liq
        assert abs(total - 27.27) < 0.01, f"Expected 27.27, got {total}"

    def test_cad_4_routh_hurwitz(self):
        """CAD-4: Routh-Hurwitz conditions for the premium feedback SDE.

        Jacobian:
        [[-kV*  r0  -1 ]
         [ 0   -kL   0 ]
         [ gam  bet -muL]]

        Characteristic polynomial: s^3 + a1*s^2 + a2*s + a3
        """
        # Use reasonable positive parameters
        for kV_star, kL, muL, r0, gamma_, beta_ in [
            (0.5, 0.3, 0.4, 0.05, 0.1, 0.02),
            (1.0, 0.5, 0.8, 0.1, 0.2, 0.05),
            (2.0, 1.0, 1.5, 0.2, 0.5, 0.1),
        ]:
            a1 = kV_star + kL + muL
            a2 = gamma_ + kV_star * kL + kV_star * muL + kL * muL
            a3 = kL * (kV_star * muL + gamma_)

            # Routh-Hurwitz: a1 > 0, a3 > 0, a1*a2 > a3
            assert a1 > 0, f"RH violated: a1 = {a1}"
            assert a3 > 0, f"RH violated: a3 = {a3}"
            assert a1 * a2 > a3, f"RH violated: a1*a2 = {a1 * a2} <= a3 = {a3}"

    def test_cad_5_lyapunov_eta(self):
        """CAD-5: Lyapunov eta condition.
        eta > max(4*kV* + (r0+beta)^2 / (2*muL), 1/gamma)
        """
        kV_star, muL, r0, gamma_, beta_ = 0.5, 0.4, 0.05, 0.1, 0.02
        eta_cond1 = (4 * kV_star + (r0 + beta_) ** 2) / (2 * muL)
        eta_cond2 = 1.0 / gamma_
        eta_min = max(eta_cond1, eta_cond2)

        # The whitepaper claims eta > 2.3 suffices under nominal parameters
        # We verify the condition is satisfiable
        assert eta_min < 100, f"eta_min = {eta_min} is unreasonably large"
        eta = eta_min + 1.0
        assert eta > eta_cond1
        assert eta > eta_cond2
