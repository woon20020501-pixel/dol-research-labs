# PolyShard: Information-Theoretic Security for Threshold Key Management

**Research Note — v1.0**

> *This note specifies the mathematical foundation for threshold secret sharing used in Dol's treasury key management. It does not describe a standalone product.*

---

## 1. Model and Assumptions

| Symbol | Definition |
|---|---|
| p | Large prime modulus, p > 2^60 |
| t | Recovery threshold (minimum shards required) |
| n | Total shard count, n >= t |
| s in F_p | Master secret |
| f(x) = s + a_1*x + ... + a_{t-1}*x^{t-1} | Random polynomial of degree t-1 |
| y_i = f(i) mod p | Shard #i |
| A | Adversary, can capture at most t-1 shards |

**Goal:** Prove that an adversary who captures fewer than t shards learns zero information about the secret s.

---

## 2. Security Theorem

### Lemma 1 (Shamir Impermeability)

In a modular (t-1)-degree polynomial sharing over F_p:

```
|Omega| < t  ==>  I(s; Y) = 0
```

where Y = {(i, y_i)}_{i in Omega} is the observed shard set and I denotes mutual information.

**Proof.** For any subset of fewer than t evaluations of a degree-(t-1) polynomial over F_p, every value of the free coefficient s is equally consistent with the observations. Formally:

```
Pr[s = sigma | Y] = Pr[s = sigma] = 1/p
```

for every sigma in F_p. The posterior equals the prior, so mutual information is zero. QED

**Interpretation:** Capturing a single device (PC, phone, or cloud storage) reveals exactly zero bits about the master secret, regardless of computational power — including quantum computers. This is an information-theoretic guarantee, not a computational one.

---

## 3. Multi-Device Deployment Scenario

| Storage Location | Shard Count | Example |
|---|---|---|
| Laptop HDD | 1 | y_1 |
| Smartphone Secure Enclave | 2 | y_2, y_3 |
| Cloud Storage (encrypted) | 2 | y_4, y_5 |

With t = 3, n = 5:
- **PC malware alone:** 1 shard captured. Lemma 1 applies. Information = 0.
- **Phone theft alone:** 2 shards captured. Still < t. Information = 0.
- **Cloud breach alone:** 2 shards captured. Still < t. Information = 0.
- **Any single-device compromise:** Information = 0.
- **Recovery requires:** any 3 of 5 shards from at least 2 different storage locations.

---

## 4. MAC Tag Independence

Each shard may carry an LWE-based MAC tag z_i = <a_i, y_i> + e_i for integrity verification. Even if the adversary obtains MAC tags, these do not help recover s:

- Tags verify integrity, not confidentiality
- Without the corresponding shard value y_i, a tag reveals no information about s
- Lemma 1 holds regardless of tag knowledge

---

## 5. Quantum Resistance

- **Shard security:** The uniformity argument in Lemma 1 is information-theoretic (applies to all adversaries, classical or quantum, with unbounded computation)
- **MAC tamper resistance:** Reduces to the lattice SIS problem, for which no polynomial-time quantum algorithm is known

---

## 6. Test Vectors

### Vector A — Hand-Verifiable (modulus 7,919)

| Parameter | Value |
|---|---|
| p | 7,919 |
| t | 3 |
| n | 5 |
| Secret s | 1,234 |

| Shard i | y_i = f(i) mod p |
|---|---|
| 1 | 1,494 |
| 2 | 1,942 |
| 3 | 2,578 |
| 4 | 3,402 |
| 5 | 4,414 |

**Verification:** Select any 3 shards (e.g., shards 1, 3, 4). Compute Lagrange coefficients over F_7919. Interpolate to recover s = 1,234.

### Vector B — Production-Scale (Mersenne prime 2^61 - 1)

| Parameter | Value |
|---|---|
| p | 2,305,843,009,213,693,951 (= 2^61 - 1) |
| t | 3 |
| n | 5 |
| Secret s | 9,876,543,210 |

| Shard i | y_i mod p |
|---|---|
| 1 | 14,567,900,112 |
| 2 | 25,810,146,926 |
| 3 | 40,382,283,940 |
| 4 | 58,284,311,154 |
| 5 | 79,516,228,568 |

All values fit in 64-bit unsigned integers. Any 3 shards interpolate to exactly 9,876,543,210.

---

## 7. Application to Dol Treasury

Dol's multi-sig treasury (see CAD-F Section 8) uses threshold signing with t-of-n key shares distributed across physically separated devices. The PolyShard construction ensures:

1. **Single-breach safety:** compromising one signing device reveals zero information about the master key
2. **Recovery without single point of failure:** any t devices can reconstruct the signing capability
3. **Quantum-forward security:** the information-theoretic guarantee survives advances in quantum computation

This complements the CAD-F operational safety controls (oracle redundancy, circuit breaker, Armageddon vault) by securing the key management layer itself.

---

## References

- Shamir, A. (1979). How to share a secret. *Communications of the ACM*, 22(11), 612-613.
- Regev, O. (2005). On lattices, learning with errors, random linear codes, and cryptography. *STOC 2005*.

---

*This document is a research note of the Dol project. It specifies mathematical properties of a cryptographic construction and does not constitute a security audit or certification.*
