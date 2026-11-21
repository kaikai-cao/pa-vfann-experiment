# PA-VFANN-09 / EXP-01 — Policy-Hiding Filtered ANN 实验原型

**研究问题**：当搜索轨迹不能依赖授权匹配结果时，过滤 ANN 的召回率与检索成本会受到多大影响？

**边界**：这是一个受控算法模拟实验，**不是** HNSW / ACORN / RACORN / Atlas / VIDA 的复现，也**没有**实现 MPC、ORAM、Halo2、SNARK 或任何真实密码学隐私机制。受控 kNN 图模拟器不得称为 HNSW；E2 是自定义受控桥接基线，不得称为 ACORN 或 RACORN。`secret_filter` 是客户端侧的**模拟**接口，仅用于验证「搜索计划不读取授权位」这一算法性质，**不等于**访问模式隐藏或密码学安全。

---

## 1. 环境与一键复现

```bash
# Python 3.11+（本次实际使用 3.14.7）
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt

# 全套：单测 → 选择率实验 → 相关性/泄露实验 → 表格与图 → 单测
PYTHONPATH="src;." .venv/Scripts/python scripts/run_all.py

# 单独运行
PYTHONPATH="src;." .venv/Scripts/python experiments/run_selectivity.py
PYTHONPATH="src;." .venv/Scripts/python experiments/run_correlation.py
PYTHONPATH="src;." .venv/Scripts/python experiments/make_report.py
PYTHONPATH="src" .venv/Scripts/python -m pytest -q
```

`requirements.txt` 中的 scipy 按任务包列出但实际未使用（精确 kNN 由 numpy BLAS 分块实现），故未列为硬依赖。所有实验参数冻结在 `config/experiment.yaml`，主种子 2026 通过 `SeedSequence` 派生数据、查询与各策略的独立随机流。

## 2. 仓库结构

```
config/experiment.yaml            冻结参数（另含 experiment_smoke.yaml 仅作冒烟测试）
src/pa_vfann/
  config.py, dataset.py, graph.py, ground_truth.py, policies.py,
  search_common.py, baseline_postfilter.py, filter_aware.py,
  fixed_trace.py, secret_filter.py, leakage.py, metrics.py
experiments/
  run_selectivity.py, run_correlation.py, make_report.py, exp_common.py
scripts/run_all.py
tests/                            数据/图/GT/E1/E2/E3/预算/泄露/CSV 完整性
results/raw|tables|figures
docs/EXP01_REPORT.md              实验报告
```

`config.py`（YAML 读取）、`policies.py`（授权标签）、`secret_filter.py`（模拟过滤接口）、`exp_common.py` 与 `make_report.py` 是任务包结构之外的最小必要补充，均在本文明确说明。

## 3. 统一设置

| 参数 | 数值 |
|---|---:|
| 向量数量 / 维度 | 10,000 / 128（i.i.d. 标准正态，float32） |
| 查询数量 | 200（独立标准正态流） |
| Top-K | 10 |
| 图节点出度 | 16（精确 kNN，L2） |
| 搜索预算 | 20 / 50 / 100 / 200 / 500 / 1000 |
| 授权选择率 | 1% / 5% / 10% / 30% |
| 随机种子 | 2026 |
| 距离 | 平方 L2（排序与报告中的距离开方由 `np.linalg` 语义等价；全链路统一用平方 L2 排序） |

三种算法使用同一数据集、同一图、同一批查询、同一份授权标签。失败查询一律保留，不删除、不重采样。

## 4. 图构造

1. 对 10,000 个向量分块计算精确平方 L2 距离矩阵（块大小 500）。
2. 每个节点取距离最近的 16 个**其他**节点作为出边（并列按节点 id 稳定排序）。
3. `add_reverse_edges: true`：取正向边与反向边的**并集**作为搜索邻接表，得到对称无向图；出度仍严格为 16，无向度可能大于 16；无自环。
4. 连通性**不作保证**：运行日志与实验记录中报告实际连通分量数（本次主配置实测为 1），不对未连通图的跨分量检索作任何外推。

该图是**可控精确 kNN 图模拟器**，不是 HNSW，也不声称 HNSW 的真实性能。

## 5. 授权标签分布

- **Random Policy**：以策略派生随机流无放回抽取目标数量的记录，标签与向量位置独立。
- **Clustered Policy**：选取 3 个固定样本点作为中心，按 `exp(-d²/(2σ²))` 归一化权重无放回抽样；σ 越小，授权记录越集中在中心附近。默认 σ=40；相关性实验扫描 σ∈{15,40,120,10⁶}（最后一个近似随机）。
- 每次实验记录**实际授权记录数**与**实际选择率**；授权不足 K 时不伪造结果，以占位符返回并在 CSV 中标记 `insufficient_gt`。

## 6. Ground Truth

`GroundTruth(q,P)` = 在满足授权策略 P 的全部记录中，按与实验统一的平方 L2 距离升序（并列按 id）取最近 K 条。由全量暴力排序计算，**不使用任何 ANN 搜索算法**。测试验证：只含授权记录、距离升序、不超过 K、可重复、授权不足时不超过真实数量。

## 7. 三种算法

**E1 — Adaptive Post-filter**：距离优先 best-first 遍历，与 E3 使用**同一个公开搜索计划**；唯一自适应行为是服务端读取授权匹配位，在已访问节点中合法数 ≥ K 且访问数 ≥ `initial_budget`(20) 时提前停止。未授权节点不会被提权或压制。

**E2 — Predicate-aware Search（自定义受控桥接）**：
1. 只有授权节点进入结果候选集；未授权节点仅作桥接，永不返回。
2. 自上一个授权节点起，连续未授权节点数不得超过 `r`；授权邻居总是可入队并把计数清零。
3. 队列优先级 `(平方L2距离, 桥接跳数, 节点id)`；同一节点重复入队时以**首次弹出**确定跳数（惰性去重）。
4. 预算计入桥接节点。r∈{1,2,4}。

**E3 — Fixed-trace Private Filtering**：
1. `plan_fixed_trace(q, G, B)` **只**接受查询距离、图与预算，不接触 policy / 授权标签 / 匹配位 / 合法数。
2. 完整访问计划后才调用**独立的模拟过滤接口** `secret_filter.py`，按距离返回合法 Top-K；不足 K 用 `None` 占位并记录真实数量。
3. 不因合法数提前停止。核心可测性质：`T(q,G,B,P₁) = T(q,G,B,P₂)`。

**预算口径**（三算法一致）：`budget` = 唯一访问节点数上限；另分别记录 `expanded_nodes_count`（枚举邻居的节点数）与 `neighbor_checks_count`（逐边检查次数，含重复），三者绝不合并。批量运行先执行一次最大预算搜索，再用 `truncate_outcome` 取精确前缀得到小预算结果；预算只截断遍历长度，不改变优先级/入队/停止规则，因此前缀与直接运行等价（有单元测试逐字段比对）。

## 8. 比较与泄露

- **比较 A（同预算）**：Recall@10、唯一访问节点数、扩展节点数、邻居检查次数、合法候选数、返回数。
- **比较 B（达标成本）**：每算法达到平均 Recall@10 ≥ 0.90 的最小预算；未达到记 `NOT_REACHED`。同时报告 P95 唯一访问节点数。
- **泄露**：`L_set = 1 − |T₁∩T₂|/|T₁∪T₂|`（两集合皆空按 0），序列差异用归一化编辑距离（公共前后缀裁剪后动态规划）。停止位置、返回数量、返回 ID 三类泄露**分别报告**。
- E3 只保证**搜索计划**不受授权策略影响；输出 ID、结果数量、公开图本身均未被隐藏，不据此声称完整访问模式隐私。

## 9. 产物

```
results/raw/experiment_results.csv
results/tables/summary_by_selectivity.csv
results/tables/budget_to_recall_090.csv
results/tables/leakage_summary.csv
results/figures/recall_vs_budget.png
results/figures/budget_to_recall.png
results/figures/p95_access_nodes.png
results/figures/trace_leakage.png
```

## 10. 边界与禁令（必守）

- 不实现密码学协议；不声称 MPC / ORAM / ZK / PIR；不把模拟过滤当真实隐私机制。
- 不把受控精确 kNN 图称 HNSW，不把 E2 称 ACORN/RACORN。
- 不外推真实 HNSW 性能、真实 Agent 授权系统或 exactly-once 语义。
- 不删除失败查询；授权不足 K 必须占位并标记，不得伪造 K 条。
- N=200 查询为工程规模测量，非统计显著性证明，也非形式化安全证明。
