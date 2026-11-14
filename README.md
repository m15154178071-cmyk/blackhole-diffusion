### Completeness and fallback strategy / 完备性与兜底策略

Blackhole Diffusion does not rely on a single search pass. Instead, it combines a multi-stage candidate generator with a final independent-cycle reduction.

The pipeline is:

1. Build a spanning-tree fundamental-cycle seed set from the graph.
2. Search for short and medium candidate cycles and chordless paths.
3. Expand candidate boundaries via blackhole-style local growth.
4. When the search space is still incomplete, trigger a localized Horton-style completion pass seeded by the most relevant nodes and boundary structures.
5. Run GF(2) incremental elimination to keep only linearly independent cycles and enforce the target cycle-space rank.

This means the algorithm is designed as a hybrid framework: local Horton completion provides additional candidate coverage, while the modular GF(2) reducer acts as the final correctness filter. In other words, the reducer is not merely a post-processing cosmetic step; it is the mechanism that removes linear dependence and preserves full rank.

This hybrid structure is why the project can claim a full-rank chordless cycle basis under its intended design, while still explicitly avoiding a stronger claim of strict minimum cycle basis (MCB) optimality. The library guarantees the correctness conditions of a full-rank chordless basis, not the global minimum-total-length property.

在本库中，并不是只依赖单一搜索阶段，而是采用“候选搜索 + 局部扩展 + 兜底补全 + GF(2) 消元”的混合流程：

1. 先从生成树基本环构造初始种子。
2. 继续搜索短环、中长环和无弦路径候选。
3. 通过黑洞边界扩展与局部闭合补全候选范围。
4. 在候选不够时触发局部 Horton 式补集，并以关键节点和边界类型作为种子。
5. 最后执行 GF(2) 增量消元，保留线性独立的环，确保达成目标秩。

也就是说，Horton 兜底负责补足候选覆盖，GF(2) 消元负责甄别并保留真正的独立环基。它不是“单纯枚举所有环”的启发式方案，而是一种“候选覆盖 + 代数筛选”的双重机制。

这也是该项目不声称严格 MCB 但仍能声称“满秩无弦环基”的核心原因：它保证的是完整环空间的一组独立无弦基，不保证全局总环长最小。

---
