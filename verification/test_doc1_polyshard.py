"""
Doc 1: PolyShard (보안.rtf) — Verification Suite

Coverage level for each test:
  PS-1: Vector A share values           [FULL]     independent computation vs document's stated values
  PS-2: Vector A 3-of-5 recovery        [FULL]     all C(5,3)=10 combinations, independent Lagrange impl
  PS-3: Vector B share values            [FULL]     FOUND DOCUMENT ERROR — shares i=2..5 are wrong
  PS-4: Vector B 3-of-5 recovery        [FULL]     all 10 combinations with CORRECTED share values
  PS-5: Shamir info-theoretic security   [THEORETICAL] re-derives Shamir 1979 theorem, not new verification
  PS-6: Noise-MAC bound                 [FORMULA ONLY] checks 3*(q/32) < q/8, which is arithmetic

Verification scripts authored with Claude Code assistance.
All results are reproducible via: pytest verification/
"""
import itertools
import pytest


# ============================================================
# Helpers: modular arithmetic & Lagrange interpolation over F_p
# ============================================================

def mod_inv(a: int, p: int) -> int:
    """Modular inverse via extended Euclidean algorithm."""
    return pow(a, p - 2, p)


def lagrange_interpolate_at_zero(shares: list[tuple[int, int]], p: int) -> int:
    """Recover f(0) from a list of (x_i, y_i) shares in F_p."""
    s = 0
    k = len(shares)
    for j in range(k):
        xj, yj = shares[j]
        num = 1
        den = 1
        for m in range(k):
            if m == j:
                continue
            xm = shares[m][0]
            num = (num * (0 - xm)) % p
            den = (den * (xj - xm)) % p
        lam = (num * mod_inv(den, p)) % p
        s = (s + yj * lam) % p
    return s


def eval_poly(coeffs: list[int], x: int, p: int) -> int:
    """Evaluate polynomial with coefficients [a0, a1, a2, ...] at x mod p."""
    result = 0
    for i, c in enumerate(coeffs):
        result = (result + c * pow(x, i, p)) % p
    return result


# ============================================================
# Vector A: small modulus p = 7919, t = 3, n = 5
# ============================================================
VA_P = 7919
VA_SECRET = 1234
VA_COEFFS = [1234, 166, 94]  # f(x) = 1234 + 166x + 94x^2
VA_SHARES_EXPECTED = {1: 1494, 2: 1942, 3: 2578, 4: 3402, 5: 4414}
VA_T = 3
VA_N = 5


class TestPS1_VectorA_ShareValues:
    """PS-1: f(i) mod 7919 must match the document's stated share values."""

    @pytest.mark.parametrize("i,expected_y", list(VA_SHARES_EXPECTED.items()))
    def test_share_value(self, i, expected_y):
        computed = eval_poly(VA_COEFFS, i, VA_P)
        assert computed == expected_y, (
            f"Share {i}: expected {expected_y}, got {computed}"
        )


class TestPS2_VectorA_Recovery:
    """PS-2: Any 3-of-5 shares must recover secret = 1234."""

    @pytest.mark.parametrize(
        "combo",
        list(itertools.combinations(range(1, VA_N + 1), VA_T)),
        ids=lambda c: f"shares_{c}",
    )
    def test_recovery(self, combo):
        shares = [(i, VA_SHARES_EXPECTED[i]) for i in combo]
        recovered = lagrange_interpolate_at_zero(shares, VA_P)
        assert recovered == VA_SECRET, (
            f"Combo {combo}: expected {VA_SECRET}, got {recovered}"
        )


# ============================================================
# Vector B: Mersenne prime p = 2^61 - 1, t = 3, n = 5
# ============================================================
VB_P = (1 << 61) - 1  # 2305843009213693951
VB_SECRET = 9876543210
VB_COEFFS = [9876543210, 1234567890, 3456789012]
# FINDING: Document states these share values, but they are WRONG for i=2..5.
# f(1) is correct, but f(2)..f(5) do not match f(x) = s + a1*x + a2*x^2 mod p.
# Correct values computed below.
VB_SHARES_DOC = {
    1: 14567900112,
    2: 25810146926,   # doc WRONG, actual = 26172835038
    3: 40382283940,   # doc WRONG, actual = 44691347988
    4: 58284311154,   # doc WRONG, actual = 70123438962
    5: 79516228568,   # doc WRONG, actual = 102469107960
}
VB_SHARES_EXPECTED = {
    1: 14567900112,
    2: 26172835038,
    3: 44691347988,
    4: 70123438962,
    5: 102469107960,
}
VB_T = 3
VB_N = 5


class TestPS3_VectorB_ShareValues:
    """PS-3: f(i) mod (2^61-1) must match COMPUTED values (document has errors)."""

    @pytest.mark.parametrize("i,expected_y", list(VB_SHARES_EXPECTED.items()))
    def test_share_value_corrected(self, i, expected_y):
        computed = eval_poly(VB_COEFFS, i, VB_P)
        assert computed == expected_y, (
            f"Share {i}: expected {expected_y}, got {computed}"
        )


class TestPS3_FINDING_DocumentError:
    """FINDING: Document's Vector B share values for i=2..5 are incorrect.

    f(x) = 9876543210 + 1234567890*x + 3456789012*x^2 mod (2^61-1)
    f(1) = 14567900112  (correct in document)
    f(2) = 26172835038  (document says 25810146926 — WRONG)
    f(3) = 44691347988  (document says 40382283940 — WRONG)
    f(4) = 70123438962  (document says 58284311154 — WRONG)
    f(5) = 102469107960 (document says 79516228568 — WRONG)
    """

    @pytest.mark.parametrize("i,doc_val,correct_val", [
        (2, 25810146926, 26172835038),
        (3, 40382283940, 44691347988),
        (4, 58284311154, 70123438962),
        (5, 79516228568, 102469107960),
    ])
    def test_document_share_is_wrong(self, i, doc_val, correct_val):
        """Confirm the document's stated value does NOT match the polynomial."""
        computed = eval_poly(VB_COEFFS, i, VB_P)
        assert computed != doc_val, f"Share {i}: doc value unexpectedly matches"
        assert computed == correct_val, f"Share {i}: our correction is also wrong"


class TestPS4_VectorB_Recovery:
    """PS-4: Any 3-of-5 shares must recover secret = 9876543210."""

    @pytest.mark.parametrize(
        "combo",
        list(itertools.combinations(range(1, VB_N + 1), VB_T)),
        ids=lambda c: f"shares_{c}",
    )
    def test_recovery(self, combo):
        shares = [(i, VB_SHARES_EXPECTED[i]) for i in combo]
        recovered = lagrange_interpolate_at_zero(shares, VB_P)
        assert recovered == VB_SECRET, (
            f"Combo {combo}: expected {VB_SECRET}, got {recovered}"
        )


# ============================================================
# PS-5: Information-theoretic security (t-1 shares => zero info)
# ============================================================
class TestPS5_InformationTheoreticSecurity:
    """
    PS-5: Given any t-1 = 2 shares, every possible secret in F_p is consistent
    with exactly one polynomial of degree t-1.

    For small p (Vector A), we enumerate all possible secrets and verify
    each is achievable. For large p (Vector B), we verify algebraically.
    """

    def test_vector_a_all_secrets_consistent(self):
        """With 2 shares from Vector A, every s in F_p has exactly one
        consistent polynomial. We verify by checking that for each candidate
        secret, there exists a unique (a1, a2) satisfying the share equations."""
        shares_2 = [(1, VA_SHARES_EXPECTED[1]), (2, VA_SHARES_EXPECTED[2])]
        # For each candidate secret s, we need:
        #   s + a1*1 + a2*1  = y1 mod p
        #   s + a1*2 + a2*4  = y2 mod p
        # This is a 2x2 linear system in (a1, a2) with a non-singular
        # Vandermonde-like matrix, so it has exactly one solution for any s.
        #
        # Matrix: [[1, 1], [2, 4]]
        # det = 1*4 - 1*2 = 2, which is nonzero mod 7919.
        det = (1 * 4 - 1 * 2) % VA_P
        assert det != 0, "System must be non-singular"

        # Verify for a sample of secrets (full enumeration of 7919 is feasible)
        consistent_count = 0
        for s_candidate in range(VA_P):
            rhs1 = (shares_2[0][1] - s_candidate) % VA_P
            rhs2 = (shares_2[1][1] - s_candidate) % VA_P
            # Solve: a1 + a2 = rhs1, 2*a1 + 4*a2 = rhs2
            det_inv = mod_inv(det, VA_P)
            a2 = ((rhs2 - 2 * rhs1) * det_inv) % VA_P  # actually (4*rhs1 - rhs2) / det ... let me redo
            # Cramer's rule:
            # |rhs1  1|     |1  rhs1|
            # |rhs2  4|     |2  rhs2|
            a1 = (rhs1 * 4 - rhs2 * 1) * mod_inv(det, VA_P) % VA_P
            a2 = (1 * rhs2 - 2 * rhs1) * mod_inv(det, VA_P) % VA_P
            # Verify this polynomial is consistent
            y1_check = (s_candidate + a1 * 1 + a2 * 1) % VA_P
            y2_check = (s_candidate + a1 * 2 + a2 * 4) % VA_P
            if y1_check == shares_2[0][1] and y2_check == shares_2[1][1]:
                consistent_count += 1

        assert consistent_count == VA_P, (
            f"Expected all {VA_P} secrets to be consistent, got {consistent_count}"
        )

    def test_vector_b_algebraic_uniformity(self):
        """For Vector B (large p), verify algebraically that the system
        matrix for 2 shares is non-singular, hence every secret is consistent."""
        shares_2 = [(1, VB_SHARES_EXPECTED[1]), (2, VB_SHARES_EXPECTED[2])]
        # Same Vandermonde argument: det([[1,1],[2,4]]) = 2 != 0 mod p
        det = (1 * 4 - 1 * 2) % VB_P
        assert det != 0, "System must be non-singular for information-theoretic security"
        # Non-singular => for every s in F_p, unique (a1, a2) exists => uniform


# ============================================================
# PS-6: Noise-MAC bound
# ============================================================
class TestPS6_NoiseMACBound:
    """
    PS-6: If each noise term |e_i| < q/32 and we sum t=3 terms,
    then |sum(e_i)| < 3*q/32 < q/8 = 4*q/32.

    The document claims: individual |e_i| < q/32 => total |e| < q/8.
    This holds because 3 * (q/32) = 3q/32 < 4q/32 = q/8.
    """

    @pytest.mark.parametrize("q", [7919, VB_P, 2**128])
    def test_noise_bound_arithmetic(self, q):
        t = 3
        individual_bound = q / 32
        worst_case_sum = t * individual_bound  # 3q/32
        claimed_bound = q / 8  # 4q/32
        assert worst_case_sum < claimed_bound, (
            f"Noise bound violated: {t}*q/32 = {worst_case_sum} >= q/8 = {claimed_bound}"
        )

    def test_noise_bound_with_random_samples(self):
        """Monte Carlo: sample random noises within bound, verify sum bound."""
        import random
        random.seed(42)
        q = 7919
        bound = q // 32
        for _ in range(10000):
            noises = [random.randint(-bound + 1, bound - 1) for _ in range(3)]
            total = sum(noises)
            assert abs(total) < q // 8, f"Noise sum {total} exceeds q/8 = {q // 8}"
