# EXP-03E：单方输出与策略无关视图审计

> 本轮**只审计安全性质与协议适配**：不做性能实验、不重新搜索文献、不追加队列结构、不声称创新。唯一问题是：Afshar 2015 的恶意安全 RAM-2PC 能否适配成"服务端不可区分的单方输出"协议。
>
> **本轮只新增本报告**，不修改代码、数据、已有报告及实验结果。本轮不重开 EXP-03D 的成本/创新判决；若本轮命题证明失败，Afshar 适配路线 NO-GO，PA-VFANN 维持关闭。

---

## 0. 边界、基线与证据状态

| 项 | 内容 |
|---|---|
| 新分支 | `exp03e-output-privacy-audit` |
| 基线 | `d03ef22c6aba29066fef0419c1982dc498096f8b`（EXP-03D 最终 HEAD） |
| 唯一新增 | `docs/EXP-03E-OUTPUT-PRIVACY-AUDIT.md` |
| 一手全文 | Afshar et al., EUROCRYPT 2015 会议正式版（LNCS 9056, pp.702–729；DOI `10.1007/978-3-662-46800-5_27`，Springer 官方 PDF） |
| 受限 | ePrint 2014/759 full version 在本环境持续 403；Appendix D 未逐字核验，不作引用 |
| 证据标记 | **[原文]** = 会议版明确写出；**[推导]** = 由协议流程严格推出；**[未确认]** = 需 full version 或实验才能定论 |

引文来源：<https://link.springer.com/content/pdf/10.1007/978-3-662-46800-5_27.pdf>；ePrint 题录：<https://eprint.iacr.org/2014/759>

---

## 1. Afshar 协议的角色与可见性审计

### 1.1 七问逐项

**Q1：P1、P2 分别持有什么输入？**

**[原文]** §3.2："during the first timestep, the parties will provide inp1 = x1 and inp2 = x2, while in subsequent timesteps they input their shares r1 and r2 of the RAM program's randomness. P2's input is further secret shared to prevent a selective failure attack on both x2 and his random input r2."

**[原文]** §3.2 第 3(c) 步：\(P_2\) 的输入 \(x_2\) 被拆成 \(n\)-wise independent shares（"To prevent selective abort attacks, we must have P2 encode his input as n-wise independent shares"）。

**[推导]** 因此 \(P_1\) 持 \(x_1\)，\(P_2\) 持 \(x_2\)；后续每步 \(P_2\) 的秘密输入是随机带 share，需 OT。

**Q2：哪一方持有或生成 ORAM memory 的 wire labels？**

**[原文]** §3.4："For each bit of RAM memory, P1 must store the two wire labels (and their decommitment info) corresponding to that bit, from the last write-time of that memory location. P2 must store only a single wire label per memory bit."

**[原文]** §5.3：\(P_1\) 可通过 PRF \(F_k(t,j,i,b)\) 生成内存 wire labels，但仍需记住每个位置的最后写入时间 \(t\)。

**[推导]** **\(P_1\) 生成并掌握内存每个位的两个 label 及其真值映射，因此 \(P_1\) 知道内存内容**；\(P_2\) 每内存位只有一个 label，且 \(\tau(\text{block})\) 未打开，所以 \(P_2\) 不能解码内存块内容。

**Q3：每轮 `inst` 的解码结果是什么？双方分别看到哪些字段？**

**[原文]** §2.2："we use st(W), inst(W) and block(W) to denote the outgoing internal state, output instruction (read/write/halt, and memory location), and outgoing memory data block."

**[原文]** §3.2 第 3(f) 步："P1 opens the commitment to GC(i) and to τ (inst(D(i)))."；第 3(g) 步："P2 sends Y˜ = inst(Yt) to P1. Both parties decode the output instt = lsb(Y˜ ) ⊕ τ (inst(D(hdt)))."

**[原文]** §4 第 (f) 步 streaming 版同样由 \(P_1\) 发送 \(\tau(\text{inst}(D(t,i)))\)；第 (h) 步 \(P_2\) 解码 \(inst_t\)；第 (j) 步 "P2 opens the commitments to values w j and P1 uses them to decode the output instt."

**[推导]** `inst` 字段 = 操作类型（read/write/halt）+ 内存地址。**\(P_1\) 与 \(P_2\) 每轮都解码完整的 `inst`，包括地址字段**。只有 `inst` 的 decoding information 被打开；`block` 的没有被打开，故 \(P_2\) 看不到块内容。

**Q4：哪一方知道逻辑地址、物理 ORAM 地址和 memory block？**

- **[推导]** \(\Pi\) 在 §3.2 被称为 "the ORAM program to be computed"，§5.1 明确 ORAM 构造负责"translating logical memory accesses to physical accesses"。故 `inst` 中的 memory location 是 \(\Pi\) 所操作内存（即 ORAM 内存）的地址，而非公开可解释的节点 `id`。**标为[推导]**，会议版未逐字写出"物理地址"四字。
- **[推导]** \(P_1\) 知道地址（Q3）且知道块内容（Q2）；\(P_2\) 知道地址但不知道块内容。
- **[未确认]** \(P_2\) 是否能从连续地址的非随机化实现中反推逻辑 `id`，取决于 ORAM 实例化；本报告不假设这一点自动成立或不成立。

**Q5：最终 `halt,z` 如何被双方解码？**

**[原文]** §3.2 第 3(g) 步："If instt =(halt,z), then both parties halt with output z."

**[原文]** §4 第 (j) 步 \(P_1\) 用 \(w_j\) 解码 \(inst_t\)；streaming 的最终 `halt,z` 同样落在 `inst` 输出线上。

**[推导]** **原协议双方都得到最终输出 \(z\)**，无任何单方输出语义。

**Q6：输出真实性检查依赖哪些双方可见的信息？**

**[原文]** §3.2 第 3(g) 步："P1 aborts if the claimed wire labels Y˜ do not equal the expected wire labels inst(D(hdt)) |∗ instt."；§4 第 (f)–(j) 步：`P_1` 用 \(c_{i,j,b}=\mathsf{Enc}_{v_{i,j,b}}(w_{t,j,b})\) 与 \(h_{i,j,b}=H(c_{i,j,b})\) 保护真实性，\(P_2\) 提交 \(w_j\)，\(P_1\) 解码并校验。

**[推导]** 真实性检查依赖：(a) `inst` 输出 wire labels 本身；(b) \(P_1\) 掌握的 \(\tau(\text{inst}(D))\) 与真实性密钥 \(w_{t,j,b}\)；(c) \(P_2\) 回送的 label/承诺。**注意：这是 \(P_1\) 对 \(P_2\) 的检查（防 \(P_2\) 谎报结果），不是客户端对服务端的完整性证明**；客户端侧完整性来自 cut-and-choose 与索引承诺，需单独写证明。

**Q7：两个腐败情形下的模拟器分别获得什么？**

**[原文]** §3.3（恶意 \(P_1\)）："S can extract P1's input x1 ... S can send x1 to the ideal functionality and receive the output z. Then S generates a simulated ORAM memory-access sequence."；模拟器按承诺判断电路正确性并复现 \(P_2\) 的中止概率（"match (up to a negligible difference) the probability of an honest P2 aborting due to cheating in the GetInput2 subprotocol"）。

**[原文]** §3.3（恶意 \(P_2\)）："S also extracts P2's input x2 from its select bits sent to Fot. It sends x2 to the ideal functionality and receives the output z. Then S generates a simulated ORAM memory-access sequence."；并对可见 wire label 与解码信息做 equivocate。

**[原文]** §4.3 给出 streaming 版对应模拟器，同样"receiving output z in return. S generates a simulated ORAM memory access pattern."

**[推导]** **两个模拟器都以 \(z\) 为输入**，这是原安全定义的泄露函数。映射到我们的目标（服务端不得见 \(z\) 或 \(P\)）时必须改写模拟器。

### 1.2 服务端角色映射

| 映射 | 可行性 | 主要问题 |
|---|---|---|
| **S = P1（garbler）** | **唯一合理映射** | \(P_1\) 生成内存 wire labels、掌握索引真值与 \(\tau\)；\(P_1\) 输入 \(x_1=I\) 很大，输入一致性开销按 \(|x_1|\) 计（§4.1 的 \(M\cdot(x_1\Vert r)\)），但 \(P_1\) 不经 OT 收输入（GetInput1 只开承诺），可控。\(P_1\) 每轮看到 `inst` 地址。 |
| S = P2（evaluator） | 排除 | \(P_2\) 的巨大索引输入须经 \(s\)-wise OT 与 GetInput2；且原协议 \(P_2\) 也解码 `inst` 与最终 \(z\)，服务端会直接看到结果，违反目标。 |

**结论：服务端必须映射为 \(P_1\)，客户端为 \(P_2\)。** 该映射下 \(P_1\) 每轮可见 `inst`（含 ORAM 地址）——这是策略无关视图审计的核心对象。

### 1.3 与 ORAM 定义的关系

**[原文]** §2.1："Our constructions require a RAM program that hides only the memory access pattern ... Define I(Π,M,x1,x2) as the random variable denoting the sequence of values taken by the inst variable ... there exist a simulator S such that ... the output S(1λ,z) is indistinguishable from I(Π,M,x1,x2)."

**[推导]** 原定义允许访问序列泄露"最终输出 \(z\) 所含信息"。我们的 \(\mathcal F\) 要求服务端泄露 \(L_S\) 中**不含 \(z\)**。因此不能直接引用 §2.1 的安全性；必须证明在固定执行结构下存在**不以 \(z\) 为输入**的轨迹模拟器。

---

## 2. 目标理想功能 \(\mathcal F_{\text{PA-VFANN}}\)

### 2.1 参与方与输入

- \(D\)（可信发布者）：发布 \((R_I,\mathrm{ver})\)，其中 \(R_I=H(\mathrm{root}_{MT}(I))\)，签名 \(\sigma_D=\mathrm{Sign}_D(R_I,\mathrm{ver},\mathrm{params})\)。
- \(S\)（不可信服务端）：持索引 \(I=\{v_i\}\)，\(v_i=(id_i,\mathbf{x}_i,A_i,T_i,\mathcal N_i)\)，附带 Merkle 路径。
- \(C\)（客户端）：持公开查询 \(q\)、秘密谓词 \(P\)、凭证 \(\mathrm{Cred}\)、公开预算 \(E\)。

### 2.2 功能步骤

1. **凭证验证**：\(\mathsf{VerifyCred}(\mathrm{Cred},P,\mathrm{ver},id_C)=1\)；失败则中止，不进入搜索。\(\mathrm{Cred}=\mathrm{Sign}_D(\mathrm{Commit}(P),\mathrm{ver},\exp,id_C)\)。
2. **索引绑定**：\(S\) 的索引输入必须在 MPC/RAM 内与 \(R_I\) 一致；伪造、替换、旧版本均导致中止（DoS，可检测）。
3. **检索**：\(z=\mathsf{FilteredANN}(I,q,P,E)\)，采用 EXP-03D §3.1 的**语义 A**（filter-oblivious traversal + post-filter）：队列键仅为 \((\delta,id)\)，\(P\) 只控制结果插入，不改变轨迹。固定 \(E=100\) 轮、每轮固定 \(M=16\) 个邻居读。
4. **输出**：\(\mathcal F:\ S\mapsto\bot,\ C\mapsto z\)；\(z\) 为固定 \(K=10\) 条，不足用哑记录补齐。服务端不获结果 ID、内容、真实数量。

### 2.3 允许泄露

\[
L_S=(R_I,\ \mathrm{ver},\ q,\ E,\ \text{public parameters}).
\]

**拒绝服务**：不能阻止恶意 \(S\) 停机/断连；允许可检测中止，但要求中止行为不泄露 \(P\)（由 \(P_2\) 输入的 \(s\)-wise sharing 与新增掩码输入的 sharing 保证）。不得声称协议阻止 DoS。

**不扩展**：\(q\) 公开，本轮不研究查询隐私。

---

## 3. 策略不可区分性游戏

### 3.1 两个世界

- World 0：\(C\) 输入 \(P_0\)；World 1：\(C\) 输入 \(P_1\)。
- 两世界的公开输入 \((R_I,\mathrm{ver},q,E,\text{params})\) 相同；凭证**公开格式**相同（签名格式、版本、有效期字段长度一致），但 \(\mathrm{Commit}(P_i)\) 本身不进入 \(L_S\)。
- 两谓词均通过 \(\mathsf{VerifyCred}\)。

### 3.2 服务端视图

\[
\mathrm{View}_S=(\text{messages},\ \mathrm{ORAM\_trace},\ \text{lengths},\ \text{timing\_class},\ \text{abort},\ \text{output}),
\]

其中 \(\mathrm{output}=\bot\)（服务端无输出），\(\text{timing\_class}\) 只按固定轮数/固定消息长度分类，不含微秒级时序。

**目标**：

\[
\mathrm{View}_S(P_0)\approx_c \mathrm{View}_S(P_1)\quad\text{且只允许 }L_S\text{ 中信息}.
\]

### 3.3 三类对手

| 对手 | 结论 | 理由 |
|---|---|---|
| 半诚实 \(S\) | 可由固定轨迹 + dummy read 达到 | 见 §4；\(P_1\) 每轮只见 `inst` 地址与固定长度消息 |
| 恶意 \(S\) | 需重证模拟器与中止独立性 | §1.1-Q7 的原模拟器以 \(z\) 为输入；§4.4 的中止处理需对新增掩码输入重做 |
| 恶意 \(C\) | 由凭证 + 输入一致性约束 | \(P_2\) 输入经 \(s\)-wise sharing；输入一致性由 §4.1 的 hiding hash 与 cut-and-choose 保证；谓词隐私不等于访问控制 |

**禁止**：把半诚实轨迹不可区分外推为恶意安全；本报告不作该外推。

---

## 4. 固定访问轨迹审计（命题 2 的核心）

### 4.1 七项检查（\(E=100,\ M=16,\ N_{\text{logical reads}}=1600\)）

| # | 情况 | 是否执行 dummy ORAM read | 判定 |
|---|---|---|---|
| 1 | 队列为空 | **必须执行**固定地址 dummy read | EXP-03D 未写明；本轮补齐为协议規則 |
| 2 | 遇到重复节点 | **必须执行** dummy read | 同上 |
| 3 | 未授权节点禁止展开（语义 B） | **必须执行** dummy read | 同上 |
| 4 | 有界桥接达深度上限（语义 B） | **必须执行** dummy read | 同上 |
| 5 | 每轮消息长度与 ORAM 操作数 | 固定为 \(M\) 读 + 固定电路 I/O | 可满足 |
| 6 | 数据相关提前终止 | **禁止**；固定 \(E\) 轮，halt 只在末轮 | 可满足 |
| 7 | `inst`、物理地址、消息、中止是否恢复 \(P\) 信息 | 语义 A 下逻辑序列与 \(P\) 无关；ORAM 随机化物理地址 | 需证明（§4.4） |

**[推导]** 固定消息长度 ≠ 固定 ORAM 轨迹；必须把"逻辑读序列"也固定（包括 dummy 地址），否则 ORAM 物理轨迹的分布会随逻辑序列变化。

### 4.2 逻辑地址与物理轨迹的区别

- 逻辑地址：程序请求访问的节点槽位；语义 A 下由 \(q,I\) 与固定规则决定，与 \(P\) 无关。
- 物理轨迹：ORAM 把逻辑读翻译为随机化物理访问；§2.1 只保证给定 \(z\) 时可模拟。
- **[推导]** 若逻辑序列本身与 \(P\) 无关，则物理轨迹的分布只取决于 ORAM 随机 tape 与固定索引 \(I\)，与 \(P\) 无关；此时模拟器不需要 \(z\)。

### 4.3 对命题 2 的直接回答

> **固定预算 + dummy ORAM access 能否隐藏策略相关轨迹？**

- **语义 A（filter-oblivious traversal + post-filter）：能。** 前提是上述七项 dummy read 规则全部写入状态机，且 `inst` 地址是 ORAM 物理地址而非可解释的节点 `id`。此时逻辑访问序列是 \((R_I,\mathrm{ver},q,E)\) 的确定函数，ORAM 物理轨迹与 \(P\) 独立，可构造不以 \(z\) 为输入的模拟器。
- **语义 B（predicate-aware traversal）：不能由此得到。** 下一个扩展节点由秘密匹配位 \(\mu\) 决定，逻辑序列本身随 \(P\) 变化；固定读次数只固定"数量"，不固定"序列"。§2.1 的模拟器仍可能需要 \(z\)，且 \(z\) 本身依赖 \(P\)，无法替换为 \(L_S\)。

**因此命题 2 的肯定答案只适用于语义 A。** 本轮不宣称语义 B 可满足。

### 4.4 需要显式证明的一点

**待证**：对固定逻辑读序列（1600 次，含 dummy）的 ORAM 程序，存在一个模拟器 \(\mathcal S_{\text{ORAM}}\) 使

\[
\{\mathrm{InstSeq}(\Pi,I,q,P)\}_{P}\equiv \{\mathcal S_{\text{ORAM}}(1^\lambda,R_I,\mathrm{ver},q,E)\},
\]

且 \(\mathcal S_{\text{ORAM}}\) 的输入中**没有 \(z\)**。这不是对 §2.1 的直接引用：§2.1 的定义只给出 \(\mathcal S(1^\lambda,z)\)，需要利用"逻辑序列固定"这一额外结构做混合论证。

---

## 5. 单方输出改造审计

不能只写 \(z\oplus\rho\) 就宣布安全。

| # | 问题 | 审计结论 |
|---|---|---|
| 1 | \(\rho\) 由谁生成、谁持有？ | 由 \(C\)（\(P_2\)）本地采样并持有；\(P_1\) 不持有真值 |
| 2 | \(\rho\) 是否在协议执行前被绑定？ | 必须在首轮作为 \(P_2\) 秘密输入进入电路，并按 \(s\)-wise sharing 经 GetInput2 输入，否则选择性失败可探测 \(\rho\) |
| 3 | 服务端能否从输出 wire labels / decoding info 恢复 \(\rho\) 或 \(z\)？ | \(P_1\) 可见 \(z\oplus\rho\)；因 \(\rho\) 均匀且只用于一次，该值独立于 \(z\)。**不得再向 \(P_1\) 打开 \(z\) 输出线的 \(\tau\)**（原 §3.2 3(g) 与 §4 (j) 必须改） |
| 4 | 客户端如何验证结果真实性？ | cut-and-choose 保证电路正确；索引承诺在 MPC 内验证保证数据正确；**不能依赖 \(P_1\) 对 \(P_2\) 的真实性检查**（那是反方向） |
| 5 | 恶意服务端能否给错结果且客户端通过？ | 若承诺内检查与 cut-and-choose 成立，则不能；需独立证明混合论证，不能引用 §3.3 模拟器代替 |
| 6 | 恶意服务端能否利用不同失败行为区分 \(P\)？ | 原 \(s\)-wise sharing 处理 \(P_2\) 输入 \(x_2\)；新增 \(\rho\) 输入必须同样分享并重证中止独立性 |
| 7 | 最终真实性检查是否仍需服务端获知 \(z\)？ | **不需要**：改为检查掩码输出 wire labels 的真实性（\(P_1\) 用自己掌握的 \(\tau\) 与 \(w\) 比较回送 label，得到 \(z\oplus\rho\)），不再解码 \(z\) |
| 8 | 需要修改哪些步骤与模拟器？ | 电路输出分层（`inst` 与 \(z\oplus\rho\) 分离）；§3.2 3(f)/3(g)、§4 (f)/(h)/(j) 的 \(\tau\) 打开范围；§3.3 与 §4.3 两个模拟器；新增 \(\rho\) 的分享与 equivocate |

**[推导]** 单方输出有明确构造路径，但属于**需重新证明**的类，不是标准组合的一次调用即可完成。

---

## 6. 可实现性判定、证明清单与真正缺口

### 6.1 可实现性判定

| 问题 | 判定 |
|---|---|
| Afshar 原协议能否直接满足目标？ | **否**：§3.2 3(g) 与 §4 (j) 双方解码 `inst` 与 \(z\)；§2.1 ORAM 模拟以 \(z\) 为输入 |
| 单方输出改造是否有明确构造路径？ | **有**：\(z\oplus\rho\) 掩码 + \(\tau\) 打开范围收缩 + 输出线分层（§5） |
| 固定访问预算能否去掉对 \(z\) 的轨迹泄露？ | **语义 A 可以**（§4.3），**语义 B 不可以** |
| 恶意服务端选择性中止能否被控制？ | 原 \(s\)-wise sharing 可复用，但必须把 \(\rho\) 一并纳入并重证（§5-6） |

### 6.2 最小安全证明清单（全部必须完成）

1. **轨迹模拟器**：构造 \(\mathcal S_{\text{ORAM}}(1^\lambda,L_S)\)，证明固定 1600 次读（含 dummy）的物理轨迹分布与 \(P\) 无关（§4.4）。
2. **恶意 \(P_1\) 模拟器**：在不知道 \(z\)、只知道 \(z\oplus\rho\) 的条件下复现服务端视图；中止概率与 \(P,\rho\) 仅可忽略相关。
3. **恶意 \(P_2\) 模拟器**：抽取 \(P\) 与 \(\rho\)，对掩码输出做 equivocate，保持输入一致性检查成立。
4. **单方输出混合论证**：从原协议到分层输出电路的连续混合，证明 \(P_1\) 视图中 \(z\) 被 \(\rho\) 遮蔽。
5. **索引绑定混合论证**：承诺检查失败即中止，且不产生"看起来成功的错误结果"。
6. **客户端结果真实性证明**：cut-and-choose + 承诺内检查 → \(C\) 接受的结果等于 \(\mathsf{FilteredANN}(I,q,P,E)\)（G3-alg，非全局精确 Top-K）。
7. **凭证绑定证明**：\(\mathrm{Cred}\) 绑定的 \(\mathrm{Commit}(P)\) 与 2PC 内实际使用的 \(P\) 为同一值；服务端只见固定公开格式。

### 6.3 真正的技术缺口

| 候选缺口 | 是否本轮核心 |
|---|---|
| 输出隐私 | 已定位且有构造路径（§5），不是不可修复障碍 |
| **访问轨迹隐私** | **是**：§2.1 模拟器依赖 \(z\)，必须靠固定逻辑序列 + dummy read 做新的混合论证；只对语义 A 成立 |
| 恶意输入一致性 | Afshar 已处理 \(x_2\)；新增 \(\rho\) 需重证，属证明工作量 |
| 索引完整性 | 可在 MPC 内检查，属证明工作量 |
| **上述性质的组合** | **是**：原协议的真实性检查是 \(P_1\) 对 \(P_2\)，客户端侧完整性必须另写；不能把各性质分别成立直接当成组合成立 |

**最准确的缺口表述**：不是"输出隐私做不到"，而是"**把 ORAM 轨迹模拟器的输入从 \(z\) 换成 \(L_S\)，并把 \(P_1\) 侧真实性检查改造成客户端可验证的完整性保证，这两步不能由 Afshar 原证明直接得到**"。

---

## 7. 判决

### 7.1 三个命题分开

| 命题 | 本轮状态 |
|---|---|
| Afshar 原协议满足单方输出要求 | **不成立**（双方解码 `inst` 与 \(z\)） |
| 固定预算 + dummy ORAM access 隐藏策略相关轨迹 | **语义 A 成立（有明确论证路径）；语义 B 不成立** |
| 完成适配形成论文创新 | **尚无证据**；本轮不主张创新 |

### 7.2 判决：**HOLD**（只剩一个待证明命题）

**待证明命题**：

> 在语义 A（filter-oblivious traversal + post-filter）、固定 \(E=100\) 轮 × \(M=16\) 次 dummy-inclusive ORAM read、且最终输出以客户端独占掩码 \(\rho\) 遮蔽的条件下，可构造服务端模拟器 \(\mathcal S(1^\lambda,L_S)\)，使恶意 \(P_1\) 的视图与 \(P\) 不可区分，同时客户端能验证结果等于指定过滤 ANN 状态机在承诺索引上的执行结果。

**为什么不是 GO**：没有可核验的差异化协议贡献；单方输出掩码与固定轨迹都属于标准组合，创新证据为零（命题 3）。

**为什么不是 NO-GO**：构造路径明确，七个证明项都是可写的技术工作，未发现不可修复障碍；对命题 2 已给出肯定的结构性答案（限语义 A）。

**停止规则**：本轮后不再增加队列方案、参数或文献搜索。若上述命题的证明尝试失败，判定 **Afshar 适配路线 NO-GO**；PA-VFANN 维持 EXP-03D 的关闭状态。本 HOLD 不是延长调研，而是把范围锁死在一个命题上。

**若结论涉及否定**：本轮没有否定 PA-VFANN 整体；否定的是"在语义 B 下用 Afshar 适配得到 \(L_S\)-only 服务端视图"这条路线，以及"Afshar 原协议直接使用"这一想法。

---

## 8. 审计元信息

| 项 | 值 |
|---|---|
| 基线 | `d03ef22c6aba29066fef0419c1982dc498096f8b` |
| 分支 | `exp03e-output-privacy-audit` |
| 报告正文 commit | 待提交 |
| 远端 HEAD | 待推送核验 |
| 工作区状态 | 提交前已确认除本报告外无改动 |

---

**一句话结论**：Afshar 原协议必须映射为 \(S=P_1/C=P_2\)，但双方每轮都解码含地址的 `inst`，ORAM 模拟器以 \(z\) 为输入，因此原协议直接违反目标；在语义 A + 1600 次 dummy-inclusive 固定读 + 掩码单方输出下，服务端视图可做到与 \(P\) 无关（命题 2 肯定），但需完成七项证明，尚无可主张的创新贡献。判决 **HOLD**，只剩§7.2 一个待证明命题。
