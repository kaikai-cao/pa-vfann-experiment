# PA-VFANN-11 / EXP-02A — 协议可观测性与通信成本审计

本目录是对 EXP-02（分支 `exp02-no-distance-oracle` @ `29ec958`）的**只读审计**。

它不重跑 ANN 搜索、不修改 E1/E2/E3 算法、不改写 EXP-02 的任何 CSV、图或报告。所有成本数字都由冻结的
`exp02/results/raw/experiment_results.csv` 中的候选数推导；基线文件的 SHA256 清单在
`audit/exp02_baseline_manifest.json`，测试会逐个校验。

## 解决的两个模型缺口

1. **E3 候选传输成本不完整**：EXP-02 的 8 字节/候选（4 B ID + 4 B 平方距离）只是下界，
   不含 ACL、TTL 和其他谓词元数据，客户端无法仅凭该记录完成授权判断。
2. **输出 ID 泄露被错误归因为服务端**：E3 默认由客户端本地过滤，服务端看不到过滤后的 Top-K ID。
   旧指标 `output_id_leakage` 在此改名为 `cross_policy_output_distinguishability`（跨策略输出可区分性），
   并新增 `server_observable_leakage`，只统计服务端确实可见的信道。

## 三种通信模型

| 模型 | 每条候选记录 | 客户端能否执行过滤 | 消息数 |
|---|---|---|---:|
| A | 4 B ID + 4 B 距离 | 否（仅下界） | 1 |
| B | A + ACL + TTL + 其他谓词元数据 | 是 | 1 |
| C | A + 属性引用；属性经额外一轮获取 | 是 | 3（不含客户端反馈） |

属性长度**没有真实测量值**，全部为明确标注的扫描参数（见 `config/audit.yaml`）。
基线举例值 `ACL=16 B, TTL=8 B, 其他=8 B`（合计 32 B/候选）只是一个声明假设，不作为实测常数。

## 三类观察者

- `O_server`：查询、搜索轨迹、候选 ID/距离、停止位置、消息大小与次数；模型 B 下还看到属性值，
  但**任何模型下都看不到授权匹配位**；仅当 E1/E2 或 E3 显式反馈时看到 Top-K ID。
- `O_client`：查询、候选 ID/距离、授权属性、Top-K ID、消息元数据；看不到服务端内部搜索轨迹和停止位置。
- `O_network`：默认 TLS 假设下只看得到消息大小与次数；`network_tls: false` 时可见明文载荷（对照场景）。

## 运行

```bash
cd D:/Research/pa-vfann-experiment/exp02a
PYTHONPATH="src" python experiments/run_transfer_audit.py
PYTHONPATH="src" python experiments/run_observer_audit.py
PYTHONPATH="src" python experiments/make_figures.py
python -m pytest
```

依赖：Python 3.11+，numpy / pandas / matplotlib / pyyaml / pytest（与 EXP-01/02 相同，无新增依赖）。

## 输出

`results/tables/`：
- `candidate_field_requirements.csv` — 字段归属与传输状态
- `transfer_cost_by_model.csv` — A/B/C 每查询平均与 P95 字节
- `transfer_cost_by_attribute_size.csv` — 属性长度参数扫描
- `transfer_cost_at_recall_target.csv` — 达标成本，两种查询人口分开列
- `recall_target_query_sets_detail.csv` / `recall_target_query_sets.csv` — 达标口径核验
- `observer_visibility_matrix.csv` / `observer_channel_counts.csv` / `server_observable_channels.csv`
- `observer_leakage_summary.csv` — 重解释后的泄露指标

`results/figures/`：
- `transfer_cost_vs_attribute_size.png`
- `observer_visibility_comparison.png`

## 边界

不做：MPC、ORAM、SNARK、Halo2、真实 HNSW、候选压缩实现、修改 EXP-02 原始结果、合并 main。
本轮**不提出新的密码学构造**。结论与未解决问题见 `REPORT.md`。
