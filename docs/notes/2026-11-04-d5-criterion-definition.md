---
note_id: "2026-11-04-d5-criterion-definition"
date: "2026-11-04"
author_agent: "dev-orchestrator"
pr_ref: "9"
supersedes_status_of: "2026-10-31-d5-threshold-relaxation"
change_scope:
  - "docs/notes/2026-11-04-d5-criterion-definition.md"
  - "tests/test_mesh/test_impurity_column.py"
---

# D5: the criterion definition is settled in-repo (the clarification request is withdrawn)

The earlier note
[`2026-10-31-d5-threshold-relaxation.md`](2026-10-31-d5-threshold-relaxation.md)
left the *definition* of the criterion open and listed five questions for the
delivery author. This note closes that status: the criterion is restated here in
a self-contained form, and the five questions are answered from material already
in hand. **No numeric limit, case, or measurement changes.** The change is a
wording/definition one, plus a broken cross-reference fix.

The deliverer-facing clarification draft
(`D5-definition-clarification-DRAFT-v2.docx`, `sha256 5af611d1…e5383`) is
**withdrawn and is not to be sent**. Its only upload was a Feishu-side draft
record; it was never forwarded to the delivery author.

## The criterion, restated

Let

```
r  ≡  x_He,top  =  I / (D + I)          top-product impurity mole fraction (flow-weighted)
I  =  z_f * F                            impurity flow riding with the top product
D  =  d * F                              main-component top-product flow,  d = D/F
z_f                                      impurity (He-4) fraction of the TOTAL feed
```

`r` is **not** a free design output. Because He-4 is non-condensable
(`to_top = 1`) and `I = z_f * F` holds exactly, `r` is fixed by a flow balance:

```
r  ≡  z_f * F / (D + I)  =  z_f / (d + z_f)          (identity, not a performance metric)
```

For this fixture (`F = 80.357`, `d = 0.979`, `z_f = 0.005`, `B/F = 0.016`):

```
r                              = 0.5081300813 %        structural lower bound for this flowsheet
E  ≡ r / z_f                   = 1.01626
adopted limit   r <= 2 * z_f   = 1 %                   (identical to the 2026-10-31 ruling)
margin t / r                   = 1.968x
equivalent design condition    d >= z_f (1 - t) / t = 0.495      (case sits at 0.979)
```

**The adopted 1 % limit is exactly `2 * z_f` for this fixture.** It is the
statement "the top product's impurity mole fraction may not exceed twice the
feed's impurity mole fraction", `E <= 2`. No tolerance below the structural
lower bound (`0.5081301 %`) is reachable at this flowsheet, because reaching
`r <= z_f` would require `d >= 1 - z_f = 0.995` — i.e. the top taking
essentially the entire feed.

## The five questions, answered

| # | Question | Answer | Basis |
|---|---|---|---|
| 1 | Which operating point is the criterion meant to bound? | **The delivered reference case itself** (CD2, `D/F = 0.979`, reflux 15, 75 stages). The task wording names no other point; the deliverer implemented and locked tests on this case; acceptance is therefore taken on this case. The "some other operating point" branch is void. | Task wording has no operating point; fixture + locked tests define it |
| 2 | Is `z_f` the fraction of the total feed, or of the main-component feed? | **Fraction of the TOTAL feed** (`z_f = 0.005` of `80.357 mol/h`). The `I = z_f * F` identity is what the delivered code and tests assert; no main-component-relative reading has any support. | Fixture definition; identity asserted in `test_exact_dilution_identity` |
| 3 | Denominator `D + I` or `D` alone? | **`D + I`** (flow-weighted top flow). The delivered `dilute_top_product()` is flow-weighted; there is no implementation of the `D`-only reading. Both clear the adopted limit (`0.5081 %` vs `≈0.5107 %`). | Delivered implementation |
| 4 | Mole-fraction comparison, or a *relative* dilution figure? | **Mole-fraction comparison — and the two coincide.** Under the delivered assumptions the relative change is not a second quantity: `rel_change ≡ I/(D+I) = r` exactly (the delivered script notes "dilution equals the He fraction by construction (flow-weighted)"). No separate definition is needed. A distinct quantity would require `to_top < 1` or `I ≠ z_f * F`, neither of which holds here. | Delivered `dilute_top_product()`; script self-note |
| 5 | Which operating point satisfies the original criterion, and is it required or optional? | **N/A — not pursued.** Reaching `r <= z_f` needs `D/F >= 0.995`, which conflicts with this fixture's own `x_D2,top > 0.999` assertion; changing the case to pass a criterion is not done. The original `r <= z_f` stays on record and is not an acceptance item. | `D/F` vs `x_D2,top` conflict (see `2026-10-28` note, P1) |

## What is kept, what changed

**Kept (verbatim, unchanged):**

1. the delivered criterion `r <= z_f`, encoded as a **strict `xfail`**
   (`test_d5_strict_dilution_band_r_le_zf`) — a future XPASS is a failure and
   forces re-review;
2. the numeric limit `D5_DILUTION_LIMIT = 0.01`;
3. the reference case, the fixture, and the `x_D2,top > 0.999` assertion;
4. the 2026-10-28 and 2026-10-31 notes as written (historical record).

**Changed:**

1. the limit's statement is now `r <= 2 * z_f` (`E <= 2`), numerically identical
   to 1 % for this fixture;
2. the clarification draft is withdrawn (above);
3. a broken cross-reference to the 2026-10-31 note is corrected in
   `tests/test_mesh/test_impurity_column.py` (the file is
   `2026-10-31-d5-threshold-relaxation.md`; the test named a
   `…-dev-orchestrator-…` variant that does not exist).

## What this note does and does not claim

**Claims:** the definition is settled in-repo; the item is met under the adopted
`r <= 2 * z_f` limit; the delivered `r <= z_f` is still not met.

**Does not claim:** that the 0.5 % figure was ever a reachable design
requirement; that `r` measures column *performance* — under this flowsheet it is
a flow-balance identity; that the 1 % bound has an engineering derivation in
this repository (it is a project-acceptance decision).

## Related

- Delivered criterion, NOT MET:
  [D5 dilution band: NOT MET](2026-10-28-d5-dilution-band-not-met.md)
- Limit relaxed to 1 % (owner ruling); its "definition question open" status is
  superseded by this note:
  [D5 threshold relaxation](2026-10-31-d5-threshold-relaxation.md)
- Impurity post-processing convention and its unverified assumptions:
  [Impurity post-processing: what the convention claims](2026-10-28-impurity-post-processing-assumptions.md)
