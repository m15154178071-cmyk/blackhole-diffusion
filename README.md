# Blackhole Diffusion（黑洞弥散）

A pure-Python graph engine for extracting full-rank chordless cycle bases.  
Zero dependencies — runs anywhere Python runs.

纯 Python 标准库实现的图算法引擎，专注于提取满秩无弦环基。零外部依赖，即插即用。

💡 **Core Features / 核心特性**
- **Zero External Dependencies**: Built entirely with Python's standard library. No C compilation, no wheel files, and no third-party packages. Plug-and-play in any Python 3.x environment.
  **零外部依赖**：100% Python 标准库构建。无 C 编译、无 wheel 文件、无第三方包。任何 Python 3.x 环境即插即用。
- **Full-Rank Correctness Guarantee**: Outputs are 100% full-rank decompositions—every cycle is algebraically independent and absolutely chordless. Verified across 20 benchmark datasets (5,000–10,000 edges).
  **满秩正确性保证**：输出结果 100% 满秩解构，所有环代数独立且绝对无弦。20 个基准数据集（5000–10000 边）全部审计通过。
- **Deployment Flexibility**: Designed specifically for environments where compiling C extensions is impossible or restricted, such as AWS Lambda, Docker minimal images, financial auditing clusters, and online coding platforms.
  **部署灵活性**：专为 AWS Lambda、Docker 精简镜像、金融审计集群、在线编程平台等无法编译 C 扩展的环境设计。
- **Dense to Sparse Support**: Handles the full spectrum of topologies—from purely dense 3-cycle graphs and pure 4-cycle grids to large-scale mixed-cycle-length graphs.
  **稠密到稀疏支持**：支持从纯 3-环稠密图到纯 4-环网格再到混合环长大规模图的全谱系拓扑。

🛠 **Algorithmic Architecture / 算法架构**

**Edge-wise Expansion + Collision Elimination**  
Traditional cycle-search algorithms (including igraph) rely on dynamically maintaining a shortest spanning tree. Blackhole Diffusion uses edge-wise expansion combined with collision elimination: it does not maintain a global spanning tree but searches dimension-by-dimension for chordless cycles based on cycle length, eliminating candidates on-the-fly. The longest cycle in the current basis serves as a dynamic pruning upper bound.

**边向扩展 + 碰撞消元**  
传统环搜索算法（包括 igraph）依赖最短生成树的动态维护。Blackhole Diffusion 采用边向扩展 + 碰撞消元：不维护全局生成树，按环长维度逐维搜索无弦环，边搜边消元，用当前基的最长环作为动态剪枝上界。

**Elimination Engine: CSRBlackholeDevourer**  
The core eliminator uses Compressed Sparse Row (CSR) format, featuring built-in black-hole boundary detection and alternating annihilation mechanisms. Excels at short cycles and dense graphs, outperforming igraph’s C implementation on pure 4-cycle grids.

**消元引擎：CSRBlackholeDevourer**  
核心消元器采用 CSR（压缩稀疏行）格式，内置黑洞边界检测与交替湮灭机制。擅长短环和稠密图，在纯 4-环网格上反超 igraph C 实现。

**Language Tax: ~15×**  
Python incurs an inherent ~15× bytecode-level overhead compared to C++. In practice, the real cost during elimination—billions of XOR operations, random memory accesses, and Python object allocations—is far higher. Direct runtime comparisons between Blackhole Diffusion and igraph do not reflect algorithmic efficiency alone.

However, this gap is completely reversed on pure 4-cycle grids:

| Dataset      | BH (Py) | igraph (C) |
|--------------|---------|------------|
| edge007 (5k edges) | 5.56s   | 8.70s      |
| edge017 (10k edges)| 23.38s  | 52.82s     |

The performance advantage grows with scale—from 1.6× faster to 2.3× faster.

**语言税：~15×**  
Python 相对于 C++ 有约 15 倍的字节码层面固有开销。实际消元过程中，亿次级 XOR + 随机内存访问 + Python 对象分配的真实开销远超此值。直接对比 Blackhole Diffusion 和 igraph 的耗时不能等价反映算法本身效率。

但在纯 4-环网格上，这一差距被算法效率完全逆转：

| 数据集|BH (Py)|igraph (C)|
| ---|---|---|
| edge007 (5k边)|5.56s|8.70s|
| edge017 (10k边)|23.38s|52.82s|

规模越大差距越显著，从 1.6 倍扩大到 2.3 倍。

📊 **Benchmarks / 基准测试**

All datasets pass full-rank audits (100% rank alignment, 0 chorded cycles, 0 fragmented cycles).

**5,000-edge Scale**

| Dataset | V / E / R | MCB | iGraph (C) | BH (Py) | Ratio |
|---------|-----------|-----|------------|---------|-------|
| edge001 | 141/5072/4932 | 3 | 0.44s | 3.35s | 7.6× |
| edge002 | 223/4997/4775 | 4 | 0.71s | 8.24s | 11.6× |
| ... | ... | ... | ... | ... | ... |
| edge007 | 2500/4900/2401 | 4 | 8.70s | 5.56s | 0.64× 🔥 |

**10,000-edge Scale**

| Dataset | V / E / R | MCB | iGraph (C) | BH (Py) | Ratio |
|---------|-----------|-----|------------|---------|-------|
| edge011 | 200/10053/9854 | 3 | 1.33s | 8.44s | 6.3× |
| ... | ... | ... | ... | ... | ... |
| edge017 | 4900/9660/4761 | 4 | 52.82s | 23.38s | 0.44× 🔥 |

*Note*: BH outperforms igraph on pure 4-cycle grids (edge007/017). For pure short-cycle graphs (MCB ≤ 4), total base edges align exactly with igraph. Candidate pool explosion in long-cycle mixed graphs increases runtime—a known characteristic of CSR elimination on long-cycle topologies, not a defect.  
Ratio = BH time / iGraph time (<1 means BH is faster).  
For full analysis (cycle-length drift, base-edge inflation, MCB hit rate, historical consistency), see [Benchmark Report](docs/benchmark.md).

**注**：  
纯 4-环网格（edge007/017）上 BH 反超 igraph。纯短环图（MCB ≤ 4）基总边数与 igraph 精确对齐。  
长环混合图候选池膨胀导致耗时上升——这是 CSR 消元在长环拓扑上的已知特征，非缺陷。  
Ratio = BH 耗时 / iGraph 耗时（<1 表示 BH 更快）。  
完整分析（环长漂移、基边膨胀、MCB 精确命中率、与历史数据一致性）见 [基准测试报告](docs/benchmark.md)。

📐 **Mathematical Guarantees / 数学保证**
- **Full-Rank Chordless Cycle Basis**: Every cycle is simple, chordless, and algebraically independent. Rank = E − V + C (number of connected components). Verified on all benchmark datasets.
  **满秩无弦环基**：每个环是简单的、无弦的、代数独立的。秩 = E − V + C（连通分量数）。全部基准数据集验证通过。
- **Safe Upper Bound Theorem**: Given a full-rank chordless cycle basis B with maximum cycle length M, all potentially better bases must have cycles of length ≤ M. M serves as an exact pruning upper bound for all subsequent cycle searches (existence-proven, not heuristic).
  **安全上界定理**：已有一个满秩无弦环基 B，其最长环长度为 M。所有可能存在的更优基的环长均 ≤ M。M 是后续所有环搜索的精确剪枝上界（存在性证明保证，非启发式）。

🎯 **Use Cases / 典型场景**
- **GIS Automation**: Spatial topology reconstruction, vector-to-polygon conversion, cadastral parcel attribute mapping.
  **GIS 自动化**：空间拓扑重建、矢量线转面、地籍地块属性映射
- **Serverless & Microservices**: Plug-and-play on AWS Lambda, Cloud Functions.
  **无服务器 & 微服务**：AWS Lambda、Cloud Functions 即插即用
- **Circuit Netlist Analysis**: Feedback loop tracing, loop checking, topological block isolation.
  **电路网表分析**：反馈回路追踪、回路检查、拓扑块隔离
- **Molecular Topology Ring Extraction**: Direct secondary structure ring identification in zero-dependency pipelines.
  **分子拓扑环提取**：零依赖流水线中直接识别二级结构环
- **Financial Isolation Clusters**: Pure Python code passes security audits instantly.
  **金融隔离集群**：纯 Python 代码秒级审计通过

⚖️ **FAQ**

**Q: Why not just use igraph?**  
igraph requires compiling C cores. In environments like AWS Lambda, Docker minimal images, or financial audit clusters, installing compiled binaries is often prohibited or requires weeks of approval. Blackhole Diffusion addresses scenarios where igraph cannot be deployed. They are complementary, not substitutes.

**Q: 为什么不直接用 igraph？**  
igraph 需要编译 C 核心。在 AWS Lambda、Docker 精简镜像、金融审计集群等环境中，安装编译二进制往往被禁止或需数周审批。Blackhole Diffusion 解决的是 igraph 进不去的场景。两者互补，非替代。

**Q: Why isn’t the cycle-length distribution identical to igraph’s?**  
Both produce mathematically valid full-rank bases. Blackhole Diffusion’s edge-wise expansion strategy intentionally favors longer, more diverse cycles—this is by design, prioritizing diversity over absolute minimal total cycle length. Outputs typically align exactly on dense short-cycle graphs and pure grids.

**Q: 环长分布为什么和 igraph 不完全一致？**  
两者都是数学上有效的满秩基。Blackhole Diffusion 的边向扩展策略倾向于找到更长、更多样的环——这是刻意设计选择，追求环长多样性而非绝对最短总环长。在短环稠密图和纯网格图上，两者输出通常精确对齐。

**Q: When is it fast or slow?**  
- **Fast**: Pure dense 3-cycle graphs, pure 4-cycle grids (the latter even outperforms igraph’s C implementation).
- **Medium**: Mixed graphs dominated by short cycles (MCB ≤ 6); typically 10–50s for 5,000 edges.
- **Slow**: Mixed long-cycle graphs (MCB ≥ 7); candidate pool explosion occurs, but results remain correct full-rank chordless cycle bases.

**Q: 什么时候快，什么时候慢？**  
- **快**：纯 3-环稠密图、纯 4-环网格——后者甚至反超 igraph C 实现  
- **中等**：短环为主的混合图（MCB ≤ 6），通常 10–50s @ 5000 边  
- **慢**：长环混合图（MCB ≥ 7），候选池膨胀，但结果是正确的满秩无弦环基

📜 **License**  
MIT License — free to use, modify, and distribute.

**许可证**  
MIT License — 自由使用、修改、分发。
