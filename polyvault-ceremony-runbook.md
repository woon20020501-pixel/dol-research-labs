# PolyVault Phase 1 DKG Ceremony — Operational Runbook

**Version:** v1.0 (matches PolyVault DeFi Spec v3.2, D2 Phase 1)

> *This runbook is the executable procedure for a Phase 1 air-gapped trusted-dealer Distributed Key Generation (DKG) ceremony. It produces the master signing scalar `k*` for the Dol treasury, Shamir-splits it across custodians, and distributes shards in tamper-evident form.*
>
> *Read in conjunction with `polyvault-security-v3.2-defi.md` §6.3.*
>
> *This runbook is not a tutorial. It is a script. Every step is executed in order, in the presence of all required witnesses. Deviation is a ceremony abort.*

---

## 0. Pre-ceremony decisions (complete before scheduling)

| Decision | Default | Alternative | Signed off by |
|---|---|---|---|
| `(t, n)` threshold | `(3, 5)` | `(4, 7)` if AUM > $100M day-one | Governance quorum |
| Custodian identities (5 for default) | — | — | Governance quorum |
| Ceremony location | Rented secure meeting room, no windows, 24h camera removed in advance | Team HQ if camera-sweepable | Dealer + Security Lead |
| Ceremony date and duration window | — | — | All custodians + witnesses |
| Dealer identity | Founding team security lead OR external, retained auditor | — | Governance quorum |
| Witness list (≥ 2 not including dealer) | — | — | Governance quorum |
| Corpus of `common_passwords_v1.txt` | Pinned at file SHA-256 `<hash>` | Newer version if released | Security Lead |

The dealer, all custodians, all witnesses, and the Security Lead must agree in writing before the ceremony is scheduled. Record the agreement in governance.

---

## 1. Equipment manifest

All items are purchased new, in tamper-evident packaging, opened for the first time at the ceremony.

### 1.1 Compute

- **1× ceremony laptop.** Off-the-shelf, recent model, ≥ 16 GiB RAM. Wiped and packaged in Faraday bag. Brand, model, serial logged in the transcript.
- **1× physical TRNG device.** [OneRNG](https://onerng.info/) or [FST-01 NeuG](https://www.gniibe.org/FST-01/fst-01.html). Packaged at purchase.
- **1× bootable USB stick.** Contains the ceremony image (see §2.2). Pre-built by the security lead from a public, reproducible source; SHA-256 hash of the image published in governance 7 days before ceremony.

### 1.2 Consumables

- **1 pad of tamper-evident bags.** One per custodian + one for dealer destruction evidence.
- **1 color printer** (for QR-code output) with fresh toner cartridge. Brand, model, serial logged.
- **High-quality paper** for QR output. Ream packaged at purchase.
- **5× tamper-evident envelopes** (one per custodian), numbered 1..5.
- **Hammers, bolt cutters, angle grinder** for storage destruction at ceremony close.
- **Chain-of-custody log sheet** (paper).

### 1.3 People

- **Dealer** — operates the ceremony laptop. Does not leave the room with any material after destruction.
- **2+ witnesses** — observe every step, sign transcript, hold hands on physical TRNG during entropy input (optional but symbolic).
- **Each custodian, in person** — receives their tamper-evident envelope at the ceremony close, signs the chain-of-custody log.
- **Security Lead (ex officio)** — ensures runbook is followed; does not operate equipment; may abort ceremony.

### 1.4 Audio-visual

- **2× video cameras** — orthogonal angles, recording the entire room and the laptop screen. Memory cards taken by witnesses at ceremony close; retained in governance-multisig-controlled storage.
- **No mobile phones** in the room. Collected and stored in a Faraday box outside the room.

---

## 2. Pre-ceremony preparation (dealer's solo steps, week before)

### 2.1 Build the ceremony image

A Tails-based custom live image with the following inclusions:

- Tails 6.x base (latest LTS)
- Python 3.11+ with `argon2-cffi`, `pycryptodome`, `ecdsa` (all frozen at pinned versions)
- `polyvault_defi_sim.py` vendored in `/ceremony/`
- `ceremony_generate.py` — the script below (§3) vendored in `/ceremony/`
- `common_passwords_v1.txt` and `wordlist_v1.txt` vendored with matching pinned SHA-256
- QR-code generator (`qrencode`)
- **No network drivers loaded at boot.** Kernel config excludes WiFi and Ethernet modules. Attempts to load them refuse.

### 2.2 Publish image hash AND per-script hashes

The image's SHA-256 is posted to governance ≥ 7 days before the ceremony. In addition to the image hash, the following individual scripts inside the image each have their SHA-256 pinned and published separately in the same governance notice:

- `ceremony_generate.py` — the key-generation script
- `entropy_check.py` — the TRNG statistical-test script
- `polyvault_defi_sim.py` — the reference oracle

Per-script hashes let an auditor verify "this specific script ran" from a single line in the ceremony transcript, without needing to re-extract and hash the full image. The image hash transitively covers the scripts, but having the script hash alone in the transcript makes audit far cheaper.

Witnesses verify all hashes by independently downloading the image and extracting the scripts. Mismatch on any hash is a ceremony abort.

### 2.3 Do not pre-generate

The dealer does NOT pre-generate any keys. All keys emerge inside the ceremony.

---

## 3. Ceremony script

The ceremony is scripted minute-by-minute. Dealer reads each step aloud; witnesses confirm "understood, proceed."

### 3.1 Open (minutes 0–15)

1. Witnesses and dealer enter the room. Phones out, Faraday box sealed.
2. Cameras started (both angles, verified recording on camera displays).
3. Equipment unpacked on camera:
   - Ceremony laptop: inspect seal, break, boot from USB.
   - TRNG: inspect seal, break.
   - Printer: inspect seal, break, load paper.
4. Ceremony image hash verified: dealer runs `sha256sum /path/to/image.iso` on a witness-provided comparison machine outside the room if desired; or witnesses accept the pre-published hash.
5. Ceremony laptop boots to Tails. Dealer confirms no network interfaces available: `ip link show` must show only `lo`.
6. Transcript started on paper (or on a separate witness-laptop that will not leave the room).

### 3.2 Entropy collection (minutes 15–30)

1. Plug TRNG into ceremony laptop.
2. Run:
   ```
   cd /ceremony
   python3 entropy_check.py --source /dev/ttyACM0 --bytes 4096 > entropy_sample.bin
   ```
   This pulls 4 KiB from the TRNG and runs NIST SP 800-22 statistical tests. All tests must pass. If any fails, abort ceremony and reschedule with a new TRNG.
3. Verify OS entropy pool health: `cat /proc/sys/kernel/random/entropy_avail` shows ≥ 256.
4. Witnesses observe. Transcript records: TRNG model/serial, entropy sample SHA-256, test results.

### 3.3 Key generation (minutes 30–60)

Dealer runs:

```
python3 /ceremony/ceremony_generate.py \
    --t 3 --n 5 \
    --trng-device /dev/ttyACM0 \
    --output-dir /ceremony/out/ \
    --custodians alice,bob,carol,dave,erin
```

This script, which is vendored in the image and reviewed in advance:

1. Opens an interactive prompt. Witnesses confirm custodian list matches governance decision.
2. Samples `k*` from mixed entropy: `k* ← SHA-256(os.urandom(64) ∥ trng_sample) mod n`. This guards against a single-source entropy failure.
3. Samples polynomial coefficients `(a_1, a_2)` the same way.
4. Computes `y_i = f(i) mod n` for `i = 1..5`.
5. For each custodian:
   - Generates a fresh `argon2_salt` (32 random bytes).
   - **Does not** generate passphrases — each custodian provides their own after the ceremony (§3.5).
   - **Does not** provision hardware tokens — each custodian brings their own YubiKey / HSM-bound token and binds in a separate on-device session (§3.5).
   - Outputs: `shard_i_raw.bin` (32 bytes `y_i` as big-endian) + `argon2_salt_i.bin` (32 bytes) + `custodian_i_id.txt`.
6. Computes SHA-256 of all outputs and of `k*` (for audit purposes). `k*` itself is NOT recorded to disk — only its hash.
7. Prints per-custodian materials as QR codes (one per custodian: `shard_i_raw` + `argon2_salt_i` encoded together).
8. **Computes Feldman VSS commitments** and prints them to the transcript (see §3.3a below). These commitments are PUBLIC; they let each custodian independently verify that their shard is consistent with the polynomial, without revealing any other coefficient.

Witnesses observe screen; transcript captures each on-screen confirmation.

### 3.3a Feldman VSS commitment emission (required since v3.2)

The dealer also emits a short public commitment set, which every custodian (and any third party) can later use to verify their shard's consistency with the polynomial without reconstructing `k*`. Commitments are points on secp256k1:

```
C_j  =  G · a_j       for j ∈ {0, 1, ..., t-1}
```

where `G` is the secp256k1 generator, `a_0 = k*`, and `a_1, a_2` are the polynomial's non-constant coefficients.

Verification of shard `i` against the commitments:

```
G · y_i  ==  Σ_{j=0}^{t-1}  i^j · C_j   (point equation over secp256k1)
```

`G · y_i` is the public point derived by scalar-multiplying `G` by the shard; the right side is a linear combination of the public commitments. If the equation holds, the shard lies on the committed polynomial.

**What this unlocks.** Post-ceremony verification (§6.2) no longer requires reconstructing `k*` on a general-purpose machine. Each custodian independently runs the point equation on their own signing device with their own shard; Security Lead observes all five confirmations. `k*` never reassembles in the field.

**Storage.** `C_0, C_1, ..., C_{t-1}` are printed to the transcript, photographed, and pinned in governance. They are public values — publishing them leaks nothing about `k*` because they are one-way commitments (recovering `a_j` from `C_j` is the discrete-log problem).

### 3.4 Distribution (minutes 60–75)

1. QR codes for custodian `i` placed in tamper-evident envelope `i`. Envelope sealed on camera.
2. Custodians `i = 1..5` receive their envelopes one at a time. Each custodian signs the chain-of-custody log, stating receipt and envelope integrity.
3. Envelopes are NOT opened in the ceremony room. Custodians leave with sealed envelopes.

**Transit policy (tightened).** Custodians MUST NOT make intermediate stops (café, restaurant, errand) between the ceremony venue and their provisioning location. Envelope remains on the custodian's physical person at all times. Any break of seal discovered at any point is an immediate Security Lead notification and temporary suspension of that custodian's signing authority pending investigation. Target provisioning window is **2–4 hours** from ceremony close, not 24.

### 3.5 Per-custodian post-ceremony (each custodian, within 2–4 hours, on their signing device)

Each custodian, on their own signing laptop, runs:

```
polyvault-cli provision \
    --shard-envelope ~/envelope_<i>.scan \
    --custodian-id <i> \
    --passphrase "<user provides>" \
    --hw-token /dev/yubikey
```

This performs, locally on the custodian's device:

1. Scans the QR codes from the envelope (camera input or pasted file), recovers `y_i` and `argon2_salt_i`.
2. **Verifies shard consistency against Feldman commitments** (§3.3a). Computes `G · y_i` and `Σ i^j · C_j`; aborts provisioning if they do not match.
3. Reads `hw_token_secret` via the token's OTP or attestation interface (never leaves token).
4. Computes `unlock_key = HKDF(hw_token_secret ∥ Argon2id(passphrase, argon2_salt, m=256MiB, t=3, p=1))`.
5. AEAD-encrypts `y_i` to produce `shard_blob` (wire format v1, 98 bytes).
6. Enrolls a duress passphrase (§11.4; **required**, not optional), producing `duress_blob`.
7. HE-encrypts the real passphrase to produce `he_blob` (wire format v1, 22 bytes).
8. Writes the three blobs to the device's secure storage.
9. **Securely destroys the scanned envelope content** (overwrites + filesystem-level delete + media erasure on the scan source).
10. Shreds the paper envelope contents on camera, uploads destruction evidence to governance.

### 3.6 Dealer device destruction (ceremony close, minutes 75–90)

On camera, in view of all remaining witnesses:

1. Boot ceremony laptop is shut down, still attached to power.
2. SSD removed from laptop with security-screwdriver set.
3. SSD struck with hammer ≥ 20 times across its surface; then angle-grinder cut across controller chip.
4. RAM modules removed, snapped in half.
5. Remaining laptop carcass photographed in its destroyed state.
6. Printer paper tray emptied; any unused paper destroyed.
7. Printer ink/toner cartridge removed and physically destroyed (toner resides on drum briefly; fresh cartridge at start is the mitigation).
8. Destruction certificate signed by all witnesses; pinned in governance alongside transcript.

---

## 4. Transcript template

Every ceremony produces a transcript of the following form, signed by all witnesses:

```
POLYVAULT PHASE 1 DKG CEREMONY — TRANSCRIPT
============================================

Date:                <YYYY-MM-DD>
Start time:          <HH:MM UTC>
End time:            <HH:MM UTC>
Location:            <address or room description>
Reason for ceremony: <initial keygen / rotation / re-issue>

Dealer:              <name, signature>
Witnesses:           <name1, signature1>
                     <name2, signature2>
                     ...

Custodians enrolled: <id:name:contact> × n

Equipment
---------
Laptop:              <make model serial>
TRNG:                <make model serial, entropy test pass/fail>
USB image SHA-256:   <hash, pre-published date>
Printer:             <make model serial>

Scripts run (per-script SHA-256)
--------------------------------
ceremony_generate.py   sha256:  <64-hex>
entropy_check.py       sha256:  <64-hex>
polyvault_defi_sim.py  sha256:  <64-hex>

Configuration
-------------
(t, n):              <(3, 5) or other>
DKG tier:            <Phase 1> / <Phase 1 with Feldman VSS>
KDF:                 Argon2id m=262144 t=3 p=1
DTE corpus hash:     <sha256 of common_passwords_v1.txt>
wordlist hash:       <sha256 of wordlist_v1.txt>

Outputs (hashes only — material itself in sealed envelopes)
-----------------------------------------------------------
k* SHA-256:          <64-hex>
shard_1 SHA-256:     <64-hex>
shard_2 SHA-256:     <64-hex>
shard_3 SHA-256:     <64-hex>
shard_4 SHA-256:     <64-hex>
shard_5 SHA-256:     <64-hex>

Feldman commitments (emitted by default in v3.2 Phase 1):
  C_0 = G · k*  = <secp256k1 compressed point, 33 hex bytes>
  C_1 = G · a_1 = <secp256k1 compressed point>
  C_2 = G · a_2 = <secp256k1 compressed point>
  (C_0's derived on-chain address): <0x...>
  (pre-registered owner address):   <0x...>
  (match?): <yes/no — must be yes>

Distribution
------------
Envelope 1 handed to <name> at <HH:MM> — signature: <signature>
Envelope 2 handed to <name> at <HH:MM> — signature: <signature>
...

Destruction
-----------
Laptop serial <s>: SSD destroyed <HH:MM>, RAM snapped <HH:MM>
Printer serial <s>: cartridge destroyed <HH:MM>
Tray paper: destroyed <HH:MM>

Video
-----
Camera 1 card: <ID> — handed to <witness name>
Camera 2 card: <ID> — handed to <witness name>

Abnormalities / abort conditions encountered
--------------------------------------------
<free text; "none" if clean>

Signatures
----------
Dealer:         ____________________
Witness 1:      ____________________
Witness 2:      ____________________
Security Lead:  ____________________
```

This transcript is photographed, digitized, and pinned in governance multisig storage. The photographed PDF is signed by all parties with SPHINCS+ (Layer 6).

---

## 5. Abort conditions

The ceremony MUST be aborted and rescheduled if any of the following occur:

- TRNG statistical tests fail (§3.2).
- Ceremony laptop shows any network interface active or loadable.
- USB image hash does not match pre-published hash.
- A witness requests inspection of a step and the dealer cannot satisfy the inspection.
- Any phone, recording device, or network-capable device is discovered in the room after ceremony start.
- The dealer's computer exhibits any unexpected behavior (unfamiliar process, boot menu entry, anything).
- A power outage or hardware failure.
- Any witness or custodian indicates coercion or suspicion of coercion.

An abort burns the equipment: ceremony laptop, USB, printer — all destroyed per §3.6. TRNG may be retained if its statistical tests passed and the abort cause is unrelated.

---

## 6. Post-ceremony verification (week after)

Within 7 days of ceremony close:

### 6.1 Per-custodian self-verification

Each custodian, on their own provisioned device:

1. Unlocks with their real passphrase; confirms shard unlock produces the `(x, y_i)` from their envelope.
2. Runs the Feldman-commitment verification locally: computes `G · y_i` and `Σ i^j · C_j` (the commitments `C_j` are public, from the ceremony transcript), confirms equality.
3. Reports pass/fail to Security Lead via a signed message.

This step never reassembles `k*`. All computation is local to one custodian's device.

### 6.2 Aggregate consistency verification (no `k*` reconstruction)

Security Lead does NOT reassemble `k*` on a general-purpose laptop during post-ceremony verification. The Feldman commitment structure makes reconstruction unnecessary for consistency checking:

**Procedure:**

1. Security Lead collects each custodian's signed `(i, G · y_i)` pair — the **point** `G · y_i`, not the scalar `y_i`.
2. For each `i`, verifies the Feldman equation `G · y_i  ==  Σ i^j · C_j` using the public commitments from the transcript.
3. If all 5 custodians' points verify against the published commitments, the polynomial is consistent: every shard lies on the same degree-`(t−1)` polynomial whose commitment set was published at ceremony close.
4. For a full liveness check, Security Lead additionally verifies that `C_0 = G · k*` corresponds to the **intended on-chain owner address** — i.e., that the ceremony produced the key whose address was pre-registered in governance. This is done by computing the on-chain address from `C_0` and comparing to the registered value. No `k*` involved; the comparison is on public points.

If any custodian's verification fails, the ceremony output is considered compromised: destroy all Phase-1 output and re-run the ceremony with fresh material.

**Why this replaces the v1 dry-run.** The v1 post-ceremony procedure reconstructed `k*` on a "shared witness-computer with camera attestation" to produce a dry-run signature. That placed `k*` on a general-purpose device, violating the ceremony's central property (the airgapped dealer device is the only place `k*` ever exists; its storage is destroyed before custodians leave the room). The Feldman-commitment procedure above preserves the invariant while giving stronger liveness evidence: every shard is publicly verified against a commitment that the dealer signed, and `C_0` is publicly verifiable against the on-chain owner address.

### 6.3 First legitimate signing is the liveness test

The first production signing operation — which reconstructs `k*` momentarily on the signing environment per §12 of the security spec — is the first and only time `k*` assembles after the ceremony. By this point:

- Custodians have each independently verified their shard against the commitments.
- Security Lead has verified `C_0` corresponds to the intended on-chain owner.
- The first signing is the execution test; it runs on the production signing environment (which has its own security properties), not on a one-off "dry-run" laptop.

The first signing should be chosen to be low-consequence: a governance-acknowledgment transaction, a small-value transfer to a team-controlled address, or a contract call that is idempotent. This is a production signing in every respect; there is no separate dry-run.

### 6.4 On failure

If any of §6.1 / §6.2 steps fail: re-run the ceremony with a fresh key and destroy the Phase-1 output. Do NOT attempt to "patch" a partial ceremony.

---

## 7. Schedule deviation

If the ceremony cannot be executed within the scheduled window:

- Reschedule under the same or a different dealer.
- A partial setup (equipment unpacked but ceremony not performed) still requires destruction of the seal-broken equipment before rescheduling.

---

## 8. Transition ceremonies

A Phase 1 → Phase 2 transition ceremony re-executes the entire Phase 1 script with one difference: the key generation step is replaced by **importing the freshly HSM-generated `k*` from Facility A into the ceremony script**, which then Shamir-splits it. Alternatively, run a new Phase 1 ceremony with a **fresh `k*`** and roll the on-chain owner.

**Recommendation:** fresh `k*` with on-chain owner roll. Importing Phase-1 `k*` into Phase-2 HSMs means Phase-1 hygiene effectively bounds Phase-2 hygiene forever.

Same applies to Phase 2 → Phase 3 transition with Pedersen DKG.

---

## 9. Quick-reference abbreviated script

For operators running the ceremony the Nth time, after the full script has been memorized:

```
[OPEN]
  → Phones in Faraday. Cameras on. Witnesses seated.
  → Unpack laptop, TRNG, USB, printer on camera.
  → Boot from USB. Verify no network interfaces.
  → Start transcript.

[ENTROPY]
  → entropy_check.py on TRNG → all tests pass.
  → Confirm OS pool ≥ 256.

[KEYGEN]
  → ceremony_generate.py.
  → Confirm custodian list.
  → Print QR codes.
  → Print transcript with hashes only.

[DISTRIBUTE]
  → Seal envelopes on camera.
  → Hand to custodians; each signs chain-of-custody.

[DESTROY]
  → Remove SSD, hammer, angle-grinder.
  → Snap RAM.
  → Destroy printer toner.
  → Sign destruction certificate.

[CLOSE]
  → Cameras off; cards taken by witnesses.
  → Pin transcript + destruction cert in governance.
```

The full script is mandatory the first time and every time an equipment or personnel change has occurred.

---

## 10. References

- Section 6.3 of `polyvault-security-v3.2-defi.md` — DKG tier definitions.
- NIST SP 800-22 Rev 1a — Statistical Test Suite for Random Number Generators (2010).
- Tails project — https://tails.boum.org/ (base image source).
- EFF advice on tamper-evident materials — https://ssd.eff.org/

---

*This runbook is the operational complement of PolyVault v3.2 D2 Phase 1. It does not constitute a security audit or certification. Any deviation from the script is a ceremony abort.*
