# Dol Vault — Consumer Custody Engineering Specification

**Version:** v0.2 (pre-audit, post-internal-review)
**Status:** Design specification; not yet implemented; not audited.
**Supersedes:** v0.1 (resolves findings C-01 through M-10 from `dol-vault-errata-v0.1.md`). The resolved-finding index is in §17.5.

> Dol Vault is the consumer-facing custody layer for DOL token holders. It is a separate product from the institutional treasury custody stack (see `polyvault-security-v3.2-defi.md`), though the two share cryptographic primitives and a common design philosophy. Where v3.2 protects the protocol's own treasury from institutional-scale adversaries, this document protects an individual holder's DOL and USDC from everyday loss scenarios — lost devices, stolen passkeys, unfriendly acquaintances, and the simple fear of "what happens if I forget something." The audience is three groups that rarely share one document: the engineering team that will build this, the auditors who will review it before mainnet, and the product and marketing teams who will ship and explain it.

---

## 1. Introduction & Product Identity

### 1.1 The Dol protocol as it stands today

Dol is a consumer-facing DeFi yield product. A user deposits USDC and receives DOL — a 1:1 receipt token — that represents a claim on a market-neutral, cross-venue funding-rate harvesting strategy. The strategy is delta-hedged (long perp on one venue, short on another) so the user's redemption value tracks USDC rather than any underlying asset price, while the yield comes from positive funding-rate differentials. The structural analogue is Ethena's USDe, but built natively on Pacifica's perp infrastructure with multi-venue routing (Hyperliquid, Lighter, Backpack as hedge and fallback legs).

The `Dol.sol` receipt token is deployed on Base Sepolia at `0x9E6Cc40CC68Ef1bf46Fcab5574E10771B7566Db4`. The protocol is non-custodial for users in the strict sense: DOL lives in the user's EOA after mint, and `redeem()` is callable only by the holder's signature. The heavy machinery — oracle, decision engine, venue routing, risk enforcement — is off-chain Rust; the on-chain surface is deliberately thin.

### 1.2 Why Dol Vault exists as a separate product

Holding DOL in an ordinary externally-owned account (EOA) inherits every sharp edge of self-custody: a single seed phrase, a single device, and a single mistake. This is acceptable to a crypto-native user who has made peace with the threat model. It is not acceptable to the user Dol most wants to reach: someone who has heard about bitcoin, understands that it is important, and has not entered crypto because the phrase "if you lose your keys, your money is gone" is — correctly — terrifying to them.

Dol Vault (Dol 금고) is the custody layer that sits between those users and the Dol protocol. It packages the user's DOL (and USDC, pre-conversion) into a smart-contract account with:

- A passkey as the day-to-day authenticator, not a seed phrase.
- Social recovery through friends or family, not a sticker on the back of a notebook.
- A two-tier Hot / Vault structure so that small, frequent movements feel like Toss and large, rare movements feel like a bank vault with a 24-hour time lock.
- Gas paid by the protocol, so users never see a gas fee dialog for ordinary operations.

Dol Vault is not a new yield product. The yield source is still the Dol protocol. Dol Vault is the **custody experience** for that yield.

### 1.3 Target user

The target user is the median non-crypto adult in countries where a smartphone and a passkey-capable OS are already in use: South Korea, Japan, much of Europe and North America, and increasingly Southeast Asia. Specific personas:

- *The bank-only saver.* Has heard of stablecoin yield but filed "crypto" in the "too risky, too technical" category. Opens Toss for banking, not MetaMask. Does not want to read a seed phrase. Comfortable asking a close friend to help with something online.
- *The light bitcoin holder.* Owns some bitcoin on a centralized exchange. Has never moved it to self-custody because the seed-phrase flow looks like a trap. Willing to try a product that feels like the exchange but is actually non-custodial.
- *The cautious returnee.* Lost funds once — exchange collapse, phishing, remembered the wrong seed — and is now risk-averse. Wants belt-and-braces, not ideology.

None of these users want to become experts in account-abstraction mechanics. The product must absorb complexity on their behalf.

### 1.4 What Dol Vault is not

A clear scope statement prevents a lot of arguments later.

- **Not a custodian.** Dol does not hold user funds at a legal or operational level. Funds live in a smart contract whose authorization rules are executed on-chain and whose owner key is a passkey the user alone controls.
- **Not a wallet for arbitrary assets.** v0.1 supports DOL and USDC on Base only. Other assets are not a policy statement — they are simply out of scope for this version.
- **Not a yield product.** The yield comes from the underlying Dol protocol. Dol Vault does not add a separate return.
- **Not an exchange.** DOL↔USDC conversion is supported as a deposit/withdraw convenience, implemented by calling `Dol.sol::mint` and `Dol.sol::redeem` on the user's behalf. There is no orderbook and no spread.
- **Not a recovery service.** If a user loses their passkey and has not enrolled any guardians, there is no off-ramp operated by Dol that can restore access. This is a deliberate consequence of being non-custodial.
- **Not a legal entity between the user and the protocol.** The vault is a smart contract authorized by the user's passkey. Dol, the company, provides the software that helps the user interact with it.

The marketing guardrails in §16 hold this line in public-facing language.

---

## 2. Threat Model

### 2.1 Adversary classes

Four adversary classes cover the scope Dol Vault defends against. Within each class we name the most plausible capability, not the worst-case nation-state.

| Class | Typical capability | Example attack |
|---|---|---|
| **Opportunistic thief** | Physical device access for a short window; knows the lock screen PIN or watches it shoulder-surfed; no passkey bypass. | Steals unlocked phone from a café table. Tries to drain the wallet before the owner notices. |
| **Targeted adversary** | Knows the victim personally. May know a passkey, a device, *or* one or two guardians, but rarely all at once. | A close acquaintance who was trusted as a guardian, plus an ability to briefly hold the victim's phone. |
| **Insider** | An employee at Dol or a vendor (Privy, paymaster operator, infrastructure provider). May see metadata and logs; cannot by policy access passkey private keys or user funds. | A rogue Dol engineer who tries to push a malicious front-end update or drain the paymaster. |
| **Supply-chain adversary** | Compromises a dependency (SDK, library, DNS, bundler). Can briefly execute arbitrary code in the user's browser or on the protocol's off-chain services. | A malicious npm release of a Privy SDK dependency; a hijacked bundler that censors user operations. |

### 2.2 Assets in scope

| Asset | Adversary capability considered | In scope (what we defend) | Out of scope (explicitly) |
|---|---|---|---|
| User's Hot balance | Opportunistic thief with passkey access | Passkey is bound to OS user verification (biometric or device PIN); stolen unlocked device still requires user verification for sign. A watchful user can cancel nothing — Hot is by design immediate. | A thief who already authenticated as the user (matches the biometric or knows the device PIN). |
| User's Vault balance | Targeted adversary with passkey access for < 24 h | 24-hour timelock lets the user observe the pending withdrawal and cancel with one passkey tap. Notifications across channels alert them. | A user who is unreachable for ≥ 24 h and has no trusted guardian to alert. |
| Guardian-mediated recovery | Targeted adversary controlling 1 guardian | Threshold (≥ 2-of-3 for Vault) prevents single-guardian takeover. | A user whose guardian set the adversary *already controls* `k` of. See §3 for why this is user responsibility. |
| Passkey itself | Opportunistic thief | Passkey private key is non-extractable from the secure enclave; adversary must coerce the user's biometric or bypass OS security. | Direct attack on iCloud Keychain or Google Password Manager sync. Out of scope — this is Apple's or Google's threat model. |
| User's DOL/USDC on the Dol protocol | Insider adversary | Dol Vault does not grant the protocol operator any authority to move user funds from the vault. The account owner (passkey) must sign. | Smart-contract bugs in `Dol.sol` itself. Those are audited separately. |
| Paymaster funds | Supply-chain or insider | Paymaster policy (§6.4) rate-limits; exhaustion causes fallback to user-paid gas, not loss of user funds. | Non-payment of sponsored gas if the paymaster deposit is drained during an incident. |
| Governance of the vault code | Insider | Contract is immutable at the account level; upgrades require user redeploy into a new account. Protocol-level pause is limited in scope (§14). | Hostile governance action that an adversary achieves by compromising the Dol team's multisig. |

### 2.3 Explicit out-of-scope items

Everything below is acknowledged as a real risk and explicitly not defended by Dol Vault. They are documented so that users, auditors, and the product team share the same understanding.

- **Guardian collusion.** If `k` (threshold) of the user's guardians coordinate to execute a recovery against the user's will, and the user does not cancel within 24 hours, recovery succeeds and the adversary controls the vault. Choosing guardians is user responsibility.
- **Concurrent passkey and guardian compromise.** A targeted adversary who controls the user's passkey device *and* enough guardians to clear the recovery threshold can bypass every designed defense. The product is not robust to an `n+1`-way compromise when it was designed to tolerate up to `n-1`.
- **Base chain reorganizations or governance attacks.** The vault's state depends on Base's finality. A catastrophic reorg would invalidate on-chain state; this is a chain-level risk shared by every Base user.
- **Apple or Google account takeover.** Passkey sync uses iCloud Keychain or Google Password Manager. An attacker who owns the user's Apple ID or Google account with 2FA bypassed can restore passkeys on a new device. This is the OS vendor's threat model and outside Dol's reach.
- **Bugs in `Dol.sol`.** The receipt token and its redemption logic are audited separately. Dol Vault delegates to `Dol.sol` for mint and redeem; bugs there would affect the vault indirectly. Any such bug is out of this document's scope.
- **Privy outage or compromise at the SDK level.** If Privy's SDK silently starts derives passkeys differently, or their hosted flow is compromised, the user-facing passkey layer could degrade. Mitigations: SDK version pinning, subresource integrity, and in the worst case, an emergency client that interacts directly with the contract.

A reader who sees an attack not in the in-scope table above should treat it as out of scope for v0.1. We will add rows as the product matures.

---

## 3. Trust Model & Responsibility Boundaries

### 3.1 Root of trust

```
         ┌────────────────────────────────────┐
         │         User's WebAuthn key        │    ← passkey private key
         │  (non-extractable, secure enclave) │
         └────────────────┬───────────────────┘
                          │
                          │   generates ECDSA/Ed25519 signatures
                          │   only after OS user verification
                          ▼
         ┌────────────────────────────────────┐
         │     Device secure enclave          │    ← Apple T2 / Secure Enclave
         │     or Android StrongBox            │      or equivalent
         └────────────────┬───────────────────┘
                          │
                          │   syncs via iCloud Keychain (Apple)
                          │   or Google Password Manager (Android)
                          ▼
         ┌────────────────────────────────────┐
         │     User's device(s) and OS         │
         │     account(s) — Apple ID / Google  │
         └────────────────┬───────────────────┘
                          │
                          │   WebAuthn ceremony produces a signature
                          │   over a user operation
                          ▼
         ┌────────────────────────────────────┐
         │     Dol Vault smart-contract       │
         │     account (ERC-4337, on Base)    │
         └────────────────────────────────────┘
```

The diagram's top-to-bottom direction is "what has to hold for the user to sign." Everything above the vault contract is outside the contract's code; the contract simply enforces that a valid passkey signature or a threshold of guardian signatures authorizes a given operation.

### 3.2 Responsibility boundary table

This table is intended to double as a reference for the Terms of Service. The marketing guardrails in §16 must remain consistent with it.

| Responsibility | Dol (the company) | User | Third party (OS, Privy, Base, …) |
|---|---|---|---|
| Correctness of the vault smart contract code | **Yes** — Dol owns the contract source, audit relationship, and any emergency pause within its defined scope (§14). | No (user does not modify the contract). | No. |
| Correctness of the dashboard URL and the code served from it | **Yes** — HTTPS, HSTS, subresource integrity, domain registration hygiene. | Users are expected to visit the canonical URL. | DNS registrars and TLS CAs. |
| Passkey private key integrity | No (Dol cannot reach the enclave). | **Yes** — maintain device security, keep OS up to date. | **Yes** — OS vendor provides enclave and sync. |
| Guardian selection | No (Dol does not choose guardians). | **Yes** — user picks who they trust, reviews annually. | No. |
| Guardian signature when recovery is requested | No (Dol does not sign on behalf of guardians). | **Yes (as a guardian)** — respond to recovery requests via the Dol app or an independent path. | No. |
| Timely user response to suspicious activity | No. | **Yes** — the 24-hour timelock window is the user's chance to react. | Notification channels (push, email) are best-effort by their providers. |
| Gas cost for ordinary operations | **Yes** (subject to paymaster policy in §6.4 and rate-limiting). | No, as long as user behavior is within policy. | No. |
| Availability of funds when Dol is offline | **Yes at best effort; see §12.3 for fallback.** The user can interact with the contract directly through any Base RPC, bypassing Dol's dashboard. | **Yes** — holding their passkey is what lets them sign the fallback transaction. | Base's RPC providers for on-chain reachability. |
| Correct execution of `Dol.sol` mint/redeem | No (separate contract and audit). | No. | **Yes** — the `Dol.sol` authors and auditors own this. |
| Privacy of user's wallet history | Partial. On-chain activity is public by construction on Base. Dol avoids collecting unnecessary off-chain metadata; specifics in the privacy policy. | Partial. | No. |
| Legal disputes between guardians and users | **No** (Dol is not an arbiter). | **Yes** — civil matter between the parties. | No. |

The critical reading of this table is: **loss scenarios caused by a compromised guardian choice, a lost passkey with no guardians enrolled, or an Apple/Google account takeover are user responsibility**, not Dol's. This is expressed explicitly in the ToS and repeated in the app at the moment a user enables the Vault tier (see §11 onboarding flow).

### 3.3 The word "non-custodial" made precise

"Non-custodial" is often used loosely. For Dol Vault the precise definition is:

1. **Funds are held in a smart contract** whose account owner is a public key derived from the user's passkey. The contract code is immutable at the account level (upgrades require a new account, not a storage-layout migration).
2. **No operator signature suffices to move user funds, cancel user actions, or change account authentication.** Dol's own keys (the paymaster key, the factory-level emergency-pause multisig) cannot transfer user balances, cannot alter `ownerPubKeyHash`, cannot modify guardians, cannot cancel a pending user-initiated action. Operators may halt **NEW** flows (new deposits, new recovery initiations) at the factory level for up to 72 hours at a time, with public disclosure, per §14.1 (errata M-10). The pause does not touch any existing user balance or any pending user-initiated transaction.
3. **The passkey private key is not stored, transmitted, or reconstructable by Dol.** It lives in the user's device enclave. Dol's backend sees only signed user operations and public metadata.
4. **Guardian signatures are checked on-chain** against addresses the user themselves registered. Dol's backend may relay guardian approvals for UX reasons but cannot forge them.
5. **A fallback exit exists.** If Dol's dashboard and back-end are entirely unavailable, a user who retains their passkey can craft a UserOperation directly against the Base EntryPoint and interact with their account (§12.3).
6. **Compliance policies may decline to subsidize but cannot restrict.** Dol's paymaster may refuse to sponsor gas for specific operations (e.g., transfers to sanction-flagged addresses). This is a *sponsorship* decision, not a *transfer* restriction. The user retains the ability to execute the operation at their own gas cost. (Errata H-04.)

When the marketing copy says "non-custodial," the six bullets above are what is claimed. Nothing more.

---

## 4. Layer Map

### 4.1 Overview diagram

```
                       User
                        │
                        ▼
    ┌──────────────────────────────────────────────────┐
    │ Layer 1: Passkey Authentication                  │
    │   WebAuthn, OS secure enclave, Privy SDK         │
    └───────────────────┬──────────────────────────────┘
                        │  (signed UserOperation)
                        ▼
    ┌──────────────────────────────────────────────────┐
    │ Layer 2: Smart-Contract Wallet                   │
    │   ERC-4337 account; Safe-pattern guardian logic  │
    └──────┬─────────────────────────────┬─────────────┘
           │                             │
           │ Hot path (Layer 4a)         │ Vault path (Layer 4b)
           │ passkey only, fast          │ passkey + timelock (Layer 5)
           ▼                             ▼
     ┌──────────┐                  ┌──────────────┐
     │ Execute  │                  │  Request →   │
     │   now    │                  │  24 h wait   │
     └──────────┘                  │  → Execute   │
                                   └──────┬───────┘
                                          │  cancel window
                                          ▼
                                   ┌──────────────┐
                                   │ Recovery     │
                                   │ path (L3):   │
                                   │ guardians    │
                                   │ + 24 h lock  │
                                   └──────────────┘
```

### 4.2 Layer-to-threat mapping

| Layer | Defends against |
|---|---|
| **Layer 1 — Passkey authentication** | Unauthenticated adversary. Anyone without the user's bound device and OS user-verification check cannot sign. |
| **Layer 2 — Smart-contract wallet** | Protocol-level policy violations. Enforces Hot/Vault balance separation, guardian threshold, and all on-chain authorization rules. |
| **Layer 3 — Social recovery** | Device loss. A user who has lost their passkey but retains their guardian relationships can restore access. |
| **Layer 4a — Hot tier** | Day-to-day UX friction. Small, frequent operations complete immediately with a single passkey tap. |
| **Layer 4b — Vault tier** | Single-step theft of large balances. The adversary must survive a 24-hour observation window during which the user can cancel. |
| **Layer 5 — Timelock & cancel** | Passkey compromise of a vigilant user. Buys the user 24 hours of real calendar time to notice and respond. |

The mapping is read as "without this layer, what breaks." None of the layers individually carries the entire security burden. §13 extends this to a degraded-security table showing what remains when any one layer is compromised.

---

## 5. Layer 1 — Passkey Authentication

### 5.1 What the layer is

A passkey is a WebAuthn public-key credential. The private key lives in the user's device secure enclave (Apple's Secure Enclave, Android's StrongBox, or the TPM on Windows laptops) and is never extractable. The browser or OS asks the user for "user verification" — biometric (Face ID, Touch ID, fingerprint) or device PIN — before the enclave will produce a signature. The signature is then conveyed to whoever requested authentication: in Dol Vault's case, the dashboard, which bundles it into a UserOperation for Layer 2.

Dol Vault uses passkeys as *discoverable credentials* (a.k.a. resident keys): the OS lists available passkeys without the relying party needing to supply a username. This matches the product requirement that users should never type an email or wallet address; the passkey itself is the identifier.

### 5.2 Privy SDK's role

Privy's SDK is the integration layer between the dashboard and the WebAuthn platform authenticator. The SDK handles:

- The WebAuthn registration and authentication ceremonies.
- Derivation of a stable wallet public key from the passkey (Privy-internal mapping).
- A consistent API across browsers and OSes, absorbing the genuine differences between Apple and Google platforms.

Dol Vault's code calls Privy SDK for three operations: initial passkey registration, authentication for each UserOperation, and passkey retrieval for recovery-adjacent flows. Dol does *not* ask Privy to custody funds, to relay unsigned transactions, or to store anything that is not already public. If Privy's service is unavailable, the vault is still reachable through the fallback path in §12.3.

**Privy's non-WebAuthn surfaces are NOT enabled (errata M-08).** Privy's product includes OAuth / social-login / embedded-wallet flows. **Dol Vault uses Privy exclusively for WebAuthn (passkey) credential provisioning and cross-device sync coordination. The OAuth / social-login / embedded-wallet fallback paths are not enabled for Dol Vault accounts.** The user's passkey is the sole authentication path; there is no email-login, no SMS-login, no Google-account fallback, no "sign in with" alternative. This preserves the single-root-of-trust property of §3.1: if the passkey is the only thing that can authenticate UserOperations, the OAuth provider does not become a second root of trust, and §2's threat model does not need to account for OAuth compromise as a distinct path.

### 5.3 Apple vs Google differences that affect UX

| Aspect | Apple (iCloud Keychain) | Google (Password Manager on Android; Chrome on desktop) |
|---|---|---|
| Passkey sync | Automatic across devices signed into the same Apple ID with iCloud Keychain enabled. | Automatic across Android devices and Chrome signed into the same Google account. |
| Cross-ecosystem passkey | Via Bluetooth caBLE (scan a QR on a nearby device). | Via Bluetooth caBLE. |
| Backup | Inside iCloud Keychain, end-to-end encrypted. | Inside Google's end-to-end encrypted passkey store. |
| Revocation of a lost device's passkey | Possible from iCloud settings (by removing the device). | Possible from Google account security. |
| OS-level "passkey not available" fallback | Rare; typically a prompt to use another device via Bluetooth. | Similar fallback via caBLE. |

These differences matter because the "I lost my phone" flow (recovery in §7) depends on how quickly a user can regain a passkey on a replacement device, which is an Apple/Google flow, not a Dol flow. Dol Vault treats passkey recovery on a new device as an external step that precedes guardian-assisted recovery; if the user can regain their passkey via iCloud or Google, guardian recovery is not needed.

### 5.4 The "same ecosystem, all lost" scenario

The worst realistic passkey-loss scenario is: the user has only Apple devices, loses all of them, cannot regain access to their Apple ID (password forgotten, recovery contacts unreachable), and therefore cannot restore iCloud Keychain. In this case the user's Dol Vault passkey is unrecoverable through the Apple path.

This is precisely the scenario that Layer 3 (social recovery) exists for. The user enrolls guardians at the point of activating the Vault tier; if their passkey is gone, the guardians can collectively authorize a new passkey as the account owner.

A user who has chosen *not* to enable guardians is operating in "Hot-only, no recovery" mode. This is a supported configuration — it's the default right after onboarding, before the user has invited anyone — but it is labeled clearly in the UI and the user is prompted to activate Vault and set guardians before moving substantial value in. See §11 for the narrative.

### 5.5 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| Passkey private key remains in the secure enclave | Jailbroken/rooted device exposes the enclave (rare but possible with historic iOS/Android exploits) | Adversary could extract the key and sign freely. Mitigated only by OS-level security; Dol cannot defend. |
| User verification precedes every signature | Enclave policy misconfigured (e.g., OS update regression) | Passkey could sign without biometric check. Out of Dol's control; report to OS vendor. |
| Privy SDK derives the same public key for the same passkey across sessions | SDK bug or silent upgrade changes derivation | Dol Vault account "loses" its owner; funds inaccessible until SDK regression fixed. Mitigation: SDK version pinning; track Privy release notes. |
| OS sync correctly propagates passkey to new devices | Apple ID / Google account compromised; attacker restores passkey on their device | Attacker becomes an authenticated signer. Out of Dol's scope; user responsibility to protect OS account. |
| User keeps at least one device with the passkey | User loses all devices and cannot re-sync from iCloud/Google | Layer 3 (social recovery) is the fallback. Without guardians, funds are unrecoverable. |
| Passkey origin binding works (dashboard origin pinned) | Attacker serves a fake dashboard that presents a fake passkey prompt | WebAuthn's origin check refuses the signature for the wrong origin. Strong protection; but phishing-resistance is a WebAuthn invariant, not a Dol-specific one — respect it in the integration. |

The failure-modes table is conservative. It lists capabilities Dol explicitly does not defend against, and marks them as such.

---

## 6. Layer 2 — Smart Contract Wallet (ERC-4337 + Safe guardian pattern)

### 6.1 Design stance

The vault contract is an ERC-4337 account. Every user action — deposit, withdrawal request, cancel, recovery step — is a UserOperation that flows through the standard 4337 pipeline. The contract is a self-contained implementation; it does not import the full Safe codebase. It borrows the *pattern* of Safe's `SocialRecoveryModule`: guardians, threshold, pending recovery state, timelock, cancel. This keeps the contract small enough to audit carefully while preserving the industry-validated recovery topology.

There are three motivations for this choice:

1. **UX.** Account abstraction is the only path to "no seed phrase, gas sponsored, passkey-native" on the EVM today. ERC-4337 is the standard that EVM clients implement.
2. **Portability.** The contract does not depend on Safe's broader module system, so it can deploy on Base today and on any other 4337-capable chain tomorrow without a Safe deployment there.
3. **Auditability.** A ~1,500 line contract is reviewable by two independent firms in a reasonable timeline. A Safe-full deployment would require reviewing the entire Safe codebase's interaction with our customizations.

### 6.2 ERC-4337 components in use

| Component | Who runs it | Dol Vault's relationship |
|---|---|---|
| `EntryPoint` | Base-native, canonical deployment `0x0000000071727De22E5E9d8BAf0edAc6f37da032` | External; the one authority allowed to call `validateUserOp` on the account. |
| `Account` (per user) | Deployed by the account factory at first-use, one per user | **This is Dol Vault's contract.** Owns the user's balance (internally partitioned Hot/Vault), enforces authorization rules. |
| `Account Factory` | Deployed once by Dol | Creates new `Account` instances via CREATE2 given a passkey public key. |
| `Bundler` | Either Dol-run or a public bundler; both acceptable | Relays UserOperations. The bundler is trusted for liveness, not security — a malicious bundler can censor but cannot forge. |
| `Paymaster` | Dol-run | Sponsors gas for UserOperations that meet the sponsorship policy (§6.4). Pays the bundler in ETH; deducts from an on-chain deposit. |

### 6.3 Account storage layout

The per-user Account contract holds the following state. This layout is the audit target for the smart-contract review; every storage slot is documented for layout stability across future upgrades (upgrade path is "deploy new account, migrate," not in-place slot reuse).

```
struct AccountStorage {
    // ── owner authentication ─────────────────────────────────────────
    bytes32  ownerPubKeyHash;              // SHA-256 of P-256 public key (x ∥ y)
    uint64   nonce;                        // ERC-4337 standard nonce

    // ── tiering (Layer 4) — v0.2 ratio-based (errata H-05) ──────────
    uint128  hotLimitUsd;                  // user-set, default $500; floor $0
    uint16   vaultRatioBps;                // 0..10000; portion assigned to Vault
    mapping(address => uint128) lastSeenBalance;  // per-asset; delta-since-last-sync

    // ── pending Hot-limit increase (Layer 5, errata C-01) ────────────
    uint256  hotLimitChangeNonce;          // monotonic id for pending changes
    mapping(uint256 => PendingHotLimitChange) pendingHotLimitChanges;

    // ── withdrawal timelock (Layer 5) ────────────────────────────────
    uint256  withdrawNonce;                // monotonic id for pending requests
    mapping(uint256 => WithdrawRequest) pendingWithdrawals;
    uint32   userTimelockSeconds;          // ≥ 86400 (contract-enforced)

    // ── guardians (Layer 3) ──────────────────────────────────────────
    address[] guardians;
    mapping(address => bool) isGuardian;
    uint8    guardianThreshold;
    PendingRecovery pending;               // at most one active

    // ── keeper (errata H-02) ─────────────────────────────────────────
    address  keeper;                        // authorized to call tier-transfer only
    PendingKeeperChange pendingKeeperChange;

    // ── ops and policy ───────────────────────────────────────────────
    bool     paused;                       // per-account self-pause, owner-only
    bool     vaultTierEnabled;             // gate: off until guardians + notification channel set
}

struct WithdrawRequest {
    uint128  amount;
    address  asset;                        // DOL or USDC
    address  recipient;
    uint64   unlockAt;                     // block.timestamp + timelock
    uint8    status;                       // 0 pending, 1 executed, 2 cancelled
}

struct PendingHotLimitChange {             // v0.2 (errata C-01)
    uint128  newLimit;                     // requested new hotLimitUsd
    uint64   unlockAt;                     // block.timestamp + 86400
    uint8    status;                       // 0 pending, 1 executed, 2 cancelled
}

struct PendingKeeperChange {               // v0.2 (errata H-02)
    address  newKeeper;
    uint64   unlockAt;                     // block.timestamp + 86400
    uint8    status;
}

struct PendingRecovery {
    bytes32  newOwnerPubKeyHash;
    uint64   initiatedAt;
    uint8    approvals;                    // count of guardian signatures
    mapping(address => bool) approved;     // per-guardian approval flag
    uint8    status;                       // 0 none, 1 pending, 2 executable, 3 cancelled
}
```

**Layout stability.** The first two members (`ownerPubKeyHash`, `nonce`) are fixed across any future minor versions. v0.2 storage differs from v0.1 in two ways: absolute balance fields are replaced by `vaultRatioBps` + `lastSeenBalance` (errata H-05), and pending-change slots for `hotLimitUsd` and `keeper` are added (errata C-01, H-02). New fields are appended. A storage-layout test asserts these offsets in CI. **Migration note:** v0.2's layout is incompatible with any v0.1 deployment; upgrading requires deploying a new account contract per user (no v0.1 users exist yet, so this is a forward-looking discipline rather than a migration cost today).

**Why `ownerPubKeyHash` is a SHA-256 hash of the P-256 public key.** Storing the full 64-byte public key would cost two storage slots per account. The hash is 32 bytes (one slot), and the full public key is passed as a calldata parameter in every `validateUserOp` call (§6.5). The account verifies (a) the passed key hashes to the stored value, (b) the signature validates under that key via the RIP-7212 P-256 precompile at address `0x0000000000000000000000000000000000000100` on Base. This makes the verification primitive explicit for audit (errata M-09).

### 6.4 Paymaster sponsorship policy

The paymaster sponsors gas for UserOperations that satisfy all of the following at `validatePaymasterUserOp` time:

1. The calling account is a contract deployed by Dol's account factory (checked by comparing the account's creation-code hash against the factory's known hash).
2. The operation's selector is in a **sponsorable-selectors allowlist**: `deposit`, `depositAndConvert`, `withdrawHot`, `initiateVaultWithdraw`, `cancelWithdraw`, `executeVaultWithdraw`, `initiateRecovery`, `approveRecovery`, `executeRecovery`, `addGuardian`, `removeGuardian`, `setThreshold`, `initiateHotLimitIncrease`, `executeHotLimitIncrease`, `cancelHotLimitIncrease`, `decreaseHotLimit`, `setKeeper` (initiate/execute/cancel variants). Operations with other selectors pay their own gas.
3. The account has not exceeded its per-window rate limit:
   - Per-account rate: no more than **N_PER_DAY** sponsored UserOps per 24 h. Default proposal: `N_PER_DAY = 30`. Final value set at deployment; see §17 Open Questions.
   - Per-account value cap: sponsored withdrawal UserOps above a certain USD equivalent pay their own gas. Default proposal: `$10,000` in a 24 h window.
4. No sanction screening flag (a conservative, narrowly scoped list) is set on the recipient address for outbound transfers. This is a compliance measure; it is not a censorship mechanism beyond the legal minimum.

**Sanction screening is a sponsorship policy, not a transfer restriction (errata H-04).** The on-chain `withdrawHot`, `executeVaultWithdraw`, and related functions in the Account contract perform no destination-address checking. A user whose recipient is sanction-flagged may still execute the transfer by (a) paying gas directly via a user-paid UserOp (the account accepts any signed UserOp from its owner regardless of paymaster sponsorship), or (b) interacting directly with `EntryPoint` through the emergency client documented in §12.3. This posture is consistent with the non-custodial invariants pinned in §3.3: Dol may decline to *subsidize* an operation; it cannot *prevent* it.

If any check fails, the paymaster returns `validation_failed` and the UserOperation either fails (if the account has no EOA fallback with ETH) or falls back to user-paid gas.

Paymaster exhaustion is an availability failure, not a security failure: user funds remain safe; only new sponsored operations are unavailable until the paymaster is topped up. The user retains the option to pay gas directly (see §12.2).

### 6.5 UserOperation flow for a typical deposit

```
        User clicks "Deposit 500 USDC"
                   │
                   ▼
┌──────────────────────────────────────────┐
│ Dashboard builds UserOp:                 │
│   sender        = user's account addr    │
│   nonce         = current account nonce  │
│   initCode      = empty (account exists) │
│   callData      = deposit(500e6, USDC)   │
│   gas fields    = estimated + buffer     │
│   paymasterData = paymaster signature    │
│   signature     = <placeholder>          │
└─────────────────────┬────────────────────┘
                      │
                      ▼
        Dashboard asks Privy to produce a WebAuthn
        signature over the UserOp hash. Browser
        triggers OS user verification.
                      │
                      ▼
┌──────────────────────────────────────────┐
│ Dashboard replaces signature field       │
│ with the passkey signature.               │
└─────────────────────┬────────────────────┘
                      │   POST UserOp to bundler
                      ▼
              Bundler → EntryPoint
                      │
                      ▼
        EntryPoint.validateUserOp() on Account:
          - substep 1: hash check
              SHA-256(passedPubKey_x || passedPubKey_y) == ownerPubKeyHash ?
          - substep 2: P-256 precompile call
              call 0x0000000000000000000000000000000000000100 with
              (userOpHash, r, s, x, y); must return 1
          - substep 3: nonce freshness + validAfter/validUntil
              reject if nonce seen; return validity window
                      │
                      ▼
        EntryPoint.validatePaymasterUserOp():
          - check selector in allowlist
          - check rate limits
          - deduct gas reserve from paymaster deposit
                      │
                      ▼
        EntryPoint.execute():
          - Account.deposit(500e6, USDC)
          - Account transfers USDC in
          - Account calls Dol.sol.mint() if conversion requested
                      │
                      ▼
              Event DepositCompleted(...)
                      │
                      ▼
        Dashboard receives event; updates balance view.
```

The entire flow typically resolves in 2–4 seconds on Base. The user sees only "Confirm with Face ID" and then "Deposit confirmed."

### 6.6 Solidity interface sketch

The following is the public interface of the Account contract, at a level sufficient for audit scoping. `pragma solidity ^0.8.20` compiles the signatures as shown.

```solidity
pragma solidity ^0.8.20;

enum WithdrawTier { Hot, Vault }

struct WithdrawRequestView {
    uint256 id;
    uint128 amount;
    address asset;
    address recipient;
    uint64  unlockAt;
    uint8   status;
}

interface IDolVaultAccount {
    // ── Deposits ─────────────────────────────────────────────────────
    /// @notice Deposit `amount` of `asset` (DOL or USDC) into the account.
    ///         Tier assignment (Hot vs Vault) is automatic per hotLimitUsd.
    function deposit(uint256 amount, address asset) external;

    /// @notice Deposit USDC and convert to DOL via Dol.sol in one step.
    ///         Gas overhead vs deposit(USDC): one additional external call.
    function depositAndConvert(uint256 usdcAmount) external;

    // ── Withdrawals ──────────────────────────────────────────────────
    /// @notice Hot-tier withdrawal; executes immediately, passkey-only.
    function withdrawHot(uint256 amount, address asset, address to) external;

    /// @notice Vault-tier withdrawal; creates a pending request that unlocks
    ///         after userTimelockSeconds. Returns the request id.
    function initiateVaultWithdraw(
        uint256 amount,
        address asset,
        address to
    ) external returns (uint256 requestId);

    /// @notice Cancel a pending Vault-tier withdrawal. Passkey-only.
    function cancelWithdraw(uint256 requestId) external;

    /// @notice Execute a pending Vault-tier withdrawal whose timelock expired.
    function executeVaultWithdraw(uint256 requestId) external;

    // ── Recovery (guardians) ─────────────────────────────────────────
    /// @notice A guardian initiates recovery toward `newOwnerPubKeyHash`.
    ///         First call creates PendingRecovery; subsequent calls count
    ///         as approvals toward the threshold.
    function initiateRecovery(bytes32 newOwnerPubKeyHash) external;

    /// @notice A guardian approves the currently pending recovery.
    ///         Any guardian can call; double-approval rejected.
    function approveRecovery() external;

    /// @notice The user (current owner) cancels a pending recovery.
    function cancelRecovery() external;

    /// @notice Executes a pending recovery whose timelock expired.
    ///         Callable by anyone (the transaction fee is subject to
    ///         paymaster sponsorship policy).
    function executeRecovery() external;

    // ── Guardian management ──────────────────────────────────────────
    function addGuardian(address guardian) external;
    function removeGuardian(address guardian) external;
    function setThreshold(uint8 newThreshold) external;

    // ── Tiering policy (v0.2: asymmetric — raise timelocked, lower instant) ─
    /// @notice Request an INCREASE of hotLimitUsd. 24 h timelock (errata C-01).
    function initiateHotLimitIncrease(uint256 newLimit)
        external returns (uint256 requestId);
    function executeHotLimitIncrease(uint256 requestId) external;
    function cancelHotLimitIncrease(uint256 requestId) external;

    /// @notice DECREASE hotLimitUsd immediately. Strengthens protection; no delay.
    function decreaseHotLimit(uint256 newLimit) external;

    function setVaultTimelock(uint32 seconds_) external;  // ≥ 86400

    // ── Keeper management (v0.2, errata H-02) ────────────────────────
    /// @notice Authorized to call tier-transfer functions only. 24 h timelock on change.
    function initiateSetKeeper(address newKeeper) external;
    function executeSetKeeper() external;
    function cancelSetKeeper() external;

    // ── Tier transfer (internal state only; no external token movement) ──
    /// @notice Rebalance account's Hot/Vault ratio. onlyOwnerOrKeeper.
    function rebalance() external;

    // ── Emergency (per-account, owner-only) ──────────────────────────
    function pause() external;     // owner-only; blocks withdrawals on this account
    function unpause() external;   // owner-only

    // ── Views ────────────────────────────────────────────────────────
    function owner() external view returns (bytes32 pubKeyHash);
    function guardians() external view returns (address[] memory);
    function threshold() external view returns (uint8);
    function keeper() external view returns (address);
    function hotLimit() external view returns (uint256);
    function vaultRatioBps() external view returns (uint16);
    function hotBalance(address asset) external view returns (uint256);
    function vaultBalance(address asset) external view returns (uint256);
    function pendingWithdrawal(uint256 id)
        external view returns (WithdrawRequestView memory);
    function pendingHotLimitIncrease(uint256 id)
        external view returns (uint128 newLimit, uint64 unlockAt, uint8 status);
}

/// @notice Factory-level interface for the narrow-scope global pause.
///         Pauses NEW flows only; existing user actions remain fully functional.
///         (v0.2, errata M-10.)
interface IDolVaultFactory {
    /// @notice Halt new deposits across all accounts for `duration` seconds.
    ///         Requires 3-of-5 Dol-team multisig. Max `duration` = 72 h.
    ///         Cancellable only by letting the duration expire (auto-expiry).
    function pauseNewDeposits(uint64 duration) external;

    /// @notice Halt new recovery initiations. Same access + duration bound.
    function pauseNewRecoveries(uint64 duration) external;

    /// @notice Views; public state so auditors can verify pause is rate-limited.
    function depositsPausedUntil() external view returns (uint64);
    function recoveriesPausedUntil() external view returns (uint64);
    function lastPauseEndedAt() external view returns (uint64);
}
```

Not shown above: the standard ERC-4337 hooks (`validateUserOp`, `executeUserOp`), which are implemented by the base account contract and behave per the 4337 specification.

### 6.7 Authorization rules (who can call what)

Each external function has an authorization predicate enforced in the contract. The table below is the spec; the audit scope includes a test suite that exercises each predicate positively and negatively.

| Function | Authorized caller | Additional preconditions |
|---|---|---|
| `deposit`, `depositAndConvert` | Any (the account itself via UserOp) | Not paused |
| `withdrawHot` | Account owner (passkey signature via UserOp) | Not paused; `amount ≤ hotBalance(asset)` |
| `initiateVaultWithdraw` | Account owner | Not paused; `amount ≤ vaultBalance(asset)`; `vaultTierEnabled` |
| `cancelWithdraw` | Account owner | Request exists and status == pending |
| `executeVaultWithdraw` | Any (anyone can execute after unlock) | Request unlocked; not paused |
| `initiateRecovery` | One of the current guardians | No other recovery pending |
| `approveRecovery` | A guardian who has not yet approved | Recovery pending |
| `cancelRecovery` | Account owner (current passkey) | Recovery pending |
| `executeRecovery` | Any | Recovery pending, approvals ≥ threshold, timelock passed |
| `addGuardian`, `removeGuardian`, `setThreshold` | Account owner | New threshold respects min 2-of-3 rule when `vaultTierEnabled` |
| `initiateHotLimitIncrease` | Account owner | Creates a pending change with 24 h timelock. Errata C-01. |
| `cancelHotLimitIncrease` | Account owner | Request exists and status == pending |
| `executeHotLimitIncrease` | Any | Request unlocked; applies the new limit |
| `decreaseHotLimit` | Account owner | `newLimit < currentLimit`; no timelock (strengthens protection). Errata C-01. |
| `setVaultTimelock` | Account owner | `seconds_` ≥ 86400; change applies only to requests created *after* this call |
| `initiateSetKeeper`, `cancelSetKeeper` | Account owner | 24 h timelock on keeper change. Errata H-02. |
| `executeSetKeeper` | Any | Pending change unlocked |
| `rebalance` (tier-transfer only) | **Account owner OR registered keeper** | `onlyOwnerOrKeeper` modifier. Internal state change only; no external transfer. Errata H-02. |
| `pause`, `unpause` | Account owner | Per-account self-pause (§14.1). Global/factory pauses live in `IDolVaultFactory`. |

Note that `executeRecovery`, `executeVaultWithdraw`, `executeHotLimitIncrease`, and `executeSetKeeper` are callable by anyone after their respective timelocks. Making them permissionless means a user who is offline at the exact moment the timelock expires does not lose the transition — a third party (typically Dol's keeper, subject to paymaster rate limiting) can finalize. This is purely a liveness property; the authorization conditions (timelock + threshold, or timelock alone) have already been satisfied.

By contrast, the `rebalance` tier-transfer function is **not** permissionless in v0.2 (errata H-02). In v0.1 it was public on the grounds that it performs an internal state change only. That is true but incomplete: even an internal-only call consumes paymaster-sponsored gas, and an adversary who calls `rebalance` against many accounts can drain the paymaster. v0.2 restricts `rebalance` to the account owner or the registered keeper. Permissionless decentralization of the keeper role (with a bounty mechanism to prevent grief) is deferred to v2 and tracked in §17 Open Questions.

### 6.8 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| `EntryPoint` is the canonical Base deployment | Account accidentally constructed against a different `EntryPoint` | Bundlers and EOA callers cannot execute UserOps correctly; the account is stuck. Mitigation: factory hardcodes the address. |
| Account factory CREATE2 salt is unpredictable (no account-address-squatting attacks) | A maker of the factory allows arbitrary salts | Attackers could predict future account addresses and griefing transfers to them. Mitigation: salt derived from passkey public-key hash and a factory-held secret. |
| Paymaster policy is correctly enforced on-chain | Bug in `validatePaymasterUserOp` accepts an out-of-allowlist selector | Paymaster funds drained. Mitigation: independent audit of paymaster contract; on-chain rate-limit backstop. |
| Sponsored UserOps have a reasonable gas bound | Bug causes unbounded gas | Paymaster drained. Mitigation: `maxFeePerGas` and `callGasLimit` capped by paymaster. |
| Guardians set respects threshold ≥ 2-of-3 for Vault tier | Contract bug allows 1-of-1 while Vault is enabled | Single-guardian recovery hijack possible. Mitigation: Vault tier activation requires the minimum threshold on-chain. |
| Pending recovery is singleton | Bug allows two concurrent recovery processes | Conflicting outcomes; first-execute wins, second stuck. Mitigation: recovery state machine enforces one active. |
| `executeRecovery` after timelock replaces ownership atomically | Bug leaves old owner partially valid | Two owners. Mitigation: single storage slot for `ownerPubKeyHash`, updated last. |
| On-chain clock (`block.timestamp`) is monotonic | Base sequencer time-skew, reorganization | Timelock could appear to expire early if clock skewed. Mitigation: accept `block.timestamp` as provided; reorg protection is at the chain level. |
| Hot limit cannot be raised without timelock (errata C-01) | `initiateHotLimitIncrease` or `executeHotLimitIncrease` bypasses the 24 h gate | Passkey thief raises Hot limit, rebalances Vault → Hot, drains immediately. Mitigation: v0.2 introduces the two-step timelock; `decreaseHotLimit` (the only immediate path) is one-directional (strengthens protection). |
| `rebalance` restricted to owner or registered keeper (errata H-02) | Missing `onlyOwnerOrKeeper` modifier | Adversary calls `rebalance` on many accounts to drain paymaster. Mitigation: explicit access control; keeper address change itself is timelocked. |
| Balance sync hook correctly classifies direct transfers (errata H-05) | `_sync` misreads external transfer (e.g., rebasing ERC-20) | Account's vault-ratio drifts or reverts. Mitigation: token allowlist in §10.5 restricts assets to DOL + USDC, both non-rebasing; sync reverts on unexpected balance decrease. |
| Balance sync hook correctly classifies direct transfers (errata H-05) | Adversary sends dust transfer to poison last-seen-balance | Next legitimate user action sees a small delta assigned to Hot. Impact is bounded by the dust amount; user sees unexpected Hot increase in the UI. |
| RIP-7212 precompile behavior stable (errata M-09) | Base upgrades P-256 precompile with a breaking change | Signatures fail to validate; user locked out until migration. Mitigation: monitor Base upgrade announcements; any incompatible change requires redeploying accounts under a migration flow that relies on the recovery path (guardians as fallback). |

---

## 7. Layer 3 — Social Recovery

### 7.1 Guardian model

A guardian is a wallet address the user nominates to help recover the vault in the event of passkey loss. Guardians are **not** co-signers on day-to-day transactions; they are only active during recovery.

Guardian properties:

- **Type.** An externally-owned account, smart-contract account (e.g., a friend's Dol Vault), or any address that can produce an ECDSA/4337 signature on Base. v0.1 does **not** support community-pool guardians or third-party escrow guardians. Friends, family, a user's own hardware wallet in cold storage — all fine.
- **Constraints.**
  - Must be a non-zero address.
  - Must be on Base (same chain as the vault).
  - Cannot be the account itself (a self-guardian loop is rejected on-chain).
  - Cannot be duplicated.
- **Thresholds.**
  - Hot tier active only: 1-of-1 allowed (user may skip guardians entirely).
  - **Vault tier enabled: minimum 2-of-3 is contract-enforced.**
  - Recommended default at onboarding: 3-of-5.
  - Maximum: 7.

### 7.2 Guardian provisioning UX

At first use, the user creates a Dol Vault account with just their passkey and operates in Hot-only mode. No guardians. The app makes clear that Vault (larger, safer) cannot be activated yet, and that recovery from passkey loss is not available in this mode.

To activate Vault, the user must set at least 2 guardians with a threshold of 2-of-3 (i.e., invite 3 guardians; require 2 approvals for recovery). The app guides them through two provisioning options:

1. **Address input.** If the user has a guardian's Base address handy, they paste it in. This is efficient but does not verify the guardian is online or reachable.
2. **Friend invite flow (preferred).** The user enters the friend's display name (for their own reference) and the app generates a single-use invite link. The friend opens the link, completes a short "guardian onboarding" flow that (a) verifies they control a Base wallet or are willing to create a Dol account, (b) explains their responsibilities as a guardian, and (c) registers their address on the user's account. This is both a provisioning flow and a viral growth loop: the friend may end up creating their own Dol Vault as a side effect.

The contract records the addresses only. Dol's off-chain systems may cache the friend's display name for UX but do not rely on that cache for authorization.

### 7.3 Recovery flow

The recovery flow restores access for a user who no longer controls the account's current passkey.

```
1. User on a new device:
     - Generates a new passkey in Privy (same flow as first onboarding,
       but initiated through a "I lost my access" entry).
     - The Dashboard hashes the new passkey public key and presents a
       "recovery code" to the user — this is newOwnerPubKeyHash.
     - Dashboard offers two distribution options: deeplink + in-app
       message to each guardian (if the guardian is also a Dol user),
       or a shareable URL (if the guardian is not yet a Dol user).

2. The user contacts their guardians through their own channels
   (call, text, in person — Dol does not mediate) to tell them a
   recovery is being requested.

3. Each guardian opens the link / notification. The guardian UI shows
   the full recovery hash and, prominently separated, the first 8 and
   last 8 hex characters (16 chars total) in a large font:

       RECOVERY CODE:  0xA1B2C3D4 ........ E5F6A7B8

   **Before approving, the guardian MUST contact the user through an
   out-of-band channel (phone call, in-person, known-trusted messaging)
   and verify those first-8 and last-8 hex characters match what the
   user reads aloud from the new-device screen.** This step defends
   against a phishing page that substitutes an attacker-controlled
   recovery hash in transit (errata H-03). The user, on their new
   device, sees the same 16 characters in the same large-font format.
   Only after verbal confirmation does the guardian sign the on-chain
   call `initiateRecovery` (if they are the first) or `approveRecovery`
   (if already initiated). Gas is sponsored by the paymaster under the
   guardian-approval selector allowlist.

   Guardian UI copy for the verification step:

       "Before approving: call Alice directly and ask her to read the
        first 8 and last 8 characters of her recovery code. Match them
        here:  0xA1B2C3D4 ........ E5F6A7B8
        Verified by phone?  [ Yes, approve ] [ No, cancel ]"

4. When approvals ≥ threshold on-chain:
     - The contract starts the 24-hour timelock by setting
       pending.status = executable and pending.initiatedAt.
     - The *old* owner (if they still have any device with the old
       passkey) is notified through every channel the account knows.
     - The Dol backend also posts a visible notice on the account's
       dashboard.

5. During the 24-hour window:
     - The *old* owner can call `cancelRecovery` with the current
       passkey. This invalidates the pending recovery.
     - The *new* owner (via the new passkey) can observe but not
       accelerate.

6. After 24 hours:
     - Anyone can call `executeRecovery`. The contract swaps
       ownerPubKeyHash to newOwnerPubKeyHash. The old passkey is no
       longer authorized.
     - The new owner is emailed / pushed a confirmation.
     - If the user had set `vaultTierEnabled`, guardians remain as
       before; the user may choose to rotate them as a follow-up.
```

Step 5 is the critical defense: if a malicious guardian or guardian coalition initiates recovery without the user's consent, and the user still has their old passkey, the user cancels and the attack fails. Step 4's notifications exist to make step 5 possible in practice.

### 7.4 Notification channels during recovery

The product expects the old owner to notice a pending recovery before the 24-hour window expires. Notifications are sent through every channel the user has enabled:

- **In-app push.** The Dol Vault dashboard is installed as a PWA (Progressive Web App) on the user's devices. Push notifications are standard PWA notifications, delivered via APNs/FCM. This is the primary channel.
- **Email.** If the user has enrolled an email (optional but strongly recommended), a recovery-initiated alert is sent immediately and a 6-hours-remaining reminder at hour 18.
- **SMS.** Not supported in v1 due to operational cost and global delivery complexity. SMS is an Open Question for later versions (see §17).

Notifications go out regardless of whether the user's old device is reachable; the user's "new" device (the one requesting recovery) also sees a "we have notified the old owner" confirmation. The absence of a cancellation within 24 hours is taken as consent.

### 7.5 Guardian rotation

The user may want to change guardians for ordinary life reasons (a guardian friend changed wallets; a family relationship changed).

**Normal guardian rotation — user-initiated:** the user signs `addGuardian`, `removeGuardian`, or `setThreshold` with their current passkey. These changes are subject to the standard 24-hour timelock when `vaultTierEnabled`, so a thief with the passkey cannot silently remove the genuine guardians. The old guardian set remains active during the timelock; if the user cancels (via `cancelWithdraw`-style revocation for the governance change — details in §6.7), the rotation aborts.

**Abnormal case — a guardian refuses to help:** a guardian does not have a right to keep their seat against the user's wishes. The user can remove them with a passkey signature; the guardian's cooperation is not required.

**Abnormal case — the user is "stuck" behind a guardian set they no longer control:** this is the same scenario as "passkey lost." The user initiates recovery from a new device; the remaining, cooperative guardians approve; recovery succeeds. If the user's guardian set is entirely uncooperative *and* their passkey is lost, the funds are not recoverable by Dol — by construction. This is the exact residual risk documented in §3 as user responsibility.

### 7.6 Malicious recovery scenarios and their defenses

| Scenario | Attack | Defense |
|---|---|---|
| A single rogue guardian tries to take over | Calls `initiateRecovery` alone | Threshold not met; attack stalls at 1 approval, user and other guardians receive notification. Owner cancels. |
| A coalition of exactly `k` (threshold) guardians collude against the user | All approve a fake recovery | Attack reaches the timelock stage. User receives notifications and cancels with passkey. |
| Same coalition of `k`, plus user is offline ≥ 24 h | Attack completes | Out of scope; documented as user responsibility (§3, §13). |
| A malicious dashboard tricks the user into signing a guardian addition | User unknowingly adds attacker | Dashboard origin check (WebAuthn), subresource integrity on Dol-served scripts, and the 24-hour timelock on governance changes together mitigate. User has opportunity to cancel. |
| An attacker races `executeRecovery` with a user's `cancelRecovery` | Permissionless executor front-runs the cancel | Blockchain serialization: the later-included tx wins. Dol's bundler and RPC infrastructure include a "fast cancel" path with higher priority fees for genuine cancels, to make front-running costly. |
| Phishing page substitutes `newOwnerPubKeyHash` during recovery invitation (errata H-03) | Attacker's hash is shown to guardian as if it were the user's | Out-of-band verbal verification between guardian and user (first 8 + last 8 hex characters). Guardian UI requires explicit "verified by phone?" confirmation before approval. The attacker cannot substitute a hash whose first-8 and last-8 hex characters match the user's legitimate hash without a preimage-pairing that is computationally infeasible under SHA-256. |

### 7.7 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| Guardian addresses stay controlled by the nominated person | Guardian's wallet is stolen | Attacker gains one guardian signature; still needs `k-1` more to reach threshold. User should rotate this guardian out on discovery. |
| The user's passkey is available when a hostile recovery is attempted | User lost their passkey and cannot cancel | Hostile recovery succeeds. This is indistinguishable on-chain from legitimate recovery; mitigated only by the user choosing guardians well. |
| Notifications reach the user within 24 h | Notification delivery fails (spam filter, push permission disabled) | User does not cancel in time. Mitigation: multi-channel notification; in-app banner visible on any subsequent login; recommendations to enable push during onboarding. |
| Guardians can be reached to approve legitimate recovery | Guardian is unavailable or has lost their own wallet | Threshold unmet; user cannot recover. Mitigation: default 3-of-5 recommendation spreads risk; user reviews guardians annually (§14). |
| Timelock is honored by the chain | Base reorganization longer than the timelock window | Guardian actions could be rolled back / replayed. Mitigation: Base's finality is well under 24 h; extreme reorgs would trigger broader chain issues beyond Dol's scope. |
| Invite links are one-time and not publicly posted | User shares an invite link publicly | A stranger registers as a guardian. Mitigation: invite links expire after 24 h; user sees the friend's address after they accept and can remove if wrong. |

---

## 8. Layer 4 — Hot / Vault Tiering

### 8.1 Why two tiers

A single balance enforced uniformly would force one trade-off between speed and safety. Two tiers separate them:

- **Hot** is what the user touches daily: buy a coffee, pay a friend, transfer to another wallet. Immediate, single-tap, low-friction. Capped at a user-set limit.
- **Vault** is savings: untouched for weeks at a time, with a deliberate friction layer (24-hour timelock) before any withdrawal. If it's stolen, the user has 24 hours to notice.

Every well-designed consumer custody product converges on some form of this tiering (Toss, Bitcoin hardware+software pairings, traditional bank "main account + savings"). Dol Vault's choice is simply to make the split explicit, user-configurable, and on-chain.

### 8.2 Threshold policy (asymmetric; errata C-01)

The tier split is a single user-settable threshold `hotLimitUsd`, stored on-chain:

- **Floor:** $0. A user who sets the limit to $0 effectively disables the Hot tier; all balance sits in Vault, all withdrawals are timelocked. A conservative user's choice.
- **Default at onboarding:** $500.
- **Ceiling:** no hard cap. A user with a $1,000,000 account who wants $50,000 in Hot may do so, knowing the risk.

**Change authentication is asymmetric** (this is v0.2's correction of a v0.1 design flaw; see errata C-01):

| Direction | Authentication | Delay |
|---|---|---|
| **Raising** `hotLimitUsd` (weakens protection) | Passkey + 24 h timelock via `initiateHotLimitIncrease` / `executeHotLimitIncrease` | 24 h (contract-enforced) |
| **Lowering** `hotLimitUsd` (strengthens protection) | Passkey only via `decreaseHotLimit` | Immediate |

**Why the asymmetry.** The Vault tier's whole purpose is that a short-term passkey compromise does not drain funds, because the user has 24 hours to observe and cancel. v0.1 allowed `setHotLimit` to raise the limit without a timelock; an attacker with the passkey could raise the limit to an absurd value, trigger rebalance, and drain Hot — completely bypassing the Vault timelock. v0.2 fixes this: raising the limit is itself a Vault-level sensitive operation and inherits the 24 h delay. Lowering the limit is the opposite direction (more protection) and needs no delay.

The state machine parallels Vault withdrawal (§9.1): `initiate` creates a `PendingHotLimitChange`, `execute` applies the new limit once `unlockAt` is reached, `cancel` aborts. Notifications for pending increases use the same channels as Vault withdrawals (§9.4).

### 8.3 Automatic rebalancing (ratio-based; errata H-02, H-05)

v0.2 stores only a **partition ratio**, not absolute per-tier balances. `vaultRatioBps ∈ [0, 10000]` is the portion of total USD value assigned to Vault. Absolute balances are computed on demand from `IERC20(asset).balanceOf(address(this))` multiplied by the ratio (and by 1 − ratio for Hot).

**The `_sync(address asset)` internal hook** runs at the start of every balance-reading function:

1. Read `IERC20(asset).balanceOf(address(this))`.
2. Compare to `lastSeenBalance[asset]`.
3. If balance **increased**, the delta is credited to **Hot** (direct incoming transfers default to Hot). Update `lastSeenBalance[asset]` and leave `vaultRatioBps` unchanged — i.e., the newly-arrived amount is fully Hot; the ratio is preserved for existing value.
4. If balance **decreased** outside a known outbound operation, emit an anomaly event and **revert**. Decreases must always correspond to an executed withdrawal whose accounting the function already tracks.
5. Non-allowlisted tokens (anything other than DOL, USDC) are rejected at `_sync` — even if mistakenly transferred in, the account will not attribute value to them (this is already policy in §10.5; v0.2 enforces it at the sync layer as well).

**Rebalance rule.** `rebalance()` recomputes the desired ratio from `hotLimitUsd` and current total USD value:

- Let `total_usd = balance(DOL) × price(DOL) + balance(USDC) × price(USDC)` (price source per §8.4).
- If `total_usd ≤ hotLimitUsd`: set `vaultRatioBps = 0` (everything Hot).
- Else: set `vaultRatioBps = ((total_usd − hotLimitUsd) / total_usd) × 10000`, clamped to [0, 10000].
- Apply a 10% hysteresis: do not update `vaultRatioBps` if the new value differs from the stored one by less than 100 bps (1 percentage point of total value), preventing thrashing on small price moves.

**Access control.** `rebalance()` is callable only by the account owner or the registered keeper (errata H-02). The registered keeper is an address the user opts into (or leaves unset). Permissionless decentralization is deferred to v2 when a bounty mechanism can prevent grief attacks.

**Triggers.**

- Every user-initiated action that changes balances (deposit, Hot withdrawal, Vault execute) calls `rebalance()` inline.
- A daily keeper sweep operated by Dol calls `rebalance()` on accounts whose last user-action is old. The keeper's calls are sponsored by the paymaster under the `rebalance` selector within the standard rate limits.
- **The keeper cannot move funds out of any account under any circumstance.** `rebalance()` changes only `vaultRatioBps`; no external token transfer is constructed. A compromised keeper can, at worst, mis-set `vaultRatioBps` on an account, which the user can correct with their passkey.

### 8.4 Oracle design

Hot/Vault tier decisions require a DOL/USD and USDC/USD price. The oracle requirements are modest — we need a price within a few percent, updated within a few minutes — but the trade-offs between oracle choices are worth spelling out.

| Option | Accuracy | Freshness | Cost to read | Trust assumption |
|---|---|---|---|---|
| Chainlink USDC/USD | High | Minutes | Low (public feed) | Chainlink oracle network |
| Chainlink DOL/USD | Not yet available (DOL is too small for a Chainlink feed) | — | — | — |
| TWAP from a Uniswap v3 DOL/USDC pool | Moderate | Live | Moderate (on-chain view) | Pool liquidity; low-liquidity pools can be manipulated |
| Dol-operated oracle | High (authoritative for DOL's NAV) | Minutes | Low | Dol's oracle signer |
| DOL := 1 USDC (by protocol design) | Exact at mint/redeem | — | Free | The Dol protocol's peg |

**v0.1 assumed DOL = 1 USDC unconditionally.** That assumption is unsafe during off-peg windows — see the worked example below. **v0.2 (errata M-07)** introduces an oracle-backed tier valuation with a fallback:

- **Primary source:** the Dol protocol's NAV oracle, read from `Dol.sol`'s view function (interface TBD by the protocol team; dependency tracked in §17).
- **Fallback:** the 1:1 identity assumption, subject to a **5% divergence circuit breaker**. If the NAV-oracle reading (when available) ever diverges from 1:1 by more than 5%, the circuit breaker trips and the vault contract blocks further `rebalance()` calls until a user-paid `rebalance()` explicitly acknowledges the oracle state. This prevents silent miscomputation during an off-peg event.

USDC is always valued at $1. USD-peg breaks are a systemic event beyond Dol Vault's scope to address.

**Off-peg exploit example (what v0.2 prevents).**

> User holds 2,000 DOL + 0 USDC; `hotLimitUsd = $500`. Under a 1:1 peg, 500 DOL sit in Hot, 1,500 DOL in Vault. Now suppose DOL trades at 0.75 USDC briefly (off-peg). The user's 500 DOL in Hot are worth $375 (below threshold), but if the rebalance uses the 1:1 assumption it does nothing. A passkey thief during this window can `withdrawHot(500 DOL)` and obtain 500 DOL that, at 0.75 USDC current price but 1 USDC long-run, is economically equivalent to 500 USDC of claims. The user intended the Hot tier to carry $500 of risk, not more. **v0.2's oracle-backed valuation** computes `hot_usd = 500 × 0.75 = $375`, finds the ratio is above the threshold, and refuses to expand Hot further until the peg recovers.

USDC is valued at $1. USD-peg breaks are beyond this design's scope.

### 8.5 Keeper operational model

The daily rebalance sweep is operated by Dol as a batched keeper job. Properties:

- **Authority.** The keeper is a specific registered address per account (errata H-02). It is set via `initiateSetKeeper` / `executeSetKeeper` with 24 h timelock. A user who has not registered a keeper sees only their own-passkey-triggered rebalances; the daily sweep skips them.
- **Capability bound.** The keeper can only call `rebalance()` (internal state change, no external transfer). It cannot withdraw, cannot change guardians, cannot change `hotLimitUsd`, cannot touch `ownerPubKeyHash`. Compromise of the keeper key causes at worst a mis-set ratio, user-correctable.
- **Gas.** Keeper UserOps go through the paymaster under the `rebalance` selector allowlist with the standard rate limits.
- **Failure handling.** If the keeper is down or falls behind, the tier split drifts toward stale values. The next user-initiated action (deposit or withdrawal) triggers inline rebalancing; the user is never blocked.
- **Decentralization.** The keeper is centralized in v0.2 for simplicity. A future version (v2+) can open the keeper role to anyone with a bounty mechanism to prevent grief attacks; see §17 Open Questions.

### 8.6 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| Oracle-backed tier valuation tracks real DOL value (errata M-07) | NAV oracle returns stale price; TWAP manipulated | Rebalance sets wrong ratio. Mitigation: 5% divergence circuit breaker refuses to rebalance until user-paid acknowledge; attacker cannot silently exploit without hitting the breaker. |
| DOL off-peg timing unknown to an attacker | Passkey thief times attack to an off-peg window | See §8.4 worked example. Mitigation: oracle-backed valuation refuses to expand Hot during off-peg. |
| Keeper runs daily | Keeper offline for weeks | Tier split drifts; user eventually re-balances at next interaction. Mitigation: monitoring alerts on keeper liveness (§14). |
| Hysteresis band prevents thrashing | Adversary with keeper key deliberately oscillates ratio | Wasted paymaster spend for that account only; no other account affected; keeper is per-account and rate-limited. Mitigation: keeper rotation if misbehavior observed; rate limits (§6.4). |
| `rebalance` restricted to owner or keeper (errata H-02) | Access control bug makes `rebalance` public | Griefing via mass rebalance calls across accounts drains paymaster. Mitigation: explicit `onlyOwnerOrKeeper` modifier; test suite asserts public caller reverts. |
| `hotLimitUsd` is a sane user choice | User sets it to an absurd value (e.g., $1 trillion) via `initiateHotLimitIncrease` | 24 h timelock (errata C-01) gives user and notifications time to catch a mistake. UI warning at extreme values. |
| Tier-transfer functions cannot exfiltrate funds | Bug allows `rebalance()` to construct an external call | Catastrophic. Mitigation: audit scope; static analysis that `rebalance` contains no external calls. |

---

## 9. Layer 5 — Timelock & Cancel

### 9.1 State machine for Vault withdrawals

```
              ┌─────┐
              │ Idle│
              └──┬──┘
                 │ initiateVaultWithdraw()
                 ▼
        ┌────────────────┐
        │   Requested    │
        │  (pending;     │
        │  unlockAt =    │
        │  t + duration) │
        └───┬────────┬───┘
            │        │  cancelWithdraw() (by owner; any time before execute)
            │        └──────────────►┌──────────┐
            │                        │ Cancelled │
            │                        └──────────┘
            │ block.timestamp ≥ unlockAt
            ▼
        ┌────────────────┐
        │   Executable   │
        │   (anyone can  │
        │    execute)    │
        └────────┬───────┘
                 │ executeVaultWithdraw()
                 ▼
        ┌────────────────┐
        │    Executed    │
        └────────────────┘
```

A request in `Executable` state remains cancellable until executed. `Executed` and `Cancelled` are terminal.

### 9.2 Timelock duration policy

- **Contract floor:** 24 hours (`86400` seconds). The contract rejects any `setVaultTimelock(v)` with `v < 86400`. This is a hard invariant; no user and no owner-only function can reduce it.
- **Default at onboarding:** 24 hours.
- **User-adjustable options:** 24 h / 48 h / 72 h / 168 h (1 week) / custom value ≥ 24 h. A user who wants extra protection against their own impulse or a known upcoming travel window can extend the timelock.
- **Changes apply prospectively only.** A `setVaultTimelock` that lowers (still ≥ 24 h) or raises the duration affects *new* requests; existing pending requests keep their original `unlockAt`. This prevents a user from accidentally (or an attacker from maliciously) shortening a live request.

### 9.3 Cancel

The cancel path is intentionally light: one passkey signature, any time before the request is executed. There is no "undo the cancel" — if a user cancels and wants the same withdrawal, they start a new request (and a new timelock).

The cancel does not refund any gas from the original request UserOp; the paymaster treats the cancel as a fresh sponsored call subject to the standard rate limits.

### 9.4 Notifications during a pending request

The dashboard surfaces a pending Vault withdrawal prominently:

- **On creation.** Push + email (if enrolled): "Vault withdrawal requested — $X to address Y — unlocks in 24 hours. Cancel anytime."
- **At 6 hours remaining.** Push + email: "Vault withdrawal executes in 6 hours. If this wasn't you, tap to cancel."
- **At execution.** Push + email: "Vault withdrawal completed."
- **On cancel.** Push + email: "Vault withdrawal cancelled."

The dashboard banner is persistent until the request resolves; a user who logs in at any point sees the state clearly.

### 9.5 Attack scenario: attacker holds a passkey for < 24 h

The key threat the timelock defends against is a short-term passkey compromise — the user's device is briefly in an adversary's hands, or an adversary obtains a sign from a phished interaction, but the user still controls their account and can act.

Attacker's capabilities:
- Can call `withdrawHot` immediately → **Hot balance is lost.** This is the acknowledged cost of the low-friction Hot tier.
- Can call `initiateVaultWithdraw` for the full Vault balance → request is created, 24-hour timelock starts.
- Has 24 hours to also obtain the user's cancel, which also requires a passkey signature.

The race is explicit: either the attacker keeps the passkey and the user does not notice, or the user notices and cancels. The product's job is to maximize the second outcome through notifications (§9.4) and a user interface that makes cancel a single tap from the notification banner.

### 9.6 Attack scenario: user ignores their verified notification channel ≥ 24 h

This is the narrowed residual risk in v0.2 (errata M-06). v0.1 said the user could have no working channel at all; v0.2 requires a verified channel (minimum email) before Vault is enabled (§11.1), so "no channel at all" is structurally prevented. The remaining residual is: a user who *has* a channel but *does not read it* during a 24-hour window when their passkey is compromised and a Vault withdrawal is pending.

For such a user:

- Email is still delivered to their inbox; the attack is visible in their mail.
- Push is still delivered to any device with the PWA installed.
- Dashboard on next login would show the pending banner even before email is read.

The compromise that remains: a passkey-compromised user who is physically unreachable (no network access, medical emergency, etc.) for ≥ 24 hours **and** has not pre-extended their Vault timelock. Mitigations Dol offers:

1. Notification channel enrollment is required to enable Vault (§11.1) — "no channel" is no longer a state a Vault user can be in.
2. Timelock extension is one passkey tap, available pre-travel or at any time.
3. Guardian-assisted recovery (§7) can rotate ownership even after a Vault drain, preventing the *next* attack from succeeding (though not reversing the first).

A future version may introduce optional "vacation mode" (user-set max timelock extension until explicit re-activation) — still not in v0.2.

### 9.7 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| 24-hour floor is contract-enforced | Bug allows `setVaultTimelock(3600)` | User's Vault can be drained in 1 hour, eliminating the main defense. Mitigation: audit scope; this is the most critical invariant. |
| Cancel is always callable by the owner | Bug gates cancel on a flag that can be manipulated | Pending requests become unable to cancel. Mitigation: cancel has no precondition except ownership and pending state. |
| `block.timestamp` is reasonably accurate | Base sequencer clock skew | Timelock expires slightly earlier or later than wall clock. Tolerable for 24-hour durations. |
| Notification channels work | Push disabled, email spam-filtered | User does not notice pending request. Mitigation: dashboard banner on next login; multi-channel delivery; email-channel enrollment is a **gate** for Vault activation in v0.2 (errata M-06). |
| User reads notifications | User on vacation for 2 weeks without monitoring | Vault drains at hour 24 if compromised. Mitigation: pre-travel timelock extension. |
| Hot limit cannot be raised without timelock (errata C-01) | `initiateHotLimitIncrease` or `executeHotLimitIncrease` bypasses the 24 h gate | Attacker with passkey bumps Hot limit, rebalances Vault → Hot, drains via `withdrawHot` in seconds. Mitigation: two-step state machine enforced in v0.2; `executeHotLimitIncrease` reverts before `unlockAt`. Notification issued at initiate and at 6 h remaining (§9.4 extended). |

---

## 10. DOL/USDC Interaction

### 10.1 User-facing flows

From the user's perspective, the flows are:

- **"Deposit 10,000 USDC" → "I have 10,000 DOL in my vault."** Internally: the account pulls 10,000 USDC from the user's EOA (via a `permit2` flow to avoid an explicit approve), calls `Dol.sol::mint(10000e6)`, receives 10,000 DOL into the vault account, allocates to Hot or Vault per the user's threshold.
- **"Withdraw 5,000 DOL as USDC."** Internally: account determines the tier of the requested amount. If Hot-sufficient, immediate: `Dol.sol::redeem(5000e18)` → USDC to user's chosen recipient. If requires Vault funds: create a pending Vault withdrawal request (24-hour timelock); on execute, the redeem-then-transfer pair runs.
- **"Transfer 1,000 DOL to a friend's address."** Internally: Hot-tier if sufficient, immediate; Vault-tier if larger, timelocked. No redemption; DOL is sent directly.

The user never sees the `Dol.sol` address, never approves `Dol.sol` directly, never initiates mint or redeem on `Dol.sol`. The vault contract is the delegate; that relationship is documented in the UI with a plain-English explanation of what happens under the hood.

**Direct-transfer behavior (errata H-05).** If a user (or anyone) sends DOL or USDC **directly** to their vault's account address — bypassing the dashboard deposit flow — the account's `_sync(asset)` hook (§6.3) detects the incoming balance on the next interaction and credits it to the **Hot tier** by default. This is the safe default: a direct transfer is functionally a deposit, and new deposits always start in Hot before any rebalance moves them. To put a direct transfer into Vault, the user can either (a) initiate a Hot-limit decrease (immediate per §8.2), causing the next `rebalance()` to push excess value to Vault, or (b) trigger a manual rebalance via their passkey. User-facing note in the UI:

> If you send USDC or DOL directly to your vault address (instead of using Deposit in the app), the funds show up in your Hot tier. Move them to Vault by lowering your Hot limit or by tapping Rebalance.

Non-allowlisted tokens sent to the vault address (anything other than DOL or USDC) are not credited to any tier; `_sync` rejects them, and they sit in the contract's raw ERC-20 balance — retrievable only by a future upgrade path or by the owner executing an emergency token-recovery UserOp. v0.2 does not expose such a recovery function publicly; this is tracked for v1.0.

### 10.2 Contract relationship diagram

```
    ┌─────────┐
    │  User   │
    │  (EOA + │
    │ passkey)│
    └────┬────┘
         │ UserOp (signed by passkey, built by dashboard)
         ▼
    ┌──────────────┐
    │  EntryPoint  │  (Base canonical: 0x0000...032)
    │   (ERC-4337) │
    └──────┬───────┘
           │ validate + execute
           ▼
    ┌──────────────────────┐
    │   DolVaultAccount    │  (user's per-account contract)
    │                      │
    │  deposit(), withdraw,│
    │  initiate*, execute* │
    └──────┬───────────────┘
           │
           ├──► ERC-20 (USDC on Base)    : transfer / transferFrom
           │
           └──► Dol.sol (receipt token)  : mint / redeem
                   (0x9E6Cc40CC68Ef1bf46Fcab5574E10771B7566Db4 on Base Sepolia)
```

The DolVaultAccount holds both USDC and DOL balances simultaneously within the Hot/Vault partition. Conversions happen lazily: a user who deposits USDC without conversion keeps USDC in the vault; conversion to DOL happens on demand via `depositAndConvert`, or on the first `Dol.sol::mint` call the user explicitly requests.

### 10.3 Approval and allowance strategy

`Dol.sol::mint(usdcAmount)` requires the caller to have approved USDC for the Dol.sol address. For the vault, this is an intra-contract interaction (the account is the caller; it owns the USDC). The account sets an allowance to `Dol.sol` equal to the `usdcAmount` for each mint, and resets to zero immediately after the mint completes. This "per-transaction allowance" pattern avoids leaving a long-lived open approval that could be exploited if a `Dol.sol` vulnerability is discovered later.

For `Dol.sol::redeem(dolAmount)` the approval flow is reversed: the account owns DOL; no approval needed to burn its own tokens.

### 10.4 ERC-7540 (async redemption) forward compatibility

Dol.sol currently implements a synchronous `redeem` that returns USDC immediately. Dol's roadmap includes an optional ERC-7540 "async redemption" mode in which:

1. The user requests a redemption: the DOL is locked in the `Dol.sol` contract; a pending redemption is recorded.
2. After a protocol-defined settlement window (e.g., 8 hours for a typical window, longer during stress), the user calls `claim` and receives USDC.

If Dol.sol adopts ERC-7540, the vault's withdrawal path must handle both a synchronous and an async case. The design affordance in v0.1 is that the vault's `WithdrawRequest` struct already has a timelock-like notion of `unlockAt`; in an async world this would double as the protocol's settlement unlock time, or a `max(user_timelock, protocol_settlement)` value. The on-chain state machine supports both readings.

v0.1 assumes synchronous redemption. When ERC-7540 lands, the vault contract gains an additional state (`ProtocolPending`) between `Requested` and `Executable`; no user-visible change.

### 10.5 Failure modes

| Assumption | Violation | Effect |
|---|---|---|
| `Dol.sol::mint` and `redeem` work as specified | Bug in `Dol.sol` | Vault's deposit/redeem flows fail; user funds stuck in the vault (but not lost). Mitigation: `Dol.sol`'s own audit. |
| Per-transaction allowance fully zeroes after mint | Failure to reset leaves open allowance | A `Dol.sol` vulnerability could drain residual allowance. Mitigation: reset in the same transaction; assertion at function end. |
| Redemption returns approximately USDC-denominated value | Dol NAV collapse | The vault's "1 DOL = 1 USDC" accounting becomes misleading for tiering. Mitigation: oracle question reopens (§8.4); user-visible NAV display. |
| Async redemption (if enabled) honors its settlement window | Protocol queue grows unbounded | Withdrawals delayed beyond user's 24-hour expectation. Mitigation: UI clearly shows protocol-pending state vs user-timelock state. |
| External token is ERC-20 compliant | USDC (reputable issuer) or DOL (internal) deviates | Accounting errors; stuck balances. Mitigation: use established tokens only; v0.1 supports only DOL + USDC. |

---

## 11. UX Flow

This section is narrative. It describes what the user sees, in plain English, for the six product flows that define Dol Vault's experience. Each flow includes proposed UI copy (English; Korean copy will be derived by the product team with the guardrails in §16), backend operations, and expected timings.

The guiding UX principle: **security layers are invisible until they matter.** A user depositing $50 should experience the product as a bank app. A user getting a suspicious recovery notice should experience it as a security alert with a clear cancel button. The same layers are underneath both; the visibility differs.

### 11.1 Flow 1 — First onboarding (no account → vault created)

**Trigger:** a new user opens Dol Vault for the first time (web app at `https://vault.dol.finance` or PWA launched from home screen).

**Screens:**

1. *Welcome.* "Your Dol Vault is a secure home for your DOL and USDC. It uses Face ID instead of a seed phrase and lets friends help you recover access if you ever lose your device. Create your vault in 30 seconds."
   - **Primary button: "Create with Face ID."** (This is the only sign-in option. Dol Vault does not offer email-login, social-login, or "Sign in with Google" alternatives — see §5.2, errata M-08.)
2. *Passkey creation.* Browser invokes WebAuthn. iOS prompts for Face ID / Touch ID. Android prompts for screen lock / biometric.
3. *Confirmation.* "Your vault is ready. Address: `0x...` (tap to copy). You can receive DOL or USDC here anytime."
4. *Gentle nudge toward Vault tier.* A banner below the balance reads: "You're in Hot mode. For amounts over $500, we recommend turning on Vault — it protects you with a 24-hour lock and social recovery. Set up later →"

When the user later taps "Turn on Vault," the **Vault-activation gate** runs (errata M-06). The gate requires, before Vault is enabled on-chain:

- At least 2 guardians enrolled with threshold ≥ 2-of-3.
- **At least one verified notification channel.** Email is the minimum; the user enters an email, receives a one-click verification link, clicks it, returns to the dashboard. The dashboard records the verified address in its own database (not on-chain; this is off-chain product state used only for notifications).
- Until both conditions are met, `vaultTierEnabled` remains `false` and the contract rejects `initiateVaultWithdraw`. The user can still use Hot without either.

This gate is the mechanism that closes the "user has no working notification channel" failure mode from v0.1 (§9.6 in v0.2 is rewritten accordingly).

**Backend operations:**

- Dashboard calls Privy SDK to register a new discoverable passkey (WebAuthn only; no fallback).
- Privy returns the passkey public key. Dashboard hashes it to produce `newOwnerPubKeyHash`.
- Dashboard triggers account factory on-chain to deploy a per-user `DolVaultAccount` via CREATE2. Gas is sponsored by the paymaster.
- Deployment is confirmed on-chain (typically 1–3 seconds on Base).
- At Vault activation (later flow), dashboard sends the email-verification link; on click, dashboard records verification and sets its internal flag; user's next on-chain `setVaultTierEnabled` UserOp (passkey-signed) completes activation.

**Expected time:** 30–45 seconds for initial vault creation (Face ID + factory deploy). Vault activation adds email verification (typically 1–2 minutes including the email round-trip), unless the user defers.

**Friction point + justification:** the biometric prompt is brief and familiar. The email-verification step is new friction at Vault activation time; it is deliberate — without a verified channel, Vault's 24-hour-cancel defense is meaningless.

### 11.2 Flow 2 — Deposit (USDC from an external wallet → DOL in the vault)

**Trigger:** a user who already holds USDC on Base (from an exchange withdrawal, say) wants to move it into Dol Vault.

**Screens:**

1. *Receive tab.* "Your vault address: `0x...`. Send USDC to this address, or tap Connect Wallet to move funds from an external wallet."
2. *After inbound transfer detected:* "We received 10,000 USDC. Convert to DOL to start earning yield? [Keep as USDC] [Convert to DOL]."
3. *Conversion confirmation:* "You're about to convert 10,000 USDC → 10,000 DOL. This uses Dol's mint to produce your DOL. Confirm with Face ID."
4. *Success:* "You now have 10,000 DOL in your vault." A breakdown shows: "Hot: $500 (your daily spending). Vault: $9,500 (protected, 24 h timelock). Adjust →."

**Backend operations:**

- Inbound detection: the dashboard polls the account's USDC balance on Base (or subscribes to Transfer events via RPC webhook).
- On user-confirmed conversion: dashboard builds a `depositAndConvert(10000e6)` UserOp. Privy requests the passkey signature. UserOp goes to bundler → EntryPoint → account. Account pulls USDC from itself, approves `Dol.sol` for exactly 10000e6, calls `Dol.sol::mint`, resets approval to 0, assigns DOL to Hot up to the limit and Vault for the remainder.
- Rebalance event is emitted.

**Expected time:** 10–20 seconds from confirmation to settled state.

**Friction point + justification:** the user does see "Convert to DOL?" which is one step more than many would like. It's there because an immediate auto-convert on receipt would surprise users who deposited USDC intending to keep it as USDC (for, say, a future DOL price decision). The opt-in feels better than a reverse-able auto-convert.

### 11.3 Flow 3 — Hot withdrawal (pay a friend, no timelock)

**Trigger:** user wants to send 100 DOL to a friend's wallet. Amount is below `hotBalance`.

**Screens:**

1. *Send tab.* "Send DOL. To: [paste or scan]. Amount: 100."
2. *Confirmation:* "Send 100 DOL to `0x...` (Base). Tap Face ID to send."
3. *Success:* "Sent. 100 DOL is on its way."

**Backend operations:**

- Dashboard builds `withdrawHot(100e18, DOL, to)` UserOp.
- Passkey signs; paymaster sponsors.
- EntryPoint → account → ERC20 transfer. Confirmed in 2–4 seconds on Base.

**Expected time:** 5–10 seconds end-to-end.

**Friction point + justification:** effectively none. This is the "bank app" path.

### 11.4 Flow 4 — Vault withdrawal (timelocked, $5,000 out)

**Trigger:** user wants to send $5,000 DOL to an external wallet. Amount exceeds Hot balance.

**Screens:**

1. *Send tab.* After entering amount: "This is a Vault withdrawal. It unlocks in 24 hours, giving you time to cancel if something's wrong. [Why?]"
2. *Confirmation:* "Request Vault withdrawal: 5,000 DOL to `0x...`. Unlocks at [date/time in user's locale]. You can cancel anytime before then. Tap Face ID to request."
3. *Post-request:* A prominent banner on the home screen: "Vault withdrawal pending. Unlocks in 23:58. [Cancel]."
4. *6 hours before unlock:* Push notification: "Your Vault withdrawal of 5,000 DOL unlocks in 6 hours. If this wasn't you, tap to cancel."
5. *At unlock:* Push notification: "Withdrawal unlocked. It will complete automatically. [View]."
6. *Completed:* Push notification: "Withdrawal complete. 5,000 DOL sent to `0x...`."

**Backend operations:**

- Request: `initiateVaultWithdraw(5000e18, DOL, to)` UserOp. Passkey signs; paymaster sponsors. On-chain `WithdrawRequest` created with `unlockAt = now + 86400`.
- Dol's keeper monitors pending requests; at `unlockAt + 30s` (small buffer for RPC drift), submits `executeVaultWithdraw(id)` as a sponsored UserOp. Execution pulls DOL from Vault and transfers to recipient.
- If the user cancels, `cancelWithdraw(id)` marks the request Cancelled; the keeper skips.

**Expected time:** 24 hours (by design).

**Friction point + justification:** this is the intentional friction that defines Dol Vault. The UX makes the friction visible but explainable ("24 hours to cancel if something's wrong"). It is the friction users *wanted* when they enabled Vault.

### 11.5 Flow 5 — Device lost, social recovery

**Trigger:** user has lost their phone with all their Dol Vault passkeys. They have guardians set up.

**Screens (on a new device):**

1. *Sign-in page.* "Lost your access? Recover with your guardians." Primary button.
2. *New passkey.* Browser prompts to create a new passkey (biometric or device PIN). The new passkey is for this session's recovery; the user can keep using it afterward.
3. *Recovery code.* "Your new recovery code: `0xA1...F4` (also shown as QR). Share this with your guardians — each needs to approve your recovery."
4. *Guardian list.* "Your guardians: Alice, Bob, Carol. At least 2 need to approve."
5. *Initiate.* "Send invitations to guardians?" Buttons per guardian: copy link, share via app, display QR.
6. *Status screen:* "Waiting for guardians. Approvals: 0/2. [How it works]"
7. *As guardians approve:* the status updates in real time. At 2-of-2 approvals: "Threshold reached! 24-hour safety window starts now. Your vault will be transferred to your new device at [date/time]."
8. *During the 24 hours:* the user is instructed to "stay reachable" in case their old passkey is still functional (if another device is recovered or the old device is found, cancel is possible).
9. *At unlock:* "Recovery complete. Welcome back to your vault."

**Screens (from a guardian's perspective):**

1. *Notification / link:* "Alice is trying to recover her Dol Vault. She sent you a recovery code: `0xA1...F4`. If this was Alice, tap Approve below. If you're not sure, contact her directly before approving."
2. *Confirm:* "Approve recovery of Alice's vault to new owner `0xA1...F4`? Tap Face ID."

**Backend operations:**

- The user's new passkey is registered with Privy on the new device.
- Dashboard constructs the recovery payload. Guardian invitation links embed `newOwnerPubKeyHash` and account address.
- Each guardian's UserOp calls `initiateRecovery` (first guardian) or `approveRecovery` (subsequent guardians). Guardians' own vaults pay their gas, or the paymaster does if the guardian is also a Dol user within policy.
- Timelock starts when approvals ≥ threshold. `executeRecovery` is callable by anyone after 24 h — Dol's keeper submits it automatically.

**Expected time:** mostly out of Dol's control. Guardians approve at their own pace. Once threshold met, 24 hours more.

**Friction point + justification:** high friction, by necessity. Recovery is a rare, high-stakes event; walking users through it with calm clarity reduces errors.

### 11.6 Flow 6 — Inviting a friend as a guardian

**Trigger:** user is setting up Vault tier for the first time, or wants to add a guardian later.

**Screens:**

1. *Add guardian page.* "Guardians help you recover access if you lose your device. Invite a friend — they don't need a Dol account yet."
2. *Invite link:* "Invite link for your guardian: [copy] [share]. Expires in 24 hours."
3. *Friend clicks link:* "Your friend Alice wants you to be her Dol Vault guardian. This means: if Alice ever loses her device, she'll ask you (and her other guardians) to approve her new access. You won't have day-to-day access to her funds. Ready to help?"
4. *Friend, if not already a Dol user:* walks through Dol Vault onboarding. At the end, the friend's own vault is registered as a guardian on the original user's vault.
5. *Friend, if already a Dol user:* "Register your vault `0x...` as Alice's guardian? Tap Face ID."
6. *Confirmation back to original user:* "Alice accepted! She's now one of your guardians. [Add another]"

**Backend operations:**

- Invite link encodes the user's account address and a single-use token.
- On friend's acceptance: if friend has an account, a UserOp calls `addGuardian(friendAccountAddr)` on the original user's account. The call requires the original user's passkey signature (sent via dashboard sync), so the original user is asked to confirm with Face ID before the on-chain call.
- 24-hour timelock on `addGuardian` applies when Vault is already enabled; skipped for the initial setup because the user is still in the Vault-onboarding flow where the timelock is deliberately deferred for first-time setup.

**Expected time:** seconds for the user's action; depends on the friend for the rest.

**Friction point + justification:** viral loop. The friction is meaningful (a new user is asked to create their own Dol Vault in the same flow) and proportional — a friend signing up adds a data point for both parties' security.

### 11.7 UX principles recap

- **Invisible until it matters.** Security layers do not appear in the primary UI during ordinary use.
- **Progressive disclosure.** More sensitive actions unfold with more explicit UI; the timelock is the biggest visible layer.
- **Cancel is always one tap.** Across notifications, banners, and screens, Cancel on a pending action is a single interaction.
- **The user's confidence is the output.** A user who has completed Flow 1 and 2 should feel the product is "like a bank app, but my friends help me." A user who has completed Flow 5 should feel relief, not panic.

---

## 12. Failure Modes (comprehensive)

This section consolidates per-layer failure tables from §5–§9 and adds cross-layer cases.

### 12.1 Per-layer summary (consolidated)

| Layer | Most dangerous failure | Impact |
|---|---|---|
| L1 Passkey | Secure enclave bypass | Attacker can sign at will; no defense below the OS level. |
| L2 Wallet contract | Auth logic bug (timelock floor ignored; unauthorized guardian add) | Entire defense-in-depth collapses to the weakest remaining check. |
| L3 Recovery | Guardian coalition ≥ threshold + user offline 24 h | Ownership lost; documented as residual risk. |
| L4 Tiering | Oracle deviation (v0.2+) | Tier split miscomputed; UX confusion, no direct fund loss. |
| L5 Timelock | 24-hour floor violated by contract bug | Vault becomes as immediate as Hot; primary Vault defense voided. |

### 12.2 Cross-layer failures

| Failure | Scenario | Effect | Defense posture |
|---|---|---|---|
| **Passkey + 1 guardian simultaneously compromised** | Attacker phished the user's passkey *and* turned one guardian. | Hot is taken immediately; Vault times out in 24 h with a failed cancel attempt if user is unaware. Recovery by attacker still needs threshold-1 more guardians. | Hot/Vault asymmetry holds; guardian threshold (≥ 2-of-3) prevents ownership change unless additional guardians are compromised. |
| **Paymaster exhaustion mid-incident** | Attack triggers many sponsored UserOps; paymaster drains. | New sponsored UserOps fail. User can still pay gas directly to EntryPoint with their own ETH (EOA fallback path) to cancel or execute. UX degrades significantly; security properties intact. | Documented fallback (see §12.3); monitoring alerts before exhaustion (see §14). |
| **Base chain congestion during a timelock** | Congestion causes all UserOps to be delayed by hours. | A cancel submitted near the end of the timelock window may not land in time. Mitigation: the dashboard encourages users to cancel well before the deadline (6-hour-remaining notification). | Accepting that a pathological congestion event near the window boundary is unavoidable; users typically have hours of slack. |
| **Privy SDK outage** | Privy's CDN or API is unreachable. | Dashboard cannot produce new passkey signatures through the standard flow. Existing session may still sign if the SDK cached its state. | Fallback client (emergency build) that calls WebAuthn directly without Privy's abstraction; contract calls on a public RPC. Emergency client published in a repository mirror. |
| **Dashboard URL DNS / HTTPS hijack** | Attacker serves a fake UI that asks users to sign a malicious UserOp. | WebAuthn origin check prevents the passkey from signing for the wrong origin. Users still see "Sign in to vault.dol.finance" — phishing-resistant by WebAuthn's design. | The WebAuthn origin binding is the core defense; do not weaken it (e.g., no "allow any origin" debug flag in production). |
| **Guardian-invite link phishing** | Attacker tricks user into installing an invite link that adds the attacker as guardian. | On-chain `addGuardian` with vault-enabled has a 24-hour timelock; user gets notifications and can cancel. | Timelock on governance changes — same defense as for ordinary withdrawals. |

### 12.3 Availability failures and the fallback exit

The product must remain accessible to users even in scenarios where Dol, the company, is unable or unwilling to operate the dashboard. This is a non-negotiable property of a non-custodial system.

**Fallback architecture:**

- The vault contract is immutable per-account. No Dol-controlled upgrade can change its logic.
- The account's owner (the user's passkey) can sign arbitrary UserOperations. The dashboard is a convenience; any WebAuthn-capable client can produce the signatures.
- The paymaster is convenience-only. Users can pay gas themselves directly, bypassing the paymaster entirely.

**Emergency access procedure (documented publicly for users who ask):**

1. Load any EVM-compatible interface (Etherscan's `Write Contract` on Base, a self-hosted wallet tool, etc.) that can craft a UserOperation.
2. Sign the UserOp with any WebAuthn tool that understands Privy's key-derivation (publicly documented by Privy) or, if the SDK's derivation is opaque, with an exported passkey export (WebAuthn passkeys on a recent Apple/Google OS are exportable via platform settings).
3. Submit through any public Base ERC-4337 bundler.
4. User pays gas from their own Base ETH.

This fallback assumes the user retains their passkey (or can regain it via OS recovery). It also assumes the chain is available — outside Dol's reach. The fallback is not pretty; it is meant to exist, not to be used daily.

**Dol commits, in this spec:**

- The emergency access procedure is kept publicly documented on a non-Dol-controlled repository mirror (e.g., IPFS, a community-maintained wiki) so it remains discoverable if Dol itself is offline.
- The Privy key-derivation scheme used by Dol Vault is either documented publicly or replaced with a scheme that is self-describing on-chain (the account contract stores `ownerPubKeyHash`, which the user's own passkey can match against).

### 12.4 "Dol disappears tomorrow" user scenario

If the company fails or is shut down:

| Scenario | What works | What does not |
|---|---|---|
| Dashboard URL down | Vault contract; user's passkey; public Base RPCs; public bundlers. | Dol's keeper (daily tier sweep); paymaster-sponsored gas for most UserOps. |
| Paymaster drained and not topped up | Vault contract; user's passkey; user-paid gas. | Free transactions. |
| `Dol.sol` halted by its own operator | Pre-existing DOL balances in vaults; transfers within Base; redemption to USDC via `Dol.sol` if still operational, otherwise transfer DOL to external recipients and use whatever liquidity remains on secondary markets. | New mints and redemptions through `Dol.sol`. |
| Privy SDK discontinued | User's passkey (still in OS enclave); direct WebAuthn signing via emergency client. | Privy-specific flows in the main dashboard. |

The commitment: in every failure combination above, a user with their passkey retains the ability to move their funds. The ability may be awkward; it exists.

---

## 13. Composition & Degraded Security

A compact table of "what remains when one layer is compromised." Extends and makes precise what §12 lists in prose.

| Layer broken / scenario | What remains | Residual user risk |
|---|---|---|
| Passkey stolen, Hot-only user | Nothing — user is fully compromised at their current risk tier. | Hot balance is lost. |
| Passkey stolen, Vault enabled, user responsive within 24 h | Vault timelock; user cancels pending withdrawal. Guardian rotation path still available. | Hot balance lost; Vault preserved if cancel succeeds. |
| Passkey stolen, Vault enabled, attacker tries `initiateHotLimitIncrease` (errata C-01) | 24 h timelock on the limit-raise itself; user receives notification at initiate and at 6 h remaining, can cancel. | Hot balance (at its current limit) lost; Vault preserved if user cancels in time. |
| Passkey stolen, Vault enabled, user **ignores verified channel ≥ 24 h** (errata M-06) | Vault timelock expires; attacker executes Vault withdrawal. Guardian path can rotate *next* owner. | Hot + Vault both lost; narrowed residual risk — a verified channel is now required to enable Vault, so "no channel at all" is no longer a state. |
| One guardian phished, threshold ≥ 2 | Threshold unmet; recovery stalls at 1 approval; user notified and removes the rogue guardian. | None if user acts. |
| Phishing page substitutes recovery hash during invitation (errata H-03) | Guardian verbally verifies first-8 + last-8 hex with user over phone; attacker's hash fails to match. | None (verbal verification is the defense). |
| `k` guardians collude, user responsive | 24-hour timelock on recovery; user cancels. | None if user acts. |
| `k` guardians collude, user **ignores verified channel ≥ 24 h** | Recovery completes; vault ownership transferred to attacker. | Full loss; narrowed residual risk (verified channel required). |
| Paymaster drained | User-paid gas fallback; all contract functions still reachable. | UX degraded, not lost. |
| Dashboard URL hijacked | WebAuthn origin check rejects signing on attacker's domain; legitimate dashboard remains signed via HTTPS/HSTS. | None (phishing-resistance of passkeys). |
| Privy SDK outage | Emergency client (documented) works directly against WebAuthn + EntryPoint. | UX degraded, not lost. |
| `Dol.sol` vulnerability | Vault's mint/redeem temporarily unusable; DOL/USDC balances in vaults are safe until `Dol.sol` is paused or fixed. | Availability of convert-path lost; funds in the vault are not directly impacted. |
| Base chain outage or extreme congestion | Chain-wide impact; nothing Dol-specific. | Out of scope. |
| Apple ID / Google account compromised | Attacker restores passkey on their device → effectively same as passkey stolen. | Same as passkey-stolen path. |
| Dol operator multisig compromised | Can pause contract if pause was in scope for the multisig; cannot move user funds. | Availability may be affected briefly; no fund loss. |

The pattern: every single-layer compromise leaves at least one layer of defense in place. The residual losses are at the explicit failure points Dol has identified as user responsibility.

---

## 14. Operational Runbook

### 14.1 Incident response playbook

Major incident classes and the response sequence for each.

**Class A — Active exploitation of a contract vulnerability.**

1. On first indication (audit notice, on-chain anomaly, user report), Security Lead is paged.
2. **Two tiers of pause are available (updated in v0.2, errata M-10).**
   - *Per-account self-pause.* The contract retains the per-account `pause()` / `unpause()` (owner-only). Individual users can pause their own account through the dashboard. This is unchanged from v0.1.
   - *Factory-level narrow-scope pause.* A **3-of-5 Dol-team multisig** has authority to call `pauseNewDeposits(duration)` and `pauseNewRecoveries(duration)` on the account factory. These halt **new** user-facing flows at the product surface. Existing user actions — `cancelWithdraw`, `executeVaultWithdraw` on a matured timelock, `withdrawHot`, `cancelRecovery`, `executeRecovery` on a matured timelock — remain **fully functional**. The pause cannot: (a) freeze any existing user balance, (b) cancel any pending user action, (c) change any user's `ownerPubKeyHash` or guardians, (d) extract any user funds. `duration` is capped at 72 hours per invocation; after a pause is invoked, there is a mandatory 72-hour public-disclosure window before the pause can be renewed (preventing silent indefinite pauses). The factory's `IDolVaultFactory` interface (§6.6) makes this explicit.
3. Dol publishes a plain-language advisory on a non-dashboard channel (status page, Twitter) explaining the issue and what users can do. If a factory pause was invoked, the disclosure includes the start time, duration, and a plain-language description of what is affected.
4. If the vulnerability is in a dependent contract (e.g., `Dol.sol`), coordinate with that contract's team.
5. Post-incident: public post-mortem; user compensation policy decided case-by-case per ToS.

**Class B — Paymaster drained beyond threshold.**

1. Monitoring alerts fire when paymaster balance < N days of expected sponsorship.
2. Top up from treasury (standard); failing that, reduce rate limits to stretch remaining balance; communicate to users that some operations will require user-paid gas temporarily.
3. If paymaster reaches zero: UX degrades to user-paid gas; no security property lost.

**Class C — Compromised vendor (Privy, bundler, keeper).**

1. Rotate the affected vendor — replace Privy with alternate SDK fallback, switch to a different public bundler, disable the compromised keeper and run the daily sweep from a backup environment.
2. If Privy was compromised: push the emergency client to users via documented channels; walk users through passkey re-registration if derivation scheme differs.
3. Review session logs for anomalies.

**Class D — Mass guardian-phishing campaign.**

1. Detect by: spike in `initiateRecovery` events across unrelated accounts; social-media reports; external threat-intel feeds.
2. Boost notifications: multiple reminders during timelock windows; in-app top banner with plain warning.
3. Do not autonomously cancel user recoveries — that would be custodial. Users must cancel via their passkey.
4. After incident: guardian-hygiene campaign (annual guardian review prompt accelerated).

### 14.2 Guardian disputes

Guardian relationships can sour. The product does not mediate; it provides mechanics.

- **"My friend won't remove themselves as my guardian."** The user removes them with a passkey signature. The former guardian's cooperation is not required.
- **"My friend is initiating a recovery I did not ask for."** The user cancels within 24 hours using their passkey. If the user has reason to believe the friend will do this repeatedly, remove them as guardian (the same passkey signature that cancels can also remove, within a short flow).
- **"My friend is refusing to approve my legitimate recovery."** The user proceeds with the remaining guardians if threshold can still be met; if not, the user is blocked. Dol cannot help without breaking non-custodial guarantees.
- **"I and my friend had a falling out. Can Dol freeze their guardianship?"** No. The user self-services.
- **Legal disputes.** Dol is not an arbiter. The ToS is explicit that guardian disputes are civil matters between the parties; any subpoena directed to Dol can be answered only with the public on-chain state, which is what the user themselves can see.

### 14.3 CS response templates

A user who contacts support with one of the following situations receives the response below. Scripts are given in English; the Korean versions follow the same substance in the locally natural register.

**"Why is my USDC withdrawal taking 24 hours?"**

> Your withdrawal amount is larger than your Hot tier limit (currently $X). Large withdrawals go through a 24-hour Vault timelock so that, if anyone tries to steal from your vault, you have a full day to notice and cancel. You can cancel this withdrawal anytime before it completes. If you want faster withdrawals for larger amounts, you can raise your Hot limit in Settings — just know that the trade-off is less protection.

**"I had a fight with my guardian friend. What happens?"**

> Your guardian friend cannot do anything to your vault on their own. They can only help you recover access if you ever lose your device, and even then at least [threshold] of your guardians need to agree. If you no longer want this friend as a guardian, open Settings → Guardians → Remove. You can also add a new guardian at any time. Dol doesn't get involved in disagreements between you and your guardians.

**"I lost my phone. What do I do?"**

> If you still have access to another signed-in device (another phone, a laptop), open Dol Vault there — you're still logged in and can keep using it. If that's your only device, you can recover access on a new device using your guardians:
>
> 1. On the new device, tap "Lost your access? Recover with your guardians."
> 2. Follow the steps to create a new passkey.
> 3. Your guardians will each get a request to approve.
> 4. Once enough guardians approve, there's a 24-hour safety window, and then your vault is yours again on the new device.
>
> If your old device is simply misplaced and not stolen, consider cancelling the recovery if you find the device before 24 hours — your old passkey will still work.

**"I got a recovery request in my app but I didn't ask for one!"**

> This is urgent. Someone is trying to take over your vault. Right now, on your device, open Dol Vault — you should see a banner on the home screen that says "Recovery pending. Cancel?" Tap Cancel and confirm with Face ID. This must be done within the 24-hour timelock window; we recommend doing it immediately.
>
> After cancelling, open Settings → Guardians and review your guardians. Remove any that you no longer trust. If this was a widespread phishing attempt or you suspect a guardian's account was compromised, let us know — we'll post a public advisory to warn other users.

### 14.4 Rotation schedule

| Material | Cadence | Trigger-based rotation |
|---|---|---|
| Guardian set review | Annual — an in-app prompt reviews the guardian list and asks "Do you still trust all of these people?" | Guardian changes address; user reports guardian abuse; guardian's own account is known to be compromised. |
| Passkey | User-driven: every device replacement / OS reinstall. Automatic via iCloud / Google sync for same-ecosystem device replacements. | Device lost; OS account compromise suspected. |
| Paymaster signer key | Quarterly rotation. | Any operational incident involving the paymaster infrastructure. |
| Emergency-pause role (Dol team multisig) | Signers reviewed quarterly. | Staff change; suspected compromise. |
| Dashboard TLS certificate | Per CA policy (Let's Encrypt: 90 days). | Private key compromise suspected. |
| Bundler endpoint | As needed. | Public bundler outage, censorship, or price change. |

### 14.5 Monitoring signals

The operations team watches the following signals. Alerts go to a 24/7 on-call rotation for Class A/B events.

- Paymaster balance < 2 weeks of projected spend.
- Keeper last-run > 48 h.
- Pending recovery count + timing: unusual spike above baseline.
- Per-account UserOp rate anomalies.
- Dashboard uptime; 5xx rate.
- RPC provider latency and error rate.

Detail thresholds are an operational concern; §17 Open Questions notes the specific numeric thresholds are to be calibrated during the first 90 days of mainnet.

---

## 15. Deployment Checklist

Pre-mainnet gate. Each item is blocking.

### 15.1 Contract deployment

- [ ] `EntryPoint` canonical address on Base confirmed: `0x0000000071727De22E5E9d8BAf0edAc6f37da032`.
- [ ] Account factory contract deployed; CREATE2 salt scheme reviewed.
- [ ] Paymaster contract deployed; policy logic audited; initial deposit funded.
- [ ] Per-user Account contract audited; storage layout test green; no compiler warnings.
- [ ] Emergency per-account pause path tested end-to-end.
- [ ] `addGuardian` / `removeGuardian` / `setThreshold` timelock tested on pre-enabled Vault tier.

### 15.2 Off-chain infrastructure

- [ ] Bundler chosen: self-run for v1 (control over inclusion policy); fallback public bundler identified.
- [ ] Dashboard hosted at canonical URL with HTTPS + HSTS + preload + SRI.
- [ ] Email notification channel (SES or similar) tested for deliverability across major providers.
- [ ] Push notifications (APNs + FCM) tested on real devices.
- [ ] Status page deployed on a separate origin from the dashboard.
- [ ] Emergency client mirror published on IPFS or equivalent with a permanent pin.

### 15.3 Pre-launch audit

- [ ] At least **two** independent smart-contract audit firms engaged; scope includes Account contract, factory, paymaster, and all guardian-related code.
- [ ] Formal verification attempt on the withdrawal state machine and the recovery state machine (optional but recommended).
- [ ] Findings triaged; all Critical and High severity findings closed; Medium findings triaged with documented decisions.
- [ ] Fuzz / property tests covering all public contract entry points.

### 15.4 Monitoring

- [ ] Paymaster balance monitor with alert threshold < 2 weeks of projected burn.
- [ ] Keeper liveness monitor; last-run staleness alert at 48 h.
- [ ] Recovery-event dashboard; baseline rate recorded; anomaly detector armed.
- [ ] UserOp anomaly detection (rate per account, value per account, unusual calldata patterns).

### 15.5 Legal & policy

- [ ] ToS in place, reviewed by counsel, explicit about:
  - Non-custodial nature.
  - Guardian responsibility and dispute handling.
  - Chain-level and OS-level risks outside Dol's control.
  - ToS change notification procedure.
- [ ] Privacy policy explicit about what Dol stores (passkey public-key hash only; guardian addresses; user's verified email for notifications; *not* guardian names unless user opts in).
- [ ] Jurisdictional legal review for non-custodial custody legality in launch markets.
- [ ] Consumer-protection disclosures where applicable (e.g., Korea's digital asset protection act).
- [ ] Marketing guardrails (§16) internalized by the marketing team; copy review process includes a security sign-off step.

### 15.6 v0.2-specific additions (errata follow-ups)

- [ ] `setHotLimit` timelock state machine tested end-to-end: `initiateHotLimitIncrease` → 24 h wait → `executeHotLimitIncrease` succeeds; `executeHotLimitIncrease` before unlock reverts; `decreaseHotLimit` (immediate) works; `cancelHotLimitIncrease` clears pending state (errata C-01).
- [ ] Keeper address registered on test accounts; `onlyOwnerOrKeeper` modifier asserted by test that public-caller `rebalance()` reverts; `setKeeper` timelock tested (errata H-02).
- [ ] Recovery-hash verbal verification flow tested on real devices: guardian UI shows first-8 + last-8 hex in large font; user-readable format matches on both devices (errata H-03).
- [ ] Email verification flow tested for deliverability: Naver, Daum, Kakao mail, Gmail, Apple iCloud, Outlook. Per-provider delivery rate ≥ 95% verified (errata M-06).
- [ ] `_sync` hook unit tests: direct-transfer detection credits Hot; non-allowlist token reverts; unexpected balance decrease reverts (errata H-05).
- [ ] NAV-oracle interface on `Dol.sol` available; 5% divergence circuit-breaker tested (errata M-07).
- [ ] Privy SDK configured with OAuth / social-login paths disabled; UI has no non-passkey sign-in entry (errata M-08).
- [ ] RIP-7212 P-256 precompile at `0x0000000000000000000000000000000000000100` exercised; gas cost measured on Base; recorded in ops docs (errata M-09).
- [ ] Factory `pauseNewDeposits` / `pauseNewRecoveries` tested: 72 h auto-expiry verified; second invocation before disclosure window passes reverts (errata M-10).

---

## 16. Marketing Messaging Guardrails

This section is the security-team-approved boundary for public-facing language. Adherence is binding on product, marketing, and customer-facing support.

### 16.1 Do not write

The following phrases must not appear in any public Dol Vault material. Each is accompanied by the reason.

- ❌ "완전한 보안" / "absolute security" / "perfect security" / "complete security"
  *Reason:* false under any of the documented residual risks (§2.3, §13).
- ❌ "절대 뚫리지 않는" / "unhackable" / "can't be broken"
  *Reason:* same.
- ❌ "100% 안전한" / "100% safe"
  *Reason:* numerical overclaim.
- ❌ "은행보다 안전한" / "safer than a bank"
  *Reason:* comparative claim we cannot substantiate and that invites regulatory scrutiny.
- ❌ "양자 컴퓨터도 막는" / "quantum-proof"
  *Reason:* Dol Vault's on-chain ECDSA signing is **not** post-quantum. Any such claim is false. (See §7.7 of `polyvault-security-v3.2-defi.md` for the institutional doc's position on this same asymmetry.)
- ❌ "key loss impossible" / "can never lose your funds"
  *Reason:* passkey loss without guardians = fund loss, per §3 and §5.4.
- ❌ "regulated" / "licensed" in any context where that implies a license Dol does not hold.
- ❌ Any claim of APY / yield rate in a Dol Vault specific surface — yield is a Dol protocol property, not a Dol Vault property.

### 16.2 Recommended phrases

The following are safe, accurate, and carry the intended emotional weight.

- ✅ "은행 금고 수준의 다층 방어" / "bank-vault-level layered defense"
  *Note:* the "수준/level" framing describes the layers' structural depth without making a comparative claim.
- ✅ "키를 잃어도 친구들의 도움으로 되찾을 수 있습니다" / "Even if you lose your device, your friends can help you recover access."
- ✅ "큰돈은 24시간 대기시간으로 한 번 더 보호됩니다" / "Larger amounts are held behind a 24-hour safety window so you have time to cancel if something's wrong."
- ✅ "여러 겹의 보안 장치" / "multiple layers of security."
- ✅ "Passkey로 서명합니다. 시드 문구는 없습니다." / "Sign with your Passkey. No seed phrase."
- ✅ "가족·친구를 Guardian으로 지정할 수 있습니다." / "Designate family or friends as your guardians."
- ✅ "친구가 recovery를 요청하면 반드시 전화로 직접 확인하세요." / "If a friend requests recovery, always call them directly to verify." (Errata H-03; required guardian guidance at onboarding.)
- ✅ "Call your friend directly. Do not approve based on a message alone." — shown to guardians at approval time.

### 16.3 Required disclosures

The following must appear — at least in-app on the onboarding screen that activates Vault tier, and in the ToS — in substantively equivalent language:

1. **Guardian responsibility.** "You choose your own guardians. Dol does not vet them. If you choose guardians who later act against you, and you cannot cancel in time, Dol cannot recover your funds."
2. **Smart-contract risk.** "Your funds are held in a smart contract on Base. Bugs in smart contracts, while audited, remain a possibility. Audits reduce but do not eliminate risk."
3. **Chain-level risk.** "Dol Vault operates on the Base network. Network-wide issues (outages, reorganizations) can affect access to your funds."
4. **OS-level risk.** "Your passkey is protected by Apple's or Google's secure enclave. Compromise of your Apple ID or Google account could allow someone else to sign as you."
5. **Compliance policy (errata H-04).** "Dol may decline to sponsor gas for transfers to sanctioned addresses. This does not prevent the transfer; you may pay gas yourself."
6. **Narrow-scope pause (errata M-10).** "In rare security incidents, Dol may temporarily pause NEW deposits or NEW recovery requests across the product for up to 72 hours. This does not affect your existing balance or any pending transaction you have already started; you can still cancel, execute, or withdraw as normal. Every such pause is publicly disclosed."

### 16.4 Message A/B examples

Copy permutations the marketing team can test, all within the guardrails above.

**Headline A:**
> Dol Vault. A digital vault with friends as backup.
> No seed phrase. No panic. Just Face ID.

**Headline B:**
> Keep your DOL and USDC like a savings account.
> Day-to-day in Hot. Savings in Vault, with a 24-hour safety window.

**Headline C (Korean-native):**
> Dol 금고. 열쇠를 잃어도 친구가 도와줍니다.
> 시드 문구 없이, 얼굴 인식으로.

**Body copy A (feature-led):**
> Deposit USDC, earn yield on your DOL, and sleep well at night. Dol Vault's Hot/Vault tiering lets you spend freely while big amounts are held behind a 24-hour safety window. If you ever lose your device, the guardians you set up — family or close friends — can help you recover access with their approvals.

**Body copy B (user-led):**
> You don't have to be a crypto expert. Dol Vault uses the same Face ID you already trust, not a 12-word seed phrase. When you want to move a lot of money at once, it sits behind a 24-hour window — plenty of time to notice if something's off. And if your phone ever disappears, your closest people help you get back in.

**Body copy C (fear-aware):**
> Cryptocurrency is powerful but unforgiving. Lose your key and it's gone. Dol Vault is built for people who find that scary. Your passkey lives in your phone, not on paper. Your guardians back you up. Your savings sit behind a 24-hour lock. None of it is magic; all of it reduces the one mistake from catastrophic to recoverable.

Any new copy that diverges materially from these patterns requires a security-team review before publication.

---

## 17. Open Questions & Future Work

### 17.1 Open questions (remaining after v0.2 — to be resolved before v1.0)

- **Paymaster rate-limit numerics.** `N_PER_DAY` (default proposal 30) and the per-account value cap (default proposal $10,000 per 24 h) are proposals; final values require usage modeling during mainnet beta.
- **`Dol.sol` NAV oracle interface.** v0.2 commits to the oracle-backed tier valuation (errata M-07), but the specific view-function signature on `Dol.sol` depends on the protocol team's implementation. Dependency tracked; must be finalized before v1.0.
- **Dashboard form-factor.** PWA vs native app. PWA is lighter to ship and update; native offers better push-notification reliability. Decision deferred to the v1.0 transition.
- **SMS notifications.** Email is **required** in v0.2 (errata M-06). SMS remains open: operational cost and delivery reliability across markets argue against v1.0 inclusion; revisited in v2.
- **Keeper sweep frequency.** Daily is proposed; busier usage may push toward hourly. To be calibrated during the first 90 days of mainnet.
- **`initiateHotLimitIncrease` extreme-value UX guardrails.** Should setting a very large Hot limit trigger a secondary confirmation ceremony (e.g., a 7-day timelock above some user-config threshold)? Open; the 24 h timelock addresses the immediate safety problem (errata C-01), but a graded UX may still be warranted.
- **Guardian-invite link transport.** Dashboard-to-dashboard (in-app), SMS, email, or deeplink. UX research needed.
- **Permissionless keeper bounty mechanism.** v0.2 retains a single registered keeper per account (errata H-02). A future bounty-paid permissionless keeper design is desirable but needs a model for preventing grief; deferred to v2.

**Resolved in v0.2** (moved out of this list):

- Oracle choice — resolved by errata M-07 (protocol NAV oracle + 1:1 fallback with 5% circuit breaker).
- Emergency-pause scope — resolved by errata M-10 (narrow-scope factory pause, 72 h cap, public disclosure; existing user actions unaffected).

### 17.2 Future work (post-v1)

- **Integration with the institutional treasury stack (`polyvault-security-v3.2-defi.md`).** The DOL yield paid to vault users originates from the protocol-level treasury. Future coordination: when the institutional treasury rotates master keys (per v3.2 §11), downstream product state (active vault accounts, paymaster) should continue operating uninterrupted.
- **Multichain deployment.** Ethereum mainnet, Arbitrum, Optimism. Each adds deployment surface but no architectural change.
- **ERC-7540 async redemption integration.** Contract affordance exists (§10.4); switch-over depends on `Dol.sol`'s adoption.
- **Guardian-pool mode.** A professional escrow / community-pool guardian as an alternative or supplement to personal guardians. Requires legal and UX investigation.
- **Hardware-wallet guardians.** Ledger or Trezor as a guardian address, for users who want a "cold" guardian slot. Supported by the architecture today (guardians are just addresses); product surface is the missing piece.
- **Passkey rotation UX.** Today rotation means "OS-managed device swap." A dedicated in-app passkey-rotation flow would let users proactively cycle passkeys.
- **Timelock strategies beyond 24 h.** The contract supports any value ≥ 24 h; future UX might let the user define a schedule (e.g., "48 h during vacations").
- **Audit-signature layer.** v3.2 treasury has SPHINCS+ audit signatures over every governance event. A similar, lighter-weight audit log for vault operations would improve transparency for users who want verifiable history.

### 17.3 Known limitations acknowledged

- Dol Vault cannot help a user who has lost both their passkey and all guardians simultaneously. This is by design of non-custodial custody.
- Dol Vault's 24-hour timelock assumes a user who checks their verified notification channel at least every 24 hours during active account management. A user who ignores the channel for an extended window remains exposed.
- On-chain activity is public. A user seeking on-chain privacy should use additional tools outside Dol Vault's scope.

### 17.4 Migration discipline

Any change to the `AccountStorage` layout (§6.3) requires deploying a **new** account contract per user, not an in-place storage migration. v0.2's layout is incompatible with any v0.1 deployment — absolute balances were removed and pending-change slots were added (errata H-05, C-01, H-02). No v0.1 accounts exist yet, so this is a forward-looking discipline rather than a migration cost today; future versions must preserve the rule.

### 17.5 Resolved Findings from v0.1

The following errata entries from `dol-vault-errata-v0.1.md` are resolved in v0.2. Each row points to the section(s) where the resolution lives.

| ID | Severity | Finding | Resolved in |
|---|---|---|---|
| **C-01** | CRITICAL | `setHotLimit` bypasses Vault timelock | §3.3 · §6.3 (storage) · §6.6 (interface) · §6.7 · §6.8 · §8.2 · §9.7 · §11.1 · §13 · §15.6 |
| **H-02** | HIGH | Tier-transfer permissionless, griefable | §6.3 (keeper storage) · §6.6 (setKeeper + rebalance) · §6.7 · §8.3 · §8.5 · §8.6 · §15.6 |
| **H-03** | HIGH | Recovery-hash integrity phishing | §7.3 (step 3 rewrite) · §7.6 · §11.5 UI copy · §13 · §16.2 · §15.6 |
| **H-04** | HIGH | Paymaster sanction-screen ambiguity | §3.3 (point 6) · §6.4 · §16.3 (disclosure 5) |
| **H-05** | HIGH | Balance dual source of truth | §6.3 (ratio-based storage) · §6.6 (`_sync`) · §8.3 · §10.1 · §6.8 · §15.6 |
| **M-06** | MED | Notification channel too soft | §9.6 (rewrite) · §9.7 · §11.1 (Vault activation gate) · §13 · §15.5 · §15.6 · §17.1 |
| **M-07** | MED | Oracle off-peg exploit | §8.4 (worked example + oracle choice) · §8.6 · §17.1 |
| **M-08** | MED | Privy role scope | §5.2 · §11.1 (UI copy) |
| **M-09** | MED | Signature primitive not named | §6.3 (pubkey-hash note) · §6.5 (three-substep validation) · §6.8 · §15.6 |
| **M-10** | MED | Global pause absence | §3.3 (point 2 revision) · §6.6 (`IDolVaultFactory`) · §14.1 · §16.3 (disclosure 6) · §17.1 |

Any new findings discovered before or during external audit will be appended to the errata with incrementing IDs (C-02, H-06, ...) and their resolutions to future v0.X specifications.

---

## 18. References

- Ethereum Foundation. *ERC-4337: Account Abstraction via Entry Point Contract.* EIP-4337.
- Safe (Gnosis Safe) team. *SocialRecoveryModule* — reference implementation of guardian-based recovery for smart-contract accounts.
- W3C. *Web Authentication: An API for Accessing Public Key Credentials — Level 3 (WebAuthn).*
- Privy Documentation. *Passkey and Embedded Wallet SDK.* https://docs.privy.io/
- `polyvault-security-v3.2-defi.md` — the institutional-treasury companion specification; shares this document's design philosophy and several primitives.
- `polyvault-dte-spec.md` — wire-level specification example used as a template for §6 storage layout.
- `polyvault-ceremony-runbook.md` — operational-runbook example used as a template for §14.
- `dol-vault-errata-v0.1.md` — internal review findings that v0.2 resolves (see §17.5).
- Argent. *Guardians: Social Recovery for Self-Custody Wallets* — public design notes.
- Vitalik Buterin. *Why we need wide adoption of social recovery wallets.* 2021.
- NIST. *FIPS 201 / Guidelines on Electronic Authentication* for background on multi-factor authentication models applicable to WebAuthn.
- RIP-7212. *Precompile for secp256r1 Curve Support* — the on-chain P-256 verification primitive used for passkey signatures on Base (errata M-09).
- EIP-4337. *Account Abstraction via Entry Point Contract* — the canonical Base deployment at `0x0000000071727De22E5E9d8BAf0edAc6f37da032`.

---

*This document is a research engineering specification of the Dol project for Dol Vault consumer custody. Does not constitute a security audit or certification. v0.2 is pre-audit and post-internal-review; expect further changes after external audit.*

