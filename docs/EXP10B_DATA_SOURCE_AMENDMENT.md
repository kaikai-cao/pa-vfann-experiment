# EXP-10B.1 — BEIR 官方原始组件恢复与数据源条款修订

日期：2026-11-25  
分支：`exp10-fiqa-hnswlib-external-validity`  
基线：`ccebb03e67c31ea1cc325c2837c92ccfc4323fd4`  
修订编号：`EXP-10B.1`

---

## 1. 修订性质

原 EXP-10B 因 UKP 官方 ZIP 下载服务器在当前环境中不可用，已在 `docs/EXP10B_PHASE0_STOP.md` 记录 `STOP_PRE_REGISTERED_DATA_GATE`，提交为 `ccebb03e67c31ea1cc325c2837c92ccfc4323fd4`。该历史停止记录保持不变。

本修订只放宽“必须取得官方 `fiqa.zip` 并通过其 MD5”这一条数据源固定方式；允许使用 BEIR 官方 Hugging Face 组织 `BeIR` 在历史 revision 中发布的原始组件文件：

- `BeIR/fiqa` 的 `corpus.jsonl.gz`
- `BeIR/fiqa` 的 `queries.jsonl.gz`
- `BeIR/fiqa-qrels` 的 `test.tsv`

这不是第三方镜像，不是 Parquet 转换结果，也不是人工拼装的 split。

**必须保留的边界：原 ZIP 的 MD5 `17918ed23cd04fb15047f73e6c3bd9d9` 仍然未被验证，不得写成 PASS。** 本轮数据门裁决只能写为 `PASS_COMPONENT_ARTIFACTS`。

---

## 2. 固定 revision 与文件

| 角色 | 仓库 | revision | 文件 | 预期原始大小 | 预期 SHA-256 |
| --- | --- | --- | --- | ---: | --- |
| corpus | `BeIR/fiqa` | `a90551af496e20ce7887c02f07f7ea5c86908fb9` | `corpus.jsonl.gz` | 17,662,437 | `6d2c7e27aeb8c646791178e3e5591a373813642f38d9c992c0a4f6cbf4092f72` |
| queries | `BeIR/fiqa` | `01557ca93ac1c5f4ba52cd6955bc44515846f3fa` | `queries.jsonl.gz` | 193,723 | `a683bbedd2fd3b1fcb1a44fbd706daf9aff27291cd99e7a086b3cf7624785acb` |
| test qrels | `BeIR/fiqa-qrels` | `93a4617fe9d8263f8055a67a2269eb40b8659c0a` | `test.tsv` | 下载后实测 | 下载后实测并固定 |

所有下载必须通过 revision-pinned 方式，不得使用 `main`。

---

## 3. 数据门验收口径

1. corpus/queries 原始文件大小和 SHA-256 必须与表中值逐字节一致；
2. gzip 解压成功，逐行 JSON 解析成功；
3. qrels 固定 revision 一致，TSV header 正确，计算并记录 SHA-256；
4. corpus `_id` 唯一、queries `_id` 唯一；
5. qrels 的 query ID 和 corpus ID 均可解析，且无重复 query-document 对；
6. test split 由 qrels query IDs 从 6,648 条全量 queries 中选取，预期 648 条；
7. manifest 记录原始文件、行数、ID 集合哈希、license、原 ZIP MD5 状态 `NOT_VERIFIED`；
8. 任一检查失败即停止，不寻找其他替代源。

数据门全部通过后标记为 `PASS_COMPONENT_ARTIFACTS`，直接进入原 EXP-10B embedding 阶段，不再等待确认。

---

## 4. Recall@10 准入门矛盾修正

原任务包 §8 与 §14.8 对 `0.90` 门槛的停止逻辑相反。此处按新任务包固定为：

> **只有当三个 efSearch（64、128、256）的 mean unfiltered exact Recall@10 全部低于 0.90 时，才停止正式 Oracle Prefix 主结论。**

该规则已在查看任何基线 Recall 数值之前写入 `experiments/exp10_fiqa_hnswlib/experiment_config.json` 和本文档。

执行细则：

- 64、128、256 全部报告；
- 至少一个达到 0.90：继续 Oracle Prefix 主分析；
- 未达到 0.90 的 efSearch 保留完整结果，但标记 `LOW_QUALITY_CONFIG`；
- 三个都未达到 0.90：停止正式 Oracle 结论，不扩大网格、不更换参数、不更换模型或数据集。

---

## 5. 不变的实验条款

除上述数据源和准入门矛盾修正外，原 EXP-10B 条款全部不变：

- 模型：`sentence-transformers/all-MiniLM-L6-v2`
- 模型 revision：`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`
- CPU、float32、384 维、归一化 embedding
- hnswlib v0.9.0 + EXP-10A 最小插桩
- M=32、efConstruction=200、efSearch={64,128,256}、k=10、seed=2026、单线程
- 18 个合成授权 mask
- first-touch prefix Recall@10、Oracle Prefix、qrels nDCG@10
- query ID 配对 bootstrap 2000 次，seed=20261125
- 本轮完成即停止，不自动启动 EXP-11，不包装成 Agent/RAG 安全贡献

---

## 6. Git 与冻结边界

`docs/EXP10B_PHASE0_STOP.md` 保持原样。EXP-10A、Faiss STOP、EXP-01/08/09/09.1 历史文件保持零修改。

原始 corpus/queries/qrels、模型权重、embedding 矩阵和 trace 原始数据不提交 Git；提交范围限于脚本、manifest、汇总结果、报告和必要的压缩 trace。
