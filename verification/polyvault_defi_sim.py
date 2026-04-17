"""
PolyVault DeFi Treasury Vault — End-to-End Simulation (v3 architecture)

Validates the re-architected PolyVault stack for a DeFi custody use case:

Architecture (revised from v2):
  - Master key k* is a uniform-random scalar in F_n of secp256k1 (n = curve order),
    compatible with standard EVM signing.
  - k* is Shamir-split over F_n with (t, n) = (3, 5). Shards live on custodian devices.
  - Each custodian unlocks their shard via:
        unlock_key = HKDF( hw_token_secret || HE.Decrypt(passphrase, HE_blob) )
    where HE is Honey Encryption over a PASSPHRASE distribution (not over the raw key —
    HE is a bad fit for uniform keys but a good fit for low-entropy passphrases).
  - Cold backup: k* itself (not shards) is dual-symmetric-encrypted with two independent
    keys held in separate cold storage facilities. Stand-in for dual-PQC.
  - Audit trail: every signing event is signed with a hash-based stateless signature
    (Lamport stand-in for SPHINCS+). Quantum-forward audit log.

What this simulation proves:
  S1  End-to-end: 3 of 5 custodians can always reconstruct k* exactly.
  S2  1 or 2 compromised custodians + their passphrases + tokens still yield zero
      information about k* (perfect secrecy).
  S3  Stolen shard file WITHOUT the hardware token is computationally locked; WITHOUT
      the passphrase it is additionally HE-wrapped (wrong passphrase yields plausible
      fake passphrases from the common-password distribution).
  S4  DRBG independence across layers: pairwise correlation near zero.
  S5  Proactive re-share: shards rotated while k* preserved, old shards become stale.
  S6  Full rotation: new k*', reshare, old material orphaned (for post-compromise).
  S7  HE over raw keys is BAD: wrong-key decryption gives another uniform key — no hiding.
      HE over passphrases is GOOD: wrong-key decryption gives a plausible common password.

Run:
    python3 polyvault_defi_sim.py
or:
    pytest polyvault_defi_sim.py -v
"""

import os
import sys
import time
import hashlib
import hmac
import struct
import secrets
from typing import List, Tuple, Dict, Optional

import numpy as np
from scipy import stats as sp_stats
from Crypto.Cipher import AES
from Crypto.Protocol.KDF import scrypt as _scrypt

# Argon2id for production-accurate passphrase stretching (v3.2 D3 pinned).
# Falls back to scrypt if argon2-cffi is not available; wire format keeps
# kdf_variant byte to distinguish.
try:
    from argon2.low_level import hash_secret_raw, Type as _Argon2Type
    _ARGON2_AVAILABLE = True
except ImportError:
    _ARGON2_AVAILABLE = False


# ============================================================
# secp256k1 scalar field
# ============================================================
# Curve order n (public constant from SEC 2)
SECP256K1_N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141


def rand_scalar(n: int = SECP256K1_N) -> int:
    """Uniform scalar in [1, n-1] using os.urandom."""
    while True:
        b = os.urandom(32)
        s = int.from_bytes(b, "big") % n
        if 1 <= s < n:
            return s


# ============================================================
# Shamir secret sharing over F_n
# ============================================================

def mod_inv(a: int, p: int) -> int:
    return pow(a % p, p - 2, p)


def shamir_split(secret: int, t: int, n_shares: int, p: int = SECP256K1_N,
                 rng_scalar=rand_scalar) -> List[Tuple[int, int]]:
    """Return list of (x, y) shares. Polynomial degree t-1."""
    coeffs = [secret] + [rng_scalar(p) for _ in range(t - 1)]
    shares = []
    for x in range(1, n_shares + 1):
        y = 0
        xp = 1
        for c in coeffs:
            y = (y + c * xp) % p
            xp = (xp * x) % p
        shares.append((x, y))
    return shares


def shamir_reconstruct(shares: List[Tuple[int, int]], p: int = SECP256K1_N) -> int:
    """Lagrange at x=0."""
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
            num = (num * (-xm)) % p
            den = (den * (xj - xm)) % p
        lam = (num * mod_inv(den, p)) % p
        s = (s + yj * lam) % p
    return s


# ============================================================
# Symmetric AEAD (AES-256-GCM) — DEM layer
# ============================================================

def aead_enc(key: bytes, pt: bytes, aad: bytes = b"") -> bytes:
    """nonce(12) || ct || tag(16)"""
    assert len(key) == 32
    nonce = os.urandom(12)
    c = AES.new(key, AES.MODE_GCM, nonce=nonce)
    c.update(aad)
    ct, tag = c.encrypt_and_digest(pt)
    return nonce + ct + tag


def aead_dec(key: bytes, blob: bytes, aad: bytes = b"") -> bytes:
    assert len(key) == 32
    nonce, body, tag = blob[:12], blob[12:-16], blob[-16:]
    c = AES.new(key, AES.MODE_GCM, nonce=nonce)
    c.update(aad)
    return c.decrypt_and_verify(body, tag)


def hkdf(ikm: bytes, info: bytes, length: int = 32, salt: bytes = b"") -> bytes:
    """HKDF-SHA256."""
    if salt == b"":
        salt = b"\x00" * 32
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    okm = b""
    block = b""
    counter = 1
    while len(okm) < length:
        block = hmac.new(prk, block + info + bytes([counter]), hashlib.sha256).digest()
        okm += block
        counter += 1
    return okm[:length]


# -----------------------------------------------------------------------------
# Slow KDF for passphrase stretching (v3.2 §3.1 D3 pinned).
# -----------------------------------------------------------------------------
KDF_VARIANT_SCRYPT   = 0x01
KDF_VARIANT_ARGON2ID = 0x02

ARGON2ID_M_COST_PROD = 262144   # 256 MiB (production)
ARGON2ID_T_COST_PROD = 3
ARGON2ID_P_COST_PROD = 1

ARGON2ID_M_COST_SIM  = 8192     # 8 MiB  (sim; ~20 ms/op)
ARGON2ID_T_COST_SIM  = 2
ARGON2ID_P_COST_SIM  = 1

SCRYPT_N_SIM         = 2 ** 12  # fallback only


def stretch_passphrase(passphrase: str, salt: bytes,
                        m_cost: int = ARGON2ID_M_COST_SIM,
                        t_cost: int = ARGON2ID_T_COST_SIM,
                        p_cost: int = ARGON2ID_P_COST_SIM) -> bytes:
    """Slow KDF. Argon2id if available, scrypt fallback otherwise.
    Returns exactly 32 bytes."""
    if _ARGON2_AVAILABLE:
        return hash_secret_raw(
            secret=passphrase.encode("utf-8"),
            salt=salt,
            time_cost=t_cost, memory_cost=m_cost, parallelism=p_cost,
            hash_len=32, type=_Argon2Type.ID,
        )
    return _scrypt(passphrase, salt, key_len=32, N=SCRYPT_N_SIM, r=8, p=1)


def active_kdf_variant() -> int:
    return KDF_VARIANT_ARGON2ID if _ARGON2_AVAILABLE else KDF_VARIANT_SCRYPT


# -----------------------------------------------------------------------------
# shard_blob wire format v1 (98 bytes) — v3.2 §3.2 D3
# -----------------------------------------------------------------------------
SHARD_BLOB_VERSION = 0x01
SHARD_BLOB_LEN     = 98


def serialize_shard_blob(kdf_variant: int, m_cost: int, t_cost: int, p_cost: int,
                          salt: bytes, aead_nonce: bytes, aead_ct: bytes,
                          aead_tag: bytes) -> bytes:
    assert len(salt) == 32 and len(aead_nonce) == 12
    assert len(aead_ct) == 32 and len(aead_tag) == 16
    m_cost_log2 = m_cost.bit_length() - 1 if m_cost else 0
    header = (bytes([SHARD_BLOB_VERSION, kdf_variant & 0xFF])
              + m_cost_log2.to_bytes(2, "big")
              + bytes([t_cost & 0xFF, p_cost & 0xFF]))
    blob = header + salt + aead_nonce + aead_ct + aead_tag
    assert len(blob) == SHARD_BLOB_LEN
    return blob


def parse_shard_blob(blob: bytes) -> dict:
    if len(blob) != SHARD_BLOB_LEN:
        raise ValueError(f"shard_blob wrong length {len(blob)}")
    if blob[0] != SHARD_BLOB_VERSION:
        raise ValueError(f"shard_blob wrong version {blob[0]:#x}")
    return {
        "version":     blob[0],
        "kdf_variant": blob[1],
        "m_cost":      1 << int.from_bytes(blob[2:4], "big"),
        "t_cost":      blob[4],
        "p_cost":      blob[5],
        "salt":        blob[6:38],
        "aead_nonce":  blob[38:50],
        "aead_ct":     blob[50:82],
        "aead_tag":    blob[82:98],
    }


# -----------------------------------------------------------------------------
# he_blob wire format v1 (22 bytes) — dte-spec §7.4 D4
# -----------------------------------------------------------------------------
HE_BLOB_VERSION     = 0x01
HE_BLOB_DTE_VARIANT = 0x01
HE_BLOB_LEN         = 22


def serialize_he_blob(nonce: bytes, ct_uint32: int) -> bytes:
    assert len(nonce) == 12
    blob = (bytes([HE_BLOB_VERSION, HE_BLOB_DTE_VARIANT])
            + nonce
            + (ct_uint32 & 0xFFFFFFFF).to_bytes(4, "big")
            + b"\x00\x00\x00\x00")
    assert len(blob) == HE_BLOB_LEN
    return blob


def parse_he_blob(blob: bytes) -> dict:
    if len(blob) != HE_BLOB_LEN:
        raise ValueError(f"he_blob wrong length {len(blob)}")
    if blob[0] != HE_BLOB_VERSION or blob[1] != HE_BLOB_DTE_VARIANT:
        raise ValueError("he_blob unsupported version/variant")
    return {
        "version":     blob[0],
        "dte_variant": blob[1],
        "nonce":       blob[2:14],
        "ct":          int.from_bytes(blob[14:18], "big"),
        "reserved":    blob[18:22],
    }


# ============================================================
# Honey Encryption over a PASSPHRASE distribution
# ============================================================
# HE only makes sense when the message space has a known non-uniform distribution.
# A DeFi vault's master key is uniform — HE would be useless. But the custodian's
# PASSPHRASE follows a known distribution (human password frequencies). So we use
# HE to wrap the passphrase-derived share of the unlock key.

COMMON_PASSPHRASES = [
    "password", "123456", "qwerty", "letmein", "admin", "welcome",
    "monkey", "dragon", "master", "shadow", "sunshine", "princess",
    "football", "iloveyou", "trustno1", "ninja", "azerty", "starwars",
    "passw0rd", "baseball", "hello123", "freedom", "whatever",
    "p@ssword", "s3cret", "changeme", "zaq12wsx", "batman", "superman",
]
N_COMMON = len(COMMON_PASSPHRASES)  # 29


class PassphraseDTE:
    """Distribution-Transforming Encoder for a known passphrase corpus.

    We map the top-K common passphrases to CDF bins with higher weight,
    and reserve a tail for arbitrary user-chosen passphrases (hashed to bins).
    Codomain: integer in [0, N).

    Wrong-key decryption produces a passphrase from this distribution — a
    plausible decoy to a brute-force attacker.
    """
    N_BINS = 1 << 20  # 1M bins for smooth CDF

    def __init__(self):
        # Boost common passphrases, tail is near-uniform
        weights = np.ones(N_COMMON + 1)
        weights[:N_COMMON] = 8.0  # common passphrases 8x more likely
        weights[N_COMMON] = N_COMMON * 1.0  # the "rare/tail" bucket
        self.probs = weights / weights.sum()
        # Allocate bins proportional to probability
        self.bin_edges = np.zeros(N_COMMON + 2, dtype=np.int64)
        for i in range(N_COMMON + 1):
            width = max(1, int(round(self.probs[i] * self.N_BINS)))
            self.bin_edges[i + 1] = self.bin_edges[i] + width
        self.bin_edges[-1] = self.N_BINS

    def passphrase_to_idx(self, pw: str) -> int:
        if pw in COMMON_PASSPHRASES:
            return COMMON_PASSPHRASES.index(pw)
        return N_COMMON  # tail bucket

    def encode(self, pw: str, rng: Optional[np.random.Generator] = None) -> int:
        """Map passphrase to a point in its CDF bin."""
        if rng is None:
            rng = np.random.default_rng()
        idx = self.passphrase_to_idx(pw)
        lo = int(self.bin_edges[idx])
        hi = int(self.bin_edges[idx + 1])
        return int(rng.integers(lo, hi))

    def decode(self, u: int) -> str:
        """Inverse CDF: point in [0, N) -> passphrase (common or '<tail>')."""
        idx = int(np.searchsorted(self.bin_edges[1:], u, side="right"))
        idx = min(idx, N_COMMON)
        if idx < N_COMMON:
            return COMMON_PASSPHRASES[idx]
        return "<tail>"


class HoneyPassphraseWrapper:
    """HE.Enc(K, pw) -> he_blob v1 (22 bytes).

    Wire format per polyvault-dte-spec.md §7.4:
        [0]   version = 0x01
        [1]   dte_variant = 0x01
        [2:14]  nonce (12 bytes, per-encrypt fresh)
        [14:18] ct uint32 big-endian
        [18:22] reserved = 0x00000000

    PRF per spec §7.1: HMAC-SHA256(K, "PolyVault DTE v1 | HE_PASSPHRASE")[:4]
    as uint32 big-endian. (Simulation uses a smaller N_BINS — inherited from
    the legacy PassphraseDTE — because the full 2^32 tail generator isn't
    fully implemented in the sim; this is documented as a sim-vs-prod
    divergence. The wire format is v1-compliant.)
    """
    PRF_LABEL = b"PolyVault DTE v1 | HE_PASSPHRASE"

    def __init__(self):
        self.dte = PassphraseDTE()
        self.N = self.dte.N_BINS

    def _prf(self, key: bytes) -> int:
        # HMAC-SHA256 (D4 pinned); cross-language 1st-party primitive
        h = hmac.new(key, self.PRF_LABEL, hashlib.sha256).digest()
        return int.from_bytes(h[:4], "big") % self.N

    def encrypt(self, key: bytes, pw: str,
                rng: Optional[np.random.Generator] = None) -> bytes:
        """Emit an he_blob v1 (22 bytes)."""
        u = self.dte.encode(pw, rng)
        off = self._prf(key)
        c = (u + off) % self.N
        nonce = os.urandom(12)
        return serialize_he_blob(nonce, c)

    def decrypt(self, key: bytes, blob: bytes) -> str:
        parsed = parse_he_blob(blob)
        c = parsed["ct"] % self.N
        off = self._prf(key)
        u = (c - off) % self.N
        return self.dte.decode(u)


# ============================================================
# Lamport OTS (stand-in for SPHINCS+) for audit trail
# ============================================================

def _h(b: bytes) -> bytes:
    return hashlib.sha256(b).digest()


def lamport_keygen(seed: bytes) -> Tuple[List[Tuple[bytes, bytes]],
                                         List[Tuple[bytes, bytes]]]:
    sk, pk = [], []
    st = seed
    for i in range(256):
        st = _h(st + i.to_bytes(4, "big"))
        s0 = _h(st + b"\x00")
        s1 = _h(st + b"\x01")
        sk.append((s0, s1))
        pk.append((_h(s0), _h(s1)))
    return sk, pk


def lamport_sign(sk, msg: bytes) -> bytes:
    h = _h(msg)
    out = b""
    for i in range(256):
        bit = (h[i // 8] >> (7 - i % 8)) & 1
        out += sk[i][bit]
    return out


def lamport_verify(pk, msg: bytes, sig: bytes) -> bool:
    h = _h(msg)
    for i in range(256):
        bit = (h[i // 8] >> (7 - i % 8)) & 1
        rev = sig[i * 32:(i + 1) * 32]
        if _h(rev) != pk[i][bit]:
            return False
    return True


# ============================================================
# Custodian
# ============================================================

class Custodian:
    """One of n custodians. Holds:
      - hw_token_secret: simulates a hardware token (YubiKey / HSM-bound).
      - shard_blob:      AEAD-encrypted Shamir shard, key derived from (token, passphrase-HE).
      - he_blob:         HE-wrapped passphrase indicator (so a stolen file reveals a plausible
                         wrong passphrase, not a "decryption failed" oracle).
    """
    # v3.2 §3 info labels — domain separated, version-prefixed
    HKDF_UNLOCK_LABEL = b"PolyVault v3.2 | UNLOCK | "
    HKDF_HE_KEY_LABEL = b"PolyVault v3.2 | HE_KEY | "
    AEAD_SHARD_AAD    = b"PolyVault v3.2 | shard | "

    def __init__(self, idx: int, x: int, y: int, passphrase: str,
                 hw_token_secret: bytes, he: HoneyPassphraseWrapper,
                 rng: np.random.Generator,
                 duress_passphrase: Optional[str] = None):
        self.idx = idx
        self.x = x
        # Generate a fresh 32-byte random Argon2id salt (D3 pinned: salt is
        # independent of hw_token_secret; decouples passphrase rotation from
        # token rotation).
        self.argon2_salt = os.urandom(32)
        # Track parameters actually used (recorded in wire format).
        self.kdf_variant = active_kdf_variant()
        if self.kdf_variant == KDF_VARIANT_ARGON2ID:
            self.m_cost = ARGON2ID_M_COST_SIM
            self.t_cost = ARGON2ID_T_COST_SIM
            self.p_cost = ARGON2ID_P_COST_SIM
        else:
            self.m_cost = SCRYPT_N_SIM
            self.t_cost = 8   # scrypt r, stuffed into byte for format consistency
            self.p_cost = 1
        # HE-wrap the passphrase
        he_key = hkdf(hw_token_secret, self.HKDF_HE_KEY_LABEL + bytes([idx]))
        self.he_blob = he.encrypt(he_key, passphrase, rng)
        # Produce the shard_blob in v1 wire format
        self.shard_blob = self._build_shard_blob(passphrase,
                                                  y.to_bytes(32, "big"),
                                                  hw_token_secret)
        # Optional duress: separate blob with canary plaintext
        if duress_passphrase is not None:
            canary_bytes = b"\xFF" * 32
            self.duress_blob = self._build_shard_blob(duress_passphrase,
                                                       canary_bytes,
                                                       hw_token_secret)
        else:
            self.duress_blob = None
        # Hardware token secret is "in the token"
        self._hw_token_secret = hw_token_secret

    def _build_shard_blob(self, passphrase: str, plaintext32: bytes,
                           hw_token_secret: bytes) -> bytes:
        """Produce a v1 shard_blob (98 bytes fixed)."""
        stretched = stretch_passphrase(passphrase, self.argon2_salt,
                                        self.m_cost, self.t_cost, self.p_cost)
        ikm = hw_token_secret + stretched   # 32 + 32 = 64 bytes (fixed)
        unlock_key = hkdf(ikm, self.HKDF_UNLOCK_LABEL + bytes([self.idx]))
        aead_nonce = os.urandom(12)
        aad = self.AEAD_SHARD_AAD + bytes([self.idx])
        cipher = AES.new(unlock_key, AES.MODE_GCM, nonce=aead_nonce)
        cipher.update(aad)
        ct, tag = cipher.encrypt_and_digest(plaintext32)
        return serialize_shard_blob(
            kdf_variant=self.kdf_variant,
            m_cost=self.m_cost, t_cost=self.t_cost, p_cost=self.p_cost,
            salt=self.argon2_salt,
            aead_nonce=aead_nonce,
            aead_ct=ct, aead_tag=tag,
        )

    def _try_unlock(self, blob: bytes, passphrase_attempt: str) -> bytes:
        """Attempt to AEAD-decrypt a 98-byte shard_blob. Returns 32-byte plaintext
        or raises. Parses wire format to recover KDF params."""
        parsed = parse_shard_blob(blob)
        stretched = stretch_passphrase(passphrase_attempt, parsed["salt"],
                                        parsed["m_cost"], parsed["t_cost"],
                                        parsed["p_cost"])
        ikm = self._hw_token_secret + stretched
        unlock_key = hkdf(ikm, self.HKDF_UNLOCK_LABEL + bytes([self.idx]))
        aad = self.AEAD_SHARD_AAD + bytes([self.idx])
        cipher = AES.new(unlock_key, AES.MODE_GCM, nonce=parsed["aead_nonce"])
        cipher.update(aad)
        return cipher.decrypt_and_verify(parsed["aead_ct"], parsed["aead_tag"])

    def unlock_and_get_share(self, passphrase_attempt: str) -> Tuple[int, int]:
        """Unlock with provided passphrase. Raises on invalid.
        If duress passphrase matches, returns the canary share silently —
        caller can't distinguish; canary fails signature verification downstream.
        """
        try:
            y_bytes = self._try_unlock(self.shard_blob, passphrase_attempt)
            return (self.x, int.from_bytes(y_bytes, "big"))
        except Exception:
            pass
        if self.duress_blob is not None:
            try:
                y_bytes = self._try_unlock(self.duress_blob, passphrase_attempt)
                return (self.x, int.from_bytes(y_bytes, "big"))
            except Exception:
                pass
        raise ValueError("Invalid passphrase")

    def he_probe_passphrase(self, candidate: str, he: HoneyPassphraseWrapper) -> str:
        """What an offline attacker with the HE blob but NO token would see:
        they guess a 'key' and HE-decrypt, getting a decoy passphrase."""
        fake_key = hkdf(candidate.encode("utf-8"),
                         self.HKDF_HE_KEY_LABEL + bytes([self.idx]))
        return he.decrypt(fake_key, self.he_blob)


# ============================================================
# Cold backup: dual-symmetric wrap of k* (stand-in for dual PQC)
# ============================================================

def cold_backup_encrypt(secret_int: int) -> Tuple[bytes, bytes, bytes]:
    """Returns (ciphertext, k1, k2). k1 and k2 stored in two separate facilities."""
    k1, k2 = os.urandom(32), os.urandom(32)
    msg = secret_int.to_bytes(32, "big")
    inner = aead_enc(k1, msg, aad=b"cold_inner")
    outer = aead_enc(k2, inner, aad=b"cold_outer")
    return outer, k1, k2


def cold_backup_decrypt(blob: bytes, k1: bytes, k2: bytes) -> int:
    inner = aead_dec(k2, blob, aad=b"cold_outer")
    msg = aead_dec(k1, inner, aad=b"cold_inner")
    return int.from_bytes(msg, "big")


# ============================================================
# Vault orchestrator
# ============================================================

class Vault:
    def __init__(self, t: int, n: int, passphrases: List[str],
                 seed_rng: Optional[int] = None,
                 duress_passphrases: Optional[List[Optional[str]]] = None):
        assert len(passphrases) == n
        if duress_passphrases is not None:
            assert len(duress_passphrases) == n
        else:
            duress_passphrases = [None] * n
        self.t = t
        self.n = n
        self.np_rng = np.random.default_rng(seed_rng)
        # Generate master key k* in F_n
        self.k_star = rand_scalar()
        # Shamir split
        shares = shamir_split(self.k_star, t, n)
        # HE wrapper shared across custodians (public parameters)
        self.he = HoneyPassphraseWrapper()
        # Provision custodians
        self.custodians: List[Custodian] = []
        for i in range(n):
            tok = os.urandom(32)
            x, y = shares[i]
            c = Custodian(i, x, y, passphrases[i], tok, self.he, self.np_rng,
                          duress_passphrase=duress_passphrases[i])
            self.custodians.append(c)
        # Cold backup
        self.cold_blob, self.cold_k1, self.cold_k2 = cold_backup_encrypt(self.k_star)
        # Audit SPHINCS-stand-in key (one Lamport keypair per event in real SPHINCS hypertree;
        # here a fresh keypair for illustration)
        self.audit_sk, self.audit_pk = lamport_keygen(os.urandom(32))

    def sign_with_threshold(self, msg: bytes,
                            custodian_indices: List[int],
                            passphrases: List[str]) -> bytes:
        """Collect t shares, reconstruct k*, sign (stand-in), zeroize."""
        assert len(custodian_indices) == len(passphrases)
        assert len(custodian_indices) >= self.t
        shares = []
        for i, pw in zip(custodian_indices, passphrases):
            x, y = self.custodians[i].unlock_and_get_share(pw)
            shares.append((x, y))
        k_recovered = shamir_reconstruct(shares[:self.t])
        # "Sign" the message: for demo, ECDSA-like but we just HMAC with k_recovered
        sig = hmac.new(k_recovered.to_bytes(32, "big"), msg, hashlib.sha256).digest()
        # Audit-sign the event
        event = b"signed:" + _h(msg) + b":by:" + bytes(custodian_indices)
        audit_sig = lamport_sign(self.audit_sk, event)
        # Zeroize (Python can't truly zero ints, but we document the intent)
        k_recovered = 0
        return sig, audit_sig, event


# ============================================================
# SIMULATIONS
# ============================================================

def sim_S1_threshold_roundtrip():
    """S1: any t-of-n custodians reconstruct k* exactly."""
    print("\n[S1] Threshold sign round-trip, all C(5,3)=10 combinations")
    import itertools
    passphrases = [f"custodian_{i}_secret!" for i in range(5)]
    vault = Vault(t=3, n=5, passphrases=passphrases, seed_rng=42)
    msg = b"Transfer 1000 USDC to 0xABCD..."
    ok = 0
    for combo in itertools.combinations(range(5), 3):
        pws = [passphrases[i] for i in combo]
        sig, audit_sig, event = vault.sign_with_threshold(msg, list(combo), pws)
        # Verify audit signature
        assert lamport_verify(vault.audit_pk, event, audit_sig)
        ok += 1
    print(f"  [PASS] {ok}/10 combinations signed and audit-verified")
    return True


def sim_S2_subthreshold_zero_info():
    """S2: t-1 compromised custodians (with their passphrases and tokens!) learn
    nothing about k*. Quantified by: every k* in F_n is consistent with the observed
    t-1 shares. We verify this algebraically for the secp256k1 curve."""
    print("\n[S2] Sub-threshold adversary: t-1 = 2 shares give zero info on k*")
    passphrases = [f"pw_{i}" for i in range(5)]
    vault = Vault(t=3, n=5, passphrases=passphrases, seed_rng=123)
    # Adversary fully compromises custodians 0 and 1 (has passphrases, tokens, devices)
    shares_known = []
    for i in [0, 1]:
        x, y = vault.custodians[i].unlock_and_get_share(passphrases[i])
        shares_known.append((x, y))
    # For each candidate secret s_cand, the system
    #   s_cand + a1*x_i + a2*x_i^2 = y_i  (mod n)   for i in {1,2}
    # has non-singular 2x2 Vandermonde coefficient matrix [[x1, x1^2], [x2, x2^2]]
    x1, x2 = shares_known[0][0], shares_known[1][0]
    det = (x1 * x2 * x2 - x2 * x1 * x1) % SECP256K1_N
    assert det != 0, "Vandermonde minor must be non-singular"
    # Pick a few random candidate secrets; each must admit a valid (a1, a2)
    for trial in range(100):
        s_cand = rand_scalar()
        rhs1 = (shares_known[0][1] - s_cand) % SECP256K1_N
        rhs2 = (shares_known[1][1] - s_cand) % SECP256K1_N
        # Solve 2x2 system with Cramer's rule
        det_inv = mod_inv(det, SECP256K1_N)
        a1 = (rhs1 * (x2 * x2) - rhs2 * (x1 * x1)) * det_inv % SECP256K1_N
        a2 = (rhs2 * x1 - rhs1 * x2) * det_inv % SECP256K1_N
        # Verify
        y1_c = (s_cand + a1 * x1 + a2 * x1 * x1) % SECP256K1_N
        y2_c = (s_cand + a1 * x2 + a2 * x2 * x2) % SECP256K1_N
        assert y1_c == shares_known[0][1]
        assert y2_c == shares_known[1][1]
    print(f"  [PASS] All 100 random candidate secrets are consistent with 2 known shares")
    print(f"         => I(k* ; 2 shares) = 0 over F_n of secp256k1 (n ~ 2^256)")
    return True


def sim_S3_stolen_shard_without_token():
    """S3: shard_blob alone (device stolen, no hw token) — adversary cannot decrypt.
    HE_blob alone — adversary can 'decrypt' with any guess and get a plausible
    common passphrase as decoy, giving no decrypt oracle.
    """
    print("\n[S3] Stolen shard file: AEAD lock + HE decoy behavior")
    passphrases = [f"custodian_{i}" for i in range(5)]
    vault = Vault(t=3, n=5, passphrases=passphrases, seed_rng=7)
    target = vault.custodians[0]

    # Part A: attacker tries arbitrary (fake_token, fake_pw) pairs against the
    # shard_blob v1 wire format. Parses the blob to recover salt and KDF params
    # (those are public by design), then computes an unlock_key with the wrong
    # token. Every AEAD verification must fail.
    failures = 0
    trials = 200
    parsed = parse_shard_blob(target.shard_blob)
    for _ in range(trials):
        fake_token = os.urandom(32)
        fake_pw = secrets.choice(COMMON_PASSPHRASES)
        stretched = stretch_passphrase(fake_pw, parsed["salt"],
                                        parsed["m_cost"], parsed["t_cost"],
                                        parsed["p_cost"])
        ikm = fake_token + stretched
        unlock = hkdf(ikm, Custodian.HKDF_UNLOCK_LABEL + bytes([0]))
        aad = Custodian.AEAD_SHARD_AAD + bytes([0])
        try:
            cipher = AES.new(unlock, AES.MODE_GCM, nonce=parsed["aead_nonce"])
            cipher.update(aad)
            cipher.decrypt_and_verify(parsed["aead_ct"], parsed["aead_tag"])
            # If AEAD verifies, catastrophic
        except Exception:
            failures += 1
    print(f"  [A] Without token: {failures}/{trials} random attempts failed AEAD (expected {trials})")
    assert failures == trials

    # Part B: HE blob produces plausible common passphrases for wrong keys
    # We simulate 1000 wrong-token attempts and tally how often the decoy is a
    # real common passphrase.
    decoy_common = 0
    n = 1000
    for _ in range(n):
        decoy = target.he_probe_passphrase(secrets.token_hex(8), vault.he)
        if decoy in COMMON_PASSPHRASES:
            decoy_common += 1
    rate = decoy_common / n
    print(f"  [B] Wrong-key HE-decrypt produced common passphrase: {decoy_common}/{n} = {rate:.3f}")
    print(f"      (Expected ~ 0.89 given weight structure; <0.5 would indicate DTE bug)")
    assert rate > 0.5, "HE decoys not sufficiently biased toward common-password distribution"
    return True


def sim_S4_drbg_independence():
    """S4: pairwise correlation of keys generated via os.urandom across layers."""
    print("\n[S4] DRBG independence across layers (pairwise Pearson correlation)")
    N = 5000
    layers = 5  # master, 4 keying layers (shard rng, cold k1, cold k2, HE PRF seed)
    first_bytes = np.zeros((N, layers), dtype=np.int32)
    for i in range(N):
        ks = [os.urandom(32) for _ in range(layers)]
        for j, k in enumerate(ks):
            first_bytes[i, j] = k[0]
    max_abs_corr = 0.0
    worst_pair = None
    for a in range(layers):
        for b in range(a + 1, layers):
            r, _ = sp_stats.pearsonr(first_bytes[:, a].astype(float),
                                     first_bytes[:, b].astype(float))
            if abs(r) > max_abs_corr:
                max_abs_corr = abs(r)
                worst_pair = (a, b, r)
    print(f"  Worst-pair correlation: layers {worst_pair[0]}–{worst_pair[1]}, r = {worst_pair[2]:+.4f}")
    assert max_abs_corr < 0.05, f"DRBG independence FAIL: |r|={max_abs_corr:.4f}"
    # Also chi-squared uniformity of each layer's first byte
    for j in range(layers):
        counts = np.bincount(first_bytes[:, j], minlength=256)
        exp = np.full(256, N / 256)
        _, p = sp_stats.chisquare(counts, exp)
        assert p > 0.001, f"Layer {j} uniformity FAIL: p={p:.4f}"
    print(f"  [PASS] All pairs |r| < 0.05; each layer passes chi-squared uniformity")
    return True


def sim_S5_proactive_reshare():
    """S5: Proactive Secret Sharing — rotate shards while preserving k*.
    Old shards do NOT lie on the new polynomial.
    """
    print("\n[S5] Proactive re-share (PSS): k* preserved, old shards orphaned")
    passphrases = [f"pw_{i}" for i in range(5)]
    vault = Vault(t=3, n=5, passphrases=passphrases, seed_rng=2026)
    k_star = vault.k_star

    # Snapshot old shares
    old_shares = []
    for i in range(5):
        x, y = vault.custodians[i].unlock_and_get_share(passphrases[i])
        old_shares.append((x, y))

    # Fresh polynomial with same k*(0) = k_star
    new_shares = shamir_split(k_star, 3, 5)

    # Verify: any 3 new shares recover k_star
    rec = shamir_reconstruct(new_shares[:3])
    assert rec == k_star, "PSS round-trip failed"
    # Verify: old shares under the NEW polynomial are inconsistent (orphaned)
    # Reconstruct k using 2 new shares + 1 old share at a fresh x position => wrong
    # Specifically: the probability that an old (x, y_old) lies on the new polynomial
    # is 1/n ~ 2^-256 (old y_old is uniform given new poly at x != 0).
    # We can't test 2^-256, but we can confirm old != new for every x.
    diffs = sum(1 for (xo, yo), (xn, yn) in zip(old_shares, new_shares) if yo != yn)
    print(f"  Shards changed at {diffs}/5 positions (expected 5: new polynomial uncorrelated)")
    assert diffs == 5, "Old and new shards unexpectedly collide"
    # And: reconstructing with a mix of 3 old shares still gives k_star (old poly still recovers)
    rec_old = shamir_reconstruct(old_shares[:3])
    assert rec_old == k_star, "Old shards still recover k* (by design, until replaced)"
    print(f"  [PASS] New shards recover k*; old shards recover k* but don't lie on new poly")
    return True


def sim_S6_full_rotation():
    """S6: Post-compromise: fresh k*', reshare, old material entirely orphaned."""
    print("\n[S6] Full rotation (post-compromise): new k*' with fresh polynomial")
    passphrases = [f"pw_{i}" for i in range(5)]
    vault = Vault(t=3, n=5, passphrases=passphrases, seed_rng=808)
    k_old = vault.k_star

    # Fresh master
    k_new = rand_scalar()
    assert k_new != k_old, "Two fresh keys collided — ~2^-256 event, sim is wrong"
    new_shares = shamir_split(k_new, 3, 5)
    rec = shamir_reconstruct(new_shares[:3])
    assert rec == k_new
    # Old shards CANNOT reconstruct the new key
    rec_from_old = shamir_reconstruct([(c.x, 0) for c in vault.custodians[:3]])  # contrived
    # More meaningfully, old shares trivially reconstruct k_old, not k_new:
    old_shares = []
    for i in range(5):
        x, y = vault.custodians[i].unlock_and_get_share(passphrases[i])
        old_shares.append((x, y))
    rec_old = shamir_reconstruct(old_shares[:3])
    assert rec_old == k_old
    assert rec_old != k_new
    print(f"  [PASS] k_old recovered from old shares; k_new recovered from new shares; "
          f"no cross-recovery")
    return True


def sim_S7_HE_is_bad_for_uniform_keys():
    """S7: Demonstrate that HE wrapping a UNIFORM KEY gives no hiding —
    wrong-key decrypt just yields another uniform key, which the adversary
    can test against the on-chain address directly. HE must be applied only
    where the message space has a non-uniform distribution (e.g., passphrases).
    """
    print("\n[S7] HE over uniform keys vs. HE over passphrases")
    # Part A: uniform key wrapped by toy HE (simple XOR-with-PRF over 256-bit space)
    # Wrong-key decrypt gives another uniform 256-bit value. No distributional hiding.
    true_key = os.urandom(32)
    wrap_key = os.urandom(32)
    prf = hashlib.shake_256(wrap_key + b"UNIFORM_HE").digest(32)
    ct = bytes(a ^ b for a, b in zip(true_key, prf))

    # Adversary tries many wrong wrap_keys
    outputs = []
    for _ in range(5000):
        wk = os.urandom(32)
        pf = hashlib.shake_256(wk + b"UNIFORM_HE").digest(32)
        pt = bytes(a ^ b for a, b in zip(ct, pf))
        outputs.append(pt[0])
    # First byte should be uniform in [0, 255] — adversary has no signal
    counts = np.bincount(outputs, minlength=256)
    _, p = sp_stats.chisquare(counts, np.full(256, len(outputs) / 256))
    print(f"  [A] Uniform-key HE: first-byte uniformity p = {p:.3f}")
    print(f"      Adversary gets a uniform key regardless of guess — NO additional brute-force "
          f"barrier beyond 2^256. HE is useless here because every candidate is plausible.")
    # The point is: real brute force against a uniform 256-bit key is already infeasible,
    # so HE adds nothing. But adversary can't distinguish correct from incorrect either —
    # they'd verify against the on-chain address / derived pubkey.

    # Part B: passphrase distribution — HE adds value
    he = HoneyPassphraseWrapper()
    rng = np.random.default_rng(999)
    true_pw = "password"
    wrap_key = os.urandom(32)
    blob = he.encrypt(wrap_key, true_pw, rng)

    # Adversary tries wrong keys, decrypts to common passphrases
    decoys = []
    for _ in range(3000):
        wk = os.urandom(32)
        d = he.decrypt(wk, blob)
        decoys.append(d)
    common = sum(1 for d in decoys if d in COMMON_PASSPHRASES)
    rate = common / len(decoys)
    print(f"  [B] Passphrase HE: {rate:.3f} of wrong-key decoys are plausible common passwords")
    print(f"      This is the CORRECT use: adversary cannot brute-force with online oracle, "
          f"because every attempt returns a plausible 'password'/'123456'/'qwerty' decoy.")
    assert rate > 0.5
    return True


def sim_S9_slow_kdf_raises_bruteforce_cost():
    """S9: scrypt/Argon2id passphrase stretching raises offline dictionary-attack
    cost by a factor equal to the work parameter.

    Without stretch: adversary tries HKDF(token || pw) at ~1 us/op.
    With stretch:    adversary must run scrypt(pw, salt) first, per attempt.
    This shifts the economics of "stolen device, no token, brute-force the
    passphrase" from feasible to expensive.
    """
    print("\n[S9] Slow KDF raises offline brute-force cost")
    # Fast path: plain HKDF (no passphrase stretching)
    t0 = time.perf_counter()
    N_FAST = 2000
    for _ in range(N_FAST):
        hkdf(b"fake_token" * 4 + b"password", b"UNLOCK_0")
    dt_fast = time.perf_counter() - t0

    # Slow path: scrypt-stretch then HKDF
    t0 = time.perf_counter()
    N_SLOW = 20
    salt = os.urandom(32) + bytes([0])
    for _ in range(N_SLOW):
        s = stretch_passphrase("password", salt)
        hkdf(b"fake_token" * 4 + s, b"UNLOCK_0")
    dt_slow = time.perf_counter() - t0

    per_fast = dt_fast / N_FAST
    per_slow = dt_slow / N_SLOW
    ratio = per_slow / per_fast
    slow_name = "Argon2id + HKDF" if _ARGON2_AVAILABLE else "scrypt + HKDF"
    print(f"  HKDF only:          {per_fast*1e6:7.1f} us/op  ({1/per_fast:,.0f} ops/s)")
    print(f"  {slow_name:18s}{per_slow*1e3:7.1f} ms/op  ({1/per_slow:,.0f} ops/s)")
    variant = "Argon2id" if _ARGON2_AVAILABLE else "scrypt"
    print(f"  Slowdown factor:    {ratio:,.0f}x   (sim {variant}; prod Argon2id m=256MiB t=3 p=1)")
    # At N=2**12 the sim should see ratio > 500; at N=2**15 production >> 5000
    assert ratio > 100, f"Slow KDF not meaningfully slower (ratio={ratio:.0f})"
    return True


def sim_S10_duress_canary_deterministically_fails():
    """S10: On-device duress passphrase produces a canary shard (0xFF...FF).
    When included in Lagrange reconstruction, the resulting k_recovered is NOT
    the true k*. The signature over any transaction will therefore verify
    against the WRONG public key / address — verification fails without
    needing network-based flags.

    This is the network-free duress model: a coercer who forces a custodian
    to reveal their passphrase obtains a full-looking signing ceremony that
    produces an invalid signature at on-chain submission.
    """
    print("\n[S10] Duress passphrase produces canary -> recovered k does NOT match k*")
    pw_real = [f"real_pw_{i}" for i in range(5)]
    pw_duress = [f"DURESS_{i}!!" for i in range(5)]
    vault = Vault(t=3, n=5, passphrases=pw_real,
                   duress_passphrases=pw_duress, seed_rng=555)

    # Normal signing with all-real passphrases: recovered k* should match
    shares_real = []
    for i in [0, 1, 2]:
        x, y = vault.custodians[i].unlock_and_get_share(pw_real[i])
        shares_real.append((x, y))
    k_rec_real = shamir_reconstruct(shares_real)
    assert k_rec_real == vault.k_star, "real reconstruction failed"
    print(f"  [real] k_recovered == k*   (OK)")

    # Coerced signing: one custodian under duress provides duress_pw
    shares_mixed = []
    x, y = vault.custodians[0].unlock_and_get_share(pw_duress[0])  # canary
    shares_mixed.append((x, y))
    for i in [1, 2]:
        x, y = vault.custodians[i].unlock_and_get_share(pw_real[i])
        shares_mixed.append((x, y))
    k_rec_duress = shamir_reconstruct(shares_mixed)
    assert k_rec_duress != vault.k_star, (
        "duress-poisoned reconstruction accidentally recovered k*"
    )
    print(f"  [duress] k_recovered != k* (canary poisoned reconstruction, OK)")

    # Two duress passphrases (two coerced custodians): still poisoned
    shares_mixed2 = []
    for i in [0, 1]:
        x, y = vault.custodians[i].unlock_and_get_share(pw_duress[i])
        shares_mixed2.append((x, y))
    x, y = vault.custodians[2].unlock_and_get_share(pw_real[2])
    shares_mixed2.append((x, y))
    k_rec_duress2 = shamir_reconstruct(shares_mixed2)
    assert k_rec_duress2 != vault.k_star
    print(f"  [2-duress] k_recovered != k* (OK)")

    # ALL THREE duress: still poisoned (3 canaries -> reconstruction of 0xFF...FF)
    shares_all_duress = []
    for i in [0, 1, 2]:
        x, y = vault.custodians[i].unlock_and_get_share(pw_duress[i])
        shares_all_duress.append((x, y))
    k_rec_all_duress = shamir_reconstruct(shares_all_duress)
    # All canaries are 0xFF*32; Lagrange of a constant function at 0 yields that
    # same constant (since f(x) = C polynomial of degree 0, interpolation
    # through k points all equal to C gives C). But shamir_reconstruct assumes
    # degree t-1 polynomial; 3 equal-value "points" at x=1,2,3 interpolate to
    # that constant. So k_rec_all_duress = int(0xFF*32) != k_star. Confirm.
    canary_int = int.from_bytes(b"\xFF" * 32, "big") % SECP256K1_N
    assert k_rec_all_duress == canary_int
    assert k_rec_all_duress != vault.k_star
    print(f"  [all-duress] k_recovered == canary constant, != k* (OK)")
    print(f"  => signature over tx will not verify against on-chain address")
    return True


def sim_S8_end_to_end_latency():
    """S8: End-to-end signing latency (provisioning + sign) — production viability check."""
    print("\n[S8] End-to-end latency (provision + sign cycle)")
    passphrases = [f"custodian_{i}_long_passphrase_for_real" for i in range(5)]
    t0 = time.perf_counter()
    vault = Vault(t=3, n=5, passphrases=passphrases, seed_rng=None)
    t_prov = time.perf_counter() - t0

    t1 = time.perf_counter()
    msg = b"Transfer 1,000,000 USDC from treasury 0xVault to 0xRecipient, nonce=42"
    sig, audit_sig, event = vault.sign_with_threshold(
        msg, [0, 2, 4], [passphrases[0], passphrases[2], passphrases[4]]
    )
    t_sign = time.perf_counter() - t1

    print(f"  Provisioning (5 custodians + audit key): {t_prov*1000:.1f} ms")
    print(f"  Threshold sign (unlock 3 + Lagrange + audit-sign):    {t_sign*1000:.1f} ms")
    print(f"  Signature size: {len(sig)} B (HMAC stand-in); audit sig: {len(audit_sig)} B")
    assert t_sign < 1.0, "Sign path too slow for on-demand DeFi use"
    return True


def sim_S11_wire_format_conformance():
    """S11: shard_blob and he_blob wire formats (v1) parse/serialize round-trip
    and have the exact pinned byte layouts. This is the test the Rust port's
    conformance test will mirror — any divergence between Python and Rust
    output for the same inputs breaks the cross-language guarantee."""
    print("\n[S11] Wire format v1 conformance (shard_blob 98B, he_blob 22B)")

    # --- shard_blob ---
    fake_salt = bytes(range(32))
    fake_nonce = bytes(range(12))
    fake_ct = b"\xAA" * 32
    fake_tag = b"\xBB" * 16
    blob = serialize_shard_blob(
        kdf_variant=KDF_VARIANT_ARGON2ID,
        m_cost=262144, t_cost=3, p_cost=1,
        salt=fake_salt, aead_nonce=fake_nonce,
        aead_ct=fake_ct, aead_tag=fake_tag,
    )
    assert len(blob) == 98, f"shard_blob length {len(blob)} != 98"
    assert blob[0] == 0x01, "version byte must be 0x01"
    assert blob[1] == 0x02, "kdf_variant must be 0x02 (Argon2id)"
    assert int.from_bytes(blob[2:4], "big") == 18, "m_cost_log2 for 256MiB"
    assert blob[4] == 3, "t_cost"
    assert blob[5] == 1, "p_cost"
    assert blob[6:38]  == fake_salt
    assert blob[38:50] == fake_nonce
    assert blob[50:82] == fake_ct
    assert blob[82:98] == fake_tag
    parsed = parse_shard_blob(blob)
    assert parsed["salt"] == fake_salt
    assert parsed["aead_ct"] == fake_ct
    assert parsed["m_cost"] == 262144
    print(f"  shard_blob 98B layout OK; parsed fields match serialized input")

    # --- he_blob ---
    nonce = bytes(range(12))
    he_blob = serialize_he_blob(nonce, ct_uint32=0xDEADBEEF)
    assert len(he_blob) == 22
    assert he_blob[0] == 0x01
    assert he_blob[1] == 0x01
    assert he_blob[2:14] == nonce
    assert he_blob[14:18] == b"\xDE\xAD\xBE\xEF"
    assert he_blob[18:22] == b"\x00\x00\x00\x00"
    parsed_he = parse_he_blob(he_blob)
    assert parsed_he["nonce"] == nonce
    assert parsed_he["ct"] == 0xDEADBEEF
    print(f"  he_blob 22B layout OK")

    # --- round-trip via real Custodian (integration) ---
    he = HoneyPassphraseWrapper()
    rng = np.random.default_rng(0)
    tok = b"\x42" * 32
    c = Custodian(idx=0, x=1, y=999_999, passphrase="s3cret_pa55phrase!",
                   hw_token_secret=tok, he=he, rng=rng)
    # Size check
    assert len(c.shard_blob) == 98
    assert len(c.he_blob) == 22
    # Parse-ability
    s_parsed = parse_shard_blob(c.shard_blob)
    h_parsed = parse_he_blob(c.he_blob)
    assert s_parsed["kdf_variant"] in (KDF_VARIANT_ARGON2ID, KDF_VARIANT_SCRYPT)
    # Round-trip
    x, y = c.unlock_and_get_share("s3cret_pa55phrase!")
    assert x == 1 and y == 999_999
    # Wrong passphrase fails cleanly
    try:
        c.unlock_and_get_share("wrong_passphrase")
        raise AssertionError("wrong passphrase must fail")
    except ValueError:
        pass
    print(f"  Custodian integration round-trip OK")
    print(f"  kdf_variant={s_parsed['kdf_variant']:#x} "
          f"({'Argon2id' if s_parsed['kdf_variant'] == KDF_VARIANT_ARGON2ID else 'scrypt'})")
    return True


# ============================================================
# pytest-compatible tests
# ============================================================

def test_S1_threshold_roundtrip():
    assert sim_S1_threshold_roundtrip()

def test_S2_subthreshold_zero_info():
    assert sim_S2_subthreshold_zero_info()

def test_S3_stolen_shard_without_token():
    assert sim_S3_stolen_shard_without_token()

def test_S4_drbg_independence():
    assert sim_S4_drbg_independence()

def test_S5_proactive_reshare():
    assert sim_S5_proactive_reshare()

def test_S6_full_rotation():
    assert sim_S6_full_rotation()

def test_S7_HE_is_bad_for_uniform_keys():
    assert sim_S7_HE_is_bad_for_uniform_keys()

def test_S8_end_to_end_latency():
    assert sim_S8_end_to_end_latency()

def test_S9_slow_kdf_raises_bruteforce_cost():
    assert sim_S9_slow_kdf_raises_bruteforce_cost()

def test_S10_duress_canary():
    assert sim_S10_duress_canary_deterministically_fails()

def test_S11_wire_format_conformance():
    assert sim_S11_wire_format_conformance()


if __name__ == "__main__":
    print("=" * 64)
    print("PolyVault DeFi Treasury Vault — Simulation")
    print(f"  secp256k1 curve order n = {SECP256K1_N:x}")
    print(f"  (t, n) = (3, 5)")
    print("=" * 64)
    all_ok = all([
        sim_S1_threshold_roundtrip(),
        sim_S2_subthreshold_zero_info(),
        sim_S3_stolen_shard_without_token(),
        sim_S4_drbg_independence(),
        sim_S5_proactive_reshare(),
        sim_S6_full_rotation(),
        sim_S7_HE_is_bad_for_uniform_keys(),
        sim_S8_end_to_end_latency(),
        sim_S9_slow_kdf_raises_bruteforce_cost(),
        sim_S10_duress_canary_deterministically_fails(),
        sim_S11_wire_format_conformance(),
    ])
    print("\n" + "=" * 64)
    print("ALL SIMULATIONS PASSED" if all_ok else "SOME SIMULATIONS FAILED")
    print("=" * 64)
    sys.exit(0 if all_ok else 1)
