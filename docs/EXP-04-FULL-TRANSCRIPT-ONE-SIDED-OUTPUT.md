# EXP-04：完整 Transcript 与单方输出可行性审计（立项决策关口）

> 项目：PA-VFANN-25。协议级审计，不写代码、不改实验数据、不改 EXP-03A–L 历史报告、不扩文献、不为得到 GO 降低安全标准。
> 目标：判断 Afshar 2015 batching（§3）的恶意安全 RAM 机制能否改造为「只有客户端得到最终结果、完整执行轨迹仍满足安全要求」的协议，并给出立项决策关口所需的明确判决。
> 停止条件：原文足以确定的按原文判定；原文未明确的一律标记 UNKNOWN 并写明缺什么证据；不把局部结论外推为完整协议安全性。

---

## 0. 交付与证据状态

| 项 | 内容 |
| --- | --- |
| 基线 commit | `71c95b68399cc839175de61def134ee0b86f92c3`（EXP-03L 最终 HEAD） |
| 分支 | `exp04-full-transcript-one-sided-output` |
| 新增文件 | `docs/EXP-04-FULL-TRANSCRIPT-ONE-SIDED-OUTPUT.md`（本文，唯一新增） |
| 一手来源 | Afshar, Hu, Mohassel, Rosulek, *How to Efficiently Evaluate RAM Programs with Malicious Security*, EUROCRYPT 2015 Part I, LNCS 9056, pp. 702–729, DOI `10.1007/978-3-662-46800-5_27`；Springer 官方会议版 PDF，810,112 字节，SHA-256 `92ccf8ab8014f4fd50eba8641369ee52fe5ae4dc5a349daad2466f9f5ee73d50`（与 EXP-03L 同一文件） |
| 引用格式 | 「§x.y，PDF p.X，印刷页 Y」；提取文本行号见于括号 |
| 证据限制 | full version Appendix D 本环境受限，会议版 §3.3 明确「complete details deferred to full version」；凡会议版未逐字写明处，一律标为结构性论证或 UNKNOWN |

**一句话判决：HOLD。** 原始 Afshar batching **不能**直接提供单方输出（REJECT，有原文硬证据）；但改造路线没有被证明不可能。当前存在 5 个明确、有限、可列出的阻断项，其中两个是决定性的——**无 \(z\) 的恶意服务端完整视图模拟器**与**索引初始内存/认证根绑定**（Afshar §2.1 的安全定理明确只对 initially empty \(M\) 成立）。因此既不 GO 进入原型，也不 NO-GO 关闭 PA-VFANN 核心问题。

---

## 1. 任务 1：固定理想功能与角色

### 1.1 参与方与输入

沿用 EXP-03E 修正后的角色映射（P1 = Garbler/Client，P2 = Evaluator/Server）：

| 参与方 | 私密输入 | 公开/共享输入 | 输出 |
| --- | --- | --- | --- |
| Client = P1 | 策略 \(P\)、凭证 \(\mathrm{Cred}\)、查询 \(q\)（若 \(q\) 保密） | \(E,M,K,\mathrm{ver},R_I\)，公开参数 | \(R_C\)（结果） |
| Server = P2 | 索引 \(I\)（作为 \(x_2\) 进入内部状态） | 同上 | \(\bot\) |

**\(q\) 的归属需明写**：既有 EXP-03F/G 把 \(q\) 放入 \(L_S\)（允许泄露）。本轮沿用该设定；若后续要求 \(q\) 也保密，则 \(q\) 必须走 `GetInput1`（P1 独占开 label），\(L_S\) 收缩，服务端模拟器可行域反而更小——不会使本协议更容易，只会更难。故本轮不扩大 \(L_S\)。

### 1.2 理想功能

\[
\mathcal F_{\mathrm{retrieve}}(P,\mathrm{Cred},q,I)\ \to\ (R_C,\bot_S)
\]

- **凭证检查**：\(\mathsf{VerifyCred}(\mathrm{Cred},P,\mathrm{ver})=1\)，否则输出固定拒绝（长度固定，与 \(\bot_S\) 不可区分）。
- **计算**：\(z=\mathsf{FilteredAnnStateMachine}(I,q,P,E)\)，含义限定为 EXP-03C/G3-alg 的固定预算检索状态机输出，**不是**全局精确 Top-K（EXP-03A 的反例仍然有效）。
- **输出形态**：\(R_C\) 为定长 \(K\) 槽的「记录 ID + 距离」二元组；不足 \(K\) 条用不可区分 dummy 补齐。定长是防止消息长度泄露的必要条件。是否只给 ID 不给距离属接口选择，不影响本轮安全结论。
- **允许泄露**：\(L_S=(R_I,\mathrm{ver},q,E,K,M,\text{公开参数})\)，加上服务端自身输入 \(I\) 作为腐化方辅助输入。\(R_C\) 与 \(P\) 均不在 \(L_S\) 中。

### 1.3 四个性质必须分开定义（不得互相代替）

| 性质 | 定义 | 失败条件 |
| --- | --- | --- |
| 输出隐私 | \(\mathrm{View}_S(P,I,q)\approx \mathrm{Sim}_S(I,L_S)\)，模拟不需要 \(R_C\) 或 \(P\) | 模拟器必须知道 \(z\) 或 \(P\) |
| 执行完整性 | \(R_C\) 等于诚实执行 \(E\) 轮状态机的输出 | 电路错误、输入不一致、ORAM 执行错 |
| 授权正确性 | 通过 \(\mathsf{VerifyCred}\) 才产出结果，且结果不超出凭证授权范围 | 绕过检查或越权读取 |
| 轨迹隐私 | 服务器观察到的逻辑与物理访问、停止点、中止、消息长度与 \(P,z\) 无关 | 任一分量与 \(P\) 或 \(z\) 统计相关 |

### 1.4 中止的双方恶意定义

- **DoS 不可阻止**：任一方拒发消息都可使协议停止；安全定义只要求中止事件本身不携带 \(P\) 或 \(z\) 的信息。
- **选择性中止**：必须证明中止概率在 \(z=0/1\) 与不同 \(P\) 下不可区分；定长消息、固定 \(E\)、固定 halt 时刻是必要条件。
- **双方不对称**：恶意 P2 中止影响的是「客户端是否收到结果」，恶意 P1 中止影响的是「服务端是否被探测」。两个方向的模拟器必须分别给出，不能互相代替（§3）。

---

## 2. 任务 2：重建 batching 完整 transcript

### 2.1 原文流程逐项（§3.2，PDF pp.12–14，印刷页 713–715）

| # | 阶段 | 原文动作 | P2 可见 | 依赖 \(P\) | 依赖 \(z\) |
| --- | --- | --- | --- | --- | --- |
| 1 | 电路生成 | \(N=O(sT/\log T)\)，各 \(E(i),D(i)\) 独立采样并对分量 \(F_{xcom}\) 承诺，\(GC(i)=\mathrm{Garble}(\Pi,\tilde E(i),D(i))\) 对 \(F_{com}\) 承诺（step 1） | 仅承诺 | 否（输入前） | 否 |
| 2 | cut-and-choose | P2 选 \(S_c\)（一半），P1 开 \(E,D,GC\)，P2 验 \(GC(i)\in\mathrm{Garble}\)（step 2） | 开集全部 | 否 | 否 |
| 3a | bucket/head | P2 选 \(B_t\subset S_e\)（\(\Theta(s/\log T)\)）与 \(hd_t\) 并公告，\(S_e:=S_e\setminus B_t\) | 是（P2 自选） | 否 | 否 |
| 3b | 随机带输入 | `GetInput1`/`GetInput2`（OT），见 step 3(b) | OT 输出 label | 否 | 否 |
| 3c | 状态输入 | \(\Delta_{st}=\mathrm{Solder}(st(D(hd_{t-1})),st(E(hd_t)))\)，`Adjust`；首轮 \(x_1\) 走 `GetInput1`，\(x_2\) 走 \(n\)-wise share | solder 差值 | 否（\(x_1=P\) 被 label 隐藏） | 否 |
| 3d | 内存块输入 | 读未初始化/非读 → `GetInputpub(0^n)`；读最近写 → `Solder`+`Adjust` | block label | 逻辑序列（语义 A 下否） | 语义 A 下否 |
| 3e | MkBucket | 各 \(j\) 的 \(\Delta(hd\to j),\Delta(j\to hd)\)、\(\Delta(hd\to hd)=0\) | 全部 solder 差值 | 否 | 否 |
| 3f | 评估 | P1 开 \(GC(i)\) **与 \(\tau(inst(D(i)))\)**（全部 \(i\in B_t\)），P2 执行 `EvalBucket` 得 \(Y_t\) | 控制线解码信息 | 控制线（语义 A 下否） | 语义 A 下否 |
| 3g | 输出真实性 | P2 送 \(\tilde Y=inst(Y_t)\) 给 P1；**双方**解码 \(inst_t=\mathrm{lsb}(\tilde Y)\oplus\tau(inst(D(hd_t)))\)；P1 验 membership；若 \(inst_t=(halt,z)\) **双方**以 \(z\) 输出（step 3(g)） | 控制线明文 + \(z\) | 是（经 \(z\)） | **是** |
| 4 | 中止/异常 | cut-and-choose 失败、solder 检测失败、membership 失败 → abort | 中止事件 | 待证 | 待证 |
| 5 | 物理访问 | \(inst\) 序列即 §2.1 的 \(I(\Pi,M,x_1,x_2)\)；§3 未逐条列出物理 ORAM 消息 | 服务器亲自执行 | 语义 A 下逻辑否；物理依 ORAM 实例 | 原文模拟器用 \(z\) |

### 2.2 「原始机制直接提供单方输出」= REJECT

硬证据三条，均为原文事实：

1. §2.1：`do until inst has the form (halt,z) ... output z` —— \(z\) 是 `inst` 的一个域，不是独立输出线（提取文本第 109–111 行）。
2. §3.2 step 3(f)：P1 对**所有** \(i\in B_t\) 打开 \(\tau(inst(D(i)))\)（第 343 行）——控制与结果共用同一解码信息。
3. §3.2 step 3(g)：「**Both parties** decode the output … If \(inst_t=(halt,z)\), then **both parties** halt with output \(z\)」（第 343 行）。

因此沿用原始接口，服务端必然得到 \(z\)。用户此前提出的 \(inst\_ctrl/result\) 拆分是**必需的协议改写**，不是可选优化。这与 EXP-03G §1.1 一致，本轮不推翻。

### 2.3 模拟器审计：原文模拟器都用 \(z\)，且不能直接用

§3.3 原文（PDF p.14，印刷页 715，第 368–380 行）：

- **P1 腐化**：`S can extract P1's input x1 … sends x1 to the ideal functionality and receives the output z. Then S generates a simulated ORAM memory-access sequence.`
- **P2 腐化**：`It sends x2 to the ideal functionality and receives the output z. Then S generates a simulated ORAM memory-access sequence.` 并且 `S also equivocates on the decommitment to the decoding information τ(inst(D(i))), chosen so that the visible output wires will decode to the next simulated ORAM memory instruction.`

**不允许的秘密信息检查**：在 \(\mathcal F_{\mathrm{retrieve}}\) 下，理想功能给 P2 的输出是 \(\bot\)。所以 P2 腐化模拟器**无法**执行上述 `receives the output z` 一步。这是单方输出改造的核心断点，不是措辞问题。

**唯一可行的替代路径**（结构性论证，非原文定理）：

- 控制线改造为 \(inst\_ctrl\)，以固定 \(t=E\) 强制 halt，\(z\) 移到独立 `result` 线且 \(\mu=0\)（不开 \(\tau(result)\)，§2.2 部分解码性质）；
- 逻辑访问序列在语义 A + 固定 \(E,M\) + dummy 下是 \((I,q,E)\) 的确定函数，故可由 \((I,L_S)\) 生成，**不需要 \(z\)**（承接 EXP-03E 修正、03F §5.4、03G §4.3）；
- 物理 ORAM 序列再经所选 ORAM 的模拟器由逻辑序列生成——注意 Afshar §2.1 的 ORAM 定义模拟器输入是 \(z\) 而非逻辑序列（第 120–124 行），这里替换成了一个更强的、需要单独实例化 ORAM 的性质。

**结论**：替换路径在结构上自洽，但**完整 transcript 的联合模拟从未证明**。EXP-03H–L 只证明了 result 线的局部联合视图在原始 \((T\perp)+P\) 随机结构下与 \(z\) 独立；没有覆盖「GC equivocation + 控制线指令 equivocation + result 活动 label + ORAM 物理序列 + 中止分支」的联合分布。这正是 EXP-03G §6.2 命题 3 的第 3、5、6 项，仍未闭合。

---

## 3. 任务 3：两个腐化方向分别审计

### 3.0 一项独立更正（不修改旧报告）

EXP-03H §4.2 声称「P2 能从 solder 差值算出 head 结果线的**两条** label（含互补 label）」。按 §3.2 `Solder` 的原文定义逐字重推：

\[
\Delta[i,b]=A[i,b]\oplus A'[i,\delta\oplus b],\quad b\in\{0,1\},\ \delta=\tau(A)\oplus\tau(A').
\]

P2 Evaluating 电路 \(j\) 得活动 label \(Y_j=D(j)[i,b_j]\)，故
\[
Y_j\oplus\Delta[i,b_j]=D(hd)[i,\delta\oplus b_j]
\]
是**活动** head label；要算互补 label \(D(hd)[i,\delta\oplus b_j\oplus1]\)，需要 \(\Delta[i,b_j\oplus1]\oplus D(j)[i,b_j\oplus1]\)，而 \(D(j)[i,b_j\oplus1]\) 是电路 \(j\) 的互补 label，§2.2 明确不可预测。作者（EXP-03H）在那一步隐含假设 P2 已知 \(D(j)\) 的互补 label。

小域穷举验证（\(\lambda=3\)，遍历所有合法 label 对、\(\tau_j,\tau_h\in\{0,1\}\)、\(b_j\in\{0,1\}\)）：256 个不同的 P2 可见状态 \((\delta,\Delta[i,0],\Delta[i,1],b_j,Y_j)\) 中，**活动 head label 在 256/256 状态下唯一确定**，而**互补 head label 在 256/256 状态下都不唯一确定**（例如可见值 \((0,0,0,0,0)\) 对应互补 label ∈ {1,3,5,7}）。

**后果**：EXP-03H §4.2 的「authenticity 资源受损」结论应撤回；原始结构下互补 label 不可预测性**保持**。这使 result 线的 label-level authenticity 更强（见 §3.1），但**不改变**输出隐私的结论（隐私靠 \(\mu=0\) 与局部联合引理，不靠互补 label 被暴露）。按用户约束，本轮不修改 EXP-03H 旧报告，仅在此登记更正。

### 3.1 恶意 Server（P2）

| 攻击面 | 判定 | 依据 |
| --- | --- | --- |
| 伪造/替换输出 label | **受阻（label 级）**。§3.0 更正后 P2 只有活动 result label，无互补 label；P1 做 \(D_{result}(hd_E)\) 逐位置 membership，跨位置 label 是独立随机值。 | §2.2 不可预测性；§3.2 3(g)；EXP-03G §3.3 |
| 跨会话/跨 timestep 重放 | **受阻**（前提：P1 必须绑定到本会话本轮 \(D_{result}(hd_t)\)）。§3.2 step 1 每电路独立采样，无跨会话复用；check 电路与 eval 电路不相交（EXP-03L §1.3）。 | §3.2 step 1–2 |
| 跨电路标签关系伪造 | **受阻**。EXP-03L：原始放弃跨电路共享 offset，check 打开不泄露 eval 的 \(\Delta\)；solder 只开差值。 | §3.1（印刷 710）；EXP-03L §1.2 |
| 提前终止/顺序/长度泄露 | **结构性受阻但未证**。固定 \(E\)、halt 强制在 \(t=E\)、\(\mu=0\) ⇒ P2 看不到结果位，无法按 \(z\) 中止；但**中止消息必须定长**这一工程约束 Afshar 未写，需新增。 | §3.2 3(g)；§2.2 |
| 让 Client 接受错误结果 | **label 级受阻，正确性级 UNKNOWN**。前者见上；后者依赖电路正确性（cut-and-choose）、输入一致性（\(x_2=I\) 绑定）、ORAM 正确与索引绑定——后两项未闭合（§4）。 | §3.2 step 2；§4.2 |

**总判定：UNKNOWN**。没有任何一条攻击构成对原始 Afshar 的成功攻击；但恶意 P2 的**完整视图模拟器**（不使用 \(z\)）未构造，且它正是 §3.3 原证明的核心。缺少的证据：命题 3 的联合不可区分证明、定长中止规范、索引绑定。

### 3.2 恶意 Client（P1）

| 攻击面 | 判定 | 依据 |
| --- | --- | --- |
| 选择输入操纵执行路径 | **结构性受阻**。语义 A 下逻辑轨迹与 \(P\) 无关；P1 作为 garbler 看不到 P2 的 OT 选择（\(x_2=I\)）。 | EXP-03E/F；§3.2 3(b) |
| 重复请求探测索引 | **UNKNOWN**。服务器只见到 \((I,q,E)\) 决定的逻辑序列与自身执行的物理序列；同 \(q\) 重复不应新增信息。但多查询下 \(\mathrm{ver}\)、nonce、\(\rho\) 的累积泄露 EXP-03F §4.4 已标未定义。 | EXP-03F §4.4 |
| 恶意策略/凭证越权 | **UNKNOWN**。\(\mathsf{VerifyCred}\) 只在理想功能层定义，协议层是否在电路内实现、如何与 \(R_I\) 绑定未给出；cut-and-choose 只能保证电路按 \(\Pi\) 正确 garble，不能保证 \(\Pi\) 本身实现了凭证检查。 | §1.2；§3.2 step 2 |
| 提取超授权数据 | **结构性受阻（在同一 \(L_S\) 下）**。P2 只把 \(inst(Y_t)\) 与 result label 送回 P1；block 线 label 不回传，且 P1 不知道 P2 的 OT 选择。新增 result 线必须严格限于授权字段。 | §3.2 3(g) |

**总判定：UNKNOWN**。P1 腐化模拟器在原文中可拿 \(z\)（P1 本就是结果接收方，这不违反单方输出），但 result 线加入后需要重写 P1 腐化模拟器以处理它自己生成的结果 label；且 \(\mathsf{VerifyCred}\) 的电路内实现与输入一致性 \(x_1=P\) 的约束未闭合。**不得用 P2 腐化模拟器的论证代替本方向。**

---

## 4. 任务 4：两个尚未闭合的问题

### 4.1 ORAM 与轨迹隐私

| 层次 | 状态 | 关键边界 |
| --- | --- | --- |
| 逻辑 RAM 访问 | 语义 A 下是 \((I,q,E)\) 的确定函数 | 依赖「策略不影响队列优先级、dummy 补齐」这一程序性质；语义 B 下 EXP-03E 的否定结论仍成立 |
| ORAM 物理访问 | **UNKNOWN** | Afshar §2.1 的 ORAM 模拟器以 \(z\) 为输入（`S(1^\lambda,z)\approx I(\Pi,M,x_1,x_2)`），且只定义于 initially empty \(M\)；本轮需要的是「给定逻辑序列 → 物理序列」的标准 ORAM 性质，需实例化 ORAM 后另证 |
| dummy access | 逻辑 dummy 仍触发物理访问 | 若跳过物理访问则真实/ dummy 可从次数区分；必须照常执行 ORAM 步骤 |
| 访问次数 | 由 \(E,M\) 与 ORAM 实例决定 | **\(E\cdot M=1600\) 是逻辑邻居读，不是物理 ORAM 访问数**（EXP-03F §5.3 保留） |
| 停止位置 | 固定 \(t=E\) | 必须改写 §2.1 的 `do until halt` 语义；属程序改写，非新原语 |
| abort / 消息长度 / 时序 | UNKNOWN | 定长、定时不是 Afshar 的明文要求，需新增规范并证明与 \(P,z\) 独立 |

**判定：UNKNOWN。** 缺少三样证据：(i) 语义 A 在电路级的实现与证明；(ii) 选定 ORAM 实例及其「逻辑序列→物理序列」模拟定理；(iii) 定长/中止规范。不得把「固定逻辑读取次数」写成「物理轨迹隐私」。

### 4.2 索引初始化与认证根绑定

**原文硬边界**：§2.1 明写 `memory M ... initially set to 0^n`，且 ORAM 安全定义限于 `for all x1,x2 and initially empty M`（第 105、120–124 行）。§3.2 step 3(c) 中 \(x_2\) 进入 \(st:=x_1\|x_2\|0^n\)，**不进入内存**；step 3(d) 对未初始化读走 `GetInputpub(...,0^n)`。

因此：

- 「服务器持有索引」≠「索引已在 RAM 内存中」。必须新增初始化程序 \(\Pi_{init}\) 把 \(I\) 写入 ORAM，成本含 \(O(s|I|)\) OT 与 \(O(|I|)\) 次写（EXP-03F §3.2），本轮只定义要求不设计系统。
- **认证根绑定**：\(R_I=\mathsf{Commit}(I)\) 是对明文的承诺；Afshar 内存是 wire-label 表示，二者之间没有天然对应。必须在电路内做 \(\mathsf{CheckBind}(I_{loaded},R_I,\mathrm{ver})=1\)（EXP-03F §3.3），否则恶意服务器可替换块。
- **防回滚**：\(R_I\) 必须含 \(\mathrm{ver}\)，并在电路内绑定到初始 \(st\) 且由客户端核验；Afshar 原协议**没有跨执行状态概念**，这是新增需求。
- **动态更新**：超出本轮模型，不设计。

**判定：UNKNOWN**，并附一条明确的 REJECT 子结论：**Afshar §2.1 的安全定理不能直接用于非空初始内存**，因此「按原文定理即可覆盖索引加载」是不成立的。缺少的证据：初始化程序、\(\mathsf{CheckBind}\) 电路构造、版本防回滚规范，以及三者与 §3 证明的组合证明。这是本轮最大的单一缺口。

---

## 5. 最终判决表

| 检查项 | 结果 | 论证 / 反例 / 缺失证据 |
| --- | --- | --- |
| 原始 Afshar 机制能否直接提供单方输出 | **REJECT** | §2.1 `inst=(halt,z)`；§3.2 3(f) 对全 bucket 开 \(\tau(inst)\)；3(g) 双方解码并以 \(z\) 输出。硬证据，无需新反例。 |
| 输出隐私模拟 | **UNKNOWN** | 原文两个模拟器都 `receives the output z`；\(\mathcal F_{retrieve}\) 给 P2 的是 \(\bot\)。局部 result 线引理保留，但完整 transcript 联合模拟未证；缺 (i) 语义 A 电路级证明 (ii) ORAM 实例与物理模拟 (iii) 命题 3 联合不可区分。 |
| 输出真实性 | **UNKNOWN**（细分：label 级 **ACCEPT**，正确性级 **UNKNOWN**） | label 级：§3.0 更正后互补 label 不可预测，P1 逐位置 membership 可拦伪造/重放；正确性级依赖索引绑定与输入一致性，未闭合。 |
| 恶意 Server 安全性 | **UNKNOWN** | 六类攻击在 label 级均受阻，无成功攻击；但无 \(z\) 的完整 P2 模拟器未构造，定长中止未规范。 |
| 恶意 Client 安全性 | **UNKNOWN** | 必须单独模拟；\(\mathsf{VerifyCred}\) 电路内实现、\(x_1=P\) 输入一致性、多查询累积泄露未定义。 |
| ORAM 轨迹隐私 | **UNKNOWN** | 固定逻辑 ≠ 物理；§2.1 ORAM 模拟器以 \(z\) 为输入且限于空内存；缺 ORAM 实例、语义 A 电路证明、定长规范。 |
| 索引初始化绑定 | **UNKNOWN**（子结论：原文定理直接适用 = **REJECT**） | §2.1 `M` 初始全零且定理限 initially empty \(M\)；缺 \(\Pi_{init}\)、\(\mathsf{CheckBind}\)、版本防回滚及组合证明。 |
| 协议实现可行性 | **UNKNOWN**（成本红灯） | §3.4：\(T=10^6,s=40\) 需 \(10T\) 电路、bucket 5。本方案 \(T\) 为 **ORAM 物理步数**而非 1600 逻辑读，可能达 \(10^4\)–\(10^5\) 量级 ⇒ 每查询离线 \(O(sT/\log T)\) 个电路重生成，量级 \(10^5\)–\(10^6\)；在线 \(sn\) OT/步。本轮禁止实测，不给毫秒数；结论是成本结构不利但未被证明不可接受。 |

### 整体判决：**HOLD**

- **不 GO**：多项 UNKNOWN 中有两个是决定性的（无 \(z\) 模拟器、索引初始内存绑定），且它们不是参数调优问题，而是需要新证明与新构造。用户明确「不为得到 GO 降低安全标准」。
- **不 NO-GO**：没有出现不可修复矛盾。EXP-03L 已排除人为 \(T=\) 实例化带来的伪反例；本轮 §3.0 又撤回了一条对 authenticity 的夸大担忧。剩余问题是「缺证明/缺构造」，不是「已证不可能」。
- **项目级口径**：REJECT 的对象仅是「原始 Afshar 机制直接提供单方输出」这一具体路径，**不是** PA-VFANN 核心研究问题（严格策略隐私 + 服务端持索引 + 单方输出过滤 ANN）。核心问题继续 HOLD，不外推为整体 NO-GO。

---

## 6. 立项决策接口（交给用户的下一步）

若继续，只允许针对以下**有限阻断项**做一次定向修复评估，不重新调研、不枚举新实例化：

1. **B1（决定性）**：给 \(inst\_ctrl/result\) 四分区输出扩展 §2.2 安全定义，构造不使用 \(z\) 的 P2 腐化模拟器，并证明与 GC/cut-and-choose 承诺 equivocation、控制线指令 equivocation、ORAM 物理序列的**联合**不可区分。
2. **B2（决定性）**：给 \(\Pi_{init}+\mathsf{CheckBind}+\mathrm{ver}\) 防回滚构造，并把它与 §3 online phase 组合；明确放弃「§2.1 空内存定理可直接复用」。
3. **B3**：恶意 P1 模拟器重写（含 result 线与 \(\mathsf{VerifyCred}\) 电路内实现）。
4. **B4**：ORAM 实例选定 + 定长/中止规范 + 逻辑→物理模拟定理。
5. **B5**：符号成本表补齐 B1–B4 的额外开销；若量级仍不利，则成本项单独转 REJECT，并据此做选题转向。

任一 B 项被证明不可修复 ⇒ 只关闭「基于 Afshar batching 的单方输出适配路线」，保留已获研究成果，按用户决策规则转向其他候选问题；不写成 PA-VFANN 整体关闭。

---

## 7. 版本与合规核验

| 项 | 内容 |
| --- | --- |
| 分支 | `exp04-full-transcript-one-sided-output`（基线 `71c95b6`） |
| 新增文件 | 仅 `docs/EXP-04-FULL-TRANSCRIPT-ONE-SIDED-OUTPUT.md` |
| 未修改 | 代码、CSV、实验数据、EXP-01/02/02A/03A–03L 全部历史报告 |
| 新增文献 | 无；仅核对已取得的 Afshar 会议版 PDF 与既有报告 |
| 本轮新发现 | §3.0：更正 EXP-03H §4.2 的互补 label 结论（穷举验证；按约束不改旧报告） |
| 判决 | HOLD；8 项检查表见 §5；不写 GO、不写整体 NO-GO |
| `git diff --check` | 提交前执行并通过 |
| 推送 / 远端 HEAD | 提交后核验，见最终汇报 |
