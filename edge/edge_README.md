# Edge Datasets / 边表数据集

## Data Format / 数据格式
Each line contains two integers separated by a space, representing an undirected edge:
每行两个整数，用空格分隔，表示一条无向边：
    
```
    u v
```

- `u`, `v`: Node IDs (can start from 0 or 1; continuity not required).
  `u`, `v`：节点编号（从 0 或 1 起始均可，不要求连续）
- Edges are treated as undirected. Duplicate edges and self-loops are automatically handled during loading.
  边视为无向，重复边和自环在读取时会被自动处理
- Encoding: UTF-8.
  编码：UTF-8

## Dataset List / 数据集列表

| File           | Nodes | Edges | Topology Type         |
|----------------|-------|-------|------------------------|
| edge001.txt    | 141   | 5072  | Pure dense 3-cycles    |
| edge002.txt    | 223   | 4997  | 3-cycles + one 4-cycle |
| edge003.txt    | 1666  | 4989  | Mixed 3–7 cycles       |
| ...            | ...   | ...   | ...                    |
| edge020.txt    | 2500  | 10000 | Mixed 3–7 cycles       |

| 文件|节点数|边数|拓扑类型|
| ---|---|---|---|
| edge001.txt|141|5072|纯 3-环稠密|
| edge002.txt|223|4997|3-环 + 1 个 4-环|
| edge003.txt|1666|4989|混合 3-7 环|
| ...|...|...|...|
| edge020.txt|2500|10000|混合 3-7 环|

## Generation Method / 生成方式
Generated using `test/generate_large_cases.py` via five NetworkX random graph models: Erdős-Rényi, Barabási-Albert, Watts-Strogatz, 2D Grid, and Random Regular.

使用 `test/generate_large_cases.py` 通过 NetworkX 的 Erdős-Rényi、Barabási-Albert、Watts-Strogatz、Grid 2D、Random Regular 五种随机图模型合成。

```bash
python test/generate_large_cases.py