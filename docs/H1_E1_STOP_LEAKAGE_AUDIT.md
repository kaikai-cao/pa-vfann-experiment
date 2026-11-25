# H1.1 — E1 Stop-Boundary Leakage Audit

- 基线：`main` @ `0145ccad4444633789dfd5ae42e4732bb0f76e46`
- 分支：`research/h1-e1-stop-boundary-leakage`（从 main SHA 建隔离 worktree；原 `exp08` 分支与 untracked `exp02/` 未触碰）
- 性质：对冻结 EXP-01 结果的只读回溯审计；不重跑 `run_all.py`，不重建或改写原始产物，不运行 EXP-10，不采集 FiQA/HNSW 新轨迹，不训练分类器，不追加 E2 攻击，不提出防御效果。

## 0. 被验证的引理

公开遍历顺序 `π_q=(v_1,…,v_B)`、最小访问数 `m=20`、授权结果数 `K=10`、最大预算 `B=1000`。E1 停止位置：

`τ = min{ t≥m : Σ_{i=1}^{t} a_{v_i} ≥ K }`

若 `m<τ<B`，则 `a_{v_τ}=1` 且 `Σ_{i=1}^{τ-1} a_{v_i}=K-1`：观察者仅凭停止位置即可确定最后一个被访问节点属于隐藏授权集合。两个必须排除的边界：`τ=m`（最小访问数下限，最后节点不一定授权）、`τ=B`（预算耗尽，不一定是达到阈值）。

## 1. Phase 0 / Phase 1：基线与路径重建

- 本地 main ref 与远端 main 均为 `0145ccad`；隔离 worktree HEAD 等于该 SHA，工作区 clean。
- 用冻结 `config/experiment.yaml` 的 `prepare()` 重建 dataset（n=10000、d=128、seed=2026、200 查询、exact-kNN 度 16、连通分量 1），对每条查询用 `plan_fixed_trace(q, graph, 1000)` 重建公开路径。
- 读取原始 CSV 中 `experiment=selectivity`、`algorithm=E1_POSTFILTER`、`budget=1000`：8 组策略（random/clustered × 1%/5%/10%/30%），每组 200 条，共 1600 条。
- **关键门槛**：对每条记录，取重建公开路径的前 `τ=stop_position` 个节点，按 `exp_common.make_row` 的同款公式计算 `sha256(",".join(path[:τ]))[:16]`，与原始 `trace_sha16` 比对。**1600/1600 全部匹配，0 不匹配**。这证明攻击所需的"公开路径 + 停止位置"可由公开信息独立重建，无需访问 ACL 或结果 ID。
- 另做 ACL 重建校验：用 `policy_for` 从固定种子重建每组授权 mask，其 `mask.sum()` 与 CSV `actual_authorized_count` 一致；再用该 mask 重算 E1 停止位置，1600/1600 与 CSV `stop_position` 一致。若不一致则审计中止。

## 2. Phase 2/3：攻击与度量

**架构边界（不可跳过）**：攻击函数 `infer_last_node(public_path, tau, min_visits, max_budget)` 的签名经测试断言，只接收公开路径与停止位置及公开参数，物理上无法接收 ACL、policy、结果 ID 或任何授权位。真实 ACL 只在独立评估函数 `evaluate_inference` 中使用，且仅用于给攻击输出打分（`a_{π[τ]}` 与前缀授权计数），不参与攻击生成。

对 `20<τ<1000` 的记录，攻击输出 `π_q[τ]`，即重建路径第 τ 个节点。逐组结果：

| policy | sel% | total | τ=20 排除 | τ=1000 排除 | informative | positive events | unique inferred | precision | ACL coverage | repeat nodes | random baseline | lemma_ok |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| clustered | 1 | 200 | 0 | 70 | 130 | 130 | 53 | 1.0 | 0.5300 | 32 | 0.0100 | 130 |
| clustered | 5 | 200 | 0 | 0 | 200 | 200 | 126 | 1.0 | 0.2520 | 46 | 0.0500 | 200 |
| clustered | 10 | 200 | 0 | 0 | 200 | 200 | 162 | 1.0 | 0.1620 | 34 | 0.1000 | 200 |
| clustered | 30 | 200 | 7 | 0 | 193 | 193 | 171 | 1.0 | 0.0570 | 19 | 0.3000 | 193 |
| random | 1 | 200 | 0 | 99 | 101 | 101 | 56 | 1.0 | 0.5600 | 26 | 0.0100 | 101 |
| random | 5 | 200 | 0 | 0 | 200 | 200 | 141 | 1.0 | 0.2820 | 39 | 0.0500 | 200 |
| random | 10 | 200 | 0 | 0 | 200 | 200 | 160 | 1.0 | 0.1600 | 33 | 0.1000 | 200 |
| random | 30 | 200 | 13 | 0 | 187 | 187 | 158 | 1.0 | 0.0527 | 22 | 0.3000 | 187 |

指标定义：
- informative queries：满足 `20<τ<1000` 的查询数。
- positive events：推断出的授权节点事件数（每条 informative 查询一次）。
- unique inferred nodes：positive events 去重后的节点数。
- precision：推断节点中实际授权的比例；`E[precision_random]=|A|/N`，即 random baseline 列。
- ACL coverage：去重推断节点覆盖全部授权节点的比例 `|Â_positive ∩ A|/|A|`。
- repeat nodes：被多次查询重复推断的节点数；repeat events 为重复次数总和。
- lemma_ok：`a_{π[τ]}=1` 且前缀授权数 `=K-1` 同时成立的事件数。

`τ=20` 排除总数 20 条（clustered 30% 7 条、random 30% 13 条），`τ=1000` 排除总数 169 条（集中在 1% 档：clustered 70、random 99），均**不作为确定性正标签**。

## 3. 决策标准对照

| 任务包判据 | 实测 | 判断 |
|---|---|---|
| Trace hash 重建失败 | 1600/1600 匹配 | 通过 |
| Precision 不为 1 | 全部为 1（0 反例）；脚本对反例会中止 | 通过 |
| Precision=1 但 coverage 极低 | 1% 档 0.53/0.56，10% 0.16，30% 0.057 | 低选择率有明显规模；高选择率覆盖低 |
| coverage 明显且远高于随机基线 | 1% 档 0.53/0.56 vs 0.01；5% 0.25/0.28 vs 0.05 | 成立，值得进入独立 ACL 实例的泛化研究 |
| 不同选择率表现明显不同 | 1% 档 τ=1000 大量排除、coverage 高；30% 档几乎不排除但 coverage 最低 | 成立 |

结论：**该确定性控制流泄露在当前 EXP-01 配置上被实测验证**（precision=1、引理全成立），且在低选择率下具有可观的授权成员覆盖规模、显著高于随机猜测。按任务包标准，这支持"进入独立 ACL 实例的攻击泛化研究"这一下一步判断；本轮不自动开展该研究。

## 4. 不能支持的陈述与统计限制

- **单授权集合实例**：每组策略只有一个授权集合实例（由固定种子生成），所有 coverage、precision、repeat 都是描述性结果，**不能据此构造跨授权集合的统计置信区间**，也不构成对随机 ACL 总体的推断。
- ACL mask 为合成策略（random / clustered），不是真实企业 ACL。
- 攻击假设索引服务看不到 ACL 位图、也看不到最终结果 ID，只能观察内部节点访问与停止行为；若服务直接持有 ACL 或结果 ID 已暴露，则不能称其为独立的隐藏授权成员攻击。
- 这是一个可证明的控制流泄露性质，**不等于**完整论文贡献；是否具有新颖性仍需独立核对相关工作（ACORN/Tag-Filtered ANNS、PP-RFANNS、SAGE、ObliSC、企业 RAG ACL 检索等），本轮不下结论。
- 不声称已解决 Agent/RAG 授权检索、不声称访问模式隐私、不声称在线无损停止、不声称 PA-VFANN 普遍优于现有方法。
- 观测口径是**合成图上的公开遍历计划与停止位置**，不是 HNSW/Faiss 硬件 cache trace、物理内存访问轨迹或侧信道观测。

## 5. 交付与复算

新增且仅新增三个文件：

- `experiments/analyze_e1_stop_leakage.py`：Phase 1 hash 门槛 + Phase 2/3 攻击与度量，纯打印、不写文件。
- `tests/test_e1_stop_leakage.py`：8 项测试，含 τ=m / 窗口内 / τ=B 三类边界、引理构造、攻击签名无 ACL、hash 公式一致性。
- `docs/H1_E1_STOP_LEAKAGE_AUDIT.md`：本报告。

原始 CSV、配置文件与原始实验代码 SHA-256 不变；未新增数据集；未启动 EXP-11。38 项测试全部通过（30 原有 + 8 新增）。复算命令（使用含 numpy/pandas/scipy/yaml 的 Python 环境）：

```
PYTHONPATH="src;tests" python -m pytest -q
python experiments/analyze_e1_stop_leakage.py
```
