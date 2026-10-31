---
note_id: "2026-10-31-d5-threshold-relaxation"
date: "2026-10-31"
author_agent: "dev-orchestrator"
pr_ref: "TBD"  # replaced by the pull-request number when one is opened
supersedes_status_of: "2026-10-28-d5-dilution-band-not-met"
change_scope:
  - "docs/notes/2026-10-31-d5-threshold-relaxation.md"
  - "tests/test_mesh/test_impurity_column.py"
---

# D5: the dilution limit is relaxed to 1 % (owner ruling)

This note records **one** change: the acceptance limit for the top-product
dilution criterion. It does **not** alter the earlier measurement, the case, or
the finding that the delivered criterion is unmet. The earlier note
[`2026-10-28-d5-dilution-band-not-met.md`](2026-10-28-d5-dilution-band-not-met.md)
stays as written and remains the record of the delivered criterion.

## What changed

```
delivered criterion :  r <= z_f      (z_f = 0.5 % for this fixture)   UNMET
adopted limit       :  r <= 0.01     (1 %, owner ruling 2026-10-31)    MET
r = I / (D + I)     =  0.005081300813008131  (0.5081300813 %)
```

`0.005081300813008131 <= 0.01` → **True** (margin 1.97x).

`0.005081300813008131 <= 0.005` → **False** — unchanged, and still asserted
verbatim in the strict-`xfail` test.

## Why the two facts are kept in separate tests

| Test | Asserts | Expected | What a pass means |
|---|---|---|---|
| `test_d5_strict_dilution_band_r_le_zf` | `r <= z_f` (0.5 %) | `xfail` (strict) | nothing — it is recorded as failing |
| `test_d5_relaxed_dilution_band_r_le_1pct` | `r <= 0.01` (1 %) | pass | the adopted limit is met |

Merging them (e.g. replacing the strict test, or relaxing its constant) would
erase the difference between "the delivered criterion was met" and "we adopted a
looser limit that this case meets". The strict test is therefore left intact: a
future change that makes the 0.5 % criterion hold turns it into an `XPASS`, and
with `strict=True` that is a failure, forcing a re-review instead of a silent
change of history.

## What a pass at 1 % does and does not claim

**Claims:**

1. The measured dilution of this case, `0.5081300813 %`, is below the adopted
   1 % limit.
2. Under the adopted limit the equivalent design condition is
   `D/F >= z_f (1 - t) / t = 0.005 * 0.99 / 0.01 = 0.495`; the case sits at
   `D/F = 0.979`, so the margin is structural, not marginal.

**Does not claim:**

1. That the delivered criterion `r <= z_f` is satisfied. It is not:
   `0.508 % > 0.5 %`.
2. That 1 % is the intended design requirement, or that it has a physical or
   contractual basis in this repository. No source in this repo derives a 1 %
   limit; it is a **project-acceptance decision taken by the owner**, and it is
   recorded as such so that it cannot later be read as an engineering
   derivation.
3. That the design point is optimal or plausible at a higher recovery. Raising
   `D/F` to meet the 0.5 % criterion was never attempted (see P1 in the earlier
   note) and its physical plausibility remains unverified.

## Status of the definition question

Relaxing the limit **does not** answer "what was `r <= z_f` meant to apply to?".
The five questions put to the delivery author (operating point, `z_f` basis,
denominator basis, comparison form, and a satisfying operating point) remain
open, because the answer determines whether 0.5 % or 1 % is even the right
quantity to compare. Consequence for reporting:

- the item may be reported as **met under the adopted 1 % limit**;
- it must simultaneously be reported as **not met against the delivered 0.5 %
  criterion**;
- it must not be reported as "D5 satisfied" without both qualifications.

## Provenance of the ruling

Owner instruction of 2026-10-31, verbatim in substance: the reference case's
`0.00508` is only slightly above `0.005`, the requirement is too strict and
essentially already satisfied, so the requirement should be relaxed to `0.01`.
Recorded here because the ruling changes an acceptance limit that originates
outside this repository; the code-side effect is limited to one test constant
(`D5_DILUTION_LIMIT = 0.01`) and one additional test.

## Related

- Delivered criterion and its measurement:
  [D5 dilution band: NOT MET](2026-10-28-d5-dilution-band-not-met.md)
- Impurity post-processing convention and its unverified assumptions:
  [Impurity post-processing: what the convention claims](2026-10-28-impurity-post-processing-assumptions.md)
