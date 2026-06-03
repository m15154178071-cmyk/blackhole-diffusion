import sys
import io
if isinstance(sys.stdout, io.TextIOWrapper):
    sys.stdout.reconfigure(encoding='utf-8')
if isinstance(sys.stderr, io.TextIOWrapper):
    sys.stderr.reconfigure(encoding='utf-8')

import networkx as nx
import os
import random
import math

def save_graph(G, filename):
    with open(filename, 'w') as f:
        for u, v in G.edges():
            f.write(f'{u} {v}\n')
    print(f'已生成 {filename}，包含 {G.number_of_nodes()} 个节点和 {G.number_of_edges()} 条边。')

def generate_graphs(target_edges, start_idx):
    os.makedirs('edge', exist_ok=True)
    
    # 1. Erdős-Rényi (随机图)
    # E = p * N * (N-1) / 2 => p = 2E / (N*(N-1))
    N1 = int(math.sqrt(target_edges * 4)) # 适中的边密度
    p1 = target_edges / (N1 * (N1 - 1) / 2)
    G1 = nx.erdos_renyi_graph(N1, p1)
    save_graph(G1, f'edge/edge{start_idx:03d}.txt')

    N2 = int(math.sqrt(target_edges * 10)) # 较稀疏的图
    p2 = target_edges / (N2 * (N2 - 1) / 2)
    G2 = nx.erdos_renyi_graph(N2, p2)
    save_graph(G2, f'edge/edge{start_idx+1:03d}.txt')
    
    # 2. Barabási-Albert (无标度网络)
    # E = N * m
    m3 = 3
    N3 = target_edges // m3
    G3 = nx.barabasi_albert_graph(N3, m3)
    save_graph(G3, f'edge/edge{start_idx+2:03d}.txt')
    
    m4 = 5
    N4 = target_edges // m4
    G4 = nx.barabasi_albert_graph(N4, m4)
    save_graph(G4, f'edge/edge{start_idx+3:03d}.txt')
    
    # 3. Watts-Strogatz (小世界网络)
    # E = N * k / 2 => N = 2E / k
    k5 = 6
    N5 = target_edges * 2 // k5
    G5 = nx.watts_strogatz_graph(N5, k5, 0.1)
    save_graph(G5, f'edge/edge{start_idx+4:03d}.txt')

    k6 = 10
    N6 = target_edges * 2 // k6
    G6 = nx.watts_strogatz_graph(N6, k6, 0.2)
    save_graph(G6, f'edge/edge{start_idx+5:03d}.txt')
    
    # 4. Grid 2D Graph (二维网格图)
    # E 约等于 2 * L * W。假设 L = W, 则 2 * L^2 = E => L = sqrt(E/2)
    L7 = int(math.sqrt(target_edges / 2))
    G7 = nx.grid_2d_graph(L7, L7)
    # 将节点标签重新映射为整数
    G7 = nx.convert_node_labels_to_integers(G7)
    save_graph(G7, f'edge/edge{start_idx+6:03d}.txt')

    L8 = int(math.sqrt(target_edges / 2))
    G8 = nx.grid_2d_graph(L8, L8)
    G8 = nx.convert_node_labels_to_integers(G8)
    # 在网格中添加一些随机的对角线边，使其更复杂杂乱
    nodes = list(G8.nodes())
    for _ in range(target_edges // 10):
        u, v = random.choice(nodes), random.choice(nodes)
        if u != v:
            G8.add_edge(u, v)
    save_graph(G8, f'edge/edge{start_idx+7:03d}.txt')
    
    # 5. Random Regular Graph (随机正则图)
    # E = N * d / 2 => N = 2E / d
    d9 = 4
    N9 = target_edges * 2 // d9
    G9 = nx.random_regular_graph(d9, N9)
    save_graph(G9, f'edge/edge{start_idx+8:03d}.txt')

    d10 = 8
    N10 = target_edges * 2 // d10
    if (N10 * d10) % 2 != 0: N10 += 1
    G10 = nx.random_regular_graph(d10, N10)
    save_graph(G10, f'edge/edge{start_idx+9:03d}.txt')

if __name__ == '__main__':
    for group in range(1, 3):
        target_edges = group * 5000
        start_idx = (group - 1) * 10 + 1
        end_idx = group * 10
        print(f"正在生成约 {target_edges:,} 条边的图数据 ({start_idx:03d}-{end_idx:03d})...")
        generate_graphs(target_edges, start_idx)