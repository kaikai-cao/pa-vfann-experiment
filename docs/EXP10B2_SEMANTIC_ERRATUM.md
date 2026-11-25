# EXP-10B.2-R1：三中心授权分布语义勘误

- 基线提交：`b9c088a9b974aa464e9d04d5f6b46ae279288f3c`
- 分支：`exp10-fiqa-semantic-erratum`
- 性质：有限文档勘误，不是新实验；EXP-10 冻结轮次。
- 机器可读名称 `clustered_3center_farthest_first` **不重命名**：mask 文件、数据字段、manifest 键与 CSV 列全部保持原样。

## 1. 需要纠正的语义

`clustered_3center_farthest_first` 的**实际**授权集合构造（`experiments/exp10_fiqa_hnswlib/rebuild_cluster_masks.py`，`build_three_center_mask`）：

1. 在归一化 corpus embedding 上用 farthest-first 选 3 个中心：初始中心 `default_rng(seed).choice(N)`，后续中心按到已选中心的最小平方欧氏距离最大者选取，同分取最小 corpus 行号；
2. 每个文档按最大 dot product 分配给最近中心，同分取选择顺序靠前的中心；
3. cluster 按中心选择顺序排列；
4. **从第一个 cluster 开始整簇取文档，当前 cluster 不足时才进入下一个 cluster**；
5. 簇内部分截取时按到中心平方距离升序、再按 corpus 行号升序；
6. 达到 `K = ceil(selectivity * N)` 即停止（577 / 5764 / 17292）；
7. 不使用任何 query 内容参与 mask 构造。

因此该构造是 **farthest-first cluster-prefix authorization（三中心空间划分 + 按中心顺序截取簇前缀）**。它**不是**三个中心对应区域的均衡混合，也**不保证**每个中心都贡献授权文档。任何将其表述为"均衡三中心""多区域共同参与的授权分布"的说法都是过度解释。

## 2. 事实核验（全部 seed × selectivity）

数据来源：`results/exp10b2/cluster_mask_manifest.json` 的 `rule.cluster_sizes` 与 `rule.partial_details`，并与 `rebuild_cluster_masks.py` 的循环顺序逐项对照。N = 57638。

| seed | cluster_sizes（按选择顺序） | 1% K=577 | 10% K=5764 | 30% K=17292 |
|---:|---|---|---|---|
| 2026 | [22150, 26572, 8916] | 仅簇 0 | 仅簇 0 | 仅簇 0 |
| 2027 | [30389, 16011, 11238] | 仅簇 0 | 仅簇 0 | 仅簇 0 |
| 2028 | [10789, 36094, 10755] | 仅簇 0 | 仅簇 0 | 簇 0 全取 10789 + 簇 1 取 6503 |

结论：**9 个 mask 中 8 个授权集合完全落在第一个 cluster 内**；唯一跨簇的是 seed=2028、30% 档，进入第二个 cluster 取 6503 篇。第三个 cluster 在全部 9 个 mask 中均未贡献文档。

判读注意：manifest 的 `partial_details` 只记录"被部分截取"的簇；整簇纳入的簇 0 不在其中。因此 seed=2028、30% 档的 `partial_details=[{cluster_order:1, taken:6503}]` 不能读成"仅来自簇 1"，必须结合 `cluster_sizes` 与 K 判断。

## 3. 修正后的结论边界

原表述："新三中心 mask 复现 1% 授权困难现象。"

修正表述："**在当前 farthest-first cluster-prefix 构造下，首簇局部授权子集在 1% 授权率下仍出现明显 full-trace Recall 损失。**"

必须同时说明：

- 这是当前构造下的**局部授权分布观察**，不是三个 cluster 均衡参与的授权分布结果；
- 当前结果**不能证明**一般意义上的三中心或多区域授权分布具有相同现象；
- 数值本身（1% 档 full-trace Recall@10：ef64=0.3783、ef128=0.4981、ef256=0.6336）不变，且仍与 10%/30% 档的对比保持一致。

## 4. 保留不变的内容

以下结论**不因本轮语义修正而删除或否定**，仅按"直接观测 / 统计比较 / 研究假设 / 未验证泛化"区分表述层次：

- random 与 `clustered_128_random_direction` 的历史对比（C.1/C.2/C.3）；
- Oracle reached-only 统计与 NOT_REACHED 空白编码（C.1）；
- query-level cluster bootstrap 与配对差异（C.2/C.3）；
- 修正后的 nDCG@10（C.4）；
- 原始 trace 可靠性检查（A）；
- 1% 授权率下的质量损失观察（D，按第 3 节措辞）。

## 5. 修改范围与可复算声明

仅修改：

- `docs/EXP10B2_CORRECTION_REPORT.md`（语义描述、结论措辞、限制说明、冻结记录）
- 本文件（新增）

未修改且未重新生成：原始 EXP-10 报告、原始 trace、EXP-10B.2 全部 CSV/JSON、mask 文件与 manifest、统计脚本、embedding、HNSW index、Ground Truth。原始输入/结果 SHA-256 清单 `results/exp10b2/original_input_sha256.txt` 共 39 项，本轮复算全部一致（0 缺失、0 不符）。

所有统计结果仍可从已提交的原始 trace 与脚本重算；本轮不产生任何新数值。

## 6. 冻结

- EXP-10A：trace feasibility 完成。
- EXP-10B：FiQA 外部有效性实验完成。
- EXP-10B.1：数据源修订完成。
- EXP-10B.2：统计与指标修正完成。
- EXP-10B.2-R1：语义勘误完成（本轮）。

**EXP-10 STATUS: FROZEN**

本轮之后不启动 EXP-11、不增加新数据集、不重跑 HNSW、不追加统计审计。后续新实验必须先提出独立、明确的研究假设与贡献目标。
