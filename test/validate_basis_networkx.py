#!/usr/bin/env python3
"""Validate a node-set cycle-basis file against an input graph using NetworkX.

Expected input format:
  graph file: one undirected edge ``u v`` per line
  cycle file: one cycle's vertex IDs, separated by whitespace, per line

The cycle file format matches the ``out.txt`` files written by benchmark.py.
NetworkX checks graph/cycle structure; a small bitset GF(2) eliminator checks
linear independence of the returned cycle edge sets.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Iterable

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


def validate(graph: nx.Graph, cycles: list[tuple[int, ...]]) -> int:
    components = nx.number_connected_components(graph) if graph.number_of_nodes() else 0
    target_rank = graph.number_of_edges() - graph.number_of_nodes() + components

    # Stable edge positions make each cycle an edge-incidence bit vector.
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

        # An induced subgraph is a chordless cycle iff it is connected and
        # every vertex has induced degree two.
        induced = graph.subgraph(node_set)
        if not nx.is_connected(induced) or any(degree != 2 for _, degree in induced.degree()):
            errors.append(f"{label}: is not a simple chordless cycle in the input graph")
            continue

        vector = 0
        for u, v in induced.edges():
            vector |= 1 << edge_ids[frozenset((u, v))]
        vectors.append(vector)

    actual_rank = gf2_rank(vectors)
    independent = actual_rank == len(vectors)
    full_rank = actual_rank == target_rank

    print(f"Nodes: {graph.number_of_nodes()}")
    print(f"Edges: {graph.number_of_edges()}")
    print(f"Connected components: {components}")
    print(f"Theoretical cycle-space rank (E - V + C): {target_rank}")
    print(f"Cycles read: {len(cycles)}")
    print(f"Structurally valid cycles: {len(vectors)}")
    print(f"GF(2) rank: {actual_rank}")
    print(f"Independent: {'PASS' if independent else 'FAIL'}")
    print(f"Full rank: {'PASS' if full_rank else 'FAIL'}")

    if errors:
        print("Cycle errors:")
        for error in errors:
            print(f"  - {error}")
    passed = not errors and independent and full_rank and len(cycles) == target_rank
    print(f"Overall: {'PASS' if passed else 'FAIL'}")
    return 0 if passed else 1


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate chordless cycle-basis output using NetworkX and GF(2) rank."
    )
    parser.add_argument("graph", type=Path, help="input edge-list file, e.g. edge/edge001.txt")
    parser.add_argument("cycles", type=Path, help="cycle output file, e.g. out.txt")
    args = parser.parse_args()

    try:
        graph = read_graph(args.graph)
        cycles = read_cycles(args.cycles)
    except (OSError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
    return validate(graph, cycles)


if __name__ == "__main__":
    raise SystemExit(main())
