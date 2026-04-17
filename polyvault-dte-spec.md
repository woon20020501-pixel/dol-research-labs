# PolyVault DTE — PassphraseDTE Implementation Specification

**Research Note — v1.0**

> *Self-contained implementation specification for the Distribution-Transforming Encoder (DTE) used by PolyVault Layer 3 (Honey Encryption over passphrase distribution). Split from the main security spec because this is a wire-level primitive that must be identical across every implementation (Python, Rust, TypeScript) to preserve the property that wrong-key decryptions produce network-consistent decoy passphrases.*
>
> *Audience: implementers. The only way to ship a PolyVault client is to match this document bit-for-bit.*

---

## 1. Purpose and threat model

A PolyVault custodian's device stores `he_blob = HE.Enc(he_key, passphrase)` alongside the AEAD-locked shard. An attacker with the device but no hardware token sees `he_blob` but cannot derive `he_key`. They can guess `he_key` values and decrypt — but every wrong guess yields a **plausible-looking passphrase** drawn from a known distribution `D`. There is no decryption oracle: the attacker cannot tell which guess was correct without also defeating the AEAD shard lock.

The DTE is the mechanism that turns wrong-key decryption outputs into plausible decoys. It maps between the passphrase space and a uniform integer space `[0, N)` via the CDF of `D`.

**Security property (Juels–Ristenpart 2014):** For any wrong key `K' ≠ K`, the distribution of `HE.Dec(C, K')` over the choice of `K'` equals `D`.

**This specification.** Pins `D`, the CDF encoding, the PRF, the wire format, and the tail generator tightly enough that two independent implementations produce bit-identical `he_blob`s for the same `(he_key, passphrase)` input.

---

## 2. Parameters

| Symbol | Value | Meaning |
|---|---|---|
| `N_BINS` | `2^32 = 4,294,967,296` | Codomain size of the DTE |
| `TOP_K` | `1024` | Number of explicitly-weighted common passphrases |
| `ZIPF_S` | `1.2` | Zipf distribution shape for common-mass weighting |
| `COMMON_MASS` | `0.5` | Fraction of `N_BINS` allocated to common passphrases |
| `TAIL_MASS` | `0.5` | Fraction of `N_BINS` allocated to the algorithmic tail |
| `WORDLIST_SIZE` | `4096` | Tail generator wordlist size |
| `TAIL_PATTERNS` | `8` | Number of tail-password patterns |

Total tail capacity: `WORDLIST_SIZE × TAIL_PATTERNS × (variable per pattern)`. Tail generator is deterministic: same bin index → same decoy string, forever.

---

## 3. Common-password corpus (TOP_K = 1024)

### 3.1 Source

The corpus is the first 1024 entries, in original rank order, of the **RockYou 2024 leaked-password frequency list** (or an equivalent annually-refreshed corpus; the specific source and its SHA-256 are pinned per major version of this spec).

### 3.2 Corpus pinning

The corpus is distributed as a plaintext file `common_passwords_v1.txt`:

- UTF-8 encoding, Unix newlines (`\n`).
- One passphrase per line, ordered by decreasing frequency.
- Exactly 1024 non-empty lines.
- No leading/trailing whitespace per line.
- Each passphrase ≤ 64 UTF-8 bytes.

The file's SHA-256 is pinned in this spec; implementations MUST refuse to load a corpus whose hash does not match.

```
common_passwords_v1.txt
  sha256: <TO-BE-FILLED-AT-BUILD>   # placeholder — set at first release
```

### 3.3 Rebuild discipline

- Corpus refresh cadence: annual, or sooner if the password-leak landscape shifts materially.
- Each refresh creates a new version: `common_passwords_v2.txt` with a new SHA-256. `dte_variant` byte in `he_blob` (§7) increments.
- `v1` continues to be supported for decryption of existing blobs; `he_blob` version byte selects the corpus.

---

## 4. Weight and bin-edge calculation

### 4.1 Common-mass weights

Define `zipf_weight(k) = 1 / (k+1)^ZIPF_S` for `k ∈ [0, TOP_K)`. Then:

```
raw_weights = [zipf_weight(k) for k in range(TOP_K)]
Z           = sum(raw_weights)
common_probs = [w / Z * COMMON_MASS for w in raw_weights]   # sums to 0.5
```

Each entry `common_probs[k]` is the fraction of `N_BINS` assigned to the `k`-th common passphrase.

### 4.2 Tail mass

`tail_mass = 0.5` of `N_BINS = 2,147,483,648` bins. Distributed uniformly over tail-index space (see §5).

### 4.3 Bin edges

```
bin_edges[0]   = 0
for k in 0 .. TOP_K-1:
    width      = max(1, round(common_probs[k] * N_BINS))
    bin_edges[k+1] = bin_edges[k] + width
bin_edges[TOP_K+1] = N_BINS     # snap final edge; tail occupies [bin_edges[TOP_K], N_BINS)
```

After this construction:
- `bin_edges` has length `TOP_K + 2`.
- `bin_edges[0] = 0`, `bin_edges[TOP_K+1] = N_BINS` exactly.
- `bin_edges` is strictly monotonic.
- Each common passphrase `k` owns the bin `[bin_edges[k], bin_edges[k+1])`.
- Tail owns `[bin_edges[TOP_K], N_BINS)`.

**Implementers:** compute `bin_edges` at initialization and cache. Do not recompute per encrypt/decrypt.

---

## 5. Tail generator

The tail generator is a deterministic function `tail_generate(bin_idx: uint64) -> str` that produces a plausible-looking passphrase for any bin index in the tail region.

### 5.1 Wordlist

`wordlist_v1.txt`: exactly 4,096 entries from the **EFF large wordlist** (`eff_large_wordlist.txt` as distributed by the Electronic Frontier Foundation, 2016 edition, 7,776 words), taking the first 4,096 entries in alphabetical order.

- UTF-8, Unix newlines, one word per line.
- ASCII lowercase only.
- SHA-256 pinned per version:

```
wordlist_v1.txt
  sha256: <TO-BE-FILLED-AT-BUILD>   # placeholder
```

### 5.2 Pattern table

Eight patterns, indexed 0..7:

| idx | pattern | example |
|---|---|---|
| 0 | `<word><2-digit-num>` | `monkey42` |
| 1 | `<Word><1-digit-num>!` | `Monkey7!` |
| 2 | `<word>_<year 2000..2025>` | `monkey_2024` |
| 3 | `<word><word>` | `monkeybear` |
| 4 | `<Word><Word>` | `MonkeyBear` |
| 5 | `<word>!` | `monkey!` |
| 6 | `<word>123` | `monkey123` |
| 7 | `<word>@<word>` | `monkey@bear` |

Capitalization rules:
- `<word>`: wordlist entry as-is (lowercase).
- `<Word>`: wordlist entry with first letter uppercased.

### 5.3 Tail generator algorithm

```
def tail_generate(bin_idx: uint64) -> str:
    # bin_idx is the offset WITHIN the tail region: [0, tail_size)
    # where tail_size = N_BINS - bin_edges[TOP_K]
    seed = HMAC-SHA256(key = b"PolyVault DTE v1 tail",
                       msg = bin_idx.to_bytes(8, 'big')).digest()  # 32 bytes
    pattern_idx = seed[0] % 8
    word1_idx   = int.from_bytes(seed[1:3],  'big') % 4096
    word2_idx   = int.from_bytes(seed[3:5],  'big') % 4096
    num_2       = int.from_bytes(seed[5:7],  'big') % 100
    num_1       = seed[7] % 10
    year        = 2000 + int.from_bytes(seed[8:10], 'big') % 26
    w1          = wordlist[word1_idx]
    w2          = wordlist[word2_idx]
    W1          = w1[:1].upper() + w1[1:]
    W2          = w2[:1].upper() + w2[1:]
    patterns = [
        f"{w1}{num_2:02d}",
        f"{W1}{num_1}!",
        f"{w1}_{year}",
        f"{w1}{w2}",
        f"{W1}{W2}",
        f"{w1}!",
        f"{w1}123",
        f"{w1}@{w2}",
    ]
    return patterns[pattern_idx]
```

### 5.4 Deterministic guarantees

- Same input bin_idx → same output string, forever, across all language implementations.
- No randomness, no clock, no locale dependency.
- ASCII output only (wordlist is ASCII; numeric suffixes are ASCII; `!`, `_`, `@` are ASCII).

---

## 6. Encode / decode

### 6.1 `passphrase_to_idx(pw: str) -> (in_common: bool, idx: int)`

```
def passphrase_to_idx(pw: str) -> tuple[bool, int]:
    try:
        k = common_list.index(pw)   # linear scan or hash-map lookup
        return (True, k)
    except ValueError:
        return (False, 0)            # "0" is a placeholder; tail encode ignores it
```

`common_list` is the 1024-entry corpus loaded from `common_passwords_v1.txt` at init.

### 6.2 `encode(pw: str, nonce: bytes) -> uint32`

```
def encode(pw: str, nonce: bytes) -> uint32:
    # nonce: 12 bytes, fresh per encryption (same as AEAD nonce discipline)
    # Used ONLY to pick a point inside the passphrase's bin — does not leak pw.
    in_common, k = passphrase_to_idx(pw)
    if in_common:
        lo, hi = bin_edges[k], bin_edges[k+1]
    else:
        # Tail: hash pw itself to pick a tail bin index deterministically,
        # then pick a uniform point in that bin. This way, re-encoding the
        # same pw twice (different nonces) produces different ciphertexts but
        # decodes back to the SAME tail string on the correct key.
        tail_seed = HMAC-SHA256(b"PolyVault DTE v1 tail-enc",
                                 pw.encode('utf-8')).digest()
        tail_bin_offset = int.from_bytes(tail_seed[:4], 'big') % (tail_size)
        abs_bin = bin_edges[TOP_K] + tail_bin_offset
        lo = abs_bin
        hi = abs_bin + 1     # tail bins are width 1
    # Pick a uniform integer in [lo, hi) using nonce as PRF seed
    prf_out = HMAC-SHA256(b"PolyVault DTE v1 enc-nonce", nonce).digest()
    pt_offset = int.from_bytes(prf_out[:4], 'big') % (hi - lo)
    return (lo + pt_offset) & 0xFFFFFFFF    # mod 2^32 guaranteed
```

`tail_size = N_BINS - bin_edges[TOP_K]`, pre-computed.

### 6.3 `decode(u: uint32) -> str`

```
def decode(u: uint32) -> str:
    # Binary search in bin_edges[1..TOP_K+1] for the first edge > u
    idx = searchsorted(bin_edges[1:], u, side='right')
    if idx < TOP_K:
        return common_list[idx]
    # Tail region
    tail_bin_offset = u - bin_edges[TOP_K]
    return tail_generate(tail_bin_offset)
```

`searchsorted` is `bisect_right` in Python, `slice::partition_point` in Rust, `Array.prototype.findIndex`-style in TypeScript.

---

## 7. Encrypt / decrypt wire format

### 7.1 PRF

```
def prf(key: bytes) -> uint32:
    # key: 32 bytes (the 'he_key' derived from hw_token_secret via HKDF)
    h = HMAC-SHA256(key, b"PolyVault DTE v1 | HE_PASSPHRASE").digest()
    return int.from_bytes(h[:4], 'big')    # mod 2^32 implicit
```

**HMAC-SHA256 chosen over SHAKE-256** because HMAC-SHA256 is a 1st-party primitive in every target language's stdlib (Rust `hmac` crate, TypeScript Web Crypto, Python `hmac`). Cross-language parity is simpler to verify.

### 7.2 Encrypt

```
def he_encrypt(he_key: bytes, passphrase: str, nonce: bytes) -> bytes:
    # nonce: 12 bytes, freshly sampled per encryption
    u = encode(passphrase, nonce)
    c = (u + prf(he_key)) & 0xFFFFFFFF
    return serialize_he_blob(version=1, dte_variant=1, nonce=nonce, ct=c)
```

### 7.3 Decrypt

```
def he_decrypt(he_key: bytes, blob: bytes) -> str:
    (version, dte_variant, nonce, c) = parse_he_blob(blob)
    if version != 1 or dte_variant != 1:
        raise InvalidBlob
    u = (c - prf(he_key)) & 0xFFFFFFFF
    return decode(u)
```

### 7.4 Wire format

`he_blob` is **22 bytes fixed**:

```
offset  size  field              value
   0     1    version            0x01
   1     1    dte_variant        0x01
   2    12    nonce              freshly sampled per encrypt (uniform 96-bit)
  14     4    ct_uint32_be       encrypted DTE point (big-endian)
  18     4    reserved           0x00000000  (for future dte_variant extension)
       ────
       22 bytes total
```

**Rationale for nonce inclusion.** Without per-encrypt nonce, `he_encrypt(he_key, pw)` is deterministic — two devices with the same `(he_key, pw)` produce identical blobs. That's fine for security but bad for forensic tracing (two custodians can't be distinguished by their he_blobs even if they enrolled the same passphrase). Fresh nonce makes each device's `he_blob` unique.

**The nonce is stored in the clear** on the device; it is a public value (same as an AEAD nonce). An attacker with the device sees the nonce; that is expected.

**Decryption is nonce-independent for correctness** but the nonce is used in `encode()` to pick the CDF-bin interior point. An attacker who wrongly decrypts sees `u = ct - prf(wrong_key) mod 2^32`, which is uniform in `[0, N_BINS)` over the choice of wrong_key. The nonce does not affect the *distribution* of wrong-key outputs — only the specific point for the correct key.

---

## 8. Initialization sequence (per process)

```python
def init_dte():
    # 1. Load and verify common-password corpus
    data = read_file("common_passwords_v1.txt")
    assert sha256(data) == PINNED_COMMON_HASH_V1
    common_list = data.decode('utf-8').split('\n')
    common_list = [p for p in common_list if p]
    assert len(common_list) == TOP_K

    # 2. Load and verify wordlist
    data = read_file("wordlist_v1.txt")
    assert sha256(data) == PINNED_WORDLIST_HASH_V1
    wordlist = data.decode('utf-8').split('\n')
    wordlist = [w for w in wordlist if w]
    assert len(wordlist) == WORDLIST_SIZE

    # 3. Compute bin_edges (§4.3)
    bin_edges = compute_bin_edges()
    assert bin_edges[0] == 0
    assert bin_edges[TOP_K + 1] == N_BINS
    assert all(bin_edges[i+1] > bin_edges[i] for i in range(TOP_K + 1))

    # 4. Build common-index map for fast lookup in encode()
    common_index = {p: i for i, p in enumerate(common_list)}

    tail_size = N_BINS - bin_edges[TOP_K]

    return DTEContext(common_list, common_index, wordlist, bin_edges, tail_size)
```

If any assertion fails, the implementation MUST refuse to proceed. Silent fallback is forbidden.

---

## 9. Conformance test vectors

Two vector tables are maintained:

- **§9.1** — *Sim corpus (`common_passwords_sim_v0.txt`, 29 entries).* These vectors are live and are emitted by `verification/polyvault_defi_sim.py::sim_S12_corpus_hash_and_dte_vectors`. They regression-test the Python implementation and are the baseline for early cross-language compatibility.
- **§9.2** — *Production corpus (`common_passwords_v1.txt`, 1024 entries).* These vectors will be pinned at the first tagged production release, after the operator selects and pins the corpus file (see §12). Until then, §9.1 is the authoritative cross-language reference.

Any implementation change that alters the output for any vector is a breaking change requiring a `dte_variant` bump (§10).

### 9.1 Sim-corpus vectors (corpus SHA-256 `2e616939…07e83d9`, deterministic)

Encoding convention for these vectors: `encode(pw, nonce)` picks the lower edge of the pw's bin (deterministic — sim only; production picks a uniform interior point with fresh nonce). Other values pinned:
- `he_key = 0x00 × 32`
- `nonce  = 0x0102030405060708090a0b0c`

| passphrase | he_blob (hex, 22B) | decoy on `he_key = 0xFF × 32` |
|---|---|---|
| `password` | `01010102030405060708090a0b0c000a319200000000` | `ninja` |
| `123456`   | `01010102030405060708090a0b0c000aaf1e00000000` | `azerty` |
| `s3cret`   | `01010102030405060708090a0b0c0005f6b200000000` | `dragon` |
| `changeme` | `01010102030405060708090a0b0c0006743e00000000` | `master` |

Regeneration: `python3 verification/polyvault_defi_sim.py` prints the table to stdout. CI test `test_S12_corpus_hash_and_dte_vectors` asserts bit-exactness.

### 9.2 Production-corpus vectors (pending corpus pin)

| he_key (hex, 32B) | passphrase | nonce (hex, 12B) | he_blob (hex, 22B) | decoy on wrong key |
|---|---|---|---|---|
| `0000…0000` | `"password"` | `000…000` | `<to-pin>` | `<to-pin>` |
| `0000…0000` | `"correcthorse"` | `000…000` | `<to-pin>` (tail) | `<to-pin>` (tail) |
| `ffff…ffff` | `"123456"` | `fff…fff` | `<to-pin>` | `<to-pin>` |

**Owner of the pin:** Security Lead, at the first tagged production release. Rust port `Sprint 1` exit criterion blocks on this pin being published — see `polyvault-rust-port-plan.md` §3 Sprint 1.

---

## 10. Migration between versions

When a new corpus is released (`common_passwords_v2.txt`) or a new pattern table is adopted:

1. New `dte_variant` byte assigned (`0x02`).
2. Both `v1` and `v2` supported for decryption; new encryption uses `v2`.
3. Custodians' `he_blob` rotated at next passphrase change — no mass re-encryption required because he_blob is ancillary, not load-bearing for shard security.
4. After N years of the new version being in the field, `v1` support may be deprecated. This is a soft deprecation: old blobs still decrypt; new clients refuse to emit `v1`.

Never mutate a pinned `dte_variant` in place. Every change is a new variant.

---

## 11. Security considerations

### 11.0 HE is distributional, not computational

The PRF truncation to 4 bytes (§7.1) caps the effective search space for `he_key` at `2^32`. A GPU-equipped adversary can enumerate this space in wall-clock minutes. This is **intentional**: HE provides *distribution-indistinguishability*, not computational hardness per guess.

Read carefully:

- **Under brute-force attack on `he_blob` alone**, every candidate `he_key` produces a *plausible* passphrase via the DTE. The attacker sees no error, no distinguisher, no oracle. They cannot rank one candidate as "more likely correct."
- **The computational barrier against passphrase recovery lives in Layer 1** (Argon2id), not here. HE's job is to eliminate the oracle; Argon2id's job is to make each guess expensive.
- **Together, the two layers** force an adversary with only the on-device files (no hardware token) into a bind: brute-forcing `he_key` yields a plausible decoy but no validation; validating requires running Argon2id on the candidate passphrase and attempting the Layer-2 AEAD unlock, which costs ~100 ms per attempt.

Do not read "HMAC-SHA256 → 256-bit security" into this primitive. The 4-byte truncation is part of the design, and the purpose is distributional hiding, not computational secrecy.

### 11.1 Attack: corpus guessing

**Threat.** An adversary who knows the deployed corpus can skew their decryption-attempt distribution toward uncommon passphrases, reasoning that the custodian's real passphrase is likely off the corpus.

**Response.** The adversary's prior is not the defense. The defense is that the adversary has no decryption *oracle* — they cannot tell when they've guessed correctly without also defeating the AEAD shard lock and the slow KDF. Shifting the adversary's search doesn't help them verify.

Further: if the custodian picks a passphrase that's NOT on the corpus (i.e., a tail passphrase), wrong-key decryption lands in the tail region and produces a tail-generated string. The adversary has no signal distinguishing "legitimate tail passphrase that generated a specific decoy" from "wrong key that happens to land in the tail."

### 11.2 Attack: adversary has a better corpus

**Threat.** An adversary with an up-to-date leak corpus that post-dates the deployment's pinned `common_passwords_v1.txt` can flag decoys as "low probability under current reality."

**Response.** Refresh cadence is annual (§3.3). The residual window is ≤ 12 months. If a leak event materially shifts the landscape between refreshes, operators issue an unscheduled update.

### 11.3 Attack: low-entropy custodian passphrase

**Threat.** Custodian picks `"password"`. HE decoys don't matter; the slow KDF is the only defense.

**Response.** HE is not a substitute for a real passphrase. Deployment checklist (main spec §13) requires ≥ 16-char password-manager-generated passphrase. HE is a defense-in-depth against the specific failure mode of a lost device *plus* a defender who used a moderate passphrase.

### 11.4 Attack: length-based distinguisher

**Threat.** Real custodian passphrases may be systematically longer than typical decoys. The adversary, seeing many wrong-key decryption outputs from a brute-force, could cluster by length and flag the "too long" cluster as likely real.

**Response.** The adversary does not *see* the wrong-key decryption outputs of other custodians. Each `he_blob` is local to its device. Per-device, the adversary's wrong-key decryption outputs follow the tail/common distribution; clustering on a single device's outputs is exactly the DTE output distribution, by design.

Cross-device clustering is a real concern if the adversary breaches many devices simultaneously. The current design does not defend against that. Mitigation: require `> 16` char passphrases so the tail generator output (typically < 12 chars) doesn't stand out against real inputs. The deployment checklist enforces this.

---

## 12. Open questions flagged for operator decision

- **Corpus source.** RockYou 2024 is a choice; leaked-password corpora have legal-gray status. Some jurisdictions require an IRB / compliance sign-off to distribute even as part of security tooling. Recommend: use a research-respected academic corpus (e.g., LIPS or similar) whose license is explicit. **Operator decision required before release.**
- **Wordlist licensing.** EFF large wordlist is CC BY 3.0 US. Compatible with most licenses; verify against Dol's chosen project license before shipping.
- **Corpus distribution.** Ship with the client binary, or fetch at install time? Fetching at install time allows rotation without client rebuild but introduces a supply-chain surface. Recommend: ship with binary, rotate via versioned client release.

---

## 13. References

- Juels, A., Ristenpart, T. (2014). Honey Encryption: Security Beyond the Brute-Force Bound. *EUROCRYPT 2014*.
- EFF. (2016). EFF's Large Wordlist for Passphrases. https://www.eff.org/dice
- Zipf, G. K. (1935). The Psycho-Biology of Language.
- Krawczyk, H. (2010). Cryptographic Extraction and Key Derivation: The HKDF Scheme. *CRYPTO 2010*.

---

*This document is an implementation specification of the Dol project's PolyVault DTE. Version 1.0 is frozen at release; changes produce new versions (v2, v3, ...) with new `dte_variant` bytes. v1.0 does not constitute a security audit or certification.*
