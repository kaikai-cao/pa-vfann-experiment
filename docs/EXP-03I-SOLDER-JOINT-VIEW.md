# EXP-03I：Solder 结果线联合视图隐私——局部引理的联合采样器证明

> 项目：PA-VFANN-21（承接 PA-VFANN-20 / EXP-03H 的独立审阅意见）
> 目标：只证明或反驳**一个局部命题**——固定结果线视图的完整六要素后，\(\mathcal V_{\mathrm{solder}}(z=0)\) 与 \(\mathcal V_{\mathrm{solder}}(z=1)\) 是否分布等价。
> 范围：**不搜新文献、不写实验代码、不改队列、不碰索引初始化、不动 ORAM**。只做纯推导，依据仅为会议版 §2.2/§3.2 已核验事实（见 EXP-03H §0/§1）与代数。
> 方法修正：放弃 EXP-03H 的 hybrid「逐项替换」（用户指出的 H1→H2 缺口成立），改为**从头联合重采样**——从隐藏随机量一次性生成全部可见量，联合一致性由构造保证。

---

## 0. 交付与证据状态

| 项 | 内容 |
| --- | --- |
| 基线 commit | `d417cbed8fd9d354b5ea89221a7fb52214d375cd`（EXP-03H 最终 HEAD） |
| 分支 | `exp03i-solder-joint-view` |
| 新增文件 | `docs/EXP-03I-SOLDER-JOINT-VIEW.md`（本文，唯一新增） |
| 一手来源 | Afshar, Hu, Mohassel, Rosulek, *How to Efficiently Evaluate RAM Programs with Malicious Security*, EUROCRYPT 2015, LNCS 9056, DOI `10.1007/978-3-662-46800-5_27`（沿用 EXP-03H 已核验的 §2.2、§3.1–3.3 引文，本轮不新增引用） |
| 证据限制 | ePrint `2014/759.pdf` 仍 403；full version Appendix D 未逐字核验。凡涉及 τ 与 Δ 显式关系、check circuit 打开细节，均按「会议版未给 → 列为实例化条件」处理，不臆造。 |

**一句话结论**：局部命题**不是无条件成立**。在「τ 与 label 差独立、各电路独立 garble」的实例化下，可给出不依赖 z 的联合采样器并证明**严格分布相等**（§3、§4.1）；在「τ 绑定全局 Δ 的某一位」或「garbling 重用」的实例化下，P2 有**具体区分器**可恢复 z（§4.2、§4.3）。两种结果**都不自动决定 PA-VFANN 整体生死**（§6）。

---

## 1. 命题的精确定义：视图 \(\mathcal V_{\mathrm{solder}}\) 的完整六要素

### 1.1 记号（沿用 EXP-03H §1）

- point-permute：wire \(i\) 两条 label \(D[i,0],D[i,1]\)，\(\operatorname{lsb}(D[i,b])=b\)；translation bit \(\tau_i\) 使 \(D[i,\tau_i]\) 编码 \(0\)。**真值 \(x\leftrightarrow\) 选择位 \(x\oplus\tau_i\)**。
- 固定一个结果输出位 \(i\)、一个 bucket \(B_t\)、head \(h\in B_t\)。记
  \[
  \tau_j=\tau(D(j))_i,\quad \tau_h=\tau(D(h))_i,\quad \delta_j=\tau_j\oplus\tau_h,\quad c=z\oplus\tau_h .
  \]
- Solder 输出侧 \(D(j)\to D(h)\) 暴露（§1.2，`Solder(A,A')` 取 \(A=D(j),A'=D(h)\)）：
  \[
  \Delta_j^{(out)}[i,b]=D(j)[i,b]\oplus D(h)[i,\delta_j\oplus b],\quad b=0,1 .
  \]
- Solder 输入侧 \(E(h)\to E(j)\) 暴露：
  \[
  \tau^{(in)}_j=\tau(E(h))_{i'}\oplus\tau(E(j))_{i'},\quad
  \Delta_j^{(in)}[i',b]=E(h)[i',b]\oplus E(j)[i',\tau^{(in)}_j\oplus b] .
  \]
- \(Y_j=D(j)[i,b_j]\) 为电路 \(j\) 的活动输出标签，\(b_j=z\oplus\tau_j\)；\(\tilde Y_j=\operatorname{Adjust}(Y_j,\Delta_j^{(out)})=D(h)[i,\delta_j\oplus b_j]=D(h)[i,c]\)；majority 结果 \(Y_t=D(h)[i,c]\)，\(\operatorname{lsb}(Y_t)=c\)。

### 1.2 视图六要素（按审阅意见逐项形式化）

固定 \(z\in\{0,1\}\)，定义 P2 在结果线上的**完整可见视图** \(\mathcal V_{\mathrm{solder}}(z)\) 为以下六类对象的联合：

| # | 审阅意见要求 | 本命题中的形式化对象 |
| --- | --- | --- |
| V1 | 所有电路的活动输出标签 | \(\{Y_j=D(j)[i,b_j]\}_{j\in B_t}\)，其中 \(b_j=z\oplus\tau_j\)，\(\operatorname{lsb}(Y_j)=b_j\) |
| V2 | Solder 打开的 translation XOR 差值 | \(\{\delta_j=\tau_j\oplus\tau_h\}_{j\in B_t,j\ne h}\)（\(\delta_h=0\)）；输入侧 \(\{\tau^{(in)}_j\}\) |
| V3 | 两组 label XOR 差值 | 输出侧 \(\{\Delta^{(out)}_j[i,0],\Delta^{(out)}_j[i,1]\}_{j\ne h}\)；输入侧 \(\{\Delta^{(in)}_j[i',0],\Delta^{(in)}_j[i',1]\}_{j\ne h}\) |
| V4 | Adjust 后标签及 majority 结果 | \(\{\tilde Y_j=D(h)[i,c]\}_{j\in B_t}\) 与 \(Y_t=D(h)[i,c]\)，\(\operatorname{lsb}(Y_t)=c\) |
| V5 | 结果线 translation bit 不开放 | \(\mu=0\)：\(\tau_h,\{\tau_j\}_{j\in B_t}\) **均不对 P2 开放**（假设 A1）。head 结果线描述 \(D(h)[i,\cdot]\) 为 P1 独占 |
| V6 | Free-XOR 实例化下的标签相关性 | 参数化：每条结果线 \(D(\cdot)[i,0]\oplus D(\cdot)[i,1]=\Delta_{(\cdot)}\)；τ 与 Δ 的关系为**待定实例化参数**（见 §4） |

### 1.3 命题

\[
\boxed{\mathcal V_{\mathrm{solder}}(0)\;\overset{?}{\equiv}\;\mathcal V_{\mathrm{solder}}(1)}
\]

其中 \(\equiv\) 指分布严格相等（从而计算不可区分）。审阅意见的核心立场——「局部视图不直接暴露 z」不等于「联合视图可在不知 z 时模拟」——**完全正确**：V1–V6 不是六个独立量，它们通过隐藏量 \(\tau_h,\{\tau_j\},D(\cdot)[i,\cdot]\) 强相关；任何只替换单一量而保留其余的论证（EXP-03H 的 H1→H2）都可能出现联合不一致。本命题必须对**整个联合分布**作答。

---

## 2. 方法论修正：为什么放弃 hybrid 逐项替换

EXP-03H 的 \(H_0\to H_6\) 序列中，\(H_1\) 把「活动选择位替换为均匀 \(\rho_i\)」但保留所有 solder 差值与 label XOR 差值，\(H_2\) 再单独替换 label XOR 差值。审阅意见指出这是**最实质的缺口**，理由精确：

1. 活动选择位 \(b_j=z\oplus\tau_j\) 决定 P2 拿到哪条活动标签 \(Y_j\)；
2. \(\Delta_j^{(out)}\) 又把 \(Y_j\) 与 head 两条标签绑定（\(Y_j\oplus\Delta^{(out)}_j[i,b_j]=D(h)[i,c]\)）；
3. 只改 \(b_j\) 而不联动改 \(Y_j,\Delta^{(out)}_j,\tilde Y_j\) 及承诺打开，会破坏 \(b_j\oplus\delta_j=c\) 与 majority 一致性——替换后的 transcript 可能根本不是任何合法执行的输出。

**修正是结构性的**：不逐项替换真实 transcript，而是**从头构造一个联合采样器**——先采样少量隐藏随机量（\(c\)、\(\{\delta_j\}\)、各线 label 描述），再由确定性函数一次性导出 V1–V6 的全部对象。这样：

- 联合一致性由「所有可见量都是同一组隐藏量的函数」**自动保证**，无需逐 hybrid 检查相关性；
- 只要采样器输入不含 \(z\)，输出分布与 \(z\) 无关即直接得证，不存在「替换后相关性丢失」问题。

这是比 hybrid 更强、更干净的证明策略，也是本文相对 EXP-03H 的实质推进。

---

## 3. 局部引理 L1：\(\tau\perp\Delta\) 实例化下的联合采样器与严格分布相等

### 3.1 实例化假设（L1 的前提）

- **(A1)** 结果线 \(\mu=0\)：\(\tau_h,\{\tau_j\}\) 不对 P2 开放（V5）。
- **(A2)** 各电路 \(GC(j)\) 独立 garble：\(\{D(j)[i,\cdot]\}_{j\in B_t}\) 与 \(\tau_j\) 联合独立；不存在被复制重用的 garbling。
- **(A3)** \(\tau\) 与 label 差独立：对每条结果线，\(\tau_{(\cdot)}\) 作为 garbling 元信息独立均匀选取，**不是** label 值或 label 差 \(\Delta_{(\cdot)}\) 的函数。非 Free-XOR 时 label 对 \((D[i,0],D[i,1])\) 独立均匀（受 \(\operatorname{lsb}\) 约束）；Free-XOR 时 \(D[i,1]=D[i,0]\oplus\Delta\) 且 \(\tau\perp\Delta\)。

> (A3) 正是会议版 §2.2「Free-XOR 分布 satisfies all the properties of W」的必要解读：若 \(\tau\) 可从互补标签算出，则违反 W 的「complementary labels unpredictable except lsb」。这一点在 §4.2 会作为**可检验的分水岭**。

### 3.2 联合采样器 \(\mathcal S\)（输入不含 z）

固定安全参数 \(\lambda\)。采样器输出与 \(\mathcal V_{\mathrm{solder}}\) 同型的对象：

1. **采样 head 选择位**：\(c\leftarrow\{0,1\}\) 均匀。
2. **采样 τ 差值**：对每个 \(j\ne h\)，\(\delta_j\leftarrow\{0,1\}\) 均匀；置 \(\delta_h=0\)。由此对每 \(j\) 置
   \[
   b_j:=c\oplus\delta_j .
   \]
3. **采样各结果线 label 描述**（用 (A2)(A3)）：
   - head：取 \(L_0=D(h)[i,0]\leftarrow\{0,1\}^{\lambda}\) 且 \(\operatorname{lsb}(L_0)=0\)；若非 Free-XOR，取 \(D(h)[i,1]\leftarrow\{0,1\}^{\lambda}\) 且 \(\operatorname{lsb}=1\)；若 Free-XOR，取 \(\Delta_h\leftarrow\{0,1\}^{\lambda},\operatorname{lsb}(\Delta_h)=1\)，置 \(D(h)[i,1]=L_0\oplus\Delta_h\)。令 \(\tilde Y_j:=D(h)[i,c]\)（对全部 \(j\)），\(Y_t:=\tilde Y_h\)。
   - 每个 \(j\ne h\)：独立同法采样 \(D(j)[i,0],D(j)[i,1]\)。令 \(Y_j:=D(j)[i,b_j]\)。
4. **导出 solder 差值**（确定性）：
   \[
   \Delta^{(out)}_j[i,b]:=D(j)[i,b]\oplus D(h)[i,\delta_j\oplus b],\quad b=0,1 .
   \]
5. **输入侧**：对每条输入线独立采样 \(E(\cdot)[i',\cdot]\) 及 \(\tau^{(in)}_j\)，按 §1.1 公式导出 \(\Delta^{(in)}_j[i',b]\)（输入线与 z 无关，详见 §3.4）。
6. **输出**：\(\big(\{Y_j\},\{\delta_j\},\{\Delta^{(out)}_j[i,\cdot]\},\{\tilde Y_j\},Y_t,\{\tau^{(in)}_j\},\{\Delta^{(in)}_j[i',\cdot]\}\big)\)。

注意 \(\mathcal S\) 的输入参数中**没有 \(z\)，也没有 \(\tau_h\)**：它只用 \(c\) 作为 head 空间的活动选择位。

### 3.3 分布相等证明（逐量核对）

记真实执行中隐藏量为 \(\tau_h,\{\tau_j\},D(\cdot)[i,\cdot]\)。由 (A1)(A2)，\(\tau_h,\{\tau_j\}\) 均匀且互相独立，且与所有 label 描述独立。真实中：

\[
c=z\oplus\tau_h .
\]

因为 \(\tau_h\) 均匀且独立于 \(z\)，**无论 \(z=0\) 还是 \(z=1\)，\(c\) 都是均匀 bit**。逐量比对：

| 可见量 | 真实分布（用隐藏量表达） | \(\mathcal S\) 的分布 | 相等？ |
| --- | --- | --- | --- |
| \(c=\operatorname{lsb}(Y_t)\) | \(z\oplus\tau_h\)，\(\tau_h\) 均匀 ⇒ 均匀 | 均匀 | ✓ |
| \(\delta_j\) | \(\tau_j\oplus\tau_h\)，独立均匀 XOR ⇒ 均匀 | 均匀 | ✓ |
| \(b_j=\operatorname{lsb}(Y_j)\) | \(z\oplus\tau_j = c\oplus\delta_j\) | \(c\oplus\delta_j\)（步骤 2） | ✓ 恒等式对齐 |
| \(Y_j\) | \(D(j)[i,b_j]\)，\(D(j)\) 按 (A2)(A3) 采样 | 同（步骤 3） | ✓ |
| \(\Delta^{(out)}_j[i,\cdot]\) | \(D(j)[i,b]\oplus D(h)[i,\delta_j\oplus b]\) | 同（步骤 4） | ✓ |
| \(\tilde Y_j=Y_t\) | \(D(h)[i,c]\) | 同（步骤 3） | ✓ |
| majority \(Y_t\) | \(D(h)[i,c]\) | 同 | ✓ |

**关键的相关性核对**（这是审阅意见要求、hybrid 式无法自动保证的部分）：

- **恒等式 \(b_j\oplus\delta_j=c\)**：真实中 \((z\oplus\tau_j)\oplus(\tau_j\oplus\tau_h)=z\oplus\tau_h=c\)；\(\mathcal S\) 中 \(b_j:=c\oplus\delta_j\) 由构造满足。两者一致，且 \(\mathcal S\) 中 \(b_j\) 与 \(c,\delta_j\) 的联合依赖**完全复刻**真实中的依赖。✓
- **Adjust 一致性**：\(\tilde Y_j=\operatorname{Adjust}(Y_j,\Delta^{(out)}_j)=D(h)[i,\delta_j\oplus b_j]=D(h)[i,c]\) 在 \(\mathcal S\) 中由步骤 4 的确定性导出自动成立，无需引用 \(z\)。✓
- **head 两标签的联合**：\(\mathcal S\) 中 P2 可借 \(Y_j\oplus\Delta^{(out)}_j[i,b_j]=D(h)[i,c]\) 与 \(Y_j\oplus\Delta^{(out)}_j[i,b_j\oplus1]=D(h)[i,c\oplus1]\) 算出 head 两条标签——这与真实完全相同（EXP-03H §4.2 已识别「互补 label 暴露」，此处不是新信息，且**不依赖 z**）。✓
- **跨电路独立性**：(A2) 保证各 \(D(j)[i,\cdot]\) 独立，\(\mathcal S\) 逐步独立采样，联合分布一致。✓

因此 \(\mathcal S\) 的输出分布对每个 \(z\) 都等于 \(\mathcal V_{\mathrm{solder}}(z)\)，且 \(\mathcal S\) 与 \(z\) 无关。故

\[
\mathcal V_{\mathrm{solder}}(0)\equiv\mathcal V_{\mathrm{solder}}(1)\qquad\text{（在 (A1)(A2)(A3) 下，严格相等）}.
\]

**这正面回答了审阅意见第 2 点**：不需要在真实 transcript 上逐 hybrid 替换（那会破坏联合一致性），而是从隐藏量从头联合采样；H1→H2 的缺口在联合重采样框架下**自动消解**。

**这同时回应第 1 点**：代数式 \(b_j\oplus\delta_j=z\oplus\tau_h\) 只是本证明的一个环节（用于对齐 \(b_j\) 与 \(c,\delta_j\)）；完整的隐私结论来自**整个联合分布**的采样器等价性，而非单靠该等式。

### 3.4 输入侧差值 V3 与「两组 label XOR 差值」的独立性

输入侧 \(\tau^{(in)}_j=\tau(E(h))\oplus\tau(E(j))\) 与 \(\Delta^{(in)}_j\) 只涉及**输入线**（\(inst\_ctrl\)/查询/索引），其活动值由 P2 的 \(x_2=I\) 与模拟指令决定（见 EXP-03H §5 的 \(H_4\)），**与电路输出 \(z\) 无关**。因此输入侧量在 \(z=0,1\) 下分布相同，可原样列入 \(\mathcal S\) 的输出（步骤 5）。唯一需注意的交叉点：若 Free-XOR 下输入侧与输出侧共享电路级 \(\Delta\)，则 \(\Delta^{(in)}_j[i',0]\oplus\Delta^{(in)}_j[i',1]=\Delta_j\oplus\Delta_h=\Delta^{(out)}_j[i,0]\oplus\Delta^{(out)}_j[i,1]\)，两式一致、**不产生关于 \(z\) 的新信息**（见 §4.1）。

---

## 4. Free-XOR 实例化：条件成立与具体反例

审阅意见 V6 明确要求把 Free-XOR 相关性纳入视图。这是本命题的**分水岭**：结论完全取决于 \(\tau\) 与 \(\Delta\) 的关系。

### 4.1 情形 A：\(\tau\perp\Delta\) 且各电路独立 garble → L1 适用，引理成立

若 (A3) 成立（\(\tau\) 独立选取，非 \(\Delta\) 的函数；各电路 \(\Delta_j\) 独立），则 §3 的采样器直接适用，即使 Free-XOR 也**严格分布相等**。此时 P2 虽能从 V1+V3 算出 head 两条标签，进而得到 \(\Delta_h=D(h)[i,c]\oplus D(h)[i,c\oplus1]\)，但：

- \(\tau_h\perp\Delta_h\)（A3），故 \(\Delta_h\) 不含 \(\tau_h\) 信息；
- \(z=c\oplus\tau_h\)，P2 有 \(c\) 但无 \(\tau_h\)，仍不可恢复 \(z\)；
- check circuit 打开若泄露某个 \(\Delta_{check}\)，在「各电路独立 garble」(A2) 下也**不等于** \(\Delta_h\)，且 \(\tau_h\perp\Delta\) 使 \(\Delta_h\) 泄露本身无害。

**结论**：会议版 §2.2 声称 Free-XOR 满足 W 的全部性质，若按此解读（\(\tau\perp\Delta\)），则局部引理在论文的 Free-XOR 实例化下**成立**。

### 4.2 情形 B：\(\tau=\Delta[k]\) → **具体区分器，引理不成立**

考虑一种常见高效实例化：把 translation bit 定义为全局标签差的某固定位 \(\tau_i=\Delta[k]\)（对某个公开 \(k\)），以减少随 \(\tau\) 一同分发的元信息。此时：

1. P2 由 §3.3 已能从 V1+V3 算出 head 两条标签 \(D(h)[i,c],D(h)[i,c\oplus1]\)；
2. 异或得 \(\Delta_h=D(h)[i,c]\oplus D(h)[i,c\oplus1]\)；
3. 由 \(\tau_h=\Delta_h[k]\) 直接得到 head 结果线的 translation bit；
4. 由 \(c=\operatorname{lsb}(Y_t)\) 得

\[
z=c\oplus\tau_h=\operatorname{lsb}(Y_t)\oplus\Delta_h[k].
\]

**区分器 \(\mathcal D\)**：给定 \(\mathcal V_{\mathrm{solder}}(z_b)\)，按上式算 \(\hat z=\operatorname{lsb}(Y_t)\oplus\Delta_h[k]\)，输出 \(\hat z\)。则 \(\Pr[\mathcal D(\mathcal V_{\mathrm{solder}}(z_b))=z_b]=1\)，完美区分 \(z=0\) 与 \(z=1\)。

故在此实例化下

\[
\mathcal V_{\mathrm{solder}}(0)\not\equiv\mathcal V_{\mathrm{solder}}(1),
\]

**局部 batching 输出隐私论证被否定**。这不是抽象担心，而是从 V1–V6 可见量显式构造的区分器。

> 一致性说明：若 \(\tau=\Delta[k]\)，则互补标签 \(=\) 活动标签 \(\oplus\Delta\) 且 \(\tau\) 已知，违反 W 的「complementary labels unpredictable except lsb」。因此这种实例化**不符合论文声称的 W 性质**；但会议版 §2.2 未给出 \(\tau\) 与 \(\Delta\) 的显式约束，实现者可能误选此优化。这正是必须锁定的实例化条件。

### 4.3 情形 C：garbling 重用 → 另一条具体区分器

若 bucket 内电路**不是独立 garble**，而是把同一 garbling 复制多次（cut-and-choose 的错误实现），则 head 与某 check circuit 共享 \(\tau_h=\tau_{check}\)。check circuit 被完全打开（§3.2 step 2），其 \(\tau\) 公开，于是 P2 得 \(\tau_h\)，再由 \(z=c\oplus\tau_h\) 恢复 \(z\)。区分器同 §4.2 步 4。这违反 (A2)，同样否定该实例化。

### 4.4 判定树汇总

| 实例化 | \(\tau\) 与 \(\Delta\) 关系 | 独立 garble | 局部命题 |
| --- | --- | --- | --- |
| 非 Free-XOR | \(\tau\) 独立（独立标签） | 是 | **成立**（L1，严格相等） |
| Free-XOR（论文解读） | \(\tau\perp\Delta\) | 是 | **成立**（L1，严格相等） |
| Free-XOR（\(\tau=\Delta[k]\)） | \(\tau\) 绑定 Δ | 是 | **不成立**（§4.2 区分器） |
| 任意（garbling 重用） | 视情况 | 否 | **不成立**（§4.3 区分器） |

---

## 5. 多位、多电路、多轮扩展

- **多输出位 \(m\)**：若各位 \((\tau_h^{(i)},\Delta^{(i)})\) 独立且各位满足 (A3)，则 §3 采样器逐位独立调用，联合分布仍相等；若 Free-XOR 使用跨位共享的单一 \(\Delta\)，则 (A3) 的 \(\tau\perp\Delta\) 必须**逐位**成立，且 §4.2 的区分器对任意一位有效即整体失效。
- **多电路 \(j\in B_t\)**：§3 已对全部 \(j\) 联合采样；(A2) 的独立 garble 是跨电路 independence 的关键，违反即落入 §4.3。
- **多轮 \(E\)**：每轮独立调用本引理；轮间的 ORAM 状态传递属整体模拟定理（§7），不在本局部引理范围。

---

## 6. 判决与停止条件

### 6.1 对局部命题的判决

> **命题**：\(\mathcal V_{\mathrm{solder}}(0)\overset{?}{\equiv}\mathcal V_{\mathrm{solder}}(1)\)，视图含 V1–V6。

**判决：条件成立（附可检验的实例化前提与具体反例）。**

- **接受**：在 (A1)(A2)(A3)（结果线 \(\mu=0\)、各电路独立 garble、\(\tau\perp\Delta\)）下，§3 给出不依赖 \(z\) 的联合采样器并证明**严格分布相等**。按审阅意见停止条件第一条，**接受局部引理**。
- **否定边界**：在 \(\tau=\Delta[k]\) 或 garbling 重用下，§4.2/§4.3 给出从 V1–V6 构造的**具体区分器**，按停止条件第二条，**否定这两种实例化的 batching 输出隐私论证**。
- **未闭合**：会议版 §2.2 只声明「Free-XOR 分布 satisfies all properties of W」，未给 \(\tau\) 与 \(\Delta\) 的显式独立约束；full version Appendix D 本环境受限。因此「论文实际实例化属于情形 A 还是 B」无法从已核验证据判定——**这一项 HOLD**。

这是审阅意见所说「一个能经受密码学审稿的联合分布证明」的精确形态：不是无条件断言，也不是模糊的「尚未证明」，而是**成立的充分条件 + 不成立的具体反例 + 未决的实例化归属**。

### 6.2 相对 EXP-03H 的实质推进

| 维度 | EXP-03H | EXP-03I（本轮） |
| --- | --- | --- |
| 方法 | hybrid 逐项替换 \(H_1\to H_6\) | 从头联合重采样，联合一致性由构造保证 |
| H1→H2 缺口 | 存在（用户指出） | **消解**（不再逐项替换） |
| 代数式地位 | 当作隐私论证核心 | 仅为联合采样的一环，隐私来自分布等价 |
| Free-XOR | 列为 G1 待补 | **给出判定树 + 两个具体区分器** |
| 结论形态 | 模糊「肯定但有条件」 | 「充分条件成立 / 反例不成立 / 归属未决」三分 |

### 6.3 停止条件执行（按审阅意见）

- 本轮**不再找论文、不写实验代码、不改任何旧文件**；只用已核验引文与代数。✅
- 已给出不依赖 \(z\) 的联合采样器（§3）→ 接受局部引理（条件下）。✅
- 已给出具体区分器（§4.2/§4.3）→ 否定对应实例化。✅
- **两种结果都不自动决定 PA-VFANN 整体生死**：PA-VFANN 整体维持 EXP-03D 的 NO-GO 关闭状态；本轮既不「复活」整体，也不因局部区分器追加宣判。✅

---

## 7. 范围边界：局部引理与整体模拟定理的拆分（回应审阅意见第 3 点）

审阅意见第 3 点成立：H4（ORAM 逻辑访问序列）与 \(inst\_ctrl\) 的 \(\tau\) 开放**不是** Solder 结果线局部引理的组成部分。本文严格遵守该拆分：

- **局部引理（本文范围）**：给定其他协议输入与 transcript 条件，证明 Solder/MkBucket/Adjust 的**结果线**联合视图 \(\mathcal V_{\mathrm{solder}}\) 在 (A1)(A2)(A3) 下不依赖 \(z\)（§3）。
- **整体模拟定理（本文范围外）**：结果线模拟器与 ORAM 物理/逻辑访问序列、\(inst\_ctrl\)、承诺语义、check 集、结果相关中止的**组合**。具体包括 EXP-03H 的 \(H_4\)（ORAM 序列由 \(L_S,I\) 生成）、\(H_5\)（恶意 P2 位置绑定 membership）、\(H_6\)（中止独立性 / w-key 面）以及 EXP-03F 的索引初始化与回滚。**这些均不进入本文证明，也不得因本文局部引理成立而被误读为已闭合。**

因此，即便局部引理在情形 A 下成立，命题 3（完整 batching 单方输出协议）仍需单独完成上述外部构件；反之，情形 B 的局部区分器只否定「该 Free-XOR 实例化的 batching 输出隐私」，不等价于否定 Afshar RAM-2PC 本身。

---

## 8. 版本信息

| 项 | 内容 |
| --- | --- |
| 报告正文 commit | 见下方元信息提交（本提交之后的 HEAD 在最终汇报中给出） |
| 分支 | `exp03i-solder-joint-view`（基线 `d417cbe`） |
| 推送状态 | 提交后核验远端 HEAD 与本地一致 |
| 工作区状态 | 提交前确认除本报告外无改动；`git diff --check` 通过 |
