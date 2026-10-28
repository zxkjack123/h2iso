---
note_id: "2026-10-28-d5-dilution-band-not-met"
date: "2026-10-28"
author_agent: "dev-orchestrator"
pr_ref: "TBD"  # replaced by the pull-request number when one is opened
change_scope:
  - "docs/notes/2026-10-28-d5-dilution-band-not-met.md"
  - "tests/test_mesh/test_impurity_column.py"
---

# D5: the top-product dilution criterion is NOT MET

## Criterion (as defined, verbatim)

Let `r` be the relative dilution of the top product by the non-condensable and
`z_f` the helium fraction of the **total** feed (impurities included):

```
criterion:  r <= z_f          (literal, NO tolerance)
r        =  I / (D + I)       I = impurity flow leaving with the top product
                              D = main-component top-product flow
```

The denominator is the **total flow including impurities**, and the comparison
is strict: no tolerance, no rounding, no "approximately equal" escape hatch.

## Recalculation for the reference case

```
F  = 80.357 mol/h          total feed (fixture)
z_f = 0.005                He-4 fraction of the total feed
I  = z_f * F = 0.401785 mol/h
D  = 0.979 * F = 78.669503 mol/h
r  = I / (D + I) = 0.5081300813 %
```

`r <= z_f` evaluates to `0.005081300813008131 <= 0.005` → **False**.

Equivalence (valid because `I = z_f * F` holds exactly for this case):

```
r <= z_f   <=>   D/F >= 1 - z_f = 0.995
```

The case has `D/F = 0.979`, which is below `0.995`. The violation is therefore
**structural**, not a rounding artefact: with `D < F`, the impurity fraction of
the top product is always larger than its fraction of the feed unless the
distillate takes at least `1 - z_f` of the feed.

## Conclusion

**NOT-MET.** The criterion above is not satisfied by the reference case, and no
tolerance or approximation may be used to report it as satisfied.

An earlier statement that "0.508 % is consistent with 0.5 %" was wrong and has
been withdrawn: `0.5081300813 %` is strictly greater than `0.5 %`.

The test suite encodes this state rather than hiding it: the criterion is
asserted verbatim in a strict-`xfail` test, which fails under
`pytest --runxfail` with `assert 0.005081300813008131 <= 0.005`. A strict
`xfail` turns into `XPASS` (and therefore a failure) if the criterion ever
becomes true, so the gap cannot silently disappear.

## Reconciliation paths — MUTUALLY EXCLUSIVE

Exactly one of the following applies. They are MUTUALLY EXCLUSIVE because each
changes a different object: the case, the reading of the criterion, or the
criterion itself.

## P1 — Design side: raise `D/F` to >= 0.995

- **What:** change the case/design parameter (`distillate/feed` 0.979 -> >= 0.995;
  this case needs `D >= 79.955 mol/h`, i.e. `+1.29 mol/h` of distillate) so that
  `r <= z_f` holds literally.
- **Consequences:**
  1. This changes the design/case, **not the criterion**: criterion and measured
     quantity stay as defined above.
  2. It departs from the original reference-case operating point: the
     `distillate_to_feed_ratio = 0.979` of the impurity fixture is identical to
     the plain reference fixture and is pinned by a provenance test, so a new
     fixture would be required and the original NOT-MET conclusion must be kept
     (a new case may not overwrite the old conclusion).
  3. Physical plausibility of the new case (can a 0.995 recovery be reached at
     reflux ratio 15 within 75 stages?) is **unverified** and needs its own
     convergence evidence — outside the scope of this batch.
- **Requires a user ruling:** yes (changing the case changes the delivered object).
- **Evidence:** the equivalence above plus the measured `D/F`.

## P2 — Reading side: confirm what the criterion applies to; record NOT-MET as-is

- **What:** no code, criterion or case change. Record this case as `NOT-MET` and
  escalate "which case / which measured quantity should this criterion apply
  to?" as a user ruling.
- **Consequences:**
  1. The only action is an honest record: a strict-`xfail` test plus this note,
     so the package stays re-runnable.
  2. The criterion is neither weakened nor approximated: `0.5081 % > 0.5 %` stays
     visible forever.
  3. The deliverable stays `DEFINED-NOT-MET` on this item; it does not create a
     false impression that the criterion has been met.
  4. Cost: the item is not "solved", only defined precisely and not overstated.
- **Requires a user ruling:** yes (which object/quantity the criterion applies to
  is a definition question).
- **Evidence:** `r = I / (D + I)` is the only quantity derivable from this
  measurement; `z_f = 0.5 %` is a **feed** mole fraction. Treating a feed
  fraction as an upper bound on a **product** fraction is structurally
  unsatisfiable whenever `D < F` (unless `D/F >= 1 - z_f`), which suggests the
  criterion may have been matched to the wrong object (a feed-side quantity
  compared with a product-side quantity).

## P3 — Assertion side: replace the criterion with a conservation identity

- **What:** delete `r <= z_f`, replace it with a conservation/identity assertion
  (e.g. `y_He,top == I / (D + I)` on the total-flow basis, or
  `I == sum of top-product impurity flows`), and remove every "< 0.5 %"
  statement.
- **Consequences:**
  1. This **changes the user-defined criterion** and is therefore a criterion-level
     (D2) decision that must be ruled on separately; it must not be executed on
     the strength of this note.
  2. If adopted, the item changes from "not met" to "criterion replaced"; the
     deliverable must then disclose both the old and the new criterion,
     otherwise it is criterion drift.
  3. Risk: an identity assertion never fails for any valid input, so as an
     acceptance gate it is **empty**; it must be paired with an explicit
     "this is not the acceptance criterion" statement and must never be used to
     claim a pass.
- **Requires a user ruling:** yes — this path is out of scope by construction and
  must not be implemented without one.
- **Evidence:** `r` is identically `I / (D + I)`; the same identity already exists
  in the test suite as `test_exact_dilution_identity`.

## Ruling status

**PENDING USER RULING (D2).** The reconciliation path is a decision for the
project owner, not for the implementation. The criterion itself may not be
changed, and the case may not be swapped, without that ruling. Until then:

- this item stays `NOT-MET`;
- no path may be described as satisfying the criterion;
- the strict-`xfail` test stays in place as the visible reminder.

## Related

- The impurity post-processing convention and its four unverified assumptions:
  [Impurity post-processing: what the convention claims](2026-10-28-impurity-post-processing-assumptions.md)
