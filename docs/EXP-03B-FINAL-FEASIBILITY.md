# PA-VFANN-13 / EXP-03B：多租户秘密授权检索最终可行性审计

> 本轮为 PA-VFANN 的最终审查。结论不是"再列一批文献"，而是对 EXP-03A 留下的 HOLD 作一次性收口：以 Compass 为主要基线，逐一回答 6 个构造性问题，区分 A/B/C 三种执行架构，给出符号成本结构，并按六项 GO 条件作最终判决。
>
> 本轮**只新增本报告**，不修改 EXP-01、EXP-02、EXP-02A、EXP-03A，不修改任何实验数据，不实现协议。

---

## 0. 审计边界与来源状态

| 项目 | 内容 |
|---|---|
| 基线 commit | `d18e7818f834cef77d92cd41ac1cbbdd3a713242`（EXP-03A，分支 `exp03a-verifiability-audit`） |
| 本轮分支 | `exp03b-final-feasibility`（从基线新建，独立分支） |
| 改动范围 | 仅新增 `docs/EXP-03B-FINAL-FEASIBILITY.md` |
| 一手全文已取得 | Compass（OSDI 2025 官方 PDF）；Atlas、V3DB、VIDA、HONEYBEE、RACORN v2、Tiptoe（官方页面/全文或正文片段） |
| 一手全文受限 | BiSON（ePrint 403，仅摘要与二手威胁模型描述）、VeriRAG（ePrint 403，仅摘要）、zkRAG（反爬拦截，沿用 EXP-03A 的限制标注） |
| 证据纪律 | "未检出"不等于"文献中绝对不存在"；符号成本是结构性模型，不是已证明的渐近下界；不声称跨存储原子性、exactly-once 或形式化不可能性 |

主要来源：

- Compass 正文与附录：<https://www.usenix.org/conference/osdi25/presentation/zhu-jinhao>；ePrint 记录：<https://eprint.iacr.org/2024/1255>（ePrint PDF 在本环境被 Cloudflare 拦截，故使用 USENIX 官方 PDF，内容一致且含附录 A/B/C）。
- BiSON：<https://eprint.iacr.org/2026/1343>
- HERS：Compass §7 的一手评述，<https://arxiv.org/abs/2003.12197>
- Tiptoe：Compass §7 的一手评述，<https://people.csail.mit.edu/nickolai/papers/henzinger-tiptoe-eprint.pdf>
- VeriRAG：<https://eprint.iacr.org/2026/637>
- V3DB：<https://arxiv.org/abs/2603.03065>；Atlas：<https://arxiv.org/abs/2609.11841>；VIDA：<https://arxiv.org/abs/2611.16516>
- HONEYBEE：<https://arxiv.org/abs/2505.01538>；RACORN v2：<https://arxiv.org/abs/2607.00768>

---

## 1. 被正式接受的研究问题

经用户确认，PA-VFANN 不再研究泛化的 "Policy-Hiding Verifiable Filtered ANN"，只保留以下**三项不可删减的约束**：

- **C1（客户端隔离）**：用户不能读取未授权向量、敏感元数据或文档。
- **C2（服务端无知）**：服务端不能获知用户的 ACL/TTL 谓词及其搜索决策。
- **C3（恶意服务端可验证）**：恶意服务端不能通过遗漏、替换或操纵检索过程伪造结果；用户能验证过滤检索过程与结果的完整性。

三者的析取退化：去掉 C1 → Compass 客户端执行架构可能已经足够；去掉 C2 → 现有可验证 ANN 覆盖大部分问题；去掉 C3 → 退化为普通隐私检索。**只有合取成立才值得继续。**

本审计采用 EXP-03A 已固定的正确性分层，不重新包装：G1 为指定 ANN 算法的执行完整性，G2 为候选/发现集完整性，G3-exact 为全局授权精确 Top-K，G3-alg 为指定过滤 ANN 算法的输出。G1 ∧ G2 推不出 G3-exact（EXP-03A §5.2 的一维反例继续有效）。

---

## 2. Compass 原文核查（本轮主要基线）

### 2.1 一手事实（按章节定位）

**系统模型的原文定位（§3）**：

> "Each client owns a unique set of documents and an individual index, both stored on the server. Compass focuses on the case of a personal user searching their confidential data in the cloud, such as on Dropbox or iCloud. Data sharing could be implemented by adding shared data to each relevant user's index. We do not focus on data sharing and leave optimizations to future work."

**威胁模型的关键句（§3.1）**：

> "The server is untrusted and can be maliciously compromised... the server in Compass can deviate from the protocol arbitrarily."
>
> "The client, who owns the outsourced data, is trusted with its own documents. That is, the client may search and read the contents of these documents. However, the client cannot access or perform a search on the documents of other clients, even if the client colludes with the server."
>
> "Compass does not hide the type of operation... We do not protect against timing side-channel attacks... The server can roughly tell how large the data of each user is... but Compass does not reveal to the server the size of query results."

**客户端/服务端持有与计算（§4.1）**：

> "The client holds: ORAM-related data: a stash for overflow blocks, a position map that maps each block to a path, metadata for each bucket, and a cached treetop for the ORAM tree... HNSW-related data: metadata for HNSW search, including the dimension of the embeddings, the number of layers, and the degree bound M. If client-side caching is enabled, the client also stores the graph for the upper layers and the embeddings of nodes within these layers... Quantized hints... The server holds the ORAM tree in the Ring ORAM construction... each ORAM block corresponds to one node in the HNSW graph. The block corresponding to node x stores the embedding of x and its neighbor list... Each bucket has a tree of hashes for the integrity check."

由此可确定职责边界：

| 参与方 | 持有 | 实际执行 |
|---|---|---|
| 客户端 | ORAM stash、position map、bucket metadata、cached treetop；HNSW 维度/层数/度界；上层图与嵌入缓存；全部节点的 PQ 量化提示（ID → 量化嵌入）；解密密钥；Merkle 根/哈希路径 | 生成查询嵌入；用量化提示对邻居排序（DNF）；维护候选集/最近集；发起批量 ORAM 访问；解密**整块**并计算精确距离；执行 Alg.1 的队列更新与固定步数停止；验证 Merkle 路径；执行 lazy eviction |
| 服务端 | Ring ORAM 树，节点块为密文（嵌入 + 邻居表），桶内二级 Merkle 树与全局 Merkle 树 | 仅按客户端指令返回密文块、写回桶；可作任意偏离，但篡改/重放会被 Merkle 检查发现 |

**恶意保护（§4.8）与证明（§4.10、附录 C）**：

> "A malicious server can alter ciphertexts, rearrange the layout of ORAM buckets, perform replay attacks, or provide incorrect query responses. To protect integrity and freshness... we construct a Merkle tree on top of the ORAM tree."
>
> "The integrity guarantee of our protocol comes directly from the Merkle tree on top of ORAM... the attacker must respond correctly to all requests, with their only capability being to learn which items are accessed on the server during these requests."
>
> "Because the paths are chosen randomly, Compass does not leak the access pattern under the threat model described in §3.1."

Theorem 1 原文：在 CRHF 与 IND-CCA2 加密假设下，敌手在条件 (1)（区分查询）下优势不超过 1/2 + negligible，条件 (2)（输出不是明文 Compass 算法的正确执行）下为 negligible。**其安全游戏是"客户端诚实、服务端恶意"的两方模型**；客户端被明确信任可读取自己的全部文档。§4.11 另注明：只有在客户端本地磁盘完好、可恢复本地状态与日志时，才完全防御恶意服务端；若客户端磁盘也失败，无法检测服务端提供的陈旧状态。

**企业场景（§6.5）**：

> "Compass can be applied in the enterprise setting using the proxy model, where the company hosts an on-premise Compass client that enforces access control, while a remote server maintains the encrypted index and data."

这是 Compass 自己给出的多租户入口，但它把访问控制放在**可信本地 proxy**，且 proxy 必须能读取其强制访问的数据；这不是"服务端不知谓词 + 用户不可读未授权向量"的密码学解。

### 2.2 六个构造性问题的逐条回答

| # | 问题 | 回答（含具体构造或反例） |
|---|---|---|
| 1 | Compass 能否直接支持客户端本地 ACL 过滤？ | **能，但只在"过滤发生在解密之后"的意义上。** 构造：把属性 `attr_x` 与嵌入、邻居表一起放进 x 的 ORAM 块并纳入 Merkle 哈希；客户端解密后本地计算谓词并过滤。服务端观察到的仍是固定步数、固定批量大小的 ORAM 轨迹，谓词不进入服务端输入。这**不是**"过滤感知搜索"：谓词没有影响 DNF 排序、候选队列或停止条件。 |
| 2 | 若能，客户端会接触哪些未授权信息？ | 客户端会接触并解密 Alg.1 第 14 行 `batch_access(E3,t)` 返回的全部块，包括最终被过滤掉的节点的**完整嵌入、邻居表与属性**；PQ hints 本身也覆盖所有节点。对个人数据模型这是授权内的；对多租户模型直接违反 C1。 |
| 3 | 能否只让客户端获得授权向量而不泄露其他向量？ | **在 Compass 原块粒度下不能。** ORAM 块是不可分割的解密单位，客户端持有解密密钥。要做"只解密授权向量"，必须改成按节点/属性分离密钥，或引入策略控制的解密权释放（ABE/PRE/FE 类），或让服务端在秘密状态下计算后再按结果 releasing——这些都在 Compass 之外。 |
| 4 | ACL 元数据放 ORAM block 后，客户端能否安全执行过滤？ | **计算上能，安全上取决于客户端是否可信。** 必须固定块大小（按最大属性长度填充）、把属性纳入 Merkle 哈希、并保持批量大小 `t` 与步数 `n` 仅依赖公开参数。若客户端不可信（C1），客户端在过滤前已看到未授权属性与向量，故"安全执行"不成立。 |
| 5 | 若客户端不能读取未授权向量，本地搜索在哪一步失效？ | 精确失效点是 **Alg.1 第 6–18 行**：第 6 行从候选集取 top `ef_spec` 时没有谓词信息；第 9–13 行用 PQ hints 对邻居排序并选 `E3`，若 hints 含 ACL 位则客户端获得全图授权位（违反 C1），若不含则可能选中未授权节点；第 14–18 行解密并加入 `V/C/W`，必然接触未授权向量。换言之，"先取块再过滤"与 C1 不兼容，"先过滤再取块"要求谓词在取块前以秘密状态参与决策。 |
| 6 | 是否需要额外密码学机制，还是仅改数据布局与密钥管理？ | **条件式回答。** 若放弃 C1 或允许按用户物化索引（见 §3-A），只需数据布局 + 密钥隔离，Compass 基本覆盖；若坚持 C1 且坚持共享物理索引，则必须引入额外机制（秘密谓词求值、秘密队列更新、策略控制的解密权释放及相应恶意安全证明），**不是**单纯改布局。 |

**结论**：不能把"论文没有讨论 ACL"当成"无法支持 ACL"。Compass 确实可容纳 ACL 字段；真正的分界点是**过滤发生在解密之前还是之后**，以及**客户端是否被信任可读全索引**。这两个问题决定了它是已覆盖的架构 A，还是仍需机制的架构 B/C。

---

## 3. 三种系统架构的精确区分

### 3.1 架构 A：客户端执行（Compass 型）

**形态**：客户端执行 ANN 与授权过滤，服务端只存加密索引；ORAM 隐藏访问；Merkle 保证完整性。

| 判断项 | 结论 |
|---|---|
| 是否已由 Compass 覆盖？ | **在个人数据模型下是。** C2 由 ORAM + 固定批量轨迹保证；C3 由 Merkle + Theorem 1 条件 (2) 保证，证明对象是"正确执行 Compass 算法"。 |
| 多租户隔离能否靠密钥管理？ | **静态授权下基本能。** Compass §3 明确建议"把共享数据加入每个相关用户的索引"，即按用户物化逻辑索引；每用户密钥隔离 + 经数据所有者认证的根哈希，可阻止用户读未授权文档，也阻止恶意服务端把未授权块混入。§3.1 明言即使客户端与服务端合谋也不能读其他客户端文档。 |
| 客户端是否会看到未授权向量？ | 按用户物化索引时不会（它根本没有这些块）；单一共享索引 + 本地后过滤时**会**（见 §2.2 第 2、5 项）。 |
| 是否还有独立研究贡献？ | **没有新的密码学问题。** 剩余工作是索引物化/密钥分发/动态撤销的工程化。TTL 类动态授权若直接改索引成员关系，会向服务端泄露"哪个用户何时被授权"，这是已知的动态可搜索加密/隐藏更新问题，并非 PA-VFANN 独有，且可用 ORAM 更新与批量填充等现有手段处理。Compass §6.5 的企业 proxy 方案已给出同型路线，但以可信 proxy 为代价。 |

**关键限定**：如果"共享索引"只是效率偏好而不是安全约束，那么 A 已把 C1∧C2∧C3 合取解掉；若把"单一物理共享索引"设为硬约束，A 被排除，只能进入 B/C。

### 3.2 架构 B：服务端执行、秘密授权

**形态**：服务端持有图与向量并执行距离计算；谓词由客户端持有，以秘密共享/密文进入；匹配位、队列成员关系与停止条件均不能以明文出现在服务端。

逐项回答任务包：

- **服务端如何参与距离计算**：在安全计算中计算 `dist(q, x_i)`；若允许服务端看到访问节点，可在秘密共享上做算术电路并只向客户端揭示最终 Top-K；若要连访问模式也隐藏，需 ORAM/PIR 化块访问。
- **哪些状态必须秘密共享**：谓词输入 `P(a)`、每个候选的匹配位、候选队列成员与优先级、已访问集合（若过滤感知搜索会据此改变访问）、合法候选计数与停止信号。仅隐藏谓词字符串而让匹配位明文，服务端立即学到策略效果。
- **候选队列如何更新**：必须在秘密状态下做"匹配位 ∧ 距离比较 → 插入/丢弃"的无分支选择；每次更新至少一次秘密比较与一次秘密写。用普通优先队列会按秘密位分支，泄露；用 ORAM 化队列则每次更新 `O(log B)` 级 oblivious access。
- **停止条件如何处理**：不能按"找到第 K 个授权候选"直接停止（计数是秘密）。必须固定在公开上界 `E` 轮执行并填充，或把停止信号作为秘密位驱动无分支循环，此时轮数仍按最坏情况支付。这正是 §4.3 反例所指的瓶颈。
- **恶意服务端如何被检测**：需要证明服务端在每一轮发送了诚实份额并正确执行秘密状态转换（信息论 MAC 检查 / zkMPC / 可验证 MPC 的论证）。只对其套一个 SNARK 并不能隐藏谓词（EXP-03A §3.3 的铁律仍成立：`π=Prove(R,G,q,P)` 中 prover 一定知道自己使用的 `P`）。
- **如何避免 prover 自己知道秘密授权 witness**：不能让服务端担任以 `P` 为 witness 的证明者；必须让 `P` 以两方秘密输入进入联合计算，证明语句是"存在一个诚实参与的两方执行"，而不是"服务端知道并正确使用了 P"。

**独立贡献判定**：架构 B 在安全目标上确实区别于 Compass/Atlas/RACORN，但实现路径落在"MPC + ORAM + 可验证 MPC"的已知工具组合内。按用户给定的 GO 规则，"只是 Compass + ACL + SNARK/MPC 组合"不构成 GO。我们没有发现一个**新的原语或新的证明语句**使 B 不同于该组合；因此 B 是真实的需求缺口，但不是已被证明的独立密码学问题。

### 3.3 架构 C：混合执行（服务端公开搜索 + 客户端过滤与验证）

**形态**：服务端执行与谓词无关的向量搜索，返回候选元数据/密文；客户端用秘密谓词过滤并验证。

| 判断项 | 结论 |
|---|---|
| 是否退化为可验证 ANN + 客户端后过滤？ | **是。** 这相当于 EXP-03A §3.1 的 C1 路径；G1/G2 由 Atlas/VIDA/V3DB 类工具提供，过滤在客户端完成。 |
| 是否存在授权元数据泄露？ | 若候选属性以可解密明文返回，服务端虽然不知谓词，但客户端看到了未授权候选的元数据，违反 C1；若属性以客户端无密钥的密文返回，客户端无法完成过滤。二者必居其一，除非引入第三种密钥释放机制。 |
| 能否避免完整传输所有候选元数据？ | 不能在不让谓词影响选择的前提下避免：服务端不知道哪些候选与谓词相关，只能按固定预算返回全部候选元数据或全部密文。 |
| 能否证明返回结果相对于指定过滤 ANN 算法是完整的？ | **存在见证位置矛盾。** 服务端是不知 `P` 的证明者，无法证明涉及秘密谓词的过滤完整性；客户端知道 `P`，但为了验证全局完整性必须看到全库候选/属性，违反 C1。能证明的只有"未过滤轨迹的执行完整性"（G1/G2）和客户端对已收到候选的本地过滤正确性，即 G3-alg 的一个弱版本，**不是**"未遗漏任何授权候选"。 |

**独立贡献判定**：混合架构在 C1∧C2∧C3 下不成立，除非重新引入 B 的秘密联合计算；不能作为独立路线。

---

## 4. 成本结构分析（符号模型，非渐近下界）

符号：`N` 全库向量数，`N_u ≤ N` 单用户物化索引规模，`d` 向量维度，`d_q` PQ 提示维度，`E` 扩展/步数，`M` 平均度（Compass 中有度界），`a` 授权属性数，`B` 候选队列大小，`t = ef_spec · ef_n` 为 Compass 批量大小，`Z/S/A/L` 为 Ring ORAM 桶参数。

| 架构 | 主要客户端计算 | 通信 | 服务端/客户端存储 | 客户端内存 |
|---|---|---|---|---|
| 1. 客户端本地过滤（A） | `O(E·M·d_q)` 提示排序 + `O(E·t·d)` 精确距离 + `O(E·M·a)` 本地过滤 | `O(E·t·log N)` ORAM 路径，块大小 `Θ(d+M+s_attr)`，规模由公开参数固定 | 服务端 `O(N(d+M+s_attr))` 密文；用户物化索引时为 `O(N_u(...))` | position map `O(N)`，PQ hints `O(N·d_q)`，stash `O(E·t + ⌈E·t/A⌉·Z·L)` |
| 2. MPC 秘密谓词（B） | `O(a+B)` 输入份额与验证状态 | `O(E·M·(a+d+B))` 场元素，轮数约 `O(E)`；恶意安全追加 MAC/证明 | 服务端 `O(N(d+M+s_attr))` 秘密共享；客户端不存向量 | `O(a+B+d)` |
| 3. MPC + ORAM（B′） | 上述 + 秘密优先队列 `O(E·M·log B)` 比较/选择 | 上述 + `O(E·M·log N)` 隐蔽块访问；固定填充到最坏 `E` | 同 B，另有 ORAM 树 | `O(a+B+d+stash)` |
| 4. 固定轨迹 + 客户端过滤（C） | `O(E·M·a)` 仅对元数据过滤 | `O(E)` 固定候选元数据/密文 | 服务端 `O(N(...))`，客户端 `O(B)` | `O(B)` |

**关键观察**：在 B/B′ 中占主导的不是 `a` 次 ACL 比较，而是**秘密匹配位如何影响队列更新、停止条件与后续访问**。若这些决策以秘密位分支，服务端从分支/轮数/访问集合学到谓词效果；若改成无分支，就必须支付固定上界 `E` 的全部轮数与 ORAM 访问。这是结构性成本驱动因素，不是已证明的渐近下界；不能据此宣称 C2 不可行。

### 4.1 具体反例：星形图上的秘密谓词瓶颈

构造：根节点 `r` 连接 `N` 个叶子 `ℓ_1 … ℓ_N`；查询 `q` 与各叶子距离互异且按 `1-ε_i` 排序；策略 `P_1` 只授权 `ℓ_1`，`P_2` 只授权 `ℓ_2`；目标为返回第一个授权候选。

- 若允许过滤影响搜索：在 `P_1` 下访问 `r, ℓ_1`，在 `P_2` 下访问 `r, ℓ_2`。服务端从访问叶子身份直接区分两个谓词，**C2 失效**。
- 若用 ORAM 隐藏访问但让客户端在取块后判断匹配：客户端必须解密 `ℓ_i` 的属性/向量才能决定是否停止，取到未授权节点即接触未授权数据，**C1 失效**。
- 若让服务端在秘密状态下判断匹配并驱动停止：停止计数是秘密，循环必须固定到最坏 `E=N` 轮，或把停止信号编码为秘密位并用 oblivious select 维护队列；此时 ANN 的亚线性优势在该最坏例上消失。

这说明 C1∧C2 把成本压力从"ACL 比较"转移到"秘密控制流"，且该压力在稀疏/高选择率查询上最尖锐。这是构造性说明，不构成形式化下界，也不排除特定数据分布下的高效协议。

---

## 5. 相邻工作的最终定位

| 工作 | 一手定位 | 对 C1/C2/C3 的影响 |
|---|---|---|
| **Compass**（OSDI'25） | 恶意服务端 + ORAM + Merkle；客户端执行搜索、持有全索引量化提示；多用户共享留作未来；企业 proxy 执行访问控制 | C2/C3 在个人模型下已覆盖；C1 仅在按用户物化索引/可信 proxy 下成立。是本轮最强基线。 |
| **BiSON**（EuroS&P 2026, ePrint 2026/1343） | 摘要：隐藏数据与查询，DiskANN + 磁盘兼容 ORAM，十亿规模毫秒级；一手全文受限，二手材料将其归为诚实但好奇 | 说明"秘密向量搜索不可扩展"不能作为立论；摘要未见 ACL/过滤/恶意完整性，不覆盖三约束合取。 |
| **HERS**（TBIAS 2022） | Compass §7：FHE 线性扫描，开销高；半诚实 | 不覆盖秘密 ACL、不覆盖 C3。 |
| **Tiptoe**（SOSP 2023） | Compass §7：依赖服务端数据公开，"nor for malicious security, integrity protection, and sublinear search"；原文亦声明恶意服务端下不保证结果正确性 | 是查询隐私工作，不是秘密谓词过滤 ANN，也不是可验证过滤结果。 |
| **VeriRAG**（ePrint 2026/637） | 摘要：ZK 保护 RAG，ANNS 检索以避免穷举，验证 top-k 排序；一手全文受限 | 证明对象是近似 top-k 排序，不应解释为全局过滤 Top-K；摘要无 ACL。"ZK-IVFPQ/Top-m 聚类选择"未在一手摘要中核实，不作为本轮结论依据。 |
| **HONEYBEE**（SIGMOD 2026） | 动态分区优化 RBAC 向量查询；RBAC 表由可信数据库执行，服务端知道策略；无密码学证明 | 说明多租户授权场景不新；不覆盖 C2/C3。 |
| **Onyx** | 未找到与本审计对象可靠对应的原始论文；可核实的同名工作是 TEE 侧磁盘隐秘 ANN，完整性来自 attestation | 排除，不纳入结论。 |
| **Atlas / V3DB / VIDA / zkRAG** | C3 强先例：Atlas 证承诺索引上的 HNSW 执行；V3DB 证承诺快照上固定五步 IVF-PQ 语义；VIDA 证确定性 ANN 执行一致性；zkRAG 全文受限 | 均不覆盖秘密 ACL；查询多为公开；V3DB 明确是所选 lists 上的 top-k，不是全局精确 Top-K。 |
| **RACORN v2** | 过滤搜索策略（filter-first、ASF），无安全模型；E2 桥接与其高度接近 | 不能再把当前 E2 包装为新过滤 ANN 算法。 |

**综合**：没有一项工作同时满足 C1+C2+C3；但"空白"本身不是 GO 的充分理由——EXP-03A 的 HOLD 解除条件要求核查是否已有直接先例、以及成本是否在量级上明显不可行。本轮结果是：A 型先例（Compass）确实存在；B/C 型没有直接先例，但其实现路径被归约为已知原语组合与秘密控制流成本，而不是产生新的原语级问题。

---

## 6. 六项 GO 条件的逐项判定

| # | GO 条件 | 判定 | 理由 |
|---|---|---|---|
| 1 | 区别于 Compass 的客户端执行与 ORAM | **未满足（机制层面）** | 问题陈述上坚持 C1 与共享索引，但本轮没有给出任何非 Compass 型的具体机制；按用户物化索引时反而落入 Compass 覆盖范围。 |
| 2 | 区别于 Atlas/VIDA/V3DB 的普通可验证 ANN | **未满足** | 没有给出新的证明语句；C3 部分仍只能由现有可验证 ANN 工具提供。 |
| 3 | 区别于 RACORN 的过滤搜索策略 | **满足于陈述，未满足于贡献** | 我们不再把 E2 当算法创新；但也没有提出新的搜索策略。 |
| 4 | 解决多租户授权隔离，而非仅隐藏 ACL 字符串 | **未满足** | 现有可行隔离是"按用户物化索引 + 密钥隔离"（工程/密钥管理），共享物理索引下的隔离只剩秘密计算组合，没有新机制。 |
| 5 | 有明确可证明的安全性质 | **未满足** | 只有期望性质 C1/C2/C3 与 G1/G2/G3 分层，没有可证明的协议定理；§4.1 反例是构造性说明，不是不可能性定理。 |
| 6 | 有合理的最小实验可验证核心贡献 | **未满足** | 没有确定协议，无法定义最小实验；EXP-01/02/02A 的实验只覆盖轨迹/成本，不覆盖秘密谓词联合计算。 |

**组合禁令**：把 Compass + ACL + SNARK/MPC 拼接起来仍不满足上表任一项的实质要求，按用户明确规则不构成 GO。

---

## 7. 最终判决：**NO-GO（关闭 PA-VFANN）**

### 7.1 判决

**NO-GO**。PA-VFANN 作为独立密码学研究选题到此关闭，不再扩展该方向，不再通过增加密码学组件延长选题。

这不是"证明了 C1∧C2∧C3 不可能"，也不是"文献绝对不存在相关工作"；这是一个**研究组合决策**：在给出全部一手核查与符号成本后，本轮没有发现能支撑独立贡献的非组合机制，而所有可立即写出的构造都落入已覆盖路线或已知原语组合。

### 7.2 EXP-03A HOLD 解除条件的收口

1. **限定范围相邻文献核查**：已完成。Compass 一手全文核实，给出 6 个构造性问题的具体回答；BiSON/HERS/Tiptoe/VeriRAG/HONEYBEE/Onyx 与 Atlas/VIDA/V3DB/RACORN 逐一重新定位。结果：A 型（客户端执行）有强先例；B/C 型无直接先例，但也没有指向新原语。
2. **纸面成本结构**：已完成。符号成本与星形图反例表明瓶颈是秘密控制流（队列更新、停止条件、访问选择），而非 ACL 比较本身；没有得出"量级明显不可行"的结论，因此不以成本不可行性作为关闭理由。

按 EXP-03A §6.2 的原规则，两项补充验证本身没有触发 NO-GO；但本轮任务把 GO 门槛提高到六项实质条件，其中第 4–6 项全部未满足，且用户明确排除组合式 GO。因此 no-GO 的依据是**贡献不成立**，不是**可行性被否证**。

### 7.3 已确认的失败原因（避免重复路线）

1. G1/G2 单独作为贡献：Atlas、VIDA、V3DB、zkRAG 已覆盖。
2. 全局精确过滤 Top-K：证明者归属困难 + 全库扫描成本 + EXP-03A §5.2 反例。
3. 固定步数 HNSW + SNARK：Atlas 已覆盖其固定步数与有界集合技术。
4. E2 式桥接机制作为新过滤 ANN 算法：RACORN v2 的 ASF/Stride Sampling 已高度接近。
5. `π=Prove(R,G,q,P)` 中让服务端持 `P` 并声称谓词保密：概念错误（prover 必然知道自己的 witness）。
6. **本轮新增**：客户端执行 + 按用户物化索引 + 密钥隔离，已由 Compass（§3、§3.1、§6.5）覆盖静态授权下的 C1∧C2∧C3。
7. **本轮新增**：单一共享索引下要求服务端执行且不知谓词、客户端不可读未授权数据，现有可行路径均为 MPC + ORAM + 可验证计算的组合；见证位置矛盾使架构 C 无法单独成立。

### 7.4 若未来重新评估的硬门槛

只有在出现**非组合式**机制——例如一种使服务端可在不知道谓词的前提下执行秘密过滤、产生可验证的过滤完整性证明、且客户端无需解密未授权向量的新原语或新证明语句——并同时给出可证明安全性质与最小实验时，才可重新开启。单纯增加 MPC、ORAM、FHE 或 SNARK 组件不构成重启理由。

---

## 8. 审计元信息

| 项 | 值 |
|---|---|
| 基线 | `d18e7818f834cef77d92cd41ac1cbbdd3a713242` |
| 分支 | `exp03b-final-feasibility` |
| 报告正文 commit | `5bf3b95d01a1fc7616974ce65f718accd0a5fa4a` |
| 元数据 commit | 本提交（最终远端 HEAD 见本轮最终汇报） |
| 远端 HEAD（首次推送后核验） | `5bf3b95d01a1fc7616974ce65f718accd0a5fa4a`，与报告正文 commit 一致 |
| 工作区状态 | 首次提交推送后 `git status --short` 为空；元数据提交仅修改本报告，无其他改动 |

---

**一句话结论**：Compass 把"客户端执行 + ORAM 隐藏轨迹 + 恶意服务端完整性"推到了很强的位置，使架构 A 基本失去独立贡献；架构 B 的三约束合取真实存在，但可立即写出的构造都是已知原语组合，架构 C 存在见证位置矛盾。按六项 GO 条件，PA-VFANN 最终判决为 **NO-GO**，关闭该方向。
