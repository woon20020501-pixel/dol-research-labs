"""
PolyVault Theorem 5: Honey Encryption (DTE-Induced Info Concealment)  [STATISTICAL]

Verifies:
  - Decryption with wrong key K' != K produces messages distributed according
    to the original message distribution D
  - Formally: for all m, Pr[Dec(C, K') = m] = D(m)
  - This is the core DTE (Distribution-Transforming Encoder) property

Does NOT verify:
  - That the DTE is optimal for a specific message space
  - Security against adversaries who know the exact distribution D
  - Integration with the full PolyVault key hierarchy

We implement a simple Honey Encryption scheme over a discrete message space
(e.g., 4-digit PINs with known frequency distribution) and verify the
distribution property empirically.
"""
import os
import hashlib
import struct
import numpy as np
from scipy import stats as sp_stats
import pytest


# ============================================================
# Distribution-Transforming Encoder for PINs (0000-9999)
# ============================================================

class PinDistribution:
    """Known distribution over 4-digit PINs.
    Based on empirical PIN frequency data (simplified)."""

    def __init__(self):
        self.n = 10000  # PINs 0000-9999
        # Create a realistic non-uniform distribution
        # Common PINs (1234, 0000, 1111, etc.) have higher probability
        probs = np.ones(self.n) * 0.5  # base weight
        # Boost common PINs
        common = [1234, 0, 1111, 2222, 3333, 4444, 5555, 6666,
                  7777, 8888, 9999, 1212, 2580, 1004, 4321, 2001]
        for pin in common:
            probs[pin] = 10.0
        # Normalize
        self.probs = probs / probs.sum()
        self.cdf = np.cumsum(self.probs)

    def sample(self, rng=None):
        if rng is None:
            rng = np.random.default_rng()
        return rng.choice(self.n, p=self.probs)

    def encode(self, pin: int) -> float:
        """Map PIN to [0,1) interval via CDF. DTE encode."""
        if pin == 0:
            return 0.0
        return float(self.cdf[pin - 1])

    def decode(self, u: float) -> int:
        """Map [0,1) back to PIN via inverse CDF. DTE decode."""
        idx = np.searchsorted(self.cdf, u, side='right')
        return min(idx, self.n - 1)


class HoneyEncryption:
    """Honey Encryption using integer-based DTE for PINs.

    The DTE works in a discrete space [0, N) where N = 10000 * RESOLUTION.
    Encode maps PIN -> uniform integer in [0, N) via inverse CDF sampling.
    Encrypt adds a PRF(key) offset modulo N (modular addition, not XOR on floats).
    Wrong-key decryption shifts the offset, producing a different but still
    CDF-distributed point, which decodes to a PIN ~ D.
    """
    RESOLUTION = 1000  # sub-bins per PIN for smooth CDF

    def __init__(self, dist: PinDistribution):
        self.dist = dist
        self.N = dist.n * self.RESOLUTION
        # Build cumulative bin edges: pin i owns bins [lo_i, hi_i)
        self.bin_edges = np.zeros(dist.n + 1, dtype=np.int64)
        for i in range(dist.n):
            self.bin_edges[i + 1] = self.bin_edges[i] + max(1, int(round(dist.probs[i] * self.N)))
        # Adjust last edge to exactly N
        self.bin_edges[-1] = self.N

    def _prf(self, key: bytes) -> int:
        """Derive a pseudo-random integer in [0, N) from key."""
        h = hashlib.shake_256(key).digest(8)
        return int.from_bytes(h, 'big') % self.N

    def _encode(self, pin: int) -> int:
        """DTE encode: PIN -> random point in its CDF bin."""
        lo = int(self.bin_edges[pin])
        hi = int(self.bin_edges[pin + 1])
        # Pick uniformly within the bin (use pin+key hash for determinism)
        return (lo + hi) // 2  # midpoint for deterministic encrypt

    def _decode(self, u: int) -> int:
        """DTE decode: integer in [0, N) -> PIN via inverse CDF."""
        idx = np.searchsorted(self.bin_edges[1:], u, side='right')
        return min(int(idx), self.dist.n - 1)

    def encrypt(self, key: bytes, pin: int) -> bytes:
        """HE.Enc(K, m): encode m, then shift by PRF(K) mod N."""
        u = self._encode(pin)
        offset = self._prf(key)
        ct_int = (u + offset) % self.N
        return ct_int.to_bytes(8, 'big')

    def decrypt(self, key: bytes, ct: bytes) -> int:
        """HE.Dec(K, C): unshift by PRF(K) mod N, then decode."""
        ct_int = int.from_bytes(ct, 'big')
        offset = self._prf(key)
        u = (ct_int - offset) % self.N
        return self._decode(u)


# ============================================================
# Tests
# ============================================================

class TestTh5_RoundTrip:
    """Correct key recovers correct PIN."""

    def test_roundtrip(self):
        dist = PinDistribution()
        he = HoneyEncryption(dist)
        key = os.urandom(32)

        for pin in [0, 1234, 5555, 9999, 42, 8080]:
            ct = he.encrypt(key, pin)
            recovered = he.decrypt(key, ct)
            assert recovered == pin, f"PIN {pin}: recovered {recovered}"

    @pytest.mark.parametrize("seed", range(20))
    def test_random_pins(self, seed):
        rng = np.random.default_rng(seed)
        dist = PinDistribution()
        he = HoneyEncryption(dist)
        key = os.urandom(32)
        pin = rng.integers(0, 10000)
        ct = he.encrypt(key, pin)
        assert he.decrypt(key, ct) == pin


class TestTh5_WrongKeyDistribution:
    """
    THE CORE THEOREM 5 TEST.

    Decryption with wrong key K' should produce PINs distributed
    according to the original distribution D.

    We encrypt many PINs with correct key, decrypt with random wrong keys,
    and verify the output distribution matches D via chi-squared test.
    """

    def test_wrong_key_produces_distribution_D(self):
        dist = PinDistribution()
        he = HoneyEncryption(dist)
        rng = np.random.default_rng(42)

        n_samples = 50000
        correct_key = os.urandom(32)

        # Encrypt random PINs
        wrong_key_decryptions = []
        for _ in range(n_samples):
            pin = dist.sample(rng)
            ct = he.encrypt(correct_key, pin)
            # Decrypt with a WRONG key
            wrong_key = os.urandom(32)
            decrypted_pin = he.decrypt(wrong_key, ct)
            wrong_key_decryptions.append(decrypted_pin)

        # Bin the results
        observed = np.bincount(wrong_key_decryptions, minlength=dist.n)

        # Expected: n_samples * D(m) for each m
        expected = dist.probs * n_samples

        # Chi-squared test (group small bins to avoid chi2 issues)
        # Group PINs into 100 buckets of 100 each
        n_buckets = 100
        bucket_size = dist.n // n_buckets
        obs_bucketed = np.array([observed[i * bucket_size:(i + 1) * bucket_size].sum()
                                  for i in range(n_buckets)])
        exp_bucketed = np.array([expected[i * bucket_size:(i + 1) * bucket_size].sum()
                                  for i in range(n_buckets)])

        # Filter out zero-expected buckets
        mask = exp_bucketed > 0
        chi2, p_value = sp_stats.chisquare(obs_bucketed[mask], exp_bucketed[mask])

        # p > 0.001: cannot reject that wrong-key decryptions follow D
        assert p_value > 0.001, (
            f"Wrong-key distribution does NOT match D: chi2={chi2:.1f}, p={p_value:.6f}"
        )

    def test_wrong_key_common_pins_more_likely(self):
        """Even with wrong key, common PINs (1234, 0000) should appear more often
        than rare PINs, matching the distribution."""
        dist = PinDistribution()
        he = HoneyEncryption(dist)

        n_samples = 30000
        correct_key = os.urandom(32)
        rng = np.random.default_rng(99)

        decryptions = []
        for _ in range(n_samples):
            pin = dist.sample(rng)
            ct = he.encrypt(correct_key, pin)
            wrong_key = os.urandom(32)
            decryptions.append(he.decrypt(wrong_key, ct))

        counts = np.bincount(decryptions, minlength=dist.n)

        # PIN 1234 should appear more than an average PIN
        avg_count = n_samples / dist.n
        assert counts[1234] > avg_count * 2, (
            f"Common PIN 1234 count {counts[1234]} not elevated above avg {avg_count:.1f}"
        )


class TestTh5_IndistinguishabilityFromReal:
    """Adversary can't tell if decryption used correct or wrong key."""

    def test_ks_test_real_vs_fake(self):
        """Two-sample KS test between:
        - PINs decrypted with correct key (= original distribution)
        - PINs decrypted with wrong key (should also = original distribution)
        """
        dist = PinDistribution()
        he = HoneyEncryption(dist)
        rng = np.random.default_rng(555)
        correct_key = os.urandom(32)

        n = 10000
        real_pins = []
        fake_pins = []

        for _ in range(n):
            pin = dist.sample(rng)
            ct = he.encrypt(correct_key, pin)
            real_pins.append(he.decrypt(correct_key, ct))
            fake_pins.append(he.decrypt(os.urandom(32), ct))

        # KS test: both should come from the same distribution
        ks_stat, p_value = sp_stats.ks_2samp(real_pins, fake_pins)
        assert p_value > 0.01, (
            f"Real vs fake distributions distinguishable: KS={ks_stat:.4f}, p={p_value:.6f}"
        )
