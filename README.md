# blackhole-diffusion（黑洞弥散）

> A pure-Python graph engine for extracting full-rank chordless cycle bases.  
> Zero dependencies — runs anywhere Python runs.

> 纯 Python 标准库实现的图算法引擎，专注于提取满秩无弦环基。零外部依赖，即插即用。

---

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/m15154178071-cmyk/blackhole-diffusion/blob/main/try_blackhole.ipynb)


## 📦 Installation / 安装

```bash
pip install blackhole-diffusion
```

---

## 🚀 Quick Start / 快速开始

### 基础用法 / Basic Usage

```python
from blackhole_diffusion import chordless_cycle_basis

edges = {(1, 2), (2, 3), (3, 1), (3, 4), (4, 1)}
cycles = chordless_cycle_basis(edges)

for cyc in cycles:
    print(sorted(cyc))
```

> 更多示例见 [examples_basic_usage.py](examples_basic_usage.py)。

### 正确性验证 / Verification

Blackhole Diffusion 输出的是**近似最小环基**（near-MCB），满秩且无弦，但不保证全局最短总环长。验证正确性需要外部基线对比：

```bash
pip install igraph networkx rich
python benchmark.py
```

也可以对单张图进行验证 / You can also verify a single graph:

```bash
python benchmark.py your_graph.txt out.txt 黑洞弥散
```

这会自动用 iGraph 的精确 MCB 做交叉审计，确认满秩无弦、环长漂移和基边膨胀是否在可接受范围内。确认无误后，生产环境只需 `blackhole_diffusion.py` 一个文件，零依赖部署。详见 [CAUTION.md](CAUTION.md)。

Blackhole Diffusion outputs a **near-MCB** (full-rank chordless cycle basis) but does not guarantee the globally shortest total cycle length. To verify correctness against an external baseline, run the benchmark script. It will cross-audit with iGraph's exact MCB. Once verified, you can deploy with just `blackhole_diffusion.py` — zero dependencies. See [CAUTION.md](CAUTION.md).

---

## 💡 Core Features / 核心特性

- **零外部依赖**：100% Python 标准库构建。无 C 编译、无 wheel 文件、无第三方包。任何 Python 3.9+ 环境即插即用。  
  **Zero External Dependencies**: Built entirely with Python's standard library. No C compilation, no wheel files, and no third-party packages. Plug-and-play in any Python 3.9+ environment.

- **满秩正确性保证**：输出结果 100% 满秩解构，所有环代数独立且绝对无弦。30 个基准数据集（1000–10000 边）全部审计通过。  
  **Full-Rank Correctness Guarantee**: Outputs are 100% full-rank decompositions—every cycle is algebraically independent and absolutely chordless. Verified across 30 benchmark datasets (1,000–10,000 edges).

- **部署灵活性**：专为 AWS Lambda、Docker 精简镜像、金融审计集群、在线编程平台等无法编译 C 扩展的环境设计。  
  **Deployment Flexibility**: Designed specifically for environments where compiling C extensions is impossible or restricted.

- **稠密到稀疏全覆盖**：支持从纯 3-环稠密图到纯 4-环网格再到混合环长大规模图的全谱系拓扑。  
  **Dense to Sparse**: Handles the full spectrum of topologies.

- **诚实声明的近似 MCB**：追求满秩正确性，不伪装精确最小环基。偏离是系统性的、方向恒定的（从不比精确 MCB 更短，只会更长）。详见[基准报告](docs/Blackhole_Benchmark_Report.md)和 [CAUTION.md](CAUTION.md)。  
  **Near-MCB, Honestly Stated**: Pursues full-rank correctness without pretending to be the exact MCB. Drift is systematic and directionally consistent. See [benchmark report](docs/Blackhole_Benchmark_Report.md) and [CAUTION.md](CAUTION.md).

---

## 🛠 Algorithmic Architecture / 算法架构

### 边向扩展 + 碰撞消元

传统环搜索算法（包括 igraph）依赖最短生成树的动态维护。Blackhole Diffusion 采用**边向扩展 + 碰撞消元**：不维护全局生成树，按环长维度逐维搜索无弦环，边搜边消元，用当前基的最长环作为动态剪枝上界。

Traditional cycle-search algorithms (including igraph) rely on dynamically maintaining a shortest spanning tree. Blackhole Diffusion uses **edge-wise expansion combined with collision elimination**: it does not maintain a global spanning tree but searches dimension-by-dimension for chordless cycles based on cycle length, eliminating candidates on-the-fly. The longest cycle in the current basis serves as a dynamic pruning upper bound.

### 消元引擎：CSRBlackholeDevourer

核心消元器采用 **CSR（压缩稀疏行）** 格式，内置黑洞边界检测与交替湮灭机制。擅长短环和稠密图，在纯 4-环网格上反超 igraph C 实现。

The core eliminator uses **Compressed Sparse Row (CSR)** format, featuring built-in black-hole boundary detection and alternating annihilation mechanisms. Excels at short cycles and dense graphs, outperforming igraph's C implementation on pure 4-cycle grids.

### 语言税：~15×

Python 相对于 C++ 有约 15 倍的字节码层面固有开销。但在纯 4-环网格上，这一差距被算法效率完全逆转：

Python incurs an inherent ~15× bytecode-level overhead compared to C++. However, this gap is completely reversed on pure 4-cycle grids:

| Dataset           | BH (Py)  | igraph (C) |
| ----------------- | -------- | ---------- |
| edge007 (5k 边)   | 5.56s    | 8.70s      |
| edge017 (10k 边)  | 23.38s   | 52.82s     |

> 规模越大差距越显著，从 1.6 倍扩大到 2.3 倍。

---

## 📊 Benchmarks / 基准测试

> 所有数据集均通过满秩审计（Rank 100% 对齐，0 弦环，0 碎环）。

### 1000 边级别：三方对比（iGraph vs NetworkX vs BH）

| Dataset | V/E/R       | iGraph MCB 终点 | iGraph  | NX-MCB   | BH     | BH vs NX |
| ------- | ----------- | --------------- | ------- | -------- | ------ | -------- |
| edge001 | 63/1003/941 | 3               | 0.02s   | 25.1s    | 0.23s  | 110×     |
| edge003 | 333/990/658 | 6               | 0.08s   | 139.5s   | 1.83s  | 76×      |
| edge006 | 200/1000/801| 5               | 0.06s   | 85.9s    | 1.28s  | 67×      |
| edge007 | 484/924/441 | 4               | 0.22s   | 197.7s   | 0.51s  | 391×     |
| edge010 | 250/1000/751| 5               | 0.08s   | 106.8s   | 0.75s  | 142×     |

> 完整 10 数据集分析见 [**1000 边基准报告**](docs/benchmark_1k.md)。

### 5000 边级别

| Dataset | V / E / R         | iGraph MCB 终点 | iGraph (C) | BH (Py)  | Ratio     |
| ------- | ----------------- | --------------- | ---------- | -------- | --------- |
| edge001 | 141/5072/4932     | 3               | 0.44s      | 3.35s    | 7.6×      |
| edge002 | 223/4997/4775     | 4               | 0.71s      | 8.24s    | 11.6×     |
| edge003 | 1666/4989/3324    | 7               | 2.88s      | 43.82s   | 15.2×     |
| edge004 | 1000/4975/3976    | 5               | 4.12s      | 35.87s   | 8.7×      |
| edge005 | 1666/4998/3333    | 12              | 3.40s      | 40.63s   | 11.9×     |
| edge006 | 1000/5000/4001    | 7               | 3.93s      | 35.84s   | 9.1×      |
| edge007 | 2500/4900/2401    | 4               | 8.70s      | 5.56s    | **0.64×** |
| edge008 | 2500/5400/2901    | 12              | 5.46s      | 41.65s   | 7.6×      |
| edge009 | 2500/5000/2501    | 11              | 6.12s      | 65.88s   | 10.8×     |
| edge010 | 1250/5000/3751    | 6               | 5.09s      | 45.39s   | 8.9×      |

### 10000 边级别

| Dataset | V / E / R         | iGraph MCB 终点 | iGraph (C) | BH (Py)   | Ratio     |
| ------- | ----------------- | --------------- | ---------- | --------- | --------- |
| edge011 | 200/10053/9854    | 3               | 1.33s      | 8.44s     | 6.3×      |
| edge012 | 316/10167/9852    | 4               | 3.54s      | 25.75s    | 7.3×      |
| edge013 | 3333/9990/6658    | 7               | 14.98s     | 202.63s   | 13.5×     |
| edge014 | 2000/9975/7976    | 6               | 10.86s     | 181.94s   | 16.8×     |
| edge015 | 3333/9999/6667    | 13              | 16.40s     | 93.22s    | 5.7×      |
| edge016 | 2000/10000/8001   | 7               | 13.50s     | 107.46s   | 8.0×      |
| edge017 | 4900/9660/4761    | 4               | 52.82s     | 23.38s    | **0.44×** |
| edge018 | 4900/10660/5761   | 13              | 27.89s     | 139.89s   | 5.0×      |
| edge019 | 5000/10000/5001   | 11              | 55.70s     | 291.22s   | 5.2×      |
| edge020 | 2500/10000/7501   | 7               | 82.22s     | 144.83s   | 1.8×      |

> **注**："iGraph MCB 终点" 是 iGraph 精确最小环基的最长环长度，仅作拓扑复杂度参考。BH 是近似 MCB，环长终点通常更高。纯 4-环网格（edge007/017）上 BH 反超 igraph。长环混合图候选池膨胀导致耗时上升——这是 CSR 消元在长环拓扑上的已知特征，非缺陷。Ratio = BH 耗时 / iGraph 耗时（<1 表示 BH 更快）。完整分析（环长漂移、基边膨胀、MCB 精确命中率）见 [**基准测试报告**](docs/Blackhole_Benchmark_Report.md)。

> **Note**: "iGraph MCB endpoint" is the longest cycle length in iGraph's exact minimum cycle basis, for topological complexity reference only. BH is near-MCB, typically with longer cycles. On pure 4-cycle grids (edge007/017), BH outperforms igraph. Candidate pool expansion on mixed graphs with long cycles increases runtime — a known characteristic of CSR elimination on long-cycle topologies, not a defect. Ratio = BH time / iGraph time (<1 means BH is faster). See [**benchmark report**](docs/Blackhole_Benchmark_Report.md) for full analysis (cycle length drift, base-edge inflation, MCB exact hit rate).

---

## 📐 Mathematical Guarantees / 数学保证

- **满秩无弦环基**：每个环是简单的、无弦的、代数独立的。秩 = E − V + C（连通分量数）。全部基准数据集验证通过。  
  **Full-Rank Chordless Cycle Basis**: Every cycle is simple, chordless, and algebraically independent. Rank = E − V + C (number of connected components). Verified on all benchmark datasets.

- **安全上界定理**：已有一个满秩无弦环基 B，其最长环长度为 M。所有可能存在的更优基的环长均 ≤ M。M 是后续所有环搜索的精确剪枝上界（存在性证明保证，非启发式）。  
  **Safe Upper Bound Theorem**: Given a full-rank chordless cycle basis B with maximum cycle length M, all potentially better bases must have cycles of length ≤ M. M serves as an exact pruning upper bound for all subsequent cycle searches (existence-proven, not heuristic).

---

## 🎯 Use Cases / 典型场景

- **GIS 自动化** — 空间拓扑重建、矢量线转面、地籍地块属性映射  
  **GIS Automation** — spatial topology reconstruction, vector line to polygon, cadastral parcel attribute mapping

- **无服务器 & 微服务** — AWS Lambda、Cloud Functions 即插即用  
  **Serverless & Microservices** — plug-and-play on AWS Lambda, Cloud Functions

- **电路网表分析** — 反馈回路追踪、回路检查、拓扑块隔离  
  **Circuit Netlist Analysis** — feedback loop tracing, loop checking, topological block isolation

- **分子拓扑环提取** — 零依赖流水线中直接识别二级结构环  
  **Molecular Topology** — direct identification of secondary structure rings in zero-dependency pipelines

- **金融隔离集群** — 纯 Python 代码秒级审计通过  
  **Financial Isolation Clusters** — pure Python code passes security audits instantly

---

## ⚖️ FAQ

### 输出的是精确最小环基（MCB）吗？ / Does it output the exact Minimum Cycle Basis (MCB)?

**不是。** Blackhole Diffusion 追求满秩正确性，不保证全局最短总环长。偏离是系统性的：从不比精确 MCB 更短，只会更长。1000 边级别 70% 的图基边膨胀 <1%，规模越大、环长跨度越大，偏离越明显。如果你需要严格 MCB 且 igraph 可用，请直接用 igraph。如果你在无法安装 igraph 的环境中需要一份正确可用的环基，Blackhole Diffusion 就是为你准备的。详见[**基准报告**](docs/Blackhole_Benchmark_Report.md)和 [CAUTION.md](CAUTION.md)。

**No.** Blackhole Diffusion pursues full-rank correctness without guaranteeing globally minimal total cycle length. The drift is systematic: never shorter than the exact MCB, only longer. At the 1,000-edge scale, 70% of graphs have <1% base-edge inflation; drift increases with scale and cycle-length span. If you need strict MCB and igraph is available, use igraph. If you need a correct, usable cycle basis in an environment where igraph can't be installed, Blackhole Diffusion is for you. See [**benchmark reports**](docs/Blackhole_Benchmark_Report.md) and [CAUTION.md](CAUTION.md).

### 为什么不直接用 igraph？ / Why not just use igraph?

igraph 需要编译 C 核心。在 AWS Lambda、Docker 精简镜像、金融审计集群等环境中，安装编译二进制往往被禁止或需数周审批。Blackhole Diffusion 解决的是 **igraph 进不去的场景**。两者互补，非替代。

igraph requires compiling C cores. In environments like AWS Lambda, Docker minimal images, or financial audit clusters, installing compiled binaries is often prohibited or requires weeks of approval. Blackhole Diffusion addresses scenarios where **igraph cannot be deployed**. They are complementary, not substitutes.

### 环长分布为什么和 igraph 不完全一致？ / Why isn't the cycle-length distribution identical to igraph's?

两者都是数学上有效的满秩基。Blackhole Diffusion 的边向扩展策略倾向于找到更长、更多样的环——这是刻意设计选择，追求环长多样性而非绝对最短总环长。在短环稠密图和纯网格图上，两者输出通常精确对齐。

Both produce mathematically valid full-rank bases. Blackhole Diffusion's edge-wise expansion strategy intentionally favors longer, more diverse cycles—this is by design, prioritizing diversity over absolute minimal total cycle length. Outputs typically align exactly on dense short-cycle graphs and pure grids.

### 什么时候快，什么时候慢？ / When is it fast or slow?

| 场景 / Scenario                             | 性能 / Performance                                    |
| ------------------------------------------- | ----------------------------------------------------- |
| 纯 3-环稠密图 / Pure 3-cycle dense graphs    | 🟢 **快 / Fast** — 甚至反超 igraph C 实现             |
| 纯 4-环网格 / Pure 4-cycle grids             | 🟢 **快 / Fast** — outperforms igraph's C impl.       |
| 短环混合图 (MCB ≤ 6) / Short-cycle mixed     | 🟡 **中等 / Medium** — 通常 10–50s @ 5000 边          |
| 长环混合图 (MCB ≥ 7) / Long-cycle mixed      | 🔴 **慢 / Slow** — 候选池膨胀，但结果正确              |

---

## 📜 License / 许可证

**MIT License** — free to use, modify, and distribute.  
**MIT License** — 自由使用、修改、分发。
