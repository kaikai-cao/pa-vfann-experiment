# 原始来源清单（EXP-02-R0）

核验日期：2026-11-25（GMT+8）。下表把「论文/数据集卡片声称」与「本审计实际读取到的文件」分开记录。

## 1. SAGE

| 项目 | 内容 |
|---|---|
| 论文 | “More Than You Expect!”: Leakage-Abuse Attacks on Encrypted Vector Search |
| 链接 | https://arxiv.org/abs/2611.27174 ；PDF https://arxiv.org/pdf/2611.27174 ；HTML v1 https://arxiv.org/html/2611.27174v1 |
| 版本 | v1，Submitted 20 Nov 2026，18 pages / 7 figures |
| 作者 | Yang Zhang, Ruiqi He, Xiaoqian Sun, Siyi Lv, Zheli Liu（Nankai University） |
| 实际核验 | 下载 HTML 全文（529,635 bytes）转纯文本，逐节读取 §III-A/B/C、§V-A/B、§VII-A/E、§VIII、附录 A/B-A/C-E |
| 公开代码 | **论文中未发现 SAGE 实现的代码仓库链接**；文中唯一 GitHub 链接是实验所用的第三方 Quiver 系统（`github.com/achref-soua/quiverOpen-source software, accessed November 2026`）。状态：NOT FOUND（不作「不存在于世界任何地方」的绝对断言） |

## 2. ASQ

| 项目 | 内容 |
|---|---|
| GitHub | https://github.com/fpezzuti/ASQ （README、结构、字段、许可证、引用） |
| HuggingFace | https://huggingface.co/datasets/AgenticSearchQueryset/ASQ |
| 论文 | “How AI agents search”, PLOS ONE 21(10), 2026；DOI https://doi.org/10.1371/journal.pone.0360157 ；arXiv:2602.17518 |
| HF revision | `14554ef4cbadc42a05d3c99da6bc18abb9d7f81e`（HF API，lastModified 2026-10-22T08:54:50Z） |
| 许可证 | MIT（GitHub README 与 HF card）；源数据集可能有各自许可证 |
| 实际核验 | 通过 HuggingFace resolve 下载 `README.md` 与一个完整 trace collection 的四个 TSV 到系统临时目录；SHA256 见 `dataset_manifest.json` |
| 下载集合 | `traces/hotpotqa-test/BM25_k3/search_r1/Qwen-14B/` |
| Dataset Viewer | HF 页面显示 "The Dataset Viewer has been disabled on this dataset."；结构核验按原始 TSV 进行 |
| 字段 | answers.tsv: `qid, answer`；iter_queries.tsv: `qid, iteration, llm_query`；retrieved_docs.tsv: `qid, iteration, docid, rank`；thoughts.tsv: `qid, iteration, thought` |

## 3. Permission-Aware Enterprise RAG Benchmark

| 项目 | 内容 |
|---|---|
| HuggingFace | https://huggingface.co/datasets/DevLCodes/permission-aware-enterprise-rag-benchmark |
| HF revision | `6e3bb8d6071c3a46e8e9c22c856a24c737b9792d`（HF API，lastModified 2026-11-05T17:08:46Z） |
| 许可证 | MIT（HF card） |
| 合成性 | 卡片声明 100% synthetic and fictional |
| 实际核验 | 下载 `acl/acl_matrix.json`、`acl/groups.json`、`acl/identities.json`、`world/bible.json`、`eval/golden.jsonl`、`eval/acl_leak_probes.jsonl`、`data/documents_manifest.jsonl` 与 README，逐文件解析；SHA256 见 `dataset_manifest.json` |
| 注意 | `world/bible.json` 在递归 tree API 中未展开，但在 `/tree/main/world` 与 resolve URL 存在且可下载（200，SHA256 已记录） |

## 4. 相关工作边界

| 工作 | 原始来源 | 核验状态 |
|---|---|---|
| Authorization-First Retrieval (AFR) | https://aclanthology.org/2026.trustnlp-main.15/ ；TrustNLP 2026, pp.256-271；DOI 10.18653/v1/2026.trustnlp-main.15 | 已读 ACL Anthology 摘要与元数据；结论限于该页可核验内容 |
| PP-RFANNS | https://arxiv.org/html/2608.16488 （arXiv:2608.16488，Aug 2026） | 已读原文 §2.2、§5.1-5.6 逐字泄露定义 |
| ObliSC | https://arxiv.org/abs/2611.25374 ；HTML https://arxiv.org/html/2611.25374v1 | 已读原文 §II-B（系统模型、Definition 1）与 §III 假设脚注 |
| DP-MultiRAG | IEEE TDSC 2026, DOI https://doi.ieeecomputersociety.org/10.1109/TDSC.2026.3724171 | 已读 IEEE 页面摘要；全文未取，结论限于摘要 |
| Private-RAG | OpenReview / Third Conference on Language Modeling (COLM) 2026；检索到 https://openreview.net （题名与摘要） | 已读公开摘要镜像；全文未取，结论限于摘要 |

## 5. 现有仓库边界

| 仓库 | 路径 | 核验范围 |
|---|---|---|
| pa-vfann-experiment | `D:/Research/pa-vfann-experiment`，分支基线 `main` @ `0145ccad4444633789dfd5ae42e4732bb0f76e46` | 只读 `README.md`；E1/E2/E3 定义见 §7、边界见 §10 |
| agent-exec-binding-mvp | `D:/Research/agent-exec-binding-mvp` | 只读 `README.md` §1-§11；未修改任何文件 |

## 6. 检索纪律记录

- SAGE、ASQ、ACL Benchmark、AFR、PP-RFANNS、ObliSC 为一手来源；DP-MultiRAG 与 Private-RAG 仅取公开摘要，文档中对它们的判断标注为「限于摘要」。
- 数据文件下载中 3 个文件首次遇到 SSL/TLS 中断，各重试一次（`--http1.1 --retry 2`）后成功；未编造替代文件。
- 未进行大规模无边界文献扩展；相关工作只覆盖任务包点名的四组。
