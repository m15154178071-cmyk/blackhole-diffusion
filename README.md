# Blackhole Diffusion（黑洞弥散）

> A pure-Python library for customizable chordless cycle-basis detection.  
> 纯 Python 标准库实现的可定制无弦环基检测库。

Blackhole Diffusion explores candidate cycles, expands cycle boundaries, and uses incremental GF(2) elimination to construct a full-rank chordless cycle basis. It is **not a strict minimum cycle basis (MCB) solver**: a full-rank chordless basis does not imply a globally minimum total cycle length.

Blackhole Diffusion 通过候选环搜索、黑洞边界扩展和 GF(2) 增量消元构造满秩无弦环基。它**不承诺求得严格意义上的最小环基（MCB）**：满秩无弦环基不等于总环长全局最小。

## Installation / 安装

```bash
pip install blackhole-diffusion
```

The core library is designed to run with the Python standard library. Optional third-party packages may be used for external benchmark comparisons; they are not required by the core library.

核心库设计为仅依赖 Python 标准库运行。外部基准对比可选用第三方工具，但核心库不依赖这些工具。

## Quick start / 快速开始

```python
from blackhole_diffusion import chordless_cycle_basis

edges = {(1, 2), (2, 3), (3, 1), (3, 4), (4, 1)}
cycles = chordless_cycle_basis(edges)

for cycle in cycles:
    print(sorted(cycle))
```

See [examples/examples_basic_usage.py](examples/examples_basic_usage.py) for more examples.  
更多示例见 [examples/examples_basic_usage.py](examples/examples_basic_usage.py)。

## Refactoring overview / 重构概述

The refactoring organizes the algorithm into clearer responsibilities while preserving its distinctive cycle-search, blackhole-expansion, and elimination workflow. The aim is to make the implementation easier to maintain, test, extend, and use through a stable public interface.

本次重构围绕职责拆分和数据边界整理算法工程结构，同时保留候选环搜索、黑洞扩展和消元等核心流程，提升代码的可维护性、可测试性、可扩展性，并稳定对外接口。

### Module responsibilities / 模块职责

| Area | Responsibility |
| --- | --- |
| Graph data | Graph initialization, adjacency, edge IDs, connected components, and graph rank |
| Encoding | Node/edge encoding and restoration |
| Validation | Simple-cycle, chordless-cycle, and chordless-path validation |
| Search | Candidate cycle and path discovery across lengths |
| Blackhole construction | Core-edge selection, boundary expansion, and long-cycle completion |
| Elimination | CSR representation, GF(2) elimination, and incremental independence checks |
| Candidate management | De-duplication, ranking, tiers, and updates |
| Scheduling | Iteration, state transitions, and termination |
| Public API | Input normalization and result conversion |

以上是各功能层的职责划分，具体文件组织以源码实现为准。

### Shared cycle and path data / 统一环与路径数据

A cycle or path is represented internally as `(edge_ids, edges, nodes)`:

- `edge_ids`: internal edge identifiers used by search and elimination.
- `edges`: original graph edges used for result restoration and edge-level checks.
- `nodes`: vertices in the cycle or path.

内部环或路径使用 `(edge_ids, edges, nodes)` 统一表达：`edge_ids` 是搜索和消元使用的内部边编号；`edges` 是用于结果还原和边关系检查的原始图边；`nodes` 是环或路径中的顶点。明确三者语义可避免节点集、边集和不同边编号空间混用。

### Structural validation and sparse elimination / 结构验证与稀疏消元

Shared validation builds local adjacency and checks node/edge counts, edge membership, connectivity, and the structure-specific degree constraints for paths and cycles. The elimination layer separates the roles of `BlockwiseCycleReducer`, `SingleDimensionCycleReducer`, and `CSRBlackholeDevourer`, with CSR-based sparse storage and incremental GF(2) independence checks.

统一验证流程负责构建局部邻接关系，并检查节点与边的数量关系、边的归属、连通性，以及路径或环各自的度数约束。消元层区分 `BlockwiseCycleReducer`、`SingleDimensionCycleReducer` 和 `CSRBlackholeDevourer` 的职责，采用 CSR 稀疏存储和 GF(2) 增量独立性判断。

### Algorithm workflow / 算法流程

The execution flow separates candidate processing and elimination into explicit stages, including safe elimination, standard probing, alternating annihilation, and completion. Candidate discovery, dynamic ranking, blackhole boundary expansion, and completion work together rather than reducing the algorithm to ordinary cycle search followed only by a spanning-tree fallback.

执行流程将候选处理和消元划分为明确阶段，包括安全消元、标准探测、交替湮灭和完成阶段。候选搜索、动态排序、黑洞边界扩展与补全协同工作，不将完整算法简化为普通环搜索加生成树兜底。

### Core mechanisms / 核心机制

- Multi-dimensional candidate-cycle mining.
- Chordless-cycle and independent-path search.
- Blackhole boundary detection and expansion.
- Dynamic candidate ranking and management.
- CSR sparse elimination and GF(2) independence checks.
- Incremental elimination.
- Long-cycle completion and local Horton completion.
- A spanning-tree fundamental-cycle fallback.

保留多维候选环挖掘、无弦环和独立路径搜索、黑洞边界识别与扩展、候选动态排序、CSR 稀疏消元与 GF(2) 独立性判断、增量消元、长环及局部 Horton 补全，以及生成树基本环兜底。

## Correctness criteria / 正确性标准

A valid full-rank chordless cycle basis should satisfy the following checks:

1. Every output edge belongs to the input graph.
2. Every output is a valid simple, chordless cycle.
3. Output cycles are linearly independent over GF(2).
4. The number of cycles equals the target cycle-space rank, `E - V + C`, where `C` is the number of connected components; graph vertex/edge counting conventions must be consistent.
5. No cycle is duplicated.
6. Disconnected graphs are handled correctly.
7. Vertex-set and original-edge-set input interfaces have consistent result semantics.

满秩无弦环基应满足：输出边均属于输入图；每个输出都是合法简单无弦环；环在 GF(2) 上线性独立；环数量等于目标环空间秩 `E - V + C`（`C` 为连通分量数，顶点和边的计数约定应保持一致）；无重复环；正确处理非连通图；顶点集合与原始边集合两种输入接口具有一致的结果语义。

A full-rank chordless cycle basis is not necessarily a strict MCB. Minimum-total-length claims require separate proof and verification.

满秩无弦环基不必然是严格 MCB。关于总环长最小的结论需要单独证明和验证。

## Benchmarking / 基准测试

Architecture changes alone do not establish a performance improvement. Compare versions using the same datasets, Python version, and test environment. Record:

- Total runtime and peak memory.
- Number of candidates and elimination operations.
- Final basis size and cycle-length distribution.
- Correctness audit results, including rank and chordlessness.

架构调整本身不能证明性能提升。版本对比应使用相同数据集、Python 版本和测试环境，并记录总运行时间、峰值内存、候选数量、消元次数、最终环基数量、环长分布，以及秩和无弦性等正确性审计结果。

Optional external tools can serve as independent comparison baselines; they are not runtime dependencies of the library. Benchmark reports should distinguish a full-rank chordless basis from an exact minimum cycle basis.

可选外部工具可作为独立对照基线，但不是本库的运行依赖。基准报告应明确区分满秩无弦环基与精确最小环基。

## Version refactoring update summary / 版本重构更新功能汇总

This refactoring update brings the algorithm's engineering structure and internal contracts into focus:

- Separates graph data, encoding, validation, search, blackhole construction, elimination, candidate management, scheduling, and public API responsibilities.
- Unifies the internal cycle/path representation as `(edge_ids, edges, nodes)`.
- Consolidates shared structural validation for paths and cycles.
- Clarifies reducer responsibilities and standardizes elimination boundaries while retaining CSR-based GF(2) incremental processing.
- Makes algorithm stages and termination flow easier to follow.
- Preserves candidate mining, blackhole expansion, dynamic ranking, long-cycle and local Horton completion, and the spanning-tree fallback.
- Defines correctness and reproducible benchmarking criteria for ongoing verification.

本次版本重构更新重点如下：

- 梳理图数据、编码、验证、搜索、黑洞构建、消元、候选管理、调度及公开接口等职责边界。
- 统一内部环与路径数据结构为 `(edge_ids, edges, nodes)`。
- 汇总路径和环共用的结构验证流程。
- 明确不同消元器的职责并规范消元接口，同时保留基于 CSR 的 GF(2) 增量处理。
- 梳理算法阶段切换及终止流程。
- 保留候选环挖掘、黑洞扩展、动态排序、长环和局部 Horton 补全及生成树兜底机制。
- 明确正确性验收和可复现基准测试要求，便于持续验证与优化。

## License / 许可证

MIT License. See the [LICENSE](LICENSE) file.
