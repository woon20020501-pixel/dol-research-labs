# PolyVault — Rust Implementation Port Plan

**Target repo:** `github.com/woon20020501-pixel/dol`
**Source of truth:** `polyvault-security-v3.2-defi.md`, `polyvault-dte-spec.md`, `polyvault-ceremony-runbook.md`
**Reference implementation:** `polyvault_defi_sim.py` (Python)

> *Sequenced plan for porting the PolyVault v3.2 custody stack into the Dol Rust runtime. Not code. The code itself is written by the implementation team after operator sign-off on this plan.*

---

## 0. Why a new crate, not an extension of `bot-adapters`

`bot-adapters` is the exchange-facing layer. It holds API credentials (env-var only, by design) and signs requests to venues. PolyVault is orthogonal: it protects the treasury master scalar `k*` from which exchange credentials and on-chain signing keys are derived.

**Decision:** add a new crate `bot-polyvault` at `bot-rs/crates/bot-polyvault/`. Nothing in `bot-adapters` depends on it. Both crates depend on a shared `bot-types` crate (existing).

---

## 1. Crate layout

```
bot-rs/crates/bot-polyvault/
├── Cargo.toml
├── src/
│   ├── lib.rs                # public API surface, feature flags
│   ├── argon2_unlock.rs      # Layer 1: custodian authentication (§3)
│   ├── aead_shard.rs         # Layer 2: shard_blob wire format + AEAD (§4)
│   ├── he.rs                 # Layer 3: HE glue (calls into dte/)
│   ├── dte/                  # Layer 3: DTE wire-level (per polyvault-dte-spec.md)
│   │   ├── mod.rs
│   │   ├── corpus.rs         # loads common_passwords_v1.txt, validates hash
│   │   ├── wordlist.rs       # loads wordlist_v1.txt, validates hash
│   │   ├── bin_edges.rs      # §4.3 edge derivation
│   │   ├── tail_gen.rs       # §5 tail generator
│   │   ├── encode_decode.rs  # §6 encode / decode
│   │   └── wire.rs           # §7 he_blob serialization
│   ├── shamir.rs             # Layer 4: Shamir over secp256k1 F_n
│   ├── cold_backup.rs        # Layer 5: dual AEAD composition, 3-facility refs
│   ├── audit_sig.rs          # Layer 6: SPHINCS+ via `pqcrypto` or fallback
│   ├── duress.rs             # §11.4 canary enrollment + verification logic
│   ├── independence.rs       # §9.2 DRBG independence invariants (CI test)
│   ├── wire_format.rs        # shard_blob v1 byte layout
│   └── conformance.rs        # cross-language test vectors
├── tests/
│   ├── shard_blob_conformance.rs
│   ├── he_blob_conformance.rs
│   ├── end_to_end.rs
│   └── independence.rs
├── data/
│   ├── common_passwords_v1.txt  # hash-pinned; validated at crate init
│   └── wordlist_v1.txt           # hash-pinned
└── benches/
    └── unlock_latency.rs     # Argon2id calibration benchmark
```

**Public API (lib.rs sketch):**

```rust
pub struct Custodian { /* opaque */ }
pub struct Vault { /* opaque */ }

pub fn provision_custodian(
    custodian_id: u8,
    shard_y: [u8; 32],          // from QR code (envelope)
    argon2_salt: [u8; 32],      // from QR code (envelope)
    passphrase: &str,
    hw_token_secret: &[u8; 32],
    duress_passphrase: Option<&str>,
) -> Result<CustodianBlobs, ProvisionError>;

pub fn unlock_share(
    blobs: &CustodianBlobs,
    passphrase: &str,
    hw_token_secret: &[u8; 32],
) -> Result<(u8, [u8; 32]), UnlockError>;

pub fn reconstruct_scalar(
    shares: &[(u8, [u8; 32])],
    threshold: u8,
) -> Result<[u8; 32], ReconstructError>;

// ... plus cold_backup::{encrypt, decrypt}, audit_sig::{sign, verify}, etc.
```

All public functions return a `Result` with an error type that never includes secret material in its Display / Debug impl. This is enforced by a custom `zeroize::Zeroize`-wrapped error constructor.

---

## 2. Dependency pinning

`Cargo.toml` pins crypto dependencies tightly. Upgrading any of these is a v-bump of `bot-polyvault`.

| Dep | Version | Purpose |
|---|---|---|
| `argon2` | 0.5 | KDF. `Argon2id` variant, m=262144 KiB, t=3, p=1. |
| `aes-gcm` | 0.10 | AES-256-GCM AEAD. |
| `hkdf` | 0.12 | HKDF-SHA256 for unlock-key derivation. |
| `hmac` | 0.12 | HMAC-SHA256 for DTE PRF. |
| `sha2` | 0.10 | SHA-256 for corpus / wordlist hash pinning. |
| `k256` | 0.13 | secp256k1 scalar arithmetic over F_n. |
| `zeroize` | 1.7 | Erase transient buffers (critical at §9.2). |
| `subtle` | 2.5 | Constant-time equality (for duress-passphrase check). |
| `pqcrypto-sphincsplus` | 0.7 | SPHINCS+-256s audit signatures. |
| `serde` + `bincode` | — | NOT used for wire formats. We hand-roll byte layouts to match the spec. Serde is acceptable for transcript / log records. |

**Rule:** no `unsafe` in `bot-polyvault` except at FFI boundaries into audited crates. Deny at the crate level: `#![forbid(unsafe_code)]`.

---

## 3. Port sequence

**Sprint length:** 1 week of focused engineering effort unless otherwise noted. The total estimate below assumes one engineer familiar with Rust crypto and the codebase. Double for a cryptographer-unfamiliar engineer or for a formal review gate between sprints.

### Sprint 0 — Python reference oracle review (PREREQUISITE, 1 week)

**Blocks Sprint 1.** The Rust port treats `verification/polyvault_defi_sim.py` as a reference oracle for byte-level conformance. Before any Rust is written, the Python sim itself must be independently reviewed for correctness. A bit-identical Rust port of a wrong Python sim gives bit-identical wrong behavior.

Pre-work items:

- Code review of `polyvault_defi_sim.py` by someone other than its original author. Specific scrutiny targets:
  - `compute_bin_edges()` (DTE): prove that the `max(1, round(prob * N_BINS))` edge-allocation loop preserves strict monotonicity `bin_edges[k+1] > bin_edges[k]` for every well-formed corpus, and that the final snap `bin_edges[TOP_K+1] = N_BINS` cannot shrink any earlier edge. Include the proof (≤ 1 page) as a markdown note in `verification/proofs/bin_edges_monotonic.md`.
  - `stretch_passphrase()`: confirm Argon2id parameters match the main spec (§3.1) byte-for-byte.
  - Wire-format serializers (`serialize_shard_blob`, `serialize_he_blob`): verify against hand-computed expected outputs for at least one vector per function.
  - `sim_S4_drbg_independence`: sample-size statistical justification (5000 samples give what confidence for `|r| < 0.05`?).
- DTE `§9.1` sim-corpus test vectors are pinned at concrete hex values (Sprint 0 verifies the table in the spec matches the sim output on a clean build).
- Pin `polyvault_defi_sim.py` SHA-256 at the reviewed commit and record in `verification/REFERENCE_ORACLE.md`.

Exit criterion: a written review of the Python sim is filed in `verification/proofs/` (or similar), and no issue identified by that review is outstanding.

### Sprint 1 — Foundations and conformance infra (blocked by Sprint 0)

- Scaffold the crate with the layout above.
- Vendor `common_passwords_v1.txt` and `wordlist_v1.txt`. Pin SHA-256 constants.
- Implement `wire_format.rs` (`shard_blob` byte layout) and `dte::wire.rs` (`he_blob` byte layout).
- Write `tests/shard_blob_conformance.rs` and `tests/he_blob_conformance.rs` that parse known vectors emitted by the Python sim. **CI fails if the Rust port produces a different byte layout for identical inputs.**
- `independence.rs` test: generate 5000 samples of 5-layer keys via `OsRng`, run pairwise Pearson on the first byte, require `|r| < 0.05`. This is the Rust equivalent of Python S4.
- **DTE spec §9.2 vector table pinned.** Security Lead selects and pins the production corpus (`common_passwords_v1.txt`). Sprint 1 cannot exit without the production-corpus vector table in DTE spec §9.2 being filled.

Exit criterion: Rust produces byte-identical `shard_blob` and `he_blob` to the Python reference for the full set of conformance vectors (sim-corpus S9.1 AND production-corpus §9.2).

### Sprint 2 — Custodian authentication (Layer 1)

- Implement `argon2_unlock.rs`:
  - `Argon2id` with exactly the pinned params.
  - `hkdf::Hkdf::<sha2::Sha256>` for unlock-key derivation.
  - Refuse to compile if Argon2id params are overridden via feature flags.
- Write `benches/unlock_latency.rs`: measure wall-clock on the developer's laptop. Must be ≥ 100 ms; if less, parameters are wrong (caught at CI with a minimum-time assertion on a known reference machine).
- `provision_custodian` and `unlock_share` functions tested against Python sim outputs.

Exit criterion: provisioning a custodian in Rust and unlocking in Python (or vice versa) round-trips the share correctly.

### Sprint 3 — AEAD shard lock + Shamir (Layers 2 + 4)

- `aead_shard.rs`: Standard AES-256-GCM with AAD as per §4.1. No custom decryptor that logs on tag failure — tag verification is always done via the aes-gcm crate's `decrypt_in_place_detached`.
- `shamir.rs`: Shamir over secp256k1 F_n using `k256::Scalar` arithmetic. Verify against Python sim's Vector A and Vector B.
- End-to-end test: provision 5 custodians, recover with any 3, compare reconstructed scalar across Rust and Python outputs for the same seeds.

Exit criterion: cross-language end-to-end signing reconstruction verified on ≥ 10 random `k*` values.

### Sprint 4 — Honey encryption (Layer 3)

- Port `dte::bin_edges`, `dte::tail_gen`, `dte::encode_decode`, `dte::wire` per `polyvault-dte-spec.md` exactly.
- `tests/he_blob_conformance.rs` grows to include the full test-vector table from the DTE spec §9.1 (once that table is filled at first release).
- Integration test: a custodian's `he_blob` produced in Python is correctly decrypted in Rust (and vice versa) to the same passphrase string.

Exit criterion: bit-identical `he_blob` and tail-generator output across Python and Rust for all test vectors.

### Sprint 5 — Cold backup (Layer 5) and duress (§11.4) — scope-limited to stubs

**Scope in this sprint:** cryptographic logic + trait interface + mock implementations only.
**Out of scope in this sprint:** real HSM integration (AWS CloudHSM / GCP KMS) — tracked as a separate deliverable per §3a below.

- `cold_backup.rs`:
  - Phase-1 AES×AES implementation (bootstrap).
  - Phase-2 trait interface for `McElieceWrapper` and `MlKemWrapper`; initial stubs, to be replaced when PQ crates are selected. This keeps the crate compilable pre-PQ while forcing the layered interface.
  - **Important:** this crate does NOT hold cold-backup keys. It only holds the encryption/decryption logic. Key fetching is delegated to a pluggable `ColdKeySource` trait; implementations live in separate crates (see §3a).
- `duress.rs`:
  - Design A (on-device canary) per §11.4.2: duress-passphrase enrollment creates a second `shard_blob`-format file with the canary plaintext `0xFF * 32`. Unlock path tries real first, falls back to duress on AEAD failure, returns the canary share silently.
  - Design B (orchestrator-side fake-success UX) per §11.4.3: client-side emits a signed duress flag over a **separate** key (provisioned at Sprint 1); orchestrator-side handling (fake receipt, suppression of broadcast, governance revocation) is a separate integration tracked with the orchestrator team, not with this crate. This crate provides the duress-flag-emission API only.

Exit criterion: full 3-facility recovery flow round-trips through **mock** `ColdKeySource` implementations. Duress canary matches Python S10 behavior. Duress-flag emission API tested and documented for the orchestrator team.

### Sprint 5a, 5b (PARALLEL TRACK) — Real HSM integrations (2 weeks each)

These are implemented in separate crates (`bot-polyvault-aws` and `bot-polyvault-gcp`), on a parallel track after Sprint 5 exits. Each integration:

- Implements the `ColdKeySource` trait using the respective cloud HSM's native API.
- Maps authentication (IAM role / service account) and error semantics to the trait's error type.
- Is tested against a staging/sandbox HSM instance with a disposable key.
- Is reviewed by Security Lead before any production key material is ever placed in that facility.

Each HSM integration is ~2 weeks of engineering, not overlapping with the main Rust port sprints. Can be scheduled after Sprint 5 or deferred until closer to Phase-2 transition.

### Sprint 6 — Audit signatures (Layer 6) + rotation primitives

- `audit_sig.rs`: SPHINCS+-256s via `pqcrypto-sphincsplus`. Append-only log writer with per-event public commitment.
- Rotation logic (§11):
  - Proactive Secret Sharing (PSS): fresh polynomial, same `k*`. Produces new blobs; old ones remain valid until physical destruction.
  - Full rotation: fresh `k*'` + fresh polynomial + on-chain owner-migration transaction builder (interacts with `bot-adapters`).

Exit criterion: SPHINCS+ sign/verify round-trip; PSS and full rotation integration tests round-trip.

### Sprint 7 — Hardening

- All error types checked for accidental secret material leakage in Display/Debug.
- Fuzz tests (`cargo-fuzz`): parser for `shard_blob` and `he_blob`; reject any malformed input without panic.
- Timing: AEAD decrypt timing on wrong key constant-time (subtle-based `ct_eq`).
- CI gates added to the `dol` main branch: all conformance + independence + end-to-end + fuzz tests must pass on every merge.

Exit criterion: `cargo test --workspace` green on a clean checkout; `cargo fuzz run parse_shard_blob -- -runs=1000000` green.

### Sprint 7.5 — External audit + remediation (2–3 weeks, hard block before Sprint 8)

The crate has not touched production key material before this gate. Sprint 7.5 is where an external audit firm reviews the entire `bot-polyvault` crate.

Scope:

- Argon2id / HKDF plumbing correctness under adversarial inputs.
- Wire-format parsers under malformed/adversarial bytes (complements the fuzz work from Sprint 7 with human review).
- Secret-material handling in error paths, panic paths, and edge-case returns.
- DTE bin-edges logic against the monotonicity proof filed in Sprint 0.
- Independence of the duress-flag-signing key from the unlock pipeline.
- Absence of unsafe blocks and validation of every public API's invariant contract.

Remediation: audit findings are triaged and classified (blocker / major / minor). All blockers must close before Sprint 8 begins. Majors are closed before any production traffic; minors are tracked in FINDINGS.md.

Exit criterion: audit report received; no blocker findings open; majors triaged with a closure plan.

### Sprint 8 — Integration with `bot-nav` and treasury operations

- `bot-nav` (NAV signer) currently signs with a key held in env var. Refactor so it obtains a short-lived signing scalar via `bot-polyvault::reconstruct_scalar` at signing time, uses it, and zeroizes.
- Wire up Phase 1 ceremony tooling: `polyvault-cli provision` (mentioned in ceremony runbook §3.5) is a binary in this crate.
- Documentation in the main `dol` README pointing to this spec.

Exit criterion: production `bot-nav` no longer reads a raw private key from env var; it reconstructs per-signing via PolyVault.

---

## 4. What must NOT be ported as-is from the Python sim

Several Python-sim behaviors are deliberate stand-ins for development convenience and must be replaced in Rust:

| Python sim | Rust production requirement |
|---|---|
| Scrypt (N=2^12) for passphrase stretch | Argon2id (m=262144, t=3, p=1) — do NOT ship scrypt to production. kdf_variant byte must be `0x02`. |
| AES-GCM × AES-GCM cold backup | Phase 2+ must be McEliece-8192 ∘ ML-KEM-1024. Phase-1 AES×AES is time-boxed ≤ 6 months. |
| Lamport OTS audit signatures | Must be SPHINCS+-256s via `pqcrypto-sphincsplus`. Lamport is a structural demonstrator, not a production primitive. |
| Trusted-dealer DKG in `Vault.__init__` | Phase 1 uses the ceremony runbook; sprints 1–7 do not re-implement "trusted dealer in a Rust unit test" as a production path. |
| SHAKE-256 in DTE PRF (earlier draft) | Use HMAC-SHA256 per `polyvault-dte-spec.md` §7.1. |
| Python's lack of real zeroization | Rust MUST use `Zeroize` / `ZeroizeOnDrop` on every type that transits a scalar or unlock key. |

Conformance tests check equivalence for the pieces that are supposed to be identical (wire formats, bit-exact DTE encoding). They do NOT require scrypt↔Argon2id equivalence; that is an intentional divergence.

---

## 5. Integration points with `dol-research-labs`

The `dol-research-labs/verification/` suite has test files for the original PolyVault design. These are research-validation tests, not production conformance tests. They remain valid for their original scope. New production conformance tests live in `dol/bot-rs/crates/bot-polyvault/tests/` and run as part of the dol CI pipeline.

The Python simulation `polyvault_defi_sim.py` becomes a **reference oracle** for Rust conformance — not production code. It should be vendored into `dol-research-labs/verification/` (future addition) and referenced in the Rust tests.

---

## 6. Smart-contract interactions

The Rust port must interact with two contract surfaces:

1. **`contracts/Dol.sol` (existing).** Not directly affected — PolyVault protects the private key that signs owner-only functions like `setGuardian`, `setCustodian`, pause/unpause. No Solidity change required for Phase 1.
2. **Future: on-chain owner rotation module.** A minimal contract with `rotateOwner(newOwner, sphinxSig)` where `sphinxSig` is a SPHINCS+ signature over `(nonce, newOwner)` verifiable on-chain. On-chain SPHINCS+ verification is expensive (~4 MB public key for -256s); for EVM it is likely off-chain with an on-chain classical signature from a rotation multisig. Design this in a follow-up spec.

---

## 7. What this plan explicitly postpones

- **Threshold signing (TSS / FROST / GG20).** §12 of the main spec says defer to Phase 3. This plan inherits that deferral. The Shamir-reconstruct `~25 ms` window is documented as residual risk until Phase 3.
- **Biometric fallback per-custodian.** v3.2 removed biometric from the architecture (DeFi custodians don't have biometrics at the institutional level). If a specific custodian wants to add a third factor of their own, the crate accepts an optional `extra_factor: &[u8; 32]` that gets fed into the HKDF IKM. Not in the default path.
- **HSM vendor-specific integration.** `ColdKeySource` trait is defined; implementations for AWS CloudHSM and GCP KMS are separate crates chosen at build time. They are not part of `bot-polyvault`.
- **On-chain SPHINCS+ verification.** Expensive and chain-specific; out of scope for this port.

---

## 8. Effort estimate

| Sprint | Focus | Effort (1 eng) |
|---|---|---|
| 0 | Python reference oracle review (prerequisite) | 1 week |
| 1 | Foundations + conformance + production-corpus pin | 1 week |
| 2 | Argon2id + unlock | 1 week |
| 3 | AEAD + Shamir | 1 week |
| 4 | HE + DTE | 1–2 weeks |
| 5 | Cold backup + duress (stubs only, no real HSM) | 1–2 weeks |
| 5a | Real AWS CloudHSM integration (parallel track) | 2 weeks |
| 5b | Real GCP KMS integration (parallel track) | 2 weeks |
| 6 | Audit sig + rotation | 1 week |
| 7 | Hardening | 1 week |
| **7.5** | **External audit + remediation (hard block before Sprint 8)** | **2–3 weeks** |
| 8 | bot-nav integration | 1–2 weeks |
| **Total (serial path, 1 eng)** | | **~13–17 weeks** |
| **Total (with parallel HSM track)** | | **~13–17 weeks + 2 weeks HSM overlap** |

Assumes one engineer familiar with Rust crypto and the codebase. Double the serial-path estimate for a cryptographer-unfamiliar engineer. The HSM-integration tracks (5a, 5b) can run in parallel with Sprints 6 and 7 if a second engineer is available; otherwise add them serially after Sprint 5.

**The audit buffer (Sprint 7.5) is not optional.** Production key material never touches the Rust code before an external firm reviews the entire crate. A compressed audit timeline has repeatedly been the source of shipped crypto bugs — this plan budgets real calendar time for it.

---

## 9. Review gates (operator sign-off required at each)

- After Sprint 1: byte-layout conformance test results reviewed by Security Lead. Any divergence is a hard block.
- After Sprint 4: DTE cross-language parity signed off by Security Lead + one external reviewer.
- After Sprint 7: full crate reviewed by external audit firm before Sprint 8 integration into `bot-nav`.
- Before Phase 1 ceremony: audit results resolved; ceremony runbook dry-run executed by team.
- Before Phase 2 transition: PQ primitive selection + HSM contracts signed off by governance.

---

---

## 12. Python reference oracle — trust and scope

The Rust port treats `verification/polyvault_defi_sim.py` as the byte-level reference for conformance. This is efficient but introduces an obvious trust-transitivity question: **a bit-identical Rust port of a buggy Python sim produces bit-identical buggy output.** Sprint 0 exists specifically to break that transitivity.

What Sprint 0 verifies in the Python sim:

1. **`compute_bin_edges()` monotonicity proof.** Short (≤ 1 page) mathematical argument showing that for every well-formed corpus (weights summing to the common mass, `max(1, round(·))` allocations, tail padded to `N_BINS - bin_edges[TOP_K]`), the resulting `bin_edges` is strictly monotonic and bounded by `[0, N_BINS]`. Filed in `verification/proofs/bin_edges_monotonic.md`. Without this, adversarial corpora could produce overlapping bins (a subtle DTE integrity failure).

2. **Argon2id parameter conformance.** Assert in CI that `ARGON2ID_M_COST_PROD`, `ARGON2ID_T_COST_PROD`, `ARGON2ID_P_COST_PROD` match main-spec §3.1 byte-for-byte. Regression-guard against a maintainer accidentally dropping these values during refactor.

3. **Wire-format hand-verification.** At least one `shard_blob` and one `he_blob` computed by hand (with an independent serializer) must match the sim's output at a byte level. The hand-computed vectors live in `verification/proofs/wire_format_hand_vectors.md`.

4. **Statistical justifications.** Every chi-squared / Pearson / KS assertion in the sim has a short note explaining the chosen `α`, `n`, and false-positive budget. For S4's `|r| < 0.05` at `n=5000`: `P(|r| > 0.05 | ρ=0) ≈ 0.000008` under normality approximation, so CI flake rate is ≤ 1e-5 per run — acceptable for a CI gate, but documented.

5. **Reference-oracle pinning.** At the end of Sprint 0, the reviewed commit SHA of `polyvault_defi_sim.py` is pinned in `verification/REFERENCE_ORACLE.md`. Any subsequent change to the sim either carries a matching Rust-side update (bumping conformance vectors) or an explicit migration note.

**Limits of Sprint 0.** Sprint 0 does not prove the sim is cryptographically correct — it verifies that the sim says what it means to say, and that its outputs are reproducible. Cryptographic correctness of the architecture itself is the job of the specs (`polyvault-security.md`, `polyvault-dte-spec.md`) and the external audit (Sprint 7.5).

---

*This plan is the operational sequencing document for implementing PolyVault v3.2 in the Dol Rust codebase. It is not itself implementation code; the implementation is produced after operator approval of this plan.*
