# EXP-10B.1 — FiQA + hnswlib 外部有效性实验报告

生成时工作区 HEAD：`21eee17e3fed653557eeb8eb99b800331eb4fa8c`
分支：`exp10-fiqa-hnswlib-external-validity`
实验编号：`EXP-10B.1`
裁决依据：`results/exp10_fiqa_summary.json` 与原始轨迹可复算结果。

---

## 1. 结论摘要

本轮在 BEIR 官方历史 revision 的原始 FiQA 组件上，使用固定模型 embedding 与 hnswlib v0.9.0 标准 `searchKnn` 路径，检验 EXP-09 / EXP-09.1 的核心发现是否可复现。

- 数据门：`PASS_COMPONENT_ARTIFACTS`。三个 BEIR 官方组件文件通过固定 revision、大小和 SHA-256 校验；**原 UKP ZIP 的 MD5 仍为 `NOT_VERIFIED`**，本轮不宣称 ZIP MD5 通过。
- C++ 小规模验收：`PASS`，512/384/20 合成设定下事件数与独立 DISTFUNC 计数一致，sink-on/off top-k bit-exact，trace hash 可复现。
- 准入门：三个 efSearch 的 mean unfiltered exact Recall@10 = 64:0.9946, 128:0.9978, 256:0.9995。
- 按修正后的规则（**三个都低于 0.90 才停止**），正式 Oracle 主结论：`CONTINUE`。低质量配置：无。
- Oracle Prefix 是事后上界，不是在线停止规则；first-touch 轨迹是 **HNSW query distance-evaluation trace**，不是硬件 cache / 预取 / 物理内存访问轨迹。

---

## 2. 数据来源与完整性

| 组件 | 仓库 | revision | 大小 | SHA-256 |
| --- | --- | --- | ---: | --- |
| corpus | BeIR/fiqa | `a90551af496e20ce7887c02f07f7ea5c86908fb9` | 17,662,437 | `6d2c7e27aeb8c646791178e3e5591a373813642f38d9c992c0a4f6cbf4092f72` |
| queries | BeIR/fiqa | `01557ca93ac1c5f4ba52cd6955bc44515846f3fa` | 193,723 | `a683bbedd2fd3b1fcb1a44fbd706daf9aff27291cd99e7a086b3cf7624785acb` |
| qrels | BeIR/fiqa-qrels | `93a4617fe9d8263f8055a67a2269eb40b8659c0a` | 25,256 | `6adc2a640dcdd22bb8b3858f89107adef2a7c3db20a63550dfa7a0f71e379e44` |

- corpus：57,638 条；全量 queries：6,648 条；test queries：648 条；qrels pairs：1,706。
- qrels query IDs 从全量 queries 中选取 648 条 test queries；没有把 6,648 当成 test query 数量。
- ID 唯一性、qrels 引用完整性、重复对、test/qrels 集合一致性均通过 manifest 中记录的检查。
- 数据描述：`BEIR first-party component artifacts, revision-pinned`。
- Dataset card license：corpus/queries/qrels 均为 `NOT_DECLARED_IN_DATASET_CARD`；据实记录，不推断。

---

## 3. Embedding 与 HNSW 配置

- 模型：`sentence-transformers/all-MiniLM-L6-v2` @ `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`，license `apache-2.0`。
- 设备/线程：CPU，embedding 固定 8 线程；HNSW 构建和查询固定单线程。
- dtype/dim/normalize：float32，384，`normalize_embeddings=true`。
- 文本约定：corpus 为 `title + newline + text`，query 为 `query text only`。
- hnswlib：hnswlib v0.9.0 + EXP-10A patch；space 为归一化向量 IP（cosine 等价排序）。
- HNSW：M=32，efConstruction=200，efSearch=[64, 128, 256]，k=10，seed=2026。
- external label = BEIR corpus 行索引；文档顺序按 corpus.jsonl 加载顺序。

## 4. 授权 mask 与指标口径

- 两类合成授权策略：random、embedding-clustered；选择率 1%/10%/30%；seeds 2026/2027/2028；共 18 个配置。这些 mask 不是真实企业 ACL。
- 精确 GT 使用归一化 embedding 的 float32 点积，排序为 score 降序、corpus 行号稳定升序；记录 rank-10 边界 score 和 exact tie count。
- ACL mask 不进入 C++ HNSW 搜索路径。每个 `(query, efSearch)` 的轨迹只采集一次，18 个 mask 共享同一条 policy-oblivious first-touch 轨迹。
- prefix 预算：`ceil(0.6B)`, `ceil(0.8B)`, `ceil(0.9B)`, `B`，其中 B 为该 query/ef 的 unique first-touch 长度。
- prefix candidate Recall@10：取 prefix 内已授权候选，用精确分数重排后取 top-10，与 filtered exact GT top-10 求交集，分母固定为 10。
- Oracle Prefix：`t*(q,p,δ)=min{t≥ceil(0.6B): R(t)≥R(B)-δ}`，δ=0.05/0.10；若窗口内未达到记 `NOT_REACHED` 并取 B。该量是事后上界。
- qrels filtered nDCG@10：仅在授权 qrels 相关文档上计算，作为 secondary metric。
- bootstrap：按 query index 配对重采样 2000 次，seed=20261125，报告 95% percentile CI。

---

## 5. 主要结果

### 5.1 Unfiltered Recall@10 准入门

| efSearch | mean unfiltered exact Recall@10 | mean events/query | mean unique/query | 判定 |
| ---: | ---: | ---: | ---: | --- |
| 64 | 0.9946 | 1530.8 | 1505.5 | QUALIFIED |
| 128 | 0.9978 | 2583.3 | 2552.7 | QUALIFIED |
| 256 | 0.9995 | 4362.8 | 4324.9 | QUALIFIED |

任务包原 §8 与 §14.8 的文字矛盾已按新任务包修正：**仅当三个 efSearch 全部低于 0.90 时停止正式 Oracle 主结论**。本轮 `oracle_main_conclusion=CONTINUE`。

### 5.2 Prefix Recall@10

| efSearch | 60% B | 80% B | 90% B | B |
| ---: | ---: | ---: | ---: | ---: |
| 64 | 0.6421 | 0.6994 | 0.7205 | 0.7384 |
| 128 | 0.7405 | 0.7878 | 0.8064 | 0.8217 |
| 256 | 0.8239 | 0.8611 | 0.8751 | 0.8866 |

### 5.3 Oracle Prefix 空间

| efSearch | mean t*/B (δ=0.05) | mean t*/B (δ=0.10) |
| ---: | ---: | ---: |
| 64 | 0.7137 | 0.6394 |
| 128 | 0.6954 | 0.6340 |
| 256 | 0.6745 | 0.6248 |

### 5.4 1% 选择率与 mask 类型

| efSearch | 1% masks full-trace Recall@10 |
| ---: | ---: |
| 64 | 0.4266 |
| 128 | 0.5720 |
| 256 | 0.7078 |

| mask type | full-trace Recall@10（跨 ef/seed/selectivity） |
| --- | ---: |
| random | 0.8992 |
| clustered | 0.7319 |

更细的按选择率、seed、mask key 与 95% CI 见 `results/exp10_fiqa_bootstrap.csv`；逐 query 原始表见 `results/exp10_fiqa_prefix_recall.csv` 与 `results/exp10_fiqa_oracle_prefix.csv`。

### 5.5 图表

生成 7 类图表：`results/figures/fig01_unfiltered_recall_gate.png` 至 `fig07_ndcg_curve.png`，覆盖准入门、prefix 曲线、1% 困难档、random vs clustered、Oracle 分布、trace 成本和 nDCG 曲线。

---

## 6. 对研究问题的回答

1. **核心发现是否在真实文本 HNSW 上复现？——部分支持。** unfiltered exact Recall@10 为 ef=64:0.9946, ef=128:0.9978, ef=256:0.9995，准入门全部通过；但 filtered prefix recall 随预算下降而下降，例如 ef=128 从 B 档 0.8217 降到 0.6B 档 0.7405。这支持“截断有可测成本、困难场景存在”的方向性发现；但 full-trace filtered recall 仍显著低于 unfiltered，**不支持**把 prefix 缩减当作在线无损 stopping rule。
2. **是否存在稳健前缀空间？——事后支持，在线不支持。** mean t*/B 在 δ=0.05 时为 ef=64 0.7137、ef=128 0.6954、ef=256 0.6745；δ=0.10 时为 0.6394、0.6340、0.6248。说明存在可观的事后前缀空间，但 Oracle Prefix 是事后上界，不是可部署在线策略；`NOT_REACHED` 配置在 oracle CSV 中逐项标记。
3. **1% 是否困难？——支持。** 1% masks 的 full-trace Recall@10 为 ef=64 0.4266、ef=128 0.5720、ef=256 0.7078，明显低于聚合水平；这与 EXP-09.1 所发现的 1% 困难档一致。
4. **random 与 embedding-clustered 是否不同？——支持，且 clustered 更难。** random 的 full-trace Recall@10 为 0.8992，clustered 为 0.7319。差异只能解释为合成授权策略分布不同，不能解释为真实企业 ACL 或图拓扑差异。
5. **与合成图实验的差异？** 本轮语料与 HNSW 来自真实文本 embedding，但授权 mask 仍为合成；轨迹口径为 HNSW 有序距离计算事件与 unique first-touch 视图，不是硬件 cache、预取、物理内存访问或真实侧信道。
6. **是否继续 PA-VFANN？** 本轮提供外部有效性证据，但不自动接入 Agent/RAG，不启动 EXP-11，也不把结果包装成安全贡献。是否继续投入应由用户结合 Oracle 仅为事后上界、1% 档仍困难这两点独立复核后决定。

---

## 7. 限制与边界

- 原始 UKP ZIP 未取得，MD5 未验证；只验证 BEIR first-party 历史 revision 的三个原始组件。
- 授权 mask 是合成的；不代表真实企业 ACL，也不代表图拓扑。
- trace 是 HNSW 查询路径上的 distance-evaluation 事件与 unique first-touch 视图，不是硬件 cache、预取、物理内存访问或真实侧信道。
- Oracle Prefix 是事后上界，不能当作可部署在线停止规则；未声称策略隐藏、形式化安全、exactly-once 或普遍性能优势。
- 模型 revision、HNSW 参数、mask 规则、prefix 规则和 bootstrap 参数均固定；未在看到结果后改网格。

---

## 8. 可复算产物

- `data/exp10_fiqa_manifest.json`：组件来源、SHA、counts、ID 集合哈希。
- `data/exp10_fiqa_embeddings/embedding_manifest.json`、`gt_manifest.json`：embedding 与 GT/mask 固定。
- `results/raw/exp10_fiqa_trace_manifest.json`：压缩轨迹 SHA-256。
- `results/exp10_fiqa_*.csv` / `.json`：分析原始表、bootstrap 和汇总。
- `results/figures/*.png`：7 类图表。
- `experiments/exp10_fiqa_hnswlib/*.py|cpp|sh`：完整执行脚本。

报告生成时的 HEAD 是上述脚本和结果提交前的父提交；最终 push 后以版本控制记录为准。
