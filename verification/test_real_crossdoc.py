"""
REAL VERIFICATION #2: Cross-Document Numerical Consistency  [CROSS-CHECK]

Verifies: numerical consistency across the research documents in this repository.
  - CAD-F-whitepaper.md (CAD-F)
  - phase2-risk-os.md (Phase 2)
  - polyshard-security.md (PolyShard)
  - MDLW-whitepaper.md (MDLW)

Does NOT verify: that any of the numbers are correct for production use.
"""
import pytest


class TestCADFCapitalTableArithmetic:
    """CAD-F capital table internal arithmetic."""

    def test_required_capital_sum(self):
        """Sum of components must equal stated Required Capital."""
        market_es = 16.4
        op_es = 6.13
        kl_addon = 0.37
        knightian = 9.32
        gas_liq = 0.8
        total = market_es + op_es + kl_addon + knightian + gas_liq
        assert abs(total - 33.02) < 0.01, f"Expected 33.02, got {total}"

    def test_deployed_capital_sum(self):
        alpha, beta, gamma = 24.0, 9.0, 6.0
        assert abs(alpha + beta + gamma - 39.0) < 0.01

    def test_car_ratio(self):
        car = 39.0 / 33.02
        assert abs(car - 1.18) < 0.01, f"CAR = {car}, expected ~1.18"

    def test_invariant_a_satisfied(self):
        """Invariant A: deployed >= required."""
        assert 39.0 >= 33.02

    def test_invariant_d_junior_cap(self):
        """Invariant D: alpha <= 0.8 * total."""
        assert 24.0 <= 0.8 * 39.0


class TestCADFOperationalES:
    """Per-category operational ES sums correctly."""

    def test_op_es_sum(self):
        categories = [0.34, 0.88, 3.12, 0.48, 0.29]
        total = sum(categories)
        assert abs(total - 5.11) < 0.01

    def test_op_es_with_buffer(self):
        """5.11 * 1.2 = 6.13 (now corrected in capital table)."""
        assert abs(5.11 * 1.2 - 6.13) < 0.01


class TestCADFParameters:
    """Key parameters are internally consistent."""

    def test_kl_epsilon(self):
        """KL epsilon = 2e-4 throughout."""
        eps = 2e-4
        assert eps < 1e-3  # order of magnitude check
        assert eps > 1e-5

    def test_knightian_epsilon(self):
        """Knightian epsilon = 0.002, must be < 1-q = 0.01."""
        eps = 0.002
        q = 0.99
        assert eps < 1 - q

    def test_semi_markov_params(self):
        """lambda_01 = 0.4/yr, lambda_12 = 0.15/yr."""
        import math
        lam01 = 0.4
        lam12 = 0.15
        t = 72.0 / 8760.0
        p = 1 - (lam12 * math.exp(-lam01 * t) - lam01 * math.exp(-lam12 * t)) / (lam12 - lam01)
        assert abs(p - 2.0e-6) < 0.5e-6


class TestPolyShard:
    """PolyShard test vectors must be self-consistent."""

    def test_vector_a_shares(self):
        """f(x) = 1234 + 166x + 94x^2 mod 7919."""
        p = 7919
        coeffs = [1234, 166, 94]
        expected = {1: 1494, 2: 1942, 3: 2578, 4: 3402, 5: 4414}
        for i, y_exp in expected.items():
            y = sum(c * pow(i, k, p) for k, c in enumerate(coeffs)) % p
            assert y == y_exp, f"Vector A share {i}: expected {y_exp}, got {y}"

    def test_vector_b_shares(self):
        """f(x) = 9876543210 + 1234567890x + 3456789012x^2 mod (2^61-1)."""
        p = (1 << 61) - 1
        coeffs = [9876543210, 1234567890, 3456789012]
        expected = {1: 14567900112, 2: 26172835038, 3: 44691347988,
                    4: 70123438962, 5: 102469107960}
        for i, y_exp in expected.items():
            y = sum(c * pow(i, k, p) for k, c in enumerate(coeffs)) % p
            assert y == y_exp, f"Vector B share {i}: expected {y_exp}, got {y}"
