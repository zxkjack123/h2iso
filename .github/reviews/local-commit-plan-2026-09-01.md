# 本地未提交工作分主题提交计划（含上游 PR 冲突规避）

- 日期: 2026-09-01
- 前置审阅: `.github/reviews/github-activity-2026-09-01.md`（PB-01 的落地执行方案）
- 计划性质: 只读分析产出。实际执行需用户确认决策项后委派 task-executor 或人工执行

## 一、事实基础（证据摘要）

| 事实 | 证据 |
|------|------|
| 本地 42 个已修改文件（+1172/-412） | `git diff --numstat` |
| 约 24 组未跟踪新文件（parity/uq/peng_robinson/iss_i fixtures 等） | `git status --porcelain` |
| 上游 4 个 PR 为堆叠链：PR2 ⊂ PR5 ⊂ PR6 ⊂ PR8 | `git merge-base --is-ancestor` 全部 STACKED |
| 冲突面共 **6 个文件**（本地修改 ∩ PR 改动） | `comm` 求交集 |
| 本地与 PR 对这 6 个文件的 diff 全部互不相同（6/6 DIFFERENT） | `diff -q` 逐文件对比 |
| 本地 `.venv` 损坏（broken symlink），无法跑测试 | `file .venv/bin/python3` |
| `.gitignore` 已覆盖 `__pycache__/`、`uq_runs/`、`build/`、`site/` | `grep .gitignore` |

### 6 个冲突文件的性质预判（外加 1 项非冲突确认事项）

| 文件 | 本地改动 | PR 改动 | 冲突性质 |
|------|----------|---------|----------|
| `src/h2iso/flowsheet/solver.py` | 多平衡器解析（按 config.equilibrators 精确匹配）+ `_apply_split` splitter 新功能（+58/-8） | 多平衡器解析（`f"{name}_out"` 通用快路径 + 前缀回退） | **同一功能点双实现**，需人工语义决策 |
| `src/h2iso/flowsheet/schema.py` | `splitter: dict` 字段族（+71/-47） | `inside_diameter_m`/`HETP_m` 几何字段族 | 同一 dataclass 不同字段族，可共存但需手工合并 hunk |
| `tests/test_flowsheet/test_isso_full.py` | 断言消息 f-string 化 + 格式微调（+12/-10） | 拓扑修复后的新数值断言（440 mol/h 等） | 本地为装饰性，PR 为语义性。以 PR 数值为准，保留本地消息改进 |
| `tests/test_flowsheet/test_isso_no_recycle.py` | 同上（+11/-7） | 撕裂流名称更新（CD2_top） | 同上 |
| `tests/test_flowsheet/test_schema.py` | 本地 splitter 测试 | PR 拓扑流股名更新 | 部分可共存，需合并 |
| `tests/test_flowsheet/test_sweep.py` | +17/-8 | PR 解耦过滤更新 | 需合并 |
| 本地 fixtures（`iss_i.json`/`iss_i_aspen_baseline.json` 为**新增文件**，与 PR 的 `wang2022_issi.json` 文件名不同） | 不冲突，但内容可能重复 | — | 需与 couuas 确认两套 ISS-I 数据的关系 |

## 二、策略决策

**推荐方案 A：先提交本地工作，再合并上游 PR。**

理由：
1. 3.5 个月未提交工作处于丢失风险中，数据安全优先。
2. 你是上游 PR 的 reviewer/merger，本地工作先落 main 后，6 文件冲突在合并 PR 时由你带着完整上下文解决。
3. 若先合并 PR 再提交本地，本地 42+24 个文件要整体 rebase 到外部大变更集上，出错面更大。

**备选方案 B：先合并 PR 再提交本地**（仅当上游 PR 有时效压力、需先让 couuas 的链上 main 时）。此时本地提交顺序不变，只是提交基准变为合并后的 main。

### 冲突一次性解决法（关键技巧）

4 个 PR 是堆叠链，最终态等于 PR8。若逐个合并，6 文件冲突会在 #2→#5→#6→#8 中反复出现 4 次。规避做法：

1. 本地建集成分支 `integration/wang2022`，一次 `git merge asipp/pr/8`，把这 6 个文件的冲突**解决一次**。
2. 在集成分支上跑全量测试，确认解决方案正确。
3. 正式合并 PR 时按 #2→#5→#6→#8 顺序，把集成分支中已验证的 6 个文件版本直接套用到各次合并的冲突解决中（内容相同，只需重复应用，不需重新决策）。

## 三、分主题提交序列（8 个 commit，按依赖排序）

每个 commit 独立可编译、可 revert、附带验证命令。执行前提：先修复 venv（见 Phase A）。

| # | Commit 主题 | 文件 | 验证 |
|---|------------|------|------|
| 1 | `chore(tooling): dev 工具链与 CI 配置` | `.gitignore`、`.coveragerc`、`.pre-commit-config.yaml`、`Makefile`、`constraints/`、`AGENTS.md`、`.github/workflows/ci.yml` | `ruff check src/ tests/` |
| 2 | `feat(vle): Peng-Robinson EOS` | `src/h2iso/vle/peng_robinson.py`(新) + `vle/{mixing,quantum,souers}.py` + `tests/test_vle/*` | `pytest tests/test_vle/ -x` |
| 3 | `feat(mesh): 列模型与 continuation 强化` | `src/h2iso/mesh/{column,continuation,stage,enthalpy,__init__}.py` + `src/h2iso/codegen/modelica_records.py`（引号风格随此） + `tests/test_mesh/*` | `pytest tests/test_mesh/ -x` |
| 4 | `feat(flowsheet): splitter 支持 + 多平衡器解析` ⚠️ 冲突面 | `src/h2iso/flowsheet/{schema,solver,sweep,unit}.py` + `src/h2iso/equilibrator/exchange.py` + `tests/test_flowsheet/{test_schema,test_solver,test_sweep,test_stream,test_isso_*,test_cli_flowsheet,test_pressure_changer,test_units,test_wegstein_simplex}.py` + `tests/test_flowsheet/test_equilibrator_multi.py`(新) | `pytest tests/test_flowsheet/ -x` |
| 5 | `feat(iss-i): ISS-I 级联 + Aspen 基线` | `tests/fixtures/wang2022/iss_i*.json`(新) + `tests/test_flowsheet/test_iss_i.py`(新) + `tests/test_mesh/test_iss_i_aspen_validation.py`(新) + `.github/plans/iss_i_flowsheet_plan.md` | `pytest tests/test_flowsheet/test_iss_i.py -x` |
| 6 | `feat(parity): DWSIM 对标框架` | `src/h2iso/parity/*`(新) + `tests/test_parity/*`(新) + `.github/plans/dwsim_parity_plan.md` | `pytest tests/test_parity/ -x` |
| 7 | `feat(uq): 不确定性传播框架` | `src/h2iso/uq/*`(新) + `tests/test_uq/*`(新) + `docs/uq/`(新) + `pyproject.toml` 的 `uq` extra（SALib）+ `.github/plans/engineering-reliability-plan.md` | `pytest tests/test_uq/ -x` |
| 8 | `feat(cli): 参数化与入口增强` + `chore(docs)` | `src/h2iso/cli.py` + `tests/e2e/*` + `tests/error_paths/*` + `tests/property/test_mass_balance.py` + 其余 plans | `pytest tests/ -x --tb=short`（全量终验） |

排序依据：commit 4 引用 commit 3 的 mesh 接口。commit 5-7 的测试依赖 commit 4 的 flowsheet 改动。`cli.py` 若在 commit 8 前引用 parity/uq 的 CLI 入口，需把对应 import 提到 6/7 之后（建议 cli 保持最后）。

## 四、执行阶段（5 个 Phase）

### Phase A：环境修复（前置）
```bash
python3.12 -m venv .venv            # 重建 venv（当前为 broken symlink）
.venv/bin/pip install -e ".[dev,solver,uq]"
git stash -u                        # 暂存全部未提交内容做安全网（保留 stash 直到 Phase E 完成）
git stash pop                       # 恢复后开始分主题提交
pytest tests/ -q --tb=short         # 基线确认（当前 42+24 文件状态下的测试基线）
```

### Phase B：分主题提交（每 commit 独立）
```bash
git add <本主题文件清单>
git diff --cached --check            # 空白错误检查
git diff --cached --stat             # 负向验证：确认 staging 只有本主题文件
git commit -m "<主题消息>"
pytest <本主题测试子集> -x           # 每 commit 后验证
```
- commit 2/3/4 涉及已修改文件时用 `git add <file>` 显式路径，避免误带其他主题。
- 跨主题文件（如 `tests/test_flowsheet/test_schema.py` 同时含 commit 4 与上游冲突内容）保持整体进 commit 4，不拆 hunk。

### Phase C：集成分支预演（一次性解决 6 文件冲突）
```bash
git checkout -b integration/wang2022 main
git merge --no-commit asipp/pr/8     # 引入上游堆叠链最终态
# 解决 6 文件冲突，决策原则：
#   solver.py   → 保留 PR5 的 f"{name}_out" 快路径 + 本地按 config.equilibrators 的精确匹配回退（两者语义可叠加）
#   schema.py   → splitter 字段族与 inside_diameter_m/HETP_m 字段族都保留（同 dataclass 不同字段，无语义冲突）
#   4 个测试文件 → 断言数值以 PR 拓扑修复为准，保留本地 f-string 断言消息改进
pytest tests/ -q --tb=short          # 集成分支全量验证
git commit --no-edit                 # 记录集成解决方案
```

### Phase D：正式合并上游 PR
1. 按 #2 → #5 → #6 → #8 顺序逐个合并（或评审通过后按顺序点 merge）。
2. 每个 PR merge 时若遇冲突，复用 Phase C 已验证的 6 个文件内容解决（不需重新做语义决策）。
3. 因堆叠关系，#5 的增量冲突只剩 solver.py 相关，#6/#8 的增量冲突只剩 schema.py 相关，工作量递减。

### Phase E：终验与清理
```bash
git checkout main
pytest tests/ -q --tb=short          # 全量
git log --oneline -15                # 核对提交序列
git stash drop                       # 确认无误后丢弃安全网 stash
git push origin main && git push asipp main
```

## 五、需要你决策的问题（执行前回答）

1. **`.opencode/` 是否入库**：建议不提交并加入 `.gitignore`（agent 工具链配置按技术秘密处理，且含本机路径）。
2. **杂项文件归属**：`h2iso_results.json`、`figures/`、`script/`、`constraints/`、`AGENTS.md` 哪些入库？建议 `script/`、`constraints/`、`AGENTS.md` 入库（AGENTS.md 为仓库级项目指南，归 commit 1），结果类文件（`h2iso_results.json`、`figures/`）不入库。
3. **solver.py 双实现取舍**：本地实现与 PR5 实现取其一，还是按 Phase C 建议合并两者？（推荐合并）
4. **两套 ISS-I 数据**：本地 `iss_i.json`（Aspen 基线）与上游 `wang2022_issi.json` 是否重复建设？建议与 couuas 沟通后再定，避免两套并存。
5. **提交顺序**：确认采用方案 A（先本地后上游），还是方案 B（先上游后本地）。

## 六、风险与回滚

- 每个主题 commit 独立，单主题出错可 `git revert` 单 commit，不影响其余 7 个。
- Phase A 的 `git stash -u` 是全程安全网，Phase E 前不删除。
- `integration/wang2022` 分支保留不删，作为冲突解决方案的存档。
- 每次 commit 前 `git diff --cached --stat` 负向验证 staging 范围（防误带文件）。
- 当前 origin/asipp 均无他人推送（0/0 分叉），push 窗口安全。若期间 couuas 有新的 push，重新拉取后再合并。

## Next Steps

- 回答第五节 5 个决策问题后，可委派 @Plan Architect 将本计划转成 PM 任务卡（含验收标准），或直接由 task-executor 按 Phase A→E 执行。
- 本计划文件可按需移动到 `.github/plans/local-commit-plan-2026-09-01.md`（repo-reviewer 权限仅覆盖 `.github/reviews/`，未越权写入 plans 目录）。
