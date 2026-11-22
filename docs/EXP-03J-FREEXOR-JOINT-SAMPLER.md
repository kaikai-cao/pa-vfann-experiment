# EXP-03J：Free-XOR 联合采样器的完整随机实验与同分布判定

> 项目：PA-VFANN-22（承接 EXP-03I 独立审阅意见）
> 目标：**唯一目标**——把 Free-XOR 下的联合采样器写成一个完整、明确的随机实验，逐项检查是否与真实 Solder transcript 同分布。不扩证明目标、不搜文献、不写代码、不改旧报告。
> 方法：不再使用笼统假设 A1/A2/A3；把「独立 garble」拆解为显式随机变量（label 基值 / offset Δ / translation bit τ / check-eval 关系 / 跨 wire 与跨位相关），对每种实例化分别给出采样器或区分器。
> 停止条件（沿用审阅意见）：能构造同分布采样器 ⇒ 接受 Free-XOR 下的局部引理；不能构造或找到真实构造中的区分器 ⇒ 否定相应实例化。两种结果都不自动决定整体协议。

---

## 0. 交付与证据状态

| 项 | 内容 |
| --- | --- |
| 基线 commit | `bfecfb0653f94e5e537e29c8aeae3f95f4926e9a`（EXP-03I 最终 HEAD） |
| 分支 | `exp03j-freexor-joint-sampler` |
| 新增文件 | `docs/EXP-03J-FREEXOR-JOINT-SAMPLER.md`（本文，唯一新增） |
| 一手来源 | 沿用 EXP-03H/03I 已核验的会议版 §2.2、§3.1–3.3（DOI `10.1007/978-3-662-46800-5_27`），本轮不新增引用 |
| 证据限制 | 会议版 §2.2 只写「Free-XOR 分布 satisfies all the properties of W」，**未显式给出** Δ 的采样域、check/eval 的 Δ 关系、τ 与 Δ 的独立性。full version Appendix D 本环境受限。故本轮对每种可能实例化分别覆盖，不臆断论文实际选择。 |

**一句话结论：接受 Free-XOR 下的局部引理，但必须替换 EXP-03I 的采样器。** EXP-03I 的采样器按「各电路独立 label」采样，未指定 Δ 结构，在 Free-XOR 下存在**完美区分器**（§5.1）。把 Δ 结构显式化后，每种与论文 W 性质一致的实例化都能构造**严格同分布**采样器（§4），且采样器输入不含 \(z\)。唯一被否定的实例化是「\(\tau=\Delta[k]\) 且 \(\Delta\) 公开」（§5.2），这是实例化排除条件，不是对 Afshar 构造的攻击。

---

## 1. 审阅意见吸收

| 审阅意见 | 本轮处理 |
| --- | --- |
| ① 采样器未表达 Free-XOR 全局 Δ；逐电路独立采样 offset 不复现真实联合分布 | 接受。§2 参数化 Δ 的采样域，§4 构造匹配 Δ 结构的采样器，§5.1 给出错误采样器的区分器 |
| ② A2「独立 garble」混淆了 label 基值 / 全局 offset / τ / check-eval 随机性 | 接受。§2 把四者拆成显式随机变量，不再使用「独立 garble」这一笼统表述 |
| ③ §4.2 的 \(\tau=\Delta[k]\) 区分器是条件反例，非论文构造攻击 | 接受。§5.2/§5.3 重新定位为实例化排除条件 |
| ④（项目级）PA-VFANN 整体不得直接写成 EXP-03D 的 NO-GO 关闭 | 接受。§7.2 纠正：已 NO-GO 的是具体贡献/包装，核心研究问题仍 HOLD |

---

## 2. 完整随机实验：把「独立 garble」拆成显式随机变量

不再写 A1/A2/A3。以下逐项定义审阅者要求明确的五件事。

### 2.1 Δ 的采样域（对应审阅意见「全局 Δ 采样一次还是逐电路」）

用**等价类**参数化：设参与运算的电路集合为 \(\mathcal C = S_c \cup S_e\)（check ∪ evaluation）。定义 offset 分配函数 \(\Delta(\cdot)\)，对每电路 \(c\in\mathcal C\) 赋 \(\Delta_c\in\{0,1\}^\lambda\)，\(\operatorname{lsb}(\Delta_c)=1\)。统一覆盖三种情形：

- **(G)** 全局共享：所有 \(c\)（含 check 与 eval）共用一个 \(\Delta\)，采样一次；
- **(E)** eval 共享、check 独立：所有 eval 电路共用 \(\Delta_{\mathrm{eval}}\)，check 电路用独立的 \(\Delta_c^{\mathrm{chk}}\)；
- **(P)** 逐电路独立：每个 \(c\) 的 \(\Delta_c\) 独立采样。

记 head \(h\) 的 offset 为 \(\Delta_h\)。关键事实（会议版未显式给出，本轮按覆盖处理）：**check 电路被完全打开（§3.2 step 2），若 \(\Delta_c^{\mathrm{chk}}=\Delta_h\)（情形 G），则 \(\Delta_h\) 对 P2 公开；否则 \(\Delta_h\) 隐藏**。这是「check/eval 是否共享随机量」的精确后果。

### 2.2 label 基值与 translation bit（对应「label 基值如何生成」「τ 与 Δ 联合分布」）

在 Free-XOR + point-permute 下，对每电路 \(c\)、每 wire \(w\)：

- 采样基值 \(L_c[w]\leftarrow\{0,1\}^\lambda\)，\(\operatorname{lsb}(L_c[w])=0\)，独立均匀；
- 设 \(D_c[w,0]=L_c[w]\)，\(D_c[w,1]=L_c[w]\oplus\Delta_c\)（故 \(\operatorname{lsb}(D_c[w,1])=1\)）；
- translation bit \(\tau_c[w]\in\{0,1\}\) 决定「哪条 label 编码 false」：\(D_c[w,\tau_c[w]]\) 编码 0，真值 \(x\) 对应选择位 \(x\oplus\tau_c[w]\)。

**τ 与 Δ 的联合分布参数化**：显式列出两种，不预设：

- **(T⊥)** \(\tau_c[w]\) 独立均匀，与所有 \(\Delta_c\)、所有 \(L_c[w]\) 独立（标准 point-permute 的 permutation bit）；
- **(T=)** \(\tau_c[w]=\Delta_c[k]\)（某固定公开位 \(k\ne \mathrm{lsb}\)）。

会议版「Free-XOR 分布满足 W 的全部性质」中，「互补 label 除 lsb 外不可预测」在 \(\Delta\) 公开时**排除 (T=)**（因互补 label = 活动 \(\oplus\Delta\) 完全可预测）；在 \(\Delta\) 隐藏时 (T=) 不违反该性质。本轮对 (T⊥)/(T=) 均分析，不把任一写成前提。

### 2.3 真实随机实验 \(R(z)\)

固定一个结果位 \(i\)、bucket \(B_t\)（head \(h\)）。执行 §2.1–2.2 生成所有电路的 garbling 随机变量。对结果线：

\[
\delta_j=\tau_j\oplus\tau_h,\qquad b_j=z\oplus\tau_j,\qquad Y_j=D_j[i,b_j],\qquad c=z\oplus\tau_h=\operatorname{lsb}(Y_t).
\]

P2 可见视图 \(\mathcal V_{\mathrm{solder}}(z)\) 为：\(\big(c,\ \{\delta_j\}_{j\ne h},\ \{Y_j\}_{j\in B_t},\ \{\Delta_j^{(out)}[i,0],\Delta_j^{(out)}[i,1]\}_{j\ne h},\ [\Delta_h\ \text{若公开}]\big)\)。结果线 translation bit 不开放（\(\mu=0\)）。

---

## 3. 决定性结构：Solder 差值在 Free-XOR 下的精确形态

这是审阅意见①的核心——必须按 Δ 结构计算，不能用非 Free-XOR 的独立 label。

### 3.1 输出侧

由 \(D_j[i,b]=L_j\oplus b\,\Delta_j\)、\(D_h[i,b']=L_h\oplus b'\,\Delta_h\)：

\[
\Delta_j^{(out)}[i,b]=L_j\oplus b\,\Delta_j\oplus L_h\oplus(\delta_j\oplus b)\,\Delta_h
=L_j\oplus L_h\oplus\delta_j\,\Delta_h\oplus b\,(\Delta_j\oplus\Delta_h).
\]

于是：

- **共享 Δ（情形 G/E 中 \(\Delta_j=\Delta_h\)）**：\(\Delta_j^{(out)}[i,0]=\Delta_j^{(out)}[i,1]=L_j\oplus L_h\oplus\delta_j\,\Delta_h\) —— **两条差值恒相等**；
- **逐电路 Δ（情形 P）**：\(\Delta_j^{(out)}[i,0]\oplus\Delta_j^{(out)}[i,1]=\Delta_j\oplus\Delta_h\) —— 两条之差揭示电路间 offset 差，**且该差对同一对 \((j,h)\) 跨所有结果位相同**。

### 3.2 输入侧（跨 wire 相关性）

对输入线 \(i'\)，记 \(\alpha_j=\tau(E_h)_{i'}\oplus\tau(E_j)_{i'}\)，同理：

\[
\Delta_j^{(in)}[i',b]=K_h\oplus K_j\oplus\alpha_j\,\Delta_h\oplus b\,(\Delta_j\oplus\Delta_h),
\]

其中 \(K_c\) 为输入线基值。**注意 \(\Delta_j\oplus\Delta_h\) 与输出侧是同一个量**——同一电路的全局 Δ 贯穿输入线与输出线。这正是审阅意见⑤要求的跨 wire 相关性；采样器必须用同一组 \(\Delta_c\) 生成两侧。

### 3.3 Adjust 与 majority 对齐（验证，非新结论）

\[
\operatorname{Adjust}(Y_j,\Delta_j^{(out)}[i,\cdot])=Y_j\oplus\Delta_j^{(out)}[i,b_j]
=L_h\oplus(\delta_j\oplus b_j)\,\Delta_h=L_h\oplus c\,\Delta_h=D_h[i,c],
\]

故所有 \(j\) 调整后落到同一 head 选择位 \(c=z\oplus\tau_h\)，majority 得 \(Y_t=D_h[i,c]\)。代数与 EXP-03H 一致，但此处带 Δ 结构。

---

## 4. 同分布采样器（每种实例化一个）

### 4.1 采样器 \(S_{\Delta}\)（统一构造，输入不含 \(z\)）

给定 Δ 分配结构（§2.1）与 τ 分布（§2.2）作为**公开的实例化描述**：

1. 按结构采样 offsets：情形 G 采一个 \(\Delta\)；E 采 \(\Delta_{\mathrm{eval}}\) 与各 \(\Delta_c^{\mathrm{chk}}\)；P 采各 \(\Delta_c\)（均 \(\operatorname{lsb}=1\) 均匀）。若该结构使 \(\Delta_h\) 公开，则输出 \(\Delta_h\)；否则作为隐藏量保留。
2. 采样 \(c\leftarrow\{0,1\}\) 均匀。
3. 对每 \(j\ne h\)，采样 \(\delta_j\leftarrow\{0,1\}\) 均匀独立；置 \(b_j:=c\oplus\delta_j\)。
4. 对每电路 \(c\in B_t\)、结果位 \(i\)（及输入线 \(i'\)）：采样基值 \(L_c[i]\)（\(\operatorname{lsb}=0\)），\(K_c[i']\) 独立均匀。
5. 置 \(Y_j:=L_j\oplus b_j\,\Delta_j\)。
6. 按 §3.1/§3.2 公式计算 \(\Delta_j^{(out)}[i,b]\)、\(\Delta_j^{(in)}[i',b]\)（用与步骤 1 相同的 \(\Delta_c\)，**不**用独立 label 对）。
7. 输出 \(\big(c,\{\delta_j\},\{Y_j\},\{\Delta_j^{(out)}[i,\cdot]\},[\Delta_h\ \text{若公开}]\big)\)。

### 4.2 同分布证明（逐量核对，联合一致性由构造保证）

记真实隐藏量为 \(\tau_h,\{\tau_j\},\{L_c\},\{\Delta_c\}\)。由 §2.2，τ 独立均匀且与 Δ、label 独立（(T⊥)；(T=) 见 §5.2）：

| 观察量 | 真实分布（隐藏量表达） | \(S_\Delta\) | 一致 |
| --- | --- | --- | --- |
| \(c\) | \(z\oplus\tau_h\)，\(\tau_h\) 均匀 ⊥ \(z\) ⇒ 均匀 | 均匀 | ✓ |
| \(\delta_j\) | \(\tau_j\oplus\tau_h\) | 均匀 | ✓ |
| \((c,\delta_j)\) 联合 | 线性可逆变换 \((\tau_h,\tau_j)\mapsto(z\oplus\tau_h,\tau_j\oplus\tau_h)\) 保均匀独立 | 独立均匀 | ✓ |
| \(b_j=\operatorname{lsb}(Y_j)\) | \(z\oplus\tau_j=c\oplus\delta_j\) | \(c\oplus\delta_j\) | ✓ |
| \(Y_j\) | \(L_j\oplus b_j\Delta_j\) | 同公式 | ✓ |
| \(\Delta_j^{(out)}[i,\cdot]\) | §3.1 公式（含 \(\Delta_j\oplus\Delta_h\) 结构） | 同公式、同 \(\Delta_c\) | ✓ |
| \(\Delta_h\) 公开性 | 由 Δ 分配结构决定 | 按结构输出/隐藏 | ✓ |

因为每个观察量都是「不含 \(z\) 的采样量」的确定性函数，且联合依赖（尤其 \((c,\delta_j)\) 独立、\(\Delta_j\oplus\Delta_h\) 跨位/跨 wire 一致）由构造复现，故对每个 \(z\)：

\[
S_\Delta\ \equiv\ \mathcal V_{\mathrm{solder}}(z)\quad\Longrightarrow\quad \mathcal V_{\mathrm{solder}}(0)\equiv\mathcal V_{\mathrm{solder}}(1).
\]

**结论：在 (T⊥) 下，对情形 G/E/P 全部三种 Δ 分配，Free-XOR 局部引理成立（严格分布相等）。** 这不依赖「论文实际选哪种 Δ 结构」——三种都覆盖。

---

## 5. 区分器：EXP-03I 采样器为何不成立，以及唯一被否定的实例化

### 5.1 区分器 \(D_1\) / \(D_2\)：针对未按 Δ 结构采样的采样器

EXP-03I §3.2 步骤 3–4 对每电路「独立同法采样两条 label」，再算 \(\Delta_j^{(out)}[i,b]=D(j)[i,b]\oplus D(h)[i,\delta_j\oplus b]\)。这相当于每条 wire 的 label 对独立（非 Free-XOR）。于是其输出满足

\[
\Delta_j^{(out)}[i,0]\oplus\Delta_j^{(out)}[i,1]=(\text{均匀 }\lambda\text{-串})\ne 0\ \text{w.h.p.}
\]

而真实执行：情形 G/E 该 XOR **恒为 0**（§3.1 共享 Δ 两条相等）；情形 P 该 XOR \(=\Delta_j\oplus\Delta_h\)，**同一对 \((j,h)\) 跨所有结果位与输入线恒定**（§3.2）。故：

- \(D_1\)：检验「是否所有 \(j,i\) 满足 \(\Delta_j^{(out)}[i,0]=\Delta_j^{(out)}[i,1]\)」。真实 G/E 恒真，EXP-03I 采样器概率 \(2^{-\lambda}\) 真 ⇒ 完美区分。
- \(D_2\)：检验「\(\Delta_j^{(out)}[i,0]\oplus\Delta_j^{(out)}[i,1]\) 是否跨结果位 \(i\) 恒定」。真实 P 恒真，EXP-03I 采样器各 \(i\) 独立 ⇒ 区分。

**即：审阅意见①成立——EXP-03I 的采样器在 Free-XOR 下不是同分布的，其「严格分布相等」声称需修正。** 修正即 §4 的 \(S_\Delta\)（用共享/逐电路 Δ 生成，而非独立 label）。

### 5.2 区分器 \(D_3\)：\(\tau=\Delta[k]\) 且 \(\Delta_h\) 公开

若实例化同时满足 (T=) 与「\(\Delta_h\) 公开」（情形 G，check 与 eval 共享 Δ）：

\[
\tau_h=\Delta_h[k]\ (\text{公开}),\qquad z=c\oplus\tau_h=\operatorname{lsb}(Y_t)\oplus\Delta_h[k],
\]

P2 完美恢复 \(z\)，**局部引理失败**。这否定的仅是 (T=)+Δ公开 这一实例化。

### 5.3 定位：实例化排除条件，非论文攻击（接受审阅意见③）

- (T=)+Δ公开 违反会议版声称的 W 性质（互补 label 除 lsb 不可预测：Δ 公开 + τ=Δ[k] ⇒ 互补 label = 活动 ⊕ Δ 完全可预测），故**不是 Afshar 的实际构造**；
- (T=)+Δ隐藏（情形 E/P）不违反 W 性质，且 \(\tau_h\) 隐藏 ⇒ §4 采样器仍适用（把 \(\tau_c[w]=\Delta_c[k]\) 作为隐藏量的确定性函数，\(c=z\oplus\Delta_h[k]\) 因 \(\Delta_h\) 隐藏而均匀）；
- 因此 \(D_3\) 是**实例化排除条件**（实现时不得同时选 τ=Δ[k] 与 check/eval 共享 Δ），不是对论文原始构造的攻击。

---

## 6. 多位、跨 wire、跨位相关性（审阅意见⑤与视图第 6 项）

- **跨 wire（输入 vs 输出）**：§3.2 中 \(\Delta_j\oplus\Delta_h\) 在输入侧与输出侧是同一个量，因为同一电路的全局 Δ 贯穿所有 wire。\(S_\Delta\) 用同一组 \(\Delta_c\) 生成两侧，复现该相关；EXP-03I 若对两侧独立采样则破坏它（并入 \(D_2\)）。
- **跨位（多结果位）**：情形 P 下 \(\Delta_j\oplus\Delta_h\) 对同一对 \((j,h)\) **跨所有结果位相同**（同一 Δ）。\(S_\Delta\) 用同一 \(\Delta_c\) 贯穿所有位；EXP-03I §5 写「各位 \((\tau_h^{(i)},\Delta^{(i)})\) 独立」在 Free-XOR 下**错误**——应改为「τ 逐位独立，Δ 跨位共享（per circuit）」，已在本轮修正。
- **多电路**：\(\{\Delta_j\oplus\Delta_h\}_{j\ne h}\) 在情形 P 下逐电路独立均匀，采样器逐电路独立采样 \(\Delta_j\) 复现。

---

## 7. 判决与停止条件

### 7.1 局部引理：接受（Free-XOR 下）

> **命题**：\(\mathcal V_{\mathrm{solder}}(0)\equiv\mathcal V_{\mathrm{solder}}(1)\)，视图含活动标签 / τ 差 / 两组 label XOR 差 / Adjust+majority / τ 不开放 / Free-XOR 相关。

**判决：接受。** 在 §2 的显式随机变量模型下，对与论文 W 性质一致的每种实例化（(T⊥) 全部 G/E/P；(T=) 且 Δ 隐藏），§4 给出输入不含 \(z\) 的严格同分布采样器 \(S_\Delta\)。按停止条件第一条，接受 Free-XOR 下的局部引理。**但 EXP-03I 的采样器被 \(D_1/D_2\) 否定，必须由 \(S_\Delta\) 替换**——这是本轮的实质性修正，不是文字调整。

**排除**：(T=)+Δ公开 由 \(D_3\) 否定（§5.2），为实例化排除条件。

**相对 EXP-03I 的推进**：EXP-03I 把「τ⊥Δ」写成未定义前提 A3，结论「条件成立但实例化归属未决」；本轮取消 A3，对全部 Δ/τ 实例化逐一覆盖，得到「所有合法实例化下引理成立」——结论不再依赖未决的实例化归属。

### 7.2 项目级表述纠正（接受审阅意见④）

撤回 EXP-03I §6.3「PA-VFANN 整体维持 EXP-03D 的 NO-GO 关闭状态」这一表述。沿用此前对 EXP-03B 的纠正口径：

- **已 NO-GO 的是具体贡献/包装**：EXP-03B 的组合式 Compass+ACL+SNARK/MPC 包装；EXP-03D 的「专用有界队列相对通用 RAM-2PC 内部状态堆具符号成本优势」这一具体主张；
- **核心研究问题仍 HOLD**：严格策略隐私下「服务端持索引、客户端持秘密谓词、单方输出」的过滤 ANN 可行性，未被证明不可能，也未被关闭；
- 本轮局部引理成立**只闭合结果线联合视图这一构件**，不等于整体 batching 单方输出协议闭合（ORAM 轨迹、\(inst\_ctrl\)、索引初始化与回滚、恶意 P2 位置绑定 membership、结果相关中止仍在外，见 EXP-03F/G/H）。
- 因此：**不写整体 GO，也不写整体 NO-GO；核心问题维持 HOLD，具体贡献的 NO-GO 结论保留但不得外推为整体关闭。**

### 7.3 停止规则

本轮未扩证明目标、未搜文献、未写代码、未改旧报告（相对基线仅 1 个新增文件）。局部引理已达停止条件；不再追加队列结构、参数搜索或实例化枚举。若后续进入原型，须先闭合 §7.2 列出的整体构件，且把「Δ 分配结构 + τ 分布」作为显式实现约束写入（禁用 (T=)+Δ公开）。

---

## 8. 版本信息

| 项 | 内容 |
| --- | --- |
| 报告正文 commit | 见下方元信息提交（最终 HEAD 在最终汇报中给出） |
| 分支 | `exp03j-freexor-joint-sampler`（基线 `bfecfb0`） |
| 推送状态 | 提交后核验远端 HEAD 与本地一致 |
| 工作区状态 | 提交前确认除本报告外无改动；`git diff --check` 通过 |
