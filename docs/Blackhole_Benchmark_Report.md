# Blackhole Diffusion · Benchmark Report / 黑洞弥散 · 基准测试报告

**Test Date**: 2026-06-03  
**Version Tested**: Base version (CSRBlackholeDevourer, pure CSR elimination engine)  
**Baseline**: iGraph C implementation (MCB)  
**Datasets**: 20 synthetic graphs (5,000–10,000 edges), covering full-spectrum topologies.

**测试日期**：2026-06-03  
**被测版本**：基础版（CSRBlackholeDevourer，纯 CSR 消元引擎）  
**对比基线**：iGraph C 实现（MCB 最小环基）  
**数据集**：20 个合成基准图（5000–10000 边），覆盖全谱系拓扑类型

## Audit Conclusion / 审计结论
✅ **20/20 datasets passed full-rank audits**  
├── Rank alignment: 100% (20/20)  
├── Pure cycles: 100% (0 chorded, 0 fragmented)  
└── Correctness: All outputs are mathematically valid full-rank chordless cycle bases.

✅ **20/20 数据集满秩审计通过**  
├── Rank 对齐率: 100% (20/20)  
├── 纯环率: 100% (0 弦环, 0 碎环)  
└── 正确性: 所有输出均为数学上合法的满秩无弦环基

## 1. 5,000-Edge Scale (edge001–edge010) / 5000 边级别（edge001–edge010）
| Dataset | V/E/R | Topology | iGraph | BH | Ratio | Base-Edge Inflation |
|---------|-------|----------|--------|----|-------|---------------------|
| edge001 | 141/5072/4932 | Pure dense 3-cycles | 0.44s | 3.35s | 7.6× | 0% |
| ... | ... | ... | ... | ... | ... | ... |
| edge007 | 2500/4900/2401 | Pure 4-cycle grid | 8.70s | 5.56s | 0.64× 🔥 | 0% |

| 数据集|V / E / R|拓扑特征|iGraph|BH 基础版|Ratio|基边膨胀|
| ---|---|---|---|---|---|---|
| edge001|141/5072/4932|纯 3-环稠密|0.44s|3.35s|7.6×|0%|
| ...|...|...|...|...|...|...|
| edge007|2500/4900/2401|纯 4-环网格|8.70s|5.56s|0.64× 🔥|0%|

## 2. 10,000-Edge Scale (edge011–edge020) / 10000 边级别（edge011–edge020）
| Dataset | V/E/R | Topology | iGraph | BH | Ratio | Base-Edge Inflation |
|---------|-------|----------|--------|----|-------|---------------------|
| edge011 | 200/10053/9854 | Pure dense 3-cycles | 1.33s | 8.44s | 6.3× | 0% |
| ... | ... | ... | ... | ... | ... | ... |
| edge017 | 4900/9660/4761 | Pure 4-cycle grid | 52.82s | 23.38s | 0.44× 🔥 | 0% |

| 数据集|V / E / R|拓扑特征|iGraph|BH 基础版|Ratio|基边膨胀|
| ---|---|---|---|---|---|---|
| edge011|200/10053/9854|纯 3-环稠密|1.33s|8.44s|6.3×|0%|
| ...|...|...|...|...|...|...|
| edge017|4900/9660/4761|纯 4-环网格|52.82s|23.38s|0.44× 🔥|0%|

## 3. Exact Base-Edge Alignment / 基边精确对齐率
7/20 (35%) datasets matched iGraph’s MCB exactly:
- edge001, edge002, edge004, edge007 (5k)
- edge011, edge012, edge017 (10k)

Additionally, edge014 (+0.01%) and edge013 (+1.0%) were near-exact.

**基总边数与 iGraph 完全一致的图（即 MCB 精确命中）**：  
| 数据集|规模|拓扑|基边 (iGraph)|基边 (BH)|
| ---|---|---|---|---|
| edge001|5k|纯 3-环|14796|14796|
| edge002|5k|3-环为主|14326|14326|
| edge004|5k|3–5 环|15477|15477|
| edge007|5k|纯 4-环网格|9604|9604|
| edge011|10k|纯 3-环|29562|29562|
| edge012|10k|3-环为主|29557|29557|
| edge017|10k|纯 4-环网格|19044|19044|

7/20（35%）精确命中 MCB。 另有 edge014（基边差 3，0.01%）和 edge013（基边差 308，1.0%）接近命中。

## 4. Cycle-Length Drift / 环长漂移特征
- **MCB ≤ 4 graphs** (e.g., edge001/002/007/011/012/017): Exact alignment.
- **MCB ≥ 5 graphs**: Drift increases with MCB endpoint and topology complexity. Grid-derived graphs (edge008/018) show pronounced drift.

| 数据集|iGraph MCB 终点|BH 终点|漂移幅度|基边膨胀|
| ---|---|---|---|---|
| edge001|3|3|—|0%|
| edge002|4|4|—|0%|
| edge003|7|8|+1|1.0%|
| ...|...|...|...|...|
| edge020|7|11|+4|30.2%|

**规律**：MCB ≤ 4 的图（edge001/002/007/011/012/017）→ 精确命中。MCB ≥ 5 的图 → 环长漂移随 MCB 终点和拓扑复杂度递增。网格衍生图（edge008/018）漂移尤为明显。

## 5. Runtime Characteristics / 时间特征
### 5,000 Edges / 5000 边
- **Fast (<10s)**: Pure short-cycle or grid graphs (edge001/002/007).
- **Medium (10–50s)**: Mixed short-cycle graphs.
- **Slow (>50s)**: Long-cycle mixed graphs (edge009: 66s).

### 10,000 Edges / 10000 边
- **Fast (<30s)**: Pure short-cycle or grid graphs (edge011/012/017).
- **Medium (30–150s)**: Mixed medium-short graphs.
- **Slow (>150s)**: Sparse + long-cycle mixes (edge013/014/019).

### iGraph Outperformance Cases / 反超 iGraph 场景
| Dataset | Scale | iGraph | BH | Speedup |
|---------|-------|--------|----|---------|
| edge007 | 5k (4-cycle grid) | 8.70s | 5.56s | 1.57× |
| edge017 | 10k (4-cycle grid) | 52.82s | 23.38s | 2.26× |

**5000 边**  
| 档位|BH 耗时|数据集|典型场景|
| ---|---|---|---|
| 快 ( <10s)|3–9s|edge001/002/007|纯短环图、纯网格|
| 中 (10–50s)|35–44s|edge003/004/005/006/008/010|混合短环图|
| 慢 (50+s)|66s|edge009|长环混合图|

**10000 边**  
| 档位|BH 耗时|数据集|典型场景|
| ---|---|---|---|
| 快 ( <30s)|8–26s|edge011/012/017|纯短环图、纯网格|
| 中 (30–150s)|93–145s|edge015/016/018/020|混合中短环图|
| 慢 (150+s)|182–291s|edge013/014/019|中等稀疏 + 长环混合|

**反超 iGraph 场景**  
| 数据集|规模|iGraph|BH|反超倍数|
| ---|---|---|---|---|
| edge007|5k (纯 4-环网格)|8.70s|5.56s|1.57×|
| edge017|10k (纯 4-环网格)|52.82s|23.38s|2.26×|

纯 Python 在网格图上反超 C 实现，且规模越大差距越显著——从 1.6× 扩大到 2.3×。

## 6. Key Highlights / 硬核亮点
- **100% Full-Rank Correctness**: 20/20 datasets—exact rank alignment, zero chorded/fragmented cycles.
- **Grid Outperformance**: Pure Python beats igraph’s C on grids (e.g., 0.44× runtime on edge017).
- **Short-Cycle Precision**: Exact base-edge alignment with igraph on pure 3/4-cycle graphs.
- **Zero Dependencies**: All tests run on pure Python—no C compilation, no third-party packages.

- **满秩正确性 100%**：20/20 数据集 Rank 完全对齐，0 弦环，0 碎环——不是“接近”，是“精确”。
- **纯网格反超 iGraph**：edge017 上纯 Python 跑出 C 实现的 0.44× 时间，且规模越大优势越显著。
- **短环稠密图精确命中**：纯 3-环和纯 4-环图上基总边数与 iGraph 逐边对齐。
- **零依赖**：所有测试在同一份纯 Python 代码上完成，无 C 编译，无第三方包。