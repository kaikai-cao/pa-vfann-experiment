# EXP-03E 修正审计：角色映射、wire-label 语义与单方输出

## 元信息

| 项目 | 值 |
| --- | --- |
| 任务 | PA-VFANN-17 / EXP-03E 修正审计（不扩展文献、不设计新队列） |
| 仓库 | `kaikai-cao/pa-vfann-experiment` |
| 基线 | `b59fb05f292a8130043283d960601c3248cee861` |
| 本轮分支 | `exp03e-role-mapping-correction` |
| 唯一新增文件 | `docs/EXP-03E-CORRECTION-AUDIT.md` |
| 一手依据 | Afshar, Hu, Mohassel, Rosulek, *How to Efficiently Evaluate RAM Programs with Malicious Security*, EUROCRYPT 2015, LNCS 9056, pp. 702–729, DOI `10.1007/978-3-662-46800-5_27`（Springer 官方会议版 PDF；ePrint `2014/759.pdf` 在本环境仍 403，full version Appendix D 未逐字核验） |
| 与前轮关系 | **EXP-03E 结论不予验收**；本报告替代其角色排除论证与单方输出结论，不修改原报告 |

## 0. 本轮范围与结论摘要

用户独立审查指出，EXP-03E 在一个基础问题上出错：把"持有两个 wire label"误当作"知道内存内容"，并据此排除了 \(S=P_2, C=P_1\) 映射。**该批评成立。** 本轮只做修正审计：

1. 承认并逐条纠正上轮错误（§1）；
2. 从会议版原文重审角色、wire-label 可见性与输出真实性方向（§2–§5）；
3. 在 \(S=P_2, C=P_1\) 下重写单方输出与模拟器中止独立性（§6）；
4. 把"语义 A 轨迹独立性"从肯定结论降为**有条件的结构性论证**，给出唯一待证明命题与停止规则（§7–§10）。

**修正判决：HOLD（保留一个明确待证明命题）。** 不再声称 \(S=P_1,C=P_2\) 是唯一映射；不再以"真实性检查方向相反"为由否定 Afshar 适配路线；也不宣布 GO——单方输出与策略无关视图的组合证明仍未完成。PA-VFANN 整体仍维持 EXP-03D 的 NO-GO 关闭状态，本 HOLD 只针对 Afshar 适配这一条具体路线。

---

## 1. 对 EXP-03E 错误的逐条纠正

| # | EXP-03E 的表述 | 修正 | 依据 |
| --- | --- | --- | --- |
| E1 | "P1 存每内存位两个 wire label，故 P1 知道实际内存内容；P2 只存一个，故不知道" | **错误。** 两个 label 是同一逻辑位的两种编码；知道候选集合与真值映射，不等于知道哪一个是活动 label。解码需要活动 label **且**需要对应输出线的 \(\tau\) | §1："wire labels ... they hide the associated logical value"；§2.2："decoded to a plain output via \(\operatorname{lsb}(Y)\oplus\tau(D)\)" |
| E2 | "只能映射为 \(S=P_1,C=P_2\)" | **错误。** 原文 RAM 定义使用对称的 \((x_1,x_2)\)，协议由 \(P_2\) 通过 OT 提供自己的输入；没有任何条款规定索引必须由 \(P_1\) 持有。\(S=P_2,C=P_1\) 未被排除 | §2.1 `RAMEval(Π,M,x1,x2)`；§3.2 3(c) `GetInput2(st2(E),r2,…)`；§4.2(d) |
| E3 | "原有真实性检查方向相反，客户端完整性必须另建" | **错误。** §3.2 3(g) 与 §4.2(j) 都是 \(P_2\) 提交、\(P_1\) 检查；§4.1 原文即写 "authenticity of the output for P1"。在 \(S=P_2,C=P_1\) 下方向正好保护客户端 | §3.2 3(g)、§4.1、§4.2(j)、§3.3、§4.3 |
| E4 | 模拟器写为 \(\mathcal S(1^\lambda,L_S)\) | **不完整。** 腐败方自己的私有输入是辅助输入，应写 \(\mathcal S(1^\lambda,I,L_S)\)；原文本身在 \(P_2\) 腐败时先抽取 \(x_2\) 再送入理想功能 | §3.3、§4.3 |
| E5 | 把 \(E\cdot M=1600\) 称为"完整 ORAM 访问次数" | **错误。** 1600 只是逻辑邻居读次数；物理访问数依赖具体 ORAM 实例，论文只给抽象定义，不固定实例 | §2.1 ORAM 定义；§3.2 3(d)/3(f) |
| E6 | §4.3 把语义 A 轨迹独立性写成肯定结论，§4.4/§6.2 又列为待证 | **结论不自洽。** 统一降为"有条件的结构性论证：在 7 项 dummy-read 规则与完整 inst 序列不依赖 P 的前提下成立，尚未证明" | 本次修正 §7 |

上轮仍然成立的部分：双方每轮都解码含地址的 `inst`（§3.2 3(g)）；最终 \(z\) 双方都可得（同处）；§2.1 的 ORAM 模拟器以最终输出 \(z\) 为输入。这三点不因角色映射改变而消失。

---

## 2. Afshar 原文事实重审（只引会议版可核验内容）

### 2.1 输入对称性与角色

- §2.1：`A RAM program ... is executed in the presence of memory M ... on inputs (x1,x2)`，`st := x1 || x2 || 0^n`。输入属于哪一方的**程序语义**，不是协议硬编码。
- §3.2：`let x1 and x2 denote the inputs of P1 and P2, respectively`；3(c) 中 `st(Xt) = GetInput1(st1(E), x1) + GetInput2(st2(E), r2,1…r2,n) + GetInputpub(st3(E),0^n)`；§3.2 脚注 3 明确首轮电路与后续电路仅在 P2 输入层增加 XOR 门。
- §4.2(d)：`we use a single OT across all threads for each input bit of P2`，进一步确认 \(P_2\) 是自己输入的持有者。

**结论**：把 \(I\) 放在 \(x_2\)、把 \(P\) 放在 \(x_1\) 与协议结构相容。上轮"P2 经 OT 输入整个索引"的说法本身没错，但被误用作排除理由——OT 输入是设计的一部分，不是障碍。

### 2.2 wire-label 语义（上轮错误根源）

§2.2 定义 \(W[i,0],W[i,1]\) 为同一线 \(i\) 的两个 label，\(\tau(W)\) 为 translation bit，使 \(W[i,W[i,2]]\) 编码 false；解码公式为 `lsb(Y) ⊕ τ(D)`。原文进一步定义部分解码信息：若 \(\mu\) 为 mask，公开 \((\mu,\tau(D)\land\mu)\) 只让评估者学到 \(\mu_i=1\) 的输出位；"such an adversary's view is then independent of \(f(x)\land\mu\)"。

§3.4 的存储描述：`For each bit of RAM memory, P1 must store the two wire labels (and their decommitment info) ... P2 must store only a single wire label per memory bit.` §4.4 对应 streaming 版：`P1 must remember 2S wire labels per bit of memory ... P2 must remember between S and 2S wire labels`。

**逐方可见性推导（区分证据等级）**：

| 事实等级 | 内容 |
| --- | --- |
| 原文事实 | P1 保存两个候选 label 与 decommitment；P2 保存活动 label；只有 `inst` 输出的 \(\tau(inst(D))\) 被公开给 P2（§3.2 3(f)、§4.2(f)）；3(g) 只回传 `inst` 的 label，不回传 `block` 的 label |
| 由协议流程推导 | P1 无活动 `block` label → 不能解码内存块内容；P2 有活动 `block` label 但无 \(\tau(block(D))\) → 也不能解码；\(P_1\) 的输入 label 经 `GetInput1` 打开（§3.2 3(c)）或经 \(k_{eval}\) 交给 eval thread 的 P2（§4.2(c)），但输入线的 \(\tau\) 未公开 → P2 只见随机 select bit，不能恢复 \(x_1\) |
| 尚未确认 | 恶意客户端通过畸形 garbling 提取超量 \(I\) 信息的界限，需靠 cut-and-choose 与目标功能输出约束联合论证，本报告不宣称已核清 |

**这一推导同时回答用户第 2 项核查**：在 \(S=P_2,C=P_1\) 下，客户端 \(P_1\) 作为 garbler 持有候选 label 与 \(\tau\)，但**缺少活动 label**，因此不能从 wire label、`block`、`st` 或 ORAM 状态恢复未授权向量内容；这一结论是**结构性论证**，不是已完成的模拟证明。

### 2.3 每轮可见的 `inst` 与地址

§3.2 3(g)：`P2 sends Ỹ = inst(Yt) to P1. Both parties decode the output instt = lsb(Ỹ) ⊕ τ(inst(D(hdt))). P1 aborts if the claimed wire labels Ỹ do not equal the expected wire labels ...`；§4.2(h)：P2 自己 `decodes the output inst(t,i) = lsb(Y(t,i)) ⊕ τ(D(t,i))` 并取多数。

**两种映射下，双方都能解码 `inst`（含读/写操作码与内存位置）。** 因此"服务端会看到逻辑地址"不是排除某一映射的理由，而是语义 A 必须处理的共同要求：逻辑地址序列必须与 \(P\) 无关。注意区分：这里可见的是 ORAM **逻辑**地址；ORAM 物理访问轨迹是另一个对象，见 §7.2。

---

## 3. \(S=P_2,C=P_1\) 下的协议重述

| 参与方 | Afshar 角色 | 持有 | 职责 |
| --- | --- | --- | --- |
| 不可信服务端 \(S\) | \(P_2\)，evaluator | \(x_2=I\)（承诺索引明文）、ORAM position map / stash 的明文侧信息、eval-thread 的活动 label | cut-and-choose 检查电路；OT 输入 \(I\) 与随机份额；执行 EvalBucket / Eval；回传 `inst` label |
| 客户端 \(C\) | \(P_1\)，garbler | \(x_1=(P,\rho,\mathrm{Cred}\) 的电路内编码\()\)、公开 \((R_I,\mathrm{ver},q,E)\) | 生成并承诺电路；开 \(GetInput1\)；验证 3(g)/4.2(j) 的输出真实性；用 \(\rho\) 恢复 \(z\) |
| 数据所有者 \(D\) | 协议外 | 签名 \((R_I,\mathrm{ver})\) | 发布承诺根；索引版本与有效期绑定 |

理想功能仍为 \(\mathcal F_{\text{PA-VFANN}}\)：先验证 \(\mathsf{VerifyCred}(\mathrm{Cred},P,\mathrm{ver},C)=1\)，再计算 \(z=\mathsf{FilteredANN}(I,q,P,E)\)，只向 \(C\) 输出固定 \(K\) 条（不足用不可区分哑记录）；\(S\mapsto\bot\)。允许泄露 \(L_S=(R_I,\mathrm{ver},q,E,\text{public parameters})\)，并明确 \(I\) 是腐败服务端自己的私有输入。

**与 EXP-03E 的差异**：不再把 \(I\) 放在 garbler 一侧；不再以角色为由否定原真实性检查；凭证验证与索引承诺绑定仍需作为电路内子电路实现，且成本单列，不得记入 ANN 贡献。

---

## 4. 输出真实性检查方向审计（回答用户第 3 项）

**原文事实**

- §3.2 3(g)：`P2 sends Ỹ = inst(Yt) to P1 ... P1 aborts if the claimed wire labels Ỹ do not equal the expected wire labels inst(D(hdt))|∗instt.`
- §3.3（\(P_2\) 腐败）：模拟器 `simply aborts if these wire labels are not the pre-determined visible output wire labels`。
- §4.1：`We ensure authenticity of the output for P1 using an approach suggested in [30].`
- §4.2(j)：`P2 opens the commitments to values w_j and P1 uses them to decode the output instt. If a value w_j does not match one of w(t,j,0) or w(t,j,1), then P1 aborts.`
- §4.3（\(P_2\) 腐败）：`S aborts if P2 does not open its commitment to the expected output keys.`

**判定**

在 \(S=P_2,C=P_1\) 下，检查方 \(P_1\) 就是客户端，被检查方 \(P_2\) 就是服务端。因此**原有输出真实性检查的方向正确，可以成为客户端验证服务端未谎报执行结果的基础**。EXP-03E 所称"方向相反、必须另建一套"的结论作废。

**但必须写清它保证什么、不保证什么**

| 保证 | 不保证 |
| --- | --- |
| \(P_2\) 不能谎报电路实际产出的 `inst` label（§2.2 的 authenticity 性质：评估者可解码输出，但无法伪造完整 label） | 不保证电路本身忠实实现了指定状态机——这靠 cut-and-choose（\(P_2\) 检查电路，但恶意 \(P_2\) 可以选择不检查；诚实 \(P_1\) garbling 下电路本就正确） |
| 在 \(P_1\) 诚实 garbling 前提下，恶意 \(P_2\) 只能原样回传，不能替换结果 | 不保证 \(x_2=I\) 与签名承诺 \(R_I\) 绑定；需在电路内加入承诺检查并把 \(R_I\) 作为公开输入 |
| 中止可由客户端检测 | 不阻止恶意服务端拒绝服务；只要求中止行为不泄露 \(P\) |

结论：用户第 3 项成立——"不能再把原检查机制简单判为方向错误"；同时不能把"方向正确"写成"客户端完整性已解决"。

---

## 5. 单方输出改造（回答用户第 4 项）

### 5.1 掩码归属

\(\rho\) 作为客户端 \(P_1\) 的**秘密输入分量**（与 \(P\) 一起进入 \(x_1\)），电路输出 \(z'=z\oplus\rho\)；\(P_2\) 只能解出 \(z'\)，\(P_1\) 用自己持有的 \(\rho\) 恢复 \(z\)。EXP-03E 的 \(z\oplus\rho\) 思路保留，但角色归属必须改为 \(P_1\) 采样并输入。

### 5.2 论文可复用的组件

§2.2 的部分解码信息 \((\mu,\tau(D)\land\mu)\) 明确支持"只公开部分输出位"。因此可把 `inst`（控制流所需）与 \(z'\)（结果位）分区：对 \(P_2\) 只开放控制流位的 \(\tau\)，结果位的 \(\tau\) 不开放。这属于**可直接使用的已有组件**。

### 5.3 需要修改的步骤

1. 把最终输出线从 `(halt,z)` 拆为 `(halt, z⊕ρ)`，并限定结果位不进入对 \(P_2\) 的 \(\tau\) 公开集合（§3.2 3(f)、§4.2(f)）；
2. \(\rho\) 作为 \(P_1\) 输入需纳入 `GetInput1` / 4.2(c) 的 k_eval 加密与输入一致性检查；
3. §3.2 3(g)、§4.2(j) 的真实性检查对象扩展为掩码后的结果线；
4. 客户端结果真实性改为：3(g)/4.2(j) 的 label 真实性 + 电路内 index commitment 检查 + \(\rho\) 恢复。不能再依赖 Afshar 原有的"双方都得到 \(z\)"语义。

### 5.4 需要重新证明的性质

- 恶意 \(P_2\) 模拟器：其视图含 \(z'\) 与 \(\rho\) 的活动 label；须证明给定 \(I,L_S\) 可模拟，且不泄露 \(\rho\) 或 \(z\)；
- 恶意 \(P_1\) 模拟器：须证明 \(P_1\) 不能通过 \(\rho\) 或 garbling 使客户端得到超出 \(z\) 的信息；
- 单方输出混合论证：\(z'\) 与独立随机 \(\rho\) 的不可区分性；
- \(\rho\) 的中止独立性：恶意 \(P_2\) 不能通过选择中止来测试 \(\rho\) 或 \(P\)。

**判定**：单方输出**未被证明已解决**，但也不再因"方向相反"被排除；现在的问题是明确的协议修改 + 四项重证，不是不可修复障碍。

---

## 6. 模拟器中止独立性（修正 E4）

论文原文的模拟器结构：

- §3.3（\(P_1\) 腐败）：抽取 \(x_1\) 送理想功能得 \(z\)，生成模拟 ORAM 访问序列；
- §3.3（\(P_2\) 腐败）：`S also extracts P2's input x2 from its select bits sent to Fot. It sends x2 to the ideal functionality and receives the output z. Then S generates a simulated ORAM memory-access sequence.`；§4.3 同构。

目标安全游戏修正为：

\[ \mathcal S(1^\lambda, I, L_S) \quad\text{s.t.}\quad \mathrm{View}_S(P_0)\approx_c \mathrm{View}_S(P_1),\ \forall P_0,P_1 \text{ with same public format}. \]

其中 \(I\) 是腐败方自己的私有输入（辅助输入），\(L_S\) 不含 \(P\)。这是我们与论文的最大差异：论文的模拟器以 \(z\) 为输入生成访问序列，而我们要的是**不依赖 \(z\)** 的访问序列模拟；同时服务端还会在每轮看到 `inst` 与最终 \(z'\)，二者都需纳入模拟。

**不允许**把"论文证明了恶意安全"直接当作本目标已证。论文的恶意安全是相对于其自身理想功能 \(\mathcal F_{\text{RAM}}\)（双方都输出 \(z\)，泄露由 \(z\) 限定的访问序列）；我们的理想功能是单方输出 + \(L_S\) 不含 \(z\)。功能不同，证明不可直接搬运。

---

## 7. 语义 A 完整可见视图审计（回答用户第 5 项，并修正 E5/E6）

### 7.1 逻辑读与物理读必须分开

\(E\cdot M=100\times16=1600\) 是**每轮 16 个逻辑邻居读取**的总数。一次逻辑读经 ORAM 展开为若干物理 block 读写（依 ORAM 实例而定，常见为 \(O(\log N)\) 量级），论文 §2.1 只定义"隐藏访问模式"的抽象，不固定实例。**因此 1600 不是完整 ORAM 物理访问数**，不能用来直接报通信量或门数。修正后的写法：

\[ N_{\text{phys}} = \sum_{j=1}^{1600} \bigl(\text{phys\_ops}(\text{ORAM instance},\ \ell_j)\bigr), \]

其中 \(\ell_j\) 为第 \(j\) 次逻辑地址。

### 7.2 语义 A 的 7 项 dummy-read 规则（结构性论证）

固定预算下，下列情形均执行固定地址 dummy read，禁止提前终止：

1. 队列空；2. 重复节点；3. 未授权节点禁止展开；4. 有界桥接达深度上限；5. 每轮消息长度固定；6. 每轮 ORAM 逻辑操作数固定为 \(M\)；7. 结果不足 \(K\) 条时用不可区分哑记录补齐。

若 \(Q,V,R\) 全部保存在 RAM 程序内部状态 `st`（§1、§3.4：状态经 garbled wire label 跨步传递，只有 RAM memory 走 ORAM），则 \(P\) 只影响结果插入的匹配位与 \(R\) 的内容，不影响 \(\ell_1,\dots,\ell_{1600}\) 与操作码序列。**于是逻辑 `inst` 序列是 \((R_I,\mathrm{ver},q,E)\) 的确定函数。**

### 7.3 仍缺的一步

逻辑序列固定 \(\nRightarrow\) 服务端完整视图固定。服务端可见还包括：

- 物理 ORAM 访问序列（依 ORAM 实例与 position map 演化）；
- 每轮 wire label 值、\(\tau(inst(D))\) 揭示、消息长度与数量；
- 中止行为（3(g)/4.2(j) 检查失败、cut-and-choose 检查失败、OT 一致性失败）；
- 最终掩码输出 \(z'\)。

论文的 §2.1 模拟器输入是 \(z\)；要得到只依赖 \(L_S\) 的模拟器，必须证明上述全部分量可在给定 \((I,L_S)\) 下模拟。**这一步尚未完成。** 因此EXP-03E §4.3 的肯定表述应统一改为：

> 语义 A + 7 项 dummy-read 规则给出了逻辑访问序列与 \(P\) 无关的**结构性论证**；完整服务端视图的不可区分性仍是有待证明的命题，见 §10。

### 7.4 语义 B 的否定结论保留

语义 B 中 \(P\) 的匹配位改变下一扩展节点与队列键，固定读次数只固定"数量"不固定"序列"；逻辑 `inst` 序列依赖 \(P\)，§2.1 模拟器仍需 \(z\)（而 \(z\) 依赖 \(P\)）。因此语义 B **不满足** \(L_S\) 不含 \(z\) 的轨迹独立性。这一判断不因角色映射改变。

---

## 8. 最小安全证明清单（实现目标所需）

1. **无 \(z\) 的轨迹模拟器**：给定 \((1^\lambda,I,L_S)\) 构造 \(\mathcal S\) 输出与真实 `inst`/物理访问序列不可区分（语义 A）。
2. **恶意 \(P_2\)（服务端）模拟器**：含 \(x_2=I\) 抽取、OT 选择位、eval-thread 可见 label、\(\tau\) 揭示、协议消息与上中止概率。
3. **恶意 \(P_1\)（客户端）模拟器**：在 \(P_1\) 为 garbler 的结构下，抽取 \((P,\rho)\) 并证明不会从 \(I\) 得到超量信息。
4. **单方输出混合论证**：\(z'=z\oplus\rho\) 下 \(P_2\) 视图与 \(z\) 独立；\(\rho\) 的活动 label 不泄露 \(\rho\)。
5. **索引绑定混合**：电路内 \(R_I\) 检查使 \(x_2\) 与签名承诺一致，防止遗漏/替换/旧版本索引。
6. **客户端结果真实性**：3(g)/4.2(j) 的 label 真实性 + cut-and-choose + 承诺检查联合保证 \(z\) 等于指定状态机在承诺索引上的输出（G3-alg，不是全局精确 Top-K）。
7. **凭证绑定**：\(\mathrm{Cred}\) 与 \(\mathrm{Commit}(P)+\mathrm{ver}+\exp\) 绑定；验证成本单列。
8. **\(\rho\) 与 \(P\) 的中止独立性**：所有中止分支的概率差为可忽略量，含跨查询累积分析。

---

## 9. 真正的技术缺口分类

| 类别 | 状态 |
| --- | --- |
| 输出隐私 | 有构造路径（§5），未证明；**不是**不可修复障碍 |
| 访问轨迹隐私 | 语义 A 有结构性论证，完整视图模拟未证明；语义 B 明确不成立 |
| 恶意输入一致性 | \(I\) 与 \(R_I\) 绑定需电路内新增检查；论文只保证双方各自输入在 thread 间一致 |
| 索引完整性 | 同上；Merkle/承诺验证必须在 MPC 内，成本与 A/B/C 三方案均为共同成本 |
| 组合问题 | 单方输出 + 无 \(z\) 轨迹模拟 + 索引绑定的联合证明是唯一真正未闭合点 |

---

## 10. 唯一待证明命题与判决

### 10.1 唯一待证明命题（命题 2′）

> 在 \(S=P_2,C=P_1\) 映射、语义 A（filter-oblivious traversal + post-filter）、7 项 dummy-inclusive 固定读与 \(z'=z\oplus\rho\) 下，存在 \(\mathcal S(1^\lambda,I,L_S)\)，使恶意服务端 \(P_2\) 的完整视图（逻辑/物理访问序列、`inst` label、\(\tau\) 揭示、消息长度与数量、中止、掩码输出）与 \(P\) 不可区分；同时客户端 \(P_1\) 能凭原有输出真实性检查与电路内索引承诺验证，确认 \(z\) 等于承诺索引上指定检索状态机的输出。

### 10.2 判决

**HOLD。** 理由：修正后构造路径明确（角色映射可行、真实性检查方向正确、§2.2 部分解码可直接复用），不存在已识别的不可修复障碍；但命题 2′ 未证明，因此没有可主张的差异化贡献，也不得进入原型实现。

### 10.3 停止规则

- 命题 2′ 证明成立 → 才允许进入最小协议原型与安全证明阶段；
- 证明失败 → 拒绝 **Afshar 适配路线**（不等于宣布 PA-VFANN 整体不可能），并停止该路线；
- 本轮后不再追加队列结构、实验参数或泛化文献搜索。若选择不再投入，按 NO-GO 关闭处理，但须在报告中明确否定对象是 Afshar 适配而非整个方向。

---

## 11. 证据等级与限制

- **一手已核**：Springer 会议版 §1、§2.1、§2.2、§3.1–§3.4、§4.1–§4.4 的原文（本报告所有引号均出自该版本）。
- **受限**：ePrint `2014/759.pdf` 在本环境持续 403，full version Appendix D 的模拟器与 selective-abort 细节无法逐字核验；本报告对 selective-abort 的表述仅引用会议版 §3.2 脚注、§3.3、§4.1、§4.3。
- **不宣称**：不宣称单方输出已完成；不宣称 G3 全局精确 Top-K；不宣称验收通过；不宣称 PA-VFANN 整体重启。
- **已核实**：仓库改动范围与基线符合本轮约束（详见最终汇报）。

| 报告正文 commit | `1867ec87c4583983bb0eccf3f4f7605972a962d3` |
| 远端 HEAD | `1867ec87c4583983bb0eccf3f4f7605972a962d3`（已核验与本地一致） |
| 工作区状态 | 报告提交与推送后 `git status --short` 为空；相对基线仅本报告一个新增文件 |
