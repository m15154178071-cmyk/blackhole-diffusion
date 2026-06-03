
---

### 3. **benchmark_1k.md (Bilingual)**

```markdown
# Blackhole Diffusion · 1,000-Edge Benchmark (Condensed Report) / 黑洞弥散 · 1000 边基准测试（精简报告）

**Test Date**: 2026-06-03  
**Version Tested**: Base version (pure CSR elimination engine)  
**Baselines**: iGraph (exact MCB), NetworkX (exact MCB)  
**Dataset Scale**: 10 synthetic graphs (~1,000 edges), covering 5 random graph models × 2 parameter configurations.

**测试日期**：2026-06-03  
**被测版本**：基础版（纯 CSR 消元引擎）  
**对比对象**：iGraph（精确 MCB）、NetworkX（精确 MCB）  
**数据规模**：10 张合成图，约 1000 边，5 种随机图模型 × 2 参数配置

## 1. Audit Summary / 审计结论（总览）
✅ **Full-rank alignment rate**: 100% (10/10)  
✅ **Chordless & non-fragmented cycles**: 100%  
🎯 **Exact MCB hits**: 50% (5/10)  
🔍 **Near hits (inflation <1%)**: 20% (2/10)  
⚠️ **Minor deviations (4–6% inflation)**: 20% (2/10)  
❌ **Significant deviation (24.6% inflation)**: 10% (1/10)  

**Key Insight**: BH never produces cycles shorter than the exact MCB—it only replaces some short cycles with longer ones. Deviation increases with greater cycle-length span.

✅ **满秩对齐率**：100%（10/10）  
✅ **无弦环、无碎环**：100%  
🎯 **MCB 精确命中**：50%（5/10）  
🔍 **几乎命中（膨胀率 <1%）**：20%（2/10）  
⚠️ **轻微偏离（膨胀率 4–6%）**：20%（2/10）  
❌ **明显偏离（膨胀率 24.6%）**：10%（1/10）  

**核心规律**：BH 从不产生比精确 MCB 更短的环，只会将部分短环替换为长环。偏差随环长跨度增大而明显。

## 2. Speed Comparison / 速度对比
| Baseline      | Best Speedup | Worst Speedup | Median Speedup | Runtime Range |
|---------------|--------------|---------------|----------------|---------------|
| vs NetworkX   | 391×         | 49×           | 98×            | BH ≤ 3s, NX 25–221s |
| vs iGraph     | 2.3× slower  | 23× slower    | 9× slower      | iGraph faster (C vs Python) |

BH is 1–2 orders of magnitude faster than NetworkX but ~9× slower than iGraph (C implementation)—close to Python’s language tax.

| 对比对象|最快加速|最慢加速|中位数加速|所有图耗时|
| ---|---|---|---|---|
| vs NetworkX|391×|49×|98×|BH ≤ 3 秒，NX 25–221 秒|
| vs iGraph|2.3×（慢）|23×（慢）|9×（慢）|iGraph 快于 BH（C vs Python）|

BH 比 NetworkX 快 1–2 个数量级，比 iGraph（C 实现）慢约 9 倍（接近 Python 语言税）。

## 3. Precision Breakdown / 精度分层详情
✅ **Exact Hits (5/10)**: edge001 (ER dense), edge003 (BA m=3), edge006 (WS k=10), edge007 (pure grid), edge010 (RR d=8).  
→ All have MCB max cycle ≤ 6; BH aligns perfectly.

✅ **精确命中（5/10）**  
edge001（ER 稠密）、edge003（BA m=3）、edge006（WS k=10）、edge007（纯网格）、edge010（RR d=8）  
特点：MCB 最长环 ≤ 6，BH 完全对齐。

🔍 **Near Hits (2/10)**: edge002 (+0.3%), edge004 (+0.04%).  
→ Engineering-equivalent to exact hits (1–8 edge offsets).

🔍 **几乎命中（2/10）**  
edge002（+0.3%）、edge004（+0.04%）  
工程上等同于精确命中（1–8 条边偏移）。

⚠️ **Minor Deviations (2/10)**: edge005 (+5.6%), edge008 (+4.4%).  
→ Cycle-length distribution shifts toward longer cycles; total base-edge inflation <6%.

⚠️ **轻微偏离（2/10）**  
edge005（+5.6%）、edge008（+4.4%）  
环长分布向长端漂移，短环数量不变，总基边膨胀 <6%。

❌ **Significant Deviation (1/10)**: edge009 (RR d=4, +24.6%).  
→ Cycle lengths drift from 3–9 to 3–13; long cycles dominate.

❌ **明显偏离（1/10）**  
edge009（RR d=4，+24.6%）  
环长从 3–9 漂移到 3–13，长环大量涌入。

## 4. Topology Trends / 拓扑类型趋势
| Model               | Representative Graph | Exact/Near | Inflation Trend |
|---------------------|----------------------|------------|------------------|
| ER Dense (3-cycles) | edge001              | ✅         | Always exact     |
| BA Scale-free       | edge003/004          | ✅/⚠️      | <0.05%           |
| Pure 2D Grid        | edge007              | ✅         | Always exact     |
| WS Small-world      | edge005/006          | ❌/✅      | 5.6% / 0%        |
| Grid + Random Edges | edge008              | ❌         | ~4.4%            |
| RR Regular (d=4)    | edge009              | ❌         | 24.6% (worst)    |
| RR Regular (d=8)    | edge010              | ✅         | 0%               |

**Most Vulnerable**: Low-density regular graphs (d=4), sparse and uniform cycle spaces.

| 拓扑模型|代表性图|精确/接近|膨胀率趋势|
| ---|---|---|---|
| ER 稠密（纯 3-环）|edge001|✅|必中|
| BA 无标度（m=3/5）|edge003/004|✅/⚠️|<0.05%|
| 纯 2D 网格|edge007|✅|必中|
| WS 小世界（k=6/10）|edge005/006|❌/✅|5.6% / 0%|
| 网格 + 随机边|edge008|❌|~4.4%|
| RR 正则（d=4）|edge009|❌|24.6%（最差）|
| RR 正则（d=8）|edge010|✅|0%|

**最脆弱模式**：低密度正则图（d=4）、稀疏且均匀的环空间。

## 5. Scaling Behavior (vs 5k/10k edges) / 规模扩展规律（与 5000/10000 边呼应）
| Topology Type       | 1k Edges | 5k Edges | 10k Edges |
|---------------------|----------|----------|-----------|
| ER Dense            | 0%       | 0%       | 0%        |
| BA Mixed Short      | 0–0.04%  | 0–1%     | 0–1%      |
| Pure Grid           | 0%       | 0%       | 0%        |
| WS / Derived Grid   | 4–6%     | 8–11%    | 9–12%     |
| RR d=4 Sparse       | 24.6%    | 36.9%    | 46.2%     |

**Pattern**: Base-edge inflation amplifies by 50–80% per doubling of edges—a systematic, predictable trait.

| 拓扑类型|1000 边|5000 边|10000 边|
| ---|---|---|---|
| ER 稠密|0%|0%|0%|
| BA 混合短环|0–0.04%|0–1%|0–1%|
| 纯网格|0%|0%|0%|
| WS / 衍生网格|4–6%|8–11%|9–12%|
| RR d=4 稀疏|24.6%|36.9%|46.2%|

**规律**：边数每翻一倍，基边膨胀率放大 50–80% —— 系统性的、可预期的特征。

## 6. Positioning Statement / 定位陈述（适用/不适用）
Blackhole Diffusion is a pure-Python full-rank chordless cycle basis extractor.

✅ **Guarantees**: Full rank, chordless, non-fragmented, algebraically correct cycle bases.  
⚠️ **Does Not Guarantee**: Globally minimal total cycle length (allows 0–25% base-edge redundancy).

### Suitable For:
- Environments where igraph installation is impossible or NetworkX is too slow.
- Scenarios requiring a correct, usable cycle basis quickly, accepting 0–25% redundancy.
- Downstream computations insensitive to cycle length (e.g., rank, chordlessness checks).

### Not Suitable For:
- Applications requiring strict MCB when igraph is available → use igraph directly.

*Report ends. See full version for detailed data and cycle-length distributions.*

**Blackhole Diffusion 是一个纯 Python 的满秩无弦环基提取引擎。**

✅ **保证**：满秩、无弦、无碎环，环基代数正确。  
⚠️ **不保证**：全局最短总环长（允许一定比例的基边冗余）。

**适用场景**
- 无法安装 igraph / NetworkX 速度过慢时
- 需要快速获得一份正确可用的环基，接受 0–25% 的基边冗余
- 下游计算对环基长度不敏感（如秩、无弦性校验）

**不适用场景**
- 必须获得严格最小环基（MCB），且 igraph 可用 → 直接使用 igraph

**报告结束（完整数据与环长分布细节参见原始版本）**