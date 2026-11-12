# Changelog / 更新日志

All notable changes to this project will be documented in this file.
本项目的所有重要更新都会记录在此文件中。

The format is based on [Keep a Changelog](https://keepachangelog.com/),
and this project adheres to [Semantic Versioning](https://semver.org/).

---

## [0.1.1] - 2026-11-13

### Added / 新增
- **Standard Unit Tests (`test/test_basic.py`)**: Zero-dependency `unittest` suite covering empty graphs, trees, single triangles, complete graphs (K4), shared edges, chordless verification, and edge API formats.
  - 纯 Python 标准库单元测试，覆盖基础拓扑结构与无弦环基验证。
- **Real Graphs Benchmark Suite (`test/test_real_graphs.py`)**: Automated verification for 10 real topology datasets (Erdős-Rényi, Barabási-Albert, Watts-Strogatz, 2D Grid, Random Regular), asserting 100% full-rank ($|E| - |V| + C$) completion.
  - 真实拓扑自动化测试套件，验证 10 组 5000 边规模经典图模型的满秩与无弦性。
- **Optional Dependencies in `pyproject.toml`**: Added `[project.optional-dependencies] benchmark = ["networkx", "rich", "igraph"]` following PEP 621 standards.
  - 在 `pyproject.toml` 中按规范声明可选基准测试依赖。

### Fixed / 修复
- **Zero-Dependency Decoupling in Core (`blackhole_diffusion.py`)**: Removed external `debug_util` import and embedded an inline silent `Debug` stub to eliminate `ModuleNotFoundError` and keep production execution clean and quiet.
  - 移除核心算法中的外部调试模块依赖，内嵌纯静默桩，杜绝缺失依赖崩溃。
- **Auditor Logic in `benchmark.py`**: Refactored `CycleAuditor` to verify chordless cycles via independent induced subgraph degree and connectivity checks, fixing `TypeError` and aligning with the new refactored structure.
  - 修复 `CycleAuditor` 审计逻辑，基于导出子图独立校验，完美支持三方交叉审计对比。
- **Graceful Fallbacks in `benchmark.py`**: Added safe fallbacks for `rich` and `igraph` to prevent `missing-import` diagnostics and allow execution in clean Python environments without third-party packages.
  - `rich` 与 `igraph` 支持无扩展包环境下的优雅降级，防止 IDE / 静态分析器报红。
- **Standalone Execution Paths**:
  - Added repository root path resolution in `examples/examples_basic_usage.py` so it runs directly without `pip install -e .`.
  - Anchored output path in `test/generate_large_cases.py` to project root `edge/`.
- **Documentation**: Fixed broken relative hyperlink to `examples/examples_basic_usage.py` in `README.md`.
