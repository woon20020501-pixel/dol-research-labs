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

### 2.2 Publish image hash

The image's SHA-256 is posted to governance ≥ 7 days before the ceremony. Witnesses verify by independently downloading and hashing.

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
8. Prints the **ceremony transcript** to paper: dealer name, witness names, custodian list, `k*` SHA-256 (not `k*`), output SHA-256s, per-shard Feldman commitment `g^{coeff}` values if Option B tier is active.

Witnesses observe screen; transcript captures each on-screen confirmation.

### 3.4 Distribution (minutes 60–75)

1. QR codes for custodian `i` placed in tamper-evident envelope `i`. Envelope sealed on camera.
2. Custodians `i = 1..5` receive their envelopes one at a time. Each custodian signs the chain-of-custody log, stating receipt and envelope integrity.
3. Envelopes are NOT opened in the ceremony room. Custodians leave with sealed envelopes.

### 3.5 Per-custodian post-ceremony (each custodian, within 24 hours, on their signing device)

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
2. Reads `hw_token_secret` via the token's OTP or attestation interface (never leaves token).
3. Computes `unlock_key = HKDF(hw_token_secret ∥ Argon2id(passphrase, argon2_salt, m=256MiB, t=3, p=1))`.
4. AEAD-encrypts `y_i` to produce `shard_blob` (wire format v1, 98 bytes).
5. Optionally enrolls a duress passphrase (§11.4), producing `duress_blob`.
6. HE-encrypts the passphrase to produce `he_blob` (wire format v1, 22 bytes).
7. Writes the three blobs to the device's secure storage.
8. **Securely destroys the scanned envelope content** (overwrites + filesystem-level delete + media erasure on the scan source).
9. Shreds the paper envelope contents on camera, uploads destruction evidence to governance.

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

Configuration
-------------
(t, n):              <(3, 5) or other>
DKG tier:            <Phase 1>
KDF:                 Argon2id m=262144 t=3 p=1
DTE corpus hash:     <sha256 of common_passwords_v1.txt>

Outputs (hashes only — material itself in sealed envelopes)
-----------------------------------------------------------
k* SHA-256:          <64-hex>
shard_1 SHA-256:     <64-hex>
shard_2 SHA-256:     <64-hex>
shard_3 SHA-256:     <64-hex>
shard_4 SHA-256:     <64-hex>
shard_5 SHA-256:     <64-hex>

Feldman commitments (if tier supports):
  g^a_0 = <point>
  g^a_1 = <point>
  g^a_2 = <point>

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

1. Each custodian runs a local self-test: unlock with their passphrase, produce a share, confirm `(x, y)` matches their QR output. Report outcome to Security Lead.
2. Security Lead coordinates a dry-run signing: all 5 custodians unlock their shards, produce shares, run Lagrange on a shared witness-computer **with camera attestation**, confirm reconstructed scalar's `sha256` matches transcript's `k* SHA-256`. The reconstructed scalar is then zeroized. **This is the only time after the ceremony that `k*` reassembles.**
3. Dry-run signing produces an attestation signature on a non-critical on-chain message (e.g., a governance-proposal acknowledgment). Confirm the signature verifies under the intended on-chain owner.
4. If any step fails: re-run the ceremony with a fresh key and destroy the Phase-1 output. Do NOT try to "patch" a partial ceremony.

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
