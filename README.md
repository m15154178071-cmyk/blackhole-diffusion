# Blackhole Diffusion（黑洞弥散）

> A pure-Python library for customizable chordless cycle-basis detection.  
> 纯 Python 标准库实现的可定制无弦环基检测库。

Blackhole Diffusion explores candidate cycles, expands cycle boundaries, and uses incremental GF(2) elimination to construct a full-rank chordless cycle basis. It is **not a strict minimum cycle basis (MCB) solver**: a full-rank chordless basis does not imply a globally minimum total cycle length.

Blackhole Diffusion 通过候选环搜索、黑洞边界扩展和 GF(2) 增量消元构造满秩无弦环基。它**不承诺求得严格意义上的最小环基（MCB）**：满秩无弦环基不等于总环长全局最小。

> **Refactoring status / 重构状态**  
> This README records the refactoring baseline and acceptance plan. The modular architecture, correctness improvements, and performance changes described below are targets—not claims that the refactor has already been implemented or verified.  
> 本 README 记录重构基线与验收方案。下述模块架构、正确性改进和性能变化均为目标，不代表重构已完成或已通过验证。

## Installation / 安装

```bash
pip install blackhole-diffusion
```

The library aims to use only the Python standard library at runtime. Optional third-party packages may be used for external benchmark comparisons; they are not required by the core library.

核心库目标是仅依赖 Python 标准库运行。外部基准对比可能使用第三方包，但核心库不依赖这些包。

## Quick start / 快速开始

```python
from blackhole_diffusion import chordless_cycle_basis

edges = {(1, 2), (2, 3), (3, 1), (3, 4), (4, 1)}
cycles = chordless_cycle_basis(edges)

for cycle in cycles:
    print(sorted(cycle))
```

See [examples_basic_usage.py](examples_basic_usage.py) for more examples.  
更多示例见 [examples_basic_usage.py](examples_basic_usage.py)。

## Refactoring plan / 重构方案

The goal is to make the implementation easier to maintain, test, extend, and use independently—without replacing or simplifying the algorithm's core mechanisms.

重构目标是在不替换或简化核心算法机制的前提下，让实现更易维护、测试、扩展和独立使用。

### Target module boundaries / 目标模块边界

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

以上是目标职责划分，不要求机械地一项对应一个文件。最终边界应结合更新后的源码审查确定。

### Shared data contracts / 统一数据契约

The recorded implementation represents a cycle or path as `(edge_ids, edges, nodes)`:

- `edge_ids`: identifiers used internally, including by elimination.
- `edges`: original graph edges, used for result restoration and edge-level checks.
- `nodes`: vertices in the structure.

Keep these meanings explicit at module boundaries. Do not mix node sets with edge sets or silently combine incompatible edge-ID spaces.

当前记录中的环或路径使用 `(edge_ids, edges, nodes)` 表示：`edge_ids` 用于内部处理（包括消元），`edges` 是用于结果还原和边关系检查的原始图边，`nodes` 是结构中的顶点。模块边界应明确这些语义，避免混用节点集和边集，或混淆不同的边 ID 空间。

### Validation and elimination / 验证与消元

The recorded baseline includes `_validate_and_build_local_path()` for shared structural checks such as node/edge counts, edge membership, local adjacency construction, and connectivity. Path and cycle degree constraints should then be checked according to their respective structure.

The elimination layer should keep the responsibilities of `BlockwiseCycleReducer`, `SingleDimensionCycleReducer`, and `CSRBlackholeDevourer` clear while exposing consistent inputs and outputs. The CSR implementation's compact `array.array('Q')` representation and incremental GF(2) independence checks are important design elements to preserve where confirmed by the updated source.

当前记录中的基线包含 `_validate_and_build_local_path()`，用于共享的结构检查，例如节点数与边数关系、边的归属、局部邻接构建和连通性；之后再按路径或环分别验证度数约束。

消元层应明确 `BlockwiseCycleReducer`、`SingleDimensionCycleReducer` 和 `CSRBlackholeDevourer` 的职责，同时提供一致的输入输出。若更新后的源码确认仍采用 CSR 紧凑存储 `array.array('Q')` 和 GF(2) 增量独立性判断，应在重构中保留这些设计要点。

### Algorithm mechanisms to preserve / 必须保留的算法机制

- Multi-dimensional candidate-cycle mining.
- Chordless-cycle and independent-path search.
- Blackhole boundary detection and expansion.
- Dynamic candidate ranking and management.
- CSR sparse elimination and GF(2) independence checks.
- Incremental elimination.
- Long-cycle completion and local Horton completion.
- A spanning-tree fundamental-cycle fallback.

重构应保留多维候选环挖掘、无弦环与独立路径搜索、黑洞边界识别和扩展、候选动态排序、CSR 稀疏消元与 GF(2) 独立性判断、增量消元、长环及局部 Horton 补全，以及生成树基本环兜底。不能将完整流程简化成普通环搜索加生成树兜底。

## Correctness and acceptance criteria / 正确性与验收标准

A refactored version should be accepted only after it has been checked against the updated implementation and tests. At minimum, verify that:

1. Every output edge is an edge in the input graph.
2. Every output is a valid simple cycle and is chordless.
3. Output cycles are linearly independent over GF(2).
4. The number of cycles equals the target cycle-space rank, `E - V + C`, where `C` is the number of connected components (with the graph's vertex/edge conventions stated and consistently applied).
5. No cycle is duplicated.
6. Disconnected graphs are handled correctly.
7. Vertex-set and original-edge-set input interfaces have consistent result semantics.
8. The result is described as a full-rank chordless cycle basis—not as a strict MCB unless that property is separately proved and tested.

重构版本必须结合更新后的实现和测试验收，至少验证：输出边均来自输入图；每个结果都是合法简单无弦环；环在 GF(2) 上线性独立；环数量等于目标环空间秩 `E - V + C`（其中 `C` 为连通分量数，并统一说明顶点和边的计数约定）；无重复环；正确处理非连通图；顶点集合与原始边集合两种输入接口语义一致；并且只在另行证明和测试后才称为严格 MCB。

## Benchmarking / 基准测试

Architecture changes alone do not establish a performance improvement. Compare the old and refactored versions on the same datasets, Python version, and test environment. Record:

- Total runtime and peak memory.
- Number of candidates and elimination operations.
- Final basis size and cycle-length distribution.
- Correctness audit results, including rank and chordlessness.

架构拆分本身不能证明性能提升。前后版本必须使用相同数据集、Python 版本和测试环境进行对比，并记录总运行时间、峰值内存、候选数量、消元次数、最终环基数量、环长分布及秩和无弦性等正确性审计结果。

Optional external tools can be used as independent comparison baselines; they are not runtime dependencies of the library. Results should distinguish a full-rank chordless basis from an exact minimum cycle basis.

可选地使用外部工具作为独立对照基线，但它们不是本库的运行依赖。报告应明确区分满秩无弦环基与精确最小环基。

## Development notes / 开发说明

The refactoring record dated 2026-11-12 was prepared from the supplied `Blackhole_Base(1).py` source. The repository code may not yet match that source or this plan. Revisit the architecture, API compatibility, and every performance or correctness claim after the updated code is available; publish measured results only after reproducible tests.

2026-11-12 的重构记录依据用户提供的 `Blackhole_Base(1).py` 整理，仓库当前代码可能尚未与该源码或本方案一致。待更新代码提交后，应重新审查架构、接口兼容性及所有性能和正确性声明；只有在可复现测试完成后，才发布实测结论。

## License / 许可证

MIT License. See the [LICENSE](LICENSE) file.
