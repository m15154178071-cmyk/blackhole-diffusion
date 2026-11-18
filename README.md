# Blackhole Diffusion

<p align="left">
  <a href="https://pypi.org/project/blackhole-diffusion/"><img alt="PyPI" src="https://img.shields.io/pypi/v/blackhole-diffusion.svg"></a>
  <img alt="Python" src="https://img.shields.io/badge/python-%3E%3D3.8-blue.svg">
  <img alt="License" src="https://img.shields.io/badge/license-MIT-green.svg">
  <img alt="Dependencies" src="https://img.shields.io/badge/dependencies-0-brightgreen.svg">
</p>

A pure-Python graph library for constructing a **full-rank chordless cycle basis**.

It combines spanning-tree fundamental cycles, candidate cycle/path generation, localized Horton-style fallback, and GF(2) incremental elimination. The core implementation has **zero runtime dependencies**.

> [!IMPORTANT]
> “Full-rank chordless” and “minimum cycle basis (MCB)” are different guarantees. Blackhole Diffusion aims to return a correct, algebraically independent basis whose cycles are chordless. It does **not** claim to solve exact MCB globally or guarantee globally minimal total cycle length.

## Contents

- [Why Blackhole Diffusion](#why-blackhole-diffusion)
- [Installation](#installation)
- [Quick Start](#quick-start)
- [API](#api)
- [Graph and Cycle Semantics](#graph-and-cycle-semantics)
- [What the Algorithm Guarantees](#what-the-algorithm-guarantees)
- [Testing](#testing)
- [Benchmarks](#benchmarks)
- [Project Structure](#project-structure)
- [Documentation](#documentation)
- [Limitations](#limitations)
- [Contributing](#contributing)
- [License](#license)
- [中文简介](#中文简介)

## Why Blackhole Diffusion

- **Pure Python:** the core module has no third-party runtime dependencies.
- **Full-rank output:** the basis dimension targets `E − V + C`, where `C` is the number of connected components.
- **Chordless cycles:** returned cycles are checked against the induced subgraph so no cycle vertex may have an extra internal neighbor.
- **Disconnected-graph support:** computes rank independently for the overall graph and processes components.
- **Two APIs:** get a result as vertex sets or as edge sets.
- **File input:** pass either an edge set or a whitespace/comma-separated edge-file path.

## Installation

Requires Python 3.8 or newer.

### From PyPI

```bash
pip install blackhole-diffusion
```

### From a source checkout

```bash
git clone https://github.com/m15154178071-cmyk/blackhole-diffusion.git
cd blackhole-diffusion
pip install -e .
```

The core package has no dependencies. Optional development and benchmark dependencies are declared separately:

```bash
pip install -e ".[dev]"
pip install -e ".[benchmark]"
```

## Quick Start

### Vertex-set API

```python
from blackhole_diffusion import chordless_cycle_basis

edges = {
    (1, 2), (2, 3), (3, 1),
    (2, 4), (4, 3),
}

cycles = chordless_cycle_basis(edges)

for cycle in cycles:
    print(sorted(cycle))
```

### Edge-set API

```python
from blackhole_diffusion import chordless_cycle_basis_edges

edges = {(1, 2), (2, 3), (3, 1)}
cycle_edges = chordless_cycle_basis_edges(edges)

print(cycle_edges)
# [frozenset({(1, 2), (1, 3), (2, 3)})]
```

### Read edges from a file

The input file supports whitespace- or comma-separated undirected edges:

```text
1 2
2 3
3 1
```

```python
from blackhole_diffusion import chordless_cycle_basis

basis = chordless_cycle_basis("edge/edge001.txt")
```

Save vertex lists directly by supplying an output path:

```python
chordless_cycle_basis(edges, output_file="cycles.txt")
```

Each output line contains one cycle, with its vertices separated by spaces.

### Command-line usage

```bash
python blackhole_diffusion.py edge/edge001.txt out.txt
```

More runnable examples are available in [`examples/examples_basic_usage.py`](examples/examples_basic_usage.py).

## API

### `chordless_cycle_basis(edges, output_file=None)`

Returns a list of vertex sets representing the cycle basis.

- `edges`: a set of `(u, v)` tuples or a path to an edge file.
- `output_file`: optional path for writing one vertex cycle per line.
- `return`: `list[set]`.

```python
basis = chordless_cycle_basis({(1, 2), (2, 3), (3, 1)})
assert basis == [{1, 2, 3}]
```

### `chordless_cycle_basis_edges(edges, output_file=None)`

Returns the same basis as a list of frozen edge sets.

- `edges`: a set of `(u, v)` tuples or a path to an edge file.
- `output_file`: optional path for writing each cycle with `u-v` pairs.
- `return`: `list[frozenset[(u, v)]]`.

### `get_cycles_results(raw_edges)`

The lower-level public entry used to obtain vertex cycles from an already loaded edge set.

### Supported vertex types

The implementation includes integer and string vertex encoding support. The recommended public API usage is integer-labeled vertices or a consistent label type across the graph.

## Graph and Cycle Semantics

- Edges are treated as undirected.
- `(u, v)` and `(v, u)` are the same edge.
- Duplicate edges are removed.
- Self-loops are ignored for graph-rank and cycle calculation.
- Isolated vertices cannot be represented by an edge-only input.
- The target cycle rank is:

```text
rank = E - V + C
```

where:

- `E` is the number of unique undirected edges,
- `V` is the number of vertices appearing in those edges,
- `C` is the number of connected components.

A cycle is chordless when every vertex on the cycle has exactly two neighbors inside the induced cycle subgraph. Thus, extra chords between cycle vertices are rejected.

## What the Algorithm Guarantees

The library is designed to return a basis that is:

1. algebraically linearly independent over GF(2),
2. full-rank with respect to `E − V + C`, and
3. chordless according to the cycle's induced subgraph.

For the full-rank and chordlessness claims, the implementation uses independent edge/rank reduction and validation. The public tests cover empty graphs, trees, triangles, complete graphs, shared-edge graphs, and edge/API output.

## Algorithm Overview

The implementation is organized as a hybrid pipeline:

1. Build a spanning-tree fundamental-cycle seed set.
2. Search short and medium-length chordless-cycle candidates.
3. Expand candidate boundaries through local graph growth.
4. Use localized Horton-style candidate completion when coverage is incomplete.
5. Reduce candidates incrementally using GF(2) elimination.
6. Retain independent candidates until the target cycle rank is reached.

This is a candidate-coverage framework, not a simple enumeration of every cycle. See [`CAUTION.md`](CAUTION.md) for the project’s exact limitations and verification scope.

## Testing

Run the standard-library test suite:

```bash
python -m unittest test/test_basic.py
```

Run all tests with pytest:

```bash
python -m pytest
```

Tests are located in [`test/`](test/), including:

- `test/test_basic.py` — core API and graph cases,
- `test/test_real_graphs.py` — generated real-topology-style graph tests,
- `test/generate_large_cases.py` — large edge-case generation,
- `test/validate_basis_networkx.py` — optional NetworkX cross-validation.

For benchmark dependencies:

```bash
pip install -e ".[benchmark]"
python benchmark.py
```

## Benchmarks

Benchmark utilities compare Blackhole Diffusion with NetworkX and, when available, igraph.

Reports in this repository include:

- [`docs/benchmark_1k.md`](docs/benchmark_1k.md) — 1,000-edge benchmark summary,
- [`docs/Blackhole_Benchmark_Report.md`](docs/Blackhole_Benchmark_Report.md) — broader benchmark report,
- [`edge/edge_README.md`](edge/edge_README.md) — benchmark dataset notes.

Benchmark results are illustrative and vary with graph topology, graph size, hardware, and Python/runtime version. They should not be interpreted as a proof of optimality or a substitute for independent validation.

## Project Structure

```text
blackhole-diffusion/
├── blackhole_diffusion.py       # Core implementation and public API
├── benchmark.py                 # NetworkX / igraph / audit benchmark runner
├── examples/
│   └── examples_basic_usage.py  # Runnable basic examples
├── test/                        # Unit and validation suites
├── docs/                        # Benchmark and algorithm documentation
├── edge/                        # Example graph datasets
├── pyproject.toml               # Package metadata and dependencies
├── README.md
├── CAUTION.md                   # Guarantees and non-guarantees
├── CHANGELOG.md
├── COLLABORATION.md
└── LICENSE
```

## Documentation

- [`CAUTION.md`](CAUTION.md) — important guarantee boundaries,
- [`CHANGELOG.md`](CHANGELOG.md) — release history,
- [`COLLABORATION.md`](COLLABORATION.md) — collaboration interests,
- [`docs/benchmark_1k.md`](docs/benchmark_1k.md) — condensed benchmark results,
- [`docs/Blackhole_Benchmark_Report.md`](docs/Blackhole_Benchmark_Report.md) — detailed benchmark report.

## Limitations

- This project does not currently guarantee the exact minimum cycle basis.
- Output cycle size and redundancy depend on the graph and candidate-search path.
- Self-checking validates full rank and chordlessness; it does not prove global minimum length.
- Pure-Python implementation may be slower than compiled graph libraries.
- Benchmark comparisons against exact MCB implementations are for engineering assessment, not formal guarantees.
- Large or highly irregular graphs may require more memory and runtime than compact C/C++ implementations.

## Contributing

Contributions are welcome, especially in:

- correctness and property tests,
- disconnected-graph handling,
- performance and memory optimization,
- reproducible benchmark datasets,
- documentation and API ergonomics,
- theorem/algorithm review.

Please include a minimal reproducer and verification details with bug reports or pull requests.

## License

MIT License. See [`LICENSE`](LICENSE).

---

# 中文简介

Blackhole Diffusion 是一个纯 Python 图算法库，用于构造**满秩无弦环基**。

核心实现零外部运行时依赖，并把生成树基本环、多阶段候选环/无弦路径、局部 Horton 式兜底候选，以及 GF(2) 增量消元组合成混合流水线。

目标环空间秩为：

```text
rank = E - V + C
```

其中 `E` 是无向边数，`V` 是参与边的节点数，`C` 是连通分量数。

### 快速使用

```python
from blackhole_diffusion import chordless_cycle_basis

edges = {(1, 2), (2, 3), (3, 1)}
cycles = chordless_cycle_basis(edges)

print(cycles)
# [{1, 2, 3}]
```

返回边集合也可使用：

```python
from blackhole_diffusion import chordless_cycle_basis_edges

cycle_edges = chordless_cycle_basis_edges(edges)
```

### 重要说明

本项目保证满秩、无弦与 GF(2) 线性独立性，但**不声称获得严格的全局最小环基（MCB）**。如需必须保证全局总环长最小，应使用精确 MCB 实现并进行独立验证。

完整约束与验证范围见 [`CAUTION.md`](CAUTION.md)。