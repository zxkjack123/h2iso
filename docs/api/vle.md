# VLE API Reference

## `h2iso.vle.souers` — Vapor Pressure

### `pvap(T, species)`

Pure-component saturation pressure using DIPPR 101 correlation.

```python
from h2iso.vle.souers import pvap

P = pvap(24.0, "D2")  # Returns pressure in Pa
```

**Parameters:**

- `T` (float | ndarray): Temperature in K. Valid range: triple point to critical point.
- `species` (str): One of `"H2"`, `"HD"`, `"HT"`, `"D2"`, `"DT"`, `"T2"`.

**Returns:** Pressure in Pa (same shape as T).

**Warns:** `UserWarning` if T is outside the valid range for the species.

### `pvap_all(T)`

Vapor pressures for all 6 species at temperature T.

```python
from h2iso.vle.souers import pvap_all

P_vec = pvap_all(24.0)  # Returns 6-element array [P_H2, P_HD, ..., P_T2]
```

---

## `h2iso.vle.quantum` — Quantum Corrections

### `quantum_correction(T, species)`

Quantum correction factor for vapor pressure (accounts for zero-point energy effects).

```python
from h2iso.vle.quantum import quantum_correction

f = quantum_correction(20.0, "H2")
```

**Parameters:**

- `T` (float): Temperature in K
- `species` (str): Species identifier

**Returns:** Dimensionless correction factor (typically 0.95–1.05).

---

## `h2iso.vle.mixing` — Mixture VLE

### `kvalue(T, P, x)`

Equilibrium K-value vector (K_i = y_i / x_i) using modified Raoult's law.

```python
from h2iso.vle.mixing import kvalue
import numpy as np

x = np.array([0, 0, 0, 0.98, 0.02, 0])
K = kvalue(24.0, 90_000, x)
```

**Parameters:**

- `T` (float): Temperature in K
- `P` (float): Total pressure in Pa
- `x` (ndarray): Liquid mole fractions, shape (6,)

**Returns:** ndarray of shape (6,) — K-values for each species.

### `bubble_pressure(T, x)`

Calculate bubble point pressure at given temperature and liquid composition.

```python
P_bub = bubble_pressure(24.0, x)
```

### `bubble_temperature(P, x)`

Calculate bubble point temperature at given pressure and liquid composition.

```python
T_bub = bubble_temperature(90_000, x)
```

### `flash_TP(T, P, z)`

Isothermal flash calculation (Rachford-Rice). Returns vapor fraction, liquid
and vapor compositions.

```python
from h2iso.vle.mixing import flash_TP

beta, x_liq, y_vap = flash_TP(24.0, 90_000, z_feed)
```

**Parameters:**

- `T` (float): Temperature in K
- `P` (float): Pressure in Pa
- `z` (ndarray): Feed composition, shape (6,)

**Returns:** Tuple (beta, x, y) — vapor fraction, liquid comp, vapor comp.

---

## `h2iso.vle.eos` — Equation of State

### EOS classes

Two pluggable equation-of-state implementations sharing a common interface
(`kvalue`, `fugacity_coeff_liquid`, `fugacity_coeff_vapor`):

- **`IdealVLE`** — modified Raoult's law with vapour-pressure quantum
  correction (`K_i = (P_sat_i / P) · φ_corr`). Baseline used for low-pressure
  H-isotope distillation (P ≲ 100 kPa).
- **`SRKQuantum`** — full Soave-Redlich-Kwong cubic EOS with
  Graboski-Daubert α function and a leading-order Feynman-Hibbs quantum
  correction. The cubic `Z³ − Z² + (A−B−B²)Z − AB = 0` is solved via
  `numpy.roots`; liquid root = smallest real root > B, vapour root = largest.
  Van der Waals mixing is used with `k_ij = 0` (no binary interaction
  parameters fitted). The vapour-phase fugacity coefficient is applied as a
  residual correction on top of the Souers-anchored Raoult K-value, so SRK
  reduces to `IdealVLE` to within ~1 % at P < 50 kPa and shows > 5 %
  non-ideal departure for P > 500 kPa.

### `liquid_molar_volume(T, species)`

Liquid molar volume using Rackett correlation.

### `vapor_molar_volume(T, P, species)`

Vapor molar volume (ideal gas approximation at cryogenic pressures).

---

## `h2iso.species` — Species Definitions

### Constants

- `SPECIES_ORDER`: Tuple `("H2", "HD", "HT", "D2", "DT", "T2")`
- `N_SPECIES`: `6`
- `SPECIES`: Dict mapping species name to `Species` dataclass

### `Species` dataclass

```python
@dataclass
class Species:
    name: str
    molecular_weight: float  # g/mol
    T_triple: float         # K
    T_critical: float       # K
    T_boiling: float        # K (at 101325 Pa)
```
