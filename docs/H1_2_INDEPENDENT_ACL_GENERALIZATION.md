# H1.2 — Independent ACL Generalization

- 基线 SHA：`2703472fe8c846c2ac91eb397babfe41d74483ef`（H1.1-R1 HEAD）
- 分支：`research/h1-2-independent-acl-generalization`
- 隔离 worktree：`D:\Research\pa-vfann-h1-2-independent-acl-generalization-workspace`
- 性质：固定检索环境下的可行性与稳健性研究；不设计新算法、不启动 H1.3/E2、不启动 H2/防御、不写论文创新点、不重跑 `run_all.py`、不追加 ACL 样本。

## 0. 研究问题

H1.1 已证明单个停止边界可确定性推断一个授权成员；H1.1-R1 已澄清 precision 与 coverage 的随机基线不是两份独立证据。H1.2 只估计这个泄露在独立授权集合下的**实际覆盖范围、查询有效率和成员去重效率**：

> 对固定 ANN 图和查询工作负载，停止边界成员泄露在独立生成的 ACL 中是否稳定？每个 ACL 能恢复多少不同授权成员？

本轮不重新验证已由停止规则推出的引理，只在每个 informative event 上执行必要的正确性守卫。

## 1. Phase 1：固定检索环境

沿用 EXP-01，只构造一次：

| 项 | 值 |
|---|---:|
| 向量 | 10,000 个，128 维，standard_normal |
| 查询 | 200 个 |
| 图 | exact-kNN，out-degree 16，反向边并集，连通分量 1 |
| E1 参数 | `m=20`，`K=10`，`B=1000` |
| 公开路径 | 200 条，`plan_fixed_trace(q, graph, 1000)`，构建一次后复用 |
| 配置 | `config/experiment.yaml`，`data.seed=2026` 未改 |

内容哈希（与 `results/h1_2_acl_generalization/manifest.json` 一致）：

| 对象 | SHA-256 |
|---|---|
| vectors | `6038583a516bae0c19efaaf5047fbe4f03668834a65ae15e0c842c7750fe6d59` |
| queries | `92423945f7320dca15db6b20959b593c6cbf0dc59dc471715d7936501daed0fc` |
| qdist | `7f5eb28daf65db8098fca5db7a33546fb130a259a97c9cf5efd0a9209177b9ef` |
| graph | `b2f6ecc6a53ab9131d553e3792ef319d92281ab4edb677468c0079dc7b0b3841` |
| 200 条公开路径 | `4ec122742f69de502028a9103a824ec7af18c60199fef9f5d9b71ec7aa220058` |
| config 文件 | `85436bed1d1cdcf6ec53e4829d8c58027302e93f7f621d0f016c8c69ebe37da8` |

独立复核脚本重算以上六项，全部 `OK`；manifest 另存 200 条路径各自的 `trace_sha16`。原始数据、配置、图构建与搜索实现均未被改写。

## 2. Phase 2：独立 ACL 样本

采用 `replace(base_dataset, master_seed=acl_seed)` 构造仅更换策略随机流的 Dataset 副本，并断言：

- `acl_dataset.vectors is base_dataset.vectors`
- `acl_dataset.query_vectors is base_dataset.query_vectors`

因此改变的是 ACL 随机流，不是向量、查询或图。ACL seeds 由固定命名空间、`data.seed=2026`、策略类型、选择率派生，可复现。

| 策略 | 授权率 | ACL 实例 |
|---|---:|---:|
| random / clustered | 1% | 各 30 |
| random / clustered | 5% | 各 30 |
| random / clustered | 10% | 各 30 |
| random / clustered | 30% | 各 30 |

总计 `2×4×30=240` 个独立 ACL 实例。每个 ACL 记录 `acl_seed`、`mask_sha256`、实际授权数量、实际选择率、策略类型、`sigma`、`n_centers` 与 `center_ids`。

生成门禁全部通过：

- 240 个 `acl_id` 唯一；每 cell 30 个 mask SHA-256 互不重复。
- 每 cell 30 个 ACL seed 互不重复；同 seed 重建 mask 一致。
- 每个 ACL 的实际授权数量等于目标 cardinality（100 / 500 / 1000 / 3000）。
- 每个 ACL 的 200 条查询严格划分为 informative、`τ=m`、`τ=B` 三类。

## 3. Phase 3：三角色分离与正确性守卫

脚本保持三个逻辑函数分离：

1. `simulate_e1_stop(path, mask, ...)`：可信执行侧模拟，使用 ACL 生成停止位置 `τ`。
2. `infer_last_node(path, τ, ...)`：攻击侧，直接复用 H1.1 函数；签名只含 `public_path`、`tau`、`min_visits`、`max_budget`，不接收 ACL。
3. `evaluate_inference(path, τ, mask, inferred, ...)`：独立评估，在攻击输出产生后才使用 ACL 打分。

对 `20<τ<1000` 的事件，攻击输出 `π_q[τ]`。所有 informative events 均满足 `a_{π[τ]}=1` 且前缀授权数 `=K-1`；`lemma_ok_events = informative_queries` 在 240 个 ACL 上全部成立。任意错误成员都会在运行期中止，不产生汇总结果。

## 4. Phase 4：指标定义

| 指标 | 定义 |
|---|---|
| informative rate | `I/Q`，`I` 为 informative queries 数，`Q=200` |
| ACL coverage | `U/M`，`M` 为授权集合大小 |
| unique yield | `U/min(M,I)`，实际恢复的不同成员数占当前 informative queries 可达上限的比例 |
| duplicate event rate | `(I-U)/I`；`I=0` 时记为 0 |
| stop-position 分位数 | informative queries 的 `τ` 的 5/25/50/75/95 分位数 |
| precision | `I` 个推断成员中正确的比例；只作正确性不变量，不作为新发现 |

硬不变量：`U ≤ min(M,I)`。本轮不再把 `U/N` 与 ACL coverage 的倍率作为第二条独立证据。

## 5. Phase 5：统计结果

以 ACL instance 为唯一抽样单位；每个 cell 30 个 ACL，5,000 次 ACL-level bootstrap，95% percentile interval。没有 query-level bootstrap，也没有把同一 ACL 下的 200 条查询当作 200 个独立样本。

表中格式为 `均值 [95% CI 下界, 上界]`：

| policy | sel% | informative rate | ACL coverage | unique yield | duplicate rate |
|---|---:|---:|---:|---:|---:|
| random | 1 | 0.5347 [0.4855, 0.5832] | 0.5383 [0.5087, 0.5660] | 0.5845 [0.5623, 0.6074] | 0.4786 |
| random | 5 | 1.0000 [1.0000, 1.0000] | 0.2680 [0.2627, 0.2735] | 0.6700 [0.6572, 0.6833] | 0.3300 |
| random | 10 | 1.0000 [1.0000, 1.0000] | 0.1547 [0.1527, 0.1566] | 0.7737 [0.7637, 0.7833] | 0.2263 |
| random | 30 | 0.9468 [0.9393, 0.9540] | 0.0554 [0.0546, 0.0561] | 0.8772 [0.8680, 0.8861] | 0.1228 |
| clustered | 1 | 0.5513 [0.4982, 0.5998] | 0.5433 [0.5110, 0.5733] | 0.5956 [0.5770, 0.6157] | 0.4873 |
| clustered | 5 | 1.0000 [1.0000, 1.0000] | 0.2720 [0.2679, 0.2760] | 0.6800 [0.6695, 0.6903] | 0.3200 |
| clustered | 10 | 1.0000 [1.0000, 1.0000] | 0.1544 [0.1525, 0.1562] | 0.7722 [0.7627, 0.7812] | 0.2278 |
| clustered | 30 | 0.9577 [0.9490, 0.9658] | 0.0561 [0.0554, 0.0568] | 0.8791 [0.8708, 0.8878] | 0.1209 |

30 个 ACL 之间的描述性范围：

| policy / sel% | coverage 范围 | informative rate 范围 | unique yield 范围 | `τ` 中位数范围 |
|---|---:|---:|---:|---:|
| random / 1% | 0.3200–0.6800 | 0.2800–0.8750 | 0.4839–0.7143 | 737.0–880.5 |
| random / 5% | 0.2380–0.3000 | 1.0000–1.0000 | 0.5950–0.7500 | 166.0–229.0 |
| random / 10% | 0.1400–0.1640 | 1.0000–1.0000 | 0.7000–0.8200 | 84.0–112.5 |
| random / 30% | 0.0513–0.0593 | 0.8900–0.9850 | 0.8308–0.9293 | 30.0–35.0 |
| clustered / 1% | 0.3000–0.6700 | 0.2050–0.7650 | 0.5000–0.7317 | 742.0–897.0 |
| clustered / 5% | 0.2400–0.3000 | 1.0000–1.0000 | 0.6000–0.7500 | 163.5–222.5 |
| clustered / 10% | 0.1410–0.1630 | 1.0000–1.0000 | 0.7050–0.8150 | 82.0–103.0 |
| clustered / 30% | 0.0507–0.0597 | 0.8900–0.9950 | 0.8306–0.9326 | 30.0–35.0 |

边界排除的每 ACL 平均数：1% 档 `τ=B` 为 random 93.07、clustered 89.73；30% 档 `τ=m` 为 random 10.63、clustered 8.47；5% 与 10% 档两类排除均为 0。

## 6. 停止标准对照

| 判据 | 结果 | 判断 |
|---|---|---|
| 每配置 30 个独立 ACL 生成成功 | 8 cells × 30 = 240，mask 互不重复 | 通过 |
| 实际授权数量与预期一致 | 240/240 与 cardinality 一致 | 通过 |
| informative events 满足确定性引理 | 全部满足，precision 不变量为 1 | 通过 |
| 覆盖率在 ACL 间形成稳定描述性分布 | 各 cell 均形成可复现范围与 CI；1% 档跨度较大但可判定 | 通过 |
| 重复、cardinality 错误或引理反例 | 0 | 未触发 |
| 追加样本追逐理想结果 | 未追加，固定 240 | 通过 |

## 7. 解释边界

- 结果显示：在固定合成图、固定 200 查询和当前随机 / clustered ACL 分布下，停止边界泄露的覆盖率、查询有效率与 unique yield 均形成稳定的描述性分布；H1.1 不是某个固定 ACL seed 的偶然结果。
- 授权率越高，`U/M` 越低，但 unique yield 越高（30% 档约 0.88），与“每次有效推断更少产生新成员”不同；这里观察到的是有效推断更集中地命中新成员，同时覆盖更大授权集合的比例受限。
- 1% 档的 informative rate 与 coverage 跨 ACL 波动明显大于 5%/10%/30% 档；结论只描述这组分布，不把它压成一个单点。
- 这些 bootstrap 区间只衡量**给定当前数据、查询集合、图结构下，对授权集合随机性的变化**。不是对其他数据集、ANN 图、真实企业 ACL 或真实查询分布的泛化保证。
- 本轮没有 E2 路径、跨查询累积模型、防御机制、ZKP/ORAM 或论文创新点主张；没有新的置信区间用于跨数据集推断。
- 不声称访问模式隐私、在线无损停止、PA-VFANN 普遍优于现有方法。

## 8. 交付与复算

新增且仅新增六个文件：

- `experiments/run_h1_2_acl_generalization.py`
- `tests/test_h1_2_acl_generalization.py`
- `docs/H1_2_INDEPENDENT_ACL_GENERALIZATION.md`
- `results/h1_2_acl_generalization/acl_metrics.csv`
- `results/h1_2_acl_generalization/summary.csv`
- `results/h1_2_acl_generalization/manifest.json`

完整测试 **59 passed**（H1.1-R1 基线 49 + H1.2 新增 10）。复算命令（使用含 numpy/pandas/scipy/yaml 的 Python 环境）：

```
PYTHONPATH="src;tests" python -m pytest -q
python experiments/run_h1_2_acl_generalization.py
```

脚本会在同一路径重写三份结果文件；ACL seeds、bootstrap seeds 与环境哈希固定，因此输出可复现。本轮完成后停止，等待独立验收；未进入 H1.3 或 H2。
