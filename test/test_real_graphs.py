#!/usr/bin/env python3
"""
test_real_graphs.py —— 真实拓扑图基准测试脚本
运行 edge/ 目录下各随机图拓扑结构并验证：
1. 节点数、边数、连通分支数
2. 理论极小圈基满秩维数 (E - V + C)
3. 算法提取的满秩无弦环数量与最大环长度
4. 运行耗时
"""

import os
import sys
import time

# 导入当前目录上级的 blackhole_diffusion
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from blackhole_diffusion import _load_edges, chordless_cycle_basis


def get_connected_components(nodes, edges):
    adj = {u: set() for u in nodes}
    for u, v in edges:
        adj[u].add(v)
        adj[v].add(u)
    
    visited = set()
    comps = 0
    for n in nodes:
        if n not in visited:
            comps += 1
            stack = [n]
            visited.add(n)
            while stack:
                curr = stack.pop()
                for nxt in adj.get(curr, ()):
                    if nxt not in visited:
                        visited.add(nxt)
                        stack.append(nxt)
    return comps


def test_real_graphs(graph_indices=range(1, 11)):
    edge_dir = os.path.join(ROOT_DIR, "edge")
    
    type_map = {
        1: "Erdős-Rényi (Dense)",
        2: "Erdős-Rényi (Sparse)",
        3: "Barabási-Albert (m=3)",
        4: "Barabási-Albert (m=5)",
        5: "Watts-Strogatz (k=6)",
        6: "Watts-Strogatz (k=10)",
        7: "2D Grid",
        8: "2D Grid + Diagonals",
        9: "Random Regular (d=4)",
        10: "Random Regular (d=8)",
    }

    print(f"{'File':<12} | {'Topology':<22} | {'Nodes':>5} | {'Edges':>5} | {'Theoretical':>11} | {'Basis':>6} | {'MaxLen':>6} | {'Time (s)':>8} | {'Status':<6}")
    print("-" * 95)

    results = []
    for idx in graph_indices:
        fname = f"edge{idx:03d}.txt"
        fpath = os.path.join(edge_dir, fname)
        if not os.path.exists(fpath):
            continue

        edges = _load_edges(fpath)
        nodes = set()
        for u, v in edges:
            nodes.add(u)
            nodes.add(v)
        
        comps = get_connected_components(nodes, edges)
        theoretical_rank = len(edges) - len(nodes) + comps

        t0 = time.perf_counter()
        basis = chordless_cycle_basis(edges)
        dt = time.perf_counter() - t0

        max_len = max((len(c) for c in basis), default=0)
        status = "PASS" if len(basis) == theoretical_rank else f"DIFF({len(basis) - theoretical_rank})"
        topo_name = type_map.get(idx if idx <= 10 else (idx - 10), "Mixed Topology")

        print(f"{fname:<12} | {topo_name:<22} | {len(nodes):>5} | {len(edges):>5} | {theoretical_rank:>11} | {len(basis):>6} | {max_len:>6} | {dt:>7.2f}s | {status:<6}")
        sys.stdout.flush()
        
        results.append({
            "file": fname,
            "topo": topo_name,
            "nodes": len(nodes),
            "edges": len(edges),
            "theoretical": theoretical_rank,
            "basis": len(basis),
            "max_len": max_len,
            "time": dt,
            "status": status,
        })
    return results


if __name__ == "__main__":
    test_real_graphs(range(1, 11))

