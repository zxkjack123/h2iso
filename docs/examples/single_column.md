# Single Column Example

Solve the Wang 2022 ISS-I CD2 column (75 stages, D₂/DT separation).

```python title="docs/examples/single_column.py"
--8<-- "docs/examples/single_column.py"
```

## Expected Output

```
Convergence: Solved_To_Acceptable_Level
Top D2 purity:  99.9966%
Top DT:         0.003437%
Bottom DT:      95.0780%
T_top:          23.26 K
T_bottom:       23.93 K
Condenser duty: -429.7 W
Reboiler duty:  479.1 W
```

## Run It

```bash
cd h2iso
python docs/examples/single_column.py
```
