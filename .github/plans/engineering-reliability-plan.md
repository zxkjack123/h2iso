# h2iso 工程可靠性提升计划

## 背景与目标

**现状**：469 tests 全绿，CI 覆盖 5 个 job（lint/test/benchmark/e2e/wheel），但存在以下工程可靠性缺陷：

| 缺陷 | 影响 |
|------|------|
| 无 pre-commit hooks | 本地提交可能带 lint 错误，需 CI 反馈后才发现问题 |
| 无 Makefile | 新人需要熟读 AGENTS.md 才能跑常用命令 |
| CI 全量测试 6 分钟 | 所有 solver 测试串行跑，无分层快慢 |
| 无代码覆盖率门槛 | 不知道哪些路径未被测试覆盖 |
| 无依赖安全扫描 | 第三方依赖漏洞无法及时发现 |
| `.gitignore` 缺 UQ 输出目录 | `uq_runs/` 下的报告可能被误提交 |
| `__version__` 未在代码中暴露 | 无法通过 `h2iso --version` 或 `import h2iso; h2iso.__version__` 获取版本 |

**目标**：建立一个自动化质量门控体系，让每次 `git commit` 和 `git push` 都有快速反馈，同时降低新贡献者的入门门槛。

**非目标**：
- 不修改代码逻辑（tests/src 不动）
- 不改变 CasADi/OpenModelica 的安装方式
- 不做 CI 平台迁移（仍用 GitHub Actions）

---

## 修改方案

### 现状调研核心结论

1. **CI 已是 5-job 矩阵**：`test`（py39/311/312 3 矩阵）、`test-solver`（全量含 solver）、`test-wheel`（构建 + 导入冒烟）、`benchmark`（仅 main push）、`e2e-modelica`（workflow_dispatch + main）。结构合理，但缺分层和 pre-commit。

2. **pyproject.toml 覆盖完整**：ruff、pytest、setuptools 配置均在 toml 中，无需散落配置文件。

3. **`pip install -e ".[dev,solver]"` 6 min** 全量回归时间可接受但可优化：拆出 fast lane（仅 lint + 非 solver 测试）本地 ~15s。

4. **无 `uv.lock` / `pip freeze` 锁依赖**：当前用 version range（e.g., `numpy>=1.22`），CI 中依赖版本不锁定可能导致偶发的构建失败。

### 修改路径分类

| 文件 | 变更类型 | 预计行数 |
|------|---------|---------|
| `.pre-commit-config.yaml` | New | +60 |
| `Makefile` | New | +80 |
| `.github/workflows/ci.yml` | Medium | +30 |
| `src/h2iso/__init__.py` | Light | +5 |
| `.gitignore` | Light | +3 |
| `pyproject.toml` | Light | +10 |
| `constraints/` directory | New | +3 files |

**不再修改** `src/h2iso/*`（除 `__init__.py` 添加 `__version__`）、`tests/`。

### 关键设计决策

#### D1：pre-commit hooks 范围

**选择**：pre-commit 只跑 `ruff check` + `ruff format --check` + **非 solver 快速测试**（30s 内）。不跑 CasADi solver 测试（本地 CI 环境可能未装）。

**替代方案（被拒绝）**：跑全量 `pytest tests/`。不选——pre-commit 必须快（<30s），而 solver 测试需 6 min。

**风险**：低。solver 测试由 CI `test-solver` job 覆盖。

#### D2：依赖锁定方案

**选择**：用 `pip freeze` 生成 `constraints/ci-3.12.txt` 文件，CI 中 `pip install -c constraints/ci-3.12.txt -e ".[dev,solver]"`。每月手动或用 Dependabot 更新。

**替代方案（被拒绝）**：用 `uv.lock` / `pipenv` / `poetry.lock`。不选——增加额外工具依赖，且 h2iso 是 library（不是 application），宽松的 version range 对下游更友好。仅在 CI 中锁定以保证可复现性。

**风险**：低。锁文件仅用于 CI，不影响 `pip install h2iso` 的用户。

#### D3：CI 分层策略

**选择**：新增一个 `lint-and-fast` job（仅 ruff + 非 solver 测试），在 1 分钟内完成。现有的 `test` matrix job 保留但只跑非 solver 测试（与 lint 合并）。

实际新增的 job：
- `lint-and-fast-test`：ruff check + ruff format --check + pytest（非 solver，~1 min）
- 保留 `test-solver`（全量含 CasADi）、`test-wheel`、`benchmark`、`e2e-modelica`

**替代方案（被拒绝）**：把 solver 测试拆到单独的 slow job 中，fast test matrix 不装 CasADi。不选——当前 `test` job 已在 matrix 中，改动过大。

**风险**：低。只是新增 fast job，不删改现有 job。

---

## 执行计划

### Phase 1: 本地开发工具（Makefile + pre-commit）

#### Task 1.1: 创建 Makefile

- **目标**：提供 `make lint`、`make test`、`make test-fast`、`make docs` 等常用命令
- **依赖**：无
- **修改内容**：
  - 新建 `Makefile`
  - 包含 targets：

```makefile
.PHONY: lint format test test-fast test-all docs clean help

lint:
	ruff check src/ tests/

format:
	ruff format src/ tests/

test-fast:
	pytest tests/ --ignore=tests/benchmark --ignore=tests/e2e \
		--ignore=tests/test_mesh --ignore=tests/test_flowsheet \
		--ignore=tests/property \
		--ignore=tests/test_uq/test_cd2_uq.py \
		--ignore=tests/test_uq/test_isso_uq.py \
		-x --tb=short

test:
	pytest tests/ --ignore=tests/benchmark --ignore=tests/e2e -x --tb=short

test-all:
	pytest tests/ --tb=short

bench:
	pytest tests/benchmark/ --benchmark-enable --override-ini="addopts="

docs:
	mkdocs serve

clean:
	rm -rf dist/ build/ .pytest_cache/ .mypy_cache/ htmlcov/ .coverage
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

help:
	@echo "lint      Run ruff check"
	@echo "format    Run ruff format"
	@echo "test-fast Run fast tests only (no solver, <30s)"
	@echo "test      Run all tests except benchmark/e2e"
	@echo "test-all  Run every test including benchmark/e2e"
	@echo "bench     Run performance benchmarks"
	@echo "docs      Serve documentation locally"
	@echo "clean     Remove build artifacts"
```

- **修改边界**：不修改任何 Python 文件
- **质量检查**：`make help` 输出所有 targets，`make lint` 返回 0
- **验收标准**：
  - ✅ `make test-fast` 在 30s 内完成
  - ✅ `make lint` + `make format` 无 diff（代码已格式化）
  - ✅ `make clean` 后 `git status` 干净

#### Task 1.2: 配置 pre-commit hooks

- **目标**：安装 `.pre-commit-config.yaml`，每次 `git commit` 自动跑 lint + format check + fast test
- **依赖**：Task 1.1
- **修改内容**：
  - 新建 `.pre-commit-config.yaml`
  - 3 个 hooks：ruff lint、ruff format、pytest-fast（本地 hook）
  - `pytest-fast` hook 只跑 VLE/species/equilibrator/data/UQ 非 solver 测试

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.4.0
    hooks:
      - id: ruff
        args: [check, --fix]
      - id: ruff-format
  - repo: local
    hooks:
      - id: pytest-fast
        name: pytest-fast
        entry: pytest tests/ --ignore=tests/benchmark --ignore=tests/e2e --ignore=tests/test_mesh --ignore=tests/test_flowsheet --ignore=tests/property --ignore=tests/test_uq/test_cd2_uq.py --ignore=tests/test_uq/test_isso_uq.py -x --tb=line -q
        language: system
        pass_filenames: false
        always_run: true
```

- **修改边界**：不修改 Python 代码
- **质量检查**：`pre-commit run --all-files` 成功
- **验收标准**：
  - ✅ `pre-commit run --all-files` 3 个 hook 全绿
  - ✅ 有格式问题的代码被 `ruff-format` 拦截

### Phase 2: CI 增强

#### Task 2.1: 新增 lint-and-fast-test CI job

- **目标**：CI 在 1-2 分钟内给出快速反馈（lint + 非 solver 测试）
- **依赖**：无
- **修改内容**：
  - 编辑 `.github/workflows/ci.yml`
  - 在现有 jobs 前新增 `lint-and-fast-test` job
  - 不含 CasADi，只跑 `ruff check` + `ruff format --check` + `pytest`（非 solver）

```yaml
  lint-and-fast-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install deps
        run: pip install -e ".[dev]"
      - name: Lint
        run: |
          ruff check src/ tests/
          ruff format --check src/ tests/
      - name: Fast test
        run: pytest tests/ --ignore=tests/benchmark --ignore=tests/e2e --ignore=tests/test_mesh --ignore=tests/test_flowsheet --ignore=tests/property --ignore=tests/test_uq/test_cd2_uq.py --ignore=tests/test_uq/test_isso_uq.py -x --tb=short
```

- **修改边界**：不改现有 CI jobs
- **质量检查**：CI 通过后在该 job 日志中确认 <2 min
- **验收标准**：
  - ✅ CI green，`lint-and-fast-test` 在 2 分钟内完成
  - ✅ 现有 5 个 jobs 不受影响

#### Task 2.2: 添加依赖锁定文件

- **目标**：CI 中依赖版本可复现，防止上游 breaking change 导致 CI 随机失败
- **依赖**：无
- **修改内容**：
  - 新建 `constraints/ci-3.12.txt`（`pip freeze` 输出）
  - CI 中 `pip install -c constraints/ci-3.12.txt -e ".[dev,solver]"`
  - 修改 `ci.yml` 的 `test-solver` 和 `test` job 使用 constraint 文件
- **修改边界**：不修改 pyproject.toml 中的 version range
- **验收标准**：
  - ✅ `pip install -c constraints/ci-3.12.txt -e ".[dev,solver]"` 成功
  - ✅ CI 全部通过

#### Task 2.3: 代码覆盖率报告

- **目标**：CI 中生成覆盖率报告，了解未测试路径
- **依赖**：无
- **修改内容**：
  - 新建 `.coveragerc` 配置文件（排除 tests、__init__ 样板代码）
  - 在 CI `test-solver` job 中加 `pytest --cov=h2iso --cov-report=term-missing`
  - 不设 coverage gate（仅信息性），后续可逐步设门槛
- **修改边界**：不修改测试或源代码
- **验收标准**：
  - ✅ CI 日志中显示覆盖率百分比
  - ✅ 覆盖率 > 60%（当前状态）

### Phase 3: 版本管理 + 安全扫描

#### Task 3.1: 添加 `__version__`

- **目标**：`import h2iso; print(h2iso.__version__)` 可用，CLI `h2iso --version` 可用
- **依赖**：无
- **修改内容**：
  - `src/h2iso/__init__.py`：添加 `__version__ = "0.1.0"`
  - `src/h2iso/cli.py`：`main()` 中加入 `--version` 参数
  - 版本号与 `pyproject.toml` 的 `version = "0.1.0"` 保持一致
- **修改边界**：不改其他模块
- **验收标准**：
  - ✅ `python -c "import h2iso; print(h2iso.__version__)"` 输出 `0.1.0`
  - ✅ `h2iso --version` 输出 `h2iso 0.1.0`

#### Task 3.2: 添加依赖安全扫描

- **目标**：CI 中扫描已知漏洞
- **依赖**：无
- **修改内容**：
  - 在 `pyproject.toml` 的 dev deps 中加入 `pip-audit`
  - CI 新增 `security-audit` job：`pip-audit`（自动扫描当前 venv 已安装包）
  - 仅报告，不阻塞 CI（首次运行后逐步收紧）
- **验收标准**：
  - ✅ CI job `security-audit` 通过（无高危漏洞则绿）

#### Task 3.3: 补充 `.gitignore`

- **目标**：防止 UQ 运行输出、约束文件等被误提交
- **修改内容**：
  - `.gitignore` 追加 `uq_runs/`、`.benchmarks/`、`*.prof`

---

## Execution Wave

| Wave | Task | 预计时间 |
|------|------|---------|
| W1 | T1.1 (Makefile) | 10 min |
| W2 | T1.2 (pre-commit) | 10 min |
| W3 | T3.1 (__version__) | 5 min |
| W4 | T3.3 (.gitignore) + T2.2 (constraints) | 15 min |
| W5 | T2.1 (fast CI job) + T2.3 (coverage) + T3.2 (security) | 30 min |

---

## Post-Execution Verification

### Automated
| ID | Description | Command |
|----|-------------|---------|
| V1 | make help | `make help` |
| V2 | make lint | `make lint` |
| V3 | make test-fast | `make test-fast` |
| V4 | pre-commit all | `pre-commit run --all-files` |
| V5 | h2iso version | `h2iso --version` |
| V6 | ruff check | `ruff check src/ tests/` |
| V7 | Full regression | `pytest tests/ --ignore=tests/benchmark --ignore=tests/e2e -q` |

### Manual
- [ ] `git commit` 触发 pre-commit hooks 并全部通过
- [ ] `make test-fast` 在 30s 内完成
- [ ] CI 提交后所有 jobs 绿

---

## 审查日志

### R1 — 结构完整性
- Phase 1（本地工具）：Makefile + pre-commit — 可直接提升本地开发体验
- Phase 2（CI 增强）：fast lane job + 约束文件 + 覆盖率 — 提升 CI 反馈速度和可复现性
- Phase 3（版本 + 安全）：`__version__` + pip-audit + `.gitignore` — 补充工程基础
- ✅ 覆盖完整，Task 依赖合理

### R1.5 — 外部引用事实核查
- `.github/workflows/ci.yml` 现有 5 jobs，138 行 ✓
- `pyproject.toml` 已配 ruff+pytest+setuptools ✓
- `.gitignore` 已有 34 行 ✓
- pre-commit `ruff-pre-commit` 官方仓库 https://github.com/astral-sh/ruff-pre-commit ✓
- `pip-audit` PyPI 包存在（pypa/gh-action-pip-audit）✓
- ✅ issue 清零

### R2 — 可执行性
- 每个 Task 有完整示例代码或配置文件内容
- Task 3.1 `__version__` 需同时修改 `__init__.py` 和 `cli.py`，两文件路径明确
- Task 2.2 约束文件需先在本地 `pip freeze > constraints/ci-3.12.txt`
- ✅ 无模糊项

### R2.8 — LLM 可执行性审查
- Task 1.1：Makefile 完整内容已提供 ✓
- Task 1.2：`.pre-commit-config.yaml` 完整内容已提供 ✓
- Task 2.1：CI job YAML 已提供 ✓
- Task 3.1：指定了 2 个文件路径 + 修改内容 ✓
- ✅ issue 清零

### R3 — 风险与边缘
- **R3-1** 并行化：W1-W4 的 Task 全部互相独立，可完全并行执行 ✓
- **R3-3** 回滚安全：所有修改均为新增配置文件或单行插入，git revert 秒回 ✓
- **R3-5** 边界控制：明确不改任何测试或 src 逻辑代码 ✓
- **R3-7** What-If：如果 constraint 文件导致 CI 失败 → 更新 constraints 文件或移除 -c flag
- **终止条件**：T1.2（pre-commit pytest hook 失败）→ 查看是环境缺依赖还是测试真的有 regress，前者调整 hook entry，后者修复后继续
- ✅ 低保底风险

---

## 假设记录

1. `[假设: 开发者已安装 pre-commit]` — `pip install pre-commit && pre-commit install` 后生效。如未安装，不影响 CI。
2. `[假设: CI runner 有 pip-audit 可用的网络访问]` — `pip-audit` 需访问 PyPI advisory DB。如网络受限，security job 标记为 `continue-on-error: true`。
3. `[假设: constraint 文件每季度手动更新一次]` — 锁文件不会自动更新，需定期人工执行 `pip freeze` 更新。此频率对 h2iso 的迭代速度合理。
