# EXP-01 勘误：达标预算表的 random / clustered 口径

- 状态：本文件为 EXP-09 新增勘误，**不修改** `docs/EXP01_REPORT.md` 与任何历史 CSV。
- 核验基线：本工作区 `exp09-policy-oblivious-stop` @ `14862ad2b775d1005f47d6ca3a734de0b61fca31`；EXP-01 原始数据文件与 `0145cca` 完全一致。
- 证据等级：`[原文 CSV]`——数值直接来自 `results/tables/budget_to_recall_090.csv`，并由 `results/raw/experiment_results.csv` 的分组聚合复核；`[原报告]`——`docs/EXP01_REPORT.md` §7。

## 1. 原报告中的具体错误

`[原报告]` §7（约第 92–99 行）写：

> `results/tables/budget_to_recall_090.csv`：达标最小预算（节选，Random / Clustered 结果一致）：
>
> | 选择率 | E1 | E2 r=1 | E2 r=2 | E2 r=4 | E3 |
> |---|---|---|---|---|---|
> | 1% | NOT_REACHED | NOT_REACHED | 1000 | 1000 | NOT_REACHED |
> | 5% | 500 | NOT_REACHED | 200 | 500 | 500 |
> | 10% | 200 | NOT_REACHED | NOT_REACHED | 200 | 200 |
> | 30% | NOT_REACHED | NOT_REACHED | NOT_REACHED | NOT_REACHED | 100 |

两处错误：

1. **括注错误**："Random / Clustered 结果一致" 在 1% 选择率下不成立。
2. **表格数值错误**：1% 行的 `E2 r=4 = 1000` 只对应 clustered；同一行的 E1、E3、E2 r=1、E2 r=2 对应 random。即该行**混用了两种策略分布**，既不是纯 random 也不是纯 clustered。

## 2. 对应 CSV 分组与正确数值

`[原文 CSV]` `results/tables/budget_to_recall_090.csv` 的 1% 分组（分组键 `policy_type × selectivity_pct × algorithm`）：

| policy_type | selectivity_pct | algorithm | min_budget_reaching_090 | max_mean_recall |
|---|---|---|---|---|
| clustered | 1.0 | E1_POSTFILTER | 1000 | 0.9190 |
| clustered | 1.0 | E2_BRIDGE_r1 | NOT_REACHED | 0.8960 |
| clustered | 1.0 | E2_BRIDGE_r2 | 1000 | 0.9845 |
| clustered | 1.0 | E2_BRIDGE_r4 | 1000 | 0.9190 |
| clustered | 1.0 | E3_FIXED_TRACE | 1000 | 0.9190 |
| random | 1.0 | E1_POSTFILTER | NOT_REACHED | 0.8840 |
| random | 1.0 | E2_BRIDGE_r1 | NOT_REACHED | 0.8390 |
| random | 1.0 | E2_BRIDGE_r2 | 1000 | 0.9820 |
| random | 1.0 | E2_BRIDGE_r4 | NOT_REACHED | 0.8840 |
| random | 1.0 | E3_FIXED_TRACE | NOT_REACHED | 0.8840 |

逐列比对 1% 行：

| 列 | 原报告值 | random（CSV） | clustered（CSV） | 判定 |
|---|---|---|---|---|
| E1 | NOT_REACHED | NOT_REACHED | 1000 | 与 random 一致 |
| E2 r=1 | NOT_REACHED | NOT_REACHED | NOT_REACHED | 两者一致 |
| E2 r=2 | 1000 | 1000 | 1000 | 两者一致 |
| E2 r=4 | 1000 | NOT_REACHED | 1000 | **与 clustered 一致，与 random 冲突** |
| E3 | NOT_REACHED | NOT_REACHED | 1000 | 与 random 一致 |

正确写法应为两行分立：

| 选择率 | 分布 | E1 | E2 r=1 | E2 r=2 | E2 r=4 | E3 |
|---|---|---|---|---|---|---|
| 1% | random | NOT_REACHED | NOT_REACHED | 1000 | NOT_REACHED | NOT_REACHED |
| 1% | clustered | 1000 | NOT_REACHED | 1000 | 1000 | 1000 |

5% / 10% / 30% 三档的 10 个分组逐项核对：random 与 clustered 的达标预算**完全一致**，原报告的这两三行数值无误。因此错误范围被限定在 1% 一档。

## 3. 对原有实验结论的影响

1. **受影响**：`[原报告]` §9 观察 8 的表述"σ 扫描未见系统性差异"针对的是 correlation 实验的 σ 维度（见 §9 观察 8 上下文），**不是**本次勘误的 random/clustered 拓扑维度；本勘误不推翻该观察。但 §7 的"结果一致"括注若在 β 口径下被引用为"拓扑无关"，则该引用无效：1% 档下 E1、E2 r=4、E3 三个算法的达标预算随拓扑从 NOT_REACHED 变为 1000。
2. **不受影响**：§9 观察 1（E3 策略无关性）、观察 2–7（召回/成本格局）、观察 9–10（猜想）均由 `results/raw/experiment_results.csv` 与 `results/tables/leakage_summary.csv` 支撑，未引用 §7 的达标表。
3. **定量影响范围**：受影响的格子 = 1 个选择率档 × 5 个算法 × 2 个拓扑 = 10 个 CSV 分组中的 3 个不一致分组（E1、E2 r=4、E3）；占全表 40 个分组（4 选择率 × 5 算法 × 2 拓扑）的 3/40。

## 4. 证据缺口

- `[原文 CSV]` 只能确认达标预算与最大平均召回的差异，**不能**解释差异机制（为何 clustered 1% 下更容易达到 0.90）。可能原因包括 clustered 授权与向量位置的空间耦合，但本轮未做机制检验，记为 `INSUFFICIENT_EVIDENCE`，不写入结论。
- 原报告 §7 表格为何混用两种口径，无提交说明或日志证据，记为 `UNKNOWN`，不推测作者意图。

## 5. 处理原则

- 不删除、不覆盖原报告；EXP-09 及后续报告引用 §7 达标表时，必须按 `policy_type` 分别列出，且 1% 档以本节第 2 页两行表为准。
- 原始 CSV 与 `budget_to_recall_090.csv` 保持不变；本勘误为新文件。
