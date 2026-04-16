# Verification Findings

**Date:** 2026-04-16
**Suite:** `pytest verification/`

---

## Resolved Findings

These issues were identified during automated verification and have been corrected in this repository.

### 1. PolyShard Vector B Share Values (CRITICAL — resolved)

Share values for i=2..5 in `polyshard-security.md` did not match `f(x) = s + a_1*x + a_2*x^2 mod (2^61 - 1)`. Corrected with independently computed values. See erratum note in the document.

**Test:** `verification/test_doc1_polyshard.py::TestPS3_FINDING_DocumentError`

### 2. Operational ES Buffer Arithmetic (MODERATE — resolved)

Per-category operational ES sums to 5.11M. The capital table previously stated "Operational ES x 1.2 = 5.9M", but 5.11 * 1.2 = 6.13M. Corrected to 6.13M; Required Capital and CAR updated accordingly.

**Test:** `verification/test_real_crossdoc.py::TestCADFOperationalES`

---

## Verification Coverage

See [README.md](./README.md#verification) for the full coverage table.
