# Dol Vault — Errata and Review Findings (v0.1)

**Status:** v0.1 spec pre-audit review findings. To be resolved in v0.2.
**Review date:** 2026-04-17
**Reviewer:** Security review (internal)
**Source document:** `docs/dol-vault-spec-v0.1.md`

> Each finding below has a severity, a description of the issue, the
> scenarios under which the issue manifests, and the required resolution.
> The resolution field defines what v0.2 must look like.

---

## Severity taxonomy

- **CRITICAL** — Release blocker. v0.1 must not reach audit or mainnet until resolved.
- **HIGH** — Structural issue. Could lead to exploitation or design incoherence.
- **MEDIUM** — Design improvement. Resolvable before external audit.

---

## CRITICAL

### C-01 — `setHotLimit` bypasses Vault timelock

**Location:** §8.2 ("Threshold policy"), §6.6 (`setHotLimit` interface)

**Finding.** `setHotLimit` is currently authenticated by passkey alone with no timelock. An adversary who obtains the user's passkey for any duration can raise `hotLimitUsd` to an arbitrary high value, trigger automatic rebalancing that moves the entire Vault balance into Hot tier, and then call `withdrawHot` for the full balance. All three steps require only passkey signatures. **The 24-hour Vault timelock is completely bypassed.**

The current spec's justification ("a thief with the passkey who raises Hot limit then withdraws is the same attack surface as withdrawing from the Vault directly") is incorrect. The entire point of the Vault tier is that a short-term passkey compromise does not immediately drain funds, because the user has 24 hours to cancel. `setHotLimit` without a timelock eliminates this protection.

**Attack walkthrough:**

1. Attacker obtains user's passkey (stolen unlocked device, phishing, brief access).
2. `setHotLimit(1_000_000_000)` → succeeds immediately.
3. Keeper sweep or user-action-triggered rebalance moves full Vault → Hot (same-account state transition, no external check).
4. `withdrawHot(total_balance, to=attacker)` → succeeds immediately.
5. Total time: seconds. User has no cancellation window.

**Resolution required in v0.2.**

- `setHotLimit` must apply a **24-hour timelock when *raising* the limit**. Lowering the limit (strengthening protection) remains immediate.
- Introduce `initiateHotLimitIncrease(uint256 newLimit)` and `executeHotLimitIncrease(uint256 requestId)` as a two-step flow with 24h delay, using the same state machine pattern as Vault withdrawal.
- `cancelHotLimitIncrease(uint256 requestId)` mirrors `cancelWithdraw`.
- Storage layout change: add a pending-hot-limit-change slot, analogous to the pending-recovery slot.
- §8.2, §6.3, §6.6, §6.7, §6.8, §9.7, §11 (flow for changing limits), §13, §16 (if it changes any user-facing copy) — all updated.

**Failure-mode table entries to add (§6.8, §9.7, §13):**

| Assumption | Violation | Effect |
|---|---|---|
| Hot limit cannot be raised without timelock | setHotLimit has no delay | Passkey thief raises Hot limit, rebalances Vault → Hot, drains immediately. v0.1 bug; fixed in v0.2 by two-step timelock. |

---

## HIGH

### H-02 — Tier transfer permissionless, griefable paymaster

**Location:** §8.3 ("Automatic rebalancing"), §8.6 (failure modes)

**Finding.** Tier-transfer functions are declared "public and authorization-free." An attacker can repeatedly trigger rebalance on arbitrary accounts (or on their own by oscillating micro-deposits) to drain the paymaster through sponsored keeper calls. §8.6 acknowledges this at a high level but mitigation ("rate limits apply to the keeper as well") is insufficient — the attacker can distribute calls across many accounts.

**Resolution required in v0.2.**

- Restrict tier-transfer functions to `onlyOwner` OR `onlyKeeper` where `keeper` is an authorized address registered at account deployment time.
- Keeper address is settable only by `onlyOwner` via the standard governance-change timelock (24h).
- §8.3 revised: "Permissionless decentralization of the keeper role is deferred to v2, when a bounty mechanism can prevent grief attacks."
- §8.6 failure mode updated to reflect the new access control.

### H-03 — `newOwnerPubKeyHash` integrity in recovery flow is user-verifiable only

**Location:** §7.3 (recovery flow steps 1–3), §7.6 (malicious scenarios)

**Finding.** When a user initiates recovery, the guardian receives `newOwnerPubKeyHash` via a link. A phishing page between the user and guardian can substitute the hash for the attacker's. The guardian cannot distinguish the legitimate 32-byte hash from an attacker's. This is a documented real-world failure mode in other social-recovery wallets.

**Resolution required in v0.2.**

- §7.3 adds an explicit **verbal verification step** between user and guardian:
  > Before approving, the guardian MUST contact the user through an
  > out-of-band channel (phone call, in-person, known-trusted messaging)
  > and verify the first 8 and last 8 hex characters of the recovery hash.
- The guardian approval UI displays these 16 characters in a large, prominent format, separated from the rest of the hash.
- §7.3's step 3 rewritten to include this verification as a gating step in the UX.
- §16.1 adds a corresponding user-facing guidance entry: guardians are told during onboarding that they must verify out-of-band.
- §16.2 adds recommended copy: "Call your friend directly. Do not approve based on a message alone."
- A parallel §7.6 row is added: "Phishing page substitutes hash during recovery invitation → defense is verbal out-of-band verification."

### H-04 — Paymaster sanction screening creates non-custodial ambiguity

**Location:** §6.4 (paymaster policy point 4), §3.3 (non-custodial definition)

**Finding.** §6.4 authorizes the paymaster to refuse sponsorship for outbound transfers to sanction-flagged recipients. §3.3 defines "non-custodial" as "no operator signature suffices to move user funds." These are not strictly contradictory (the user can pay their own gas), but the marketing posture and audit framing depend on consistency.

**Resolution required in v0.2.**

- §6.4 explicitly states that sanction screening is a **sponsorship policy, not a transfer restriction**. The contract's `withdraw*` functions have no sanction check. The user retains the ability to execute any transfer by paying their own gas (user-paid UserOp or direct EntryPoint interaction per §12.3).
- §3.3 adds a fifth clarification:
  > Dol's compliance policies (paymaster sponsorship) may decline to
  > subsidize specific operations. They do not restrict the user's
  > ability to execute those operations at the user's own cost.
- §16.3 Required disclosures adds a fifth:
  > **5. Compliance policy.** "Dol may decline to sponsor gas for
  > transfers to sanctioned addresses. This does not prevent the
  > transfer; you may pay gas yourself."

### H-05 — Balance tracking dual source of truth

**Location:** §6.3 (storage layout), §10.1 (user-facing flows)

**Finding.** The account's storage duplicates ERC-20 balance tracking (`hotBalanceDol`, `vaultBalanceUsdc`, etc.) alongside the actual ERC-20 contract state. Direct ERC-20 transfers into the account address (a normal thing that happens on EVM) leave the storage counters stale. Rebalancing based on stale counters is incorrect; worse, tier enforcement could be circumvented.

**Resolution required in v0.2.**

- Storage retains only **partition ratios**, not absolute amounts:
  ```solidity
  uint16 vaultRatioBps;  // portion of balance assigned to Vault (0..10000)
  ```
- Absolute balances are computed at call time from `IERC20(asset).balanceOf(address(this))` multiplied by the ratio.
- A `_sync()` internal hook is called at the start of every balance-reading function:
  - If token balance increased since last seen, the delta is assigned to **Hot** (direct transfers are treated as Hot deposits by default).
  - If token balance decreased (shouldn't happen outside executed withdrawals), an event is emitted and the function reverts — this catches any bug in the internal accounting.
- §10.1 adds a user-facing note: "If you send USDC directly to your vault address, it will appear in your Hot tier. Deposits made through the app are allocated per your Hot/Vault split."
- §6.3 storage layout updated.
- §6.8 adds failure mode:
  | Balance sync hook works | Direct transfer of a non-ERC-20-compliant token causes sync to misread | External tokens outside the allowlist (DOL, USDC) are rejected; this is already policy in §10.5 but is now enforced in sync as well. |

---

## MEDIUM

### M-06 — Notification channel enforcement too soft

**Location:** §7.4, §9.4, §11.1 (onboarding), §13, §15.5

**Finding.** Defense against malicious recovery and Vault drain depends entirely on the user receiving a notification within 24 hours and acting. The spec treats push notifications as primary, email as optional, SMS as unsupported in v1. PWA installation rates in the target demographic are low; email delivery is unreliable for transactional alerts. In practice, a meaningful fraction of users will have no working channel when recovery is attempted against them.

**Resolution required in v0.2.**

- §11.1 onboarding flow modified: **Vault tier activation is gated on at least one verified notification channel.** Email is the minimum; verification is a one-click confirmation link.
- §15.5 Deployment checklist adds: "Email deliverability tested to major Korean providers (Naver, Daum, Kakao mail) in addition to Gmail/Apple/Outlook."
- §13 table updated: "User offline ≥ 24h with no notification channel" removed from residual-risk-user-responsibility and added to "configuration prevented by the product" — because the product now refuses to enable Vault without a channel.
- §9.6 rewritten: the "user unreachable" scenario now applies only to users who ignore their verified channels, not to users who never had one.
- §17 Open Questions updates: SMS remains open; email is now required.

### M-07 — Oracle off-peg exploit scenarios not modeled

**Location:** §8.4 (oracle design), §8.6 (failure modes)

**Finding.** The v0.1 assumption "DOL = 1 USDC" means Hot/Vault split is maintained in *nominal* DOL/USDC units, not USD value. If DOL trades off-peg (even briefly), the split becomes wrong in USD terms. A passkey thief during off-peg window captures more USD value from Hot than the user intended.

**Resolution required in v0.2.**

- §8.6 adds explicit failure mode: "DOL off-peg temporal arbitrage by passkey-compromised attacker." With worked example.
- §8.4 states that the 1:1 assumption is **a deliberate simplification for v0.1**, and that v0.2 introduces an oracle-backed tier valuation using:
  - Primary: the protocol's NAV oracle (read from `Dol.sol`'s view function once that interface is public).
  - Fallback: a time-weighted USDC/USDC identity oracle set to 1:1 with a circuit-breaker that triggers if any future DOL oracle reads diverge by more than 5%.
- §17 Open Questions: the specific oracle interface to `Dol.sol` moves from "open" to "to be defined by Dol team by v0.2 release; dependency tracked."

### M-08 — Privy role scope not declared

**Location:** §5 (Layer 1), §11.1 (onboarding)

**Finding.** Privy's product surface includes OAuth/social-login-based embedded wallets. Readers may wonder whether Dol Vault supports email/social login as a fallback authentication path. If yes, the trust model in §3.1 is incomplete (OAuth provider becomes a second root of trust). If no, the spec must declare it.

**Resolution required in v0.2.**

- §5.2 new paragraph:
  > Dol Vault uses Privy exclusively for WebAuthn (passkey) credential
  > provisioning and cross-device sync coordination. Privy's OAuth /
  > social-login / embedded-wallet fallback paths are NOT enabled for
  > Dol Vault accounts. The user's passkey is the sole authentication
  > path; there is no email-login, no SMS-login, no Google-account
  > fallback. This preserves the single-root-of-trust property of
  > §3.1.
- §11.1 Flow 1 clarifies that the only button is "Create with Face ID" — no "Sign in with Google" alternative is offered.

### M-09 — Signature verification primitive not named

**Location:** §6.3 (storage: `ownerPubKeyHash`), §6.5 (validation flow)

**Finding.** WebAuthn signatures are P-256 (ECDSA over secp256r1), not secp256k1. Base supports the RIP-7212 P-256 precompile at address `0x100`. The spec stores a hash of the public key but never states how verification works. Auditors and implementers need the primitive choice explicit.

**Resolution required in v0.2.**

- §6.3 adds a note on storage:
  > `ownerPubKeyHash` is the SHA-256 hash of the concatenated P-256
  > public key coordinates (x ∥ y, 64 bytes), stored to save storage
  > space. The full public key is passed as a calldata parameter in
  > each validateUserOp call; the account contract verifies (a) the
  > passed key hashes to the stored value, (b) the signature validates
  > under that key via the RIP-7212 P-256 precompile at `0x0000...100`
  > on Base.
- §6.5 validation flow step ("check signature against ownerPubKeyHash") expanded to three sub-steps: hash check, P-256 precompile call, `validAfter`/`validUntil` return.
- §6.8 failure mode added:
  | RIP-7212 precompile behavior stable | Base upgrades P-256 precompile with breaking change | Signatures fail; user locked out. Mitigation: monitor Base upgrade announcements; contract migration path via recovery if needed. |

### M-10 — Global pause absence is operationally untenable at scale

**Location:** §14.1 Class A incident response

**Finding.** The spec rejects any global pause mechanism on the grounds that it would be custodial. For per-account emergencies this is correct. For a contract-level vulnerability affecting all accounts, "each user must pause individually" is not a workable incident response; many users will not check the app in time, and the attacker iterates.

A **narrow-scope pause** — affecting only new deposits and new recovery initiations — is not a custody violation. It freezes no existing assets; cancellable pending actions (cancel, execute-already-past-timelock) still work.

**Resolution required in v0.2.**

- §14.1 Class A response adds a new mechanism:
  > Dol team multisig (3-of-5) has authority to call `pauseNewDeposits()`
  > and `pauseNewRecoveries()` on the account factory. These halt new
  > user-facing flows at the product surface. Existing user actions
  > (cancel pending, execute matured, withdraw Hot, withdraw Vault after
  > timelock) remain fully functional.
  >
  > This authority cannot:
  > - Freeze any existing user balance
  > - Cancel a user's pending action
  > - Change any user's ownerPubKeyHash or guardians
  > - Extract any user funds
  >
  > The multisig is rate-limited at the factory: after any pause is
  > invoked, there is a mandatory 72-hour public-disclosure window
  > before the pause can be renewed. This prevents silent indefinite
  > pauses.
- §3.3 "Non-custodial" definition updated: point 2 revised:
  > No operator signature suffices to move user funds, cancel user
  > actions, or change account authentication. Operators may halt
  > NEW flows (deposits, recovery initiations) for up to 72 hours
  > at a time, with public disclosure.
- §16.3 Required disclosures updated accordingly.
- §17 Open Questions removes "global pause scope"; it is resolved here.

---

## Cross-cutting adjustments

Beyond the findings above, v0.2 must also:

- Update the **document header banner** to note: "v0.2 — resolves findings C-01 through M-10 from `dol-vault-errata-v0.1.md`."
- Add an **§18-equivalent "Errata Log"** section tracking which findings are resolved. Each finding references the v0.2 section where the resolution lives.
- Bump references to "v0.1" inside the document to "v0.2" where the reference is to this document itself; retain "v0.1" where referencing the prior version.
- Add an explicit **migration note** for any users (none exist yet, but for the pattern): changing the account's storage layout requires a new account deployment, not an in-place upgrade.

---

*Errata log maintained by the Dol security team. Any new findings discovered before or during external audit will be appended with incrementing identifiers (C-02, H-06, ...). Findings already resolved in v0.2 will carry a `[RESOLVED in v0.2 §X.Y]` annotation in place.*
