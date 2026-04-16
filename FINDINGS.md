# Verification Findings

**Date:** 2026-04-16
**Suite:** `pytest verification/` (209 tests, 209 passed)

---

## Resolved Findings

These issues were identified during automated verification and have been corrected in this repository.

### 1. PolyShard Vector B Share Values (CRITICAL — resolved)

Share values for i=2..5 in `polyshard-security.md` did not match `f(x) = s + a_1*x + a_2*x^2 mod (2^61 - 1)`. Corrected with independently computed values. See erratum note in the document.

**Test:** `verification/test_doc1_polyshard.py::TestPS3_FINDING_DocumentError`

**How it was found:**

```python
# Independent polynomial evaluation for each shard index
p = (1 << 61) - 1  # 2^61 - 1 = 2305843009213693951
s, a1, a2 = 9876543210, 1234567890, 3456789012

for i in range(1, 6):
    y = (s + a1 * i + a2 * i * i) % p
    # i=1: 14567900112 (matched document)
    # i=2: 26172835038 (document said 25810146926 — delta +362,688,112)
    # i=3: 44691347988 (document said 40382283940 — delta +4,309,064,048)
    # i=4: 70123438962 (document said 58284311154 — delta +11,839,127,808)
    # i=5: 102469107960 (document said 79516228568 — delta +22,952,879,392)
```

Errors grow quadratically with i, consistent with the a_2 * i^2 term being computed differently in the original document. All C(5,3) = 10 Lagrange recovery combinations were tested with corrected values — all recover s = 9,876,543,210.

### 2. Operational ES Buffer Arithmetic (MODERATE — resolved)

Per-category operational ES values from CAD-F Table 4.1:

```
Oracle manipulation:    0.34M
Smart contract bug:     0.88M
Exchange insolvency:    3.12M
Regulatory shutdown:    0.48M
Key management failure: 0.29M
────────────────────────────
Total C_op:             5.11M
```

The capital table previously stated "Operational ES x 1.2 = 5.9M", but `5.11 * 1.2 = 6.132M`. The actual multiplier was `5.9 / 5.11 = 1.155`, not 1.2 as stated. Corrected to 6.13M; Required Capital updated from 32.79 to 33.02, CAR from 1.19 to 1.18.

**Test:** `verification/test_real_crossdoc.py::TestCADFOperationalES`

---

## Verification Methods

### Symbolic Verification (SymPy)

The premium feedback SDE Jacobian and characteristic polynomial were verified by symbolic differentiation:

1. Defined drift functions `f_V, f_L, f_C` from the SDE in the whitepaper
2. Computed `J[i,j] = d(f_i)/d(x_j)` via `sympy.diff`
3. Compared the resulting 3x3 matrix element-by-element against the whitepaper's stated J
4. Computed `det(sI - J)` symbolically, expanded, extracted coefficients a1, a2, a3
5. Verified `simplify(a_computed - a_claimed) == 0` for all three

Result: Jacobian and polynomial match. Routh-Hurwitz conditions (a1 > 0, a3 > 0, a1*a2 > a3) were verified to hold for 1000 random positive parameter samples.

**Test:** `verification/test_real_jacobian.py`

### Monte Carlo Cross-Validation

| Computation | Paths | Steps | Seed | Result |
|-------------|-------|-------|------|--------|
| Semi-Markov P(0->2, 72h) | 100,000,000 | n/a | 12345 | Matches analytical 2.0e-6 within standard error |
| GBM barrier d=0.05 | 1,000,000 | 5,000 | 42 | Matches closed-form within 3 SE |
| GBM barrier d=0.10 | 1,000,000 | 5,000 | 42 | Matches closed-form within 3 SE |
| GBM barrier d=0.15 | 1,000,000 | 5,000 | 42 | Matches closed-form within 3 SE |
| GBM barrier d=0.20 | 1,000,000 | 5,000 | 42 | Matches closed-form within 3 SE |
| GBM barrier d=0.27 | 1,000,000 | 5,000 | 42 | Matches closed-form within 3 SE |
| GBM barrier d=0.35 | 1,000,000 | 5,000 | 42 | Matches closed-form within 3 SE |

The semi-Markov analytical formula was also independently derived via numerical convolution integral (`scipy.integrate.quad`) — residual < 1e-12.

**Tests:** `verification/test_real_semimarkov.py`, `verification/test_real_mdlw_pricing.py`

### Independent Polynomial Evaluation

PolyShard test vectors were verified by implementing Lagrange interpolation from scratch (modular inverse via Fermat's little theorem, not using any crypto library) and testing all C(5,3) = 10 shard combinations for both Vector A (p=7919) and Vector B (p=2^61-1).

**Test:** `verification/test_doc1_polyshard.py`

---

## What Is Not Verified

The following are explicitly out of scope for this automated suite:

- Whether any model (EVT, Hawkes, copula, SDE) is the *right* model for this protocol
- Whether calibrated parameters reflect real market conditions
- Whether production code matches the whitepaper formulas
- Whether the Panjer frequency parameters are correctly estimated from empirical data
- Whether the pricing engine produces fair premiums vs. market
- Whether the system is actually stable (only that the stated stability conditions are internally consistent)

These require empirical validation with production data, independent audit, or both.

---

## Verification Coverage

See [README.md](./README.md#verification) for the full coverage table with per-test classifications.
