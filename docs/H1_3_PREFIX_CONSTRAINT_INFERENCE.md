# H1.3 — E1 Prefix-Constraint Inference

- 基线：`b60447ec8b78a4d208261d301978df35357acc82`（H1.2 HEAD）
- 分支：`research/h1-3-prefix-constraint-leakage`
- 隔离 worktree：`D:\Research\pa-vfann-h1-3-prefix-constraint-workspace`
- 性质：对 H1.2 已有 240 个 ACL 与 200 条固定公开路径的只读再分析；不新增 ACL、不重建向量/图/查询、不进入 E2/H2、不设计防御、不升级 ILP 或机器学习。

## 0. 威胁模型边界

本审计沿用用户收紧后的架构条件：

- 可信组件（客户端 / TEE）持有 ACL，执行授权检查并决定何时达到 `K` 个授权节点。
- 不可信索引存储服务提供图节点与邻接信息，观察节点 ID、访问顺序和请求结束位置，但看不到 ACL 位图与最终解密结果。
- 若由索引服务自己执行 ACL 判断，则它本来持有授权位，"隐藏 ACL 成员推断"不成立；本实验不覆盖该架构。

## 1. 复用的实验环境与 ACL

脚本从冻结配置重建 H1.2 的检索环境，并逐项比对 H1.2 `manifest.json` 的六项内容哈希（vectors、queries、qdist、graph、public paths、config），全部一致。

- 200 条公开遍历路径，预算 `B=1000`。
- H1.2 的 240 个 ACL 由 CSV 中记录的 `acl_seed` 重建，`mask_sha256`、`authorized_docs`、`informative_queries`、`tau_eq_m`、`tau_eq_B`、`unique_inferred_nodes` 全部与 H1.2 记录一致。
- 未新建 ACL 实例；ACL seed 的复现只用于生成可信侧的停止位置，不进入攻击输入。

## 2. 完整停止约束

对每条查询，公开路径为 `π_q`，停止位置为 `τ`。攻击只使用 `π_q`、`τ` 和公开参数 `m=20`、`K=10`、`B=1000`：

| 情形 | 公开约束 |
|---|---|
| `τ=m` | `Σ_{i=1}^{m} a_{π_q[i]} ≥ K` |
| `m<τ<B` | `Σ_{i=1}^{τ-1} a_{π_q[i]} = K-1`，且 `a_{π_q[τ]}=1` |
| `τ=B` | `Σ_{i=1}^{B-1} a_{π_q[i]} ≤ K-1` |

多个查询的约束共同形成关于隐藏 ACL 位图的公开线性约束系统。本轮只做确定性 bound propagation：若某前缀的上界等于当前最大可能授权数，则其中未知节点全部标为授权；若下界已等于允许的最大授权数，则未知节点全部标为未授权。不调用 ILP、不训练分类器。

三个逻辑角色保持分离：

1. H1.2 的 `simulate_e1_stop`：可信执行侧，使用 ACL 生成 `τ`。
2. 本轮 `public_constraints` 与 `infer_from_constraints`：攻击侧，只接收公开路径、停止位置和公开参数；签名中无 ACL、mask、policy 或结果 ID。
3. 本轮 `score_labels`：独立评估，在攻击输出产生后才读取真实 ACL。

可选辅助知识：授权集合总大小 `M`。该聚合数值作为单独变体 `prefix_with_size` 加入全局等式 `Σ_v a_v = M`；它与 `prefix_no_size` 分开报告。

## 3. 对照与预先固定的停止阈值

对照变体：

- `terminal_only`：H1.1/H1.2 的终端节点攻击，只把 `π_q[τ]` 标为授权。
- `prefix_no_size`：完整三类停止约束 + 确定性传播。
- `prefix_with_size`：同上 + 已知 `M`。

预先固定并以 manifest 记录的升级判据（只看主攻击 `prefix_no_size`）：至少在一个 cell 中同时满足

- 平均每 ACL 新增恢复授权成员 `≥5`；
- 出现新增授权成员的 ACL 比例 `≥0.50`；
- 平均授权召回相对增益 `≥10%`；

且 precision 无反例，才视为值得升级到更强约束求解方法。否则按停止条件结束，不追加 ILP/ML。

## 4. 正确性门禁

| 检查 | 结果 |
|---|---|
| H1.2 环境哈希 | 6/6 一致 |
| H1.2 ACL mask 重建 | 240/240 SHA-256 一致 |
| H1.2 停止聚合统计 | 240/240 `τ=m`/`τ=B`/informative 一致 |
| 攻击函数输入 | 无 ACL / mask / policy / result ID |
| 授权推断误报 | 0 |
| 未授权推断误报 | 0 |
| terminal recall vs H1.2 coverage | 240/240 完全一致 |
| `prefix_with_size` vs `prefix_no_size` | 四个核心输出列逐 ACL 完全相同 |

所有 informative events 的确定性引理由 H1.2 已验证；本轮只复用其停止位置，不再重做攻击发现。

## 5. 结果：授权成员恢复没有额外增益

三个变体共 `240×3=720` 行结果，8 个 cell × 3 变体共 24 行汇总。

- 所有 `prefix_no_size` 与 `prefix_with_size` 的 `new_authorized_nodes = 0`：确定性约束传播没有恢复任何超出 terminal-only 的授权成员。
- 授权召回、授权 precision 与 terminal-only 完全相同；`mean_relative_recall_gain = 0`。
- 授权推断 precision 为 1，未授权推断 precision 为 1（在存在未授权标签的 cell 中）。
- 已知 `M` 没有带来任何额外标签：辅助知识变体与主变体逐 ACL 完全一致。

按预先固定的判据：**未达到升级阈值，决策为 `STOP_NO_ESCALATION`**。不启动 ILP、不引入机器学习、不设计为提升召回而改动实验条件。

## 6. 结果：额外确定的是未授权（负成员）标签

prefix 约束确实提升了"已确定标签比例"，但这些新增标签全部是未授权标签，不是新的授权成员。下表为主变体相对 terminal-only 的均值变化：

| policy / sel% | 新增未授权节点均值 | 出现新增未授权的 ACL 比例 | 确定标签比例增益 | 未授权 recall |
|---|---:|---:|---:|---:|
| random / 1% | 4476.9 | 1.00 | 0.4477 | 0.4522 |
| clustered / 1% | 4994.0 | 0.93 | 0.4994 | 0.5044 |
| random / 5% | 335.4 | 0.83 | 0.0335 | 0.0353 |
| clustered / 5% | 283.1 | 0.83 | 0.0283 | 0.0298 |
| random / 10% | 12.9 | 0.13 | 0.0013 | 0.0014 |
| clustered / 10% | 8.1 | 0.10 | 0.0008 | 0.0009 |
| random / 30% | 0.0 | 0.00 | 0.0000 | 0.0000 |
| clustered / 30% | 0.0 | 0.00 | 0.0000 | 0.0000 |

跨 ACL 的范围显示幅度很不稳定：例如 1% 档新增未授权节点 random 为 660–8336、clustered 为 0–7540。也就是说，低选择率下多数 ACL 能确定大量负成员，但数量随 ACL 变化很大；30% 档没有 `τ=B` 上界约束，因而没有新增负标签。

这个现象被记录为次级观测，未纳入本轮升级判据：它不等同于"恢复更多授权成员"，也不能单凭均值宣称稳定恢复。manifest 中 `secondary_label_determination.in_escalation_gate = false` 明确标出这一边界。

## 7. 解释与研究定位

- H1.3 没有推翻 H1.1/H1.2；它把可主张的 Positive-membership 结论收紧为：在当前图和查询工作负载下，terminal-only 停止边界是简单确定性传播能够恢复授权成员的主要来源。
- 多查询前缀约束在本实验中没有增加授权成员恢复；因此"从一系列普通 ANN 请求系统性恢复更多授权成员"尚未得到支持，不能写成论文贡献。
- 约束传播能增加负成员标签，尤其在 1%/5% 档；这属于隐藏 ACL 的负成员信息泄露，但幅度不稳定，且不等于用户最关注的授权成员恢复。
- 本轮不做跨数据集、跨 ANN 图或真实企业 ACL 的泛化主张；不声称访问模式隐私、在线无损停止或 PA-VFANN 普遍优于现有方法。
- 后续若继续，必须先明确负成员标签是否构成独立研究问题，或另设可产生正成员增益的信息源；本阶段不自动进入 H1.3-extension、E2、H2 或防御设计。

## 8. 交付与复算

新增且仅新增六个文件：

- `experiments/run_h1_3_prefix_constraint_inference.py`
- `tests/test_h1_3_prefix_constraint_inference.py`
- `docs/H1_3_PREFIX_CONSTRAINT_INFERENCE.md`
- `results/h1_3_prefix_constraint/acl_metrics.csv`
- `results/h1_3_prefix_constraint/summary.csv`
- `results/h1_3_prefix_constraint/manifest.json`

完整测试 **68 passed**（H1.2 基线 59 + H1.3 新增 9）。复算命令：

```
PYTHONPATH="src;tests" python -m pytest -q
python experiments/run_h1_3_prefix_constraint_inference.py
```

H1.2 原始结果、配置、搜索实现与 ACL 定义零改动。本轮完成后停止，等待独立验收。
