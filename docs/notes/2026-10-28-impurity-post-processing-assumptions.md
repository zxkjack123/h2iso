---
note_id: "2026-10-28-impurity-post-processing-assumptions"
date: "2026-10-28"
author_agent: "dev-orchestrator"
pr_ref: "TBD"  # replaced by the pull-request number when one is opened
change_scope:
  - "docs/api/impurities.md"
  - "docs/notes/2026-10-28-impurity-post-processing-assumptions.md"
  - "src/h2iso/impurity_routing.py"
  - "src/h2iso/impurities.py"
---

# Impurity post-processing: what the convention claims, and what it does not

## What this layer is

The impurity extension (`h2iso.impurities`, `h2iso.impurity_routing`,
`h2iso.purge`) is an **experimental post-processing convention**, not a physical
acceptance of impurity transport. Non-condensable helium is carried along the
solved vapour path as a tracer; freezing species are split between a
dissolved-trace allowance and a "frozen" remainder. Nothing in this layer
changes the six-component MESH solution, and no claim here is a validation of
where an impurity physically ends up.

Terminology used below: a **terminus** is any place a tracer leaves the
flowsheet — a condenser purge branch, a declared product stream, or a leaf
stream that the topology neither connects nor declares.

## The four unverified assumptions

1. **`UNVERIFIED` — CO/CH4 solubility cap is zero.** No published solubility of
   CO or CH4 in liquid hydrogen was located, so the cap is set to `0.0`
   ("fully frozen"). That is a modelling choice for the missing datum, not a
   measured value.
2. **`UNVERIFIED` — classification ignores concentration.** `classify_species()`
   decides from the operating temperature window alone (`T_min > T_c` → top,
   `T_min < T_tp` → frozen). It implements no solubility- or
   saturation-limited criterion, so a trace and a bulk amount classify
   identically.
3. **`UNVERIFIED` — `frozen_mol_h` is bookkeeping, not equilibrium.**
   `frozen_mol_h = impurity flow − dissolved trace` is an accounting
   allocation. It is not a solid-phase equilibrium solution and does not predict
   deposition location, accumulation over time, or plugging.
4. **`UNVERIFIED` — there is no feedback.** The layer runs on a converged
   six-component MESH solution and does not feed back into temperature, flow or
   composition profiles. That the influence of trace impurities is negligible is
   itself an assumption; it has not been demonstrated.

A triple point only bounds where a pure substance solidifies. It does not prove
that a trace of CO, CH4 or N2 freezes out completely at any concentration, and a
critical temperature above the operating window does not by itself prove zero
solubility. Both statements are therefore kept as model assumptions.

## Terminal-stream semantics (`status == "vent"`, `enters_vent`, `terminal_kind`)

`status == "vent"` means **"reached a terminal stream"** — nothing more. It
covers a declared product end and an undeclared leaf, and it does *not* mean the
impurity entered a vent.

`ImpurityRoute.enters_vent` returns `status in ("vent", "product")`. That makes
it `True` for a plain product end and `False` for a real condenser purge branch
(`status == "purge"`), so it cannot answer "did the impurity enter a vent?". The
attribute is retained unchanged for backward compatibility and is documented as
deprecated and misleading.

The unambiguous replacement is `ImpurityRoute.terminal_kind`, with three
mutually exclusive values plus `None`:

| `terminal_kind` | meaning |
|---|---|
| `"purge_branch"` | routed into a real condenser purge branch |
| `"declared_product_end"` | reached a stream declared in `config.products` |
| `"undeclared_terminal_end"` | reached a leaf stream the flowsheet neither connects nor declares |
| `None` | no stream terminus (frozen / dissolved / recirculating / vle_active) |

Convenience accessors: `exits_via_terminal_stream` (both product-end kinds) and
`enters_purge_branch` (purge branch only). `terminal_kind` is also exported by
`ImpurityRoute.to_dict()`.

## Related

The dilution-band criterion is **not met** by the reference case; see
[D5 dilution band: NOT MET](2026-10-28-d5-dilution-band-not-met.md).
