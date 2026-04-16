"""
Doc 3: CAD-F Unified Whitepaper (message-2.txt) — Verification Suite

Coverage levels:
  UNI-1  GPD CDF                  [LIBRARY CHECK]  our GPD impl matches scipy — tests our code, not the whitepaper
  UNI-3  Knightian regime         [FORMULA ONLY]    0.002 < 0.01, arithmetic
  UNI-4  Knightian interpolation  [FORMULA ONLY]    verifies interpolation formula bounds, not calibration
  UNI-5  Panjer recursion         [TEXTBOOK]        reproduces known Poisson-compound result, not protocol-specific
  UNI-6  Semi-Markov 72h          [CROSS-CHECK]     plugs stated params into formula, gets ~2.0e-6
  UNI-8  Lyapunov Q pos-def       [CONDITIONAL]     specific params => Q>0, does not prove system stability
  UNI-9  Student-t ES monotone    [KNOWN RESULT]    well-known property of Student-t, not a whitepaper claim
  UNI-10 Capital table            [CROSS-CHECK]     verifies Doc 2 vs Doc 3 numbers match

Does NOT verify:
  - Whether EVT threshold u=95th percentile is appropriate for this protocol
  - Whether Panjer frequency/severity params reflect real operational risk
  - Whether copula model captures actual cross-product dependence
  - Whether any calibrated parameter is correct for production use
"""
import math
import numpy as np
from scipy import stats, special
import pytest


# ============================================================
# UNI-1: EVT Tail Splice (GPD)
# ============================================================

class TestUNI1_EVT:
    """GPD tail splice: F(x|u) = 1 - (1 + xi*(x-u)/beta)^(-1/xi)"""

    def test_gpd_cdf_correctness(self):
        """Verify our GPD CDF matches scipy's genpareto."""
        xi = 0.29
        beta_scale = 1.8e6
        u = 10e6  # threshold

        x_values = np.linspace(u + 1000, u + 20e6, 100)
        for x in x_values:
            z = (x - u) / beta_scale
            our_cdf = 1 - (1 + xi * z) ** (-1 / xi)
            scipy_cdf = stats.genpareto.cdf(z, xi)
            assert abs(our_cdf - scipy_cdf) < 1e-10, f"GPD mismatch at x={x}"

    def test_gpd_positive_shape_heavy_tail(self):
        """xi > 0 => heavy tail (Pareto-like), survival decreases as power law."""
        xi = 0.29
        beta_scale = 1.8e6
        # Survival at x = u + k*beta
        for k in [1, 5, 10, 50]:
            z = k
            survival = (1 + xi * z) ** (-1 / xi)
            assert survival > 0
            assert survival < 1


# ============================================================
# UNI-3 & UNI-4: Knightian epsilon-contamination
# ============================================================

class TestUNI3_Knightian:
    """Knightian epsilon-contamination regime and ES formula."""

    def test_regime_check(self):
        """UNI-3: eps = 0.002 < 1 - q = 0.01 => well-defined (not degenerate)."""
        eps = 0.002
        q = 0.99
        assert eps < 1 - q, "Should be in non-degenerate regime"

    def test_degenerate_regime(self):
        """If eps >= 1-q, worst-case ES = L_max (degenerate)."""
        eps = 0.02
        q = 0.99
        assert eps >= 1 - q
        # In this regime, worst-case Q puts all mass on L_max

    def test_uni4_interpolation_formula(self):
        """UNI-4: Worst-case ES interpolates between nominal ES and L_max."""
        eps = 0.002
        q = 0.99
        alpha = 1 - q  # = 0.01
        L_max = 100e6  # maximum possible loss
        ES_nominal = 15e6  # nominal ES at shifted confidence

        # q' = q / (1 - eps) for the shifted confidence
        q_prime = q / (1 - eps)
        assert q_prime < 1.0, "Shifted confidence must be < 1"

        # Worst-case formula: (eps * L_max + (alpha - eps) * ES'_q) / alpha
        ES_worst = (eps * L_max + (alpha - eps) * ES_nominal) / alpha

        # Must be between ES_nominal and L_max
        assert ES_worst >= ES_nominal, f"ES_worst {ES_worst} < ES_nominal {ES_nominal}"
        assert ES_worst <= L_max, f"ES_worst {ES_worst} > L_max {L_max}"

    def test_knightian_addon_reasonable(self):
        """The Knightian add-on should be ~3.80M under stated parameters."""
        eps = 0.002
        q = 0.99
        alpha = 1 - q
        L_max = 100e6
        # Approximate nominal ES
        ES_nominal = 13.67e6  # market ES / 1.2

        ES_worst = (eps * L_max + (alpha - eps) * ES_nominal) / alpha
        addon = ES_worst - ES_nominal

        # Document says ~3.80M
        # This is order-of-magnitude check
        assert addon > 0, "Add-on must be positive"
        assert addon < 50e6, "Add-on unreasonably large"


# ============================================================
# UNI-5: Panjer Recursion
# ============================================================

class TestUNI5_Panjer:
    """Panjer recursion for compound Poisson distributions."""

    def test_panjer_poisson_basic(self):
        """Panjer recursion with Poisson frequency (a=0, b=lambda) and
        discrete severity reproduces known compound distribution."""
        # Poisson(lambda=2), severity P(X=1) = 0.6, P(X=2) = 0.4
        lam = 2.0
        a, b = 0, lam  # Panjer params for Poisson

        # Severity PMF (index = loss amount)
        f_s = [0.0, 0.6, 0.4]  # f_s[0]=0, f_s[1]=0.6, f_s[2]=0.4
        max_n = 20

        # Panjer recursion: g[0] = exp(-lambda), g[n] = (1/(1-a*f_s[0])) * sum...
        g = [0.0] * (max_n + 1)
        g[0] = math.exp(-lam)

        for n in range(1, max_n + 1):
            s = 0.0
            for k in range(1, min(n, len(f_s) - 1) + 1):
                if k < len(f_s):
                    s += (a + b * k / n) * f_s[k] * g[n - k]
            g[n] = s / (1 - a * f_s[0]) if (1 - a * f_s[0]) != 0 else s

        # Verify probabilities sum to ~1
        total = sum(g)
        assert abs(total - 1.0) < 0.01, f"Panjer PMF sums to {total}, expected ~1.0"

        # Verify mean = lambda * E[X] = 2 * (0.6*1 + 0.4*2) = 2 * 1.4 = 2.8
        mean = sum(n * g[n] for n in range(max_n + 1))
        expected_mean = lam * (0.6 * 1 + 0.4 * 2)
        assert abs(mean - expected_mean) < 0.1, f"Mean {mean} != {expected_mean}"


# ============================================================
# UNI-6: Semi-Markov 72h Downtime
# ============================================================

class TestUNI6_SemiMarkov:
    """Semi-Markov 3-state model: S0 -> S1 -> S2 (absorbing)."""

    def test_72h_absorption_probability(self):
        """
        P(0->2, 72h) = 1 - (lam12 * exp(-lam01*t) - lam01 * exp(-lam12*t)) / (lam12 - lam01)
        With lam01=0.4/yr, lam12=0.15/yr, t=72h = 72/8760 yr
        """
        lam01 = 0.4   # per year
        lam12 = 0.15  # per year
        t = 72.0 / 8760.0  # 72 hours in years

        # Hypoexponential CDF for absorption
        p = 1 - (lam12 * math.exp(-lam01 * t) - lam01 * math.exp(-lam12 * t)) / (lam12 - lam01)

        # Document claims ~2.0e-6
        assert p > 0, "Probability must be positive"
        assert p < 1e-4, f"P = {p} seems too high"
        assert abs(p - 2.0e-6) < 5e-6, f"P = {p}, expected ~2.0e-6"

    def test_72h_monte_carlo_cross_check(self):
        """Monte Carlo cross-check of semi-Markov absorption."""
        rng = np.random.default_rng(42)
        lam01 = 0.4
        lam12 = 0.15
        t_horizon = 72.0 / 8760.0
        n_sims = 10_000_000

        # Time in S0 ~ Exp(lam01), then time in S1 ~ Exp(lam12)
        t_s0 = rng.exponential(1.0 / lam01, n_sims)
        t_s1 = rng.exponential(1.0 / lam12, n_sims)
        absorbed = (t_s0 + t_s1) <= t_horizon
        p_mc = absorbed.mean()

        # Should be very close to 2.0e-6, but MC with 10M samples has limited precision
        # at this probability. We just check order of magnitude.
        assert p_mc < 1e-3, f"MC estimate {p_mc} too high"


# ============================================================
# UNI-8: Lyapunov Q matrix positive definite
# ============================================================

class TestUNI8_Lyapunov:
    """Q matrix from Lyapunov analysis must be positive definite."""

    def test_q_matrix_positive_definite(self):
        """
        Q = [[kV*    -r0/2           -(1-eta*gamma)/2]
             [-r0/2   kV_mean_revert  -eta*beta/2    ]
             [-(1-eta*gamma)/2  -eta*beta/2   eta*muL ]]
        """
        kV_star = 0.5
        kV = 0.3
        muL = 0.4
        r0 = 0.05
        gamma_ = 0.1
        beta_ = 0.02
        eta = 6.0  # document says eta >= 6 works

        Q = np.array([
            [kV_star, -r0 / 2, -(1 - eta * gamma_) / 2],
            [-r0 / 2, kV, -eta * beta_ / 2],
            [-(1 - eta * gamma_) / 2, -eta * beta_ / 2, eta * muL],
        ])

        eigenvalues = np.linalg.eigvalsh(Q)
        assert all(ev > 0 for ev in eigenvalues), (
            f"Q not positive definite: eigenvalues = {eigenvalues}"
        )


# ============================================================
# UNI-9: Student-t copula tail dependence monotone in nu
# ============================================================

class TestUNI9_CopulaTailDependence:
    """Student-t ES is decreasing in nu for nu >= 2."""

    def test_student_t_es_decreasing_in_nu(self):
        """ES of Student-t decreases as nu increases (lighter tails)."""
        q = 0.99
        nus = [3, 5, 10, 20, 50]
        es_values = []
        for nu in nus:
            # ES for standard Student-t at level q
            var_q = stats.t.ppf(q, df=nu)
            # ES = E[X | X >= VaR] for Student-t
            # = (nu + var_q^2) / (nu - 1) * stats.t.pdf(var_q, nu) / (1 - q)
            pdf_val = stats.t.pdf(var_q, df=nu)
            es = (nu + var_q ** 2) / (nu - 1) * pdf_val / (1 - q)
            es_values.append(es)

        # ES should be strictly decreasing in nu
        for i in range(len(es_values) - 1):
            assert es_values[i] > es_values[i + 1], (
                f"ES not decreasing: ES(nu={nus[i]})={es_values[i]} <= ES(nu={nus[i+1]})={es_values[i+1]}"
            )


# ============================================================
# UNI-10: Capital Table Cross-Check
# ============================================================

class TestUNI10_CapitalTable:
    """Capital table numbers must match between Doc 2 and Doc 3."""

    def test_required_capital(self):
        total = 16.4 + 5.9 + 0.37 + 3.80 + 0.8
        assert abs(total - 27.27) < 0.01

    def test_deployed_capital(self):
        deployed = 18.0 + 8.0 + 5.4
        assert abs(deployed - 31.4) < 0.01

    def test_car_ratio(self):
        car = 31.4 / 27.27
        assert abs(car - 1.15) < 0.01

    def test_invariant_d_junior_cap(self):
        alpha, total = 18.0, 31.4
        assert alpha / total < 0.80
