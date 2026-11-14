#!/usr/bin/env python3
"""Validate a node-set cycle-basis file against an input graph using NetworkX.

Expected input format:
  graph file: one undirected edge ``u v`` per line
  cycle file: one cycle's vertex IDs, separated by whitespace, per line

The cycle file format matches the ``out.txt`` files written by benchmark.py.
NetworkX checks graph/cycle structure; a small bitset GF(2) eliminator checks
linear independence of the returned cycle edge sets.

Usage examples:
  python test/validate_basis_networkx.py edge/edge001.txt out.txt
  python test/validate_basis_networkx.py edge/ out/
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Iterable, Iterator

try:
    import networkx as nx
except ImportError as exc:  # pragma: no cover - depends on environment
    raise SystemExit("NetworkX is required. Install it with: pip install networkx") from exc


def read_graph(path: Path) -> nx.Graph:
    graph = nx.Graph()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.partition("#")[0].strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) != 2:
                raise ValueError(f"{path}:{line_number}: expected exactly two node IDs")
            try:
                u, v = map(int, parts)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: node IDs must be integers") from exc
            graph.add_edge(u, v)
    return graph


def read_cycles(path: Path) -> list[tuple[int, ...]]:
    cycles: list[tuple[int, ...]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            line = line.partition("#")[0].strip()
            if not line:
                continue
            try:
                cycle = tuple(map(int, line.split()))
            except ValueError as exc:
                raise ValueError(f"{path}:{line_number}: node IDs must be integers") from exc
            cycles.append(cycle)
    return cycles


def gf2_rank(vectors: Iterable[int]) -> int:
    """Return the binary rank of integer bit vectors using pivot elimination."""
    pivots: dict[int, int] = {}
    rank = 0
    for vector in vectors:
        value = vector
        while value:
            pivot = value.bit_length() - 1
            if pivot in pivots:
                value ^= pivots[pivot]
            else:
                pivots[pivot] = value
                rank += 1
                break
    return rank


def validate(graph: nx.Graph, cycles: list[tuple[int, ...]]) -> tuple[bool, dict[str, object]]:
    components = nx.number_connected_components(graph) if graph.number_of_nodes() else 0
    target_rank = graph.number_of_edges() - graph.number_of_nodes() + components

    edge_ids = {frozenset(edge): i for i, edge in enumerate(graph.edges())}
    vectors: list[int] = []
    seen: set[frozenset[int]] = set()
    errors: list[str] = []

    for index, cycle in enumerate(cycles, 1):
        label = f"cycle {index}"
        if len(cycle) < 3:
            errors.append(f"{label}: needs at least 3 vertices (got {len(cycle)})")
            continue
        if len(set(cycle)) != len(cycle):
            errors.append(f"{label}: contains repeated vertex IDs")
            continue
        node_set = frozenset(cycle)
        if node_set in seen:
            errors.append(f"{label}: duplicate cycle vertex set")
            continue
        seen.add(node_set)
        missing = node_set.difference(graph.nodes)
        if missing:
            errors.append(f"{label}: vertices not present in graph: {sorted(missing)}")
            continue

        induced = graph.subgraph(node_set)
        if not nx.is_connected(induced) or any(degree != 2 for _, degree in induced.degree()):
            errors.append(f"{label}: is not a simple chordless cycle in the input graph")
            continue

        vector = 0
        for u, v in induced.edges():
            edge = frozenset((u, v))
            if edge not in edge_ids:
                edge = frozenset((v, u))
            vector |= 1 << edge_ids[edge]
        vectors.append(vector)

    actual_rank = gf2_rank(vectors)
    independent = actual_rank == len(vectors)
    full_rank = actual_rank == target_rank
    passed = not errors and independent and full_rank and len(cycles) == target_rank

    summary = {
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "components": components,
        "target_rank": target_rank,
        "cycles_read": len(cycles),
        "structurally_valid": len(vectors),
        "gf2_rank": actual_rank,
        "independent": independent,
        "full_rank": full_rank,
        "errors": errors,
        "passed": passed,
    }
    return passed, summary


def match_cycle_file(graph_file: Path, cycles_dir: Path) -> Path | None:
    """Find the matching cycle file for an edge file: e.g. edge001.txt -> out_001.txt."""
    digits = re.search(r"(\d+)", graph_file.name)
    if not digits:
        return None
    suffix = digits.group(1)
    candidates = [
        cycles_dir / f"out_{suffix}.txt",
        cycles_dir / f"out{suffix}.txt",
        cycles_dir / f"basis_{suffix}.txt",
        cycles_dir / f"cycles_{suffix}.txt",
        cycles_dir / f"{graph_file.stem}.txt",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # generic fallback: scan all files for the same numeric suffix
    for candidate in sorted(cycles_dir.glob("*.txt")):
        if suffix in candidate.name:
            return candidate
    return None


def validate_pair(graph_file: Path, cycle_file: Path) -> tuple[bool, dict[str, object]]:
    graph = read_graph(graph_file)
    cycles = read_cycles(cycle_file)
    return validate(graph, cycles)


def iter_graph_cycle_pairs(graph_root: Path, cycle_root: Path) -> Iterator[tuple[Path, Path]]:
    if graph_root.is_file():
        if cycle_root.is_file():
            yield graph_root, cycle_root
        else:
            raise ValueError(f"Cycle file is not a file: {cycle_root}")
        return

    if not graph_root.is_dir() or not cycle_root.is_dir():
        raise ValueError(f"Expected graph and cycle dirs, got {graph_root} and {cycle_root}")

    graph_files = sorted(graph_root.glob("*.txt"))
    if not graph_files:
        graph_files = sorted(graph_root.glob("*.edges"))

    for graph_file in graph_files:
        cycle_file = match_cycle_file(graph_file, cycle_root)
        if cycle_file is None:
            print(f"Skipping {graph_file.name}: no matching cycle file in {cycle_root}")
            continue
        yield graph_file, cycle_file


def print_summary(graph_file: Path, cycle_file: Path, ok: bool, summary: dict[str, object]) -> None:
    print(f"\n=== {graph_file.name} vs {cycle_file.name} ===")
    print(f"Nodes: {summary['nodes']}")
    print(f"Edges: {summary['edges']}")
    print(f"Connected components: {summary['components']}")
    print(f"Theoretical cycle-space rank (E - V + C): {summary['target_rank']}")
    print(f"Cycles read: {summary['cycles_read']}")
    print(f"Structurally valid cycles: {summary['structurally_valid']}")
    print(f"GF(2) rank: {summary['gf2_rank']}")
    print(f"Independent: {'PASS' if summary['independent'] else 'FAIL'}")
    print(f"Full rank: {'PASS' if summary['full_rank'] else 'FAIL'}")
    if summary["errors"]:
        print("Cycle errors:")
        for error in summary["errors"]:
            print(f"  - {error}")
    print(f"Overall: {'PASS' if ok else 'FAIL'}")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Validate chordless cycle-basis output using NetworkX and GF(2) rank. "
            "Either pass a single graph + cycle file, or two directories to loop over all matches."
        )
    )
    parser.add_argument("graph", type=Path, help="input edge-list file or graph directory")
    parser.add_argument("cycles", type=Path, help="cycle output file or cycle directory")
    args = parser.parse_args()

    try:
        if args.graph.is_file() and args.cycles.is_file():
            ok, summary = validate_pair(args.graph, args.cycles)
            print_summary(args.graph, args.cycles, ok, summary)
            return 0 if ok else 1

        results: list[tuple[Path, Path, bool]] = []
        for graph_file, cycle_file in iter_graph_cycle_pairs(args.graph, args.cycles):
            try:
                ok, summary = validate_pair(graph_file, cycle_file)
                results.append((graph_file, cycle_file, ok))
                print_summary(graph_file, cycle_file, ok, summary)
            except (OSError, ValueError) as exc:
                print(f"Error validating {graph_file.name} vs {cycle_file.name}: {exc}", file=sys.stderr)
                results.append((graph_file, cycle_file, False))

        passed = sum(1 for _, _, ok in results if ok)
        total = len(results)
        print(f"\nBatch summary: {passed}/{total} PASS")
        return 0 if passed == total and total > 0 else 1

    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
