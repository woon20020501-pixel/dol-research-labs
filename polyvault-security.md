# PolyVault DeFi — Treasury Custody Engineering Specification

**Research Note — v3.2 (implementation-pinned)**

> *Changes in v3.2 (vs v3.1): four open items are now pinned, making this document sufficient for implementation teams to begin Rust / TypeScript / Solidity work without further architectural decisions.*
>
> | # | Pin | Rationale |
> |---|---|---|
> | **D1** | Cold-backup storage: three facilities — HSM Vendor A for `k_inner`, HSM Vendor B for `k_outer`, governance-multisig-controlled private S3 + Arweave mirror for `C_outer` (§7) | Removes implementer latitude on ciphertext placement; ensures any one or two facility breaches yield zero plaintext |
> | **D2** | DKG procedure: tiered — Phase 1 air-gapped trusted-dealer ceremony, Phase 2 HSM-internal generation, Phase 3 Pedersen DKG (§6.3) | Phase 1 is executable this week; Phase 2 requires HSM relationships; Phase 3 requires mature TSS tooling |
> | **D3** | Argon2id parameters + `shard_blob` wire format v1 frozen (§3) | Locks the on-device format before any deployment so future clients remain decryption-compatible |
> | **D4** | PassphraseDTE specification moved to a dedicated wire-level document, `polyvault-dte-spec.md` (§5 summarizes; full spec external) | Cross-implementation parity requires a bit-exact spec; stays out of the architectural doc |
>
> *Audience: security engineers and the teams who will implement the above. Companion documents: `polyvault-dte-spec.md` (DTE wire-level), `polyvault-ceremony-runbook.md` (Phase 1 DKG runbook), `polyvault-rust-port-plan.md` (implementation sequencing for the Dol Rust runtime).*
>
> *All claims labeled "simulation-verified" are reproducible by `polyvault_defi_sim.py` whose 10 tests cover every architectural decision below.*

---

## 0. Why DeFi custody shapes this architecture

PolyVault began as an individual-user key spec. DeFi treasury custody inverts several assumptions; v3 corrects them.

| Individual-user assumption | DeFi reality | Architectural consequence |
|---|---|---|
| Unlock factor = biometric | Custodians are institutions or human signers; no natural biometric; sharing one is a liability | Custodian auth = hardware token + stretched passphrase (§3) |
| Master key is arbitrary plaintext | Master key is a `secp256k1` scalar used to sign EVM transactions | Shamir over `F_n` of secp256k1 (§6) |
| HE is a universal outer armor | HE gives hiding only when the message space has a *known non-uniform* distribution. A uniform 256-bit key does not | HE wraps the passphrase, not the key (§5) |
| Device loss can be silent | DeFi key loss is governance-visible — the signing key is an on-chain owner | Rotation procedures are first-class; on-chain owner migration drills (§11) |

Two further design choices:

- **Reconstruction-free signing when feasible.** Production DeFi custody should use a threshold signature scheme (FROST, GG18/GG20, CMP21) so the master scalar is never materialized. This spec uses Shamir-reconstruct-then-sign as the baseline because it is simple and implementable in any language. §12 describes the TSS upgrade.
- **Post-quantum armor on cold backup, not hot path.** Classical on-chain ECDSA signing is quantum-reachable only via the chain's own migration path. Cold-backup ciphertexts sit around for years and are the asset most worth PQ-protecting today (§7).

---

## 1. Threat Model

| Asset | Adversary | In scope | Out of scope |
|---|---|---|---|
| Master signing scalar `k*` | ≤ `t−1` custodian devices + tokens + passphrases compromised | Shamir threshold (§6) | ≥ `t` custodians colluding or compromised |
| On-device shard file | Thief with stolen device, no token, no passphrase | Stretched-passphrase AEAD lock (§3, §4) + HE decoy (§5) | Thief with token and passphrase |
| Cold backup ciphertext | Attacker with access to one or two of three cold facilities | 3-facility split (§7) | Attacker with all three |
| Audit trail | Forger rewriting signing history | Hash-based signature (§8) | Revocation of already-signed valid events |
| Recovery operation | Adversary intercepting reshare | Governance-gated PSS / rotation (§11) | Coerced custodian executing a malicious rotation on-chain |

**Explicitly not protected against**

- `≥ t` colluding custodians (threshold is by design).
- Compromised chain node returning attacker-chosen state.
- Smart-contract bugs in the treasury contract.
- Physical coercion of a single custodian — mitigated only by `t ≥ 2` and by duress-passphrase design (§11.4).
- Quantum attack on the on-chain ECDSA scalar itself when the chain is classical.

---

## 2. Layer Map

Hot path (every signing event, in execution order):

```
[passphrase]  →  scrypt/Argon2id stretch  →  HKDF(token ∥ stretched)  →  unlock_key     [Layer 1]
                                                                             │
                                                      AEAD.Dec(unlock_key, shard_blob)  [Layer 2]
                                                                             │
                        (HE blob present as decoy for stolen device; not on legit path) [Layer 3]
                                                                             │
                                                                    yield share (x, y)
                                                                             │
   ×t  custodians  ⇒  collect t shares  ⇒  Lagrange over F_n  ⇒  k*  ⇒  sign(tx)        [Layer 4]
```

Cold path (infrequent):

```
k*  ──►  AEAD.Enc(k_inner) ──►  AEAD.Enc(k_outer)  ──►  ciphertext C                    [Layer 5]
                                                           │
                                                           ▼
                        C in Facility X, k_inner in Facility Y, k_outer in Facility Z
```

Global:

```
every signing event  ──►  SPHINCS+ / hash-based signature  ──►  append-only audit log   [Layer 6]
```

| # | Layer | Primitive | Scope | Section |
|---|---|---|---|---|
| 1 | Custodian authentication | **Argon2id → HKDF-SHA256** (D3 pinned) | per-custodian | §3 |
| 2 | AEAD shard lock | AES-256-GCM (wire format v1 pinned) | per-custodian | §4 |
| 3 | Honey encryption passphrase decoy | PassphraseDTE + HMAC-SHA256 PRF (see `polyvault-dte-spec.md`) | per-custodian | §5 |
| 4 | Shamir threshold over secp256k1 `F_n` | Shamir (1979); DKG = tiered Phase 1/2/3 (D2 pinned) | across custodians | §6 |
| 5 | Dual AEAD cold backup | AES-256-GCM × 2 → prod McEliece ∘ ML-KEM; three-facility storage (D1 pinned) | off-line | §7 |
| 6 | Audit signature | SPHINCS+-256s (sim: Lamport OTS) | global | §8 |

---

## 3. Layer 1 — Custodian Authentication

### 3.1 Construction (D3 pinned)

Each custodian holds:

- `hw_token_secret` — 256-bit value bound to a hardware token (YubiKey, HSM-attested key). Non-extractable.
- `passphrase` — memorized string. **Policy:** ≥ 16 UTF-8 characters, password-manager-generated. Signing custodians may not use a passphrase that appears in `common_passwords_v1.txt` (§5).
- `argon2_salt` — 32 random bytes per custodian, generated once at provisioning and stored plaintext in the `shard_blob` (§3.2).

Unlock key derivation (every signing event):

```
stretched   = Argon2id( password = passphrase,
                        salt     = argon2_salt,         -- fresh-random per custodian, NOT derived from token
                        m_cost   = 262144,              -- 256 MiB
                        t_cost   = 3,
                        p_cost   = 1,
                        outlen   = 32 )

ikm         = hw_token_secret ∥ stretched               -- two 32-byte values, total 64 bytes

unlock_key  = HKDF-SHA256( ikm   = ikm,
                           info  = "PolyVault v3.2 | UNLOCK | " ∥ uint8(custodian_id),
                           L     = 32 )
```

**Why `argon2_salt` is random, not derived from `hw_token_secret`.** Making the salt independent of the token decouples passphrase rotation from token rotation: a custodian can change their passphrase without re-provisioning the token, and a lost/replaced token does not automatically invalidate a known-good passphrase. Security-wise, the salt adds no hidden entropy (the attacker with the device sees it) but serves its textbook role: it prevents precomputed Argon2id tables across custodians sharing the same passphrase.

**Parameter choice (m=256 MiB, t=3, p=1).** Calibrated to OWASP 2023 guidance (m ≥ 47 MiB) with a 5.4× margin. Desktop/laptop custodian devices (16 GB+) see ~1.5% RAM pressure per unlock — acceptable. **Mobile custodianship is not supported** (6 GB iPhone would see 4% RAM pressure under memory-tight conditions, risking unlock failure). See §13 deployment checklist.

### 3.2 `shard_blob` wire format v1 (98 bytes, fixed) — D3 pinned

```
offset  size  field              value
   0     1    version            0x01
   1     1    kdf_variant        0x02        (Argon2id; 0x01 reserved for scrypt fallback)
   2     2    m_cost_log2_be     0x0012      (18 → 262144 KiB = 256 MiB)
   4     1    t_cost             0x03
   5     1    p_cost             0x01
   6    32    argon2_salt        random per custodian
  38    12    aead_nonce         random per shard write
  50    32    aead_ciphertext    AEAD-Encrypt(unlock_key, aead_nonce, y_i_bytes32, aad)
  82    16    aead_tag           AES-GCM tag (last 16 bytes of Encrypt output)
       ────
       98 bytes total
```

AAD for the AEAD call: `"PolyVault v3.2 | shard | " ∥ uint8(custodian_id)` (no version byte in AAD — the version is already enforced by refusing unknown `version` on parse).

**All implementations MUST emit and parse this exact byte layout.** A parser that accepts a different layout or a different version without explicit migration is a compliance bug.

`duress_blob` (§11.4) uses **the same wire format**, stored at a separate file path on the device, and enrolled with the duress passphrase via the identical pipeline. Observationally indistinguishable from `shard_blob`.

### 3.3 Why the slow KDF matters

Without passphrase stretching, `HKDF(hw_token_secret ∥ passphrase)` runs at roughly `10⁶ ops/s` on one CPU core. A stolen device with the HE decoy layer defeated still lets an adversary who somehow also guesses the token try one passphrase per microsecond — a common 8-character password is enumerable in seconds.

Argon2id at `m=256 MiB, t=3, p=1` drops this to `~1–5 ops/s` on a single modern core. A `≥ 200,000×` economic barrier per guess, with additional hardness against GPU/ASIC offload (memory-hard).

**Simulation S9** (sim uses scrypt `N=2^12` for CI speed, not the production Argon2id): HKDF-only runs at 370,000 ops/s; scrypt+HKDF at 122 ops/s — **3,044× slowdown**. Production Argon2id at the above parameters is meaningfully higher; the deployment-checklist requires a one-time calibration benchmark on the chosen signing hardware.

### 3.4 HKDF input encoding — no concatenation ambiguity

The HKDF IKM is `hw_token_secret (32 B) ∥ stretched (32 B)` = exactly 64 bytes. Both components are fixed-length by construction. No user-controlled variable-length material enters HKDF directly; the passphrase enters only via Argon2id's `password` argument where it is length-prefixed internally by the KDF.

### 3.5 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| `hw_token_secret` non-extractable | Token firmware bug, side channel | Degrades to passphrase-Argon2id-only; still ~10⁻¹⁶ of the unstretched rate |
| Argon2id parameters survive storage | Deployment rolls out with `m=2^10` KiB "for testing" and never upgrades | Per-guess cost drops 250×; detectable via calibration benchmark on first provisioning |
| Passphrase passes ≥ 16-char and not-in-corpus policy | Custodian uses `"password"` | HE decoy (§5) partially mitigates; deployment checklist forbids this at provisioning time |
| Distinct `argon2_salt` per custodian | Deployment bug generates salt from a shared seed | Two custodians with same passphrase derive the same stretched value; loss of isolation |
| Custodian device has ≥ 512 MiB free RAM | Mobile device attempts signing | Argon2id OOMs; signing fails; availability loss. Mitigated by policy: §13 forbids mobile signing |

---

## 4. Layer 2 — AEAD Shard Lock

### 4.1 Construction

AEAD body is AES-256-GCM with:

- `key = unlock_key` (from Layer 1)
- `nonce = random 96-bit` (stored in `shard_blob` per §3.2)
- `aad = "PolyVault v3.2 | shard | " ∥ uint8(custodian_id)`
- `plaintext = y_i` as a 32-byte big-endian scalar mod `n` (secp256k1 curve order)

Wire format is the `shard_blob` layout pinned in §3.2. Nonce is freshly sampled on every write of `shard_blob`; because `unlock_key` rotates whenever `argon2_salt` rotates (i.e., on passphrase change) and whenever the shard is re-encrypted, nonce reuse risk is bounded by one per (unlock_key, nonce) pair.

### 4.2 What the AEAD does for us

Without integrity (AEAD tag), a stolen shard file can be offline-tested against candidate unlock keys with a hash comparison. With AEAD, every wrong key produces an unverifiable ciphertext — there is no side-channel signal distinguishing "wrong key" from "right key but the resulting scalar isn't actually a live share." The attacker must reach a full threshold and test the reconstructed `k*` against the on-chain address to validate a guess.

Simulation **S3** confirms: 200/200 wrong-token unlock attempts fail AEAD verification.

### 4.3 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| AEAD implementation checks tag before returning plaintext | Custom decrypt logs partial plaintext on tag failure | Side channel; catch in code review |
| Nonce uniqueness under same key | Counter reset on device reboot without key rotation | GCM nonce reuse — catastrophic confidentiality failure on *those* ciphertexts; does not leak unlock_key itself but leaks `y_i` |
| AAD binds custodian id | `aad = ""` | A blob swapped between custodians could unlock under different shard context |

---

## 5. Layer 3 — Honey Encryption Passphrase Decoy

### 5.1 Why HE is here, not on the plaintext

HE provides hiding only when the message space has a *known non-uniform distribution*. A uniform 256-bit key has no such structure — wrong-key decryption just produces another uniform 256-bit value, which the adversary tests against the on-chain public key anyway. **Simulation S7** empirically demonstrates this (wrong-key decryption of a uniform-key HE blob is statistically uniform, `p = 0.998`).

Passphrases, in contrast, follow a known distribution (leaked-password corpora, Zipf-style frequency). A passphrase-HE wrapper produces plausible decoys on wrong keys: `"password"`, `"123456"`, `"qwerty"`. **S7-B** shows 89.4% of wrong-key decryptions yield real common passwords under the deployed DTE. An offline attacker who obtains the HE blob but not the hardware token cannot tell when they have guessed correctly.

### 5.2 PassphraseDTE — summary (full spec in `polyvault-dte-spec.md`) — D4 pinned

The full wire-level specification — parameter pinning, corpus hashes, bin-edge derivation, tail generator, encrypt/decrypt, wire format, test vectors — is in the companion document **`polyvault-dte-spec.md`** (v1.0). Implementers MUST read that document before writing any DTE code. Cross-language parity depends on bit-exact compliance with every step.

**Summary of parameters relevant at the architectural level:**

| Parameter | Value | Source |
|---|---|---|
| `N_BINS` | `2^32` | dte-spec §2 |
| `TOP_K` | 1024 | dte-spec §2 |
| Zipf shape `s` | 1.2 | dte-spec §4.1 |
| Common mass fraction | 0.5 | dte-spec §2 |
| Tail generator | 4096-word EFF-large subset × 8 pattern templates | dte-spec §5 |
| PRF | HMAC-SHA256(he_key, "PolyVault DTE v1 \| HE_PASSPHRASE")[:4] as uint32 | dte-spec §7.1 |
| `he_blob` wire format | 22 bytes: version ‖ dte_variant ‖ nonce(12) ‖ ct(4) ‖ reserved(4) | dte-spec §7.4 |

Why HMAC-SHA256 (not SHAKE-256 as in v3.1 draft): 1st-party primitive in every target language stdlib (Rust `hmac`, TypeScript Web Crypto, Python `hmac`). Cross-language parity is simpler to verify.

Why `N = 2^32` (not `2^20`): denser common region reduces adjacent-bin collision risk when the common corpus is refreshed (a slight shift in weights then shifts fewer bin edges). Also moves the tail region into a `2^31`-element space where the algorithmic tail generator has room to produce diverse decoys.

### 5.3 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| `COMMON_LIST` reflects adversary's prior | Adversary has a better password prior than the deployment | Decoys identifiable as "low-probability under adversary's model" |
| Passphrase drawn from `D` | Custodian uses a 40-char random string | HE bucket is `"<tail>"`; all wrong-key decrypts produce `"<tail>"` marker. Acceptable — attacker still can't verify without token. |
| `COMMON_LIST` refreshed periodically | 2020 list used in 2030 | Distribution drift; HE hiding degrades. Runbook §11 schedules 12-month refresh. |

### 5.4 What HE does *not* replace — and its computational-security limits

**HE does not replace the slow KDF (§3).** HE rate-limits attackers who have the HE blob but not the token; slow KDF rate-limits attackers who also have the token. Both are needed in different failure modes.

**HE is not a computational-secrecy primitive.** The PRF uses only 4 bytes of HMAC-SHA256 output (see `polyvault-dte-spec.md` §7.1), so the effective PRF search space is `2^32`. A GPU-equipped adversary can enumerate all `2^32` candidate `prf(he_key) mod N_BINS` values in wall-clock minutes. This is **intentional**: HE provides *distribution-indistinguishability* (every guess yields a plausible passphrase), not brute-force hardness.

The correct reading of HE's security contribution:

- **What HE gives:** no decryption oracle. An offline attacker with the `he_blob` but without the hardware token sees only a stream of plausible common-password decoys; there is no way to tell which guess corresponds to the real passphrase without also reaching Layer 2 (AEAD shard lock) and Layer 4 (Shamir threshold).
- **What HE does NOT give:** per-guess computational cost. Each HE decryption is one HMAC-SHA256 call (microseconds). The only computational barrier in the custodian-auth path is Argon2id (Layer 1), which charges ~100 ms per guess with production parameters.

Do not read "HMAC-SHA256 PRF → 256-bit security" into this primitive. The 4-byte truncation is deliberate and the security argument is distributional, not computational.

---

## 6. Layer 4 — Shamir Threshold over secp256k1 `F_n`

### 6.1 Construction

Master scalar `k* ∈ F_n`, where `n` is the secp256k1 curve order (the group of valid signing scalars). Polynomial `f(x) = k* + a₁x + a₂x² mod n` for `(t, n_shards) = (3, 5)`; shards `y_i = f(i) mod n`.

`k*` reconstruction via Lagrange at `x = 0`:

```
k* = Σ  y_i · Π  (-j) / (i-j)   mod n
     i∈Ω   j∈Ω, j≠i
```

for any `|Ω| ≥ t`.

Working in `F_n` (rather than, say, `F_p` for some general prime) means the reconstructed scalar is immediately usable for ECDSA signing without modular-reduction adaptation.

### 6.2 Information-theoretic property

For any observed `|Ω| < t` shards, every `σ ∈ F_n` is equally consistent with the observations. The posterior equals the prior; `I(k* ; {y_i}) = 0`.

**Sanity check (S2), not a novel verification.** The simulation picks 100 random `σ ∈ F_n` and solves the `2×2` Vandermonde-minor system for the matching `(a₁, a₂)`. Every candidate admits a unique valid polynomial completion. This restates Shamir (1979) on concrete inputs — its value is catching implementation bugs (wrong modulus, wrong Lagrange formula), not verifying the theorem.

### 6.3 DKG — tiered procedure (D2 pinned)

The project commits to a tiered DKG roadmap. The tier active at any time depends on protocol AUM and engineering readiness.

| Tier | Active when | Procedure | Dealer trust assumption |
|---|---|---|---|
| **Phase 1** | AUM < $10M, or during first 6 months of production | **Air-gapped trusted-dealer ceremony** with witnesses. Full runbook in `polyvault-ceremony-runbook.md`. | Dealer + ≥ 2 witnesses honest during the ≤ 2-hour ceremony |
| **Phase 2** | AUM ≥ $10M, or after Phase 1 term | HSM-internal generation via PKCS#11 with vendor Shamir extension. Two HSMs from different vendors; compare outputs for sanity (operational-integrity cross-check, not cryptographic). | HSM vendor + admin-role holder honest |
| **Phase 3** | AUM ≥ $100M, or when audited TSS tooling is production-ready | **Pedersen DKG** via a vetted TSS library (FROST for Schnorr; GG20/CMP21 for ECDSA). No single party knows `k*` at any point. | Up to `t−1` participants malicious tolerated |

**Phase 1 ceremony invariants** (enforced in the runbook):

- Airgapped laptop booted from a signed, reproducible live image (Tails-based custom).
- Physical TRNG (OneRNG or FST-01) contributes entropy alongside `/dev/urandom`.
- At least two custodians witness the ceremony in person; ceremony is video-recorded from two angles.
- Polynomial coefficients and shards are output as QR codes on paper; never touch a network interface.
- Shards are distributed to custodians in tamper-evident envelopes.
- Dealer device: storage physically destroyed in view of witnesses at ceremony close; destruction certificate signed by all witnesses.
- **Feldman VSS commitments** are emitted by default in v3.2 Phase 1 (see next paragraph).
- Transcript (not including secret material) is signed by all witnesses and pinned in governance.

**Feldman VSS in Phase 1.** The dealer emits public commitments `C_j = G · a_j` for every polynomial coefficient (including `C_0 = G · k*`). Commitments are pinned in the ceremony transcript. Each custodian independently verifies `G · y_i == Σ i^j · C_j` on their own device; no `k*` reconstruction on a shared machine is needed for post-ceremony consistency checking. `C_0` also lets governance verify that the ceremony produced the key whose on-chain owner address was pre-registered. Discrete-log hardness of secp256k1 ensures the commitments leak nothing about `k*`. This is what v3.1 called "Option B"; in v3.2 it is default for Phase 1 and required for Phase 2/3 as well. Ceremony runbook §3.3a gives the wire-level procedure.

**Transition Phase 1 → Phase 2** is itself a ceremony: regenerate `k*` inside Phase 2 HSMs, re-Shamir, redistribute new shards, on-chain rotate to the new address, destroy Phase 1 shards under witness. The old `k*` must not be imported into the new HSMs (treat Phase 2 as a fresh start).

**Transition Phase 2 → Phase 3** is again a fresh-start rotation; no key material migrates across phases.

**Rationale for tiering.** Starting at Phase 2 is appealing but unrealistic: cloud HSM onboarding requires KYC, contracts, and testing that cannot complete in the initial production window. An air-gapped Phase 1 ceremony delivers meaningful protection in week one; waiting for HSMs would either delay production or force an insecure interim. Phase 3 (full DKG) is strongly recommended long-term but current TSS tooling for ECDSA requires careful integration and audit; rushing into it is worse than a well-run Phase 2.

### 6.4 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| Coefficients fresh per split | PRG reuse across keygen ceremonies | Correlation across master keys — a governance-visible risk, not a silent break |
| Shards on genuinely separate devices | Two custodians outsource to same MPC provider / same cloud account | Effective `t` drops; could reach 1 if all "independent" shards live on one provider |
| Reconstruction environment trusted | Signing happens on an internet-connected laptop with screen-share | `k*` exfiltration during the ~25-ms reconstruction window |
| Modulus is `n` (prime) | Someone "optimizes" with a non-prime field | Lagrange inverse undefined on some denominators; silent bias |

---

## 7. Layer 5 — Dual AEAD Cold Backup

### 7.1 Construction and storage topology (D1 pinned)

Encryption (performed once at Phase-transition ceremony; re-performed only on rotation):

```
k_inner, k_outer  ←  two independent 256-bit keys (separate os.urandom calls,
                     generated INSIDE the respective HSM, never imported)
C_inner = AES-256-GCM( k_inner, nonce_i, aad = "cold | v3.2 | inner", k* )
C_outer = AES-256-GCM( k_outer, nonce_o, aad = "cold | v3.2 | outer", C_inner )
```

**Pinned storage topology — three facilities:**

| Facility | Vendor / controller | Access policy | Contents |
|---|---|---|---|
| **A** | HSM Vendor 1 (recommended: AWS CloudHSM, us-east-1) | IAM root role held by **Custodian #1**, in the legal entity's operational account; break-glass requires 2-of-N legal-entity sign-off | `k_inner` (32 bytes; generated inside HSM, never extracted) |
| **B** | HSM Vendor 2 (recommended: GCP Cloud KMS, europe-west) — geographically and organizationally distinct from A | IAM root role held by **Custodian #2**; break-glass same policy | `k_outer` (32 bytes; generated inside HSM, never extracted) |
| **C** | Governance-multisig-controlled cold storage | **Primary:** private S3 bucket under a separate legal entity (a Dol-subsidiary foundation or similar), bucket policy requires 2-of-N governance-multisig approval to GET. **Mirror:** Arweave permanent-storage upload under same signing policy. NOT IPFS public. | `C_outer` (ciphertext, sensitive-opaque only) |

Recovery requires:

1. Fetch `C_outer` from Facility C (needs 2-of-N governance approval).
2. Invoke Facility B's HSM to strip outer AEAD (needs Custodian #2 + break-glass).
3. Invoke Facility A's HSM to strip inner AEAD (needs Custodian #1 + break-glass).
4. `k*` surfaces only inside Facility A's HSM session.

Any one facility breach yields ≤ 1 of 3 components; any two-facility breach yields ≤ 2 of 3; **all three facilities** are required to reach plaintext `k*`.

### 7.2 Why no IPFS-public pin

A natural cheaper design is to pin `C_outer` on IPFS publicly. This was considered and rejected:

- IPFS publication is effectively permanent (content-addressed blocks propagate across pinners).
- In the 2040 quantum-break scenario where `k_inner` and `k_outer` are exfiltrated from HSMs via future attacks, a public `C_outer` means any historian with the leaked keys can reach `k*`. We cannot revoke a public IPFS pin.
- A private S3 + Arweave with 2-of-N governance gating preserves the availability guarantee (Arweave is permanent storage) while keeping access-control revocable at the governance level.

### 7.3 Why three facilities, not two

If `C_outer` lives in Facility A alongside `k_inner`, A can strip the outer layer locally, reducing the system to "adversary needs A plus one of {B, leaker of k_outer}" — a two-party condition. Separating the ciphertext into its own facility C restores the property that *no two-facility collusion* yields plaintext and forces a three-way breach.

### 7.4 Algorithm choice — honesty about AES×AES

The engineering motivation for dual encryption is **algorithm diversity**: pair a code-based cipher with a lattice-based cipher so a break in one hardness assumption (syndrome decoding, module-LWE) does not break the other. **Production choice (mandatory at Phase 2 transition):** `E_inner =` Classic McEliece-8192, `E_outer =` ML-KEM-1024 with AES-256-GCM as DEM. AES×AES is not acceptable for production cold backup.

Phase 1 (air-gapped ceremony era) MAY use AES×AES as a bootstrap if KEM tooling inside the air-gapped environment is unavailable. This is a documented exception, time-boxed to the Phase 1 → Phase 2 transition window (6 months maximum). The simulation uses AES×AES and demonstrates only the *compositional* structure (IND-CCA2 composes); it does not demonstrate algorithm diversity.

### 7.5 Composition theorem (inlined)

If `E_inner` and `E_outer` are IND-CCA2 with adversary advantages `Adv_inner, Adv_outer`, and keys are independent, the nested composition is IND-CCA2 with `Adv_nested(A) ≤ Adv_inner + Adv_outer`. The proof is a three-hybrid argument: replace `E_inner` output with encryption of a dummy (charged to `Adv_inner`), then replace `E_outer` output similarly (charged to `Adv_outer`). Standard hybrid.

### 7.6 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| Facilities A, B, C physically and administratively distinct | Same logistics provider / same cloud provider at organization level | Single-provider breach yields two of three components |
| `k_inner ⊥ k_outer` | Generated in same ceremony with shared DRBG bug | Composition advantage collapses to `max(Adv_inner, Adv_outer)` |
| Keys generated INSIDE HSMs, never exported | Operator exports k_inner during troubleshooting | Exported material is now on a general-purpose machine; HSM boundary lost |
| Algorithm diversity in production | Team extends Phase-1 AES×AES bootstrap indefinitely | Any AES advance breaks both layers at once; §11 rotation schedule forces the issue |
| AEAD tag verified before plaintext surfaces | Custom decryptor logs on tag-fail | Side channel |
| Facility-C access gate enforced | Governance-multisig policy misconfigured as single-signer | `C_outer` leakable by one party |

### 7.7 On-chain PQ asymmetry — an explicit scope limit

The cold-backup construction (§7.1) is specifically designed to be post-quantum for the Phase-2+ algorithm-diverse McEliece ∘ ML-KEM variant. This matters because cold-backup ciphertexts persist for years and may be present in archives that future adversaries can read.

**However, the on-chain signing key itself remains classical.** The `k*` used for EVM transaction signing is a secp256k1 scalar, and secp256k1 ECDSA is not post-quantum: a sufficiently capable quantum adversary can recover the private key from any on-chain signature using Shor's algorithm. This is a property of the **chain**, not of PolyVault.

The asymmetry is intentional and must be clearly documented:

- **PolyVault's PQ protection applies to:** (1) cold-backup ciphertexts, which are opaque byte-strings held offline, and (2) the audit trail (§8), which is SPHINCS+-signed and therefore hash-based.
- **PolyVault's PQ protection does NOT apply to:** the on-chain signing operation. Once `k*` signs a transaction and the signature appears on-chain, a quantum adversary with access to that signature and the public key can recover `k*`.
- **The only defense for hot signing against quantum attack is chain migration.** EVM does not currently support PQ signature verification; when it does (e.g., via a precompile or an L2 with PQ-native signatures), Dol must migrate. Until then, the residual risk is bounded by two factors: (a) current quantum capability is far below what Shor's algorithm on secp256k1 requires; (b) a compromise of `k*` via quantum attack would be detectable at the on-chain transaction level (any attacker-forged transaction would trigger the audit/pause infrastructure of §8, §11.3).

The deployment checklist (§13.6) requires a filed chain-migration plan. The research roadmap outside this document discusses PQ-native chains and how the Dol treasury would migrate.

---

## 8. Layer 6 — Audit Signature

### 8.1 Construction

Every signing event produces an audit record:

```
event = "signed | " ∥ SHA256(tx_bytes) ∥ " | custodians=" ∥ sorted_ids ∥ " | ts=" ∥ unix_time
audit_sig = SPHINCS+-256s.Sign( audit_sk, event )
append_to_log(event, audit_sig)
```

### 8.2 Why a hash-based signature (inlined)

SPHINCS+ security reduces to the collision/second-preimage/preimage resistance of the underlying hash (SHAKE-256 for `-256s`). Formally, `Adv_SIG^EUF-CMA(A) ≤ q_s · Adv_H^{PRE+SPR+CR}(B) + negl(λ)` for `q_s` signing queries. The reduction is given in the SPHINCS+ submission (Bernstein et al., 2019) with a machine-checked version in the artifact.

This matters for DeFi governance: audit logs must remain forgery-resistant after the chain's signing curve (secp256k1 today) eventually falls to quantum attack. SPHINCS+ relies only on hash security, which degrades gracefully under quantum (Grover gives at most quadratic speedup, doubled hash output restores the margin).

The simulation uses **Lamport OTS** (one key pair per test event) to demonstrate structure. The production path is a library swap for SPHINCS+-256s; the security argument above applies to the production primitive, not the Lamport stand-in.

### 8.3 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| OTS slots not reused (SPHINCS+ hypertree invariant) | State corruption causes signature reuse | EUF-CMA degrades rapidly after even one reuse |
| `audit_sk` kept offline between events | Signing key held on network-connected server | Compromise of that server forges arbitrary future log entries; past entries remain sound |
| Hash collision-resistance at `λ` bits | Advance in hash cryptanalysis | Linear impact; rotate to larger parameter set |

---

## 9. Composition and Independence

### 9.1 Independence property

For any two layer keys `k_a, k_b` in the stack: `I(k_a; k_b) = 0`.

### 9.2 Engineering rules that achieve independence (review finding R3)

1. **Single kernel-backed DRBG.** All keys from `os.urandom` (Linux `getrandom(2)` / macOS `getentropy`). No application-level PRNG for key material.
2. **No reseed.** Never write to the kernel entropy pool; never reseed libsodium/pycryptodome internal generators; never enable "deterministic mode" flags outside tests.
3. **Zeroization between layers.** After each keygen, zero the transient buffer. Enforceable in Rust/C; best-effort in Python (sim documents intent).
4. **Domain-separated KDF info strings.** Every HKDF call includes a unique `info` with a version prefix: `"PolyVault v3.2 | UNLOCK | <id>"`, `"PolyVault v3.2 | HE_KEY | <id>"`, `"PolyVault v3.2 | COLD | inner"`, etc. Two layers never compute the same HKDF output.

**Simulation S4**: 5,000 samples of 5-layer key tuples via `os.urandom`. Worst-pair Pearson `|r| = 0.016`; all pairs `|r| < 0.05`; chi-squared uniformity per layer `p > 0.001`. This detects a broken DRBG, not a subtle covert channel; it is necessary but not sufficient.

### 9.3 Failure modes for the independence assumption (inlined)

| Failure | Concrete mechanism | Severity |
|---|---|---|
| Common DRBG seed reused across reboots | VM cloned with entropy pool; both clones generate identical first-key sequence | Catastrophic — two layers' keys are bit-identical |
| Side channel observing multiple layers | Cache timing during keygen leaks partial info on every key generated in that epoch | Reduces each `Adv_i` uniformly; union bound still holds with worse `negl_i` |
| Shared TEE holds multiple layer roots | One enclave stores `k_inner, k_outer, DKG-seed`; TEE bypass surfaces all | Collapses three layers into one break event |
| AES-GCM nonce collision across layers | Both DEMs derive nonces from a shared counter | Breaks IND-CCA2 of the colliding layer |
| Hash cryptanalysis advance | SHA-256 collisions feasible → affects SPHINCS+ *and* every KDF | Layers move together; break events cease independent |

When an independence failure is suspected, rotate *all* downstream key material, not only the affected layer (§11.4).

### 9.4 Union bound

Define `B_i` = "layer `i` broken". When `{B_i}` lie on independent probability spaces:

```
Pr[system broken] = Pr[⋃ B_i]  ≤  Σ Pr[B_i]  ≤  Σ negl_i(λ)  =  negl(λ)
```

At `λ = 256`, even `6 · 2^{-256}` is well below any operational risk threshold. The bound is loose by `Σ_{i<j} Pr[B_i]·Pr[B_j]`, which is doubly negligible.

### 9.5 Degraded-security table

| Layer broken | Remaining guarantee |
|---|---|
| One custodian's AEAD lock bypassed (L2) | Shamir threshold still requires `t−1` more (L4) |
| One custodian's HE passphrase decoy defeated (L3) | Slow-KDF + token (L1) still gates the unlock |
| One custodian fully compromised (L1+L2+L3) | Shamir threshold holds (L4) |
| `t−1` custodians fully compromised | Threshold holds — need one more; cold backup (L5) still encrypted |
| `t` custodians compromised → `k*` recovered | On-chain rotation via governance is the only remaining defense; audit log (L6) still sound for post-mortem |
| Cold `k_inner` leaked (one of three facilities) | Cold `k_outer` + `C_outer` still needed; two-facility defense remains |
| Cold `k_inner` + `k_outer` leaked (two of three) | `C_outer` still needed (third facility); in the limit this degrades to single-facility-breach protection |
| All three cold facilities breached | Plaintext `k*` recoverable; audit log remains forensic evidence |
| SPHINCS+ audit key leaked | Historical log cryptographically sound; future entries forgeable — rotate audit key |

---

## 10. Measurement notes (review finding 8)

Simulation timings (S8):

- Provisioning (5 custodians, scrypt `N=2^12`, audit keygen): **40.8 ms**
- Signing: unlock 3 custodians (3× scrypt) + Lagrange at `F_n` + Lamport audit-sign: **24.5 ms**

These numbers are **single-core cryptographic time, excluding custodian-to-custodian coordination.** Real DeFi signing latency is dominated by:

- Governance workflow (proposal, review, vote): minutes to hours.
- Custodian-to-custodian network round-trips (async signal, manual approval): seconds to minutes.
- Cold-path ops (cold backup read): minutes.

The simulation's sub-second numbers establish only that the **cryptography** is not the bottleneck. Wall-clock for a real threshold signing event is realistically **1–5 seconds** for a hot, pre-authorized event with online custodians, and **minutes to hours** for a governance-gated event.

A further qualification: production parameters (scrypt `N=2^15` or Argon2id `m=64 MiB`) multiply the per-unlock cost by `8–64×`, pushing single-core signing toward `100–200 ms` per custodian's unlock. This is still an acceptable fraction of wall-clock.

---

## 11. Operational Runbook

### 11.1 Rotation schedule

| Material | Routine | Trigger-based |
|---|---|---|
| `k*` (master) | Annual on-chain rotation via governance | ≥ 2 custodian compromise; any cold backup compromise |
| Shamir shards (same `k*`, new polynomial = PSS) | Quarterly | Single-custodian device loss without evidence of compromise |
| `hw_token_secret` | When token replaced | Token firmware advisory; device loss |
| `passphrase` | 6 months | Custodian believes it may have been observed |
| Cold `(k_inner, k_outer)` | 2 years | Suspected facility compromise |
| Audit SPHINCS+ key | Per parameter-set budget; conservatively annual | Any suspected signing-environment compromise |
| HE `COMMON_LIST` / `D` | 12 months | Notable new password-leak corpus released |

### 11.2 Device-loss decision tree (answer to R1)

```
Is there evidence the device was accessed?
├─ NO    → Proactive Secret Sharing: new polynomial, same k*.
│         Fast, no on-chain change. Works only if the lost device is
│         demonstrably dormant forever (destruction proof).
│
└─ YES   → Full rotation: new k*_new, reshare, on-chain owner migration.
          Slow (governance vote) but definitively revokes the old material.
```

Both paths are simulation-verified:

- **S5 (PSS):** new polynomial with `f'(0) = k*` keeps the master; all 5 shards change. Old shards still reconstruct `k*` (they lie on the old polynomial), so **PSS is not revocation — it is device-level rotation on top of a stable master.** Until every old shard is physically destroyed or the device wiped under attestation, the old shards remain live.
- **S6 (full rotation):** fresh `k*_new ≠ k*_old`, fresh polynomial. Old shards reconstruct only `k*_old`, which is no longer the on-chain owner. Definitive.

**DeFi default: full rotation.** PSS is appropriate only when the lost device is demonstrably unrecoverable *and* full rotation's governance cost is genuinely prohibitive. For most protocols, a governance vote is cheaper than maintaining the "is the dormant shard really dormant" uncertainty.

### 11.3 Incident triage

| Indicator | First-hour action |
|---|---|
| One custodian reports device theft | Suspend that custodian's signing rights via governance timelock; do not rotate yet (await investigation) |
| Two custodians report theft within 24 h | Treat as coordinated: full rotation; audit logs for recent signings |
| Unusual on-chain signing (nonce gap, unexpected destination) | Halt treasury via emergency pause contract; verify audit log (L6); force rotation |
| HE distribution `D` shifts substantially | Non-urgent re-wrap; schedule within 30 days |
| CI independence test (S4) fails | Block all keygen. Rotate all keys generated in suspect window. |

### 11.4 Duress passphrase — layered defense

A single duress design is not sufficient; the two designs below address complementary adversary models and **both must be deployed** in any production release.

#### 11.4.1 Attacker model

A coercer forces a custodian to execute a signing. The coercer's goal is to cause a valid on-chain transaction to be broadcast. The custodian's goal is to appear compliant while producing output that fails. The adversary's observation surface includes: (a) the signing UI shown on the custodian's device, (b) the transaction broadcast and its on-chain result, (c) the coerced custodian's behavior under continued threat.

A duress design is *effective* only if the coercer cannot easily distinguish a real signing from a duress signing within the time they retain leverage over the custodian. "Transaction submission fails deterministically" is a correct defensive property but is visible to the coercer; a sophisticated adversary waits for broadcast confirmation and escalates on failure.

#### 11.4.2 Design A — On-device canary (required)

Each custodian enrolls a second passphrase `pw_duress`. On the device, `pw_duress` decrypts via the same Layer 1 pipeline but unlocks a **canary blob** whose plaintext is a constant value (`0xFF^32`). This canary is a valid `F_n` scalar but **not on the real polynomial**, so threshold reconstruction that includes it yields `k_recovered ≠ k*`.

**Storage.** Each custodian stores `shard_blob` and `duress_blob`, both AEAD-encrypted in the same wire format (§3.2). The unlock pipeline tries `shard_blob` first, falls back to `duress_blob` on AEAD failure. The two code paths are observationally indistinguishable to the coercer.

**Simulation S10** verifies: 1, 2, or 3 coerced custodians all produce `k_recovered ≠ k*`; with three duress passphrases the Lagrange reconstruction of the constant function at every `x` yields that constant, which is trivially not the on-chain owner.

**Limitation.** Design A alone protects only until broadcast. A coercer who watches the mempool / block explorer sees the invalid signature. Design A must be paired with Design B (below) to cover the broadcast-observation case.

#### 11.4.3 Design B — Orchestrator-side fake-success UX (required where network is available)

When `pw_duress` is entered on a networked custodian device, the client emits a signed duress flag to the Dol orchestrator. The orchestrator then:

1. **Suppresses the real on-chain broadcast.** The transaction never leaves the orchestrator.
2. **Synthesizes a fake success receipt for the coerced UI.** The custodian's device shows a transaction-accepted modal with a plausible transaction hash (a value indistinguishable from a real hash but not corresponding to any actual chain event). The UI also shows a fake block-explorer link whose target is a server-controlled static page that displays the fake transaction as "pending → confirmed" for as long as the coerced session is active.
3. **Locks out the custodian's device for the duress-active window** (default 72 h): subsequent signing attempts from that device also route through the fake UX.
4. **Triggers emergency governance revocation** out-of-band: pauses the on-chain emergency-pause contract (§13.6), notifies other custodians via side-channels, rotates `k*`.

The fake-success UX is the point of Design B. Without it, a coercer watching the chain detects the absence of the broadcast and escalates. With it, the coercer observes what looks like a successful signing for hours; by the time they realize otherwise, the custodian is physically safe and the key has been rotated.

**Failure mode.** If the device is offline when duress is entered, Design B is silent and the attacker sees only Design A's failed-broadcast outcome. Mitigation: (a) provisioning policy requires custodian devices to be online whenever signing is permitted (no offline signing for DeFi treasury); (b) if a signing request originates from an offline device, the orchestrator displays the fake-success UX *speculatively* on the next reachable custodian device to buy time.

#### 11.4.4 Mixed duress + real passphrase reconstruction

An attacker may coerce a subset of custodians while others cooperate normally. The space of outcomes is:

| Real shares | Duress (canary) shares | Reconstruction outcome |
|---|---|---|
| 3 | 0 | `k_recovered = k*` — legitimate signing path |
| 2 | 1 | `k_recovered ≠ k*` — poisoned; signature fails (Design A behavior) |
| 1 | 2 | `k_recovered ≠ k*` — poisoned |
| 0 | 3 | `k_recovered` = canary constant (`0xFF^32 mod n`) — poisoned; trivially wrong |

**3 real + 0 duress means legitimate recovery.** This is by design: a full quorum of legitimately-authorized custodians must always be able to sign. If the attacker coerces only 1 custodian out of 5 (holds their duress passphrase), they need 2 more *real* shares to reach `t=3`. If they have those real shares from physical device theft plus the coerced duress, reconstruction is 2 real + 1 duress → poisoned. If they have 3 real shares (threshold reached without any duress input), they do not need the coerced custodian at all.

**The duress design does not prevent `t` colluding or compromised custodians from signing** (threshold is by design). It protects against the specific scenario: coercer has `≥ 1` custodian under duress but not `t` full custodian compromises.

**Combinatorial adversary strategy.** From `{3 real + 1 duress}` a coercer who possesses all 4 shares can choose any 3-subset. Of `C(4,3)=4` subsets, one (`{real,real,real}`) recovers `k*`, three include the duress share. If the coercer does not know which share is duress (true if the custodian does not signal which passphrase they provided), they must try all 4 subsets in expectation; each wrong reconstruction is a failed signature, which Design B's fake-success UX still masks. If the coercer *does* know which share is duress (custodian told them under further threat), Design A alone is insufficient and the full `k*` recovery proceeds — at which point Design B's orchestrator-side revocation (triggered by the duress flag already emitted) is the remaining defense.

This scenario — coercer accumulating real shares from physical theft while coercing duress from a surviving custodian — is the apex case of §9.2-S8 in the original threat model. Defense is Design B's orchestrator revocation combined with on-chain emergency pause.

#### 11.4.5 Required deployment posture

- **Design A (canary):** required on every custodian device. No exceptions.
- **Design B (orchestrator fake UX + revocation):** required wherever the custodian device has network connectivity. For air-gapped custodian devices, operator signs off on the residual risk in the deployment checklist.
- **Duress flag transmission** (custodian → orchestrator): signed with a custodian-specific key derived separately from the unlock pipeline so that a device compromise does not also forge duress flags.
- **Out-of-band custodian alerts**: on duress flag receipt, orchestrator notifies other custodians via two pre-agreed side channels (e.g., encrypted messaging + phone call) so that surviving custodians learn of the event independent of the attacker's device.

### 11.5 When independence failure is detected

If a CI independence test (S4) fails:

1. Pause all keygen. No new keys generated until root cause is identified.
2. Enumerate every key generated in the suspect window (from CI red to detection).
3. Rotate each such key — this includes shards, cold backup keys, audit key. The union bound no longer holds on correlated break events, so assume any correlated pair is fully compromised.
4. Post-mortem must identify whether the correlation was from a DRBG fault, a shared memory channel, a shared TEE flaw, or a library upgrade changing entropy handling. File the cause in §13.

---

## 12. Upgrade path to threshold signing (no reconstruction)

Shamir-reconstruct has a `~25 ms` critical section where `k*` exists in one process's memory (S8 timing). An adversary with root on that machine during that window can exfiltrate `k*`.

The production upgrade is a threshold signature scheme that never materializes `k*`:

| Signature scheme | Threshold protocol | Rounds | Library |
|---|---|---|---|
| ECDSA secp256k1 (EVM) | GG18 / GG20 / CMP21 | 5–7 | `ing-bank/zkkrypto`, `ZenGo/multi-party-ecdsa` |
| Schnorr (Tapscript, Solana) | FROST | 2 | `ZfndCrypto/frost`, `taurushq/tss-lib` |
| BLS (Ethereum consensus) | BLS threshold | 1 (non-interactive signing) | `blst`, `herumi/bls` |

Layers 1, 2, 3, 5, 6 (custodian auth, AEAD, HE, cold backup, audit) remain unchanged — they protect the *shards of the TSS private share*, not the reconstructed key. Layer 4 (Shamir) is replaced by "TSS private share distribution via DKG." Layer 5 (cold backup) can remain a Shamir share of `k*` that is never reconstructed on the hot path, used only for catastrophic recovery.

---

## 13. Deployment Checklist

Pre-production gate. Each item maps to a section. Each is a hard block; no "will do after launch."

### 13.1 Cryptographic configuration (D3)

- [ ] Argon2id params match §3.1 exactly: `m_cost=262144, t_cost=3, p_cost=1, outlen=32`. Recorded in a code-level constant, not a runtime config.
- [ ] `argon2_salt` is 32 random bytes per custodian, generated once at provisioning, stored plaintext in `shard_blob`.
- [ ] `shard_blob` wire format v1 (§3.2) implemented byte-for-byte; conformance test added to CI that emits a blob from known `(token, passphrase, salt)` and byte-compares.
- [ ] HKDF info string uses `"PolyVault v3.2 | UNLOCK | "` prefix with `uint8(custodian_id)` suffix. (Mirror strings in §9.2.)
- [ ] Argon2id calibration benchmark run on each signer-device model, recorded in ops docs; refuse to provision a device whose per-unlock time is < 100 ms.

### 13.2 HE / DTE (D4)

- [ ] `common_passwords_v1.txt` loaded, SHA-256 matches the pinned hash in `polyvault-dte-spec.md` §3.2.
- [ ] `wordlist_v1.txt` loaded, SHA-256 matches the pinned hash in §5.1 of dte-spec.
- [ ] `he_blob` 22-byte wire format (§5.2, dte-spec §7.4) matches DTE conformance test vectors.
- [ ] Passphrase policy enforced at provisioning: ≥ 16 UTF-8 chars AND not present in `common_passwords_v1.txt`.
- [ ] Annual corpus-refresh calendar event on file.

### 13.3 Shamir + DKG (D2)

- [ ] `(t, n)` chosen with explicit governance justification (§6). Default `(3, 5)`; `(4, 7)` for AUM > $100M.
- [ ] Custodians on physically and organizationally separated hardware (§6.4) — audit evidence that no two shards share a managing party / cloud account.
- [ ] DKG phase selected (Phase 1 / 2 / 3) and documented with the AUM and readiness criteria that justify it (§6.3).
- [ ] **Phase 1 only:** ceremony executed per `polyvault-ceremony-runbook.md`; transcript signed by all witnesses and pinned in governance; dealer device destruction certificate filed.
- [ ] **Phase 2 only:** HSM vendor contracts in place; per-HSM attestation of internal keygen captured at provisioning.
- [ ] **Phase 3 only:** TSS library pinned at an audited commit; DKG transcript archive in append-only storage.

### 13.4 Cold backup (D1)

- [ ] Facility A: HSM Vendor 1 contract active, `k_inner` generated **inside** HSM, IAM root role held by Custodian #1, break-glass requires 2-of-N legal-entity sign-off. No export policy ever enabled.
- [ ] Facility B: HSM Vendor 2 (different vendor and region from A), `k_outer` generated inside HSM. Same policy structure.
- [ ] Facility C: `C_outer` stored in private S3 under a separate legal entity, bucket policy requires 2-of-N governance signers. Arweave mirror uploaded under same policy. **No IPFS-public pin anywhere.**
- [ ] Algorithm diversity: **Phase 2 onwards,** `E_inner = McEliece-8192, E_outer = ML-KEM-1024`. Phase-1 AES×AES bootstrap exemption is logged with an expiry date ≤ 6 months from Phase-1 launch.
- [ ] Annual break-glass drill on file (the team has successfully executed a recovery-read at least once in the past 12 months on a non-production ciphertext).

### 13.5 Hardware & policy

- [ ] `hw_token_secret` in attested hardware; no software-token fallback.
- [ ] **Mobile signing forbidden.** Custodian signing devices are desktop or laptop with ≥ 8 GiB RAM free at signing time.
- [ ] Duress Design A (on-device canary) enrolled per custodian (§11.4.2) — **required**.
- [ ] Duress Design B (orchestrator-side fake-success UX) wired for every networked custodian device (§11.4.3) — required where network is available.
- [ ] Duress-flag signing key provisioned separately from unlock pipeline (§11.4.5).
- [ ] Two pre-agreed out-of-band alert channels for duress events (§11.4.5).
- [ ] Signing-environment policy: no screen-share, no accessibility services, no unattended reboot during ceremony-open intervals.

### 13.6 Legal and jurisdictional

- [ ] Legal review completed for every operational jurisdiction confirming that non-escrow threshold custody is permitted (some jurisdictions require law-enforcement escrow for cryptographic key material).
- [ ] Governance multi-sig signers' jurisdictional mix reviewed so no single-jurisdiction order can compel access to `C_outer`.
- [ ] HSM vendor contracts reviewed for jurisdictional-disclosure clauses (e.g., subpoena response without customer notification) — flag and mitigate where incompatible.
- [ ] Corpus source for PassphraseDTE (`polyvault-dte-spec.md` §12) reviewed for IP and ethics posture in each operational jurisdiction.

### 13.7 CI and operational invariants

- [ ] Independence CI test (S4) green on every build.
- [ ] Wire-format conformance tests (shard_blob, he_blob, DTE test vectors) green on every build.
- [ ] End-to-end simulation tests (`polyvault_defi_sim.py`, 11+ tests) green on production runtime.
- [ ] Python reference oracle itself externally reviewed (not just the Rust port) — see `polyvault-rust-port-plan.md` §12 for scope.
- [ ] DTE `compute_bin_edges()` monotonicity proof on file (invariant holds for all valid corpus inputs, not just the simulation's).
- [ ] On-chain emergency pause contract deployed and wired to off-chain alert channel.
- [ ] SPHINCS+ audit log in append-only storage; governance verifier operational and public.
- [ ] Runbook with all custodians executed (real ceremony, not dry-run — §6 of runbook); commitment verification completed.
- [ ] Post-quantum upgrade plan filed (chain migration; cold-backup Phase transition).
- [ ] TSS upgrade evaluated; Shamir-reconstruct `~25 ms` window accepted as residual risk, or migration plan active.

---

## 14. Simulation Reference

`polyvault_defi_sim.py` is authoritative for every simulation claim in this document. Most recent run:

| Sim | Property | Result |
|---|---|---|
| S1 | Any 3-of-5 custodians reconstruct and sign | 10/10 combinations passed |
| S2 | `t−1` compromised custodians learn zero bits about `k*` (sanity) | 100/100 random candidate masters consistent |
| S3 | Stolen shard file without token is locked; HE produces plausible decoys | 200/200 wrong-token AEAD failures; 88.3% wrong-HE-key decrypts yield real common passwords |
| S4 | DRBG independence across 5 layers | Worst-pair `\|r\| = 0.016`; all layers uniform `p > 0.001` |
| S5 | PSS preserves `k*` while rotating all shards | 5/5 shards changed; new polynomial recovers same `k*` |
| S6 | Full rotation orphans old material | No cross-recovery between `k_old` and `k_new` |
| S7 | HE useless on uniform keys; essential on passphrase distribution | Uniform-key wrong-decrypt uniform (`p = 0.998`); passphrase wrong-decrypt 89.4% common-password decoys |
| S8 | Cryptographic-path latency (single core, excludes coordination) | Provisioning 40.8 ms; signing 24.5 ms at scrypt `N=2^12` |
| S9 | Slow KDF raises offline brute-force cost | 3,044× slowdown at sim parameters; production `N ≥ 2^15` gives ≥ 20,000× |
| S10 | On-device duress canary poisons reconstruction | `k_recovered ≠ k*` under 1, 2, or 3 duress passphrases |

Reproduce:

```
python3 /Users/heoun/Downloads/polyvault_defi_sim.py
# or
pytest /Users/heoun/Downloads/polyvault_defi_sim.py -v
```

---

## 15. Errata and Verification Log

*Empty template. Monotonically growing — past entries are not edited or removed.*

| Date | Type | Finder | Document / Test | Description | Resolution |
|---|---|---|---|---|---|
| YYYY-MM-DD | errata / finding / false-alarm | — | — | — | — |

**Guidance.**

- `errata` — a document error disproved by independent computation.
- `finding` — a structural issue surfaced during review (ambiguous claim, missing assumption).
- `false-alarm` — a reported issue investigated and found correct. Log anyway.

---

## 16. References

- Bernstein, D. J. et al. (2019). SPHINCS+ — Submission to NIST PQC.
- Canetti, R., Gennaro, R., Goldfeder, S., Makriyannis, N., Peled, U. (2020/2021). UC Non-Interactive, Proactive, Threshold ECDSA with Identifiable Aborts (GG20 / CMP21). *CCS 2020/2021*.
- Classic McEliece team (2022). *Classic McEliece: conservative code-based cryptography* — NIST Round 4.
- Feldman, P. (1987). A Practical Scheme for Non-interactive Verifiable Secret Sharing. *FOCS 1987*.
- Gennaro, R., Jarecki, S., Krawczyk, H., Rabin, T. (1999). Secure Distributed Key Generation for Discrete-Log Based Cryptosystems. *EUROCRYPT 1999*.
- Gennaro, R., Goldfeder, S. (2018). Fast Multiparty Threshold ECDSA with Fast Trustless Setup (GG18). *CCS 2018*.
- Herzberg, A., Jarecki, S., Krawczyk, H., Yung, M. (1995). Proactive Secret Sharing. *CRYPTO 1995*.
- Juels, A., Ristenpart, T. (2014). Honey Encryption. *EUROCRYPT 2014*.
- Kaliski, B. (2000). PKCS #5: Password-Based Cryptography Specification v2.0. *RFC 2898*.
- Komlo, C., Goldberg, I. (2020). FROST: Flexible Round-Optimized Schnorr Threshold Signatures. *SAC 2020*.
- NIST (2024). *FIPS 203: ML-KEM*.
- Percival, C., Josefsson, S. (2016). The scrypt Password-Based Key Derivation Function. *RFC 7914*.
- Biryukov, A., Dinu, D., Khovratovich, D. (2016). Argon2: new generation of memory-hard functions for password hashing and other applications. *EuroS&P 2016*.
- Shamir, A. (1979). How to share a secret. *CACM 22(11)*.

---

*This document is a research engineering specification of the Dol project for DeFi treasury custody. Self-contained at v3.1. Does not constitute a security audit or certification.*
