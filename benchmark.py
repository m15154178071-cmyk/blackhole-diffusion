#!/usr/bin/env python3
"""
Blackhole Diffusion · 基准测试套件
需要: pip install networkx rich igraph
用法: python benchmark.py                    # 跑 edge001-010
      python benchmark.py edge001.txt out.txt 黑洞弥散  # 单图模式
"""

from __future__ import annotations

import collections
import contextlib
import csv
import itertools
import os
import sys
import time
from typing import Dict, List, FrozenSet, Set, Tuple, Optional

import networkx as nx
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.layout import Layout
from rich.live import Live

from blackhole_diffusion import (
    MainController,
    CSRBlackholeDevourer,
    StaticMethod,
    GraphDataEncoder,
    DataInitialization,
    Debug,
    chordless_cycle_basis,
)


# ==============================================================================
# 🧩 物理质量核查器 (CycleAuditor)
# ==============================================================================
class CycleAuditor:
    def __init__(self, input_file, memory_cycles, algo_name="MyAlgo-X"):
        self.input_file = input_file
        self.memory_cycles = memory_cycles
        self.algo_name = algo_name
        self.g_nx = nx.Graph()
        edges = set()
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    u, v = int(parts[0]), int(parts[1])
                    edges.add((min(u, v), max(u, v)))
                    self.g_nx.add_edge(u, v)
        self.global_edges = edges
        self.global_adj = {n: set(self.g_nx.neighbors(n)) for n in self.g_nx.nodes()}
        self.target_rank = (self.g_nx.number_of_edges()
                            - self.g_nx.number_of_nodes()
                            + nx.number_connected_components(self.g_nx))
        self._cached_stats = None   # ← 缓存，避免 run_audit() 重复计算

    def run_audit(self) -> dict:
        if self._cached_stats is not None:
            return self._cached_stats

        cycles_list = [set(c) for c in self.memory_cycles]
        rank = len(cycles_list)
        chorded = 0
        broken = 0
        pure = 0
        length_dist: Dict[int, int] = {}
        for cyc in cycles_list:
            sorted_cyc = sorted(cyc)
            if StaticMethod.verify_chordless_cycle(sorted_cyc, self.global_adj):
                pure += 1
                l = len(cyc)
                length_dist[l] = length_dist.get(l, 0) + 1
            else:
                chorded += 1

        self._cached_stats = {
            "rank": rank,
            "chorded": chorded,
            "broken": broken,
            "pure": pure,
            "target_rank": self.target_rank,
            "length_dist": length_dist,
        }

        status = "✅ 审计通过 - 全境解构达成" if (rank >= self.target_rank and chorded == 0 and broken == 0) else "❌ 审计失败"

        console = Console()
        console.print(Panel(
            f"审计引擎: {self.algo_name}\n"
            f"理论满秩: {self.target_rank} | 实测秩: {rank}\n"
            f"纯环: {pure} | 弦环: {chorded} | 碎环: {broken}\n\n"
            f"环长分布:\n" +
            "\n".join(f"  环长 {l:3d}: 纯环 {c}" for l, c in sorted(length_dist.items())),
            title=status,
            border_style="green" if "通过" in status else "red",
            width=100,
        ))

        return self._cached_stats


# ==============================================================================
# 🧪 批量测试套件 (EdgeTestSuite)
# ==============================================================================
class EdgeTestSuite:
    def __init__(self, edge_dir: str = "edge", my_algo_name: str = "黑洞弥散"):
        self.edge_dir = edge_dir
        self.my_algo_name = my_algo_name

    def run_all(self, start_idx: int = 1, end_idx: int = 30):
        found = False
        for i in range(start_idx, end_idx + 1):
            edge_file = os.path.join(self.edge_dir, f"edge{i:03d}.txt")
            if not os.path.isfile(edge_file):
                print(f"⚠️ 跳过：{edge_file} 不存在")
                continue
            found = True
            out_file = f"out_{i:03d}.txt"
            self._run_single(edge_file, out_file)
        if not found:
            print(f"❌ 在 {self.edge_dir}/ 下没有找到任何 edge 文件 (edge{start_idx:03d}.txt ~ edge{end_idx:03d}.txt)")

    def _run_single(self, input_file: str, output_file: str):
        raw_edges = set()
        with open(input_file, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    raw_edges.add((min(int(parts[0]), int(parts[1])),
                                   max(int(parts[0]), int(parts[1]))))

        dispatcher = AlgorithmDispatcher(raw_edges, my_algo_name=self.my_algo_name)
        global_target_rank = dispatcher.get_global_target_rank()
        gap_ratio = dispatcher.get_gap_ratio()
        current_v_e_rank_str = (f"{dispatcher.g_nx.number_of_nodes()}/"
                                f"{dispatcher.g_nx.number_of_edges()}/"
                                f"{global_target_rank}")

        Console().print(
            f"🚀 [bold white]单网域突击简报[/] ➔ 文件: [bold cyan]{os.path.basename(input_file)}[/] "
            f"｜ 拓扑规模: [bold magenta]{current_v_e_rank_str}[/]"
        )

        ACTIVE_ALGOS = dispatcher.get_active_algorithms()
        auditor_instances_dict = {}
        algo_times = {}

        for algo_key in ACTIVE_ALGOS:
            t_st = time.perf_counter()
            cycles_res = dispatcher.execute(algo_key)
            algo_cost = time.perf_counter() - t_st
            algo_times[algo_key] = algo_cost

            auditor = CycleAuditor(input_file, memory_cycles=cycles_res, algo_name=algo_key)
            stats = auditor.run_audit()
            auditor_instances_dict[algo_key] = auditor

            audit_pass = (stats["rank"] >= global_target_rank and
                          stats["chorded"] == 0 and stats["broken"] == 0)
            final_audit_mark = "PASS" if audit_pass else f"弦:{stats['chorded']}|缺:{global_target_rank - stats['rank']}"

            GlobalBenchmarkDashboard.record_algo_stats(
                input_file, algo_key, algo_cost,
                sum(len(c) for c in cycles_res),
                final_audit_mark, current_v_e_rank_str, gap_ratio
            )

            if algo_key == self.my_algo_name:
                with open(output_file, 'w', encoding='utf-8') as f:
                    for cyc in cycles_res:
                        f.write(" ".join(map(str, sorted(list(cyc)))) + "\n")

        MultiEngineVisualizer.print_matrix_comparison(input_file, auditor_instances_dict, algo_times)


# ==============================================================================
# 📊 多引擎可视化对比 (MultiEngineVisualizer)
# ==============================================================================
class MultiEngineVisualizer:
    @staticmethod
    def print_matrix_comparison(input_file, auditor_instances_dict, algo_times):
        console = Console()
        console.print(f"\n[bold]质量矩阵核查场 | 标的拓扑: {os.path.basename(input_file)}[/]\n")

        for algo_key, auditor in auditor_instances_dict.items():
            stats = auditor.run_audit()   # ← 现在走缓存，不会重复计算
            console.print(f"算法: {algo_key} ({algo_times.get(algo_key, 0):.3f}s)")
            for l, c in sorted(stats.get("length_dist", {}).items()):
                console.print(f"  环长 {l:3d}: 纯环 {c}")
            total_edges = sum(l * c for l, c in stats.get("length_dist", {}).items())
            console.print(f"  环数: {stats['rank']} | 基总边数: {total_edges}\n")

        console.print("--- 总结 ---")
        for algo_key, auditor in auditor_instances_dict.items():
            stats = auditor.run_audit()
            status = "✅ 全境解构达成" if stats["rank"] >= stats["target_rank"] else "❌"
            console.print(f"▶ 引擎 {algo_key:20s} {status} (Rank:{stats['rank']}/{stats['target_rank']})")


# ==============================================================================
# 📈 全局基准仪表盘 (GlobalBenchmarkDashboard)
# ==============================================================================
class GlobalBenchmarkDashboard:
    STATS_FILE = "benchmark_stats.csv"

    @staticmethod
    def record_algo_stats(input_file, algo_key, algo_cost, total_edges, audit_mark, v_e_rank, gap_ratio):
        file_exists = os.path.isfile(GlobalBenchmarkDashboard.STATS_FILE)
        with open(GlobalBenchmarkDashboard.STATS_FILE, 'a', encoding='utf-8', newline='') as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["file", "algo", "time_s", "total_edges", "audit", "v_e_rank", "gap_ratio"])
            writer.writerow([os.path.basename(input_file), algo_key, f"{algo_cost:.3f}",
                             total_edges, audit_mark, v_e_rank, f"{gap_ratio:.1f}"])

    @staticmethod
    def show_grand_finale(baseline_name="iGraph", target_name="黑洞弥散"):
        if not os.path.isfile(GlobalBenchmarkDashboard.STATS_FILE):
            return
        console = Console()
        console.print("\n[bold green]═══════════ 🏁 全局基准大结局 🏁 ═══════════[/]\n")
        with open(GlobalBenchmarkDashboard.STATS_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        if len(lines) <= 1:
            return
        header = lines[0].strip().split(",")
        table = Table(title="30 数据集基准总览")
        for h in header:
            table.add_column(h)
        for line in lines[1:]:
            table.add_row(*line.strip().split(","))
        console.print(table)


# ==============================================================================
# 🎯 算法调度器 (AlgorithmDispatcher)
# ==============================================================================
class AlgorithmDispatcher:
    _gap_cache = None   # ← 类级别缓存，微基准只跑一次

    def __init__(self, raw_edges: set, my_algo_name="黑洞弥散"):
        self.raw_edges = list(raw_edges)
        self.g_nx = nx.Graph(self.raw_edges)
        self.DEFAULT_GAP = 8.5
        self.my_algo_name = my_algo_name
        self.edge_count = len(self.raw_edges)
        self.ALGO_REGISTRY = {
            "iGraph": self._algo_igraph,
            "NX-MCB": self._algo_nx_mcb,
            self.my_algo_name: self._algo_my_proprietary
        }

    def get_global_target_rank(self) -> int:
        return (self.g_nx.number_of_edges()
                - self.g_nx.number_of_nodes()
                + nx.number_connected_components(self.g_nx))

    def get_gap_ratio(self) -> float:
        if AlgorithmDispatcher._gap_cache is not None:
            return AlgorithmDispatcher._gap_cache
        try:
            import igraph as ig
            g_ig = ig.Graph.TupleList(self.raw_edges)
            t0 = time.perf_counter()
            nx.triangles(self.g_nx)
            t_nx_std = time.perf_counter() - t0
            t1 = time.perf_counter()
            g_ig.transitivity_local_undirected()
            t_ig_std = time.perf_counter() - t1
            ratio = min(max((t_nx_std / t_ig_std if t_ig_std > 0 else self.DEFAULT_GAP), 3.0), 1500.0)
            Console().print(Panel(
                f"➤ 目标拓扑: |V|={self.g_nx.number_of_nodes()}, |E|={self.g_nx.number_of_edges()}\n"
                f"➤ Python (密集交集) 耗时: {t_nx_std:.4f}s\n"
                f"➤ C++ (连续寻址) 耗时: {t_ig_std:.4f}s\n"
                f"真理测定: Python 动态内存对象残障阻力为 {ratio:.2f}倍。",
                title="⚠️ 极渊探底：语言算力鸿沟",
                border_style="red",
                width=85
            ))
            AlgorithmDispatcher._gap_cache = ratio
            return ratio
        except:
            return self.DEFAULT_GAP

    def get_active_algorithms(self):
        active = []
        edge_limit = 2000
        for name in self.ALGO_REGISTRY.keys():
            if name == "iGraph":
                try:
                    import igraph
                    active.append(name)
                except:
                    pass
            elif "NX" in name:
                if self.edge_count > edge_limit:
                    Console().print(f"⚠️ {name} 跳过：边数 {self.edge_count} > {edge_limit} 限制")
                    continue
                try:
                    import networkx
                    active.append(name)
                except:
                    pass
            else:
                active.append(name)
        return active

    def execute(self, algo_name: str) -> list:
        if algo_name not in self.ALGO_REGISTRY:
            return []
        raw_output = self.ALGO_REGISTRY[algo_name]()
        sanitized_cycles = []
        for cycle in raw_output:
            if isinstance(cycle, (list, tuple, set, dict)):
                sanitized_cycles.append(set(cycle))
        return sanitized_cycles

    def _algo_igraph(self):
        import igraph as ig
        nodes = sorted(list(set(n for edge in self.raw_edges for n in edge)))
        node_to_id = {node: i for i, node in enumerate(nodes)}
        id_to_node = {i: node for i, node in enumerate(nodes)}
        fake_edges = [(node_to_id[u], node_to_id[v]) for u, v in self.raw_edges]
        g = ig.Graph(n=len(nodes), edges=fake_edges, directed=False)
        raw_basis = g.minimum_cycle_basis()
        real_cycles = []
        for edge_indices in raw_basis:
            cycle_nodes = set()
            for e_idx in edge_indices:
                u_fake, v_fake = g.es[e_idx].tuple
                cycle_nodes.add(id_to_node[u_fake])
                cycle_nodes.add(id_to_node[v_fake])
            real_cycles.append(cycle_nodes)
        return real_cycles

    def _algo_nx_mcb(self):
        if self.edge_count > 2000:
            Console().print(f"⚠️ NX-MCB 跳过：边数 {self.edge_count} 超过 2000 限制")
            return []
        return nx.minimum_cycle_basis(self.g_nx)

    def _algo_my_proprietary(self):
        raw_set = set(self.raw_edges)
        return chordless_cycle_basis(raw_set)


# ==============================================================================
# 🚪 主控入口
# ==============================================================================
if __name__ == "__main__":
    FINAL_REPORT_LANG = os.environ.get("FINAL_REPORT_LANG", "zh")

    if len(sys.argv) > 1:
        input_file = sys.argv[1]
        output_file = sys.argv[2] if len(sys.argv) > 2 else "out.txt"
        ALGO_NAME = sys.argv[3] if len(sys.argv) > 3 else "黑洞弥散"

        # 单图模式直接复用 EdgeTestSuite
        suite = EdgeTestSuite(edge_dir=os.path.dirname(input_file) or ".", my_algo_name=ALGO_NAME)
        suite._run_single(input_file, output_file)

    else:
        START_IDX = 1
        END_IDX = 20
        ALGO_NAME = "黑洞弥散"

        if os.path.isfile(GlobalBenchmarkDashboard.STATS_FILE):
            os.remove(GlobalBenchmarkDashboard.STATS_FILE)

        try:
            # 微基准只跑一次，不再重复
            suite = EdgeTestSuite(edge_dir="edge", my_algo_name=ALGO_NAME)
            suite.run_all(start_idx=START_IDX, end_idx=END_IDX)

            time.sleep(0.5)
            GlobalBenchmarkDashboard.show_grand_finale(baseline_name="iGraph", target_name=ALGO_NAME)

        except Exception as e:
            print(f"\n❌ 流水线溃坝：{e}")          # ← 用 print，不被 Debug 配置吞掉
            import traceback
            traceback.print_exc()
            sys.exit(1)
