---
note_id: "2026-10-31-holdup-correlation-provenance"
date: "2026-10-31"
author_agent: "dev-orchestrator"
pr_ref: "9"
change_scope:
  - "docs/notes/2026-10-31-holdup-correlation-provenance.md"
  - "src/h2iso/mesh/holdup.py"
  - "src/h2iso/mesh/efficiency.py"
  - "tests/test_mesh/test_holdup_packed.py"
---

# Holdup correlations: what each one is checked against

`src/h2iso/mesh/holdup.py` implements five liquid-holdup correlations. Until
now its docstrings pointed at "the cited design note" — a report that lives in
the **delivery package** (`2026-10-22` hand-over, `附件_调研报告/`), not in this
repository. A reader of the code could therefore not follow a single
verification chain, and several quantitative claims ("cross-confirmed by six
independent documents") had no evidence inside the repo at all. Those pointers
are replaced here by the sources themselves.

This note is the **provenance record** for that review. It states, per
correlation, which document was consulted, what was actually compared, and
which items remain unverified. It is deliberately narrow: it documents
transcription fidelity, not physical validation.

## Evidence levels used below

| Level | Meaning |
|---|---|
| **P** | Primary source (the correlation's own paper), read directly |
| **S** | Near-primary: an implementation-independent transcription of the primary source (e.g. the ChemSep Book, a FRI review paper) |
| **U** | Unverified — no accessible source states the equation |

Transcription fidelity is the only claim a **P/S** level supports. Nothing in
this note claims that a correlation predicts this repository's operating point
(20 K liquid hydrogen) correctly; see *Open items* item 4.

## Per-correlation status

### 1. Bennett, Agrawal & Cook (1983) — tray clear-liquid height

| Item | Value |
|---|---|
| Implemented | `clear_liquid_height_bennett_agrawal`, `liquid_holdup_tray_bennett_agrawal` |
| Source | **S** — Wang et al. (2018, FRI), Eq. 5-6; Perry's Handbook Sec. 14 millimetre form |
| Constants compared | `12.55`, `0.91`, `0.50`, `0.438`, `137.8`, `0.67` |
| Result | all six agree across the two secondary sources |
| Worked example | Perry's 7th ed. Sec. 14, Example 11 (Method B) — reproduced in `tests/test_mesh/test_holdup.py` |

The SI and millimetre coefficient sets are **not** related by one factor:
`137.8 = 1000 x 0.1378` exactly, but `0.438 / 0.0286 = 15.315` while
`0.500 / 0.0327 = 15.291`. An earlier docstring quoted a single "1000:15.33"
ratio, which no pair of coefficients satisfies; the docstring now states the
rounding difference instead of inventing a conversion.

Hofhuis-Zuiderweg below covers the same physical quantity; `tray_method`
defaults to this model.

### 2. Hofhuis & Zuiderweg (1979) — tray clear-liquid height (flow group `psi`)

| Item | Value |
|---|---|
| Implemented | `clear_liquid_height_hofhuis_zuiderweg` (`mode="original"`, default) |
| Source | **S** — Wang et al. (2018, FRI), Eq. 7-8, including the variable definitions |
| Result | verbatim agreement, including `p` = hole **pitch** and `u_s` = vapour velocity on the bubbling area |
| Worked example | Zarzycki & Chacuk, *Absorption*, Example 12-A — reproduced in `tests/test_mesh/test_holdup.py` |

`mode="dhulesia_froth"` (`0.5 psi^0.33 h_w^0.5 p^0.17`) is **U**:

- Wang et al. cite Dhulesia (1984, *Chem. Eng. Res. Des.* **62**(5)) by name
  and print no equation for it;
- the delivery report itself tags this row as secondary-sourced (`【检索】`) and
  records that no accuracy figure for the *original* Hofhuis-Zuiderweg form
  was found;
- the Dhulesia paper is not in the delivery package and was not retrieved.

The branch is kept (removing it would widen this change beyond a
transcription review) but is now labelled `SECONDARY-UNVERIFIED` in the
docstring, and the attribution "+/-10 % vs experiments" was removed: that
number belongs to Dhulesia's own fit, not to anything verified here. It is
also not reachable from `evaluate_column_holdup`, which never passes `mode`.

### 3. Stichlmair, Bravo & Fair (1989) — packed liquid holdup

| Item | Value |
|---|---|
| Implemented | `liquid_holdup_packed_stichlmair` (default `packed_method`) |
| Source | **P** — *Gas Sep. Purif.* **3**(1) 19-28, Eq. 14-15 |
| Result | verbatim agreement for both the pre-loading and loading-region forms |

Two earlier statements were wrong and are corrected:

1. The delivery report marked this paper as closed-source / not obtained
   (§8.3, entry S14), yet the PDF is in the delivered literature package. The
   transcription is therefore **primary-source** verified, not merely
   cross-confirmed by a chain of secondary documents.
2. The report (and the test-file header) asserted that no packed correlation
   has a published worked example. The paper contains one on p. 24:
   `u_L = 5e-3 m/s`, `a_p = 260 m^2/m^3`, `eps = 0.68` → `h0 = 0.088 m^3/m^3`.
   The code returns `0.08796683` (0.04 % — the paper rounds to three figures).
   `test_literature_worked_example` anchors that number.

**Defect found and fixed (this review):** the loading correction divided by
`Z` although the argument is already a *gradient*. Eq. 15 uses the **total**
irrigated pressure drop `dP_irr`, so `dP_irr / Z` is the gradient; feeding the
gradient and dividing again produced a group with units of 1/m. At a fixed
gradient the result drifted with packed height (`Z` = 0.5 → 0.161,
1 → 0.106, 2 → 0.093, 3 → 0.090 at 1000 Pa/m, `rho_L` = 1000). Both existing
tests pinned `Z = 1.0`, where the extra division is a no-op, so the defect was
invisible. `Z` is now validated for positivity only. The branch is dormant in
the shipped path (`evaluate_column_holdup` passes no `dP_irr_per_Z`), so no
reported result changes — but the function is a public export.

### 4. Billet & Schultes — packed liquid holdup

| Item | Value |
|---|---|
| Implemented | `liquid_holdup_packed_billet_schultes` |
| Source | **S** — ChemSep Book (Kooijman & Taylor), 2nd ed. Eq. 16.53-16.64 (1st-ed web numbering: 18.100-18.110) |
| Constants compared | `0.15`, `0.1`, `0.85`, `0.25`, `0.1`, `12`, `0.3741`, `0.05`, exponent `13` |
| Result | all nine agree |
| Worked example | none published; locked by re-computation |

`c_h` (packing-specific) is a required argument with no default — correct, and
unchanged. The docstring now names the edition, because the same equation block
carries two different numbers in the two editions.

### 5. Rocha, Bravo & Fair (1993) — structured-packing liquid holdup

| Item | Value |
|---|---|
| Implemented | `liquid_holdup_packed_rocha_bravo_fair` |
| Source | **P** — *Ind. Eng. Chem. Res.* **32**(4) 641-651, Eq. 18-19 and Eq. 28 |
| Result | verbatim agreement, including the `eps^0.6`, `sin(theta)^0.3` and `(1 - 0.93 cos gamma)` denominator terms |
| Contact-angle switch | `cos gamma = 0.9` below `sigma = 0.055 N/m`, matching the paper; ChemSep's `0.0453 N/m` is a documented deviation from the paper, not the other way round |
| Worked example | none published; locked by re-computation |

**Open dispute, now explicit instead of defaulted.** Eq. 19 as printed has no
`eps` in the denominator; the code's `include_eps_in_denom=True` convention
multiplies `h_L` by `eps**(-1/3)` (+2.2 % at `eps = 0.937`). This is a
published definitional exchange (Qiu's comment vs the authors' rebuttal), so
the switch no longer has a default: callers state which convention they use,
and `evaluate_column_holdup` passes `True` (bed-volume convention, consistent
with the executable reference implementation circulated with the paper).

Two further arguments used to default to numbers that belong to a specific
packing and a specific fluid, and are now required at the point where they
matter:

- `f_se` (surface-enhancement factor, `0.35` for Mellapak/Flexipac) — required
  whenever `a_p` is given, because it feeds `a_e` directly;
- `dP_per_Z_flood` (`1025 Pa/m` is an **air/water** flooding gradient) —
  required whenever `dP_per_Z` is given. This package simulates 20 K liquid
  hydrogen, where that number has no basis.

## Open items (not closed by this review)

1. **Dhulesia (1984) froth-regime coefficients** — unverified; the paper was
   not obtained. The branch is labelled, not validated.
2. **No published worked examples** for Billet-Schultes and
   Rocha-Bravo-Fair. Their tests are regression locks (independent
   re-computation of the printed formulas) plus dimensional and monotonicity
   checks — they would catch a code change, not a transcription error that was
   made before the lock was written.
3. **Billet-Schultes substituted for "Bravo & Fair (1982)"** in the declared
   demonstration basis. The substitution is a design decision of this
   implementation; the substituted model predicts the same physical quantity
   but is not the declared correlation.
4. **Cryogenic validity.** All five correlations were fitted on air/water or
   hydrocarbon data. Whether they describe hydrogen-isotope service at 20 K is
   an assumption of this implementation, not a verified result, and no
   cryogenic-specific liquid-holdup correlation for structured packing was
   found in the literature surveyed.
5. **Distillation-scale examples.** The SBF worked example is a hydraulic
   example, not a distillation simulation; none of the packed correlations is
   anchored to a full column result here.

## Reproducing the two substantive checks

```
$ PYTHONPATH=src .venv/bin/python -c "
from h2iso.mesh.holdup import liquid_holdup_packed_stichlmair as f
out = f(5e-3, 260.0, 0.68)          # SBF 1989 p. 24 worked example
print(out['h0'])                     # 0.08796683  (paper: 0.088)
for Z in (0.5, 1.0, 2.0, 3.0):       # fixed gradient 1000 Pa/m, rho_L = 1000
    print(Z, f(5e-3, 260.0, 0.68, dP_irr_per_Z=1000.0, Z=Z, rho_l=1000.0)['h_L'])
"
0.08796683
0.5 0.106248
1.0 0.106248
2.0 0.106248
3.0 0.106248
```

Run against the pre-review source, the last four lines were
`0.161093 / 0.106248 / 0.092537 / 0.089998` — same fixed gradient, four
different answers, which is the `Z` defect.

## Related

- Packed-column tests: `tests/test_mesh/test_holdup_packed.py`
- Tray-column tests (with the two literature worked examples):
  `tests/test_mesh/test_holdup.py`
- Delivery-side report that these docstrings used to point at:
  `附件_调研报告/B1_holdup_correlations.md` — **not** part of this repository.
