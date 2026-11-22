# EXP-03L：Afshar 2015 原始 Free-XOR 随机结构核验

> 项目：PA-VFANN-24（承接 EXP-03K 独立审阅意见）
> 目标：**唯一目标**——回到 Afshar 2015 会议版原文，判定 EXP-03K 的 \(T=\) 实例化是否属于论文原始构造，以及 \(D_{\rm cross}\) 是否适用于原始构造。不写代码、不改旧报告、不把局部结论扩展为完整协议安全性。
> 停止条件：原文足以确定随机结构 ⇒ 按原始构造重新核验，不再枚举人为实例化；原文未明确的关键关系 ⇒ 标记未决，既不作为论文缺陷也不作为安全证明；仅在发现真实跨位泄露时才讨论其对 batching 单方输出的影响。

---

## 0. 交付与证据状态

| 项 | 内容 |
| --- | --- |
| 基线 commit | `c0eedea15548ea75a6bfc539d98d31796d5b004b`（EXP-03K 最终 HEAD） |
| 分支 | `exp03l-afshar-freexor-instantiation` |
| 新增文件 | `docs/EXP-03L-AFSHAR-FREEXOR-INSTANTIATION.md`（本文，唯一新增） |
| 一手来源 | Arash Afshar, Zhangxiang Hu, Payman Mohassel, Mike Rosulek, *How to Efficiently Evaluate RAM Programs with Malicious Security*, EUROCRYPT 2015 Part I, LNCS 9056, pp. 702–729, DOI `10.1007/978-3-662-46800-5_27`；Springer 官方 PDF，810,112 字节，SHA-256 `92ccf8ab8014f4fd50eba8641369ee52fe5ae4dc5a349daad2466f9f5ee73d50`。本环境未找到此前保存的本地副本，本轮从官方 DOI 重新取得同一会议版。 |
| 引用格式 | 「PDF p.X（印刷页 Y）」，Y 取自页眉；公式按原文编号/位置定位 |
| 证据限制 | full version Appendix D 本环境仍受限（会议版 §3.3 明确「complete details deferred to full version」），本文不引用其逐字内容；凡会议版未写明的随机关系一律标记未决。 |

**一句话结论：EXP-03K 的 \(T=\) 不是 Afshar 原始构造允许的实例化，\(D_{\rm cross}\) 对原始构造不成立。** 原始 §2.2 把 \(\tau\) 定义为与 label 两列并列的独立列，并通过「互补 label 除 lsb 外不可预测」的性质从代数上排除 \(\tau=\Delta[k]\)；原始 §3.1 明确**放弃电路间共享 offset**（"forgoing common wire offsets \(w_0\oplus w_1\) between circuits"）。因此 EXP-03K 的多结果位泄露属于人为实例化的实现禁用警告，不是对 Afshar 原协议的攻击。

---

## 1. 任务一：从原文恢复真实随机结构

### 1.1 wire labels 与 translation bits（§2.2，PDF p.6，印刷页 707）

原文定义（逐项直录要点）：

- wire label 描述是 \(m\times 3\) 矩阵 \(W\)；\(W[i,0],W[i,1]\) 是 wire \(i\) 的两条 label；point-permute 要求 \(\operatorname{lsb}(W[i,b])=b\)（选择位即 lsb）。
- \(W[i,2]\) 是**单 bit translation bit**，使 \(W[i,W[i,2]]\) 编码 false；\(\tau(W)=W[1,2]\cdots W[m,2]\)。
- \(W|_v=(W[1,v_1],\dots,W[m,v_m])\)（按选择位取）；\(W|_{*}x:=W|_{x\oplus\tau(W)}\)（按真值取）。
- 解码：\(\operatorname{lsb}(Y)\oplus\tau(D)\)；部分解码：公开 \((\mu,\tau(D)\wedge\mu)\) 只泄露 \(\mu_i=1\) 的输出位。
- \(W\) 记为「满足上述 lsb 约束的 \(m\times 3\) 矩阵的**均匀**分布」；安全定义 \(\mathrm{Real}(f,x,D)\) / \(\mathrm{Sim}^{\mathcal S}(f,x,D)\) 对**所有 \(D\)** 成立，脚注 1 明确区分器**知道 \(D\)**（故知道完整的 \(\tau(D)\)）。

**直接后果**：\(\tau(W)\) 是与两条 label 列并列的、按 wire 独立的均匀 bit 列，原文**从未**把它写成 \(\Delta\) 的函数。这一点在 §2.2 的 Free-XOR 段落中被保留：Free-XOR 只把「两列 label」的分布改为「由秘密 \(\Delta\) 参数化、\(E[i,0]\oplus E[i,1]=\Delta\) 对所有 \(i\) 成立」，并明确断言「该分布满足上面用到的 \(W\) 的全部性质」（PDF p.7，印刷页 708）。

### 1.2 Free-XOR offset \(\Delta\) 的分配（§2.2 + §3.1）

| 问题 | 原文回答 | 依据 |
| --- | --- | --- |
| \(\Delta\) 是否逐 wire 独立？ | **否**。Free-XOR 下同一个 label 描述矩阵内 \(E[i,0]\oplus E[i,1]=\Delta\) 对所有 \(i\) 成立，即同一矩阵内 offset 跨 wire 恒定。 | §2.2，PDF p.7（印刷 708） |
| \(\Delta\) 是否全局跨电路共享？ | **否，原文明确放弃**。原文说 LEGO 原始工作 \([9,33]\) 用「a secret constant shared on all wires」的 Free-XOR，因此只有一个 solder 值；但这使 cut-and-choose 只能打开每门 4 种输入组合之一、只能以 1/4 概率发现错误门，**无法扩展到整电路 cut-and-choose**；「Hence our approach of **forgoing common wire offsets** \(w_0\oplus w_1\) **between circuits** and instead committing to the translation bits.」 | §3.1，PDF p.9（印刷 710） |
| 逐电路如何生成？ | 对每个电路 \(i\in\{1,\dots,N\}\)，P1 **独立**选择随机 \(E(i),D(i)\) 并对每个值分量承诺；随后计算并承诺 \(GC(i)\)。 | §3.2 step 1，PDF p.12（印刷 713） |
| Free-XOR 是否实际启用？ | **未决（非缺陷）**。原文说 garbling scheme 可用标准 PRF 实例化，或用 correlation-secure hash 等更强假设「to take advantage of free-XOR」（§3.3，PDF p.14，印刷 715）；脚注 3 说首步新增 XOR 门「When using the Free-XOR optimization」可事后加入。故 Free-XOR 是可选优化，但**一旦使用，offset 不得跨电路共享**。 | §3.3 + 脚注 3 |

因此三种人为分配中：\(G\)（全共享）与 \(E\)（eval 共享）被原文明确排除；\(P\)（逐电路独立）与原文相容。这纠正了 EXP-03J 把 \(G/E/P\) 并列为「论文可能采用的实例化」的写法。

### 1.3 check/eval 随机关系（§3.2 step 1–2，PDF p.12，印刷 713）

- step 1：所有 \(N=O(sT/\log T)\) 个电路的 \(E(i),D(i),GC(i)\) 均由 P1 逐个随机生成并分量承诺；无共享随机源的表述。
- step 2：P2 随机取一半 \(S_c\) 为 check；P1 对 \(i\in S_c\) 打开 \(E(i),D(i),GC(i)\)，P2 验证 \(GC(i)\in\mathrm{Garble}(\Pi,\tilde E(i),D(i))\)；其余 \(S_e\) 为 eval 电路。
- 因 \(\Delta\) 不跨电路共享，check 电路被完全打开（暴露其 label 与 \(\tau\)）**不泄露任何 eval 电路的 \(\Delta\) 或 \(\tau\)**。EXP-03J 的「情形 G：check 打开 ⇒ \(\Delta_h\) 公开」在原始构造中不成立。

### 1.4 Solder 公开量与内部量（§3.2，PDF pp.10–11，印刷 711–712）

`Solder(A,A')` 的原文步骤：

1. P1 通过 \(\mathcal F_{xcom}\) 打开 \(\tau(A)\oplus\tau(A')\)，P2 得到逐 wire 的 \(\tau_i=\tau(A)_i\oplus\tau(A')_i\)（即我们此前记的 \(\delta_j\) / \(\alpha_j\)）。
2. 对每个位置 \(i\) 与 \(b\in\{0,1\}\)，P1 打开 \(A[i,b]\oplus A'[i,\tau_i\oplus b]\)，P2 得到 \(\Delta[i,b]\)（两个 solder 差值）。
3. 返回 \(\Delta\)。

`MkBucket(B,hd)`：对每个 \(j\in B\setminus\{hd\}\) 计算 \(\Delta(hd\!\to\!j)=\mathrm{Solder}(E(hd),E(j))\)、\(\Delta(j\!\to\!hd)=\mathrm{Solder}(D(j),D(hd))\)，并置 \(\Delta(hd\!\to\!hd)=0\)；`Adjust(X,Δ)` 用 \(\tilde X[i]=X[i]\oplus\Delta[i,\operatorname{lsb}(X[i])]\)；`EvalBucket` 各电路调整、评估、调整回 head 空间后取 majority（PDF p.11，印刷 712）。

公开 / 内部边界：

| 量 | 原始构造中的状态 |
| --- | --- |
| \(\tau(A)\oplus\tau(A')\)（逐 wire） | **公开**（Solder 打开） |
| \(\Delta[i,0],\Delta[i,1]\)（两个 solder 差值） | **公开**（Solder 打开） |
| 单个 \(\tau(A)\)、\(\tau(A')\) | 不单独打开（仅 XOR） |
| Free-XOR offset \(\Delta\) 本身 | 秘密；check 打开只暴露 check 电路的随机量，不暴露 eval 的 |
| `Adjust`、`EvalBucket`、majority 中间结果 | 内部计算，不单独 decommit |
| \(\tau(\mathrm{inst}(D(i)))\) | 在 step 3(f) 打开（PDF p.13，印刷 714）；其余 \(\tau(D)\) 不开 |

### 1.5 模拟器可见性（§3.3，PDF p.14，印刷 715）

P2 被腐化时，模拟器发送随机 wire label（GetInput1/2/pub），在 Solder 中「equivocates soldering values chosen to map visible wire labels to their counterparts in other circuits, and chooses random soldering values for the non-visible wire labels」，并选择一组随机可见输出 label，再「equivocates on the decommitment to the decoding information \(\tau(\mathrm{inst}(D(i)))\), chosen so that the visible output wires will decode to the next simulated ORAM memory instruction」。即：\(\tau\) 在模拟中是**可自由选择的解码信息**，不是从 \(\Delta\) 派生的绑定量。这与我们的结果线 \(\mu=0\)（不开 \(\tau\)）适配方向相容，但原文模拟器以 \(z\) 为输入，完整无 \(z\) 模拟仍在我们此前的范围外。

### 1.6 原文未决项（不作论文缺陷、不作安全证明）

1. Free-XOR 是否实际启用（§3.3 表明为可选优化）。
2. 同一电路内 \(E\) 矩阵与 \(D\) 矩阵的 offset 是否为同一个 \(\Delta\)（§2.2 只对 \(E[i,0]\oplus E[i,1]\) 写等式）。
3. full version Appendix D 的具体随机采样细节（本环境受限，未逐字核验）。

三项均不影响下面关于 \(\tau\) 的判决。

---

## 2. 任务二：\(T=\) 是否符合原始构造——代数排除

设某 label 描述矩阵采用 Free-XOR：\(W[i,1]=W[i,0]\oplus\Delta\)，且由 point-permute 的 lsb 约束得 \(\operatorname{lsb}(\Delta)=1\)。设 \(k\) 为某个固定公开位，考察人为实例化 \(\tau_i=\Delta[k]\)。

**情形 \(k\neq\mathrm{lsb}\)**：安全定义对**所有** \(D\) 成立且区分器知道 \(D\)（§2.2 脚注 1），故知道 \(\tau_i=\Delta[k]\)。给定活动 label \(W[i,b]\)，互补 label 为
\[
W[i,b\oplus1]=W[i,b]\oplus\Delta,
\]
其第 \(k\) 位为
\[
\bigl(W[i,b\oplus1]\bigr)[k]=\bigl(W[i,b]\bigr)[k]\oplus\tau_i,
\]
**被完全确定**。但 §2.2 明确要求「adversary's view is independent of the complementary wire labels \(D|_{*}f(x)\), except possibly in their least significant bits (by the point-permute constraint)」。除去 lsb 后还有一个确定位，直接违反该性质。

**情形 \(k=\mathrm{lsb}\)**：\(\Delta[\mathrm{lsb}]=1\) 恒成立，故 \(\tau_i=1\) 为常量；而 \(W\) 是「满足 lsb 约束的 \(m\times3\) 矩阵的均匀分布式」，其 \(\tau_i\) 列必须均匀，常量列不属于该分布。

**结论**：
\[
\tau=\Delta[k]\ \text{不属于 §2.2 的分布族，故 } T= \text{ 不是 Afshar 原始构造的合法实例化。}
\]
这是代数排除，不是「Free-XOR 通常不会这样做」的口头判断。附带的 \(G/E\) 分配同样被 §3.1「forgoing common wire offsets between circuits」排除。

### 2.1 \(D_{\rm cross}\) 在原始构造下是否成立

原始构造下 \(\tau_c[i]\) 是 \(W\) 的独立均匀列，跨 wire 独立且独立于 \(\Delta\)。对同一电路的任意两条结果线 \(i,i'\)，P2 可见活动 label 的选择位
\[
s_i=\operatorname{lsb}(Y_c[i])=z_i\oplus\tau_c[i],\qquad
s_{i'}=\operatorname{lsb}(Y_c[i'])=z_{i'}\oplus\tau_c[i'],
\]
故
\[
s_i\oplus s_{i'}=z_i\oplus z_{i'}\oplus\tau_c[i]\oplus\tau_c[i'].
\]
因 \(\tau_c[i]\oplus\tau_c[i']\) 均匀且独立于 \(z\)，该 XOR 在 \(z\) 与 \(z\oplus e_1\) 下都是均匀分布，\(D_{\rm cross}\) 的检验「\(s_i\oplus s_{i'}=z_i\oplus z_{i'}\)」在两种假设下均以概率 \(1/2\) 成立，**优势为 0**。EXP-03K 中「\(\tau\) 跨所有 wire 共享同一个 \(\Delta[k]\)，故被消掉」的前提在原始构造中不成立。

### 2.2 排除它的具体原始约束

1. §2.2：\(\tau(W)\) 是 \(m\times3\) 矩阵中与 label 两列并列的独立列，\(W\) 为均匀分布式；Free-XOR 变体只改 label 两列并须保留 \(W\) 被用到的全部性质。
2. §2.2 安全性质：互补 label 除 lsb 外不可预测（在区分器知道 \(D\)、从而知道 \(\tau(D)\) 的前提下）；这从代数上排除 \(\tau=\Delta[k]\)（上式）。
3. §3.1：电路间放弃共享 offset，排除 \(G/E\)，并使 check 打开不泄露 eval 的 \(\Delta\)。

---

## 3. 任务三：EXP-03J / 03K 结论放回原始构造

| 原结论（出处） | 原始构造下处置 | 理由 |
| --- | --- | --- |
| (T⊥)+P 严格同分布采样器（03J §4） | **保留**（须补输入线 \(\alpha_j[i']\) 独立采样，03K §3.2） | \(P\) 与 §3.2 step 1 的逐电路独立随机相容 |
| (T⊥)+G / E 同分布采样器（03J §4） | **缩小**：仅为人为实例化的数学事实，非 Afshar 构造 | §3.1 明确放弃电路间共享 offset |
| \(D_1\)：G/E 两条 solder 差恒相等（03J §5.1） | **不适用于原始构造** | G/E 被排除 |
| \(D_2\)：P 下 solder 差 XOR \(=\Delta_j\oplus\Delta_h\)，跨位恒定（03J §5.1） | **保留**（仍否定 03I 的非 Free-XOR 采样器） | \(P\) 下同一矩阵内 offset 跨 wire 恒定（§2.2） |
| \(D_3\)：\(\tau=\Delta[k]\) 且 \(\Delta\) 公开（03J §5.2） | **保留为禁用实现，非论文攻击** | \(\tau=\Delta[k]\) 已被 §2.2 排除；\(\Delta\) 公开另违反「secret \(\Delta\)」 |
| garbling 重用区分器（03I §4.3） | **保留为禁用实现** | §3.2 step 1 逐电路独立随机；check 打开不共享 eval 随机量 |
| (T=)+Δ隐藏、单结果位 E/P 修正采样器（03K §2） | **缩小**：数学上正确，但不是原始构造所需的引理 | \(T=\) 被代数排除；\(E\) 另被 §3.1 排除 |
| \(D_{\rm cross}\) 多结果位区分器（03K §3.1） | **撤回作为对 Afshar 的攻击**；保留为「若实现者把 \(\tau\) 绑到 \(\Delta[k]\) 则禁用」的警告 | §2 的代数排除 + §2.1 优势为 0 |
| 局部引理 \(\mathcal V_{\rm solder}(0)\equiv\mathcal V_{\rm solder}(1)\) | **在原始 (T⊥)+P 下保留**（补 \(\alpha_j\) 后） | 03J §4 的采样器与原始随机结构相容 |
| 完整 batching 单方输出协议 | **不在本轮范围**，维持 HOLD | 用户停止条件：不证明完整协议安全性 |

---

## 4. 判决

| 判定对象 | 判决 |
| --- | --- |
| 原文是否足以确定决定性随机结构 | **足以确定**：\(\tau\) 为独立列、\(\Delta\) 不跨电路共享（§2.2、§3.1）；Free-XOR 是否启用等三项仍未决，但不影响本轮判决 |
| \(T=\) 是否为 Afshar 原始实例化 | **否定**（§2 代数排除） |
| \(D_{\rm cross}\) 是否适用于原始构造 | **否定**（§2.1 优势为 0） |
| 原始构造下 (T⊥)+P 局部引理 | **保留**（补 \(\alpha_j[i']\) 独立采样后，03J §4 成立） |
| 原始构造下 (T=) 局部引理 | **不适用**（实例化不存在）；03K 单结果位采样器仅作人为实例化数学记录 |
| EXP-03K 多结果位泄露的性质 | **实现禁用警告**，不是对原协议的攻击 |
| 完整 batching 单方输出协议 / PA-VFANN 核心问题 | **HOLD**，本轮不证明、不否定、不外推 |

按停止条件：原文已足以确定与 \(D_{\rm cross}\) 相关的随机结构，本轮**不再枚举人为实例化**。是否值得继续投入完整 transcript 模拟（ORAM 轨迹、`inst_ctrl`、索引初始化与回滚、位置绑定 membership、结果相关中止）留待用户决定。

---

## 5. 版本信息

| 项 | 内容 |
| --- | --- |
| 分支 | `exp03l-afshar-freexor-instantiation`（基线 `c0eedea`） |
| 新增文件 | `docs/EXP-03L-AFSHAR-FREEXOR-INSTANTIATION.md`（本文，唯一新增） |
| 一手来源 | Springer 官方会议版 PDF（SHA-256 见 §0）；未新增泛化 ZKP/MPC/ANN 文献 |
| 工作区状态 | 提交前确认除本报告外无改动；`git diff --check` 通过 |
| 推送状态 | 提交后核验远端 HEAD 与本地一致 |
