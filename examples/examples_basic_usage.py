"""
Blackhole Diffusion · 基础用法示例

零外部依赖，只需要 Python 3.9+ 标准库。
"""

from blackhole_diffusion import chordless_cycle_basis

# ======================================================
# 示例 1：最简单的三角形
# ======================================================
print("=== 示例 1：三角形 ===")
edges = {(1, 2), (2, 3), (3, 1)}
cycles = chordless_cycle_basis(edges)

print(f"边集：{edges}")
print(f"环基（{len(cycles)} 个环）：")
for cyc in cycles:
    print(f"  {sorted(cyc)}")
print()


# ======================================================
# 示例 2：完全图 K4
# ======================================================
print("=== 示例 2：完全图 K4 ===")
edges = {
    (1, 2), (2, 3), (3, 4), (4, 1),   # 外圈
    (1, 3), (2, 4)                     # 对角线（弦）
}
cycles = chordless_cycle_basis(edges)

print(f"边数：{len(edges)}")
print(f"理论满秩：{len(edges)} - 4 + 1 = {len(edges) - 3}")
print(f"实际环数：{len(cycles)}（全是无弦环）")
for cyc in cycles:
    print(f"  {sorted(cyc)}")
print()


# ======================================================
# 示例 3：两个三角形共享一条边
# ======================================================
print("=== 示例 3：共享边双三角形 ===")
edges = {
    (1, 2), (2, 3), (3, 1),   # 三角形 A
    (2, 4), (4, 3),           # 三角形 B（与 A 共享边 2-3）
}
cycles = chordless_cycle_basis(edges)

print(f"边集：{edges}")
print(f"环基（{len(cycles)} 个环）：")
for cyc in cycles:
    print(f"  {sorted(cyc)}")

print("\n✅ 全部示例运行完毕。")
