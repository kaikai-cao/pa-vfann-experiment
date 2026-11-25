# EXP-10B.2 统计与指标修正报告

- 基线提交：`69c4bd05e48f8734bc46e290ecb726320c572b45`
- 分支：`exp10-fiqa-statistical-correction`
- 生成时 HEAD：`69c4bd05e48f8734bc46e290ecb726320c572b45`
- 本轮只修正计算与指标，不重跑 embedding、HNSW、查询轨迹，不扩展研究问题。

> **EXP-10B.2-R1 语义勘误（文档级，冻结轮次）**：本文件已在分支 `exp10-fiqa-semantic-erratum` 上，对 `clustered_3center_farthest_first` 的构造语义与结论措辞做有限勘误。全部数值、CSV、mask、manifest、trace、Ground Truth、统计脚本与原始输入 SHA-256 均未改动；机器可读名称 `clustered_3center_farthest_first` 保持不变。勘误的事实依据与范围见 `docs/EXP10B2_SEMANTIC_ERRATUM.md`。

## A. 原始数据与 trace 的可靠性

- 数据门仍是 `PASS_COMPONENT_ARTIFACTS`；原 UKP ZIP MD5 仍为 `NOT_VERIFIED`，历史报告未覆盖。
- 原始 trace 事件数等于独立 DISTFUNC 计数：`True`；C++ smoke verdict：`PASS`。
- 原始输入 SHA-256 复算条目数：`39`；旧 mask 与压缩 trace 哈希均未变化：`True`。
- 旧 mask prefix Recall 重算与原 CSV 的最大绝对差：`0.00e+00`。
- 观测口径仍是 **HNSW query distance-evaluation trace**，不是硬件 cache trace、物理内存访问轨迹或侧信道观测。

## B. 修正前的错误结果

1. Oracle Prefix 把 NOT_REACHED 填成 `t_star=B`、`ratio=1.0`，把“未找到”误写成“在 B 恰好达到”。
2. Bootstrap 把展开后的 query-mask 行当成独立样本，破坏 query-level cluster 结构。
3. nDCG@10 先按 qrels 相关文档排序再与候选求交，删除了不相关候选，使相关文档名次虚高。
4. 旧 128 簇变体被简称为 `clustered`；本轮改名为 `clustered_128_random_direction`，不改写原文件。

## C. 修正后的有效结果

### C.1 Oracle 可达性（reached-only，NOT_REACHED 不填 B/1.0）

| ef | mask | p | delta | reached/total | rate | mean t*/B | median | p90 | 95% CI | NOT_REACHED mean Recall@B |
|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---:|
| 64 | clustered_128_random_direction | 1% | 0.05 | 1944/1944 | 1.000 | 0.7044 | 0.6006 | 0.9383 | [0.6984, 0.7107] | NA |
| 64 | clustered_128_random_direction | 1% | 0.10 | 1944/1944 | 1.000 | 0.6348 | 0.6004 | 0.7614 | [0.6314, 0.6386] | NA |
| 64 | clustered_128_random_direction | 10% | 0.05 | 1944/1944 | 1.000 | 0.7356 | 0.7024 | 0.9486 | [0.7294, 0.7423] | NA |
| 64 | clustered_128_random_direction | 10% | 0.10 | 1944/1944 | 1.000 | 0.6524 | 0.6004 | 0.8106 | [0.6482, 0.6570] | NA |
| 64 | clustered_128_random_direction | 30% | 0.05 | 1944/1944 | 1.000 | 0.6792 | 0.6005 | 0.8926 | [0.6736, 0.6848] | NA |
| 64 | clustered_128_random_direction | 30% | 0.10 | 1944/1944 | 1.000 | 0.6265 | 0.6004 | 0.7168 | [0.6235, 0.6299] | NA |
| 64 | clustered_3center_farthest_first | 1% | 0.05 | 1944/1944 | 1.000 | 0.7338 | 0.6724 | 0.9553 | [0.7273, 0.7405] | NA |
| 64 | clustered_3center_farthest_first | 1% | 0.10 | 1944/1944 | 1.000 | 0.6474 | 0.6004 | 0.8075 | [0.6433, 0.6515] | NA |
| 64 | clustered_3center_farthest_first | 10% | 0.05 | 1944/1944 | 1.000 | 0.7325 | 0.6896 | 0.9461 | [0.7266, 0.7382] | NA |
| 64 | clustered_3center_farthest_first | 10% | 0.10 | 1944/1944 | 1.000 | 0.6497 | 0.6005 | 0.7986 | [0.6458, 0.6535] | NA |
| 64 | clustered_3center_farthest_first | 30% | 0.05 | 1944/1944 | 1.000 | 0.6688 | 0.6005 | 0.8662 | [0.6636, 0.6740] | NA |
| 64 | clustered_3center_farthest_first | 30% | 0.10 | 1944/1944 | 1.000 | 0.6180 | 0.6003 | 0.6536 | [0.6155, 0.6204] | NA |
| 64 | random | 1% | 0.05 | 1944/1944 | 1.000 | 0.8005 | 0.8233 | 0.9684 | [0.7942, 0.8069] | NA |
| 64 | random | 1% | 0.10 | 1944/1944 | 1.000 | 0.6829 | 0.6149 | 0.8556 | [0.6780, 0.6877] | NA |
| 64 | random | 10% | 0.05 | 1944/1944 | 1.000 | 0.7105 | 0.6590 | 0.9146 | [0.7040, 0.7166] | NA |
| 64 | random | 10% | 0.10 | 1944/1944 | 1.000 | 0.6298 | 0.6004 | 0.7294 | [0.6263, 0.6332] | NA |
| 64 | random | 30% | 0.05 | 1944/1944 | 1.000 | 0.6517 | 0.6004 | 0.8196 | [0.6463, 0.6573] | NA |
| 64 | random | 30% | 0.10 | 1944/1944 | 1.000 | 0.6100 | 0.6003 | 0.6007 | [0.6078, 0.6124] | NA |
| 128 | clustered_128_random_direction | 1% | 0.05 | 1944/1944 | 1.000 | 0.7327 | 0.6786 | 0.9519 | [0.7264, 0.7392] | NA |
| 128 | clustered_128_random_direction | 1% | 0.10 | 1944/1944 | 1.000 | 0.6493 | 0.6002 | 0.8212 | [0.6454, 0.6534] | NA |
| 128 | clustered_128_random_direction | 10% | 0.05 | 1944/1944 | 1.000 | 0.7187 | 0.6312 | 0.9435 | [0.7120, 0.7253] | NA |
| 128 | clustered_128_random_direction | 10% | 0.10 | 1944/1944 | 1.000 | 0.6443 | 0.6002 | 0.7883 | [0.6403, 0.6484] | NA |
| 128 | clustered_128_random_direction | 30% | 0.05 | 1944/1944 | 1.000 | 0.6488 | 0.6002 | 0.8240 | [0.6443, 0.6534] | NA |
| 128 | clustered_128_random_direction | 30% | 0.10 | 1944/1944 | 1.000 | 0.6146 | 0.6002 | 0.6181 | [0.6123, 0.6170] | NA |
| 128 | clustered_3center_farthest_first | 1% | 0.05 | 1944/1944 | 1.000 | 0.7419 | 0.7122 | 0.9567 | [0.7359, 0.7482] | NA |
| 128 | clustered_3center_farthest_first | 1% | 0.10 | 1944/1944 | 1.000 | 0.6529 | 0.6002 | 0.8193 | [0.6489, 0.6572] | NA |
| 128 | clustered_3center_farthest_first | 10% | 0.05 | 1944/1944 | 1.000 | 0.6943 | 0.6003 | 0.9139 | [0.6889, 0.6997] | NA |
| 128 | clustered_3center_farthest_first | 10% | 0.10 | 1944/1944 | 1.000 | 0.6332 | 0.6002 | 0.7450 | [0.6297, 0.6365] | NA |
| 128 | clustered_3center_farthest_first | 30% | 0.05 | 1944/1944 | 1.000 | 0.6341 | 0.6002 | 0.7488 | [0.6301, 0.6381] | NA |
| 128 | clustered_3center_farthest_first | 30% | 0.10 | 1944/1944 | 1.000 | 0.6074 | 0.6002 | 0.6004 | [0.6058, 0.6092] | NA |
| 128 | random | 1% | 0.05 | 1944/1944 | 1.000 | 0.8024 | 0.8216 | 0.9640 | [0.7966, 0.8085] | NA |
| 128 | random | 1% | 0.10 | 1944/1944 | 1.000 | 0.6869 | 0.6332 | 0.8491 | [0.6820, 0.6917] | NA |
| 128 | random | 10% | 0.05 | 1944/1944 | 1.000 | 0.6511 | 0.6002 | 0.8162 | [0.6465, 0.6559] | NA |
| 128 | random | 10% | 0.10 | 1944/1944 | 1.000 | 0.6072 | 0.6002 | 0.6004 | [0.6057, 0.6088] | NA |
| 128 | random | 30% | 0.05 | 1944/1944 | 1.000 | 0.6186 | 0.6002 | 0.6393 | [0.6155, 0.6221] | NA |
| 128 | random | 30% | 0.10 | 1944/1944 | 1.000 | 0.6015 | 0.6002 | 0.6003 | [0.6009, 0.6023] | NA |
| 256 | clustered_128_random_direction | 1% | 0.05 | 1944/1944 | 1.000 | 0.7486 | 0.7285 | 0.9613 | [0.7424, 0.7549] | NA |
| 256 | clustered_128_random_direction | 1% | 0.10 | 1944/1944 | 1.000 | 0.6575 | 0.6002 | 0.8286 | [0.6534, 0.6617] | NA |
| 256 | clustered_128_random_direction | 10% | 0.05 | 1944/1944 | 1.000 | 0.6847 | 0.6002 | 0.9069 | [0.6788, 0.6910] | NA |
| 256 | clustered_128_random_direction | 10% | 0.10 | 1944/1944 | 1.000 | 0.6297 | 0.6001 | 0.7277 | [0.6262, 0.6333] | NA |
| 256 | clustered_128_random_direction | 30% | 0.05 | 1944/1944 | 1.000 | 0.6258 | 0.6001 | 0.6982 | [0.6225, 0.6292] | NA |
| 256 | clustered_128_random_direction | 30% | 0.10 | 1944/1944 | 1.000 | 0.6060 | 0.6001 | 0.6002 | [0.6046, 0.6076] | NA |
| 256 | clustered_3center_farthest_first | 1% | 0.05 | 1944/1944 | 1.000 | 0.7541 | 0.7415 | 0.9570 | [0.7479, 0.7604] | NA |
| 256 | clustered_3center_farthest_first | 1% | 0.10 | 1944/1944 | 1.000 | 0.6618 | 0.6002 | 0.8316 | [0.6574, 0.6660] | NA |
| 256 | clustered_3center_farthest_first | 10% | 0.05 | 1944/1944 | 1.000 | 0.6620 | 0.6001 | 0.8703 | [0.6576, 0.6668] | NA |
| 256 | clustered_3center_farthest_first | 10% | 0.10 | 1944/1944 | 1.000 | 0.6187 | 0.6001 | 0.6532 | [0.6162, 0.6213] | NA |
| 256 | clustered_3center_farthest_first | 30% | 0.05 | 1944/1944 | 1.000 | 0.6124 | 0.6001 | 0.6002 | [0.6101, 0.6152] | NA |
| 256 | clustered_3center_farthest_first | 30% | 0.10 | 1944/1944 | 1.000 | 0.6028 | 0.6001 | 0.6002 | [0.6018, 0.6040] | NA |
| 256 | random | 1% | 0.05 | 1944/1944 | 1.000 | 0.7682 | 0.7701 | 0.9557 | [0.7620, 0.7740] | NA |
| 256 | random | 1% | 0.10 | 1944/1944 | 1.000 | 0.6544 | 0.6002 | 0.8018 | [0.6506, 0.6583] | NA |
| 256 | random | 10% | 0.05 | 1944/1944 | 1.000 | 0.6150 | 0.6001 | 0.6155 | [0.6122, 0.6179] | NA |
| 256 | random | 10% | 0.10 | 1944/1944 | 1.000 | 0.6009 | 0.6001 | 0.6002 | [0.6004, 0.6014] | NA |
| 256 | random | 30% | 0.05 | 1944/1944 | 1.000 | 0.6048 | 0.6001 | 0.6002 | [0.6031, 0.6066] | NA |
| 256 | random | 30% | 0.10 | 1944/1944 | 1.000 | 0.6005 | 0.6001 | 0.6002 | [0.6001, 0.6009] | NA |

- 本轮所有 Oracle 样本均 reached：104976/104976，NOT_REACHED 数为 0。因此修正的空白编码规则在当前 FiQA 数据上没有改变数值，但纠正了语义：未找到时必须留空，不能用 B 或 1.0 填充。困难性体现在 prefix Recall/full-trace Recall 低，而不是 Oracle 不可达。
Oracle 是对固定 trace 的事后分析，不是在线 stopping rule，也不是其他搜索算法的理论下界。

### C.2 query-level cluster bootstrap

| mask | p | mean prefix Recall@10 (B) | 95% CI |
|---|---:|---:|---|
| clustered_128_random_direction | 1% | 0.4000 | [0.3818, 0.4188] |
| clustered_128_random_direction | 10% | 0.8424 | [0.8321, 0.8524] |
| clustered_128_random_direction | 30% | 0.9638 | [0.9594, 0.9680] |
| clustered_3center_farthest_first | 1% | 0.4981 | [0.4852, 0.5110] |
| clustered_3center_farthest_first | 10% | 0.9032 | [0.8962, 0.9097] |
| clustered_3center_farthest_first | 30% | 0.9851 | [0.9824, 0.9876] |
| random | 1% | 0.7439 | [0.7362, 0.7517] |
| random | 10% | 0.9850 | [0.9826, 0.9872] |
| random | 30% | 0.9951 | [0.9935, 0.9965] |

### C.3 配对差异（clustered − random）

| pair | p | metric | pairable | n pairs | mean diff | 95% CI | reason |
|---|---:|---|---|---:|---:|---|---|
| random_vs_clustered_128_random_direction | 1% | prefix_recall_80 | True | 5832 | -0.3040 | [-0.3217, -0.2854] |  |
| random_vs_clustered_128_random_direction | 1% | prefix_recall_100 | True | 5832 | -0.3254 | [-0.3428, -0.3066] |  |
| random_vs_clustered_128_random_direction | 1% | ndcg_100 | True | 5832 | -0.0053 | [-0.0132, 0.0027] |  |
| random_vs_clustered_128_random_direction | 10% | prefix_recall_80 | True | 5832 | -0.1664 | [-0.1777, -0.1552] |  |
| random_vs_clustered_128_random_direction | 10% | prefix_recall_100 | True | 5832 | -0.1414 | [-0.1516, -0.1315] |  |
| random_vs_clustered_128_random_direction | 10% | ndcg_100 | True | 5832 | -0.0069 | [-0.0249, 0.0127] |  |
| random_vs_clustered_128_random_direction | 30% | prefix_recall_80 | True | 5832 | -0.0449 | [-0.0495, -0.0403] |  |
| random_vs_clustered_128_random_direction | 30% | prefix_recall_100 | True | 5832 | -0.0352 | [-0.0391, -0.0313] |  |
| random_vs_clustered_128_random_direction | 30% | ndcg_100 | True | 5832 | -0.0101 | [-0.0282, 0.0097] |  |
| random_vs_clustered_3center_farthest_first | 1% | prefix_recall_80 | False | 0 | NA | [NA, NA] | CARDINALITY_MISMATCH |
| random_vs_clustered_3center_farthest_first | 1% | prefix_recall_100 | False | 0 | NA | [NA, NA] | CARDINALITY_MISMATCH |
| random_vs_clustered_3center_farthest_first | 1% | ndcg_100 | False | 0 | NA | [NA, NA] | CARDINALITY_MISMATCH |
| random_vs_clustered_3center_farthest_first | 10% | prefix_recall_80 | True | 5832 | -0.0996 | [-0.1071, -0.0922] |  |
| random_vs_clustered_3center_farthest_first | 10% | prefix_recall_100 | True | 5832 | -0.0823 | [-0.0889, -0.0759] |  |
| random_vs_clustered_3center_farthest_first | 10% | ndcg_100 | True | 5832 | -0.0226 | [-0.0384, -0.0063] |  |
| random_vs_clustered_3center_farthest_first | 30% | prefix_recall_80 | False | 0 | NA | [NA, NA] | CARDINALITY_MISMATCH |
| random_vs_clustered_3center_farthest_first | 30% | prefix_recall_100 | False | 0 | NA | [NA, NA] | CARDINALITY_MISMATCH |
| random_vs_clustered_3center_farthest_first | 30% | ndcg_100 | False | 0 | NA | [NA, NA] | CARDINALITY_MISMATCH |

只有 cardinality 匹配且逐 query 对齐的比较才给出配对 CI；CI 是否跨 0 不等于因果结论。

### C.4 修正后的 nDCG@10

nDCG@10 只作为辅助指标，与 exact vector Recall@10 分开解释。修正算法保留全部候选，按精确 cosine 排序，同分按 corpus row ID 确定。

| mask | p | nDCG@10 @60% | @80% | @90% | full |
|---|---:|---:|---:|---:|---:|
| clustered_128_random_direction | 1% | 0.0162 | 0.0161 | 0.0161 | 0.0161 |
| clustered_128_random_direction | 10% | 0.1066 | 0.1070 | 0.1069 | 0.1069 |
| clustered_128_random_direction | 30% | 0.2214 | 0.2220 | 0.2221 | 0.2225 |
| clustered_3center_farthest_first | 1% | 0.0135 | 0.0135 | 0.0135 | 0.0134 |
| clustered_3center_farthest_first | 10% | 0.0909 | 0.0909 | 0.0911 | 0.0912 |
| clustered_3center_farthest_first | 30% | 0.1976 | 0.1983 | 0.1987 | 0.1988 |
| random | 1% | 0.0212 | 0.0214 | 0.0214 | 0.0214 |
| random | 10% | 0.1128 | 0.1136 | 0.1138 | 0.1138 |
| random | 30% | 0.2314 | 0.2323 | 0.2325 | 0.2326 |

方向性观察：selectivity 排序（30% > 10% > 1%）与 random 高于 clustered 一致于 exact Recall；但 prefix 增益很小，说明稀疏 qrels 与候选覆盖限制使 nDCG@10 对 prefix 不敏感，不能替代 exact vector Recall。

## D. 三中心 mask 变体：farthest-first cluster-prefix authorization

机器可读名称 `clustered_3center_farthest_first` 保持不变。其**实际构造语义**是：在归一化 embedding 空间用 farthest-first 选出三个中心并把每个 corpus 文档分配给最近中心，然后按中心选择顺序排列 cluster，**从第一个 cluster 开始整簇取文档，当前 cluster 不足时才进入下一个 cluster，达到目标授权数即停止**。因此分析文字中更准确的描述是 **farthest-first cluster-prefix authorization（三中心划分 + 按中心顺序截取簇前缀）**；它**不是**三个中心对应区域的均衡混合，也**不是**每个中心都贡献文档的授权集合。

构造细节（与 `experiments/exp10_fiqa_hnswlib/rebuild_cluster_masks.py` 和 `results/exp10b2/cluster_mask_manifest.json` 一致）：初始中心为 `default_rng(seed).choice(N)`；后续中心按到已选中心的最小平方欧氏距离最大值选取，同距离取最小 corpus 行号；分配用归一化向量最大 dot product，同分取选择顺序靠前的中心；簇内不足时按到中心平方距离升序、再按 corpus 行号升序取；目标数 `K=ceil(rho*N)`；不使用任何 query 内容。

**全部 seed × selectivity 的 cluster 覆盖核验**（数据取自 manifest 的 `cluster_sizes` 与 `partial_details`，非任务包示例复制）：

| seed | cluster_sizes（按选择顺序） | 1% K=577 | 10% K=5764 | 30% K=17292 |
|---:|---|---|---|---|
| 2026 | [22150, 26572, 8916] | 仅簇 0（取 577） | 仅簇 0（取 5764） | 仅簇 0（取 17292） |
| 2027 | [30389, 16011, 11238] | 仅簇 0（取 577） | 仅簇 0（取 5764） | 仅簇 0（取 17292） |
| 2028 | [10789, 36094, 10755] | 仅簇 0（取 577） | 仅簇 0（取 5764） | 簇 0 全取 10789 + 簇 1 取 6503 |

即：9 个 mask 中 8 个授权集合完全落在第一个 cluster 内；仅 seed=2028、30% 档跨入第二个 cluster。注意 manifest 的 `partial_details` 只记录"被部分截取"的簇，整簇纳入的簇 0 不出现在其中，故 `partial_details` 的 `[1]` 不表示"仅来自簇 1"，应结合 `cluster_sizes` 与 K 判读。

| p | ceil(K) | 旧 random cardinality | 新 cluster3 cardinality | 配对状态 |
|---:|---:|---:|---:|---|
| 1% | [577] | [576] | [577] | CARDINALITY_MISMATCH |
| 10% | [5764] | [5764] | [5764] | MATCHED |
| 30% | [17292] | [17291] | [17292] | CARDINALITY_MISMATCH |

| ef | p | prefix Recall@10 @60% | @80% | @90% | full |
|---:|---:|---:|---:|---:|---:|
| 64 | 1% | 0.2724 | 0.3287 | 0.3540 | 0.3783 |
| 64 | 10% | 0.6986 | 0.7702 | 0.7942 | 0.8162 |
| 64 | 30% | 0.8956 | 0.9359 | 0.9468 | 0.9554 |
| 128 | 1% | 0.3827 | 0.4454 | 0.4729 | 0.4981 |
| 128 | 10% | 0.8184 | 0.8704 | 0.8895 | 0.9032 |
| 128 | 30% | 0.9570 | 0.9758 | 0.9810 | 0.9851 |
| 256 | 1% | 0.5013 | 0.5751 | 0.6066 | 0.6336 |
| 256 | 10% | 0.9050 | 0.9372 | 0.9480 | 0.9570 |
| 256 | 30% | 0.9850 | 0.9924 | 0.9943 | 0.9958 |

## E. 仍然无法支持的主张

本轮所有数值结论**仅适用于**：FiQA test queries + `sentence-transformers/all-MiniLM-L6-v2`（固定 revision `1110a243...`）+ hnswlib v0.9.0 + 当前 HNSW 参数（M=32、efConstruction=200、efSearch∈{64,128,256}、k=10、seed=2026、单线程）+ 当前合成授权 mask 构造 + HNSW query distance-evaluation trace 口径。三中心变体的结论进一步局限于上文所述的 farthest-first cluster-prefix 首簇局部授权子集。

- 不声称已证明完整访问模式隐私。
- 不声称已证明在线无损 stopping rule；Oracle 是事后上界。
- 不声称已证明真实企业 ACL 下的安全性；授权 mask 是合成的。
- 不声称已解决 Agent/RAG 授权检索问题。
- 不声称已证明 PA-VFANN 普遍优于现有方法。
- 不声称已证明所有 ANN 系统都存在相同问题，或三中心/多区域授权分布普遍具有同样的 1% 困难现象。

## 对七个问题的回答

1. **修正 NOT_REACHED 后，Oracle prefix 空间是否仍然存在？** 是，但只作为事后空间：例如 ef=128、旧 clustered、10%、δ=0.10 的 reached-only mean t*/B=0.6443（95% CI [0.6403, 0.6484]）。本数据所有样本均 reached，因此不存在被 B/1.0 误填的样本。
2. **哪些 selectivity 下 reached rate 明显下降？** 没有：三个 mask 类型、三个 selectivity、两个 δ、三个 efSearch 的 reached rate 全部为 1.000。1% 的困难体现在 full-trace Recall 更低，而不是 Oracle 不可达。
3. **random 与两种 clustered 授权构造的差异有多大？** C.2 给出非配对聚合均值，C.3 给出严格配对差值；三中心变体在 cardinality 不匹配档位不给配对因果解释。这里比较的是三种**合成授权 mask 构造**，不是三种均衡的多区域授权分布；其中 `clustered_3center_farthest_first` 在当前实现下是首簇为主的 cluster-prefix 子集。
4. **修正后的 bootstrap 是否支持稳定差异？** 以 C.3 的 query-level cluster bootstrap 95% CI 为准；仅跨 0 与否不足以达到因果主张。
5. **修正 nDCG 后，质量趋势是否与 exact vector Recall 一致？** 方向上一致（30% > 10% > 1%，random > clustered），但 nDCG@10 随 prefix 几乎不增长；qrels 稀疏且 IDCG 基于全部授权相关文档，因此 nDCG 是辅助指标，不能替代 exact vector Recall。
6. **三中心变体在 1% 授权率下的困难现象如何表述？** 更准确的说法是：**在当前 farthest-first cluster-prefix 构造下，首簇局部授权子集在 1% 授权率下仍出现明显 full-trace Recall 损失**——1% 档 prefix Recall@10（B）为 ef64=0.3783、ef128=0.4981、ef256=0.6336，明显低于 10% 档（0.8162/0.9032/0.9570）和 30% 档（0.9554/0.9851/0.9958）。这是**当前构造下的局部授权分布观察**：9 个 mask 中 8 个授权集合完全落在第一个 cluster 内，因此不能表述为"三个 cluster 均衡参与"，也不能据此证明"一般意义上的三中心或多区域授权分布"具有同样现象。
7. **哪些结论只适用于当前 FiQA + MiniLM + hnswlib 配置？** 本文全部数值结论都只适用于该配置、固定 revision 的组件、合成授权 mask 与有序距离计算 trace；不外推到真实 ACL、其他模型/索引或其他硬件/实现。

## 交付与停止

本轮完成 EXP-10B.2 后立即停止；不启动 EXP-11，不新增数据集，不尝试新的 stopping rule，不引入新的密码学原语，不包装成 Agent/RAG 实现。是否继续投入 PA-VFANN 由用户与研究助手共同判断。

## EXP-10B.2-R1 语义勘误与冻结记录

本轮为**有限文档勘误**：只修正 `clustered_3center_farthest_first` 的构造语义解释、结论措辞与限制说明。没有重新生成 embedding、mask、HNSW index、query trace、Ground Truth 或统计结果；原始 trace、CSV、mask manifest、统计脚本与原始输入 SHA-256 清单（39 项）全部复核一致。勘误依据见 `docs/EXP10B2_SEMANTIC_ERRATUM.md`。

EXP-10 各阶段状态：

- EXP-10A：trace feasibility 完成（hnswlib v0.9.0 有序距离计算轨迹，V1–V5 PASS）。
- EXP-10B：FiQA 外部有效性实验完成（原 ZIP 通道阻断 → BEIR 一手组件 revision-pinned 恢复）。
- EXP-10B.1：数据源修订完成（数据门 `PASS_COMPONENT_ARTIFACTS`，原 ZIP MD5 仍 `NOT_VERIFIED`）。
- EXP-10B.2：统计与指标修正完成（Oracle / bootstrap / nDCG / clustered mask）。
- EXP-10B.2-R1：三中心授权分布语义勘误完成（本轮，仅文档）。

本轮之后 EXP-10 冻结：不启动 EXP-11、不增加新数据集、不重跑 HNSW、不追加统计审计。后续如需新实验，必须先提出独立、明确的研究假设与贡献目标。

**EXP-10 STATUS: FROZEN**
