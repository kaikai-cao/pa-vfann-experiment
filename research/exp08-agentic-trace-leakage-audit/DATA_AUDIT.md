# DATA_AUDIT.md — EXP-02-R0 文献与数据可用性审计

核验日期：2026-11-25。所有数字来自 `evidence/dataset_manifest.json`、`evidence/sample_validation.json`、`evidence/acl_audit.json`、`evidence/audit_output.txt`（由 `scripts/audit_datasets.py` 从下载原始文件生成）与 `evidence/sources.md` 所列一手来源。**论文作者声称**与**本审计独立验证**分开写。

---

## 1. SAGE：原文核验（一手来源）

### 1.1 攻击者、可观察信息（§III-A/B，逐字证据）

论文定义记录为 `r_j = (id_j, b_j, λ_j, x_j)`，其中 `id_j` 是唯一记录标识符、`λ_j ∈ 𝒞` 是语义标签、`b_j` 是嵌入。

> “we consider a **passive and persistent** server-side adversary that observes legitimate retrieval executions without interfering with them. The adversary has no decryption keys and cannot access plaintext record contents, database embeddings, semantic labels, or query contents and embeddings, except for independently obtained auxiliary knowledge. It neither injects queries nor modifies the database or retrieval results.”

> “for each query i … the adversary observes the **unordered set** I_i of selected record identifiers … The accumulated access-pattern leakage is ℒ_AP = (I_1, I_2, …, I_M).”

> “The adversary only needs to recognize repeated identifiers across queries. Thus, opaque or encrypted identifiers do not prevent this leakage if they remain linkable. **SAGE uses neither similarity scores nor retrieval rankings.** Our attack applies to deployments exposing cross-query-linkable result identifiers.”

结论（本审计）：

- SAGE 的可观察面 = **跨查询可关联的返回 ID 集合序列**；不需要分数、排序、时间戳或查询明文。
- 其推断目标（§III-C）是 `λ̂`（记录语义标签）与 `ℓ̂`（查询语义类别），两者取值于同一语义类别集合 𝒞。**不是授权范围，也不是 ACL 状态变化**。
- 辅助知识两种：SAGE-Dist 用估计类别比例 `π̂`（模拟 1,000 个独立标签样本），SAGE-Known 用 1% 随机数据库记录的已知 ID-标签对。两者都已知类别数 C；多标签与未知 C 明确排除。

### 1.2 co-retrieval graph 构造（§V-A/B）

- 关联矩阵 `X ∈ {0,1}^{M×N}`，`X_ij = 1[id_j ∈ I_i]`；`O = X_Vᵀ X_V`，`O_jℓ = |Q_j ∩ Q_ℓ|`。
- Jaccard 加权：`W_jℓ = O_jℓ / (|Q_j| + |Q_ℓ| − O_jℓ)`（j≠ℓ），对角为 0。
- 对称归一化 `S = D^{−1/2} W D^{−1/2}`；取最大代数特征值的 p 维谱嵌入，行归一化后 KMeans 得 C 个匿名组；SAGE-Dist 用最优传输做组—类别匹配，SAGE-Known 用图标签传播 + 谱组锚点投票。
- 作者声称结果：1% 已知标签下 SAGE-Known 最高 84.3% 平均记录标签准确率；SAGE-Dist 在 AG News 上 66.9% 记录标签 / 68.1% 查询类别准确率，高于最强基线 21.8 / 41.9 个百分点；其它数据集效果下降。DCPE 真实实现（Quiver）上语义泄露仍存在。**这些是作者报告值，本审计未复现实验。**
- 消融（§VII-E）：M 从 100→4,000，SAGE-Known 记录标签准确率 AG News 80.0→85.3%、Yahoo 51.2→66.4%、MedMCQA 32.8→49.6%、CIFAR-100 17.8→28.3%；k∈{5,10,20,50,100,200} 时先升后饱和/下降；已知标签比例 0.1%→5% 提升准确率，类别覆盖度是限制因素。默认配置 M=2,000、k=100、10 次运行。
- 数据集：AG News(4 类)、Yahoo Answers(10)、MedMCQA(21)、CIFAR-100(100)；BGE-base-en-v1.5 / OpenCLIP ViT-B/32；数据库/查询/辅助池不重叠。

### 1.3 ID pseudonymization 与 rotation（必须区分条件）

- 附录 B-A **Proposition 1**：固定单射重命名 `φ` 下 `Q′(φ(id_j)) = Q_j`，Jaccard 权重不变，图同构。逐字条件：
  > “The result requires persistent identifier linkability and does not apply to independently unlinkable identifiers across queries.”
- §VIII：
  > “Fixed identifier pseudonymization does not prevent co-retrieval analysis when identifiers remain linkable. Identifier rotation may reduce accumulated leakage **if cross-window linkage is prevented**, although other metadata may still enable record linkage.”
- 附录 C-E 是**理想化 rotation 实验**：2,000 个查询按窗口划分、每窗口独立 pseudonyms，窗口大小 50；SAGE-Known 在 AG News 上「每窗口都能匹配锚点」76%，「锚点只在首个窗口」29%；Yahoo Answers 45% 与 19%。这是**理想化条件**，不是真实系统测量；其他持久标识符或元数据仍可能重新链接。

### 1.4 对本候选问题的直接回答

| 问题 | 回答 | 证据 |
|---|---|---|
| SAGE 已覆盖哪些跨查询语义推断？ | 记录语义标签、查询语义类别（单标签、已知 C）、在可链接 ID 的共检索图上 | §III-C、§V、§VII |
| 是否直接覆盖授权范围推断？ | **否**。目标是语义标签 λ/ℓ，不是有效权限集合或角色；没有 ACL/策略/主体概念 | §III-C Eq.(5) |
| 是否研究动态 ACL 状态变化？ | **否**。全文无 ACL、revocation、policy-state 作为攻击目标；rotation 是防御性 ID 实验，不是权限变化推断 | §VIII、附录 C-E |
| Agentic 多步结构是否提供扁平共现之外的信息？ | SAGE 用无序集合序列，**不使用顺序/分组/排序**。因此它不能直接回答 B4 相对 B2 的增益问题；但也不能由此推断增益存在——顺序信息可能只是重排已有共现信号 | §III-B、§V-A、§VIII |

**禁止事项已遵守**：没有因为应用场景从加密向量搜索换成 Agentic RAG 就认定创新。

---

## 2. ASQ：原始文件核验

### 2.1 来源、版本、许可证

- GitHub `fpezzuti/ASQ` README：MIT；论文 *How AI agents search*，PLOS ONE 21(10) 2026，DOI 10.1371/journal.pone.0360157。
- HF `AgenticSearchQueryset/ASQ` revision `14554ef4cbadc42a05d3c99da6bc18abb9d7f81e`（lastModified 2026-10-22）。Dataset Viewer 被禁用，因此核验按原始 TSV 而非 viewer 行预览。卡片声称总量 615k traces / 680k synthetic queries / 680k ranked lists / 421 MB；**本审计只下载并核验一个小集合，未逐条核验全量**。

### 2.2 实际文件结构与字段

层级：`traces/{dataset}/{retriever_config}/{agent_family}/{model}/`，四个 TSV：

| 文件 | 字段 | 视角 |
|---|---|---|
| `answers.tsv` | `qid, answer` | 研究者/Agent；服务端不可假设可见 |
| `iter_queries.tsv` | `qid, iteration, llm_query` | `llm_query` 仅研究者/Agent 可见 |
| `retrieved_docs.tsv` | `qid, iteration, docid, rank` | `docid/rank` 是候选服务端可见字段 |
| `thoughts.tsv` | `qid, iteration, thought` | 推理文本，服务端不可假设可见 |

**审计集合**：`traces/hotpotqa-test/BM25_k3/search_r1/Qwen-14B/`。SHA256 见 manifest。

### 2.3 至少 20 条完整轨迹抽查结果

`sample_validation.json` 含 **25 条**（>20），每条记录：sample_id、qid、task/session id、retrieval_call_count、iteration 值、是否有 docid、跨调用/跨轨迹可关联 docid 数、是否有 rank、是否有墙钟时间、字段是否满足审计要求、异常。抽查方式：把 `retrieved_docs.tsv` 的 qid 字典序排序后取前 N 条；生成过程不含任何查询/推理文本。

集合级统计（脚本输出）：

| 指标 | 值 |
|---|---:|
| answers / iter_queries / retrieved_docs / thoughts 行数 | 1,029 / 3,795 / 11,364 / 4,824 |
| 四文件交集 qid | 976 |
| 有 answer 但无检索记录的 qid | 53（这些 qid 有 thoughts、无 iter_queries） |
| 轨迹数（retrieved_docs qid） | 976 |
| 每条轨迹调用次数 min / median / max | 1 / 3 / 25 |
| 每条轨迹文档行数 min / median / max | 3 / 9 / 75 |
| iteration 从 0 连续的轨迹 | 973 / 976 |
| 唯一 docid | 7,101 |
| 出现在 >1 条轨迹的 docid | 97（单 docid 最多 8 条轨迹） |

### 2.4 三个观察视角（必须分开）

| 视角 | 可见内容 |
|---|---|
| 数据集研究者 | 四个 TSV 全部字段，包括 `llm_query`、`thought`、`answer` |
| Agent（客户端） | 任务/查询、自身推理、检索返回文档与内容 |
| 外包检索服务（保守基线） | 每次调用的返回 `docid` 集合、`rank`、返回数量；**调用顺序/轮次仅在客户端确实把每次检索作为独立请求发出时可见**；`qid` 是评测标识，不得默认随请求发送 |

在本审计集合中**不存在**：墙钟时间戳、`user_id`、角色标签、ACL/授权状态、文档内容（TSV 只有 ID）。因此：
- 任务边界可由 `qid` 恢复——但这是**研究者视角**的边界；
- 权限撤销/角色变更的时间点**无法**从 ASQ 观察，因为没有时间和主体；
- 跨调用文档 ID 是可以关联的（97 个 docid 跨轨迹复现），足以构造共现关系，但样本集合规模小（每轨迹 k=3），与 SAGE 默认 k=100 不同，不能直接比较数值。

### 2.5 ASQ 用途裁定

| 问题 | 裁定 |
|---|---|
| 能否提取完整 Agentic 检索轨迹？ | 能（该配置 976 条，含 iteration 顺序与 docid/rank） |
| 能否恢复任务边界与调用顺序？ | 能以 `qid`+`iteration` 恢复，但仅研究者视角；服务端任务分组需架构确认 |
| 能否构造跨调用文档共现？ | 能；本集合 97 个 docid 跨轨迹复现 |
| 是否有权限标签或权限状态真值？ | **没有**；无 user、role、ACL、时间戳 |
| 是否适合验证 B4 相对扁平共现图的额外信息？ | **不适合直接验证授权推断**；只能用于验证「轨迹结构可提取」与任务类别对照（次要目标） |

---

## 3. Permission-Aware Enterprise RAG Benchmark：原始数据核验

### 3.1 来源、版本、许可证

HF revision `6e3bb8d6071c3a46e8e9c22c856a24c737b9792d`（lastModified 2026-11-05），MIT，卡片声明 100% synthetic and fictional。只下载必要原始文件（未复制完整 90.9 MB 数据集进仓库）。

### 3.2 实际结构与数量（脚本解析）

| 项目 | 实测值 |
|---|---:|
| `identities.json` 用户 | 186（`u1`–`u6` 主要 persona + 180 NPC，含承包商） |
| `groups.json` 权限组 | 25；带时间戳的成员变更 19 条（分布在有历史的组） |
| `acl_matrix.json` 容器 | 210；全部有 `initial_acl`；其中 45 个容器含变更事件 |
| ACL 变更事件 | 49 条（分布在上述 45 个容器，非 49 个容器），时间 2026-03-01 → 2026-09-25；13 条含 `deny_users`，22 条含 `allow_users` |
| `world/bible.json` | 9 个团队、27 个微服务、18 个时间/厂商/区域转换、34 个剧情事件、40 个 canary、18 个注入 |
| `documents_manifest.jsonl` | 12,214 个文档记录 |
| `golden.jsonl` | 616 条；8 类；asking_user 仅 `u1`–`u6` |
| `acl_leak_probes.jsonl` | 1,040 条；7 类攻击 |

Golden 类别实测：multi_hop 122、acl_differentiated 122、single_hop 102、temporal 82、conflicting_sources 52、acl_time_travel 52、unanswerable 42、aggregation 42。Probe 类型：direct_ask 149、paraphrase 149、codename_guess 149、broad_summarize 149、citation_fishing 148、post_revocation_ask 148、indirect_prompt_injection 148。

### 3.3 ACL 时点真值可恢复性（关键）

- 事件是**全量替换**语义：脚本对 45 个有事件的容器核验「最后一个事件的 allow_users / deny_users / allow_groups」等于最终 `acl`，**45/45 一致**。
- 因此时点权限可按 `initial_acl` + 按时间戳排序的事件重建 `effective_acl(u, container, t)`；继承链字段 `inherits_from` 存在于 49/210 容器。
- 组历史为带时间戳的 add/remove，可重建 `members(group, t)`。
- `world/bible.json` 中用户 `u4` 有明确 `team_id=payments`、`move_date=2026-07-01T00:00:00Z`、`moved_to_team=security`；Golden QA 有 52 条 `acl_time_travel`，例如 `GOLD-0481` 在 `2026-06-15` 对 `u4` 判定拒绝并列出 `must_not_cite`。

结论：**可信的权限历史与角色变更 ground truth 存在**，这是该数据集最强的可用点。

### 3.4 合成伪相关风险（必须在实验中控制）

- 文档 ID 形如 `confluence:DATA:CONF-DATA-0001`，其中 space key `DATA` 在 `world/bible.json` 中确定性映射到团队 `data`；`PLAT→platform`、`PAY→payments`、`SEC→security` 等 12 个映射已记录在 `acl_audit.json`。
- 因此「用户角色推断」可能只是**从文档 ID 字符串解码团队名**，而不是从访问模式推断授权范围。攻击模型若拿到原始语义化 ID，会得到虚高准确率。
- 数据集 100% 合成、业务叙事固定（9 团队/12 空间/25 组），用户—部门—文档语义是人为构造的强相关。**不能把该数据集的性能写成真实企业环境验证**。
- 控制要求（写入 BASELINE_MATRIX）：任何未来实验必须把所有文档 ID 映射为**无语义的不透明随机 ID**（opaque ID），并在全部 B0–B4 中一致使用；对照条件保留语义化 ID 仅用于量化伪相关上界。

### 3.5 ACL Benchmark 用途裁定

| 问题 | 裁定 |
|---|---|
| 能否恢复完整 ACL？ | 能，210 容器均有 initial_acl，49 事件全量替换且最终态 45/45 一致 |
| 能否恢复历史授权状态？ | 能，事件与组历史均有时间戳 |
| 能否构造角色/权限范围标签？ | 能（团队、组、容器授权集合），但需 opaque ID 控制 |
| 能否构造撤权/角色变更前后样本？ | 能（49 事件、u4 转队、post_revocation_ask 探针 148 条） |
| 是否适合验证权限范围推断与状态变化检测？ | 适合作为**真值来源**；但数据集本身没有 Agentic 检索轨迹 |

---

## 4. 两个数据集的关联可行性（Phase 2 明确裁定）

**不存在真实、合法、可靠的直接关联**：

- ASQ 的 `qid` 是 HotpotQA/MS MARCO/researchy 查询标识；ACL Benchmark 的文档是虚构企业语料。两者无共享主体、无共享文档空间、无共享策略。
- 直接把两数据集拼接并声称得到「真实企业 Agentic RAG 数据」属于人为制造关联标签，**本轮不做，也不建议后续做**。
- 允许的路径：以 ACL Benchmark 的语料与 ACL 真值为基础，**用开源 Agent 独立生成**检索轨迹（ASQ 仓库 README 给出 `build_agent()`、`DataFrameExtractor`、`PyTerrier` retriever 的生成流程），生成时给每个文档分配不透明 ID，并记录 `user_id / asked_at / session/task id / call order / returned opaque docids`。本任务包规定本轮不开展完整生成实验，因此只评估可行性，不执行。
- 即便采用该路径，仍须回答：任务分组（task/session id）是否真的暴露给检索服务？若不暴露，则 B3/B4 相对 B2 的输入差异在服务端视角下不成立。

---

## 5. 相关工作边界（必要核验，非无限扩展）

| 工作 | 一手来源核验结论 | 与本项目的重叠 / 未覆盖 |
|---|---|---|
| AFR（TrustNLP 2026） | 摘要：把授权正确性归约为 noninterference，要求授权在**任何学习组件消费检索内容之前**约束候选集；受控 247 chunks / 232 docs / 12 角色 / 9 域；retrieve-then-filter 86.1% 查询暴露未授权上下文，AFR 0%；元数据标签新鲜度退化。全文未取，判断限于摘要与 ACL 元数据 | 重叠：多角色 RAG 授权。未覆盖：服务端跨调用元数据推断、权限状态变化检测。AFR 解决的是**内容级上下文暴露**，不是服务端轨迹推断 |
| PP-RFANNS（arXiv:2608.16488） | 原文 §5.4 明确泄露 `I_q`（匹配树节点）、`O_q`、HNSW 访问轨迹、候选 ID、DCE 比较顺序、最终 top-k ID；逐字：“repeated matched nodes, candidate identifiers, and result identifiers reveal equality and overlap patterns across query executions”；§5.6 静态数据库、honest-but-curious，动态更新/恶意/结果可验证均不在范围 | 重叠：访问模式与跨查询重叠泄露已显式定义。未覆盖：主体角色、授权范围、ACL 状态变化、Agent 多步轨迹。它不做语义/授权推断攻击 |
| ObliSC（arXiv:2611.25374） | 原文 §II-B：公开数据库 + 私有查询，honest-but-curious SP；Definition 1 full obliviousness = 相同公开参数下任意两查询的可观察访问轨迹不可区分；假设脚注：TEE 保护查询/中间值/结果，依赖 adaptively secure ORAM、oblivious local operations、填充到公开界 | 重叠：可作为隐藏访问模式的**防御参照**。未覆盖：授权范围推断；系统假设重（TEE+ORAM），且数据库公开、k 公开；不是本问题的现成方案 |
| DP-MultiRAG / Private-RAG | IEEE TDSC 摘要：多轮 RAG 的累积泄露由敏感文档跨轮重复暴露驱动，DP 按历史暴露自适应控制；Private-RAG 摘要：多查询 DP-RAG，每文档隐私过滤，ε≈10 可支持上百查询。**仅摘要核验** | 重叠：多轮/多查询累积泄露概念。未覆盖：服务端可见的检索元数据、ACL/角色推断；保护对象是输出侧敏感文档泄露，不是授权状态元数据 |

结论：四个方向都**没有完全覆盖**「从服务端可见的多步检索轨迹推断授权范围/权限状态」这一具体问法；但 SAGE 与 PP-RFANNS 已覆盖其核心信号形式（跨查询 ID 共现/重叠），因此新贡献不能只来自「换成 Agentic RAG 场景」。

---

## 6. 现有仓库边界（Phase 5，只读核验）

### pa-vfann-experiment（main README）

- E1 — Adaptive Post-filter：与 E3 同一公开搜索计划，服务端读取授权匹配位以提前停止；未授权节点不提权。
- E2 — Predicate-aware Search：自定义受控桥接基线，**不是** ACORN/RACORN。
- E3 — Fixed-trace Private Filtering：`plan_fixed_trace(q,G,B)` 不接触 policy/授权标签/匹配位/合法数；可测性质 `T(q,G,B,P₁)=T(q,G,B,P₂)`。
- README §10 逐字边界：不实现密码学协议；不把受控 kNN 图称 HNSW；不外推真实 Agent 授权系统；`secret_filter` 是**客户端模拟接口**，不等于访问模式隐藏或密码学安全。§8：E3 只保证搜索计划不受策略影响，**输出 ID、结果数量、公开图本身均未被隐藏，不据此声称完整访问模式隐私**。

因此：E3 的固定轨迹性质**不代表**隐藏跨查询语义共现，也**不能**推出抵御 SAGE；当前合成图实验（N=10,000 向量、200 查询、受控 kNN 图）不是真实 Agentic RAG 或真实 ANN 证据。本审计不重新包装 E1/E2/E3 作为新贡献。

### agent-exec-binding-mvp（README 只读）

研究对象是请求授权 → 工具执行的可信绑定：request-specific Ed25519 grant、gateway 快照验证、tool-signed receipt、签名哈希链审计、plan-level Merkle 承诺；README 明确 Python 路径不用 ZK、工具服务器是可信 mock、`signature authenticates the server's assertion; it does not independently prove that external data are true`。它没有研究检索服务端跨调用轨迹泄漏，不能把现有 Ed25519/Halo2 原型当作本候选问题的解决方案。本轮未修改该仓库。

---

## 7. 数据质量问题汇总（不得隐瞒）

1. ASQ 抽查集合中 53/1,029 个 qid 有 answer 与 thought 但无检索记录；3/976 轨迹的 iteration 不从 0 连续。
2. ASQ 抽查集合 k=3（每调用 3 篇），与 SAGE 默认 k=100 不可直接数值比较；跨轨迹复现 docid 仅 97/7,101。
3. ASQ 没有墙钟时间、用户 ID、角色或 ACL；不能单独做权限状态或撤权检测。
4. ACL Benchmark 文档 ID 与团队强耦合；必须用 opaque ID 控制，否则权限推断退化为命名空间解码。
5. ACL Benchmark 100% 合成；golden QA 只有 6 个 asking_user，若做用户隔离划分样本量不足，需要使用 180 NPC 扩展主体池。
6. 数据集卡片中的 `Number of rows: 17,660` 与各子表规模（43,807 messages、12,214 docs 等）口径不一致；本审计以实际下载的原始文件为准。
7. SAGE 公开代码未发现；作者实验结果未复现，均标注为作者声称。
