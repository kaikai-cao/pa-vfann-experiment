# PA-VFANN-12 / EXP-03A：可验证性缺口与秘密授权边界审计

**日期**：2026-11-22
**基线**：`exp02a-protocol-audit` @ `6e0b91cac68e2d14609708e9fdf36df2b93b1438`
**分支**：`exp03a-verifiability-audit`
**范围**：论文、定义与协议可行性审计；不实现密码学、不改实验代码与结果。

> 标注约定：【原文】= 已核对论文正文（给出章节/定理/算法号）；【受限】= 仅取得摘要或第三方正文转述；【分析】= 本审计的推导；【反例】= 构造的具体实例。

---

## 0. 执行摘要

【分析】本轮的核心结论不是"找到新方向"，而是**排除了三个看似自然但已被覆盖或不可行的创新点**，并把真正未决的问题收窄到一个需要更强证据才能判断的边界。

1. **G1（指定 ANN 算法执行完整性）与 G2（候选集完整性）已有强先例**：Atlas 证明承诺索引上的 HNSW 执行；VIDA 用重放直接覆盖"遗漏应访问节点"；V3DB 证明承诺快照上固定形状 IVF-PQ 语义；zkRAG 证明 HNSW 检索的服务一致性。把它们重新包装为创新点不成立。
2. **G3-exact（全局授权集合精确 Top-K）在本场景下代价过高**：现有可验证 ANN 工作均明确把正确性限定为"指定算法在承诺索引/快照上的输出"。要得到全局保证，要么全库扫描（失去 ANN 意义），要么依赖由已承诺数据可信产生且覆盖全库的距离下界（高维下通常不紧，且索引可能不覆盖全库）。构造的反例显示：**完整验证 G1+G2 的轨迹仍可输出非全局授权 Top-K**。
3. **真正的未覆盖点是"秘密授权谓词参与搜索 + 恶意服务端可验证"**，但必须澄清一个常见误读：普通 SNARK 的零知识性只保证 prover 的 witness 不泄露给 verifier，**不保证 prover 不知道自己的 witness**。让服务端在不知道谓词的前提下参与过滤感知搜索，需要两方秘密计算，而非给搜索套一层 SNARK。
4. **最终判决：HOLD**（详见第 6 节）：G1/G2 路径 NO-GO；G3-exact 路径 NO-GO（合理成本下不可实现）；C2 联合秘密过滤路径问题真实但创新性证据不足、成本未估算，需要一次明确且有限的补充验证。

---

## 1. G1 / G2 / G3 的形式化定义

### 1.1 公共设定

记数据库 `D = {(id_i, x_i, a_i)}_{i=1}^N`，`x_i ∈ R^d` 为向量，`a_i` 为属性（ACL、TTL 及其他参与授权的元数据）；索引 `I` 由服务端构造并承诺 `c = Commit(I)`；查询 `q`；授权谓词 `P` 由客户端秘密持有，`P(a_i) ∈ {0,1}`；搜索算法 `A`（确定性）及其参数（如 `ef, k`、扩展预算 `B`）。

算法执行产生：

- 访问/扩展轨迹 `T = (v_1, …, v_m)`；
- 发现（候选）集合 `C = Discover(T)`；
- 输出 `R = Output(T)`（长度 ≤ K 的 ID 列表）。

全局授权精确答案定义为 `R* = TopK_P(D, q) = argmin^{K}_{i: P(a_i)=1} ||x_i − q||²`。

### 1.2 G1：搜索执行完整性

| 项目 | 定义 |
|---|---|
| 安全游戏 | 挑战者给定 `(c, q, R, π)`；敌手控制服务端，目标是使验证者接受错误结果。 |
| 对手能力 | 可作任意多项式时间偏离：截断遍历、替换索引、伪造证明。 |
| 公共输入 | `c, q, A` 的描述与参数、`R`。 |
| 私有输入 | 服务端持有 `I`（以及轨迹 `T` 作为 witness）。 |
| 证明者 / 验证者 | 服务端 / 客户端。 |
| 证明语句 | `∃ I, T : c = Commit(I) ∧ T = Trace_A(I, q) ∧ R = Output(T)`。 |
| 接受条件 | `Verify(c, q, R, π) = 1`，且 `R` 等于 `A` 在 `I` 上的输出。 |
| 不满足反例 | 服务端用更便宜的索引 `I'` 或从 `T` 中途截断，返回某个"看起来合理"的 `R` 并通过验证。 |

【原文】Atlas 的语句正是这一形态：`R = HNSW-Search_{ef,k}(G,q) ∧ c = Commit(G)`（§4.1 "Our Approach"）。

### 1.3 G2：候选集完整性

| 项目 | 定义 |
|---|---|
| 安全游戏 | 在 G1 基础上，额外要求提交的候选集/轨迹承诺 `c_C` 与诚实执行一致。 |
| 对手能力 | 可遗漏、替换或伪造本应被发现的节点、邻居检查结果与距离值。 |
| 公共输入 | `c, q, c_C, A` 参数。 |
| 私有输入 | `I, T, C, {||x_v−q||²}_{v∈C}`。 |
| 证明者 / 验证者 | 服务端 / 客户端。 |
| 证明语句 | `∃ I,T,C : c=Commit(I) ∧ c_C=Commit(C) ∧ T=Trace_A(I,q) ∧ C=Discover(T) ∧ ∀v∈C: d_v=||x_v−q||²`。 |
| 接受条件 | 验证通过，且重放/约束检查确认 `C` 中没有缺失或伪造候选。 |
| 不满足反例 | 服务端跳过某个本应入队的节点 `v*`，`C` 缺项但 `R` 仍通过仅检查输出的验证。 |

【原文】VIDA 的重放论证直接覆盖此点："omitting a required node causes rejection, while deterministic replay yields the honest result"（§VII, Theorem 7.2 Proof Sketch）。

**G1 与 G2 的关系**：若 G1 的证明完整承诺并约束了整条轨迹与发现集，则 G2 是 G1 的子性质；若证明只约束最终输出的等式关系（例如只证明 `R` 等于某合法算法输出，而不绑定本次具体候选集），G2 需单独定义。两者都**不涉及**"未访问区域是否存在更近授权点"。

### 1.4 G3：过滤 Top-K 正确性（必须分成两个不同目标）

**G3-exact（全局精确）**

| 项目 | 定义 |
|---|---|
| 安全游戏 | 验证者接受 `R` 当且仅当 `R = TopK_P(D,q)`。 |
| 对手能力 | 服务端恶意；谓词 `P` 对服务端保密。 |
| 公共输入 | 全库承诺 `c_D, q, K`，（不能公开 `P`，否则谓词泄露）。 |
| 私有输入 | 客户端持有 `P`；服务端持有 `D, I`。 |
| 证明者 / 验证者 | **此处出现根本困难**：服务端不知道 `P`，无法证明关于 `P` 的语句；客户端知道 `P`，但通常不持有全库 `D`，无法自行计算全局 Top-K。 |
| 证明语句（理想化） | `∃ D : c_D = Commit(D) ∧ R = TopK_P(D,q)`，且 `P` 对 prover 隐藏。 |
| 接受条件 | 上式成立。 |
| 不满足反例 | 见第 5 节反例。 |

**G3-alg（指定过滤 ANN 算法的输出）**

把 `TopK_P` 换成明确定义的过滤 ANN 算法输出 `FilterTopK_A(P, I, q)`，并附带召回指标（如 Recall@10）。这是可形式化且可实现的，但必须明确写成"算法执行正确"，**不得**写成"全局过滤 Top-K 正确"。

【分析】严禁的推论：`G1 ∧ G2 ⇒ G3-exact` 不成立，因为验证覆盖的是 `I` 上已访问部分，未访问区域 `U = D \ Visited` 未被任何 G1/G2 语句排除。

---

## 2. 相关论文逐项核查

### 2.1 Atlas: Efficient Verifiable Semantic Search（arXiv:2609.11841v1, 2026-09-10）

【原文】§4.1 给出关系 `R = {( (c,q,R), G ) : R = HNSW-Search_{ef,k}(G,q) ∧ c = Commit(G)}`；§4 System Goals 定义 soundness 为 "a client receives the correct search result with respect to the committed index"，并明确 "We state soundness relative to the index rather than the database, as approximate search is inherently index-dependent"。§4 Threat Model 声明 "Either party may be corrupted by a malicious adversary"。§5.1.1 把多层贪心合并为固定步数 `Tg/Tb`，等价性见 Appendix §B.1 Theorem 4；§5.1.2 用单一有界集合替代两个队列，见 Lemma 1、Lemma 2、Theorem 3 与 Algorithm 3；§5.2/§5.2.3 把 trace 与分支标志作为 prover witness。

| 核查项 | 结论 | 依据 |
|---|---|---|
| 属性过滤 | 否 | 正文 §4–§5 未发现 |
| 秘密授权谓词 | 否 | 未发现 |
| 隐藏搜索轨迹 | 是（对 verifier） | §4 privacy；§5.2 trace 为 witness |
| 搜索过程完整 | 是 | §4.1 关系；§4 soundness |
| 候选集完整 | 是（蕴含于完整执行关系） | §4.1；无单独候选承诺定理 |
| 全局过滤 Top-K | 否 | §4 "relative to the index rather than the database" |
| 双方同时恶意 | 部分 | §4 "Either party may be corrupted"；合谋未单独建模 |

### 2.2 VIDA: Authenticated ANN Search in Outsourced Vector Databases（arXiv:2611.16516v1, 2026-11-12）

【原文】§II Definition 2.1 (Security) 给出理想游戏："A trusted party faithfully executes the deterministic ANN algorithm to obtain the ideal result RIdeal"，成功条件为 `Pr[(GameReal≠⊥)∧(GameReal≠GameIdeal)] ≤ negl(λ)`；§VII Theorem 7.2 给出重放论证；§II Threat Model 明确 "both the DO and the query client are honest" 而 SP 不可信；§IV-B2 与 §V-B 描述 `V_graph`（所有被 push 并计算距离的节点）与 `V_merkle`（实际展开的节点）；§VI / Algorithm 3 用 one-sided lower bound 剪枝以减少需要认证的精确距离。

| 核查项 | 结论 | 依据 |
|---|---|---|
| 属性过滤 | 否 | §IX 仅引用他人 metadata-filtered search |
| 秘密授权谓词 | 否 | 未发现 |
| 隐藏搜索轨迹 | **否** | §IV-B2/§V-B：客户端需重放搜索，轨迹用于验证 |
| 搜索过程完整 | 是 | §II Def 2.1；§VII Thm 7.2 |
| 候选集完整 | 是（重放覆盖遗漏） | §VII Thm 7.2 Proof Sketch |
| 全局过滤 Top-K | 否 | §II "we do not require the SP to return the exact result" |
| 双方同时恶意 | 否 | §II：DO 与查询客户端诚实 |

### 2.3 V3DB（arXiv:2603.03065v2, 2026-03-05）

【原文】§4.2 "Fixed-Shape Five-Step IVF-PQ Semantics" 给出 Centroid distances / Probe selection / ADC lookup / Candidate distances / Final top-k 五步（该语义**不是**编号 Algorithm；Algorithm 1/2 分别是 rebalancing 与配置搜索）；§3.1 给出 `(com,q) → payload list` 与 `Verify(com,q,list,π)` 接口及接受条件；§3.2 Scope 明确 "We treat q as a public embedding" 和 "we do not aim to provide access-pattern privacy … we make incorrect execution detectable whenever a proof is produced"；§1 明确 exact full scan 需编码 `Θ(ND)` 距离计算而不现实。

| 核查项 | 结论 | 依据 |
|---|---|---|
| 属性过滤 | 否 | 未发现 |
| 秘密授权谓词 | 否 | 未发现；且 `q` 是公开的（§3.2） |
| 隐藏搜索轨迹 | 是（对 verifier） | §3.1 "hides the snapshot contents and the execution trace from the verifier" |
| 搜索过程完整 | 是 | §3.1 接受条件 |
| 候选集完整 | 是（限于五步语义） | §4.2 |
| 全局过滤 Top-K | 否 | §1；§3.1 仅承诺快照上的 published semantics |
| 双方同时恶意 | 否 | §3.2 仅 malicious retrieval operator |

### 2.4 ACORN（arXiv:2403.04871v1, 2024-03-07）

【原文】§3.1 定义查询 `q=(x_q,p_q)`；§5 ACORN Overview 提出 predicate subgraph traversal；§5.1 Algorithm 2 `ACORN-SEARCH-LAYER` 的输入显式包含 `query predicate p_q`；§5.2 低选择性回退 pre-filtering；§5.3 ACORN-1 使用一跳/两跳扩展；§3.1/§7 以 recall@K 评估。

| 核查项 | 结论 | 依据 |
|---|---|---|
| 属性过滤 | **是** | §5.1 Algorithm 2 |
| 秘密授权谓词 | 否；`p_q` 是公开查询输入 | §3.1、§5.1 |
| 隐藏搜索轨迹 | 否 | 无隐私机制 |
| 搜索过程完整 | 否 | 无密码学可验证性 |
| 候选集完整 | 否 | 无 |
| 全局过滤 Top-K | 否 | §3.1/§7 近似 recall |
| 双方同时恶意 | 否 | 无威胁模型 |

### 2.5 RACORN（arXiv:2607.00768v2, 2026-11-06）

【原文】§II-C filter-first traversal：先做谓词判断再算距离；§IV-A Adaptive Search Fallback：每次扩展设目标 `τ=⌊bn⌋`，当 `|P|<τ` 且 `|W|<ef` 时从两跳失败节点 `F2` 抽样补足，"Each of them is measured against the query and pushed onto the candidate queue C, but none enters W. These are the bridges."；§IV-C Algorithm 1 lines 12–18 给出 `τ←⌊bn⌋`、`B←StrideSample(F2, τ−|P|)`、`push v onto C` / `not W`；§IV-B Stride Sampling 按位置取样且不算距离；§III-C 说明 predicate-agnostic 指"索引不含元数据、查询时评估"，非谓词保密；§VI 以 recall 0.95/0.97 评估。

| 核查项 | 结论 | 依据 |
|---|---|---|
| 属性过滤 | **是** | §II-C、§IV-C Algorithm 1 |
| 秘密授权谓词 | 否 | §III-C 明确 predicate-agnostic ≠ 隐藏 |
| 隐藏搜索轨迹 | 否 | 无隐私机制 |
| 搜索过程完整 | 否 | 无密码学可验证性 |
| 候选集完整 | 否 | 无 |
| 全局过滤 Top-K | 否 | §VI 近似 recall |
| 双方同时恶意 | 否 | 无威胁模型 |

【分析】**重要发现**：RACORN v2 的 ASF 桥接规则（失败节点进入候选队列但不进入结果队列、按每次扩展的预算补足、桥接节点参与扩展但不作为结果）与 EXP-02 的 E2 自定义桥接策略在机制层面高度接近。我们的 E2 用于隐私可观测性对照，不是性能创新主张；但这一重合进一步削弱"受控桥接机制本身具有新颖性"的说法。任何后续论文写作必须引用并区分 RACORN §IV-A/§IV-C。

### 2.6 zkRAG: Efficiently Proving RAG Retrieval in Zero Knowledge（IACR ePrint 2026/709, 2026-04-12）

【受限】ePrint PDF 被反爬挑战页拦截（`Just a moment...`），归档链接与短链同样不可用；已取得的是 ePrint 摘要、IACR News item 28208，以及 **Atlas 正文 §3 Related Work 对 zkRAG 的具体转述**。以下结论均标注来源强度，不对未取得全文的部分作强断言。

- 【原文·Atlas §3】zkRAG "directly encodes the HNSW search algorithm"；"preserves the layered graph structure and therefore relies on revealing the number of steps taken at every layer"；"verifies the two priority queues of beam search through a specialized PIOP for queue updates"。
- 【受限·摘要】service consistency = 结果与在固定、已承诺数据库与索引上执行约定 ANNS 一致，"revealing nothing beyond the outputs themselves"；prover 时间对 HNSW trace 长度线性；10⁶ 向量 / 128 维下单查询约 50 秒。
- 【分析】因此 zkRAG 覆盖 G1/G2，但对验证者**并非完全隐藏轨迹元信息**（每层步数可见，据 Atlas §3）。属性过滤与秘密谓词在可获取材料中未发现，**不作"不支持"的强断言**。

| 核查项 | 结论 | 依据强度 |
|---|---|---|
| 属性过滤 | 可获取材料中未发现（不断言不存在） | 受限 |
| 秘密授权谓词 | 可获取材料中未发现（不断言不存在） | 受限 |
| 隐藏搜索轨迹 | 部分：每层步数可见 | Atlas §3 正文转述 |
| 搜索过程完整 | 是 | 摘要 + Atlas §3 |
| 候选集完整 | 是（限于约定 ANNS） | 摘要 |
| 全局过滤 Top-K | 否 | 摘要："agreed ANNS … consistent" |
| 双方同时恶意 | 可获取材料中未发现 | 受限 |

### 2.7 对照表（合并）

| 工作 | 属性过滤 | 秘密谓词 | 隐藏轨迹 | G1 | G2 | G3-exact | 双方恶意 |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Atlas | ✗ | ✗ | ✓（对 verifier） | ✓ | ✓ | ✗ | 部分 |
| VIDA | ✗ | ✗ | ✗ | ✓ | ✓ | ✗ | ✗ |
| V3DB | ✗ | ✗ | ✓（对 verifier） | ✓ | ✓ | ✗ | ✗ |
| ACORN | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| RACORN | ✓ | ✗ | ✗ | ✗ | ✗ | ✗ | ✗ |
| zkRAG | 受限 | 受限 | 部分 | ✓ | ✓ | ✗ | 受限 |

【分析】表中不存在任何一行同时满足"属性过滤 + 秘密谓词 + G1/G2 可验证"。这是 HOLD 而非 NO-GO 的唯一依据；它同时是**证据不足**的区域，因为本轮未系统检索相邻隐私检索文献（Atlas §3 提到 Tiptoe、HERS、Compass、Onyx、VeriRAG，均与本题相关但本轮未逐篇核查）。

---

## 3. 两种秘密谓词架构审计

### 3.1 C1：客户端本地过滤

**协议形态**：服务端在固定入口与固定预算下执行**与 `P` 无关**的搜索 `A`，返回候选 `C`、距离与必要属性元数据；客户端本地计算 `P(a_v)`，从合法候选中选 Top-K。

| 问题 | 结论 |
|---|---|
| 谓词对服务端保密 | 是：服务端既不接收 `P`，也不计算/发送匹配位（EXP-02A §3 已核实模型 A/B/C 均无匹配位）。 |
| 服务端可观察 | `q`、搜索轨迹、候选 ID/距离、停止位置、消息大小与次数；**默认无反馈时看不到 Top-K ID**（EXP-02A 实测 `server_observable_leakage = 0`）。 |
| 客户端可验证 | 可附加 Atlas/zkRAG/VIDA 类证明验证 G1/G2；**无法验证 G3-exact**，因为证明语句不含 `P` 也不覆盖全库。 |
| 通信成本 | EXP-02A 实测：达标时模型 A 45.6–61.1 KB，模型 B 222.4–298.2 KiB，模型 C 311.5–417.7 KiB。 |
| 是否直接组合 | **是**：verifiable ANN（现成） + client-side post-filter（现成）。 |
| 创新强度 | 弱。组合没有产生新的证明语句；G1/G2 由现有工作提供，G3 仍未解决。 |

【分析】C1 还有一个语义断点：现有可验证 ANN 证明的是 `R = A(I,q)`，而 C1 最终输出是 `Filter_P(R)`。两者之间缺少一个形式化绑定——必须额外证明"客户端收到的候选集 `C` 完整且服务端发送的属性与承诺一致"，才能把 G1/G2 传递到过滤后结果。这可以做到，但仍是组合工作。

### 3.2 C2：联合秘密过滤

**协议形态**：客户端持有 `P` 与属性 `a_i`（或授权数据源持有），服务端持有图 `I` 与向量 `x_i`；过滤状态（匹配位、候选队列成员、停止条件）在两方间以秘密状态计算。

| 问题 | 结论 |
|---|---|
| 谁持有 ACL/TTL | 客户端或授权数据源；服务端不得持有明文谓词与匹配位。 |
| 谁持有索引/向量 | 服务端。 |
| 是否需要 DPF/ORAM | 若只隐藏谓词与匹配位、允许服务端看到访问节点，则不必需 ORAM，但需秘密状态的队列/优先队列更新（两方计算）；若要隐藏访问模式，则需 ORAM/PIR，成本极高。Atlas §3 将 Compass/Onyx 归为"private ANN"正交路线，且 Compass 的信任模型相反（客户端拥有数据库）。 |
| 队列/匹配位/停止条件如何保密 | 匹配位以秘密共享或密文存在；队列优先级（距离）与成员关系需在秘密状态下维护；停止条件依赖合法候选计数，也是秘密状态。 |
| 如何证明恶意服务端没跳过步骤 | 需要证明服务端在 MPC 子协议中发送了诚实份额并正确参与每一轮（如基于信息论 MAC 的检查或 zkMPC）。这不是"给 HNSW 套 SNARK"。 |
| SNARK + MPC 各证明什么 | MPC 保证谓词与匹配位对服务端不可见；SNARK/zkMPC 保证服务端按约定参与了状态转换。二者组合的语句是"存在一个诚实参与的两方执行"，不是"服务端知道并正确使用了 P"。 |
| 双方同时恶意 | 若客户端诚实（P 秘密）而服务端恶意，可用单方腐败的 MPC；若客户端也可能恶意（谎报谓词、拒绝参与），需更强安全模型，成本显著上升。六篇核查工作中没有一篇建模两方同时恶意 + 秘密谓词。 |
| 成本 | 每次扩展至少需要一次秘密谓词求值 + 一次秘密队列更新；证明开销随扩展数增长。以 EXP-02 预算 500/1000 与候选量级推算，通信轮数与每轮开销可能使成本不可接受，但本轮未做原语级估算。 |

### 3.3 必须澄清的密码学误读

【分析】若写成 `π = Prove(R, G, q, P)` 并令服务端担任 prover，则 `P` 是服务端 witness 的一部分。ZK 性质保证 verifier 学不到 `P`，**但 prover 当然知道自己使用的 witness**。因此该构造**不能**声称"授权谓词对服务端保密"。要同时满足"服务端不知道 P"与"服务端参与过滤感知搜索"，`P` 必须以两方秘密计算的方式进入，而不是作为 SNARK 的普通 witness。这是 C1 与 C2 的分水岭，也是本轮最重要的形式化修正。

---

## 4. 与原始研究问题的对照

原始目标包含两部分：（i）检索结果满足授权过滤；（ii）不能被恶意服务端随意遗漏或篡改；（iii）策略不泄露给服务端。

【分析】EXP-01/02/02A 已把（iii）的轨迹侧收窄到"E3 搜索计划与策略无关"，并量化了完整通信成本；本轮表明（ii）的 G1/G2 部分有强先例，而（i）的全局正确性（G3-exact）在 secret predicate 下没有可行证明者。因此原始问题目前呈现为：

- 可证明的部分：指定算法执行完整性 + 候选完整性（用现有工具）。
- 不可低成本证明的部分：全局授权 Top-K 正确性。
- 未决且有潜在价值的部分：谓词保密的过滤感知搜索（C2）。

---

## 5. G3 可行性审计与反例

### 5.1 三条路线

**路线 1：全库扫描。** 客户端或可信方遍历全部 `N` 条记录，计算 `P(a_i)` 与距离，选 Top-K。能保证 G3-exact，但成本 `O(Nd)` 且客户端必须持有全库与属性。外包给恶意服务端时，需证明完整扫描正确；V3DB §1 明确指出这需要编码 `Θ(ND)` 距离计算，电路不现实。结论：**正确但失去 ANN 意义**。

**路线 2：基于可信距离下界的剪枝。** 需要：对每个未访问区域 `U_j` 有 `LB(U_j) ≥ τ`（当前第 K 名距离），且 `LB` 由已承诺数据可信产生、覆盖全部授权点。

- 下界能否可信：几何下界（如 IVF 质心距离、量化误差界）可由承诺的质心/码本生成；VIDA §VI/Algorithm 3 已用 one-sided lower bound 做剪枝，但其用途是减少需要密码学认证的精确距离计算，**不是**排除未访问区域中的更近点。
- 谓词是否影响剪枝：几何下界对授权子集仍成立，但**覆盖性**依赖索引分区/图是否覆盖全库；若存在未被任何索引区域代表的数据点，下界无法排除它。
- 最坏成本：高维下界通常不紧（质心距离远小于真实距离），剪枝失效 → 退化全扫描。
- 不可避免的全扫描反例：见 5.2。

结论：**在承诺数据+可信下界下可实现，但没有普适的成本保证**。

**路线 3：固定预算 ANN 近似。** 只保证 G3-alg（指定过滤算法输出），必须明确定义算法与召回指标。EXP-02 的 E3 正是此类，Recall@10 ≈ 0.93–0.99，从不等于 1。结论：**可实现但不提供全局保证**。

### 5.2 反例：已验证轨迹仍非全局授权 Top-K

【反例】令 `d=1`，`q=0`，数据库三条记录：

| ID | 向量 x | 授权 P(a) | 到 q 距离 |
|---|---|---:|---:|
| a | 1.0 | 1 | 1.0 |
| b | 2.0 | 1 | 2.0 |
| c | 0.1 | 1 | 0.1 |

索引图 `I` 从入口 `a` 出发只有边 `a→b`；节点 `c` 在数据库与全库承诺 `c_D` 中，但不在图的任何可达组件中。固定扩展预算 `B=1`，算法 `A` 为 best-first 图搜索。

- 诚实执行轨迹 `T=(a,b)`，发现集 `C={a,b}`，输出 `R=Top2(C)={a,b}`。
- 服务端可以完全诚实地提供 G1 证明：`R = A(I,q)` 且 `c = Commit(I)`；也可提供 G2 证明：`C = Discover(T)`，两条距离 `1.0, 2.0` 均正确认证，没有遗漏图中任何应访问节点。
- 但全局授权精确答案是 `R* = Top2_P(D,q) = {c,a}`（距离 `0.1, 1.0`）。
- 因此 `G1 ∧ G2 = true` 而 `G3-exact = false`。

**失败原因**：G1/G2 的证明语句只约束"承诺索引上的指定执行"，从未包含 "`∀i∈D: i` 要么被访问，要么被可信下界排除"。验证者即使完全相信轨迹，也无从得知孤立节点 `c` 的存在与距离。

【分析】这个反例不是人为边缘情况：EXP-02 的 E3 在预算 100/500 下候选数约 5,694，未访问节点数千个，Recall@10 未达 1.0 的查询大量存在——它们正是本反例的真实规模版本。

---

## 6. 最终判决：HOLD

### 6.1 判决理由

| 候选创新点 | 判定 | 理由 |
|---|---|---|
| "证明服务端执行了约定 ANN 搜索" | **NO-GO** | Atlas §4.1、VIDA §II Def 2.1/§VII Thm 7.2、V3DB §3.1、zkRAG 摘要均已覆盖。 |
| "防止遗漏应访问候选" | **NO-GO** | VIDA 重放论证直接覆盖（§VII Thm 7.2）。 |
| "全局授权精确 Top-K + 秘密谓词" | **NO-GO（合理成本下）** | 证明者归属困难（服务端不知 P、客户端无全库）；全库扫描成本 `O(Nd)`；下界剪枝无普适保证；第 5.2 节反例。 |
| "秘密谓词参与过滤感知搜索，且恶意服务端可验证" | **HOLD** | 六篇核查工作中未发现同时覆盖该项者；但该空白可能是检索范围不足造成的假象，且没有任何成本估算支持其可行性。 |

**我不选择 GO**：因为 GO 要求"能给出具体安全定义、对手模型、协议设计和可执行实验"。本审计给出了前两者（第 1、3 节）和失败反例，但**没有**协议设计，也没有原语级成本估算；且未系统检索 Tiptoe / HERS / Compass / Onyx / VeriRAG 等相邻工作，无权断言不存在先例。

**我不选择 NO-GO（整体）**：因为 C2 确实不在六篇工作的覆盖范围内，且原始研究问题的一部分（秘密谓词参与搜索）尚未被证伪。整体 NO-GO 需要更完整的相邻文献检索与一次纸面成本否定。

### 6.2 HOLD 的解除条件（明确且有限的补充验证）

不实现代码、不引入新密码学组件，只做两件事：

1. **限定范围的相邻文献核查**：只查"谓词/属性隐藏的过滤检索 + 可验证执行"这一类（含 ABE-based filtered retrieval、PIR/ORAM-based filtered search、secure hybrid search、private set intersection + ANN、上述 Atlas §3 提到的 Tiptoe/HERS/Compass/Onyx/VeriRAG）。目标：确认 C2 是否已有直接先例。若已有 → 整体 NO-GO，按 6.3 记录失败原因并关闭。
2. **纸面成本下界估算**：按 EXP-02 的每查询扩展数（100–1000）与候选规模（约 2,000–9,500），用公开 MPC / zkMPC 原语成本估算"每次扩展一次秘密谓词求值 + 一次秘密队列更新"的通信量与轮数。目标：判断 C2 是否在量级上明显不可行。若不可行 → 整体 NO-GO。

若两项均通过，才进入 GO，届时才需要给出最小协议结构与最小可验证实验。

### 6.3 若最终 NO-GO，已确认的失败原因（避免重复路线）

1. G1/G2 单独作为贡献：被 Atlas / VIDA / V3DB / zkRAG 覆盖。
2. E2 式桥接机制作为贡献：RACORN v2 §IV-A/§IV-C 已有高度接近的 ASF + Stride Sampling。
3. "固定步数 HNSW + SNARK"作为贡献：Atlas §5.1.1/§5.1.2 已用固定步数与有界集合解决，且有等价性定理（Theorem 3/4）。
4. "全局精确过滤 Top-K"作为保证：证明者归属困难 + 全库扫描成本 + 第 5.2 反例。
5. "普通 SNARK + 秘密 P 作为 prover witness"声称谓词对服务端保密：概念错误，见 3.3。

---

## 7. 本轮未解决问题

1. zkRAG 全文未取得（反爬拦截），其属性过滤/秘密谓词/恶意客户端建模只能标注"可获取材料中未发现"。
2. 未系统核查相邻隐私检索文献（见 6.2 第 1 项）。
3. C2 的原语级成本未估算（见 6.2 第 2 项）。
4. "可验证搜索完整性"的观察者与证明目标仍未由研究负责人明确定义；本审计按第 1 节给出候选定义，不替代最终选择。
5. 本轮未运行任何实验、未修改任何实验文件。

---

## 8. 参考文献（含定位）

1. **Atlas: Efficient Verifiable Semantic Search**, arXiv:2609.11841v1 (2026-09-10). 定位：§4.1 证明关系；§4 System Goals / Threat Model；§5.1.1 + Appendix B.1 Theorem 4；§5.1.2 Lemma 1/2, Theorem 3, Algorithm 3；§5.2/§5.2.3；§3 Related Work（zkRAG 对比）。
2. **Authenticated Approximate Nearest Neighbor Search in Outsourced Vector Databases (VIDA)**, arXiv:2611.16516v1 (2026-11-12). 定位：§II Definition 2.1、§II Threat Model；§IV-B2、§V-A/B；§VI / Algorithm 3；§VII Theorem 7.2。
3. **V3DB: Audit-on-Demand Zero-Knowledge Proofs for Verifiable Vector Search over Committed Snapshots**, arXiv:2603.03065v2 (2026-03-05). 定位：§1；§3.1、§3.2；§4.2 五步语义。
4. **ACORN: Performant and Predicate-Agnostic Search Over Vector Embeddings and Structured Data**, arXiv:2403.04871v1 (2024-03-07). 定位：§3.1；§5.1 Algorithm 2；§5.2、§5.3；§7。
5. **RACORN: Robust Predicate-Agnostic Filtered Vector Search under Extreme Selectivity**, arXiv:2607.00768v2 (2026-11-06). 定位：§II-C；§III-C；§IV-A、§IV-B、§IV-C Algorithm 1 lines 1–18；§VI。
6. **zkRAG: Efficiently Proving RAG Retrieval in Zero Knowledge**, IACR ePrint 2026/709 (2026-04-12). 定位：摘要；IACR News item 28208；Atlas §3 Related Work 正文转述。全文因反爬拦截未取得，已在正文标注受限范围。
7. 内部材料：`exp02/REPORT.md`（固定入口、惰性距离、E1/E2/E3 成本）；`exp02a/REPORT.md`（观察者模型、完整通信成本、达标口径）。

---

## 9. 一句话结论

**G1/G2 已被现有工作覆盖，G3-exact 在秘密谓词下缺乏可行证明者且成本不可接受；唯一可能剩下的 C2 问题证据不足，因此判决 HOLD，先做一次有限的相邻文献核查与纸面成本下界估算，再决定进入最小协议原型还是关闭 PA-VFANN。**
