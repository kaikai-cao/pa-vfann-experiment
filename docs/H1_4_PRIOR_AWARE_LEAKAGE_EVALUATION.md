# H1.4 — Prior-aware Negative Membership Leakage Evaluation

- 基线：`75fdcac1b228273ce90bac0bf229bbc6ea39b9c7`（H1.3 HEAD）
- 分支：`research/h1-4-prior-aware-negative-leakage`
- 隔离 worktree：`D:\Research\pa-vfann-h1-4-prior-aware-workspace`
- 性质：对 H1.3 负成员推断的只读再评估。不新增 ACL、不重建向量/图/查询、不重跑 H1.2/H1.3 驱动、不升级 ILP/ML、不进入 E2/H2、不设计防御、不追加样本。

## 0. 要回答的问题

H1.3 在 1% 授权率下平均确定约 4,477（random）或 4,994（clustered）个未授权节点，且没有误报。但"未授权 precision=1.0"本身不能说明攻击有效：

1. 1% 授权率下，任意节点的未授权先验已经是 0.99；把全部节点标为未授权也有约 0.99 的 accuracy。
2. 高频访问节点是否本来就更容易被选为未授权标签，需要用只依赖公开检索环境的基线排除。

本轮把"未授权"作为正类别，用 B0/B1/B2 三种先验对照，检验 H1.3 的负成员标签是否携带超出先验、随机猜测和公开路径频率的信息。

## 1. 复用与重建边界

- 从 H1.2 的 240 个 ACL CSV（`acl_seed`、`mask_sha256`、`authorized_docs`）重建策略，逐项比对 mask SHA-256 与 cardinality。
- 从冻结配置重建 10,000×128 向量、200 查询、exact-kNN 图与 200 条完整公开路径；六项环境哈希与 H1.2、H1.3 manifest 完全一致。
- H1.2/H1.3 的 CSV 与 manifest 内容哈希均与各自 manifest 记录一致；未修改任何既有文件。
- H1.3 攻击输出是**重新构建**而非直接读取结果：按三类停止约束调用 H1.3 的 `public_constraints` + `infer_from_constraints`，再逐 ACL 对照 H1.3 的 `predicted_unauthorized`、`unauth_tp`、`unauth_fp`、`determined_fraction`，240/240 一致。
- 攻击侧函数签名仍为 `(n, constraints, authorized_count)`，无 ACL / mask / policy / result ID；真实 ACL 只进入评分函数 `score_negative_labels`。

## 2. 三种对照基线

| 基线 | 预测方式 | 使用的信息 |
|---|---|---|
| B0 All-negative | 全部 `N=10000` 节点标为未授权 | 仅类别先验 |
| B1 Matched-budget random | 均匀无放回抽取与 H1.3 相同数量 `L` 的节点 | 先验 + 预测预算 `L`，每 ACL 固定 seed 可复现 |
| B2 Public-path frequency | 按 200 条**完整**公开路径的节点访问次数降序取前 `L`；同频按 node ID 升序 | 仅公开图/查询访问结构 |

B2 在读取任何 ACL 之前构造一次，不使用停止位置 `τ`、ACL 位图或结果 ID。其排序与计数哈希写入 manifest。B1 的解析先验为

\[
\mathbb{E}[FP]=\frac{LM}{N},\qquad
P(FP=0)=\frac{\binom{N-M}{L}}{\binom{N}{L}}
\]

其中 `M` 为授权数、`N=10000`。解析值由 log-gamma 计算，并与 `scipy.stats.hypergeom.pmf(0, N, M, L)` 独立核对一致。为避免口径误读，CSV 中名为 `h1_3_budget_*_random` 的列表示"按 H1.3 攻击预算 L 的解析随机基线"，对所有方法共用，不是各方法自身的 FP 期望。

## 3. 指标与统计口径

以未授权为正类别，每个 ACL × 每种方法记录 `TP/FP/FN/TN`、`Precision=TP/(TP+FP)`、`Recall=TP/(N-M)`、`FPR=FP/M`、`Specificity=TN/M`、`BalancedAccuracy=(Recall+Specificity)/2`。`L=0` 时 precision 记为缺失，其余指标仍定义良好。

统计单位为 **ACL 实例**，不是 query。每个 cell 的 30 个 ACL 做 5,000 次配对 percentile bootstrap：同一重采样索引同时用于两种方法，得到逐 ACL 差值的均值与 95% CI。主验证组预先固定为 `random/1%`（固定大小均匀随机 ACL，超几何先验精确成立），其余 7 个 cell 仅作次级描述，不做事后挑组。

预先固定的升级条件（全部满足才算通过）：

- H1.3 相对 B2 的平均 Balanced Accuracy 提升 `≥0.05`；
- 相对 B2 的配对 95% CI 下界 `>0`；
- 相对 B1 同时满足上述两条；
- H1.3 未授权标签误报数为 0。

## 4. 正确性门禁

| 检查 | 结果 |
|---|---|
| 环境哈希（向量/查询/qdist/图/公开路径/配置） | 6/6 与 H1.2、H1.3 一致 |
| 复用 H1.2/H1.3 输入文件哈希 | 4/4 一致 |
| ACL mask 重建 | 240/240 SHA-256 与 cardinality 一致 |
| H1.3 攻击输出复核 | 240/240 预测数、TP、FP、确定标签比例一致 |
| 混淆矩阵与指标恒等式 | 960/960 行通过 |
| 攻击输入 | 无 ACL / mask / policy / result ID |
| B2 输入 | 无停止位置 / ACL / 结果 ID |
| 超几何解析值 | 与 `scipy.stats.hypergeom` 独立核对一致 |
| 输出文件哈希 | 3/3 与 manifest 一致 |

完整测试 **81 passed**（H1.3 基线 68 + 新增 13）。

## 5. 主验证组：random / 1%

30 个独立 ACL 的均值（"未授权"为正类别）：

| 方法 | L | TP | FP | Recall | FPR | Specificity | Balanced Accuracy |
|---|---:|---:|---:|---:|---:|---:|---:|
| H1.3 prefix | 4476.9 | 4476.9 | **0.0** | 0.4522 | **0.0000** | 1.0000 | **0.7261** |
| B0 all-negative | 10000.0 | 9900.0 | 100.0 | 1.0000 | 1.0000 | 0.0000 | 0.5000 |
| B1 matched-random | 4476.9 | 4430.7 | 46.2 | 0.4475 | 0.4620 | 0.5380 | 0.4928 |
| B2 path-frequency | 4476.9 | 4432.5 | 44.4 | 0.4477 | 0.4437 | 0.5563 | 0.5020 |

B1 的解析期望为 `E[FP]=44.769`，单次完全零误报概率约 `5.48×10⁻⁵`；实测单次随机抽样均值 FP=46.2，与解析期望一致。B2 的 FP 均值 44.4 也接近随机预算基线，说明完整公开路径频率排序在这个固定均匀随机 ACL 下并没有显著偏向授权集合。

配对 ACL-level bootstrap（5,000 次）：

- 相对 B2：`ΔBA=+0.2241`，95% CI `[+0.1778, +0.2682]`。
- 相对 B1：`ΔBA=+0.2333`，95% CI `[+0.1909, +0.2742]`。
- H1.3 在 30 个 ACL 上未授权误报总数为 0。

四项升级条件全部满足，manifest 决策为 **`CANDIDATE_NEGATIVE_MEMBERSHIP_LEAKAGE`**。

## 6. 次级 cell

H1.3 相对 B2 的平均 ΔBalanced Accuracy（95% CI）：

| policy / sel% | ΔBA vs B2 | 95% CI | H1.3 FP 总数 |
|---|---:|---:|---:|
| clustered / 1% | +0.2503 | [+0.2042, +0.2951] | 0 |
| random / 5% | +0.0188 | [+0.0138, +0.0241] | 0 |
| clustered / 5% | +0.0150 | [+0.0105, +0.0205] | 0 |
| random / 10% | +0.0008 | [+0.0000, +0.0017] | 0 |
| clustered / 10% | +0.0006 | [+0.0000, +0.0014] | 0 |
| random / 30% | 0.0000 | [0.0000, 0.0000] | 0 |
| clustered / 30% | 0.0000 | [0.0000, 0.0000] | 0 |

这些是次级描述，不用于宣称通过预注册判据。规律是：低选择率档收益大，5% 档很小，10%/30% 档基本消失。

## 7. 解释与边界

- H1.4 支持的是一个更窄的结论：在当前固定图、固定 200 查询和 E1 停止规则下，前缀约束能把大批节点判定为"确定未授权"，其信息增益体现在 **Specificity=1**（零误报），而不是更高的未授权召回。H1.3 与 B1/B2 的 recall 几乎相同（0.4522 vs 0.4475/0.4477）。
- 这与 H1.3 的结论并不冲突：确定性传播仍没有恢复任何新的**授权**成员。正成员恢复增益为 0 的结论保持不变。
- H1.3 的未授权 precision=1 由约束传播与 soundness 检查保证，不是独立证据；本轮的新证据是它显著优于同预算随机猜测与公开路径频率基线。
- B1/B2 的预算 `L` 取自 H1.3 攻击输出，属于"同等预测数量"的公平对照，不是独立攻击算法。配对 bootstrap 的单位是 30 个 ACL；不能把 200 条查询当作独立样本。
- 随机/1% 的超几何先验只对均匀随机 ACL 精确成立；clustered 档只作次级描述，不能把解析零误报概率直接搬过去。
- 不声称跨数据集、跨 ANN 图、跨查询分布或真实企业 ACL 的泛化；不声称访问模式隐私、在线无损停止、形式化安全证明或实际可部署攻击。没有引入 ILP/ML、防御机制或 E2 路径变化。
- 按用户设定的后续决策表，本轮结果只够"保留负成员泄露方向"；是否进一步研究其形式化性质和实际攻击价值，须单独决策。本阶段到此停止，等待独立验收。

## 8. 交付与复算

新增且仅新增六个文件：

- `experiments/run_h1_4_prior_aware_evaluation.py`
- `tests/test_h1_4_prior_aware_evaluation.py`
- `docs/H1_4_PRIOR_AWARE_LEAKAGE_EVALUATION.md`
- `results/h1_4_prior_aware/acl_metrics.csv`（960 行：240 ACL × 4 方法）
- `results/h1_4_prior_aware/summary.csv`（32 行：8 cell × 4 方法）
- `results/h1_4_prior_aware/manifest.json`

复算命令：

```
PYTHONPATH="src;tests" python -m pytest -q
python experiments/run_h1_4_prior_aware_evaluation.py
```

H1.1～H1.3 的文件、结果、配置与搜索实现零改动。本轮完成后停止，等待独立验收。
