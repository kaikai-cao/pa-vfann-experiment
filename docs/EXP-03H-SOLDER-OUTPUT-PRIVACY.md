# EXP-03H：Solder 结果线 transcript 隐私审计

> 项目：PA-VFANN-19 后续（PA-VFANN-20）
> 目标：证明或否定一个具体代数引理——在 batching 的 Solder/MkBucket/Adjust 完整流程中，P2 获得的全部结果线 transcript，能否在不知结果 \(z\) 的情况下模拟。
> 范围：仅审计 §3 batching 的输出线代数与安全性质。不搜新文献、不改队列、不碰索引初始化、不做性能实验、不写代码。

---

## 0. 交付与证据状态

| 项 | 内容 |
| --- | --- |
| 基线 commit | `f6464951bd37b189a3ebb93ed5192d02b8403211`（EXP-03G 最终 HEAD） |
| 分支 | `exp03h-solder-output-privacy` |
| 新增文件 | `docs/EXP-03H-SOLDER-OUTPUT-PRIVACY.md`（本文，唯一新增） |
| 一手来源 | Afshar, Hu, Mohassel, Rosulek, *How to Efficiently Evaluate RAM Programs with Malicious Security*, EUROCRYPT 2015, LNCS 9056, DOI `10.1007/978-3-662-46800-5_27`（Springer 官方 PDF，本轮已核对 §2.2、§3.1–3.3） |
| 证据限制 | ePrint `2014/759.pdf` 在本环境仍 403；full version Appendix D 未逐字核验。本文只引用会议版可核验内容，未核验部分一律显式标注 |

**最终判决（见 §6）：HOLD。** 本轮只给一个结论，不把「引理成立」单独写成 GO——那样会混淆「代数引理」与「EXP-03G 定义的 GO（输出接口、标签认证、恶意 P2 模拟均闭合）」。分两层陈述：

- **本轮核心代数命题**（用户提问）：P2 可见的结果线 transcript 能否在不知 \(z\) 下模拟？——**肯定，且在明确条件下成立**（§6.1）。条件是：结果线选择位由 \(\mu=0\) 屏蔽、solder 差值只暴露 \(\tau\) 差值、多位联合独立性按 §2.2 逐位组合。用户给出的 \(b_j\oplus\delta_j=z\oplus\tau_h\) 是这一证明的核心，核验为正确（§2.3）。
- **整体（命题 3）**：仍 HOLD。三个具体待补项 G1/G2/G3（§6.2）都不是不可修复矛盾，故不判 NO-GO；但也没到「均闭合」，故不判 GO。

---

## 1. 必须先固定的记号与原文事实

### 1.1 wire-label 语义（§2.2，原文可核验）

采用 point-permute：wire label 描述 \(W\) 为 \(m\times 3\) 数组，\(W[i,0],W[i,1]\) 为两条 label，\(\operatorname{lsb}(W[i,b])=b\)，\(W[i,2]\) 为 translation bit \(\tau_i\)，使得 \(W[i,W[i,2]]\) 编码 false。记 \(\tau(W)=W[1,2]\cdots W[m,2]\)。定义：

- \(W|_v=(W[1,v_1],\dots,W[m,v_m])\)：按**选择位** \(v\) 取 label；
- \(W|_*x:=W|_{x\oplus\tau(W)}\)：按**真值** \(x\) 取 label（因为 \(W[i,\tau_i]\) 编码 false）。

解码：\(\operatorname{lsb}(Y)\oplus\tau(D)\) 得明文。**因此真值 \(x\) 对应的选择位是 \(x\oplus\tau_i\)**——这是全文代数的基石。

§2.2 给出两条我们反复使用的性质：

- **部分解码**：揭示 \((\mu,\tau(D)\land\mu)\) 时，评估方只学到 \(\mu_i=1\) 那些位的输出；原文明确「Such an adversary's view is then independent of \(f(x)\land\mu\)」。
- **互补 label 不可预测**：原文「the adversary's view is independent of the complementary wire labels \(D|_{*}f(x)\), except possibly in their least significant bits」，从而得到 authenticity。
- **Free-XOR 相容**：原文「when using the Free-XOR optimization … \(E[i,0]\oplus E[i,1]=\Delta\) for all i … This distribution satisfies all the properties of \(W\) used above」。注意此处只声明**分布层面**的性质保持，并未讨论 cut-and-choose 中 check circuit 打开是否泄露 \(\Delta\)（见 §4.3）。

### 1.2 Solder / MkBucket / Adjust / EvalBucket（§3.2，原文逐字）

`Solder(A,A')`（A,A' 为 wire-label 描述）

1. P1 打开对 \(\tau(A),\tau(A')\) 的 \(F_{xcom}\) 承诺，使 P2 得到 \(\tau_i=\tau(A)_i\oplus\tau(A')_i\)（逐位置）；
2. P1 打开对 \(A[i,b]\) 与 \(A'[i,\tau_i\oplus b]\) 的承诺，使 P2 得到 \(\Delta[i,b]=A[i,b]\oplus A'[i,\tau_i\oplus b]\)（逐位置、逐 \(b\in\{0,1\}\)）。

`MkBucket(B,hd)`：对每个 \(j\in B\setminus\{hd\}\)，
\(\Delta(hd\!\to\!j)=\text{Solder}(E(hd),E(j))\)（输入侧），
\(\Delta(j\!\to\!hd)=\text{Solder}(D(j),D(hd))\)（输出侧），
\(\Delta(hd\!\to\!hd)=\) 全零。

`Adjust(X,Δ)`：逐位 \(\tilde X[i]=X[i]\oplus\Delta[i,\operatorname{lsb}(X[i])]\)。

`EvalBucket(B,X,hd)`：对每个 \(j\in B\)，\(\tilde X_j=\text{Adjust}(X,\Delta(hd\!\to\!j))\)，\(Y_j=\text{Adjust}(\text{Eval}(GC(j),\tilde X_j),\Delta(j\!\to\!hd))\)，返回 \(\{Y_j\}_{j\in B}\) 的多数元素。

### 1.3 角色与可见性（沿用 EXP-03E 修正审计，已核验）

\(P_1=C=\) garbler（持秘密谓词 \(P\)、凭证、\(D/\tau(D)\)）；\(P_2=S=\) evaluator（持索引 \(I\)，经 OT 输入 \(x_2\)）。§3.2 步骤 3(f) 中 P1 对 \(i\in B_t\) 打开 \(\tau(\texttt{inst}(D(i)))\)，3(g) 中 P2 回送 \(\tilde Y=\texttt{inst}(Y_t)\)，**双方解码** \(\texttt{inst}_t=\operatorname{lsb}(\tilde Y)\oplus\tau(\texttt{inst}(D(hd)))\)，P1 验证标签真实性。§2.1 把 RAM 输出编码为 \(\texttt{inst}=(\texttt{halt},z)\)。这些是必须修改的接口（EXP-03G 已确立），本轮在此基础上继续。

---

## 2. Solder 两组差值的完整代数表达式

### 2.1 输入侧 \(\Delta(hd\!\to\!j)=\text{Solder}(E(hd),E(j))\)

令 \(a_i=\tau(E(hd))_i\)，\(a'_i=\tau(E(j))_i\)，\(\tau^{(in)}_i=a_i\oplus a'_i\)。P2 可见：

\[
\tau^{(in)}_i=\tau(E(hd))_i\oplus\tau(E(j))_i
\]
\[
\Delta^{(in)}_j[i,0]=E(hd)[i,0]\oplus E(j)[i,\tau^{(in)}_i]
\]
\[
\Delta^{(in)}_j[i,1]=E(hd)[i,1]\oplus E(j)[i,\tau^{(in)}_i\oplus 1]
\]

作用：`Adjust(E(hd)[i,v],\Delta^{(in)}_j)` \(=E(hd)[i,v]\oplus\Delta^{(in)}_j[i,v]=E(j)[i,\tau^{(in)}_i\oplus v]\)，即把 head 输入 label 搬到电路 \(j\) 的输入空间，选择位被 \(\tau^{(in)}_i\) 扭转。

### 2.2 输出侧 \(\Delta(j\!\to\!hd)=\text{Solder}(D(j),D(hd))\)

令 \(\tau_j=\tau(D(j))_i\)，\(\tau_h=\tau(D(hd))_i\)，\(\delta_j=\tau_j\oplus\tau_h\)。P2 可见：

\[
\delta_j=\tau(D(j))_i\oplus\tau(D(hd))_i
\]
\[
\Delta^{(out)}_j[i,0]=D(j)[i,0]\oplus D(hd)[i,\delta_j]
\]
\[
\Delta^{(out)}_j[i,1]=D(j)[i,1]\oplus D(hd)[i,\delta_j\oplus 1]
\]

作用：`Adjust(D(j)[i,b],\Delta^{(out)}_j)` \(=D(j)[i,b]\oplus\Delta^{(out)}_j[i,b]=D(hd)[i,\delta_j\oplus b]\)，把电路 \(j\) 的输出 label 搬回 head 输出空间。

### 2.3 用户给出的关系：核验为**成立**

设某结果输出位真值为 \(z\)。电路 \(j\) 的活动输出 label 为 \(Y_j=D(j)[i,b_j]\)。由 §2.1「真值 \(x\leftrightarrow\) 选择位 \(x\oplus\tau\)」得

\[
b_j=z\oplus\tau_j .
\]

经 `Adjust` 回到 head 空间后，其选择位为

\[
\delta_j\oplus b_j=(\tau_j\oplus\tau_h)\oplus(z\oplus\tau_j)=z\oplus\tau_h .
\]

即用户写的 \(b_j\oplus\delta_j=z\oplus\tau_h\)。**该等式正确**，且关键含义是：所有电路 \(j\in B_t\) 的结果 label 经 solder 后都落到**同一个** head 选择位 \(z\oplus\tau_h\)——这正是 majority 能工作的原因，也正是隐私论证的关键（见 §3）。

**一个重要修正（接受用户意见）**：因此「其他电路的合法 label 一定被拒绝」的表述不准确。正确的说法是：其他电路 \(j\) 的合法 label 经**正确的** `Adjust(·,Δ^{(out)}_j)` 后，本来就应当变成 head 空间同一输出位置的合法 label（选择位同为 \(z\oplus\tau_h\)），majority 正是在这些之间取多数。真正必须拒绝的是：(i) 未经正确 solder 差值转换的 label；(ii) 属于别的输出 wire / 别的 timestep / 别的 bucket 实例但恰好是某个合法 label 的「跨位置替换」。EXP-03G 的「位置绑定 membership」应改写为「**位置+timestep+bucket 实例绑定的 solder 后 membership**」。

### 2.4 head 自身与 majority

\(\Delta(hd\!\to\!hd)=\) 全零，故 head 电路自身 `Adjust` 不改变任何 label，其输出 label 的选择位本就是 \(z\oplus\tau_h\)。于是所有 \(j\in B_t\)（含 hd）的结果 label 在 head 空间的选择位一致为 \(z\oplus\tau_h\)，majority 得到 \(Y_t\)，其 \(\operatorname{lsb}(Y_t)=z\oplus\tau_h\)。

---

## 3. 联合分布：活动 label、translation 差值、label XOR 差值

固定一个结果位 \(i\) 与一个 bucket \(B_t\)（head \(h\)）。定义 P2 在该结果线上可见的量：

| 记号 | 含义 | P2 是否可见 |
| --- | --- | --- |
| \(b_j=\operatorname{lsb}(Y_j)\) | 电路 \(j\) 活动输出 label 的选择位 | 是（P2 执行 Eval 得到 \(Y_j\)） |
| \(\delta_j\) | solder translation 差值 \(\tau_j\oplus\tau_h\) | 是（Solder 步 1 打开） |
| \(\Delta^{(out)}_j[i,0],\Delta^{(out)}_j[i,1]\) | solder label XOR 差值 | 是（Solder 步 2 打开） |
| \(z\oplus\tau_h\) | head 空间结果选择位（= \(\operatorname{lsb}(Y_t)\)） | 是（P2 执行 EvalBucket 得到 \(Y_t\)） |
| \(\tau_h=\tau(result(D(hd)))_i\) | head 结果线绝对 translation bit | **否**（我们要隐藏；EXP-03G 拆分后 \(\mu=0\)） |
| \(D(hd)[i,\cdot]\) 的完整描述、\(\tau(D(hd))\) | head 结果线 label 描述 | **否**（P1 独占） |

### 3.1 关键观测：P2 的所有结果线可见量只依赖 \(z\oplus\tau_h\) 与随机差值

由 §2.3，对每个 \(j\)：

\[
\operatorname{lsb}(Y_j)\oplus\delta_j=(\,z\oplus\tau_j\,)\oplus(\,\tau_j\oplus\tau_h\,)=z\oplus\tau_h .
\]

也就是说，P2 从每个电路得到的选择位 \(b_j\) 与 translation 差值 \(\delta_j\) **互相抵消掉 \(\tau_j\)**，只剩 \(z\oplus\tau_h\)。逐电路 \(j\) 提供的不是关于 \(z\) 的新信息，而是同一 masked 值 \(z\oplus\tau_h\) 的重复视图。

再看 label XOR 差值。由定义：

\[
\Delta^{(out)}_j[i,b]=D(j)[i,b]\oplus D(hd)[i,\delta_j\oplus b],\quad b=0,1 .
\]

P2 知道 \(\Delta^{(out)}_j[i,\cdot]\) 与活动 label \(Y_j=D(j)[i,b_j]\)，于是可算出 head 空间的活动 label：

\[
Y_j\oplus\Delta^{(out)}_j[i,b_j]=D(hd)[i,\delta_j\oplus b_j]=D(hd)[i,z\oplus\tau_h] .
\]

但 \(D(hd)[i,z\oplus\tau_h]\) 本就是 P2 通过 EvalBucket 得到的 \(Y_t\) 的候选之一——**这不是新信息**。同理，P2 也能用 \(b'=b_j\oplus1\) 算出 \(D(hd)[i,\delta_j\oplus b_j\oplus1]=D(hd)[i,z\oplus\tau_h\oplus1]\)，即 head 结果线的**另一条 label**（互补 label）——见 §4 的关键讨论。

**结论（引理的核心）**：只要 \(\tau_h\) 对 P2 隐藏，P2 的全部结果线可见量都是 \(z\oplus\tau_h\)（一次性掩码）与随机 \(\tau\) 差值的函数，与 \(z\) 独立。祈祷「每个 \(D(i)\) 独立」是不够的——真正起作用的是 §2.2 的部分解码性质：\(\mu=0\) 时 view 独立于 \(f(x)\land\mu\)（这里 \(f(x)=z\)）。Solder 把原本独立的 \(D(j)\) 连接起来，但连接所暴露的只是**差值** \(\delta_j\)，而 \(\delta_j\) 与 \(z\) 无关；它没有把 \(\tau_h\) 的绝对值暴露出来。

---

## 4. 攻击面：能否用多输出位或多电路恢复互补 label / \(z\)

### 4.1 单个结果位、单电路：不能恢复 \(z\)

P2 有 \(z\oplus\tau_h\)（经选择位）但缺 \(\tau_h\)。由 §2.2 的部分解码性质，揭示 \((\mu=0,\tau(D)\land 0=\varepsilon)\) 时 view 独立于 \(z\)。Solder 差值 \(\delta_j\) 与 label XOR 差值都是关于 \(\tau\) 的随机量，不提供 \(\tau_h\)。**结论：不能恢复 \(z\)。**（这是引理成立的一半。）

### 4.2 单个结果位、多电路：不能恢复 \(z\)，但能算出互补 label（关键！）

P2 从 \(j\) 可算出 head 结果线的两条 label（§3.1）：活动 \(D(hd)[i,z\oplus\tau_h]\) 与互补 \(D(hd)[i,z\oplus\tau_h\oplus1]\)。这**直接违反** §2.2 的「互补 label 不可预测（除 lsb）」性质——但注意：

- 这违反的是**在 P2 侧补全 head label 对**的能力，来自 Solder 的 label XOR 差值 \(\Delta^{(out)}_j[i,\cdot]\) 把两条 head label 都用 XOR 差分暴露了；
- 它**不等于**恢复 \(z\)：两条 label 的选择位 \(z\oplus\tau_h\) 与 \(z\oplus\tau_h\oplus1\) 仍被 \(\tau_h\) 掩码，P2 不知哪条对应真值 1（缺 \(\tau_h=\tau(result(D(hd)))_i\)）。

这一点必须写进判决：**Solder 的 label XOR 差值确实让 P2 拿到了 head 结果线的互补 label，但这只损伤「label 不可预测」这一 authenticity 资源，不直接泄露 \(z\)。** 这也是为什么把结果线不开放 \(\tau\)（\(\mu=0\)）是必要条件：一旦 \(\tau_h\) 开放，\(z=\operatorname{lsb}(Y_t)\oplus\tau_h\) 立即暴露。

### 4.3 多输出位：需要验证跨位独立性；原文支持但有边界

若结果有 \(m\) 位，每位 \(i\) 有独立 \(\tau^{(i)}_h\)。§2.2 的 W 分布是「逐位置独立随机」（translation bit 逐位独立），部分解码性质是逐位陈述的（揭示 \((\mu,\tau(D)\land\mu)\) 只影响 \(\mu_i=1\) 的位）。取 \(\mu=0^m\) 时，所有位的 view 都与 \(z\) 独立。**但**：

- **Free-XOR 例外**：原文明确当使用 Free-XOR 时 label 矩阵来自由单一秘密 \(\Delta\) 参数化的分布，「satisfies all the properties of W used above」。在 Free-XOR 下，同一 wire 的两条 label 满足 \(D[i,0]\oplus D[i,1]=\Delta\)，故**互补 label = 活动 label \(\oplus\Delta\)**。若 P2 通过 §4.2 拿到某电路的活动 label 与 XOR 差值，再结合任意处泄露的 \(\Delta\)，可推导更多 label 关系。原文并未证明「\(\mu=0\) 时整个 \(m\) 位结果 label 集合的联合分布与 \(z\) 独立」在 solder 场景下仍成立——它只给了单个 garbling 的性质。**结论：多位独立性在本引理中是「有原文支撑但未逐字证明」；若坚持严格证明，需把 §2.2 的性质按位组合，并把 Free-XOR 的 \(\Delta\)-相关性按本条处理。**

### 4.4 多电路：不放大 \(z\) 泄露

§3.1 已说明每个 \(j\) 只给同一 \(z\oplus\tau_h\)。多个电路 \(j\) 提供 \(b_j=z\oplus\tau_j\) 与 \(\delta_j=\tau_j\oplus\tau_h\)，二者异或恒为 \(z\oplus\tau_h\)；\(\tau_j\) 逐电路随机，故 \(b_j\) 在给定 \(z\oplus\tau_h\) 后是均匀的。**结论：多电路不提供关于 \(z\) 的额外信息。**

### 4.5 check circuits 与 evaluation circuits 的关联

§3.2 step 2：\(S_c\)（check）的 \(E(i),D(i),GC(i)\) 被完全打开；step 3(a)：bucket \(B_t\subset S_e\)（evaluation），head \(\in B_t\)。所以：

- head 与所有 bucket 成员都来自 \(S_e\)，其 \(D(i)\) 未被打开；check circuits 的 label 描述虽公开，但**不进入 bucket**、不与 head 做 Solder。因此 check circuit 的公开 label 描述不直接进入结果线 transcript。
- 但 cut-and-choose 的统计保证保证 bucket 内多数电路正确（§3.2 step 2 + §3.3）。这影响的是 output correctness，不是结果隐私。

---

## 5. hybrid 序列：真实 transcript → \(\mathcal S(1^\lambda,I,L_S)\)

设修改接口为 \((st,\texttt{inst\_ctrl},\texttt{block},\texttt{result})\)（EXP-03G），结果线 \(\mu=0\)，固定 \(E\) 轮。构造混合序列。记号：真实执行 \(H_0\)，理想执行 \(H_6=\mathcal S(1^\lambda,I,L_S)\) 的输出分布；\(L_S=(R_I,\mathrm{ver},q,E,\text{public params})\)，\(I\) 为 P2 私有输入（腐败方辅助输入，见 EXP-03E 修正）。

**\(H_0\)**：真实协议，P1 诚实持 \(P\)，P2 诚实。结果线选择位 \(z\oplus\tau_h\)，solder 差值 \(\delta_j\)，label XOR 差值 \(\Delta_j[i,\cdot]\)。

**\(H_1\)：把每个结果线活动 label 的选择位替换为均匀随机 \(\rho_i\)**（保留所有 solder 差值、label XOR 差值、其他 transcript 不变）。
- **依据**：§2.2 部分解码性质，\(\mu=0\Rightarrow\) view 独立于 \(z\);且 \(z\oplus\tau_h\) 中 \(\tau_h\) 均匀 ⇒ \(z\oplus\tau_h\) 均匀，故替换不可区分。
- **这是关键一步**：它把结果线的「\(z\)-相关量」从 transcript 中抹掉，而**不需要知道 \(z\)**。替换后所有结果线可见选择位与 \(z\) 独立。

**\(H_2\)：把 head 结果线的 label XOR 差值 \(\Delta^{(out)}_j[i,\cdot]\) 替换为对「两条 head label 的随机 XOR 差分」的采样**（模拟器自选两条 head label \(L_0,L_1\)，令 \(\Delta_j[i,b]=D(j)[i,b]\oplus L_{\delta_j\oplus b}\)）。
- **依据**：对 P2 而言 \(D(j)[i,\cdot]\) 来自 §2.2 的 W 分布（point-permute），\(\Delta\) 是两条 label 的 XOR；§4.2 表明 P2 至多借此得到 head 的互补 label，而互补 label 在 point-permute 下除 lsb 外不可预测。模拟器用等价分布采样。此处需小心 Free-XOR 相关性（§4.3）。

**\(H_3\)：把 \(\delta_j=\tau(D(j))_i\oplus\tau(D(hd))_i\) 替换为独立均匀随机 \(\delta'_j\)**（保持每轮、每位、每电路独立）。
- **依据**：\(\tau(\cdot)\) 逐位均匀随机，XOR 仍均匀；\(\delta_j\) 与 \(z\) 无关。

**\(H_4\)：把 ORAM 逻辑访问序列与 \(\texttt{inst\_ctrl}\) 的 \(\tau\) 开放替换为「由 \(L_S,I\) 生成的模拟序列」**。
- **依据**：语义 A 下逻辑读序列是 \((R_I,\mathrm{ver},q,E)\) 的确定函数，与 \(P\) 无关；§3.3 的 P2-corrupted 模拟器本就「generates a simulated ORAM memory-access sequence」并「equivocates on the decommitment to \(\tau(\texttt{inst}(D(i)))\), chosen so that the visible output wires will decode to the next simulated ORAM memory instruction」——这一步用的是**模拟指令**，不是 \(z\)。
- **注意**：这一步依赖 1600 次 dummy-inclusive 固定读（EXP-03F/03G 的 7 项规则），即「逻辑序列与 \(P\) 无关」必须先成立；否则 \(H_4\) 不成立。这是**外部依赖**，本轮不重新证明。

**\(H_5\)：把 P1 的结果线标签真实性检查（3(g) 类型的 P1 验证）替换为模拟器的确定性检查**（P2 回送的结果 label \(\tilde Y\) 必须等于模拟器预定的 visible result labels，否则 abort）。
- **依据**：§3.3「Instead of checking P2's claimed wire labels in step (3g), the simulator simply aborts if these wire labels are not the pre-determined visible output wire labels」。拆分接口后，这一步作用于 result 线而非 \(\texttt{inst}\)；位置绑定 membership 见 §2.3 修正。
- **剩余风险**：恶意 P2 的六类攻击（EXP-03G §5）在「solder 后位置绑定 membership + §2.2 互补 label 不可预测」下逐项受阻，但**未经形式化**；本轮仍未闭合。

**\(H_6\)：把 abort 与消息长度替换为 \(\mathcal S(1^\lambda,I,L_S)\) 的输出**。
- **依据**：§3.3 对恶意 P2 用 s-wise OT 分享防 selective failure，「match the probability of an honest P2 aborting … up to negligible difference」；abort 不依赖 \(P\) 的这一部分沿用原文。
- **但**：若存在「与结果相关的中止」（由 w-key 分支或结果线认证触发），则 abort 依赖 \(z\oplus\tau_h\) 从而依赖 \(P\)——这正是 EXP-03F 识别的 w-key 风险面，本轮确认它仍是 \(H_6\) 的未闭合点。

**汇总**：\(H_0\approx_c H_1\approx_c H_2\approx_c H_3\approx_c H_4\approx_c H_5\approx_c H_6=\mathcal S(1^\lambda,I,L_S)\)。前四步（\(H_1\)–\(H_4\)）有 §2.2 部分解码性质与 §3.3 原文支撑，构成引理的主要证明；\(H_5,H_6\) 依赖未形式化的恶意 P2 攻击分析与中止独立性。

---

## 6. 判决

### 6.1 对命题的直接回答

> **命题**：在 batching 的 Solder/MkBucket/Adjust 完整流程中，P2 获得的全部结果线 transcript，能否在不知结果 \(z\) 的情况下模拟？

**答案：能，在下列条件下**（这些条件是命题的一部分，不是附加放宽）：

1. **结果线选择位用 §2.2 部分解码屏蔽**（\(\mu=0\)，不向 P2 开放 \(\tau(result(D(\cdot)))\)）。否则 \(z=\operatorname{lsb}(Y_t)\oplus\tau_h\) 立即可得。
2. **solder 差值只暴露 \(\tau\) 差值与 label XOR 差值，不暴露 \(\tau_h\) 绝对值**。§2.2/§3.2 的 Solder 定义确实如此；P2 可见的 \(b_j\oplus\delta_j=z\oplus\tau_h\) 是一次性掩码。
3. **多输出位的联合独立性按 §2.2 逐位性质组合**，且不引入 Free-XOR 的 \(\Delta\)-跨位相关（见 §4.3）。

在这些条件下，\(H_1\)–\(H_4\) 给出从真实 transcript 到不依赖 \(z\) 的模拟 transcript 的可核验序列；**用户给出的代数关系 \(b_j\oplus\delta_j=z\oplus\tau_h\) 是这个证明的核心，且核验为正确**。

### 6.2 为什么整体仍是 HOLD，而不是 GO

命题 3（完整的 batching 单方输出协议）还要求三件本轮**未闭合**的事，均非「否定」而是「待补」：

- **(G1) Free-XOR 与 cut-and-choose 的 \(\Delta\)-相关性（§4.3）**：会议版 §2.2 只声明 Free-XOR 分布「satisfies all properties of W」，未讨论 check circuit 打开是否泄露 \(\Delta\) 及 solder 场景下的跨位相关。这是**实例化条件**：要么结果线不用 Free-XOR（用独立 label），要么证明 check 打开不泄露结果线 \(\Delta\)。这是可一次性锁定的实现约束，不是不可修复矛盾。
- **(G2) 恶意 P2 六类攻击的形式化（\(H_5\)）**：EXP-03G 已逐项给出受阻论证，但未形式化；位置绑定改为「solder 后 membership」后需重证。
- **(G3) 结果相关的中止独立性（\(H_6\)）**：承接 EXP-03F 的 w-key 风险面，本轮确认它仍是唯一的中止泄露通道。

三项都属于「有明确、一次性解决路径」，符合 HOLD 的定义，而非 NO-GO 的「明确不可修复矛盾」。

### 6.3 停止规则

- 本轮已把命题 3 压缩为三个**具体**待补项（G1/G2/G3），不再扩文献、不再改队列、不再碰索引初始化。
- 若 G1/G2/G3 全部闭合 ⇒ GO 进入最小原型；若其中任一项出现不可修复矛盾（尤其 G1 若证明 Free-XOR 必然泄露结果线 \(\Delta\) 且无替代实例化）⇒ 对 batching 适配路线判 NO-GO，但**不宣判 PA-VFANN 整体**。
- 维护既有边界：语义 B 的否定结论保留；1600 只是逻辑邻居读非物理访问；不把「论文恶意安全」当作单方输出 + \(L_S\)-only 视图已证。

---

## 7. 版本信息

| 项 | 内容 |
| --- | --- |
| 报告正文 commit | `b84b16bf5f8d1477cb158e511c872444b0fd070b` |
| 最终 HEAD | 见下方元信息提交（本提交之后的 HEAD 在最终汇报中给出） |
| 分支推送状态 | 报告正文 commit 已推送至 `origin/exp03h-solder-output-privacy`，`git push` 成功、无 SSL/502 回退 |
| 工作区状态 | 提交前已确认除本报告外无改动 |
