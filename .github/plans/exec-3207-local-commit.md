# Execution Plan: PM #3207 — h2iso 本地 3.5 个月未提交工作分主题提交

## 1. Scope & Source-of-Truth

- **PM task**: #3207
- **Repository**: `/home/gw/opt/h2iso`
- **Goal**: 将当前本地未提交工作拆成 8 个主题 commit，全部安全落库，供后续 #3208/#3209 继续推进。
- **Source plan**: `.github/reviews/local-commit-plan-2026-09-01.md`
- **Current baseline**: `main` 在 `eba4530`；工作树包含 42 个 modified + 26 个 untracked 条目。
- **Important**: 本计划只负责本地保存提交，不处理上游 PR 合并。

## 2. Preconditions

- 必须使用 `.venv` 内的 Python/pip，系统级 `pip` 不可用。
- `asipp/pr/2`、`asipp/pr/5`、`asipp/pr/6`、`asipp/pr/8` 已可解析。
- 若执行前远端发生更新，需要重新 `git fetch asipp` 并重新核对 `pr/8`。
- 任何超出本计划范围的动作都必须按 D2 处理：停止，返回 `NEEDS_USER_DECISION`。

## 3. Baseline & Safety Net

```bash
git rev-parse HEAD
git status --porcelain
git stash list --date=iso
git fetch asipp
git rev-parse --verify asipp/pr/8
```

### Safety checkpoint

```bash
git stash -u
STASH_REF=$(git rev-parse stash@{0})
git stash apply --index "$STASH_REF"
git status --porcelain
```

- `git stash apply` 恢复工作树但保留 stash 条目，`STASH_REF` 必须记录在执行日志中。
- 该 stash 是本任务的安全网。只有全部 8 个主题 commit 完成、全量测试通过且工作树核对无误后，才允许 `git stash drop "$STASH_REF"`。
- 如果 `stash apply` 出现冲突，立即 STOP，不得自行覆盖冲突文件。
- 若中途失败，优先使用已提交 commit 的 `git revert` 或在确认无未保存修改后再次 `git stash apply` 恢复，禁止 `reset --hard`、`branch -D`、`clean -fd`。

## 4. Environment Repair (Phase A)

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/pip install -e ".[dev,solver,uq]"
.venv/bin/python -m pytest --version
```

### Acceptance

- `.venv/bin/python` 可执行且不再是 broken symlink。
- `.venv/bin/python -m pytest --version` 成功。
- 如果安装失败，STOP，报告错误，不允许改用系统 `pip` 绕过。

## 5. Commit Sequence (Phase B)

### Commit 1 — chore(tooling): dev 工具链与 CI 配置

**Files**
- `.gitignore`
- `.coveragerc`
- `.pre-commit-config.yaml`
- `Makefile`
- `constraints/`
- `AGENTS.md`
- `.github/workflows/ci.yml`

**Actions**
```bash
git add .gitignore .coveragerc .pre-commit-config.yaml Makefile constraints AGENTS.md .github/workflows/ci.yml
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
git commit -m "chore(tooling): add repo tooling, CI config, and dev rules"
```

**Validation**
- `.venv/bin/python -m pytest tests/ --collect-only -q`
- `ruff check src/ tests/`

### Commit 2 — feat(vle): Peng-Robinson EOS

**Files**
- `src/h2iso/vle/peng_robinson.py`
- `src/h2iso/vle/mixing.py`
- `src/h2iso/vle/quantum.py`
- `src/h2iso/vle/souers.py`
- `tests/test_vle/`

**Actions**
```bash
git add src/h2iso/vle/peng_robinson.py src/h2iso/vle/mixing.py src/h2iso/vle/quantum.py src/h2iso/vle/souers.py tests/test_vle
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
git commit -m "feat(vle): add Peng-Robinson EOS support and VLE regression tests"
```

**Validation**
- `.venv/bin/python -m pytest tests/test_vle/ -x -q`

### Commit 3 — feat(mesh): 列模型与 continuation 强化

**Files**
- `src/h2iso/mesh/__init__.py`
- `src/h2iso/mesh/column.py`
- `src/h2iso/mesh/continuation.py`
- `src/h2iso/mesh/enthalpy.py`
- `src/h2iso/mesh/stage.py`
- `src/h2iso/codegen/modelica_records.py`
- `tests/test_mesh/test_column.py`
- `tests/test_mesh/test_continuation.py`
- `tests/test_mesh/test_multi_feed.py`
- `tests/test_mesh/test_stage.py`
- `tests/test_mesh/test_wang2022_mesh.py`

**Actions**
```bash
git add src/h2iso/mesh/__init__.py src/h2iso/mesh/column.py src/h2iso/mesh/continuation.py src/h2iso/mesh/enthalpy.py src/h2iso/mesh/stage.py src/h2iso/codegen/modelica_records.py tests/test_mesh/test_column.py tests/test_mesh/test_continuation.py tests/test_mesh/test_multi_feed.py tests/test_mesh/test_stage.py tests/test_mesh/test_wang2022_mesh.py
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
git commit -m "feat(mesh): strengthen column model and continuation workflow"
```

**Validation**
- `.venv/bin/python -m pytest tests/test_mesh/ -x -q`

### Commit 4 — feat(flowsheet): splitter + multi-equilibrator resolution

**Files**
- `src/h2iso/flowsheet/schema.py`
- `src/h2iso/flowsheet/solver.py`
- `src/h2iso/flowsheet/sweep.py`
- `src/h2iso/flowsheet/unit.py`
- `src/h2iso/equilibrator/exchange.py`
- `tests/test_flowsheet/test_cli_flowsheet.py`
- `tests/test_flowsheet/test_isso_full.py`
- `tests/test_flowsheet/test_isso_no_recycle.py`
- `tests/test_flowsheet/test_pressure_changer.py`
- `tests/test_flowsheet/test_schema.py`
- `tests/test_flowsheet/test_solver.py`
- `tests/test_flowsheet/test_stream.py`
- `tests/test_flowsheet/test_sweep.py`
- `tests/test_flowsheet/test_units.py`
- `tests/test_flowsheet/test_wegstein_simplex.py`
- `tests/test_flowsheet/test_equilibrator_multi.py`

**Actions**
```bash
git add src/h2iso/flowsheet/schema.py src/h2iso/flowsheet/solver.py src/h2iso/flowsheet/sweep.py src/h2iso/flowsheet/unit.py src/h2iso/equilibrator/exchange.py tests/test_flowsheet/test_cli_flowsheet.py tests/test_flowsheet/test_isso_full.py tests/test_flowsheet/test_isso_no_recycle.py tests/test_flowsheet/test_pressure_changer.py tests/test_flowsheet/test_schema.py tests/test_flowsheet/test_solver.py tests/test_flowsheet/test_stream.py tests/test_flowsheet/test_sweep.py tests/test_flowsheet/test_units.py tests/test_flowsheet/test_wegstein_simplex.py tests/test_flowsheet/test_equilibrator_multi.py
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
git commit -m "feat(flowsheet): add splitter support and improve multi-equilibrator stream resolution"
```

**Validation**
- `.venv/bin/python -m pytest tests/test_flowsheet/ -x -q`

### Commit 5 — feat(iss-i): ISS-I cascade + Aspen baseline

**Files**
- `tests/fixtures/wang2022/iss_i.json`
- `tests/fixtures/wang2022/iss_i_aspen_baseline.json`
- `tests/test_flowsheet/test_iss_i.py`
- `tests/test_mesh/test_iss_i_aspen_validation.py`
- `.github/plans/iss_i_flowsheet_plan.md`

**Actions**
```bash
git add tests/fixtures/wang2022/iss_i.json tests/fixtures/wang2022/iss_i_aspen_baseline.json tests/test_flowsheet/test_iss_i.py tests/test_mesh/test_iss_i_aspen_validation.py .github/plans/iss_i_flowsheet_plan.md
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
git commit -m "feat(iss-i): add ISS-I cascade fixtures and Aspen baseline tests"
```

**Validation**
- `.venv/bin/python -m pytest tests/test_flowsheet/test_iss_i.py -x -q`

### Commit 6 — feat(parity): DWSIM parity framework

**Files**
- `src/h2iso/parity/`
- `tests/test_parity/`
- `.github/plans/dwsim_parity_plan.md`
- `script/register_compounds.py`
- `script/run_dwsim_baseline.py`

**Actions**
```bash
git add src/h2iso/parity tests/test_parity .github/plans/dwsim_parity_plan.md script/register_compounds.py script/run_dwsim_baseline.py
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
git commit -m "feat(parity): add DWSIM parity framework"
```

**Validation**
- `.venv/bin/python -m pytest tests/test_parity/ -x -q`

### Commit 7 — feat(uq): uncertainty propagation framework

**Files**
- `pyproject.toml`
- `src/h2iso/uq/`
- `tests/test_uq/`
- `docs/uq/`
- `.github/plans/engineering-reliability-plan.md`

**Actions**
```bash
git add pyproject.toml src/h2iso/uq tests/test_uq docs/uq .github/plans/engineering-reliability-plan.md
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
git commit -m "feat(uq): add uncertainty propagation framework"
```

**Validation**
- `.venv/bin/python -m pytest tests/test_uq/ -x -q`

### Commit 8 — feat(cli): CLI + docs + residual tests

**Files**
- `src/h2iso/cli.py`
- `tests/e2e/test_modelica_compile.py`
- `tests/e2e/test_modelica_simulate.py`
- `tests/error_paths/test_invalid_inputs.py`
- `tests/error_paths/test_solver_failures.py`
- `tests/property/test_mass_balance.py`
- `.github/reviews/github-activity-2026-09-01.md`
- `.github/reviews/local-commit-plan-2026-09-01.md`

**Actions**
```bash
git add src/h2iso/cli.py tests/e2e/test_modelica_compile.py tests/e2e/test_modelica_simulate.py tests/error_paths/test_invalid_inputs.py tests/error_paths/test_solver_failures.py tests/property/test_mass_balance.py .github/reviews/github-activity-2026-09-01.md .github/reviews/local-commit-plan-2026-09-01.md
git diff --cached --check
git diff --cached --name-only
git diff --cached --stat
git commit -m "feat(cli): enhance command surface and finalize residual tests/docs"
```

**Validation**
- `.venv/bin/python -m pytest tests/ -q --tb=short`

## 6. Final Verification (Phase E)

```bash
git status --porcelain
git log --oneline -10
git stash list --date=iso
.venv/bin/python -m pytest tests/ -q --tb=short
```

### Done criteria

- `git status --porcelain` 只剩预期的不入库项，或为空。
- 预期不入库项：`.opencode/`、`h2iso_results.json`、`figures/`。
- `.github/plans/exec-3207-local-commit.md` 为执行计划工作件，不随代码落库。
- `git log --oneline -10` 显示 8 个主题 commit。
- 全量测试通过，或失败原因被明确记录并按 D1/D2 处理。

## 7. D1 / D2 Gate

- **D1**: 仅允许与本计划等价的小步修正，例如命令顺序调整、单次重试、测试命令参数微调。
- **D2**: 任何涉及范围扩张、跳过安全网、修改源码主题之外文件、直接改上游 PR、或绕过门禁的动作，必须 STOP 并返回 `NEEDS_USER_DECISION`。

## 8. Rollback Matrix

| Failure | Action |
|----------|--------|
| commit 失败 | `git status --porcelain` 检查后修正 staging，再次提交 |
| 单个 commit 测试失败 | 先修测试或代码；若无法立即修复，`git revert <sha>` 回到上一个 commit |
| 环境重建失败 | 删除 `.venv` 后重建；仍失败则 STOP 上报 |
| 误 stage 文件 | `git restore --staged <file>`，然后重新 add |
| 全部失败 | 先 `git revert` 全部已落地 commit，再 `git stash apply "$STASH_REF"` 核对安全网，重新规划 |

## 9. Notes for Executor

- 文件名以 `git status --porcelain` 实测为准。
- 每个 commit 前都必须用 `git diff --cached --name-only` 与计划清单显式比对，不得只凭 `--stat` 目视。
- 不要把 `.opencode/` 提交进库。
- 不要把 `h2iso_results.json`、`figures/` 提交进库。
- 不要把 `.github/plans/exec-3207-local-commit.md` 提交进库。
- 6 个上游冲突文件属于后续 PM #3208：`src/h2iso/flowsheet/solver.py`、`src/h2iso/flowsheet/schema.py`、`tests/test_flowsheet/test_isso_full.py`、`tests/test_flowsheet/test_isso_no_recycle.py`、`tests/test_flowsheet/test_schema.py`、`tests/test_flowsheet/test_sweep.py`。#3207 只保存本地版本，不在本任务中混入 PR 版本。
- 若发现新文件与计划不符，先记录，再按 D2 处理。
