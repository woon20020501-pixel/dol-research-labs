"""
PolyVault Theorem 4: SPHINCS+ EUF-CMA  [IMPLEMENTATION + STRUCTURAL]

Verifies:
  - Signature/verification round-trip (correctness)
  - Tampered message detection (unforgeability structure)
  - Tampered signature detection
  - Different messages produce different signatures

Does NOT verify:
  - Actual EUF-CMA security (requires breaking hash functions)
  - Quantum resistance of SHAKE-256 / SHA-256
  - The reduction Adv_SIG <= q_s * Adv_CR + negl(lambda)

We implement a simplified hash-based one-time signature (Lamport-like)
to demonstrate the structural properties. SPHINCS+ is a scaled version
of the same principle (many-time via hypertree of OTS).
"""
import os
import hashlib
import pytest


# ============================================================
# Simplified Hash-Based Signature (Lamport-style, demonstrates structure)
# ============================================================

def hash256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


class LamportKeyPair:
    """Lamport one-time signature for 256-bit messages."""

    def __init__(self, seed: bytes = None):
        if seed is None:
            seed = os.urandom(32)
        # Generate 256 pairs of random 256-bit values
        rng_state = seed
        self.sk = []  # secret key: 256 pairs of 32-byte values
        self.pk = []  # public key: hash of each sk value
        for i in range(256):
            rng_state = hash256(rng_state + i.to_bytes(4, 'big'))
            sk0 = hash256(rng_state + b'\x00')
            sk1 = hash256(rng_state + b'\x01')
            self.sk.append((sk0, sk1))
            self.pk.append((hash256(sk0), hash256(sk1)))

    def sign(self, msg: bytes) -> bytes:
        """Sign a message (hash it first to get 256 bits)."""
        h = hash256(msg)
        sig = b''
        for i in range(256):
            bit = (h[i // 8] >> (7 - i % 8)) & 1
            sig += self.sk[i][bit]
        return sig

    def verify(self, msg: bytes, sig: bytes) -> bool:
        """Verify a signature."""
        h = hash256(msg)
        for i in range(256):
            bit = (h[i // 8] >> (7 - i % 8)) & 1
            revealed = sig[i * 32:(i + 1) * 32]
            if hash256(revealed) != self.pk[i][bit]:
                return False
        return True


class TestTh4_RoundTrip:
    """Signature correctness: Sign then Verify returns True."""

    @pytest.mark.parametrize("msg", [
        b"",
        b"hello",
        b"a" * 1000,
        os.urandom(256),
    ])
    def test_valid_signature_verifies(self, msg):
        kp = LamportKeyPair(seed=b"test_seed_roundtrip")
        sig = kp.sign(msg)
        assert kp.verify(msg, sig)


class TestTh4_Unforgeability:
    """Structural properties supporting EUF-CMA."""

    def test_wrong_message_rejects(self):
        """Signature for msg1 does not verify for msg2."""
        kp = LamportKeyPair(seed=b"unforge_test")
        msg1 = b"original message"
        msg2 = b"tampered message"
        sig = kp.sign(msg1)
        assert not kp.verify(msg2, sig)

    def test_tampered_signature_rejects(self):
        """Flipping a byte in the signature causes rejection."""
        kp = LamportKeyPair(seed=b"tamper_sig")
        msg = b"test message"
        sig = kp.sign(msg)
        tampered = bytearray(sig)
        tampered[100] ^= 0xFF
        assert not kp.verify(msg, bytes(tampered))

    def test_truncated_signature_rejects(self):
        kp = LamportKeyPair(seed=b"truncate")
        msg = b"test"
        sig = kp.sign(msg)
        assert not kp.verify(msg, sig[:-32])  # missing last block

    def test_random_signature_rejects(self):
        """Random bytes are not a valid signature."""
        kp = LamportKeyPair(seed=b"random_sig")
        msg = b"test"
        fake_sig = os.urandom(256 * 32)
        assert not kp.verify(msg, fake_sig)


class TestTh4_DifferentMessagesProduceDifferentSigs:
    """Different messages should produce different signatures
    (collision resistance of the hash)."""

    def test_different_msgs_different_sigs(self):
        kp = LamportKeyPair(seed=b"diff_msg")
        msgs = [f"message_{i}".encode() for i in range(50)]
        sigs = [kp.sign(m) for m in msgs]
        # All signatures should be unique
        assert len(set(sigs)) == len(sigs)


class TestTh4_HashCollisionStructure:
    """
    Theorem 4 says Adv_SIG <= q_s * Adv_CR.
    We verify the structural claim: forging a signature requires
    finding a hash preimage (or collision).
    """

    def test_signature_reveals_preimages(self):
        """Each signature component is a preimage of the corresponding pk component."""
        kp = LamportKeyPair(seed=b"preimage_check")
        msg = b"structural verification"
        sig = kp.sign(msg)
        h = hash256(msg)

        for i in range(256):
            bit = (h[i // 8] >> (7 - i % 8)) & 1
            revealed = sig[i * 32:(i + 1) * 32]
            # The revealed value should hash to the public key
            assert hash256(revealed) == kp.pk[i][bit]
            # The OTHER public key component remains hidden
            # (no way to derive sk[i][1-bit] from sig)

    def test_one_time_property(self):
        """Signing two different messages with same key leaks secret key bits.
        This is why SPHINCS+ uses a hypertree of OTS keys.
        We verify the leak exists (structural demonstration)."""
        kp = LamportKeyPair(seed=b"one_time")
        msg1 = b"message one"
        msg2 = b"message two"
        sig1 = kp.sign(msg1)
        sig2 = kp.sign(msg2)

        h1 = hash256(msg1)
        h2 = hash256(msg2)

        # Count positions where h1 and h2 differ
        # At those positions, both sk[i][0] and sk[i][1] are revealed
        leaked_positions = 0
        for i in range(256):
            bit1 = (h1[i // 8] >> (7 - i % 8)) & 1
            bit2 = (h2[i // 8] >> (7 - i % 8)) & 1
            if bit1 != bit2:
                leaked_positions += 1

        # Roughly half the positions should differ (hash is ~random)
        assert leaked_positions > 50, "Should have significant bit differences"
        # This demonstrates why OTS must not be reused
