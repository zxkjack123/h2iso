# h2iso 方法学论文：大纲与工作方案

**版本**: v0.1（草案）
**日期**: 2026-05-19
**作者**: 张小康（通讯）
**目标期刊**: 第一优先 *Fusion Engineering and Design* (FED, IF≈2.0, 聚变工程方向匹配)；
备选 *Fusion Science and Technology* (FST)、*Nuclear Engineering and Design* (NED)
**目标定位**: methodology paper（开源、可复现、可耦合 tricys），不是参数研究。

---

## 1 论文一句话定位

h2iso 是一个开源 Python 库，把氢同位素低温精馏的稳态求解（MESH + 真实 SRK EOS + 氚量子修正 + 多塔/再循环 Wegstein 收敛）与 Modelica 代码生成耦合，使聚变氚燃料循环系统级仿真获得真正基于物性的 ISS 模块，而不是以经验黑箱代替。

---

## 2 创新点（reviewer 看 abstract 的 30 秒内必须看到）

1. **氚感知量子修正的 Souers 锚定 + SRK EOS 联合实现**——既保留 Souers 实验拟合在 T₂/HT 的精度，又在多压力下用 SRK 给出热力学一致的 K 值。
2. **稳态 → Modelica 初值的代码生成管线**：稳态结果直接作为 Modelica record 注入 tricys L3 黑箱模型，消除手工传参的复制误差。
3. **首个开源、可复现的 H₂/D₂/T₂/HD/HT/DT 六组分多塔级联工具链**，含 Wang 2022 CD2 与 ISS-O 三塔级联两组基准回归测试。
4. **完整测试金字塔**（property-based + error-path + benchmark + e2e Modelica 编译），降低后续接 tricys/数字孪生的风险。

---

## 3 章节大纲

### Abstract（180–200 字）

聚变氚燃料循环（FFC）的同位素分离系统（ISS）目前在系统级仿真中普遍以经验黑箱建模，限制了对 ISS 工艺与系统耦合的研究。本工作发布 h2iso ——一个开源 Python 库，结合 Souers 蒸汽压锚定（含氚量子修正）、真实 SRK 状态方程、MESH 方程组的 CasADi 求解、Wegstein 撕裂流加速，以及 Modelica 代码生成接口。h2iso 在 Wang 2022 CD2 基准与三塔 ISS-O 级联两组测试上分别复现产品组成误差 < 2%/< 5%。配合 tricys 0-D 燃料循环框架，h2iso 提供从工艺设计到系统级稳态/瞬态一致的 ISS 模块，且全部源码、测试夹具与回归基准开源。

关键词：聚变燃料循环；氢同位素分离；低温精馏；状态方程；Modelica；开源仿真。

### 1 Introduction（约 1.5 页）

- 1.1 聚变燃料循环对 ISS 仿真的需求（ITER/EU-DEMO/CFETR/BEST/CFEDR）
- 1.2 ISS 的关键热力学难点：氚量子修正、低温窄沸点差、六组分平衡
- 1.3 现有工作综述：
  - Aspen Plus / CHEMCAD 商业模拟器（闭源，licensing 限制，难耦合系统级）
  - Souers 1986 锚定 + 经验关联式
  - Wang 2022（CFEDR 案例研究）
  - 国内外 ISS 数字孪生尝试（ITER ISS、JADA-ISS）
- 1.4 gap：缺一个 **开源 / 可复现 / 可耦合系统级框架** 的 ISS 工具链。
- 1.5 本工作贡献：见 §2。

### 2 Methods（约 4 页，核心）

#### 2.1 物性模型分层

```
[气液平衡 K 值]
    ↑
[Souers anchor T_tp/P_tp]   ←——————— 实验数据（Souers 1986、HepData、ITER ISS-1.0）
    +
[SRK EOS + Wilson kij]      ←——————— 真气体修正（Wang 2022 拟合）
    +
[氚量子修正 Δω(T,quantum)]   ←——————— 校正同位素效应
```

- 2.1.1 Souers anchor：T_tp、P_tp、ΔH_vap 拟合
- 2.1.2 Wilson kij 数据来源与不确定性
- 2.1.3 氚量子修正：高温下衰减、低温下放大

#### 2.2 MESH 方程组与 CasADi 求解

- 2.2.1 M (material balance) / E (equilibrium) / S (summation) / H (energy)
- 2.2.2 半隐式重整：稳态变量 X_ij、T_j、L_j、V_j
- 2.2.3 CasADi 自动微分 + IPOPT 内点法
- 2.2.4 临界点附近的连续性处理（Phase 3 修复点：`_solve_step` 逻辑反转）

#### 2.3 多塔互联与 Wegstein 撕裂流

- 2.3.1 撕裂流选择（基于图论的最小撕裂集）
- 2.3.2 Wegstein 加速：q 因子自适应、防发散夹紧
- 2.3.3 平衡器子模块（2HT ⇌ H₂ + T₂）

#### 2.4 Modelica 代码生成与 tricys 耦合

- 2.4.1 Modelica record 模板（Phase 2.4.2 成果）
- 2.4.2 稳态值 → 初值参数注入
- 2.4.3 tricys L3 0-D 黑箱模型如何消费 h2iso 输出

#### 2.5 测试金字塔与可复现性

- 单元 → property-based (hypothesis) → 错误路径 → benchmark → e2e Modelica 编译
- CI matrix 配置

### 3 Validation（约 3 页）

#### 3.1 单塔基准：Wang 2022 CD2

- 输入条件、塔规格
- 产品组成误差表（vs Wang 2022 Table X）
- 灵敏度：R、D/F、feed 组成扫掠

#### 3.2 三塔级联：ISS-O fixture

- 拓扑（参见 `tests/fixtures/iss_o/`）
- 物料平衡闭合（5 sig figs）
- Wegstein 收敛迭代史（log 图）

#### 3.3 多压力包络

- 30 / 50 / 100 / 200 kPa 操作点
- K 值 vs Souers 锚定误差

#### 3.4（计划中）三塔级联：ISS-I（CFEDR）

- 待 张世坤 ISS-I 工艺参数齐全后补充
- 若论文投稿前完成，纳入；否则放入 future work

### 4 Discussion（约 1.5 页）

- 4.1 SRK vs Antoine 在低温窄沸点差的差异
- 4.2 Wegstein vs Newton-Krylov 在多塔级联的收敛域比较
- 4.3 与 Aspen Plus 的差距：催化反应器、动态相变、放射性衰变（不在本文范围）
- 4.4 Modelica codegen 的精度损失（discrete vs continuous）

### 5 Conclusion & Future Work（0.5 页）

- 总结四个贡献
- 未来：杂质扩展（CO/CH₄/N₂/He）、板效率/holdup 导出、不确定性传播、tricys 数字孪生在线对齐

### 6 Reproducibility statement（半页，独立小节）

- GitHub 仓库链接（公开化后）
- 主版本号 tag
- 全部 fixture + benchmark 数据
- CI workflow 可在 fork 上一键复现

### Appendix A：Souers 锚定参数完整表

### Appendix B：SRK kij 矩阵

### Appendix C：MESH 方程组完整推导

---

## 4 图表清单（target ≤ 10 个）

| 编号 | 类型 | 内容 | 状态 |
|------|------|------|------|
| F1   | schema | h2iso 模块架构 + 数据流（输入参数 → 物性 → MESH → 输出 + Modelica codegen 分支） | 待画（diagram-architect） |
| F2   | log-log | Souers 锚定误差 vs 温度 / 压力 | 待画 |
| F3   | line  | Wang 2022 CD2 K 值复现 (H₂/D₂/T₂/HD/HT/DT) | 已有数据 |
| F4   | bar   | Wang 2022 CD2 产品组成误差 (h2iso vs Aspen vs experimental) | 待编 |
| F5   | line+marker | ISS-O 三塔 Wegstein 迭代收敛史 | 已有数据 |
| F6   | sankey | ISS-O 三塔级联物料平衡（验证闭合） | 待画 |
| F7   | heatmap | 多压力 SRK vs Antoine K 值差异 | 待画 |
| F8   | timeline | Modelica codegen → tricys 仿真启动到稳态时间 | 待画 |
| T1   | table | h2iso 物性数据来源汇总 | 待编 |
| T2   | table | 完整验证误差矩阵 | 待编 |

---

## 5 工作方案（投稿路径）

### Phase A — 内容补全（启动）

| ID | 任务 | 责任 | 依赖 |
|----|------|------|------|
| A.1 | ISS-I 三塔基准完成（Task 5.1 解锁后） | 张小康 | 张世坤补齐 ISS-I 工艺参数 |
| A.2 | Wang 2022 CD2 多压力扫描 | 张小康 | 无 |
| A.3 | F1 架构图（diagram-architect） | 张小康 | 无 |
| A.4 | F4/F6/F7/F8 图表 | 张小康 | A.1、A.2 |

### Phase B — 初稿（启动）

- 撰写顺序：Methods → Validation → Introduction → Discussion → Conclusion → Abstract
- 委派：academic-writer 完成初稿（输入：本大纲 + h2iso 代码 + 测试结果）
- 长度目标：~10 页 FED 双栏

### Phase C — 共同作者评审

- 邀请：宋江锋（项目层级上级，负责把关 ISS 工艺合理性）、郑善良（包层中心主任，全文把关）
- 时间：2 周

### Phase D — 投稿前打磨

- factcheck-gate L2
- de-ai-fier-gate L2-Full
- innovation-reviewer 新颖性自评
- paper-reviewer 同行评审模拟
- citation-lint 参考文献 .bib 检查

### Phase E — 投稿与回复

- FED 投稿（preferred）
- 平均 4-6 周 first decision
- 若 R&R：review-responder 起草回复
- 若 reject：转 FST

---

## 6 配套产出（与本文同期）

- **专利**：h2iso 的稳态→Modelica 初值代码生成管线适合申请发明专利（系统级耦合接口），与本文论文形成 paper+patent 组合。计划在 Phase B 期间起草交底书。
- **会议**：SOFT 2026（已在 workspace 中筹备）摘要可基于本文做 conference paper / poster。
- **数据集**：所有 fixture + benchmark 结果在论文接收后一并 release 到 GitHub。

---

## 7 风险与备选

| 风险 | 影响 | 缓解 |
|------|------|------|
| ISS-I 工艺参数迟迟拿不到 | 第 3.4 节缺失 | 论文照投，把 ISS-I 放 future work；后续作为单独 short note 投 FST |
| SRK 在某些极端工况发散 | 物性章节削弱 | 已通过 Wegstein 夹紧解决；预留 fallback 到 Souers-only |
| 期刊要求与 Aspen 对比 | 缺商业模拟器使用许可 | 与课题组协商使用许可；或引用 Wang 2022 已发表的 Aspen 结果作为间接对比 |
| 杂质扩展（CO/CH₄/N₂/He）reviewer 必问 | discussion 章节扣分 | 在 future work 明确给出技术路线（与 B5 学生任务呼应） |

---

## 8 时间表（粗粒度，不写具体日期，按里程碑）

| 里程碑 | 触发条件 |
|--------|----------|
| M1 内容补全完成 | A.1–A.4 全部完成 |
| M2 初稿完成 | Phase B 输出 v0.1 manuscript |
| M3 内审通过 | Phase C 完成 |
| M4 投稿 | Phase D 通过所有 quality gate |
| M5 接收 | Phase E 完成 |

每完成一个里程碑，在 `.github/plans/h2iso-paper.md`（本文件后续 split-out 版本）中打钩。

---

## 9 引用此文档

- 本大纲：`/home/gw/opt/h2iso/docs/paper/h2iso_method_paper_outline.md`
- 主仓库：https://github.com/zxkjack123/h2iso（私有）
- 相关计划：`.github/plans/h2iso-phase3-remediation.md`、`.github/plans/phase4/`
