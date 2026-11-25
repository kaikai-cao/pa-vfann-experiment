# claims_and_evidence.md — 结论—证据—独立核验表

状态定义：
- **已核验**：本审计直接读取原文/原始文件并可重复检查。
- **作者声称**：论文作者报告值，本审计未复现实验，不能写成已验证事实。
- **UNVERIFIED**：仅见二手/摘要，未取全文。
- **NOT FOUND**：在核验范围内未找到，不作绝对不存在断言。

| 结论 | 原始证据 | 独立核验方法 | 状态 |
|---|---|---|---|
| SAGE 攻击者是 passive/persistent server，不可见明文内容/嵌入/查询/标签，不注入查询 | SAGE §III-B 逐字："we consider a passive and persistent server-side adversary that observes legitimate retrieval executions without interfering with them..." | 下载 arXiv HTML v1，转文本后定位 §III-B，逐字比对 | 已核验 |
| SAGE 可观察的是无序返回 ID 集合序列 ℒ_AP=(I₁,…,I_M)，不用分数/排序 | SAGE §III-B Eq.(2)(3)："the adversary observes the unordered set I_i..." / "SAGE uses neither similarity scores nor retrieval rankings" | 同上；见 DATA_AUDIT §1.1 | 已核验 |
| SAGE 目标是语义标签/查询类别，不是授权范围或 ACL 状态 | SAGE §III-C Eq.(5) `SAGE:(ℒ_AP,𝒫)→(λ̂,ℓ̂)`；§III-C "both take values in the same set of semantic categories" | 同上；全文检索 acl/policy/revocation 作为攻击目标未出现 | 已核验 |
| SAGE co-retrieval graph 用 Jaccard 权重、谱嵌入+KMeans、OT/标签传播 | SAGE §V-A Eq.(8)(9)、§V-B Eq.(10)(11)、§VI | 下载原文逐节读取公式 | 已核验 |
| SAGE 作者声称 1% 标签下最高 84.3% 记录标签准确率；SAGE-Dist AG News 66.9%/68.1% | SAGE Abstract、§VII；实验 M=2,000、k=100、10 runs | 只记录作者报告值；本审计未复现 | 作者声称 |
| 固定 pseudonymization 无效；理想 rotation 在锚点条件敏感 | SAGE 附录 B-A Eq.(26)(27) "requires persistent identifier linkability"；§VIII；附录 C-E：窗口 50 时 AG News 76% vs 29%，Yahoo 45% vs 19% | 下载原文，逐字读取三处 | 已核验（结果为作者实验报告） |
| SAGE 公开代码未发现 | 全文检索 github/code/artifact：唯一 GitHub 链接指向 Quiver 第三方系统 | `grep -niE "github|source code|code (is|will be|available)|reproduc|artifact"` on 本地全文 | NOT FOUND |
| ASQ revision / license / 文件层级 | HF API `sha=14554ef4…`、`lastModified=2026-10-22`、license=mit；GitHub README `MIT` | `curl` HF API + README；manifest 中记录 SHA256 | 已核验 |
| ASQ 四 TSV 字段定义 | HF card 与 GitHub README；实际文件头 `qid/iteration/docid/rank` 等 | 下载并读取 `answers.tsv` 等四个文件首行；脚本解析全部行 | 已核验 |
| ASQ 抽查集合 976 轨迹、1–25 调用/轨迹、7,101 docid、97 跨轨迹复现 | `scripts/audit_datasets.py` 输出 `audit_output.txt` | 重跑命令（README §复现命令）；对照 `sample_validation.json` 25 条 | 已核验（可复现） |
| ASQ 无 user/role/ACL/墙钟时间 | 四文件字段清单；脚本 `missing_fields` | 逐文件字段检查；全文搜索 JSON/CSV 无相关列 | 已核验 |
| ASQ 53 个 qid 有 answer 无检索；3/976 iteration 不连续 | 脚本 `answers_without_retrieval=53`、`contiguous_iteration_from_zero=973/976` | 重跑脚本核对 | 已核验 |
| ACL Benchmark revision / license / 合成性 | HF API `sha=6e3bb8d…`；card MIT；"100% synthetic and fictional" | curl HF API + 下载 README | 已核验 |
| ACL Benchmark 186 用户 / 25 组 / 210 容器 / 49 事件 / 12,214 文档 / 616 QA / 1,040 probe | 原始 JSON/JSONL 解析；`acl_audit.json` | 脚本逐文件统计，重跑可复现 | 已核验 |
| ACL 事件为全量替换，最终态与最后事件 45/45 一致 | `acl_matrix.json` 的 `initial_acl`、`acl`、`acl_change_events` | 脚本对 45 个有事件容器逐一比对 allow/deny/groups 集合 | 已核验（可复现） |
| u4 于 2026-07-01 由 payments 转 security；存在 acl_time_travel 与 post_revocation_ask 样本 | `world/bible.json` 用户字段；`golden.jsonl` GOLD-0481；probe 类型计数 | 脚本输出 `role_change_ground_truth`；人工读取 GOLD-0481 | 已核验 |
| ACL 文档 ID 与团队确定性耦合（CONF-DATA→data 等） | `world/bible.json` 12 个 space→team；`documents_manifest.jsonl` doc_id 前缀 | 脚本 `synthetic_artifact_risk`；重跑可复现 | 已核验 |
| `world/bible.json` 存在于数据集 | HF `/tree/main/world` 返回该文件（411,882 bytes）；resolve URL 200 | curl 直接下载并计算 SHA256，写入 manifest | 已核验 |
| AFR 内容级非干涉、86.1% vs 0% 等数值 | ACL Anthology 2026.trustnlp-main.15 摘要 | WebFetch 读取 ACL 页面；**全文未取** | 作者声称（限于摘要） |
| PP-RFANNS 显式泄露 matched nodes/HNSW 轨迹/候选 ID/最终 ID，且承认跨查询重叠 | arXiv:2608.16488 §5.4、§5.3、§5.6 逐字引文 | WebFetch 读原文相关节 | 已核验 |
| ObliSC 完全遗忘定义与 TEE+ORAM 假设 | arXiv:2611.25374 §II-B Definition 1 与 §III 假设脚注 | 下载 HTML 转文本，逐字读取 | 已核验 |
| DP-MultiRAG 多轮累积泄露；Private-RAG 每文档 DP 过滤 | IEEE TDSC DOI 页面摘要 / COLM 2026 公开摘要镜像 | WebFetch/WebSearch 读摘要；**全文未取** | UNVERIFIED（限于摘要） |
| PA-VFANN E3 只保证搜索计划不受策略影响，不声称完整访问模式隐私；受控图非 HNSW | `pa-vfann-experiment` main README §5、§7、§8、§10 | Read 工具读取本地 README（只读） | 已核验 |
| agent-exec-binding-mvp 解决请求授权→工具执行绑定，Python 路径不用 ZK | 该仓库 README §1、§13（What is implemented）、§34（Explicit limitations） | Read 工具只读 README；未修改文件 | 已核验 |
| 两数据集可直接拼接成真实企业 Agentic RAG 数据 | 无共享主体/文档空间/策略；ASQ qid 为公开查询 ID，ACL 文档为虚构企业语料 | 字段级比对；见 DATA_AUDIT §4 | 已否定（不得拼接） |
| B4 相对 B2 有稳定授权推断增益 | 无配对数据可测；任务分组/顺序的服务端可见性未确认 | BASELINE_MATRIX §7 | 未评估（NOT_EVALUABLE） |

## 独立复核建议（给研究者）

1. 运行 `python scripts/audit_datasets.py --data-dir <你下载的原始文件目录> --out-dir <evidence目录> --samples 25`，比对 `dataset_manifest.json` 的 SHA256 与本表统计。
2. 直接打开 SAGE HTML v1 的 §III-B / §V-A / §VIII / 附录 C-E，核对逐字引文。
3. 打开 HF 两个数据集的 Files and versions，核对 revision 与文件 SHA256。
4. 打开 `acl_matrix.json`，随机抽 3 个有事件的容器，验证「最后事件 = 最终 ACL」。
5. 打开 ASQ `retrieved_docs.tsv`，按本脚本的排序方式抽 25 个 qid，核对 `sample_validation.json` 的调用次数与 docid 统计。
