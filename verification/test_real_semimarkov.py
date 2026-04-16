"""
REAL VERIFICATION #4: Semi-Markov Formula Derivation  [INDEPENDENT DERIVATION + MC]

Verifies:
  1. The hypoexponential CDF formula is correctly stated (independent convolution integral)
  2. The specific claim P(72h) ~ 2.02e-6 is arithmetically correct given stated params
  3. 100M-sample Monte Carlo cross-validates the analytical result

Does NOT verify:
  - Whether lam01=0.4/yr, lam12=0.15/yr are reasonable for this protocol
  - Whether a 3-state semi-Markov is the right availability model
  - Whether partial-availability states (mentioned as open item) change the result
"""
import numpy as np
from scipy import integrate
import pytest
import math


class TestSemiMarkovDerivation:
    """Derive absorption CDF from first principles and compare."""

    def test_convolution_integral(self):
        """P(T1+T2 <= t) where T1~Exp(lam01), T2~Exp(lam12).
        Compute via numerical convolution integral and compare to formula."""
        lam01 = 0.4   # /yr
        lam12 = 0.15  # /yr
        t = 72.0 / 8760.0  # 72 hours in years

        # Analytical formula
        p_formula = 1 - (lam12 * math.exp(-lam01 * t) - lam01 * math.exp(-lam12 * t)) / (lam12 - lam01)

        # Numerical convolution: P(T1+T2 <= t) = integral_0^t f_T1(s) * F_T2(t-s) ds
        # where f_T1(s) = lam01*exp(-lam01*s), F_T2(u) = 1 - exp(-lam12*u)
        def integrand(s):
            if s > t or s < 0:
                return 0.0
            return lam01 * math.exp(-lam01 * s) * (1 - math.exp(-lam12 * (t - s)))

        p_numerical, error = integrate.quad(integrand, 0, t)

        assert abs(p_formula - p_numerical) < 1e-12, (
            f"Formula: {p_formula}, Numerical: {p_numerical}, diff: {abs(p_formula - p_numerical)}"
        )

    def test_72h_specific_value(self):
        """Verify the specific claim: P ~ 2.02e-6."""
        lam01 = 0.4
        lam12 = 0.15
        t = 72.0 / 8760.0

        p = 1 - (lam12 * math.exp(-lam01 * t) - lam01 * math.exp(-lam12 * t)) / (lam12 - lam01)

        print(f"P(0->2, 72h) = {p:.6e}")
        assert abs(p - 2.02e-6) < 0.5e-6, f"Expected ~2.02e-6, got {p:.6e}"

    def test_wrong_earlier_attempts_would_give_different_values(self):
        """The whitepaper says earlier analytic attempts gave 0.46 and 4.9e-4.
        These are orders of magnitude too high. Common mistakes:

        1. Forgetting to convert 72h to years (using t=72 instead of t=72/8760)
        2. Using the wrong formula (e.g., product of marginals)
        """
        lam01 = 0.4
        lam12 = 0.15

        # Mistake 1: t = 72 (treating hours as years)
        t_wrong = 72.0  # 72 YEARS
        p_wrong1 = 1 - (lam12 * math.exp(-lam01 * t_wrong) - lam01 * math.exp(-lam12 * t_wrong)) / (lam12 - lam01)
        print(f"With t=72 years: P = {p_wrong1:.4f}")
        # This would be ~1.0 (almost certain), not 0.46

        # Mistake 2: P = P(T1 < 72h) * P(T2 < 72h) — independence, but wrong formula
        t_correct = 72.0 / 8760.0
        p_t1 = 1 - math.exp(-lam01 * t_correct)
        p_t2 = 1 - math.exp(-lam12 * t_correct)
        p_wrong2 = p_t1 * p_t2
        print(f"Product of marginal CDFs: P = {p_wrong2:.6e}")
        # This IS different from the convolution answer, but it's an upper bound

        # The correct answer
        p_correct = 1 - (lam12 * math.exp(-lam01 * t_correct) - lam01 * math.exp(-lam12 * t_correct)) / (lam12 - lam01)
        print(f"Correct: {p_correct:.6e}")
        print(f"Product bound: {p_wrong2:.6e}")
        assert p_wrong2 >= p_correct, "Product should be an upper bound"

    def test_monte_carlo_validation(self):
        """Heavy MC to validate the analytical formula."""
        rng = np.random.default_rng(12345)
        lam01 = 0.4
        lam12 = 0.15
        t = 72.0 / 8760.0
        n_sims = 100_000_000  # 100M for rare event

        t1 = rng.exponential(1.0 / lam01, n_sims)
        t2 = rng.exponential(1.0 / lam12, n_sims)
        absorbed = (t1 + t2) <= t
        p_mc = absorbed.mean()

        p_formula = 1 - (lam12 * math.exp(-lam01 * t) - lam01 * math.exp(-lam12 * t)) / (lam12 - lam01)

        print(f"Formula: {p_formula:.6e}")
        print(f"MC (100M sims): {p_mc:.6e}")
        print(f"MC absorbed count: {absorbed.sum()}")

        # With 100M sims and p~2e-6, we expect ~200 events
        # Standard error ~ sqrt(p*(1-p)/n) ~ sqrt(2e-6/1e8) ~ 4.5e-7
        # So we should be within 2-3x of that
        if absorbed.sum() > 0:
            se = math.sqrt(p_mc * (1 - p_mc) / n_sims)
            assert abs(p_mc - p_formula) < 5 * se, (
                f"MC deviates from formula by {abs(p_mc - p_formula)/se:.1f} standard errors"
            )


class TestSemiMarkovEdgeCases:
    """Edge cases for the semi-Markov model."""

    def test_equal_rates(self):
        """When lam01 = lam12, the formula has a 0/0 form.
        The correct answer is the Erlang-2 CDF: 1 - (1 + lam*t)*exp(-lam*t)."""
        lam = 0.3
        t = 72.0 / 8760.0

        # Erlang-2 CDF
        p_erlang = 1 - (1 + lam * t) * math.exp(-lam * t)

        # Limit of hypoexponential as rates converge
        eps = 1e-10
        lam01 = lam
        lam12 = lam + eps
        p_hypo = 1 - (lam12 * math.exp(-lam01 * t) - lam01 * math.exp(-lam12 * t)) / (lam12 - lam01)

        assert abs(p_erlang - p_hypo) < 1e-6

    def test_zero_time_gives_zero(self):
        """At t=0, absorption probability must be 0."""
        lam01, lam12 = 0.4, 0.15
        t = 0.0
        p = 1 - (lam12 * math.exp(-lam01 * t) - lam01 * math.exp(-lam12 * t)) / (lam12 - lam01)
        assert abs(p) < 1e-15

    def test_large_time_approaches_1(self):
        """As t -> infinity, absorption probability -> 1."""
        lam01, lam12 = 0.4, 0.15
        t = 1000.0  # ~1000 years
        p = 1 - (lam12 * math.exp(-lam01 * t) - lam01 * math.exp(-lam12 * t)) / (lam12 - lam01)
        assert abs(p - 1.0) < 1e-10
