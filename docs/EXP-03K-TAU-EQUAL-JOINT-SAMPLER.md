# EXP-03K：τ=Δ[k] 且 Δ 隐藏时的联合采样器修正与跨位核验

> 项目：PA-VFANN-23（承接 PA-VFANN-22 / EXP-03J 的独立审阅意见）
> 目标：**唯一目标**——修正并核验 (T=) \(\tau_c[w]=\Delta_c[k]\)、\(\Delta\) 隐藏时，E（eval 共享、check 独立）与 P（逐电路独立）两种分配的联合采样器。不扩证明目标、不搜文献、不改实验代码/数据/旧报告。
> 方法：显式随机变量 + 形式化双射；附一次小域归一化穷举作为内部验算（\(\lambda=3,k=1\)，验算脚本不入仓库、不写入项目）。
> 停止条件（沿用审阅意见）：能构造同分布且不依赖 \(z\) 的采样器 ⇒ 接受该实例化；找到区分器 ⇒ 否定该实例化。两种结果都不自动决定整体协议。

---

## 0. 交付与证据状态

| 项 | 内容 |
| --- | --- |
| 基线 commit | `525b576bb8e8338af0718151a06149cc8f74469c`（EXP-03J 最终 HEAD） |
| 分支 | `exp03k-tau-equal-joint-sampler` |
| 新增文件 | `docs/EXP-03K-TAU-EQUAL-JOINT-SAMPLER.md`（本文，唯一新增） |
| 一手来源 | 沿用 EXP-03H/03I/03J 已核验会议版 §2.2、§3.1–3.3（DOI `10.1007/978-3-662-46800-5_27`）；本轮不新增引用 |
| 证据限制 | 会议版未显式给出 τ 与 Δ 的关系、check/eval 的 Δ 分配；full version Appendix D 本环境受限。故本轮只对审阅意见指定的 (T=)+Δ隐藏 情形作条件判定，不臆断论文实际实例化。 |

**一句话结论**：审阅者的阻断项**成立**——EXP-03J §4.1 的独立 \(\delta_j\) 采样在 (T=) 下不是同分布，必须修正。修正后得到两个结果：

1. **接受（单结果位）**：(T=)、Δ隐藏下，E 与 P 都存在严格同分布、输入不含 \(z\) 的采样器（§2），其中 \(\delta_j\) 必须由 \((\Delta_j\oplus\Delta_h)[k]\) 派生（E 恒为 0），不能独立采样。
2. **否定（多结果位）**：(T=) 使**所有 wire 共享同一** \(\tau_c[w]=\Delta_c[k]\)，故同一电路两条结果线的活动选择位之差恒等于 \(z_i\oplus z_{i'}\)，给出**明确区分器** \(D_{\rm cross}\)（§3）。因此 EXP-03J §7.1「所有合法实例化下引理成立」必须限定为**单结果位**（多结果位仅 (T⊥) 成立）。

两项均不改变项目级状态：核心研究问题继续 **HOLD**。

---

## 1. 阻断项确认

审阅者指出：EXP-03J §2.2 定义 (T=) 为 \(\tau_c[w]=\Delta_c[k]\)，于是必有

\[
\delta_j=\tau_j\oplus\tau_h=(\Delta_j\oplus\Delta_h)[k].
\]

但 §4.1 步骤 3 写的是 \(\delta_j\leftarrow\{0,1\}\) 独立均匀，再独立采样 \(\Delta_c\)。这破坏联合分布，具体为：

- **E（eval 共享 \(\Delta_{\rm eval}\)）**：head 与所有 eval 电路 \(j\) 满足 \(\Delta_j=\Delta_h\)，故真实 \(\delta_j=0\) **恒成立**；§4.1 却以 \(1/2\) 概率给 1。
- **P（逐电路独立 \(\Delta_c\)）**：真实 \(\delta_j=(\Delta_j\oplus\Delta_h)[k]\)，与 \(\Delta_j\oplus\Delta_h\) 完全相关；§4.1 却令二者独立。

进一步，EXP-03J §4.2 表中「\((c,\delta_j)\) 联合独立均匀」也只在 (T⊥) 成立：(T=) 下 \(c=z\oplus\Delta_h[k]\)、\(\delta_j=(\Delta_j\oplus\Delta_h)[k]\) 经 \(\Delta_h[k]\) 相关。§5.3「把 \(\tau_c[w]=\Delta_c[k]\) 作为隐藏量的确定性函数，§4 采样器仍适用」的断言因此失效——只是把 \(\delta_j\) 改名，采样关系并未改。

**结论：阻断项成立，EXP-03J 的 (T=) 局部结论必须按本轮修正。** 这不是措辞问题，而是联合分布层面的可区分差异（§2.5 验算给出旧采样器支持集为真实的两倍）。

---

## 2. 修正后的采样器（单结果位 \(i\)，\(\Delta\) 隐藏）

### 2.1 随机变量与视图

固定 head \(h\) 与一个 eval 电路 \(j\neq h\)，固定一个结果位 \(i\)、一个输入线 \(i'\)。\(\lambda\) 位字符串，\(k\neq\mathrm{lsb}\) 为公开固定位，\(e_k\) 为第 \(k\) 位为 1 的单位串。

隐藏量：\(\Delta_h,\Delta_j\)（\(\operatorname{lsb}=1\)，按 E/P 分配），\(L_h,L_j,K_h,K_j\)（\(\operatorname{lsb}=0\)，独立均匀）。公开量：check 电路的 \(\Delta^{\rm chk}\)（被完全打开），以及实例化描述（分配结构、\(k\)）。\(\Delta_h\) 在 E/P 下均隐藏。

(T=) 下对所有 wire \(w\) 有 \(\tau_c[w]=\Delta_c[k]\)，因此结果线与输入线的 translation bit 差相同：

\[
\delta_j=\tau_j[i]\oplus\tau_h[i]=(\Delta_j\oplus\Delta_h)[k]
=\alpha_j=\tau_j[i']\oplus\tau_h[i'].
\]

真实执行（输入 \(z\in\{0,1\}\)）：

\[
c=z\oplus\Delta_h[k],\quad b_j=c\oplus\delta_j=z\oplus\Delta_j[k],
\]
\[
Y_h=L_h\oplus c\,\Delta_h,\qquad Y_j=L_j\oplus b_j\,\Delta_j,
\]
\[
D_j^{(out)}[i,0]=L_j\oplus L_h\oplus\delta_j\Delta_h,\quad
D_j^{(out)}[i,1]=D_j^{(out)}[i,0]\oplus(\Delta_j\oplus\Delta_h),
\]
\[
D_j^{(in)}[i',0]=K_j\oplus K_h\oplus\alpha_j\Delta_h,\quad
D_j^{(in)}[i',1]=D_j^{(in)}[i',0]\oplus(\Delta_j\oplus\Delta_h).
\]

P2 视图（结果线 \(\mu=0\)，\(\tau\) 不开放）：

\[
\mathcal V_{\rm solder}=(c,\ \delta_j,\ Y_h,\ Y_j,\ D_j^{(out)}[i,\cdot],\ D_j^{(in)}[i',\cdot],\ [\Delta^{\rm chk}]).
\]

### 2.2 采样器 \(S_E^{=}\)（E：eval 共享、check 独立）

1. 采 \(\Delta_{\rm eval}\leftarrow\{0,1\}^\lambda,\operatorname{lsb}=1\)（隐藏）；采各 \(\Delta_c^{\rm chk}\)（公开，独立）。
2. **采 \(c\leftarrow\{0,1\}\) 均匀，与所有 \(\Delta\) 独立。**
3. **置 \(\delta_j:=0\)、\(\alpha_j:=0\)、\(b_j:=c\)**（不得独立采样 \(\delta_j\)）。
4. 采 \(L_h,L_j,K_h,K_j\leftarrow\{\operatorname{lsb}=0\}\) 独立均匀。
5. 置 \(\Delta_j=\Delta_h=\Delta_{\rm eval}\)，按 §2.1 公式计算 \(Y_h,Y_j,D^{(out)},D^{(in)}\) 并输出。

### 2.3 采样器 \(S_P^{=}\)（P：逐电路独立 \(\Delta_c\)）

1. 采 \(\Delta_h,\Delta_j\leftarrow\{\operatorname{lsb}=1\}\) **独立**（\(\Delta_h\) 隐藏）；采各 \(\Delta_c^{\rm chk}\)（公开）。
2. **采 \(c\leftarrow\{0,1\}\) 均匀，与所有 \(\Delta\) 独立。**
3. **派生 \(\delta_j:=(\Delta_j\oplus\Delta_h)[k]\)，并置 \(\alpha_j:=\delta_j\)、\(b_j:=c\oplus\delta_j\)**（不得独立采样 \(\delta_j\) 或 \(\alpha_j\)）。
4. 采 \(L_h,L_j,K_h,K_j\leftarrow\{\operatorname{lsb}=0\}\) 独立均匀。
5. 按 §2.1 公式计算全部可见量并输出。

### 2.4 同分布证明（形式化双射，输入不含 \(z\)）

先看真实执行为何与 \(z\) 无关。给定任一 \(z\)，构造隐藏量上的双射，把 \(z=1\) 的执行映到 \(z=0\) 的执行且**视图逐项不变**：

- **P**：\((\Delta_h,\Delta_j,L_h,L_j,K_h,K_j)\mapsto(\Delta_h\oplus e_k,\ \Delta_j\oplus e_k,\ L_h\oplus c\,e_k,\ L_j\oplus b_j e_k,\ K_h,\ K_j\oplus\delta_j e_k)\)。
  - \(c^{0}=\Delta_h[k]\oplus1=(1\oplus\Delta_h[k])=c^{1}\)；\(\delta^0=(\Delta_j\oplus\Delta_h)[k]=\delta^1\)；\(b_j^{0}=c\oplus\delta_j=b_j^{1}\)；
  - \(L_h^{0}\oplus c\Delta_h^{0}=L_h\oplus c e_k\oplus c\Delta_h\oplus c e_k=L_h\oplus c\Delta_h=Y_h^{1}\)，同理 \(Y_j^{0}=Y_j^{1}\)；
  - \(D^{(out),0}[i,0]=D^{(out),1}[i,0]\oplus(b_j\oplus c\oplus\delta_j)e_k=D^{(out),1}[i,0]\)（因 \(b_j=c\oplus\delta_j\)）；\(D^{(out)}[i,1]\) 随 \(\Delta_j\oplus\Delta_h\) 不变而相同；
  - \(D^{(in),0}[i',0]=K_j\oplus\delta_j e_k\oplus K_h\oplus\delta_j(\Delta_h\oplus e_k)=D^{(in),1}[i',0]\)；\(D^{(in)}[i',1]\) 同理相同。
  - 因 \(k\neq\mathrm{lsb}\)，所有翻转保持 \(\operatorname{lsb}\) 约束；变换是双射且保持独立均匀乘积分布。
- **E**：\(\Delta_{\rm eval}\mapsto\Delta_{\rm eval}\oplus e_k\)，\(L_h\mapsto L_h\oplus c\,e_k\)，\(L_j\mapsto L_j\oplus c\,e_k\)，\(K\) 不变。因 \(\delta_j=\alpha_j=0\)、\(\Delta_j\oplus\Delta_h=0\)，逐项验算同样得到视图不变。

故对每个 \(z\)，真实视图分布等于 \(z=0\) 的视图分布。再看采样器：在 \(z=0\) 的真实执行中 \(c=\Delta_h[k]\)，由 \(\operatorname{lsb}=1,k\neq\mathrm{lsb}\) 知 \(\Delta_h[k]\) 独立均匀且与其余隐藏量独立；\(\delta_j\) 是 \((\Delta_j\oplus\Delta_h)[k]\) 的确定性函数。采样器正是按同一联合律生成 \((c,\delta_j,\Delta,L,K)\) 再用同一确定性公式导出视图，因此

\[
S_E^{=}\equiv\mathcal V_{\rm solder}(0),\qquad S_P^{=}\equiv\mathcal V_{\rm solder}(0)
\quad\Longrightarrow\quad
\mathcal V_{\rm solder}(0)\equiv\mathcal V_{\rm solder}(1).
\]

两采样器的采样步骤均不含 \(z\)（仅含实例化描述、\(\lambda,k\)）。**按停止条件第一条，接受 (T=)+Δ隐藏、单结果位下的 E/P 局部引理。**

### 2.5 内部验算（非交付物）

在 \(\lambda=3,k=1\)、\(j,h\) 各一电路、单结果位与单输入线上穷举所有隐藏量并归一化：

| 检查 | E | P |
| --- | --- | --- |
| 真实 \(\mathcal V(0)\) 与 \(\mathcal V(1)\) 归一化分布相等 | 是 | 是 |
| 本轮修正采样器与真实分布相等 | 是 | 是 |
| EXP-03J 旧采样器（独立 \(\delta\)）与真实分布相等 | **否**（支持集 256 vs 128） | **否**（1024 vs 512） |

验算仅用于确认代数推导，未写入仓库、未改任何实验文件。

---

## 3. 跨结果位 / 跨 wire 核验：新区分器 \(D_{\rm cross}\)

审阅意见要求检查跨结果位、跨输入输出 wire 的相关性。这里发现**EXP-03J 未覆盖的额外泄露**，它限制 §2 结论的适用范围。

### 3.1 (T=) 下 τ 跨所有 wire 共享 → 完美区分器

(T=) 的定义是 \(\tau_c[w]=\Delta_c[k]\) **对每个 wire \(w\)**，不是每结果位独立采样。于是对同一电路 \(c\) 的任意两条结果线 \(i,i'\)：

\[
\operatorname{lsb}(Y_c[i])=b_c[i]=z_i\oplus\Delta_c[k],\qquad
\operatorname{lsb}(Y_c[i'])=b_c[i']=z_{i'}\oplus\Delta_c[k],
\]
\[
\Rightarrow\quad \operatorname{lsb}(Y_c[i])\oplus\operatorname{lsb}(Y_c[i'])=z_i\oplus z_{i'},
\]

**\(\Delta_c[k]\) 被消掉**。P2 可见全部活动标签，故可直接计算该 XOR。

区分器 \(D_{\rm cross}\)：给定两个候选输出 \(z,z'\)，对所有 \(c,i,i'\) 检查 \(\operatorname{lsb}(Y_c[i])\oplus\operatorname{lsb}(Y_c[i'])\) 是否等于 \(z_i\oplus z_{i'}\)。取 \(z'=z\oplus e_1\)（单比特不同），两候选给出的断言对每个 \((i,i')\) 都相反，**每次都以概率 1 区分**。小域验算显示：\(z=(0,0)\) 时 \((c_1,c_2)\in\{(0,0),(1,1)\}\)，\(z=(0,1)\) 时 \((c_1,c_2)\in\{(0,1),(1,0)\}\)，支持集不相交。

因此：

- §2 的接受结论**只适用于单结果位**（EXP-03I/03J §2.3 确实「固定一个结果位 \(i\)」）；
- **多结果位下 (T=) 不成立**：EXP-03J §7.1「所有合法实例化下引理成立」必须改写为「单结果位下所有合法实例化成立；多结果位下仅 (T⊥) 成立」；
- 该泄露不依赖 \(\Delta\) 是否公开，也不依赖 check/eval 分配，故 E/P 均命中。

### 3.2 输入侧与 (T⊥) 的采样器完整性

- **(T=) 输入侧**：\(\alpha_j=\delta_j\) 对结果线与输入线相同（同一 \(\Delta_c[k]\)）。§2.2/§2.3 已强制用同一 \(\delta_j\)；若像 EXP-03J §4.1 那样只采一个 \(\delta_j\) 却对输入线另取独立 \(\alpha_j\)，同样可区分。
- **(T⊥) 多结果位**：\(\tau_c[w]\) 逐 wire 独立均匀，故 \(c_i=z_i\oplus\tau_h[i]\) 跨位独立，无 \(D_{\rm cross}\)。但 EXP-03J §4.1 只采 \(\delta_j\)、未定义输入线 \(\alpha_j\)（§6 仅写「输入侧同构」）；完整同分布采样器必须**对每条输入线独立采 \(\alpha_j[i']\leftarrow\{0,1\}\)**。这是一处采样器不完整（非协议缺陷），补上后 (T⊥) 的 G/E/P 结论维持。

---

## 4. 判决与对 EXP-03J 的精确修正

| 命题 | 本轮判定 |
| --- | --- |
| EXP-03J §4.1 独立采样 \(\delta_j\) 在 (T=) 下同分布 | **否定**（§1、§2.5） |
| (T=)+Δ隐藏、E、**单结果位**：修正采样器 \(S_E^{=}\) | **接受**（严格同分布，不含 \(z\)） |
| (T=)+Δ隐藏、P、**单结果位**：修正采样器 \(S_P^{=}\) | **接受**（严格同分布，不含 \(z\)） |
| (T=)+Δ隐藏、**多结果位** | **否定**：区分器 \(D_{\rm cross}\)（§3.1） |
| (T⊥) G/E/P 多结果位 | 条件接受：须补 \(\alpha_j[i']\) 独立采样（§3.2） |
| (T=)+Δ公开 | 维持 EXP-03J §5.2 排除（\(D_3\) 直接恢复 \(z\)） |
| 整体 batching 单方输出协议 / 命题 3 | **HOLD**：ORAM 轨迹、`inst_ctrl`、索引初始化与回滚、位置绑定 membership、结果相关中止仍在外 |
| PA-VFANN 核心研究问题 | **HOLD**（具体贡献 NO-GO ≠ 整体 NO-GO） |

### 4.1 需要修正的 EXP-03J 具体条目（本轮不改旧报告，仅登记）

1. §4.1 步骤 3：\(\delta_j\) 改为由 \(\Delta\) 派生（E 置 0；P 置 \((\Delta_j\oplus\Delta_h)[k]\)），并显式给出 \(\alpha_j\)。
2. §4.2 表「\((c,\delta_j)\) 联合独立均匀」：仅 (T⊥) 成立；(T=) 下二者经 \(\Delta_h[k]\) 相关，但 §2.4 的双射仍给出同分布。
3. §5.3：「§4 采样器仍适用于 (T=)+Δ隐藏」需限定为**单结果位**。
4. §6：「τ 逐位独立」仅 (T⊥) 成立；(T=) 下 τ 逐位**相同**且跨 wire 共享，产生 \(D_{\rm cross}\)。
5. §7.1：「所有合法实例化下引理成立」改为分情形结论（单结果位成立 / 多结果位仅 T⊥ 成立）。

### 4.2 项目级表述

沿用 EXP-03J §7.2 口径：已 NO-GO 的只是具体贡献与包装；核心研究问题（严格策略隐私 + 服务端持索引 + 客户端秘密谓词 + 单方输出过滤 ANN）未被证明不可能，继续 HOLD。本轮局部引理的修正与限定**不写整体 GO，也不写整体 NO-GO**。

### 4.3 停止规则

本轮未扩范围：未新增文献、未写代码、未改旧报告/数据（相对基线仅 1 个新增文件）。实例化层面的联合分布检查到此闭合；不再追加新的实例化枚举。若后续进入原型，(T=) 必须限定单结果位或改用逐 wire 独立 \(\tau\)，并把「Δ 分配 + τ 分布 + 结果位宽度」写成显式实现约束。

---

## 5. 版本信息

| 项 | 内容 |
| --- | --- |
| 分支 | `exp03k-tau-equal-joint-sampler`（基线 `525b576`） |
| 新增文件 | `docs/EXP-03K-TAU-EQUAL-JOINT-SAMPLER.md`（本文，唯一新增） |
| 推送状态 | 提交后核验远端 HEAD 与本地一致 |
| 工作区状态 | 提交前确认除本报告外无改动；`git diff --check` 通过 |
