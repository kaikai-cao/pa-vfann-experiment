# PA-VFANN-15 / EXP-03D：严格隐私下的 RAM-2PC 与专用队列同口径审计

> 本轮是**最终纸面审计**：不写代码、不改数据、不启动原型、不再扩展文献范围。目标只有一个：在**同一个过滤 ANN 状态机、同一份安全定义、同一套参数**下，判断"专用有界队列 + 批量认证"是否比通用恶意安全 RAM-2PC 有可核验优势。
>
> **本轮只新增本报告**，不修改 EXP-01、EXP-02、EXP-02A、EXP-03A、EXP-03B、EXP-03C 及任何代码、CSV 或实验数据。

---

## 0. 边界、基线与证据状态

| 项 | 内容 |
|---|---|
| 仓库 | `kaikai-cao/pa-vfann-experiment` |
| 基线 commit | `37b71e6479427d84c994ab3162884fdfc710d8db`（EXP-03C 最终 HEAD） |
| 本轮分支 | `exp03d-cost-semantics`（从基线新建，独立分支，不合并 main） |
| 唯一允许新增 | `docs/EXP-03D-COST-AND-SEMANTICS.md` |
| 证据纪律 | 只引用已取得的一手原文；拿不到全文的部分明确降级；不编造毫秒数；符号估算不冒充电路门数实测；"未检出"不等于"绝对不存在" |

### 0.1 Afshar 2015 证据状态更新（相对 EXP-03C 的修订）

- **上一轮状态**：EXP-03C §0 把 Afshar 2015 记为"一手全文受限，以摘要与作者报告幻灯片为据"。
- **本轮状态**：已取得 **EUROCRYPT 2015 会议正式版全文**（LNCS 9056, pp. 702–729；DOI `10.1007/978-3-662-46800-5_27`，Springer 官方 PDF），本报告所有 Afshar 引文均出自该正式版。
- **仍受限制的部分**：`https://eprint.iacr.org/2014/759.pdf` 及 archive/getfile 旧接口在本环境持续返回 403；会议版 §3.3 与 §4.3 明确写有 "the complete details are deferred to the full version [1]"。因此**用户提到的 full version Appendix D 无法逐字核验**，本报告不引用其原文，只使用会议版中已写明的模拟器概述、sharing 处理与效率分析。
- **章节编号映射**：用户按 ePrint full version 使用的 §4.3（安全证明）/ Appendix D（模拟器）/ §4.4（效率），在会议版对应 §3.3、§4.3 与 §3.4/§4.4；§2.1（ORAM 安全定义）与 §5.1（内部状态与 ORAM 状态分离）编号一致。

来源：

- Afshar, Hu, Mohassel, Rosulek, *How to Efficiently Evaluate RAM Programs with Malicious Security*, EUROCRYPT 2015, LNCS 9056, pp. 702–729. 正式版 PDF：<https://link.springer.com/content/pdf/10.1007/978-3-662-46800-5_27.pdf>；ePrint 题录：<https://eprint.iacr.org/2014/759>
- Zhang et al., *Efficient Actively Secure DPF and RAM-based 2PC with One-Bit Leakage*, IEEE S&P 2024. ePrint：<https://eprint.iacr.org/2024/426>；开放全文：<https://par.nsf.gov/servlets/purl/10544358>
- 前序边界：`docs/EXP-03B-FINAL-FEASIBILITY.md`、`docs/EXP-03C-MINIMAL-PROTOCOL.md`

### 0.2 本轮要纠正的 EXP-03C 错误

EXP-03C §6-C 与 §7 把"省去约 \(EM\log B\approx 10^4\) 次秘密 RAM 写"当作专用队列候选优势。该对比的隐含前提是：**通用 RAM-2PC 的队列必须放在 ORAM 中**。这个前提不成立（§1.4、§4.1）。纠正后，正确基线是"通用 RAM-2PC + 内部状态堆"，它本来就没有这些队列 ORAM 写。

---

## 1. Afshar 2015：安全性质与输出功能核查

### 1.1 六问逐条回答

**Q1：服务端对应恶意 \(P_1\) 时，其视图为什么不依赖客户端秘密输入？**

会议版 §2.1 的 ORAM 定义只针对访问序列：

> "Our constructions require a RAM program that hides only the memory access pattern, and we will use other techniques to hide the contents of memory."
>
> "Define I(Π,M,x1,x2) as the random variable denoting the sequence of values taken by the inst variable in RamEval(Π,M,x1,x2). Our precise notion of ORAM security for Π requires that there exist a simulator S such that, for all x1, x2 and initially empty M, the output S(1λ,z) is indistinguishable from I(Π,M,x1,x2)."

§3.3 的模拟器对恶意 \(P_1\) 明确写道：

> "S can extract P1's input x1 in timestep t = 1 by comparing the sent wire labels to the committed wire labels extracted in the offline phase. S can send x1 to the ideal functionality and receive the output z. Then S generates a simulated ORAM memory-access sequence."

即模拟器只拿到 \(z\) 就能生成与真实访问序列不可区分的视图。映射到本协议：\(S=P_1\)（garbler，持索引），\(C=P_2\)（evaluator，持 \(P\)）；**当输出只给 \(C\) 时，\(P_1\) 的视图中不应出现 \(z\)，因此可模拟性给出的唯一信息通道被切断**（输出适配本身仍需 §2 的改造与再证明）。

**Q2：s-wise XOR sharing 如何处理 selective-abort？**

§3.2 第 3(c) 步：

> "To prevent selective abort attacks, we must have P2 encode his input as n-wise independent shares, as above."

§3.4：

> "P2's input is split in an s-way secret share to assure input-dependent failure probabilities, leading to a total of sn OTs per timestep (where n is the number of random bits required by Π̃)."

机制含义：恶意 \(P_1\) 在 OT 中对 \(P_2\) 的某一输入位送一个合法、一个非法 wire label，只能通过"\(P_2\) 是否中止"探测该位；把每位拆成 \(s\) 个独立随机 share 后，任意少于 \(s\) 个 share 的线性组合仍与真实输入独立，选择性失败的探测概率优势被压到可忽略。

**Q3：哪些中止可能发生，哪些中止概率被证明与秘密输入无关？**

- 检查电路被改坏：诚实 \(P_2\) 立即中止；恶意 \(P_1\) 想让 eval 集合中多数电路错误而不被发现的概率可忽略（§4.1、§4.3）。
- Solder / GetInput1 / GetInputpub 作弊：§3.3 写 "S can abort just as an honest P2 would abort if P1 cheats in the Solder, GetInput1, or GetInputpub subprotocols."——模拟器用同分布的中止复现。
- GetInput2 选择性失败：§3.3 写 "S can also match (up to a negligible difference) the probability of an honest P2 aborting due to cheating in the GetInput2 subprotocol."——这是**与秘密输入无关性（up to negligible）**的直接依据。
- 输出真实性检查失败：§3.2 第 3(g) 步 \(P_1\) 校验 \(P_2\) 回送的 output wire labels；§4 第 (j) 步 \(P_1\) 用 \(w_j\) 解码并校验。

**边界**：论文证明的是"中止概率至多可忽略地依赖 \(P_2\) 输入"，不是"中止不发生"。DoS 型中止仍存在；本审计不把它写成零泄露，而是按标准恶意安全定义记为可忽略偏差。

**Q4：论文中的输出由谁得到？**

§3.2 第 3(g) 步：

> "Both parties decode the output instt = lsb(Y˜ ) ⊕ τ (inst(D(hdt))). ... If instt =(halt,z), then both parties halt with output z."

§4 第 (j) 步：

> "P2 opens the commitments to values w j and P1 uses them to decode the output instt."

**结论：两个协议都是双方得到输出 \(z\)**。论文没有默认提供单方输出。

**Q5：改成 \(F(x_S,x_C)\to(\bot,z_C)\) 需要改什么？**

至少四处：

1. **功能电路**：把 `halt` 指令中的 \(z\) 拆出，电路输出 `(inst_without_z, z ⊕ ρ)`，其中 \(\rho\) 是 \(C\) 独占的一次性随机掩码，作为 \(P_2\) 秘密输入进入 GetInput2（按 Q2 做 \(s\)-wise sharing）。
2. **解码信息**：只为 inst 输出线打开 \(\tau(\cdot)\)，不再把含 \(z\) 的线纳入 \(P_1\) 可解码部分；\(C\) 本地用 \(\rho\) 解出 \(z\)。
3. **真实性路径**：保留 \(P_2\) 对掩码输出 wire label 的承诺/回送，使 \(P_1\) 仍能做 authenticity 检查，但检查对象改为 \(z\oplus\rho\) 而非 \(z\)。
4. **安全证明**：恶意 \(P_1\) 的模拟器必须在不知道 \(z\) 的情况下生成视图；恶意 \(P_2\) 的模拟器要抽取 \(\rho\) 并对掩码输出做 equivocate；中止概率独立性要对新增的 \(\rho\) 输入重做。

**Q6：改输出功能是否影响原论文的恶意安全证明？**

分层判定：

| 层级 | 内容 | 判定 |
|---|---|---|
| 原论文已证明 | ORAM 访问序列模拟；cut-and-choose / 线程检查；选中止的 share 处理；输入一致性；输出真实性 | 会议版 §2.1、§3.3、§4.1、§4.3 有明确表述；可作为构件复用 |
| 标准组合可得 | 在电路输出上加 \(C\) 独占掩码；把 \(\rho\) 作为 \(P_2\) 秘密输入；\(P_1\) 只看掩码值 | 掩码一次一密本身标准，但**与本文输出真实性/承诺流程的组合不是自动的** |
| 需要重新证明 | \(P_1\) 视图与 \(z\) 独立；\(\rho\) 的中止独立性；equivocate 掩码输出；单方交付与凭证绑定 | **必须重写模拟器段**，不能引用原证明直接宣称闭合 |

**严禁**把"论文处理了 selective-abort"写成"我们的单方输出协议已满足严格策略隐私"：前者是原语性质，后者是改造后的新声明。

### 1.2 内部状态与 ORAM 的分离（决定成本的关键事实）

会议版引言：

> "instead of secret-sharing the internal state of the RAM program between the parties, we simply 're-use' the garbled wire labels from the output of one circuit into the input of the next circuit. These wire labels already inherit the required authenticity properties, so no oblivious transfers or consistency checks are needed."

§5.1：

> "the plain-RAM internal state could be kept separate from the ORAM-specific internal state, and only fed into the appropriate circuits."

§2.2 定义 `st(W)` 为内部状态线、`inst(W)` 为读写指令线、`block(W)` 为内存块线；状态通过 Solder 跨步传递（§3.2 第 3(c) 步）。

**因此**：小容量状态（含 \(B=100\) 的队列）可以作为 `st` 放在 next-instruction circuit 之间，用 wire labels 传递；只有索引读写才进入 ORAM。**状态不是免费的**——每步要为状态线付 solder 承诺打开与 wire-label 传递，成本 ∝ \(|st|\)；但它**不产生 ORAM 写**。这一区分是本轮判决的核心。

### 1.3 效率比的正确读法

§3.4：

> "For statistical security 2−40, our protocol without preprocessing achieves a ratio of s; our online-offline protocol has a pre-processing phase and achieves online ratio ∼ 2s/log T, where T is the total execution time of the RAM program."

§4.4：streaming 协议 "always require O(s) garbled circuit executions regardless of the size of the RAM computation"，且 \(S\approx 3s\) 个线程（\(s\) 典型取 40）。

这些是**相对半诚实执行同一程序的开销比**，不是绝对通信量，不能换算成毫秒或场元素。Zhang 2024 的 one-bit leakage 路线按用户既定标准排除，只作非严格隐私对照。

---

## 2. 单方输出适配审计

### 2.1 功能与目标

\[
F:\ (I,P,\mathrm{Cred};\ q,R_I,E)\ \longmapsto\ (\bot,\ z_C)
\]

其中 \(z_C\) 是固定 \(K\) 条授权结果的编码；服务端不得获得结果数量（固定为 \(K\)）、结果 ID 或内容。

### 2.2 必须独立成立的六项

| 项 | 处理方式 | 成本归属 | 状态 |
|---|---|---|---|
| 只有 \(C\) 得到结果 | §1.1-Q5 的掩码改造 | 每查询一次，与 \(E,M\) 无关 | **需重新证明**，非标准组合 |
| \(S\) 不知结果数量 | 固定 \(K\) 条，不足补哑记录 | 固定 \(K\cdot w_{out}\) | 可写，成本同 A/B/C |
| 哑记录不暴露授权集合大小 | 哑记录用 \((\bot,\bot,0)\) 的密文层编码，跨真实/哑不可区分 | 同上 | 可写，但属输出编码约束 |
| 中止不泄露 \(P\) | 复用 §1.1-Q3 的 share 处理，但对掩码输入 \(\rho\) 重做 | 随 \(s\) 与输入宽度 | **需重新证明** |
| 凭证与谓词绑定 | \(\mathrm{Cred}=\mathrm{Sign}_D(\mathrm{Commit}(P),\mathrm{ver},\exp,id_C)\)，MPC 内验签 | \(C_{\mathrm{cred}}\) 单列 | 可写；验签不是"顺带" |
| 索引版本绑定 | 查询携带 `ver`，承诺根随版本签名 | 常数 | 可写 |

### 2.3 判定

单方输出是**明确、可解决的协议适配缺口**，但它对三种队列实现是**共同成本**。即便补齐并重新证明，也不会改变 §4 的相对比较结论。因此它不构成本轮 HOLD 的理由。

---

## 3. 两种过滤 ANN 语义的完整状态转移

记号：节点记录 \(v_i=(id_i,\mathbf{x}_i,A_i,T_i,\mathcal N_i)\)；\(\mathcal N_i\) 按 `id` 升序枚举，固定 \(M\) 个位置，不足补哑邻居 `⊥`。优先队列条目 \(\omega=(\delta,id,\mu,\ell_{br})\)：

- \(\delta\)：定点距离键（小者优先）；
- \(id\)：稳定平局键（小者优先）；
- \(\mu\in\{0,1\}\)：授权匹配位；
- \(\ell_{br}\)：桥接深度（仅语义 B 使用）。

访问集合 \(V\) 用 \(N\) 位 bitmap；结果集 \(R\) 固定 \(K\) 条 \((\delta,id)\)；每条队列条目按固定字宽补齐。所有比较为无分支 `cmux/select`，\(\mu\) 与 \(\alpha\) 不以明文出现。

### 3.1 语义 A：filter-oblivious traversal + post-filter

\[
\text{key}(\omega)=(\delta,\ id),\qquad P\ \text{不参与队列键与扩展决策}.
\]

1. **初始化**：\(Q_0=\{(0,\text{entry},0,0)\}\)，\(V_0=\varnothing\)，\(R_0=\varnothing\)。
2. **每轮 \(t=1..E\)**：
   - 从 \(Q_{t-1}\) 取键最小条目 \(\omega^*\)；平局取最小 `id`；队列空则取哑条目（保持固定轮数）。
   - 若 \(id^*\in V_{t-1}\) 或 \(id^*=\bot\)，本轮只做队列压缩，不读取索引（消息长度仍按最大值填充）。
   - 否则置 \(V_t=V_{t-1}\cup\{id^*\}\)；按固定顺序读出 \(\mathcal N_{id^*}\) 的 \(M\) 个邻居（含哑邻居）。
   - 对每个非哑邻居 \(u\) 计算 \([\delta_u]\)，生成条目 \((\delta_u,u,\mu_u,0)\)，其中 \([\mu_u]=\mathsf{Pred}([A_u],[T_u],P)\)。
   - **未授权节点可以入队、也可以被展开**：\(\mu_u\) 不改变队列键，只控制是否把该条目写入 \(R\)；因此搜索轨迹与 \(P\) 无关。
   - 把 \(M\) 个新条目并入 \(Q_{t-1}\)；若 \(|Q|>B\)，按 \((\delta,id)\) 淘汰最大者（平局淘汰较大 `id`）。
   - 若 \(\mu^*=1\)，把 \((\delta^*,id^*)\) 按 \((\delta,id)\) 有序插入 \(R\)；若 \(|R|>K\) 淘汰最大者。
3. **终止**：固定 \(E\) 轮后输出 \(R_E\) 的 top-\(K\)；不足 \(K\) 条用哑记录补齐。
4. **隐私性质**：给定公开 \(q\)、\(R_I\) 与固定长度中止信号，服务端视图与 \(P\) 无关——**前提是**单方输出与严格隐私原语成立。

语义 A 与 EXP-01/02 的 E3 固定轨迹思想一致，但本轮是**纸面状态机定义**，不复用其实验数据，也不主张算法新颖性。

### 3.2 语义 B：predicate-aware traversal with bounded bridges（自定义状态机）

\[
\text{key}(\omega)=(-\mu,\ \delta,\ id),\qquad \ell_{br}\le \Delta\ (\Delta=1).
\]

- 排序键首先按 \(\mu=1\) 优先；\(\mu\) 保持秘密共享，比较在网络内完成。
- **桥接规则**：若 \(\mu^*=0\) 且 \(\ell_{br}^*=\Delta\)，该节点不得展开；若 \(\ell_{br}^*<\Delta\)，只允许作为桥接节点展开，其邻居条目置 \(\ell_{br}=\ell_{br}^*+1\)。所有未展开分支以哑条目占位，保证每轮固定读 \(M\) 块。
- **授权匹配位控制结果插入**：仅 \(\mu^*=1\) 的节点进入 \(R\)；桥接节点无论距离多小都不进 \(R\)。
- \(V\) 插入、平局、淘汰、\(E\) 轮终止、哑记录编码与语义 A 相同。
- **成本影响**：下一个扩展节点由秘密 \(\mu\) 决定，属于秘密控制流；在 RAM-2PC 中由 ORAM 隐藏地址、由 wire labels 隐藏状态，**不额外产生 ORAM 写**（队列仍在 `st` 中）。

**明确声明**：语义 B 只是借鉴过滤感知遍历思路的**自定义确定性状态机**，不是 ACORN/RACORN 的复现，不声称算法创新。语义 A 与语义 B 是两种不同算法，成本不得混用。

### 3.3 状态宽度（统一假设下的显式声明）

| 分量 | 宽度 | 说明 |
|---|---:|---|
| `id` | 14 bit（补齐 16 bit） | \(N=10^4<2^{14}\) |
| 坐标 | 16 bit 定点 | 平方距离累加 40 bit，\(\delta\) 键 40 bit |
| ACL 属性 | \(a\times 8\) bit | \(a\) 保留为符号 |
| TTL | 32 bit | |
| 邻接表 | \(M\times 14\) bit（补齐 224 bit） | 固定 \(M=16\) |
| 单节点记录 \(w\) | 2384 bit | \(16+2048+64+32+224\) |
| 队列条目 | 64 bit（补齐） | \(40+16+1+\) 填充 |
| \(Q\) 状态 | \(B\times64=6400\) bit | |
| \(V\) 状态 | \(N=10000\) bit | bitmap |
| \(R\) 状态 | \(K\times64=640\) bit | 补齐后 |
| \(st\) 合计（含控制线） | **约 9.2 kbit/步** | 上表之和 + 少量控制线 |

---

## 4. 三种队列实现：同功能、同安全的成本对照

### 4.1 A. 通用恶意安全 RAM-2PC + 内部状态堆（**正确基线**）

- 索引节点与邻接表放 ORAM；\(Q,V,R\) 放 RAM 程序 `st`，按 §1.2 用 wire labels 跨步传递。
- 每轮 next-instruction circuit：距离 \(M d=2048\) 个坐标乘加；谓词 \(M a\) 次秘密比较；堆插入 \(M\lceil\log_2 B\rceil=16\times7=112\) 次秘密比较。
- \(E=100\) 轮：队列比较约 **11,200** 次；**队列 ORAM 写 = 0**。
- 状态传递：约 \(9.2\ \mathrm{kbit}\times100=0.92\ \mathrm{Mbit}\) 的 wire-label 传递与 solder 承诺打开（不含 ORAM）。
- 索引 ORAM 读：\(EM=1600\) 次逻辑读；物理访问次数取决于所选 ORAM（树型 ORAM 每次约 \(\ell=14\) 个块，实例化固定后才能给绝对值）。
- 单方输出、认证、凭证：与 §5 相同。

### 4.2 B. 通用 RAM-2PC + ORAM 队列（仅对照）

- 只有当队列必须作为**跨会话共享、由服务端持有的内存数组**，或状态宽度超出实现预算时，才确实需要把 \(Q\) 放进 ORAM。
- 本轮固定为单次查询、\(B=100\)、\(Q\subseteq st\)，因此该实现是**人为劣化版**：在 A 的基础上额外产生约 11,200 次秘密 RAM 写及相应 ORAM 通信。
- EXP-03C 的"省去约 \(10^4\) 次 ORAM 写"实际是**C 对 B 的节省**，不是对 A 的节省。

### 4.3 C. 专用固定容量队列电路

- 与 A 使用同一 `st` 位置、同一输入输出、同一安全模型；差别仅是 next-instruction circuit 内的 comparator network。
- 合并已有 \(B=100\) 与新 \(M=16\) 条目：\(n=116\)，向上取 \(n'=128\)。
  - bitonic **merge**（两路已排序）比较器约 \((n'/2)\log_2 n'=64\times7=448\) 次/轮 → **44,800** 次总计。
  - bitonic **full sort** 比较器 \(n'\log n'(\log n'+1)/4=1792\) 次/轮 → **179,200** 次总计。
- 电路深度：merge 约 \(7\) 层比较器，full sort 约 \(28\) 层；A 的堆插入深度约 \(7\) 层但比较器数少。
- 状态传递成本：与 A **完全相同**（同一 \(st\) 宽度、同样 wire labels）。
- **C 相对 A 没有减少 ORAM 写（都是 0），也没有减少比较器（反而多 4–16 倍）**。

### 4.4 对照结论

| 对比 | ORAM 队列写 | 比较器（总） | \(st\) 传递 | 认证/凭证/输出 | 相对优势 |
|---|---:|---:|---|---|---|
| A 内部状态堆 | 0 | ≈11,200 | 相同 | 相同 | 基准 |
| B ORAM 队列 | ≈11,200 | ≈11,200 | 更大（队列入 RAM） | 相同 | 劣化 |
| C 专用队列电路 | 0 | 44,800–179,200 | 相同 | 相同 | **无优势，且更贵** |

**关键判定**：C 与 A 的差异只是"同一个 next-instruction circuit 的另一种写法"。这正是任务包 §7 列举的 NO-GO 条件之一。

---

## 5. 认证索引与单方输出的共同成本

### 5.1 两种认证入口

| 方案 | 初始化 | 每查询 | 摊销条件 |
|---|---|---|---|
| A：初始化时整索引装入 MPC/RAM 并验承诺 | \(N\cdot w\approx 23.84\) Mbit 数据；ORAM 准线性初始化（§5.2） | 0（若内存复用） | 论文 §5.2 明确支持把复用内存视为"reactive functionality"，一次初始化多次查询 |
| B：逐读认证路径 | 0 | \(EM\ell=1600\times14=22{,}400\) 次 MPC 内哈希 | 适合单次短查询 |
| 批处理向量/多项式承诺 opening | 需额外证明生成与验证电路 | 理论上可压缩路径数 | **无可引用的低成本构造，本轮不宣称优势** |

三种队列实现采用**同一种**认证入口，因此认证成本不构成差异化优势。注意路径验证必须在 MPC 内：交给 \(C\) 外部验证会让 \(C\) 看到 \(id_i\)，违反 C1（EXP-03C §4.2 已确立，本轮不改）。

### 5.2 单方输出与凭证

- 掩码改造（§2）是一次固定成本 \(C_{\mathrm{out}}\)，与 \(E,M,B\) 无关；A/B/C 相同。
- 凭证验签 \(C_{\mathrm{cred}}\) 每查询一次，与 ANN 状态机无关；A/B/C 相同。
- 结果固定 \(K\) 条 + 哑记录，输出长度固定；A/B/C 相同。

### 5.3 存储口径（论文原文，非估算）

- batching 协议 §3.4："For each bit of RAM memory, P1 must store the two wire labels ... P2 must store only a single wire label per memory bit." → \(P_1\approx47.7\) Mbit，\(P_2\approx23.8\) Mbit（仅索引数据位）。
- streaming 协议 §4.4："P1 must remember 2S wire labels per bit of memory ... P2 must remember between S and 2S wire labels per bit of memory"，\(S\approx3s=120\)（\(s=40\)）→ 数 Gbit 量级；这是**协议选型成本**，A/B/C 同担。

---

## 6. 统一参数成本表

固定：\(N=10^4,\ d=128,\ E=100,\ M=16,\ K=10,\ B=100,\ \ell=14,\ \Delta=1\)；安全参数 \(s=40\)（统计），计算安全参数 \(\kappa=128\)；\(a\) 保留为符号。记录宽度与状态宽度见 §3.3。

| # | 项目 | 公式 | 代入值 | A | B | C |
|---|---|---|---|---|---|---|
| 1 | 一次性索引初始化 | \(N\cdot w\) | ≈23.84 Mbit + ORAM 初始化 | 同 | 同 | 同 |
| 2 | RAM-2PC 预处理 | batching \(O(sT/\log T)\)；streaming \(S\approx3s\) 线程 | \(s=40,S\approx120\) | 同 | 同 | 同 |
| 3 | 每轮 next-instruction circuit | \(Md+Ma+\)队列比较 | 2048+16a+112 | 基准 | 同 | 2048+16a+448～1792 |
| 4 | 索引 ORAM 读 | \(EM\) | 1600 次逻辑读 | 同 | 同 | 同 |
| 5 | 队列更新 | A: \(EM\lceil\log_2B\rceil\)；B: 加 RAM 写；C: comparator network | 11,200 / +11,200 写 / 44,800–179,200 | 0 写 | 11,200 写 | 0 写 |
| 6 | ACL/TTL 谓词 | \(EMa\) | \(1600a\) | 同 | 同 | 同 |
| 7 | 向量距离 | \(EMd\) | 204,800 坐标乘加 | 同 | 同 | 同 |
| 8 | 索引认证（逐读入口） | \(EM\ell\) | 22,400 次 MPC 内哈希 | 同 | 同 | 同 |
| 9 | 凭证验证 | \(C_{\mathrm{cred}}\) | 每查询 1 次 | 同 | 同 | 同 |
| 10 | 单方输出 | \(K\cdot w_{out}+\)哑记录 | 固定 K 条 | 同 | 同 | 同 |
| 11 | 状态 wire-label 传递 | \(|st|\cdot E\) | ≈0.92 Mbit | 同 | 更大 | 同 |
| 12 | 恶意安全额外开销 | batching \(s\) / 在线 \(\sim2s/\log T\) | 相对半诚实同一程序 | 同 | 同 | 同 |

**网络主要组成**：预处理电路与承诺；每次逻辑读的 ORAM 消息；每步 solder 承诺打开与状态 wire labels；\(P_2\) 输入的 \(s\)-wise OT（batching 为每步 \(sn\) 个）；认证路径哈希；最终单方结果交付。

**明确不写**：不编造毫秒数；不把 \(s\)、\(2s/\log T\) 换算成场元素；不把构造性比较宣称为渐近下界。

---

## 7. 最终判决：**NO-GO**

### 7.1 判决

**NO-GO —— 关闭 PA-VFANN，不再扩展该方向。**

这不是"三约束被证明不可能"的声明，而是**同口径研究价值判定**：在相同状态机、相同严格策略隐私、相同恶意服务端与单方输出要求下，专用机制没有可核验优势。

### 7.2 对照任务包 §7 的 NO-GO 条件逐项

| NO-GO 条件 | 本轮结论 |
|---|---|
| 通用 RAM-2PC 把小队列放入内部状态后已达专用队列成本 | **成立**（§4.4：A 队列 ORAM 写 = 0，比较器比 C 少 4–16×） |
| 专用队列只是同一 next-instruction circuit 的另一种写法 | **成立**（§4.3：同一 \(st\)、同一输入输出，仅换 comparator network） |
| 批处理认证无可核验成本优势 | **成立**（§5.1：三种实现同入口；初始化复用入口使逐读成本归零，非 C 独有） |
| 单方输出/严格隐私额外成本抵消专用机制收益 | **成立**（§2、§5.2：共同固定成本，且需重新证明；无收益可抵消） |
| 无法给出公平、同口径的优势证明 | **成立**（纠正基线后差值为零或为负） |

五项全部命中。按用户写死的停止规则，本轮结束后不得追加第五种队列结构，也不再扩展文献搜索。

### 7.3 与 EXP-03C HOLD 的关系

EXP-03C 的 HOLD 建立在"队列 ORAM 写是主导项、专用网络可省掉它"的假设上。本轮通过 Afshar 会议正式版 §2.2/§3.2/§5.1 的一手原文确认该假设错误；HOLD 的唯一未决问题因此被**否定性解决**。这不是新增证据延长调研，而是按既定停止标准作出终局判定。

### 7.4 唯一遗留项（不改变判决）

单方输出适配（§2）仍需独立重写模拟器与安全证明，若未来出现真正非组合式的新原语需要复用此协议骨架，必须先把该项补完。但按本轮规则，它不构成继续 HOLD 的理由：即使补完，A 与 C 的成本关系仍不变。

---

## 8. 审计元信息

| 项 | 值 |
|---|---|
| 基线 | `37b71e6479427d84c994ab3162884fdfc710d8db` |
| 分支 | `exp03d-cost-semantics` |
| 报告正文 commit | `4cbd65d56afb70d105cc79ac443499e4bce74cd4` |
| 元数据 commit | 本提交（最终远端 HEAD 见本轮最终汇报） |
| 远端 HEAD（首次推送后核验） | `4cbd65d56afb70d105cc79ac443499e4bce74cd4`；`git push` 多次遇 SSL EOF / CONNECT 502，改用 GitHub REST API 上传 blob/tree/commit/ref 回退，远端 SHA 与本地 SHA 一致 |
| 工作区状态 | 报告提交与推送后 `git status --short` 为空；除本报告外无改动 |

---

**一句话结论**：Afshar 2015 会议正式版确认内部状态与 ORAM 内存分离，通用 RAM-2PC 本就能把 \(B=100\) 队列放在 `st` 中而不产生队列 ORAM 写；专用队列在同等条件下比较器更多、成本无优势，批处理认证与单方输出也只是共同成本。同口径比较命中任务包全部五项 NO-GO 条件，**PA-VFANN 关闭**。
