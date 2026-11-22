# PA-VFANN-29 / EXP-06：完整视图模拟可行性审计

> 用户批准进入 L3，目标严格限定为 B1：判断**不含 \(P\)、不接收 \(z\)** 的服务端 P2 完整视图模拟器是否存在可行构造路径。不重审 L2、不混入 B3（恶意客户端）、不改协议、不做性能优化、不搜泛化文献。若发现必须依赖 \(P\) 或 \(z\) 且无法模拟的真实视图分量，记录最小阻断点并停止构造。

## 0. 边界、基线与来源

| 项目 | 值 |
| --- | --- |
| 基线 | `1162f110baf5c631696bd732b38324f6512aebfb`（EXP-05B 补充，用户已核查） |
| 分支 | `exp06-full-view-simulation-audit` |
| 被模拟方 | 恶意服务器 P2，私有输入 = 索引 \(I\) |
| 模拟器输入 | 仅 \((1^\lambda, I, L_S)\)，\(L_S\) 含公开 \(q,E\) 及协议公开参数；**不得含 \(P,z\)** |
| 目标命题 | \(\exists\mathcal S:\ \mathrm{View}_{P2}^{\rm real}(P,I,q,E)\approx_c \mathcal S(1^\lambda,I,L_S)\) |
| 本轮范围 | B1 only；B3（恶意 P1）不在范围 |

来源：Afshar 2015 会议版 PDF（SHA-256 `92ccf8ab…e73d50`），提取文本行号见 §6。既有报告：EXP-04（理想功能/判决表）、EXP-05（B1 z 依赖定位）、EXP-05A/B（语义 A / Π_A 门级非干扰）。验算为一次性内存脚本，未落盘、未新增代码文件（§7 给复现要点）。

---

## 1. 独立判断（结论先行）

**没有发现必须依赖 \(P\) 或 \(z\) 且无法模拟的真实视图分量；因此不触发停止条件。但完整联合模拟器的存在性仍为 UNKNOWN——缺口从"地址轨迹是否依赖 \(P\)"上移为"物理网表忠实性 + 索引初始化绑定 + 严格联合 hybrid"三项，均属缺证明/缺构造，而非反例。整体 HOLD，不 GO。**

三层判决必须分开，不混写：

| 层 | 判决 | 对象 |
| --- | --- | --- |
| L3-a 视图**分量级**联合采样：result + solder + control 同 bucket | **ACCEPT**（条件原始 T⊥+P） | §4.1 联合分布验算 + 隐藏量双射 |
| L3-b 唯一 \(z\) 依赖点（ORAM 逻辑序列）可由 \((I,q,E)\) 替换 | **ACCEPT（结构可行）**，条件语义 A + 物理忠实 Π_A | §4.2 + 原文 §2.1/§3.3 |
| L3-c **完整** transcript 联合模拟器 \(\exists\mathcal S\) 已构造并证明 | **UNKNOWN** | 三缺口，§5 |
| 是否触发停止条件（发现不可模拟的真实分量） | **否** | §5.2 |

---

## 2. EXP-06-A：固定 P2 完整视图对象与依赖标注

以原文 §3.1–3.3 与 Π_A 为基础，列出 P2 在一个完整执行中可观察的全部对象。依赖列标注该对象的分布取决于哪些量；"可模拟性"列判断 \(\mathcal S(1^\lambda,I,L_S)\) 能否在不触碰 \(P,z\) 下生成。

| # | 视图分量 | 原文依据 | 依赖 | 无 \(P,z\) 可模拟？ | 理由 / 条件 |
| --- | --- | --- | --- | --- | --- |
| 1 | 公开参数 \(1^\lambda,E,K,\) bucket 规模 | §3.2 step 1 / §3.4 | 公开 | 是 | 模拟输入自带 |
| 2 | 初始状态 \(st_3=0^n\)、未初始化 block 置零 | §3.2 step 3(c)(d) GetInputpub | 公开常量 | 是 | 由公开常量打开 |
| 3 | check 集 \(S_c\) 及其全开 \(E(i),D(i),GC(i)\) | §3.2 step 2 | P2 随机选 + P1 诚实 garble | 是（条件） | 模拟器对 \(S_c\) equivocate 为"诚实 garbled circuit + wire label"（§3.3）；须与实际 \(P\) 无关——check 电路输入非 \(x_1=P\) |
| 4 | GetInput1 / GetInputpub 发来的 wire label | §3.2 step 3(b)(c)(d) | P1 garble 随机性 | 是 | §3.3：「S sends random wire labels in GetInput1 and GetInputpub」 |
| 5 | GetInput2 的 OT 输出（P2 自己的 share） | §3.2 GetInput2 | \(x_2=I\) 的 share + OT 随机 | 是 | 模拟器从 P2 的 select bit 提取 \(x_2\)，OT 输出由 P2 输入决定 |
| 6 | Solder 公开的 \(\Delta[i,b]\) 与 \(\tau(A)\oplus\tau(A')\) | §3.1 / §3.2 Solder | wire label 随机性 | 是 | §3.3：「equivocates soldering values chosen to map visible labels…, random for non-visible」 |
| 7 | EvalBucket 的 majority 输出 wire label | §3.2 step 3(f) | wire label 随机性 + bucket 正确性 | 是（条件） | 模拟器自定可见 output label 再反推假 GC（§3.3），不经 \(z\) |
| 8 | 控制线 \(\tau(inst(D(i)))\) 打开与解码出的 \(inst_t\) | §3.2 step 3(f)(g) | **逻辑指令序列** | 是（条件） | 模拟器 equivocate \(\tau\) 使可见 label 解码到"期望的模拟 ORAM 指令"（§3.3）；期望序列须由 \((I,q,E)\) 生成而非 \(z\)，见 §4.2 |
| 9 | result 线：活动 label + solder 差；\(\tau_{res}\) **不打开**（\(\mu=0\)） | 本场景规范 μ=0；原始 3(g) 的 \(z\) 在 inst 内 | 结果线随机性 | 是 | §4.1 联合验算：与 \(z\) 无关 |
| 10 | 每轮物理 ORAM 访问模式 | §2.1（隐藏 access pattern） | ORAM 随机性 + 逻辑序列 | 是（条件） | tree-based ORAM 物理模式均匀（§原文 565/572 行）；但原文模拟器 \(S(1^\lambda,z)\) 生成的是**逻辑** inst 序列，见 §4.2 |
| 11 | abort 事件 / 时机 / 原因 | §3.2 step 2、3(g) | check 失败、authenticity 失败 | 是（条件） | §3.3：「aborts if these wire labels are not the pre-determined visible output wire labels」——用预设 label，不含 \(z\) |
| 12 | 通信元数据：消息数、长度、轮数、顺序 | 协议结构 | 固定预算 \(E\) + bucket 规模 | 是（条件） | 须定长规范（B4）；\(\mathrm{StopTrace}\) 由 \(t=E\) 强制（Π_A），不含 \(P,z\) |

**标注要点**：#8 是原始的 \(z\)-承载点（指令序列），#9 是结果承载点。二者**出自同一 EvalBucket 输出、经 majority 耦合**，不能拆开后分别宣称隐私——§4.1 专门做联合分析。#10 的原文证据显示模拟器输出逻辑 inst 序列，P2 实际可见的是每轮解码的 \(inst_t\)（#8），物理访问模式由 ORAM 机制隐藏。

---

## 3. EXP-06-B：模拟器构造（只用 \(1^\lambda,I,L_S\)）

按原文 §3.3 P2 腐化模拟器的 7 个动作逐项改写，保证每步输入可追溯：

| 原文动作（§3.3） | 原输入 | 改写后输入 | \(z/P\) 是否进入 |
| --- | --- | --- | --- |
| A. 模拟 \(F_{com}\) commit 消息 | 公开 | \(1^\lambda\) | 否 |
| B. check 集 opening equivocate 为诚实 GC/label | 随机 garble | \(1^\lambda\) + 诚实 garble 采样 | 否（check 电路不含 \(x_1=P\)） |
| C. GetInput1/GetInputpub 发随机 label；GetInput2 模拟 OT 输出 | 随机 + P2 输入 | 随机 + \(I\) | 否 |
| D. 从 select bit 提取 \(x_2\) | P2 select bit | \(I\)（P2 自身输入） | 否 |
| E. **发 \(x_2\) 给理想功能、收 \(z\)、生成模拟 ORAM 序列** | \(z\) | **由 \((I,q,E)\) 计算逻辑序列** | **本轮替换点** |
| F. Solder：可见 label 映射、非可见随机 | 可见 label（自定） | 自定可见 label | 否 |
| G. 反推假 GC + equivocate \(\tau(inst)\) | 期望模拟指令 | 由 \((I,q,E)\) 生成的指令 | 否（替换后） |
| H. 3(g) abort：label ≠ 预设可见 label 则中止 | 预设可见 label | 预设可见 label | 否 |

**动作 E 的替换是全部关键**。原文 P2 模拟器依赖 \(z\) 的完整链条只有：E 收到 \(z\) → 生成模拟 ORAM 指令序列 → G 令 \(\tau(inst)\) 解码到该序列。EXP-05A/B 已证语义 A + Π_A 下逻辑访问轨迹 = \(F(I,q,E)\)，与 \(P\) 无关；而 \(I\) 是 P2 自身输入、\(q,E\in L_S\)。故定义

\[
\mathcal S_E(I,q,E)\ :=\ \text{运行 } \Pi_A \text{ 的公开控制函数，输出逻辑指令序列 } \mathbf{inst}=(inst_1,\dots,inst_E),
\]

它不读 \(z\)。随后 G 按原文方式 equivocate \(\tau(inst(D(i)))\)，使可见 output label 解码到 \(\mathcal S_E\) 给出的指令。这条路径结构自洽，与原文动作 G「自定可见 label 再反推假 GC」一致，**不走** §2.2 garbling simulator 的 \(\mathrm{Sim}(f,x,D|_{*f(x)})\) 路径（那条路径的输入含结果 \(f(x)\)，看似逼模拟器知道 \(z\)）——原因见 §4.3。

---

## 4. EXP-06-C：联合分析与最小阻断点搜索

### 4.1 核心联合验算：同 bucket 的 control + result 视图与 \(z\) 无关

建模一个 EvalBucket 的两条输出线：控制线承载 \(inst_{ctrl}\)，结果线承载 \(z\)。原始 Afshar 随机结构：\(\tau\) 逐 wire 独立、跨电路无共享 offset（§3.1“forgoing common wire offsets”），point-and-permute 满足 \(\mathrm{lsb}(W[b])=b\)、活动 label \(W[\tau\oplus v]\) 的 lsb 为 \(\tau\oplus v\)（\(\tau\) 隐藏则该位隐藏）。Solder 打开 \(\Delta[i,b]=W_j[b]\oplus W_h[\delta\oplus b]\) 与 \(\delta=\tau_j\oplus\tau_h\)；控制线 \(\tau\) 经 3(f) 打开，结果线 \(\tau\) 不打开（\(\mu=0\)）。

穷举 \(\lambda=3\)、全部 4 条 wire 描述（head/j × control/result）：

- **联合视图**（control 活动 label + control solder + 打开的 \(\tau_{ctrl}\) + result 活动 label + result solder + \(\delta\)）在 \(z=0\) 与 \(z=1\) 下**逐点相等**：支持集 65536 = 65536，分布全等。
- 按 **256 个 control 分支逐条件化**，每个分支内 result 分布 \(z=0\) 与 \(z=1\) 仍相等——控制线打开不替结果线"开后门"。
- 补正说明：一次建模曾把 lsb 误编为 \(\tau\oplus b\)，导致 \(z\) 直接落在 lsb 上而误判泄露；按原文 §2.2 的 \(\mathrm{lsb}(W[i,b])=b\) 更正后结论如上。这一步本身说明为何必须用原文定义而非直觉编码。

结论：在原始 T⊥+P 结构下，**同一 bucket 内结果线的完整可见量与 \(z\) 无关，且与控制线联合后仍无关**。这是"不能拆开分别证明"要求的直接回答。

### 4.2 \(z\) 依赖点的可替换性（原文依据）

原文 §2.1 对 ORAM 的安全定义（提取文本 122–124 行）为：存在模拟器 \(S\) 使 \(S(1^\lambda,z)\approx I(\Pi,M,x_1,x_2)\)，其中 \(I(\cdot)\) 是 **\(inst\) 变量序列（逻辑指令序列）**，且限于 **initially empty \(M\)**。§3.3 模拟器用 \(z\) 正是为了生成这条逻辑序列。

替换依据分两步：
1. EXP-05B 补充已在 primitive 门级 + RO-RAM + 公开初始化 + (N-r) 下证明 \(\forall t\ Q_t,V_t,ptr_t,t\) 与 \(P\) 无关，故 \(\mathrm{AddrTrace},\mathrm{StopTrace}\) 与 \(P\) 无关；语义 A 的 post-filter 使结果累加 \(R_t\) 不回灌地址/停止逻辑。因此逻辑指令序列由 \((I,q,E)\) 确定，模拟器的 \(\mathcal S_E\) 有定义。
2. 原文 §3.2 每轮 P2 实际解码并可见的正是 \(inst_t\)（#8）；物理访问模式由 ORAM 隐藏（§原文 565/572 行明确 tree-based ORAM 物理模式均匀、可从真实切换到模拟）。因此"模拟逻辑序列"足以覆盖 P2 在指令层面的视图。

**力度边界**：原文模拟器 \(S(1^\lambda,z)\) 是**通用** ORAM 编译器性质（任意 \(\Pi\)、任意输入）；\(\mathcal S_E\) 是**本场景特定**固定预算状态机的确定性轨迹函数。用后者替代前者不是"复用原文定理"，而是"在更强的语义 A 前提下绕过对 \(z\) 的需求"——这使构造更简单，但依赖 Π_A 的物理实现确实忠实（缺口①，§5.1）。

### 4.3 为何结果线标签不需要 \(z\)（batching equivocation 的关键辨析）

表面障碍：§2.2 garbling 安全的 simulator 输入含 \(D|_{*f(x)}\)，结果分量即 \(z\)，似乎逼模拟器知道 \(z\)。但在 batching 下不成立：原文动作 G 是**先自定可见 output wire label、再反推一个只用这些可见 label 的模拟 GC**，不走 §2.2 的 \(\mathrm{Sim}(f,x,D)\) 路径（不需要对 \(f(x)=z\) 的先验知识）；再叠加结果线 \(\mu=0\) 部分解码、且结果是**终止输出**（不进入下一轮 bucket 的 solder/地址），result 活动 label 可由隐藏量双射采样生成。§4.1 的联合验算把这一辨析落实到"与 control 联合后仍与 \(z\) 无关"。

### 4.4 最小阻断点搜索：逐个分量找反例，均失败

| 候选阻断点 | 是否存在真实区分事件 | 判定 |
| --- | --- | --- |
| result label 暴露 \(z\) | 否（§4.1 联合验算 \(z=0\equiv z=1\)） | 非阻断 |
| control 线 \(\tau\) 打开泄露 \(P\) 或 \(z\) | 否（\(\mathcal S_E\) 由 \((I,q,E)\) 生成；result 分支条件化后仍无关） | 非阻断 |
| Solder \(\Delta\) / \(\tau\) 差跨电路关联泄露 | 否（原始 T⊥+P 结构；T= 已被 EXP-03L 排除为非合法实例化） | 非阻断 |
| check/eval 联合泄露 | 否（check 电路输入非 \(P\)，§3.3 equivocate 为诚实 GC） | 非阻断 |
| ORAM 序列必须经 \(z\) | 否（语义 A 使序列 =\(F(I,q,E)\)，§4.2） | 非阻断（条件物理忠实） |
| abort / 消息长度泄露 | 否（预设 label + 定长规范 B4；\(\mathrm{StopTrace}\) 强制 \(t=E\)） | 非阻断（条件定长） |

**未发现任何必须依赖 \(P\) 或 \(z\) 且无法模拟的真实视图分量。** 停止条件（用户定义：发现此类分量即停）不触发。

---

## 5. 判决表与整体判决

### 5.1 判决表

| 检查项 | 结果 | 论证 / 缺失证据 |
| --- | --- | --- |
| 同 bucket control+result 联合视图与 \(z\) 无关 | **ACCEPT**（条件 T⊥+P） | §4.1 联合验算（65536 支持集逐点相等 + 256 分支条件化） |
| result label 无需 \(z\) 可采样 | **ACCEPT** | §4.3 equivocation 辨析 + μ=0 + 终止输出 |
| 唯一 \(z\) 依赖点可替换为 \((I,q,E)\) | **ACCEPT（结构可行）** | §4.2，条件：语义 A + 物理忠实 Π_A |
| 各分量（1–12）无 \(P/z\) 可模拟 | **ACCEPT（分量级，条件逐项列出）** | §2 表 + §4.4 |
| **完整 transcript 联合模拟器 \(\exists\mathcal S\) 已证明** | **UNKNOWN** | 三缺口 §5.2；原文 §3.3 仅 overview、full version 受限 |
| 物理网表忠实于 Π_A | **UNKNOWN** | 无实现；cut-and-choose 只保证 garble 忠实于 \(\Pi\)，不保证已实现的 \(\Pi=\Pi_A\) |
| 索引初始化 / 认证根绑定（B2） | **UNKNOWN（不在本轮范围）** | 原文 §2.1 定理限 initially empty \(M\)，非空索引的 \(\Pi_{init}\) 须另证 |

### 5.2 阻止升级为无条件 ACCEPT 的三个缺口（均为缺证明，非反例）

1. **物理忠实性**：L3-b 的替换依赖真实实现的 \(\Pi\) 等于 Π_A（含 primitive 门表、RO-RAM、N-r、公开初始化）。仓库无门级网表，cut-and-choose 只保证 garble 忠实于给定 \(\Pi\)。若实现改用语义 B 队列键或让 \(r\) 进地址，立即落入 Π_B 的 REJECT（EXP-05B）。
2. **索引初始化绑定**：原文 ORAM 定理限 initially empty \(M\)；本场景 \(I\) 是非空索引。模拟器输入含 \(I\) 是假设 \(I\) 已被正确提供给真实执行双方；"如何保证真实初始内存等于承诺的 \(I\)"是 B2，未闭合。
3. **严格联合 hybrid**：§4.1 的验算是分量联合（同一 bucket 的 control+result），不是**全 transcript**（GC 反推 + check 全开 + Solder + ORAM + abort 全部消息）的联合分布证明；原文 §3.3 明确 "only an overview… complete details deferred to full version"，full version 未获取。控制线与 result 出自同一 EvalBucket 经 majority 耦合，逐分量等价 ≠ 全 transcript 等价。

### 5.3 整体判决

**HOLD（不 GO，不停止）。** 用户停止条件是"发现一个必须依赖 \(P\) 或 \(z\) 且现有协议无法模拟的真实视图分量"——本轮未发现（§4.4 全部分量检查失败），故不停止。但同时三个缺口使完整联合模拟器未证明，不足以 GO。项目级口径：原始 Afshar 直接单方输出仍 REJECT（EXP-04 §2.2）；PA-VFANN 核心研究问题继续 HOLD；本轮分量级 ACCEPT 不外推为完整协议安全，也不复活已 NO-GO 的具体贡献。

---

## 6. 原文与源码依据

| 依据 | 定位（提取文本行） | 用途 |
| --- | --- | --- |
| ORAM 安全 = \(S(1^\lambda,z)\approx I(\Pi,M,x_1,x_2)\)，限 initially empty \(M\) | §2.1，122–124 行 | §4.2 替换论证的原文锚点 |
| tree-based ORAM 物理模式均匀、可从真实切模拟 | §正文 565、572 行 | #10 物理访问可模拟 |
| point-and-permute \(\mathrm{lsb}(W[i,b])=b\)，\(W[i,W[i,2]]\) 编码 false | §2.2，130 行 | §4.1 联合验算的正确编码 |
| Solder：开 \(\tau(A)\oplus\tau(A')\) 与 \(\Delta[i,b]\) | §3.1，190 行 / §3.2 250–277 行 | #6 + 联合验算模型 |
| “forgoing common wire offsets between circuits” | §3.1，205 行 | T⊥+P 结构依据 |
| 3(f) 对全 bucket 开 \(\tau(inst(D(i)))\)；3(g) `\tau(inst)` 双方解码 | §3.2，343 行 | #8 + 原始 \(z\) 承载点 |
| P2 腐化模拟器 7 动作，唯一 \(z\) 依赖在动作 E | §3.3，370–380 行 | §3 构造表 |
| “visible labels decode to next simulated ORAM instruction” | §3.3，378–380 行 | 动作 G equivocation |
| §3.3 仅 overview，细节在 full version | §3.3，347–349 行 | 缺口 3 |
| Π_A primitive 门级非干扰 + 归纳 | EXP-05B 补充 §2–§4 | §4.2 逻辑序列 =\(F(I,q,E)\) |

## 7. 验算复现要点

内存脚本（未落盘）：(1) 枚举 \(\lambda=3\) 全部 wire 描述（\(\tau\in\{0,1\}\)、两条 label 高位各 2 bit、\(\mathrm{lsb}(W[b])=b\)），对 head/j × control/result 四组描述构造联合视图；比较 \(z=0/1\) 分布字典（含 `Fraction` 归一化），得逐点相等（支持 65536）。(2) 按 control 分支分组，逐组比较 result 边缘分布（256 组全等）。(3) T= 多结果位区分器复核：\(\tau=\Delta[k]\) 且同 offset 跨 wire 时 \((\text{lsb差})\) 在 \(z=(0,0)\) 与 \((0,1)\) 下支持不相交——与 EXP-03K/03L 一致，属非合法实例化，非本轮攻击。本轮未搜新文献、未写代码/数据文件、未改历史报告。
