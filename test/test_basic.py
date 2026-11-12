#!/usr/bin/env python3
"""
test_basic.py —— Blackhole Diffusion 基础黑盒测试套件

无需任何第三方依赖，纯 Python 标准库 unittest 运行。
运行方式：
    python -m unittest test/test_basic.py
或者在根目录下运行：
    pytest
"""

import os
import sys
import unittest

# 确保能导入上级目录的 blackhole_diffusion
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from blackhole_diffusion import (
    chordless_cycle_basis,
    chordless_cycle_basis_edges,
    get_cycles_results,
)


class TestBlackholeDiffusion(unittest.TestCase):
    """黑盒正确性与拓扑基底测试"""

    def test_empty_graph(self):
        """测试空图"""
        edges = set()
        basis = chordless_cycle_basis(edges)
        self.assertEqual(len(basis), 0)

    def test_tree_graph(self):
        """测试无环树图（环基数必须为 0）"""
        edges = {(1, 2), (2, 3), (2, 4), (4, 5)}
        basis = chordless_cycle_basis(edges)
        self.assertEqual(len(basis), 0)

    def test_single_triangle(self):
        """测试简单三角形"""
        edges = {(1, 2), (2, 3), (3, 1)}
        basis = chordless_cycle_basis(edges)
        self.assertEqual(len(basis), 1)
        self.assertEqual(basis[0], {1, 2, 3})

    def test_k4_complete_graph(self):
        """测试完全图 K4（4 节点 6 条边，理论满秩 = 6 - 4 + 1 = 3）"""
        edges = {
            (1, 2), (2, 3), (3, 4), (4, 1),
            (1, 3), (2, 4)
        }
        basis = chordless_cycle_basis(edges)
        self.assertEqual(len(basis), 3)
        # 每个环均为 3 元三角形无弦环
        for cyc in basis:
            self.assertEqual(len(cyc), 3)

    def test_shared_edge_triangles(self):
        """测试两三角形共享一条公共边"""
        edges = {
            (1, 2), (2, 3), (3, 1),
            (2, 4), (4, 3)
        }
        basis = chordless_cycle_basis(edges)
        self.assertEqual(len(basis), 2)

    def test_chordless_property(self):
        """验证返回的环均为诱导无弦环"""
        edges = {
            (1, 2), (2, 3), (3, 4), (4, 1),
            (1, 3)  # 弦
        }
        basis = chordless_cycle_basis(edges)
        # 4 节点 5 边，理论秩 2，包含 2 个三角形，外圈 4 环有弦被排除
        self.assertEqual(len(basis), 2)
        for cyc in basis:
            self.assertEqual(len(cyc), 3)

    def test_edges_api(self):
        """验证边集合版 API 返回格式"""
        edges = {(1, 2), (2, 3), (3, 1)}
        basis_edges = chordless_cycle_basis_edges(edges)
        self.assertEqual(len(basis_edges), 1)
        self.assertIsInstance(basis_edges[0], frozenset)
        self.assertEqual(len(basis_edges[0]), 3)


if __name__ == "__main__":
    unittest.main()

