# EXP-05 / B1：不使用 \(z\) 的单方输出模拟器可行性审计

> 项目：PA-VFANN-26。B1 定向修复评估（EXP-04 §6 第 1 项，决定性关口）。协议级审计，不写代码、不改实验数据、不改 EXP-01–04 历史报告、不扩文献、不为得到可行结论降低安全标准。
> 目标：判断在 \(\mathcal F_{\mathrm{retrieve}}(P,\mathrm{Cred},q,I)\to(R_C,\bot_S)\) 下，能否构造一个**不使用秘密结果 \(z\)、不使用秘密策略 \(P\)** 的恶意 P2（Server）腐化完整视图模拟器。
> 停止规则（用户设定）：若 B1 明确不可行 ⇒ 停止当前路线，不继续 B2–B5；若有具体可行构造路径 ⇒ 继续，但构造路径不等于完整安全证明。

---

## 0. 交付与证据状态

| 项 | 内容 |
| --- | --- |
| 基线 commit | `8c2e5715e30468204c16aaa6d235869952844320`（EXP-04 最终 HEAD） |
| 分支 | `exp05-b1-one-sided-simulator` |
| 新增文件 | `docs/EXP-05-B1-ONE-SIDED-SIMULATOR.md`（本文，唯一新增） |
| 一手来源 | Afshar, Hu, Mohassel, Rosulek, *How to Efficiently Evaluate RAM Programs with Malicious Security*, EUROCRYPT 2015 Part I, LNCS 9056, pp. 702–729, DOI `10.1007/978-3-662-46800-5_27`；Springer 官方会议版 PDF，810,112 字节，SHA-256 `92ccf8ab8014f4fd50eba8641369ee52fe5ae4dc5a349daad2466f9f5ee73d50`（与 EXP-03L/04 同一文件） |
| 引用格式 | 「§x.y，印刷页 Y；提取文本第 N 行」 |
| 证据限制 | §3.3 原文写明 "Due to page limits, we give only an overview of the simulator S and security proof. The complete details are deferred to the full version"（第 345–349 行）；full version Appendix D 本环境受限。凡会议版未逐字写明处，一律标为**结构性论证**，不冒充形式化证明。 |

**一句话判决：B1 的 z 依赖消除 = ACCEPT（结构性，有原文逐行依据）；完整联合不可区分证明 = HOLD（三个缺口）；停止条件未触发。** 原文模拟器的 \(z\) 依赖有且仅有一个根源，且该根源在 \(\mathcal F_{\mathrm{retrieve}}\) 下可由 P2 已知量替代；但把 result 组件、控制线轨迹、GC/check/solder/ORAM 各分量拼成严格联合 hybrid 的工作仍未完成，且受 full version 受限无法逐字核验。因此**不停止、也不 GO 进实现**。

---

## 1. B1 命题的严格口径

要判定的是是否存在高效 \(S\)，使得对每个 PPT 恶意 P2：

\[
\operatorname{View}_{P2}\big(\Pi_{\mathrm{one\text{-}sided}}(P,\mathrm{Cred},q,I)\big)\ \approx_c\ S\big(I,\ L_S\big),
\qquad L_S=(R_I,\mathrm{ver},q,E,K,M,\text{公开参数}),
\]

其中三个硬约束：

- **(C1) \(S\) 的输入不得含 \(z=\mathsf{FilteredAnnStateMachine}(I,q,P,E)\) 的任何编码，也不得含 \(P\)**；
- **(C2) 视图必须是完整 transcript**：预处理承诺、cut-and-choose 检查集、每轮 Solder/MkBucket/Adjust、GetInput1/2/pub、EvalBucket、控制线解码、result 活动 label、halt、以及所有 abort 分支；
- **(C3) 不能把"每个分量分别可模拟"直接当作"联合视图可模拟"**——这是 EXP-03H/I 已经吃过亏的地方（局部不可泄露 ≠ 联合可模拟）。

本轮只审 P2 腐化方向；恶意 P1 属 B3，不在本轮。

---

## 2. 原文 §3.3 P2 腐化模拟器的 \(z\) 依赖逐行定位

原文模拟器（印刷页 715，第 362–380 行）可拆为 7 个动作。逐项标注是否使用 \(z\)：

| # | 原文动作（逐字要点） | 输入 | 依赖 \(z\) |
| --- | --- | --- | --- |
| A | "S simulates commit messages from Fcom" | 无 | 否 |
| B | "After receiving \(S_c\) from P2, it equivocates the opening of the check sets to honestly garbled circuits and wire labels" | \(S_c\) | 否 |
| C | "S sends random wire labels in GetInput1 and GetInputpub … simulates random wire labels as the output of Fot in GetInput2 … These determine the wire labels that are 'visible' to P2" | 随机带 | 否 |
| D | "S also extracts P2's input \(x_2\) from its select bits sent to Fot" | P2 输入 | 否 |
| E | "**It sends \(x_2\) to the ideal functionality and receives the output \(z\). Then S generates a simulated ORAM memory-access sequence.**" | \(x_2,z\) | **是（根源）** |
| F | "In the Solder steps, S equivocates soldering values chosen to map visible wire labels to their counterparts … and chooses random soldering values for the non-visible wire labels" | 可见 label | 否 |
| G | "S chooses a random set of visible output wire labels and equivocates to a simulated garbled circuit generated using only these visible wire labels. S also equivocates on the decommitment to \(\tau(inst(D(i)))\), chosen so that the visible output wires will decode to **the next simulated ORAM memory instruction**" | 可见 label + E 的序列 | **是（经 E 传递）** |
| H | "the simulator simply aborts if these wire labels are not the pre-determined visible output wire labels" | 可见 label | 否 |

**结论（结构性，原文逐行可核）**：\(z\) 在 P2 腐化模拟器中只有一个入口——动作 E。动作 G 本身只需"可见 output label + 下一条逻辑指令"，之所以标依赖 \(z\)，是因为原文的下一条指令取自 E 生成的序列。动作 A/B/C/D/F/H 完全不依赖 \(z\)。

这正是 B1 的杠杆点：**只需替换动作 E 的信息来源，就可能把 \(z\) 从整个模拟器里消掉。**

---

## 3. 为什么原文用 \(z\)：ORAM 定义的角色

§2.1（印刷页 706–707，第 120–124 行）定义 \(\mathcal I(\Pi,M,x_1,x_2)\) 为 `inst` 变量取值序列，并要求

\[
\exists S:\ \forall x_1,x_2,\ \text{initially empty }M:\quad S(1^\lambda,z)\ \approx\ \mathcal I(\Pi,M,x_1,x_2),
\]

其中 \(z\) 是程序最终输出。**原文的 \(z\) 是"逻辑访问轨迹的摘要"**：它帮助模拟器生成 \(\mathcal I\)，从而驱动动作 G 的控制线 equivocation。这是原文功能"计算 \(F(x_1,x_2)=z\)"的直接后果——逻辑轨迹随输入变，只能用输出 \(z\) 概括。

在 \(\mathcal F_{\mathrm{retrieve}}\) 下，这个角色必须换掉，因为 \(z\) 不允许交给 P2 模拟器。替换命题：

> **替换命题 (R)**：在 EXP-04 §1.2 把计算限定为**固定预算状态机** \(z=\mathsf{FilteredAnnStateMachine}(I,q,P,E)\) 的前提下，逻辑访问序列是 \((I,q,E)\) 的确定函数（语义 A，EXP-03E/F/G 的轨迹不变性），而 \(I\) 是 P2 自身输入、\(q,E\in L_S\)。故模拟器可直接用 \((I,q,E)\) 生成逻辑序列，不必经 \(z\)。

(R) 不是原文定理，而是**程序层性质 + 输入可见性**的组合。它的成立依赖语义 A 在电路级被真正实现（见 §6 缺口 1）；EXP-03A 已证全局精确 Top-K 做不到这一点，只有固定预算状态机可行。

---

## 4. 逐分量构造：把 \(z\) 从每个可见量里消掉

在 (R) 下重写原文 7 个动作，得到候选模拟器 \(S_{\mathrm{one\text{-}sided}}(I,L_S)\)：

| 分量 | 生成方式（不含 \(z\)） | 依据 |
| --- | --- | --- |
| 预处理承诺 / check 集 | 同原文 A/B，与输入无关 | §3.3 原文 |
| 随机带 / GetInput1/2/pub | 同原文 C，随机 label | §3.3 原文；§2.2（`GetInput2` 的 OT 选择由 P2 自定） |
| 提取 \(x_2\) | 同原文 D，从 Fot select bits | §3.3 原文 |
| 逻辑指令序列 | 由 \((I,q,E)\) 经 (R) 计算 | 语义 A；EXP-01 E3 轨迹不变性 |
| 控制线 \(\tau\) equivocation | 令可见控制线解码为上面的逻辑指令 | §3.3 动作 G；结果线与控制线分区（见 §5） |
| result 活动 label + solder 差值 | 用不含 \(z\) 的联合采样器从头生成 | EXP-03J/K/L 局部引理；§4.1 数值验算 |
| Solder / MkBucket / Adjust | 同原文 F：可见 label 映射到对应，非可见取随机 | §3.3 原文；§3.1 solder 定义 |
| 3g abort | 同原文 H：claimed label ≠ predetermined visible label 则中止 | §3.3 原文；EXP-04 §3.0（互补 label 不可预测） |

### 4.1 result 组件的数值验算（组件级，非协议级）

对单结果线、原始随机结构（\(T\perp\)：\(\tau\) 为独立列；P：逐电路独立 \(\Delta\)；Free-XOR：\(E[i,0]\oplus E[i,1]=\Delta_c\)）做小规模穷举（\(\lambda=3\)，遍历 \(\Delta_h,\Delta_j\in\{1,3,5,7\}\)、基值 \(L_h,L_j\in\{0,2,4,6\}\)、\(\tau_h,\tau_j\in\{0,1\}\)）：

- 可见量取 \((\text{活动 }Y_h,Y_j,\delta=\tau_j\oplus\tau_h,\ \Delta_{solder}[i,0],\Delta_{solder}[i,1])\)；
- 真实执行在 \(z=0\) 与 \(z=1\) 的分布**严格相等**，支持集均 256 状态；
- 构造的不含 \(z\) 采样器（先采活动选择位 \(c_h,c_j\) 均匀、令 \(\delta=c_j\oplus c_h\)，基值与 \(\Delta\) 按原分布采）输出分布与真实分布**逐点相等**。

同一验算复现 EXP-03K 的边界：若 \(k\neq\mathrm{lsb}\) 且强制 \(\tau_c=\Delta_c[k]\)（\(T=\)），两结果位的 lsb 差为 \(z_1\oplus z_2\)，区分器成立——但 EXP-03L 已用 §2.2「互补 label 除 lsb 外不可预测」与 §3.1「forgoing common wire offsets between circuits」证明 \(T=\) 不是 Afshar 合法实例化，故该区分器**不适用于原始构造**，仅作实现禁用警告。

**这组验算只证明 result 组件可被无 \(z\) 采样，不构成完整 transcript 的联合证明**（见 §6）。验算为一次性 shell 穷举，未写入仓库、未新增代码或数据文件。

---

## 5. 关键辨析：batching equivocation 下 result label 不需要 \(z\)

这是 B1 最容易被误判为"不可行"的技术点，必须正面处理。

§2.2 的 garbling simulator（第 145–147 行）写作 \(\mathrm{Sim}(f,x,D): E\!\leftarrow\!W,\ F\!\leftarrow\!S(f,E|_{*}x,D|_{*}f(x))\)，其输入含 \(D|_{*}f(x)\)——即**正确输出对应的活动 label**。若把 result 线视作 \(f\) 的普通输出，则 \(f(x)\) 的 result 分量就是 \(z\)，于是模拟器似乎必须知道 \(z\) 才能提供 \(D|_{*}f(x)\)。

**这个疑虑在 batching 框架下不成立**，理由三条：

1. 原文 P2 腐化模拟器**不走** \(\mathrm{Sim}(f,x,D)\) 这条路径。动作 G 逐字是 "**chooses** a random set of visible output wire labels and equivocates to a simulated garbled circuit generated using only these visible wire labels"——模拟器先自定可见 output label，再反推一个一致的假 GC；它从不计算 \(f(x)\)，也不接收 \(D|_{*}f(x)\)。
2. result 线在单方输出改造中取 \(\mu=0\)（不开 \(\tau(result)\)）。P2 看不到 result 的选择位，无法询问"这条 label 编码的是 0 还是 1"。模拟器只需指定一条**合法**的活动 label（满足 lsb/point-permute），不必声称它对应 \(z\)。§2.2 的部分解码性质（第 138–149 行）保证：给 \((\mu,\tau(D)\wedge\mu)\) 且 \(\mu_i=0\) 时，视图与 \(f(x)_i\) 无关。
3. 结果线是**终止输出**，不进入后续轮次（halt 固定在 \(t=E\)）。因此 result label 不与 ORAM 轨迹或下一轮 GC 输入耦合；局部引理（§4.1）足以覆盖它。

**因此**："garbling simulator 需要 \(D|_{*}f(x)\Rightarrow\) 模拟器需要 \(z\)" 这一推理，仅在**单电路、输出完全开放**的设定成立；在 Afshar batching 的 equivocation + \(\mu=0\) + 终止输出三重条件下不成立。这是 B1 可行的核心技术依据。

---

## 6. 联合性缺口：为什么这还不是完整证明

以下三项使本轮不能把判决升级为无条件 ACCEPT，也不足以 GO 进实现：

1. **语义 A 的电路级实现未证（缺口 1）**。(R) 是程序层性质：逻辑轨迹必须与 \(P\) 无关、是 \((I,q,E)\) 的确定函数。EXP-01 E3 在算法层给出轨迹不变性证据，EXP-03A 给出"全局 Top-K 不可行"的边界，但把固定预算状态机写成电路、并在 cut-and-choose/bucket 结构下证明 majority 后轨迹仍确定，属程序构造任务（B4），非本轮密码学论证可替代。**若此项失败，B1 的动作 E 替换失效，路线回到不可行。**

2. **full version 受限（缺口 2）**。§3.3 明示完整模拟器细节在 full version；会议版只有 overview。任何"完整联合不可区分"的逐字核验在现有证据下做不到。本轮所有"同原文"的判断都是对 overview 的结构性沿用，不是对完整证明的复核。

3. **严格联合 hybrid 未写出（缺口 3）**。本轮给出的是逐分量构造 + result 组件数值验算，满足 C1/C2 的部分要求；但未构造一条完整 hybrid，把"承诺 → check → GetInput → Solder → 控制线 → result → ORAM → abort"按顺序逐项替换并证明每一步不可区分。特别是控制线指令与 result label 出自**同一 bucket 的 EvalBucket 输出**，二者经 majority 耦合；逐分量可模拟不自动推出这一对联合可模拟。这是用户反复强调的"局部 ≠ 联合"问题在协议层的对应物。

三项缺口都是"缺证明/缺构造"，没有一项是"已证矛盾"。

---

## 7. 判决表

| 检查项 | 判决 | 论证 / 反例 / 缺失证据 |
| --- | --- | --- |
| 原文模拟器 \(z\) 依赖点唯一 | **ACCEPT** | §3.3 动作 A–H 逐行：仅 E 直接使用 \(z\)，G 经 E 间接依赖；其余无依赖。 |
| 依赖点可在 \(\mathcal F_{\mathrm{retrieve}}\) 下用 \((I,q,E)\) 替换 | **ACCEPT（条件于语义 A）** | 替换命题 (R)；\(I\) 为 P2 输入、\(q,E\in L_S\)；EXP-01 E3 轨迹不变性为算法层支撑。 |
| batching equivocation 下 result label 无需 \(z\) | **ACCEPT** | §5 三条：动作 G 自定可见 label；\(\mu=0\) 部分解码；result 为终止输出。 |
| result 组件无 \(z\) 联合采样 | **ACCEPT（组件级）** | §4.1 数值验算：\(z=0/1\) 分布逐点相等，采样器同分布；受限于单结果线与 λ=3。 |
| 不使用 \(z\) 的**完整联合**模拟器已构造并证明 | **UNKNOWN** | 缺口 1/2/3：语义 A 电路级、full version 受限、严格联合 hybrid 未写。 |
| B1 是否明确不可行（停止条件） | **否** | 存在具体构造路径且关键组件已验；不满足"明确不可行"的停止触发条件。 |
| 足以 GO 进协议实现 | **否** | 完整联合证明未闭合；按用户"不为得到可行结论降低标准"，不升级为 GO。 |

### 整体判决：**B1 构造可行（ACCEPT 路径存在）／完整证明 HOLD／不停止**

- **不停**：B1 未发现不可修复矛盾；原文 \(z\) 依赖可定位、可替换，result 组件可无 \(z\) 采样。按用户停止规则，不触发终止。
- **不 GO**：C2（完整视图）与 C3（联合而非分量）尚未被严格满足；缺口 1–3 属"缺证明/缺构造"，不是参数调优。
- **项目级口径**：本轮不改动任何已成立的具体判决。原始 Afshar 直接单方输出仍为 REJECT（EXP-04 §2.2）；PA-VFANN 核心研究问题继续 HOLD。B1 的"可行"仅指**构造路径存在**，不外推为完整协议安全，也不复活任何已 NO-GO 的具体贡献。

---

## 8. 与 B2–B5 的接口（供用户决策）

若继续，B1 的三个缺口决定后续顺序应调整为：

1. **缺口 1（原 B4 的一部分）升为下一优先级**：先给出固定预算状态机的电路级实现与"majority 后轨迹与 \(P\) 无关"的证明。它是 (R) 的地基；此步失败则 B1 的替换失效，应停止。
2. **原 B3（恶意 P1）**：与 B1 正交，可并行；但要独立模拟，不得复用 P2 方向论证。
3. **原 B2（\(\Pi_{init}+\mathsf{CheckBind}+\mathrm{ver}\)）**：在 B1 地基确认后再做；Afshar §2.1 空内存定理不可直接复用。
4. **原 B4 余项**：选定 ORAM 实例、定长/中止规范、逻辑→物理模拟定理。
5. **原 B5**：成本表；若量级仍不利则成本项单独转 REJECT，据此做选题转向。

无论后续如何，**缺口 2（full version 受限）是证据天花板**：除非取得 full version，否则任何"完整联合证明"都只能标为结构性论证。本轮不为此扩文献搜索。

---

## 9. 版本与合规核验

| 项 | 内容 |
| --- | --- |
| 分支 | `exp05-b1-one-sided-simulator`（基线 `8c2e571`） |
| 新增文件 | 仅 `docs/EXP-05-B1-ONE-SIDED-SIMULATOR.md` |
| 未修改 | 代码、CSV、实验数据、EXP-01/02/02A/03A–L/04 全部历史报告 |
| 新增文献 | 无；仅核对已取得的 Afshar 会议版 PDF 与既有报告 |
| 数值验算 | 一次性 shell 穷举，未落盘、未新增代码/数据文件 |
| 判决 | B1 构造可行（ACCEPT 路径存在）／完整证明 HOLD／不停止、不 GO；§7 判决表 |
| `git diff --check` | 提交前执行并通过 |
| 推送 / 远端 HEAD | 提交后核验，见最终汇报 |
