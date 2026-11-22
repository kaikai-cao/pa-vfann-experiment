# PA-VFANN-30 / EXP-07：全 transcript 联合混合论证与局部引理的任意 \(\lambda\) 符号化

> 用户决策：下一步只攻 EXP-06 缺口③（严格全 transcript 联合 hybrid）；不重审 L2、不攻缺口①（物理网表忠实性）、不处理 B2（索引初始化绑定）/B3（恶意 P1）、不实现网表、不新增协议。
> 本轮目标：① 把 EXP-06 §4.1 的 \(\lambda=3\) 有限枚举升为任意安全参数 \(\lambda\) 的符号证明；② 固定完整 transcript 的随机变量与依赖；③ 给出 H0–H4 逐步 hybrid 并逐项判定；④ 依赖 Afshar 完整版不可获得细节的步骤只登记缺失，不自行补造。
> 验收只允许 ACCEPT / REJECT / UNKNOWN 三种结论；局部穷举通过不得推出完整模拟器 ACCEPT。

---

## 0. 交付、基线与证据状态

| 项 | 内容 |
| --- | --- |
| 基线 | `f9ced73d45d383c7670bc0eaaf2d91017cf5a84b`（EXP-06 最终 HEAD；用户独立核查 Blob `9a440eedcff433c1bd60be649fdad88e47dd3a28`，确认其 HOLD 判决合理） |
| 分支 | `exp07-full-transcript-hybrid` |
| 唯一新增 | `docs/EXP-07-FULL-TRANSCRIPT-HYBRID.md`（本文）；不改代码 / CSV / 数据 / 历史报告 |
| 一手来源 | Afshar, Hu, Mohassel, Rosulek, *How to Efficiently Evaluate RAM Programs with Malicious Security*, EUROCRYPT 2015 Part I, LNCS 9056, pp. 702–729, DOI `10.1007/978-3-662-46800-5_27`；会议版 SHA-256 `92ccf8ab…e73d50`，逐行定位沿用 EXP-03L §6 与 EXP-06 §6 的已核验表；本轮不新增泛化文献 |
| 证据限制 | §3.3 明确 “only an overview… complete details deferred to full version”；full version Appendix D 本环境受限。会议版未写明的构造关系一律登记为缺失，既不作为论文缺陷，也不作为已证事实 |

---

## 1. 结论先行

| 判定对象 | 结论 |
| --- | --- |
| 同 bucket 的 control + result 联合视图与 \(z\) 无关（任意 \(\lambda\)，符号证明） | **ACCEPT**（§2，不依赖 \(\lambda=3\) 枚举） |
| 条件于任意 control 可见结果后 result 分布仍相等 | **ACCEPT**（§2.4，双射逐纤维限制） |
| H0→H1 控制指令序列替换 | **条件 ACCEPT**（依赖缺口①被假设解决，本轮不攻） |
| H1→H2 result 标签 + Solder 视图替换 | **ACCEPT**（§2 的推论，任意 \(\lambda\)） |
| H2→H3 Check/Eval 联合视图替换 | **UNKNOWN**（完整版等价码构造细节缺失，§4.3） |
| H3→H4 ORAM 物理访问 + 通信元数据替换 | **UNKNOWN**（B2 越界 + ORAM 模拟器输入接口与定长规范缺失，§4.4） |
| **完整 transcript 联合模拟器 \(\exists\mathcal S\)** | **UNKNOWN**：无真实区分器（非 REJECT）；H3/H4 未闭合（非 ACCEPT） |
| 整体判决 / 核心研究问题 | **HOLD（不 GO、不停止）**；原始 Afshar 直接单方输出 REJECT（EXP-04）维持，不外推 |

**阶段决策（本轮后不再追加相似审计）**：局部引理已一般化闭合，剩余不确定性集中在两类外部输入——Afshar 完整版 §3.3/Appendix D 的等价码构造细节，以及越界的 B2/定长规范。这两类都不是再枚举实例化或再跑小域穷举能解决的。建议：若能取得完整版则一次性补齐 H3/H4；否则以 HOLD 结项。即使完整 hybrid 日后闭合，其结论仍以“真实电路忠实 Π_A”为前提，不能替代缺口①。

---

## 2. EXP-07-A：任意 \(\lambda\) 的符号化联合分布证明

### 2.1 隐藏随机变量空间

固定一个 EvalBucket \(B_t\)，head 为 \(h\)，eval 电路集 \(J=B_t\setminus\{h\}\)。考察两条输出 wire：控制线 \(c\)（真值 \(u=inst_{ctrl}\)）与结果线 \(r\)（真值 \(z\)）。多条控制/结果线按 wire 独立性逐条推广（§2.5）。

对电路 \(e\in\{h\}\cup J\)、wire \(w\in\{c,r\}\)：

- **一般 garbling（§2.2）**：label 对 \(W_e[w,0],W_e[w,1]\in\{0,1\}^{\lambda+1}\)，独立均匀且满足 \(\operatorname{lsb}(W_e[w,b])=b\)。
- **Free-XOR 变体（§2.2，可选优化；取原始 (P) 分配，§3.1）**：offset \(\Delta_e\in\{0,1\}^{\lambda+1}\)、\(\operatorname{lsb}(\Delta_e)=1\)，逐电路独立；基值 \(L_e[w]\) \(\operatorname{lsb}=0\) 独立均匀；\(W_e[w,b]=L_e[w]\oplus b\Delta_e\)。同一 \(\Delta_e\) 贯穿该电路全部 wire（这是跨 wire / 跨结果位相关的唯一来源，EXP-03J §3.2/§6）。
- **translation bit（(T⊥)，原始合法实例化，EXP-03L §2 代数排除 (T=)）**：\(\tau_e[w]\in\{0,1\}\) 独立均匀，且与所有 \(W_e[\cdot,\cdot]\)、所有 \(\Delta_e\) 独立；原文 §2.2 将其定义为 \(m\times3\) 矩阵中与两条 label 列并列的独立列。
- **活动标签**：真值 \(v\in\{0,1\}\) 对应选择位 \(\sigma_e[w]=v\oplus\tau_e[w]\)，活动标签 \(Y_e[w]=W_e[w,\sigma_e[w]]\)，故 \(\operatorname{lsb}(Y_e[w])=\sigma_e[w]\)。

隐藏样本空间 \(\Omega\) 是上述所有量的受约束乘积空间，测度为均匀乘积测度。注意 \(u\) 与 \(z\) **不在** \(\Omega\) 中——它们是执行输入，下面作为视图函数的固定参数。

### 2.2 Solder / Adjust 的精确形态与联合映射

Solder（§3.1/§3.2，head \(h\) 与 eval \(j\)，wire \(w\)）公开：

\[
\delta_j[w]=\tau_h[w]\oplus\tau_j[w],\qquad
\Delta_j[w,b]=W_j[w,b]\oplus W_h[w,\delta_j[w]\oplus b],\quad b\in\{0,1\}.
\]

在 Free-XOR (P) 下代入 \(W_e[w,b]=L_e[w]\oplus b\Delta_e\)：

\[
\Delta_j[w,b]=L_j[w]\oplus L_h[w]\oplus\delta_j[w]\Delta_h\oplus b(\Delta_j\oplus\Delta_h).
\]

于是 \(\Delta_j[w,0]\oplus\Delta_j[w,1]=\Delta_j\oplus\Delta_h\)：**同一对 \((j,h)\) 跨所有 wire、跨所有结果位恒定**（EXP-03J §3.1/§3.2）。这正是必须在同一混合中保留的相关性。

Adjust（§3.2 step 3(e)）以自身选择位 \(\operatorname{lsb}(Y_j[w])=\sigma_j[w]\) 调整：

\[
\widetilde Y_j[w]=Y_j[w]\oplus\Delta_j[w,\sigma_j[w]]
= L_h[w]\oplus(v\oplus\tau_h[w])\Delta_h = Y_h[w],
\]

故 majority 输出为 head 活动标签 \(Y_h[w]\)，选择位 \(c[w]=v\oplus\tau_h[w]\)。控制线 \(\tau_h[c]\) 经 3(f) 打开，\(u=\operatorname{lsb}(Y_h[c])\oplus\tau_h[c]\)；结果线 \(\tau_h[r]\) 不打开（本场景 \(\mu=0\)），\(z\) 只存在于隐藏的 \(c[r]=z\oplus\tau_h[r]\) 中。

**P2 在本 bucket 的（wire-label / Solder 层）视图**：

\[
V_B(\omega;u,z)=\Big(\tau_h[c],\ \{Y_e[c]\}_{e},\ \{\delta_j[c]\}_j,\ \{\Delta_j[c,b]\}_{j,b},\
\{Y_e[r]\}_{e},\ \{\delta_j[r]\}_j,\ \{\Delta_j[r,b]\}_{j,b}\Big).
\]

其中 \(\tau_h[c]\) 是显式打开项（其余 \(\tau\) 均隐藏）。这就是 EXP-06 §4.1 穷举对象的精确符号化：穷举把 \(\Omega\) 限制到 \(\lambda=3\) 并逐状态列表，本节直接用 \(\Omega\) 上的测度保持变换证明。

### 2.3 主定理（任意 \(\lambda\)，双射证明）

**定理 1**：固定 \(u\)。对任意 \(z\in\{0,1\}\)，分布 \(V_B(\omega;u,0)\) 与 \(V_B(\omega;u,1)\) 在 \(\Omega\) 的均匀乘积测度下**完全相等**；对任意安全参数 \(\lambda\) 成立，且与 \(\Delta\) 分配（G/E/P）、是否启用 Free-XOR 无关。

**证明**：定义 \(\varphi_r:\Omega\to\Omega\) 为“把结果线 \(r\) 上**所有**电路 \(e\in\{h\}\cup J\) 的 \(\tau_e[r]\) 各翻转 1 位，其余一切不变”：

\[
\tau_e[r]\mapsto \tau_e[r]\oplus 1\quad(\forall e),\qquad W_e[\cdot,\cdot],\Delta_e,\tau_e[c]\ \text{不变}.
\]

由 (T⊥)，各 \(\tau_e[r]\) 是独立均匀 bit 且独立于标签与 \(\Delta\)，故 \(\varphi_r\) 是对合的双射并保持均匀乘积测度。逐项核对视图：

1. \(\delta_j[r]\mapsto(\tau_h[r]\oplus1)\oplus(\tau_j[r]\oplus1)=\delta_j[r]\)，不变。
2. \(\Delta_j[r,b]\) 是 \(W_j[r,\cdot],W_h[r,\cdot],\delta_j[r]\) 的确定性函数，三者均不变，故不变；Free-XOR 下 \(\Delta_j\oplus\Delta_h\) 亦不变。
3. \(Y_e[r]\)：在参数 \(z\oplus1\) 下，选择位 \((z\oplus1)\oplus(\tau_e[r]\oplus1)=z\oplus\tau_e[r]\)，与参数 \(z\) 下的选择位相同；label 对不变，故 \(Y_e[r]\) 不变。\(Y_h[r]\) 同理。
4. 控制线全部量只依赖 \(\tau_e[c]\) 与标签，二者不变，故 \(V_B\) 的控制部分逐点不变（含打开的 \(\tau_h[c]\)）。

于是对所有 \(\omega\in\Omega\) 有

\[
V_B(\varphi_r(\omega);u,z\oplus1)=V_B(\omega;u,z).
\]

两边取分布，左式因 \(\varphi_r\) 保测度而等于 \(V_B(\omega;u,z\oplus1)\) 的分布，即得两分布相等。∎

**关键点**：定理成立的根本原因是 (T⊥) 下 \(\tau_e[r]\) 与 \(\Delta_e\)、与标签、与控制线 \(\tau_e[c]\) **全部独立**。这正是 EXP-03L §2 从原文 §2.2 得到的代数排除所保证的原始结构；(T=) 下翻转 \(\tau_e[r]\) 必须同时翻转 \(\Delta_e[k]\)，从而改变 \(\Delta_j\oplus\Delta_h\) 与控制线 \(\tau_e[c]\)，双射失效——这与 EXP-03L §2.1 的 \(D_{\rm cross}\) 结论一致，(T=) 已被排除为非原始实例化，不在本定理范围。

### 2.4 条件于控制线可见结果后的结果线分布

定理 1 的证明中，控制部分对 \(\varphi_r\) **逐点不变**（第 4 项），故 \(\varphi_r\) 限制在任一控制纤维

\[
\Omega_{v_c}:=\{\omega\in\Omega:\ V_B(\omega;u,z)|_{control}=v_c\}
\]

上仍是该纤维到自身的保测双射（对 \(v_c\) 属于支持集而言）。因此

\[
\Pr[V_B|_{result}=v_r \mid V_B|_{control}=v_c,\ z=0]
=\Pr[V_B|_{result}=v_r \mid V_B|_{control}=v_c,\ z=1]
\quad\forall v_c,v_r.
\]

这直接回答“控制线打开是否替结果线开后门”：否。此结论对任意 \(\lambda\) 成立，不是 \(\lambda=3\) 的枚举性质。

### 2.5 多 wire / 跨 bucket 的推广与力度边界

- **多条控制线 / 多条结果线**：\(u\) 是向量时固定 \(u\) 即可（控制线不要求与 \(u\) 无关）；\(z\) 是向量时令 \(\varphi_r\) 同时翻转**所有结果线**的 \(\tau_e[r_i]\)。由逐 wire 独立，(T⊥) 下联合测度仍保持，§2.3 四项逐 wire 成立。这覆盖 EXP-03K §3 关心的多结果位情形：在原始 (T⊥) 下 \(\tau_h[r_i]\) 逐位独立，\(c_i=z_i\oplus\tau_h[r_i]\) 逐位独立均匀，不存在 \(D_{\rm cross}\)（其前提是 (T=) 跨位共享，已被排除）。
- **跨 wire / 跨位相关**：由 (P) 的同一 \(\Delta_e\) 贯穿全部 wire，\(\Delta_j\oplus\Delta_h\) 跨 wire 恒定；\(\varphi_r\) 不动任何 \(\Delta_e\)，故该相关完整保留（§2.2 公式）。这比“逐 wire 独立”更强：证明没有偷换相关性。
- **结果累加线 \(R_t\)**：EXP-05A/B 允许 \(P\to R_t\)，但 \(R_t\) 走 \(\mu=0\) 隐藏且不回灌地址/停止逻辑。对任何 \(\tau\) 隐藏的 wire，把 §2.3 中的 \(z\) 换成该 wire 的任意真值 \(v\)，同一 \(\varphi\) 证明其活动标签与 Solder 视图与 \(v\) 无关。故 \(P\) 对 \(R_t\) 的影响不体现在可见量上——这是语义 A 的“允许影响但隐藏”在 \(\lambda\) 一般情形下的符号版本。
- **力度边界**：定理只覆盖 wire-label / Solder / Adjust / majority 的**可见量分布**，不覆盖 garbled circuit 表本身的等价码构造（H3）与物理 ORAM 访问（H4）。它把 EXP-06 §4.1 从“调试证据”升为“可复用的符号引理”，但**不**等于完整 transcript 相等。

---

## 3. EXP-07-B：完整 transcript 的随机变量与依赖图

### 3.1 变量清单（按执行阶段）

| 组 | 随机变量 | 生成者 / 依赖 | 含 \(P\) 或 \(z\)？ | P2 可见形式 |
| --- | --- | --- | --- | --- |
| G1 | 每电路 \(i\) 的 \(E(i),D(i),GC(i)\)：\(L_i[w],\Delta_i,\tau_i[w]\), GC 表随机 | P1，逐电路独立（§3.2 step 1） | 否（\(x_1=P\) 仅在 GetInput 阶段进入 label） | 非 check 电路只经 GC 黑盒求值可见 |
| G2 | \(F_{com}\) 承诺随机性 | P1 | 否 | 承诺串（模拟器可 equivocate） |
| G3 | check 集 \(S_c\) | P2 随机选（§3.2 step 2） | 否 |  adversary 自身选择 |
| G4 | check 电路 \(i\in S_c\) 的 \(E(i),D(i),GC(i)\) 全开 | G1 + G3 | 否（check 电路不执行 \(\Pi\) 的实际输入） | 完整 label 与 \(\tau\) |
| G5 | GetInput1/pub 的 label 与 OT 输出 | G1 + P2 select bit | 不由 \(z\) 决定；\(P\) 经 \(x_1\) label 进入但 \(\tau\) 隐藏 | 随机 label / OT share |
| G6 | 每 bucket 的 Solder \(\delta_j,\Delta_j[w,b]\) | G1（head 与 eval 的 \(\tau,\Delta,L\)） | 否 | 显式打开（§2.2 已证与 \(z\) 无关） |
| G7 | 每 bucket 的 control 输出 label + 打开的 \(\tau_h[c]\) | G1 + G6 + 逻辑指令 \(inst_t\) | \(inst_t=F_t(I,q,E)\)，否 | 解码出的 \(inst_t\)（§3.2 3(f)(g)） |
| G8 | 每 bucket 的 result / \(R_t\) 输出 label，\(\tau_h[r]\) 不打开 | G1 + G6 + \(z\) / \(R_t\) | 是（承载），但§2 证可见分布与真值无关 | 活动 label + solder 差 |
| G9 | 跨 bucket 状态 label（Q/V/ptr/t 与 \(R_t\)） | G7/G8 输出经 Solder 到下一 bucket 输入 | Q/V/ptr/t 否；\(R_t\) 含 \(P\) 但 \(\mu=0\) | 下一 bucket 输入 label |
| G10 | ORAM 物理访问模式 / 树节点 / eviction 随机 | \(inst_t\) + ORAM 随机 \(\rho_t\) + 初始内存 \(M\) | 逻辑序列否（语义 A）；物理由 ORAM 隐藏 | 访问地址序列（§2.1 定义） |
| G11 | abort 时机 / 原因 | check 失败、authenticity 失败（§3.2 step 2、3(g)） | 诚实 P1 下无 check 失败；预设 label 不含 \(z\) | 中止消息 |
| G12 | 通信元数据（消息数 / 长度 / 轮数 / 顺序） | 固定预算 \(E\) + bucket 规模（Π_A 强制 \(t=E\)） | 否 | wire 消息序列 |

### 3.2 必须放在同一个混合论证中的相关性

1. **同 bucket**：G6/G7/G8 出自**同一组** \(E(h),D(h),E(j),D(j)\)；control 与 result 经同一 \(\Delta_e\)、head label 与 majority 耦合。§2 的 \(V_B\) 已把 G6+G7+G8 作为联合对象处理，但 G1 的 GC 表尚未纳入（→ H3）。
2. **Check ↔ Eval**：G4 全开 check 电路；原始 (P) 下 \(\Delta^{\rm chk}\) 与 eval 的 \(\Delta_e\) 独立，故 check 打开不泄露 eval 随机量（EXP-03L §1.3）。这是 H3 可利用的结构事实，但“先承诺后开 check、再对 eval 等价码”的具体构造会议版未给全（→ H3 UNKNOWN）。
3. **跨 bucket**：G9 把上一 bucket 的 head 输出 label 焊到下一 bucket 输入。语义 A 保证 Q/V/ptr/t 与 \(P\) 无关；\(R_t\) 含 \(P\) 但 \(\mu=0\)。§2.5 的隐藏 wire 推论覆盖其分布，但 GC 表一致性仍需 H3 的构造。
4. **逻辑 ↔ 物理**：G7 的 \(inst_t\) 与 G10 的物理访问由 ORAM 执行耦合；模拟时必须让 ORAM 模拟序列与等价码后的 control label 解码结果**逐轮一致**（→ H4）。

---

## 4. EXP-07-C：H0–H4 逐步混合

记真实视图 \(\mathrm{View}_{P2}^{\rm real}(P,I,q,E)\) 为 G1–G12 的全部 P2 可见消息。目标模拟器输入仅 \((1^\lambda,I,L_S)\)（\(L_S\) 含公开 \(q,E\) 与协议参数），不含 \(P,z\)。

### 4.1 H0：真实执行视图

H0 即上述真实视图，诚实 P1 + 被腐化 P2。分布由 \(\Omega\)（G1）+ P2 的 \(S_c\)/OT 选择（G3/G5）+ ORAM 随机 \(\rho_t\)（G10）共同决定。不做任何替换。

### 4.2 H1：替换控制指令序列

**替换**：把 H0 中由 control label 解码出的 \(inst_t\) 序列替换为

\[
\mathcal S_E(I,q,E):= \text{计算 }\Pi_A\text{ 的公开控制函数输出 } (inst_1,\dots,inst_E),
\]

它只读 P2 自身输入 \(I\) 与公开 \(q,E\)。

**依据（分步，不写“由随机性独立”）**：

1. EXP-05B 补充已在 primitive 门级 + RO-RAM + 公开初始化 + (N-r) 下证明不变量 \(I(t): Q_t,V_t,ptr_t,t\) 与 \(P\) 无关，且 \(R_t\) 不被地址/停止逻辑读；故 AddressTrace/StopTrace = \(F(I,q,E)\)，与 \(P,z\) 无关。
2. 真实 P1 诚实 ⇒ 所有电路均为诚实 garble，§3.2 step 3(f)(g) 解码出的 \(inst_t\) 恰为该控制函数在第 \(t\) 轮的值（garbling 正确性；cut-and-choose 的可靠性在此不是必需，因为 P1 未腐化）。
3. \(I\) 是 P2 私有输入，在腐化 P2 模拟中可由 adversary 的输入带取得；\(q,E\in L_S\)。故 \(\mathcal S_E\) 对所有 \(t\) 有定义且不读 \(z\)。

**混合步骤的良定义**：H1 替换的是指令序列的**生成来源**，不是仅改解码值后保留旧标签——control label 及其打开的 \(\tau_h[c]\) 按 §2 的采样关系、以 \(\mathcal S_E\) 给出的每个 \(inst_t\) 为真值重新生成。由于两种来源给出的序列**逐轮取同一个值** \(F_t(I,q,E)\)，且§2 对任意固定 \(u\) 已给出标签视图的同分布采样器，故重生成后的 control 视图与 H0 逐点同分布，H1 是良定义的分布替换。

**判决：条件 ACCEPT**。条件 = 真实实现的 \(\Pi\) 忠实于 Π_A（缺口①）。本轮按用户指示不攻该条件，H1 的全部论证以它为前提；若该条件失败（例如实现改用语义 B 队列键或令 \(r\) 进地址），EXP-05B 的 Π_B REJECT 立即适用，H1 不成立。此替换在逻辑序列层是**相等**而非仅计算不可区分。

### 4.3 H2：替换 result 标签及其 Solder 视图

**替换**：对每个 bucket 的结果线（含 \(R_t\) 累加线）把活动 label、\(\delta_j[r]\)、\(\Delta_j[r,\cdot]\) 与 H1 固定的 control 视图**联合地**重新采样为不含 \(z\) 的采样器输出（即 §2 定理 1 提供的隐藏量 \(\tau_e[r]\) 均匀采样 + 同一组 \(\Delta_e,L_e\) 的确定性导出）。

**依据**：§2 定理 1 给出任意 \(\lambda\) 的严格分布相等，且 §2.4 保证在 control 纤维内仍相等；§2.5 把它推广到多结果位与跨 bucket 的隐藏 \(R_t\) wire。采样器复用了与 H1 control 部分**相同**的 \(\Delta_e,L_e\)，因此 \(\Delta_j\oplus\Delta_h\) 跨 wire / 跨位的相关性没有被破坏（这是 EXP-03I 旧采样器曾失败、EXP-03J §5.1 用 \(D_2\) 检出的点）。

**判决：ACCEPT（wire-label / Solder 层，任意 \(\lambda\)，条件 (T⊥)+P 原始结构）**。力度边界：不覆盖 GC 表本身；该替换在可见标签层是分布相等，不是计算不可区分。

### 4.4 H3：替换 Check/Eval 联合视图

**需要证明的对象**：G4（check 全开：\(E(i),D(i),GC(i)\) for \(i\in S_c\)）与 eval 电路的 GC 表消息、GetInput label（G1/G5）的**联合**分布，可由 \((1^\lambda,I,L_S)\) 生成并与 H1/H2 已固定的 label 视图一致。

**可利用的结构事实**：(P) 下 check 与 eval 的 garble 随机逐电路独立（§3.2 step 1 + §3.1 放弃共享 offset），故 G4 的全开不泄露 eval 随机量（EXP-03L §1.3）；模拟器可用诚实 garble 采样应答 check 电路，用 H1/H2 的 label 视图应答 eval 电路。

**一个重要限定（避免把 UNKNOWN 误读为疑似泄露）**：EXP-05 已逐行动作确认，原文 §3.3 的 A–H 中**唯一**直接接触 \(z\) 的是动作 E（收 \(z\) 生成模拟指令序列），G 经 E 间接依赖。H1 已经用 \((I,q,E)\) 生成一个与真实序列**相等**（不是仅不可区分）的替代序列，故 A/B/C/D/F/G/H 的动作输入在替换前后不变；就“\(z\) 依赖能否剔除”这一命题而言，H3 没有新的 \(z\) 障碍。本步判 UNKNOWN 的原因是：这些动作的完整构造（尤其 G 的假 GC 与跨 bucket 一致性）只以 overview 形式存在，无法在可获得原文中逐门核验其联合分布，**不是**发现了新的区分器。

**缺失（必须登记，不自行补造）**：

- M1：会议版 §3.3 只说模拟器 “equivocates on the decommitment to the decoding information \(\tau(inst(D(i)))\), chosen so that the visible output wires will decode to the next simulated ORAM memory instruction”，并给出 check 电路与 GC 的 overview；**complete details deferred to full version**（§3.3，提取文本 347–349 行）。full version Appendix D 本环境受限。
- M2：让 eval 电路的 GC 表在**已由 H1/H2 固定的输入/输出 label** 上求值得到指定 control/result label 的“假 GC / 等价码”构造，会议版未给逐门步骤；尤其未说明它如何与 check 电路的全开值、以及 G9 跨 bucket 焊到下一 bucket 的状态 label **同时**保持一致。
- M3：先承诺（G2）后知 \(S_c\)（G3）的 equivocation 顺序在理想承诺功能 \(\mathcal F_{com}\) 下的具体接口，会议版只给出动作概述（§3.3 A/B），不足以核验联合分布。

**判决：UNKNOWN**。理由不是发现区分器，而是构造细节在可获得的原文中缺失；不能因为 G4 与 eval 的随机独立（分量层）就宣称 G4+GC+label 的联合 transcript 已可模拟——这正是“分量联合 \(\not\Rightarrow\) 全 transcript”落地的具体位置。

### 4.5 H4：替换 ORAM 物理访问与通信元数据

**替换**：把 G10 的物理访问序列替换为 ORAM 模拟输出；把 G12 的消息数/长度/轮序替换为固定预算 \(E\) 下的定长规范。

**可依据的部分**：§2.1 的 ORAM 安全定义给出 \(S(1^\lambda,z)\approx I(\Pi,M,x_1,x_2)\)，其中 \(I(\cdot)\) 是逻辑指令序列；tree-based ORAM 的物理模式均匀、可从真实切换到模拟（原文 565/572 行）。H1 已把逻辑序列固定为 \(\mathcal S_E(I,q,E)\)，与真实序列**相等**，故按 ORAM 不可区分性可切换物理模式——这一步的控制线与物理序列逐轮耦合由 H1 的序列一致性保证，不需额外假设。同样，H4 的 UNKNOWN 不是因为发现物理访问模式泄露 \(P/z\)，而是因为切换所依赖的定义/规范在可获得原文中不完整。

**缺失（登记）**：

- M4：§2.1 的定理限于 **initially empty \(M\)**，本场景初始内存为非空索引 \(I\)；“如何保证真实初始内存等于承诺的 \(I\)”是 B2，用户明确本轮不处理。ORAM 模拟器输入接口是 \(z\)，而本路线改用 \((I,q,E)\) 直接生成逻辑序列；会议版没有给出“给定逻辑序列的物理模式模拟”这一变体的独立陈述，需从 §2.1 定义推导，但会议版未写出。
- M5：定长规范（消息长度/轮数由 \(E\) 固定、abort 由预设 label 决定）在 EXP-06 中是本场景规范选择（B4），原文未作为定理保证；缺该规范则 G12 的联合分布无定义。
- M6：abort 与 authenticity 检查（G11）在完整版中的处理只在 §3.3 概述出现，与 H3 的等价码构造共用 M2/M3 缺口。

**判决：UNKNOWN**。分量级（物理 ORAM 模式可模拟）有原文依据，但全 transcript 层因 M4–M6 未闭合。未发现必须依赖 \(P,z\) 且不可模拟的真实分量，故**不触发停止条件**。

### 4.6 汇总：混合链判决

| 步 | 替换内容 | 力度 | 判决 | 依据 / 缺失 |
| --- | --- | --- | --- | --- |
| H0 | 真实视图 | — | 基线 | §3.1 G1–G12 |
| H1 | 控制指令序列 → \(\mathcal S_E(I,q,E)\) | 逻辑层相等 | 条件 ACCEPT | §4.2；条件缺口① |
| H2 | result / \(R_t\) 标签 + Solder → 无 \(z\) 采样 | 任意 \(\lambda\) 严格分布相等 | ACCEPT | §2 定理 1 + §2.4/§2.5 |
| H3 | Check/Eval 联合视图 → 模拟 | — | UNKNOWN | M1–M3，完整版缺失 |
| H4 | ORAM + 元数据 → 模拟 | 分量有据 | UNKNOWN | M4–M6，B2 越界 + 定长规范 |
| **全流程** | \(\exists\mathcal S:\mathrm{View}^{real}_{P2}\approx\mathcal S(1^\lambda,I,L_S)\) | — | **UNKNOWN** | 无 REJECT 证据，H3/H4 未闭合 |

---

## 5. 判决与阶段决策

### 5.1 三种结论的严格使用

- **不是 ACCEPT**：H3/H4 未给出严格证明，且 H1 以缺口①为前提。局部任意 \(\lambda\) 引理（§2）与 \(\lambda=3\) 枚举都不足以推出完整模拟器。
- **不是 REJECT**：逐分量搜索（§3.1 + EXP-06 §4.4）仍未发现必须依赖 \(P\) 或 \(z\)、且无法由 \((I,q,E)\) 模拟的真实视图分量；§2 的双射是正面证据。
- **是 UNKNOWN**：具体缺失为 M1–M6（§4.4/§4.5）与越界的缺口①、B2。UNKNOWN 对象是**完整 transcript 联合模拟器的存在性证明**，不是研究问题整体。

### 5.2 阶段决策（本轮后不再追加相似审计）

1. **局部引理已闭合**：§2 把 EXP-06 §4.1 的 \(\lambda=3\) 结果升为任意 \(\lambda\)、任意 \(\Delta\) 分配、Free-XOR 可选、多结果位与跨 bucket 隐藏 wire 覆盖的符号证明；这是本轮可独立交付的正面结果，可复用。
2. **剩余不确定性不可由同类审计消除**：M1–M3 是原文构造细节缺失，M4/M5 是越界的 B2/定长规范，缺口①是工程实现问题。再枚举实例化、再跑小域穷举、再重审 L2 都不会改变它们。
3. **决策**：若可取得 Afshar 完整版 §3.3 与 Appendix D，一次性补齐 H3 的等价码构造与 H4 的 ORAM 变体陈述，再判完整 hybrid；否则以 **HOLD** 结项，不再追加相似审计。无论哪种情况，缺口①（物理网表忠实 Π_A）都保持独立未攻，不能由本轮的密码学层结论替代。
4. **项目级口径**：原始 Afshar 直接单方输出 REJECT（EXP-04 §2.2）与已 NO-GO 的具体贡献（03B/03D）维持；核心研究问题（严格策略隐私 + 服务端持索引 + 客户端秘密谓词 + 单方输出过滤 ANN）继续 **HOLD，未关闭**。本轮局部 ACCEPT 不外推为完整协议安全，也不构成论文贡献已确立。

---

## 6. 与既有报告的关系

| 报告 | 本轮如何使用 |
| --- | --- |
| EXP-03J §3/§4 | 复用 solder 差值在 Free-XOR (P) 下的精确形态 \(\Delta_j\oplus\Delta_h\) 跨 wire/跨位恒定，及同分布采样器；§2 的 \(\varphi_r\) 是其 (T⊥) 分支的任意-\(\lambda\) 化简 |
| EXP-03K §3 / EXP-03L §2 | 采用 (T=) 已被原文代数排除；§2 双射仅对 (T⊥) 成立，与 \(D_{\rm cross}\) 结论一致 |
| EXP-05A/B + 补充 | 采用 Π_A primitive 门级非干扰、RO-RAM、公开初始化、任意轮归纳，作为 H1 的语义 A 前提（缺口①本轮不攻） |
| EXP-06 §4.1/§4.2/§5.2 | 把 65536 支持集枚举升为 §2 符号证明；沿用“唯一 \(z\) 依赖在动作 E”与三缺口结构，本轮专攻缺口③ |

---

## 7. 版本信息

| 项 | 内容 |
| --- | --- |
| 分支 | `exp07-full-transcript-hybrid`（基线 `f9ced73`） |
| 唯一新增 | `docs/EXP-07-FULL-TRANSCRIPT-HYBRID.md`（本文） |
| 内部验算（非证据） | 一次性内存脚本（未落盘、未新增代码/数据）：在 \(\lambda=3\) 的 (T⊥)+Free-XOR(P) 样本空间上核对 §2 的 \(\varphi_r\)：逐点 \(V(\varphi_r(\omega);u,z\oplus1)=V(\omega;u,z)\) 成立；\(z=0/1\) 归一化全视图分布相等（支持集各 524288）；按 control 部分分组的 2048 个纤维内 result 边缘分布逐组相等。此验算只用于确认代数推导无编码错误，**不作任意 \(\lambda\) 的证据**——后者由 §2 的符号双射给出。 |
| 工作区 | 提交前确认除本报告外无改动；`git diff --check` 通过 |
| 推送 | 提交后核验远端 HEAD 与本地一致 |
