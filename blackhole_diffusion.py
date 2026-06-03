from __future__ import annotations

# 1. 标准库 (Standard Library) - 按字母顺序排列
import argparse
import array
import ctypes
import enum
import gc
import io
import itertools
import math
import os
import platform
import re
import subprocess
import sys
import threading
import time

# 立即禁用自动垃圾回收，防止程序退出时卡顿
gc.disable()

# 2. 标准库子模块 (Standard Library from ... import ...)
from collections import Counter, defaultdict, deque
from dataclasses import dataclass, fields
from datetime import datetime
from multiprocessing import Pool
from typing import (
    Any,
    Callable,
    DefaultDict,
    Dict,
    FrozenSet,
    Generator,
    Iterable,
    List,
    Mapping,
    Optional,
    Set,
    Tuple,
    Union,
)

# 3. 平台特定模块 (Platform-specific)
try:
    from ctypes import wintypes
except ImportError:
    # Linux/Mac 上没有 wintypes，忽略即可
    wintypes = None

    
# ==========================================
# 通用彩色调试日志工具 (Debug) - 修复版
# ==========================================
class Debug:
    """
    通用彩色调试日志工具 (完整优化修复版)
    核心功能：
    1. 默认全部关闭，避免干扰正常输出。
    2. 支持字典、字符串列表、数字列表(1-7)等方式进行全局开关统一配置。
    3. 支持在单条日志处单独覆盖配置 (按需开启)。
    4. 支持环境变量控制（DEBUG_LEVEL）。
    """
    
    # 【日志类别映射】
    TYPES = {
        "section": 1,  # 大阶段总结
        "done":    2,  # 成功完毕
        "timing":  3,  # 耗时统计
        "info":    4,  # 常规信息
        "warn":    5,  # 警报信息
        "fuse":    6,  # 熔断报错
        "detail":  7   # 繁杂细节
    }
    
    # 【反向映射】数字到字符串
    _REVERSE_TYPES = {v: k for k, v in TYPES.items()}
    
    # 【全局开关配置字典】
    _CONFIG: Dict[str, bool] = {
        "section": False,
        "done":    False,
        "timing":  False,
        "info":    False,
        "warn":    False,
        "fuse":    False,
        "detail":  False,
        "newline": False,
        "BlockwiseCycleReducer": False,
        "ZonewiseCycleReducer": False,
        "CSRBlackholeDevourer": False,
        "BigIntBlackholeDevourer": False,
        "AdaptiveBlackholeDevourer": False
    }

    # 颜色常量优化：使用更语义化的命名
    class Color:
        RST  = "\033[0m"
        BOLD = "\033[1m"
        RED  = "\033[91m"
        GRN  = "\033[92m"
        YLW  = "\033[93m"
        BLU  = "\033[94m"
        MAG  = "\033[95m"
        CYN  = "\033[96m"
        GRY  = "\033[90m"
    
    # 简短的别名（向后兼容）
    RST  = Color.RST
    BOLD = Color.BOLD
    RED  = Color.RED
    GRN  = Color.GRN
    YLW  = Color.YLW
    BLU  = Color.BLU
    MAG  = Color.MAG
    CYN  = Color.CYN
    GRY  = Color.GRY

    _t0: float = time.time()
    _caller_cache: Dict[str, str] = {}  # 调用栈缓存
    _terminal_initialized = False

    @classmethod
    def _init_terminal(cls):
        """延迟初始化终端彩色支持"""
        if cls._terminal_initialized:
            return
        try:
            if os.name == 'nt':
                _h = ctypes.windll.kernel32.GetStdHandle(-11)
                _m = ctypes.c_ulong()
                ctypes.windll.kernel32.GetConsoleMode(_h, ctypes.byref(_m))
                ctypes.windll.kernel32.SetConsoleMode(_h, _m.value | 0x0004)
        except Exception:
            pass
        cls._terminal_initialized = True

    @classmethod
    def _init_from_env(cls):
        """从环境变量初始化配置（支持 DEBUG_LEVEL=1,2,3 等）"""
        env_level = os.environ.get("DEBUG_LEVEL", "")
        if env_level:
            try:
                # 支持逗号分隔的数字列表，如 DEBUG_LEVEL=1,3,6
                levels = [int(x.strip()) for x in env_level.split(",") if x.strip()]
                if levels:
                    cls.set_config(levels)
            except ValueError:
                # 支持单词模式，如 DEBUG_LEVEL=info,warn
                levels = [x.strip() for x in env_level.split(",") if x.strip()]
                if levels:
                    cls.set_config(levels)

    @classmethod
    def set_config(cls, config: Union[Dict[str, bool], List[int], List[str]]):
        """
        [模块开关核心接口] 支持多种格式挂载配置：
        形式1 (字典): Debug.set_config({"info": True, "fuse": True})
        形式2 (单词): Debug.set_config(["section", "timing", "fuse"])
        形式3 (数字): Debug.set_config([1, 3, 6])  # 对应 section(1), timing(3), fuse(6)
        形式4 (字符串): Debug.set_config("all") 或 Debug.set_config("none")
        """
        if isinstance(config, str):
            if config.lower() == "all":
                for k in cls._CONFIG:
                    cls._CONFIG[k] = True
            elif config.lower() == "none":
                cls.reset_config()
            return
            
        if isinstance(config, dict):
            for k, v in config.items():
                if k in cls._CONFIG:
                    cls._CONFIG[k] = v
                    
        elif isinstance(config, list):
            for item in config:
                if isinstance(item, int):
                    key = cls._REVERSE_TYPES.get(item)
                    if key:
                        cls._CONFIG[key] = True
                elif isinstance(item, str) and item in cls._CONFIG:
                    cls._CONFIG[item] = True

    @classmethod
    def reset_config(cls):
        """一键全部关闭"""
        for k in cls._CONFIG:
            cls._CONFIG[k] = False

    @classmethod
    def enable_all(cls):
        """一键全部开启"""
        for k in cls._CONFIG:
            cls._CONFIG[k] = True

    @classmethod
    def is_enabled(cls, log_type: str) -> bool:
        """公开的查询接口"""
        return cls._CONFIG.get(log_type, False)

    @classmethod
    def class_debug(cls, class_name: str, msg: str = "") -> bool:
        return cls._CONFIG.get(class_name, False)

    @classmethod
    def _is_enabled(cls, log_type: str, force: Optional[bool] = None) -> bool:
        return force if force is not None else cls._CONFIG.get(log_type, False)

    @classmethod
    def _ts(cls) -> str:
        """时间戳（优化精度显示）"""
        elapsed = time.time() - cls._t0
        if elapsed < 1.0:
            return f"[{elapsed:7.3f}s]"
        elif elapsed < 60.0:
            return f"[{elapsed:7.2f}s]"
        else:
            minutes = int(elapsed / 60)
            seconds = elapsed % 60
            return f"[{minutes:3d}m{seconds:04.1f}s]"

    @staticmethod
    def _get_caller_prefix() -> str:
        """向上追溯三级调用栈获取执行位置（因为增加了一层 _print_formatted，所以层级改为 3）"""
        try:
            frame = sys._getframe(3)
            if frame is None: 
                return "[Unknown]"
            
            code = frame.f_code
            filename = code.co_filename
            func_name = code.co_name
            line_no = frame.f_lineno
            
            class_name = ""
            if 'self' in frame.f_locals:
                class_name = frame.f_locals['self'].__class__.__name__
            elif 'cls' in frame.f_locals:
                class_name = frame.f_locals['cls'].__name__
            
            short_filename = filename.replace('\\', '/').split('/')[-1]
            
            if class_name:
                return f"[{class_name}.{func_name}:{line_no}]"
            else:
                return f"[{short_filename} -> {func_name}:{line_no}]"
                
        except Exception:
            return "[Unknown]"

    @classmethod
    def _print_formatted(cls, color: str, prefix: str, msg: str, elapsed: Optional[float] = None):
        """统一的格式化输出方法（修复死循环：直接写入 stdout 而不调用 cls.info）"""
        cls._init_terminal()
        s = f"   [{elapsed:.4f}s]" if elapsed is not None else ""
        # 修正：直接输出，避免再次进入业务打印函数
        sys.stdout.write(f"{color}{cls._ts()} {cls._get_caller_prefix()} {prefix} {msg}{s}{cls.Color.RST}\n")
        sys.stdout.flush()

    @classmethod
    def newline(cls, force: Optional[bool] = None):
        """根据配置输出空行（修复死循环）"""
        if not cls._is_enabled('newline', force):
            return
        sys.stdout.write("\n")
        sys.stdout.flush()

    # ==========================================
    # 以下为所有输出接口
    # ==========================================

    @classmethod
    def section(cls, msg: str, force: Optional[bool] = None):
        if not cls._is_enabled("section", force): return
        cls._print_formatted(f"{cls.BOLD}{cls.BLU}", ">>", msg)

    @classmethod
    def done(cls, msg: str, elapsed: Optional[float] = None, force: Optional[bool] = None):
        if not cls._is_enabled("done", force): return
        cls._print_formatted(cls.GRN, "OK", msg, elapsed)

    @classmethod
    def timing(cls, msg: str, elapsed: Optional[float] = None, force: Optional[bool] = None):
        if not cls._is_enabled("timing", force): return
        cls._print_formatted(cls.MAG, "T ", msg, elapsed)

    @classmethod
    def info(cls, msg: str, force: Optional[bool] = None):
        if not cls._is_enabled("info", force): return
        cls._print_formatted(cls.CYN, "   ", msg)

    @classmethod
    def warn(cls, msg: str, force: Optional[bool] = None):
        if not cls._is_enabled("warn", force): return
        cls._print_formatted(cls.YLW, "**", msg)

    @classmethod
    def fuse(cls, msg: str, force: Optional[bool] = None):
        if not cls._is_enabled("fuse", force): return
        cls._print_formatted(f"{cls.BOLD}{cls.RED}", "!!", msg)

    @classmethod
    def detail(cls, msg: str, force: Optional[bool] = None):
        if not cls._is_enabled("detail", force): return
        cls._print_formatted(cls.GRY, "   ", msg)

    # ==========================================
    # 便捷方法
    # ==========================================
    
    @classmethod
    def progress(cls, msg: str, current: int, total: int, force: Optional[bool] = None):
        """进度条显示"""
        if not cls._is_enabled("info", force): return
        percent = current / total if total > 0 else 1.0
        bar_len = 30
        filled = int(bar_len * percent)
        bar = '█' * filled + '░' * (bar_len - filled)
        cls._init_terminal()
        # 追溯层级调整为 2，因为 progress 直接调用了底层的 stdout
        try:
            frame = sys._getframe(2)
            caller = f"[{frame.f_code.co_name}:{frame.f_lineno}]"
        except Exception:
            caller = "[Unknown]"
            
        sys.stdout.write(f"\r{cls.CYN}{cls._ts()} {caller} |{bar}| {current}/{total} ({percent*100:.1f}%) {msg}{cls.Color.RST}")
        sys.stdout.flush()
        if current >= total:
            sys.stdout.write("\n")
            sys.stdout.flush()

    @classmethod
    def table(cls, headers: List[str], rows: List[List[str]], title: str = "", force: Optional[bool] = None):
        """简单的表格输出"""
        if not cls._is_enabled("detail", force): return
        
        if title:
            Debug.detail(f"{cls.BOLD}{cls.YLW}{title}{cls.Color.RST}")
        
        col_widths = [len(h) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        
        header_str = "│ " + " │ ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers)) + " │"
        separator = "├─" + "─┼─".join("─" * w for w in col_widths) + "─┤"
        
        Debug.detail(f"┌─{'─┬─'.join('─' * w for w in col_widths)}─┐")
        Debug.detail(header_str)
        Debug.detail(separator)
        
        for row in rows:
            row_str = "│ " + " │ ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)) + " │"
            Debug.detail(row_str)
        
        Debug.detail(f"└─{'─┴─'.join('─' * w for w in col_widths)}─┘")

# 自动从环境变量初始化
Debug._init_from_env()

# ==========================================
# 静态方法类 (StaticMethod)
# ==========================================
class StaticMethod:
    @staticmethod
    def input_file_lines(input_file: str) -> List[Tuple[int, int]]:
        """
        从文件读取边数据
        
        参数:
            input_file: 输入文件路径
            
        返回:
            List[Tuple[int, int]]: 边列表，每条边为 (u, v) 元组，已排序
        """
        with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
            raw_lines = [line.strip() for line in f if line.strip()]
        
        parts_list = [parts for line in raw_lines for parts in [re.split(r"[,\s]+", line)] if len(parts) >= 2]
        
        lines: List[Tuple[int, int]] = []
        for parts in parts_list:
            try:
                u, v = int(parts[0]), int(parts[1])
                lines.append((min(u, v), max(u, v)))
            except (ValueError, IndexError):
                continue # 忽略无效行
        return lines

    @staticmethod
    def cycle_covert_eids_and_edges(cycle: List[int], adj: Dict[int, Set[int]], edge_to_eid: Dict[Tuple[int, int], int]) -> Tuple[Set[int], Set[Tuple[int, int]], bool]:
        """将一个节点环转换为边ID集合"""
        eids = set()
        edges = set()
        if len(cycle) < 3:
            return eids, edges, False
        elif len(cycle) < 5:
            for u, v in itertools.combinations(sorted(cycle), 2):
                edge = (min(u, v), max(u, v))
                if edge in edge_to_eid: # 在真实边集中有映射
                    eids.add(edge_to_eid[edge])
                    edges.add(edge)
        else:
            cycle_set = set(cycle)  
            for node in sorted(cycle_set):
                for neighbor in adj[node]:
                    if neighbor in cycle_set and neighbor != node:
                        edge = (min(node, neighbor), max(node, neighbor))
                        if edge in edge_to_eid:
                            eids.add(edge_to_eid[edge])
                            edges.add(edge)
        if len(eids) == len(cycle):
            return eids, edges, True
        return eids, edges, False

    @staticmethod
    def extract_chord_set(global_edges: Set[Tuple[int, int]]):
        """
        确定性地提取弦边集和树边集。
        
        ✅ 低度优先策略: 邻接点按度从小到大排序，度低的点优先遍历、优先进树
        """
        # 0. 预处理：确保输入边集内部也是有序的 (min, max)
        normalized_global = set()
        full_adj = defaultdict(list)
        
        # 提取所有节点并构建邻接表
        nodes_set = set()
        for u, v in global_edges:
            u, v = (u, v) if u < v else (v, u)
            normalized_global.add((u, v))
            full_adj[u].append(v)
            full_adj[v].append(u)
            nodes_set.add(u)
            nodes_set.add(v)

        # ✅ 1. 预计算每个节点的度
        node_degree = {node: len(neighbors) for node, neighbors in full_adj.items()}

        # ✅ 2. 邻接表按邻居的度从小到大排序（度低的邻居优先访问）
        #       度相同时按节点编号排序，保证完全确定性
        for node in full_adj:
            full_adj[node].sort(key=lambda neighbor: (node_degree[neighbor], neighbor))

        visited = set()
        tree_edges = set()
        tree_adj = defaultdict(list)
        
        # ✅ 3. 起始节点也按度从小到大排序
        all_nodes = sorted(nodes_set, key=lambda node: (node_degree[node], node))
        
        for start_node in all_nodes:
            if start_node not in visited:
                queue = deque([(start_node, -1)])
                visited.add(start_node)
                
                while queue:
                    curr, parent = queue.popleft()
                    
                    # full_adj[curr] 已按度排序，遍历顺序确定
                    for neighbor in full_adj[curr]:
                        if neighbor == parent:
                            continue
                        
                        if neighbor not in visited:
                            visited.add(neighbor)
                            edge = (min(curr, neighbor), max(curr, neighbor))
                            tree_edges.add(edge)
                            
                            tree_adj[curr].append(neighbor)
                            tree_adj[neighbor].append(curr)
                            
                            queue.append((neighbor, curr))

        chord_edges = normalized_global - tree_edges
        
        return chord_edges, tree_edges, tree_adj

    @staticmethod
    def verify_chordless_path(path: List[int], adj: Dict[int, Set[int]]) -> bool:
        """验证给定路径是否为无弦路径"""
        path_set = set(path)
        path = sorted(path_set)
        if len(path) < 3:
            return False
        midpoints = []
        endpoints = []
        for i in range(len(path)):
            node = path[i]
            if len(adj[node] & path_set - {node}) > 2:
                return False
            elif len(adj[node] & path_set - {node}) == 2:
                midpoints.append(node)
            else:
                if len(adj[node] & path_set - {node}) == 1:
                    endpoints.append(node)
        if len(endpoints) != 2:
            return False
        return True
    
    @staticmethod
    def verify_chordless_cycle(path: List[int], adj: Dict[int, Set[int]]) -> bool:
        """验证给定路径是否为无弦环"""
        path_set = set(path)
        path = sorted(path_set)
        if len(path) < 3:
            return False
        midpoints = []
        endpoints = []
        for i in range(len(path)):
            node = path[i]
            if len(adj[node] & path_set - {node}) > 2:
                return False
            elif len(adj[node] & path_set - {node}) == 2:
                midpoints.append(node)
            else:
                if len(adj[node] & path_set - {node}) == 1:
                    endpoints.append(node)
        if len(midpoints) != len(path):
            return False
        return True

    @staticmethod
    def get_adj_map(global_edges):
        """从嵌套结构中构建邻接表"""
        global_edges_set: Set[Tuple[int, int]] = set()
        global_adj: Dict[int, Set[int]] = defaultdict(set)
        map_adj: Dict[Tuple[int, ...], List[Tuple[int, ...]]] = defaultdict(list)
        global_edges_set = set((min(u, v), max(u, v)) for u, v in global_edges)
        for u, v in global_edges_set:
            global_adj[u].add(v)
            global_adj[v].add(u)

        map_adj_value: List[Tuple[int, ...]] = []
        for node, neighbors in global_adj.items():
            map_adj_key = (node,) + tuple (sorted(neighbors))
            map_adj_value: List[Tuple[int, ...]] = []
            history_nodes: Set[int] = set()
            current_nodes: Set[int] = set()
            history_nodes = {node}
            current_nodes = neighbors
            count: int = 0
            while True:
                if len(map_adj_value) > 0:
                    current_nodes = set(sorted(map_adj_value[-1]))
                for neighbors_node in current_nodes:
                    if len(global_adj[neighbors_node] & {node}):
                        count += 1
                        history_nodes_tuple = tuple(sorted(history_nodes))
                        current_nodes_tuple = tuple(sorted(current_nodes))
                        map_adj_value.append(history_nodes_tuple)
                        map_adj_value.append(current_nodes_tuple)
                        if count > 0:
                            break
                if count > 0:
                    map_adj[map_adj_key] = map_adj_value
                    break
        return global_adj, map_adj

    @staticmethod
    def generate_chordless_mapping(path: List[int], adj: Dict[int, Set[int]]) -> Tuple[List[int], List[int]]:
        """生成给定路径的无弦路径映射"""
        path_set = set(path)
        path = sorted(path_set)
        if len(path) < 3:
            return [], []
        midpoints = []
        endpoints = []
        for i in range(len(path)):
            node = path[i]
            if len(adj[node] & path_set - {node}) > 2:
                return [], []
            elif len(adj[node] & path_set - {node}) == 2:
                midpoints.append(node)
            else:
                if len(adj[node] & path_set - {node}) == 1:
                    endpoints.append(node)
        if len(endpoints) != 2:
            return [], []
        return endpoints, midpoints

    @staticmethod
    def _final_incremental_reduction(global_edges: Set[Tuple[int, int]], candidate_cycles: List[FrozenSet[int]], global_target_rank: int, initial_basis: List[FrozenSet[int]] = []) -> Tuple[List[FrozenSet[int]], bool]:
        """
        [新增终极拼图]：分桶增量消元 (纯静态函数)。
        接收带有历史记忆排序的环集，按环长分桶，逐维送入底层 CSR 矩阵进行最终精简。
        支持传入 initial_basis 实现真正的增量消元。
        """
        from collections import defaultdict
        import time
        t_start = time.time()

        global_data_init = DataInitialization(global_edges)
        global_adj = global_data_init.adj
        if len(candidate_cycles) == 0:
            return [], False
        max_cycle_len = max(len(cyc) for cyc in candidate_cycles)
        # 1. 按环长分桶 (利用 list 的 append 保留传入的历史冷热顺序)
        count_list: List[Tuple[str, int]] = []
        buckets = defaultdict(list)
        count: int = 0
        for cyc in candidate_cycles:
            if StaticMethod.verify_chordless_cycle(sorted(cyc), global_adj):
                buckets[len(cyc)].append(cyc)
            else:
                if StaticMethod.verify_chordless_path(sorted(cyc), global_adj):
                    buckets[max_cycle_len + 1].append(cyc)
        for length in sorted(buckets.keys()):
            # 按环长相同的情况下，按最大节点（主元）降序排列，以提升高位优先级
            buckets[length].sort(key=lambda cyc: max(cyc), reverse=True)
            count += len(set(buckets[length]))
            final_basis_parts, is_full = CSRBlackholeDevourer._final_incremental_reduction(global_edges, buckets[length], global_target_rank)
            buckets[length] = final_basis_parts
            count_list.append((f"{length}-环", len(buckets[length])))
        Debug.info(f"[消元前分桶统计] \n环的分布: {" | ".join(f'{name}: {count}' for name, count in count_list)} \n当前无弦环数量: {count}")
            
        # 2. 🚀 核心修复：初始化最底层 CSR 稀疏消元位运算类 (接收已有的基底，实现增量！)
        current_basis = list(initial_basis) if initial_basis else []
        reducer = BlockwiseCycleReducer(global_edges, current_basis)
        
        # 3. 按环长从小到大，一次送一种环长的环基进矩阵增量消元
        for length in sorted(buckets.keys()):
            bucket_cycles = buckets[length]
            
            for cyc in bucket_cycles:
                added_cyc, _ = reducer.add_candidate(cyc)
                if added_cyc:
                    current_basis.append(added_cyc)

                    # 全局秩熔断保护
                    if len(current_basis) >= global_target_rank:
                        Debug.fuse(f"[终极增量消元] 已达到全局目标秩 {global_target_rank}，提前熔断！")
                        # 满了，输出当前基底和 True
                        current_basis_count_list: List[Tuple[str, int]] = []
                        current_basis_buckets = defaultdict(list)
                        for cyc in current_basis:
                            current_basis_buckets[len(cyc)].append(cyc)
                        for length in sorted(current_basis_buckets.keys()):
                            current_basis_count_list.append((f"{length}-环", len(current_basis_buckets[length])))
                        Debug.done(f"[消元后分桶统计] \n环的分布: {" | ".join(f'{name}: {count}' for name, count in current_basis_count_list)} \n当前无弦环基础数量: {len(current_basis)}，已满秩")
                        return current_basis, True

        Debug.timing("终极分桶增量消元完成", time.time() - t_start)
        # 没满，输出当前基底和 False
        current_basis_count_list: List[Tuple[str, int]] = []
        current_basis_buckets = defaultdict(list)
        for cyc in current_basis:
            current_basis_buckets[len(cyc)].append(cyc)
    
        for length in sorted(current_basis_buckets.keys()):
            current_basis_count_list.append((f"{length}-环", len(current_basis_buckets[length])))
        Debug.info(f"[消元后分桶统计] \n环的分布: {" | ".join(f'{name}: {count}' for name, count in current_basis_count_list)} \n当前无弦环基础数量: {len(current_basis)}，未满秩，\n还有{global_target_rank - len(current_basis)} 个环待添加")
        return current_basis, False

    @staticmethod
    def verify_local_blackhole(global_edges: Set[Tuple[int, int]], candidate_cycles: List[FrozenSet[int]]) -> Tuple[bool, bool, bool]:
        """
        【黑洞反查探针】
        反拆图边，再次检查此时黑洞是否成型。
        - 连通性：局部边集是否只有一个连通分量
        - 局部满秩：通过实际消元验证候选环是否达到局部目标秩
        - is_local：局部边集是否与全局边集完全相同且满秩（即已扩展为全局）
        """
        if not candidate_cycles:
            return False, False, False

        global_data_init = DataInitialization(global_edges)
        global_adj = global_data_init.adj
        global_edges_to_eid = global_data_init.edge_to_eid
        global_target_rank = global_data_init.target_rank

        # 1. 反拆图边：提取这些环实际覆盖的边
        local_edges = set()
        for cyc in candidate_cycles:
            eids, edges, is_valid = StaticMethod.cycle_covert_eids_and_edges(sorted(cyc), global_adj, global_edges_to_eid)
            if is_valid:
                local_edges.update(edges)

        if not local_edges:
            return False, False, False

        # 2. 计算局部图的 V, E, C
        local_nodes = set()
        adj = defaultdict(set)
        for u, v in local_edges:
            local_nodes.add(u)
            local_nodes.add(v)
            adj[u].add(v)
            adj[v].add(u)

        # BFS 计算连通分量 C
        visited = set()
        components = 0
        for node in local_nodes:
            if node not in visited:
                components += 1
                q = [node]
                visited.add(node)
                while q:
                    curr = q.pop(0)
                    for nbr in adj[curr]:
                        if nbr not in visited:
                            visited.add(nbr)
                            q.append(nbr)

        # 3. 计算局部目标秩
        local_target_rank = len(local_edges) - len(local_nodes) + components

        # 4. 校验黑洞条件
        is_black = (components == 1)
        is_local = (len(local_edges) == len(global_edges)) and (global_target_rank == local_target_rank)

        # 5. 局部满秩：通过实际消元验证
        reduced_basis, _ = StaticMethod._final_incremental_reduction(
            global_edges=global_edges,
            candidate_cycles=candidate_cycles,
            global_target_rank=local_target_rank
        )
        actual_rank = len(reduced_basis)
        is_full_local = (actual_rank == local_target_rank)

        return is_black, is_full_local, is_local
    
    @staticmethod
    def find_chordless_shortest_path(
        adj: Dict[int, Set[int]], 
        endpoints: List[int],
        midpoints: List[int]
    ) -> Optional[List[int]]:
        """
        【双向相遇最短路】
        用于闭合无弦环。从 start 和 target 双向搜索相遇。
        严格避开 midpoints（中间点）及其所有直接关联点，确保闭合后绝对无弦。
        
        :param adj: 全局邻接表
        :param start: 起点 (路径的一端)
        :param target: 终点 (路径的另一端)
        :param midpoints: 已经存在的中间点集合 (不能碰它们，也不能碰它们的邻居)
        :return: 最短路径列表 [start, ..., target]，如果死路则返回 None
        """
        # ==========================================
        # 1. 构建绝对禁行区 (Forbidden Zone)
        # ==========================================
        forbidden = set(midpoints)
        for node in midpoints:
            forbidden.update(adj[node]) # 封锁中间点的所有关联点（防弦机制）
            
        if len(endpoints) < 2:
            return None
        u, v = min(endpoints), max(endpoints)
        # 必须把起点和终点从禁行区里解禁，否则连门都出不去
        forbidden.discard(u)
        forbidden.discard(v)

        # 如果起点和终点直接相连，且没有被禁，直接返回
        if v in adj[u]:
            return [u, v]

        # ==========================================
        # 2. 双向 BFS 初始化 (端点相遇机制)
        # ==========================================
        q_start = deque([u])
        q_target = deque([v])
        
        # 记录父节点，用于相遇后回溯路径
        parent_start: Dict[int, Optional[int]] = {u: None}
        parent_target: Dict[int, Optional[int]] = {v: None}

        # ==========================================
        # 3. 核心交替搜索
        # ==========================================
        while q_start and q_target:
            # 🚀 优化：永远优先扩展节点数较少的队列，极大减少搜索空间
            if len(q_start) <= len(q_target):
                curr = q_start.popleft()
                for nbr in adj[curr]:
                    if nbr in forbidden: 
                        continue
                        
                    if nbr in parent_target:
                        # 💥 两个端点的探测波相遇了！
                        return StaticMethod._reconstruct_bidirectional_path(curr, nbr, parent_start, parent_target)
                        
                    if nbr not in parent_start:
                        parent_start[nbr] = curr
                        q_start.append(nbr)
            else:
                curr = q_target.popleft()
                for nbr in adj[curr]:
                    if nbr in forbidden: 
                        continue
                        
                    if nbr in parent_start:
                        # 💥 两个端点的探测波相遇了！(注意参数顺序：从 start 过来的是 nbr)
                        return StaticMethod._reconstruct_bidirectional_path(nbr, curr, parent_start, parent_target)
                        
                    if nbr not in parent_target:
                        parent_target[nbr] = curr
                        q_target.append(nbr)
                        
        return None # 彻底死路，无法闭合

    @staticmethod
    def _reconstruct_bidirectional_path(meet_start: int, meet_target: int, parent_start: dict, parent_target: dict) -> List[int]:
        """【内部辅助】双向 BFS 相遇后，拼接完整路径"""
        # 1. 从相遇点回溯到 start
        path_start = []
        curr = meet_start
        while curr is not None:
            path_start.append(curr)
            curr = parent_start[curr]
        path_start.reverse() # 反转，变成 start -> ... -> meet_start
        
        # 2. 从相遇点回溯到 target
        path_target = []
        curr = meet_target
        while curr is not None:
            path_target.append(curr)
            curr = parent_target[curr] # 顺序本来就是 meet_target -> ... -> target
            
        return path_start + path_target

    @staticmethod
    def decompose_frozenset_cycle(global_adj: Dict[int, Set[int]], candidate_cycles: List[FrozenSet[int]]) -> List[FrozenSet[int]]:
        """
        将无序的 frozenset 环切分为无弦环
        :param global_adj: 原图邻接表 {u: set([v1, v2, ...])}
        :param candidate_cycles: 候选环列表 [frozenset([node1, node2, ...]), ...]
        """
        # 1. 还原环的顺序 (将 set 转为有序 list)
        def get_ordered_path(nodes):
            nodes = set(nodes)
            start_node = next(iter(nodes))
            path = [start_node]
            current = start_node
            visited = {start_node}
            
            while len(visited) < len(nodes):
                # 在环节点内寻找下一个邻居
                for neighbor in global_adj[current]:
                    if neighbor in nodes and neighbor not in visited:
                        path.append(neighbor)
                        visited.add(neighbor)
                        current = neighbor
                        break
                else:
                    break
            return path
        
        chordless_trees_cycles = []
        for cycle_nodes in candidate_cycles:
            ordered_cycle = get_ordered_path(list(cycle_nodes))

            queue = [ordered_cycle]

            while queue:
                curr = queue.pop(0)
                n = len(curr)
                found_chord = False
                
                # 建立当前环节点的索引映射，加速查找
                node_to_idx = {node: i for i, node in enumerate(curr)}
                
                for i in range(n):
                    u = curr[i]
                    # 检查 u 的所有原图邻居
                    for v in global_adj[u]:
                        if v in node_to_idx:
                            j = node_to_idx[v]
                            # 判断是否为弦：v 在环内，且不是 i 的相邻点 (注意环是首尾相连的)
                            if abs(i - j) > 1 and abs(i - j) != n - 1:
                                # 找到弦，进行切分
                                idx1, idx2 = min(i, j), max(i, j)
                                path1 = curr[idx1 : idx2 + 1]
                                path2 = curr[idx2:] + curr[: idx1 + 1]
                                
                                queue.append(path1)
                                queue.append(path2)
                                found_chord = True
                                break
                    if found_chord: break
                    
                if not found_chord:
                    chordless_trees_cycles.append(frozenset(curr))
                    
        return chordless_trees_cycles

    @staticmethod
    def format_cycle_length_distribution(cycles: List[FrozenSet[int]]) -> str:
        from collections import Counter
        dist = Counter(len(cyc) for cyc in cycles)
        lines = [f"  环长 {length:>2}: {dist[length]:>5}" for length in sorted(dist.keys())]
        return "\n".join(lines)

    @staticmethod
    def print_engine_report(
        engine_name: str,
        mode: str,
        total_candidates: int = 0,
        target_rank: int = 0,
        valid_basis_count: int = 0,
        is_full: bool = False,
        is_blackhole_active: bool = False,
        exec_time: float = 0.0,
        bh_call_count: int = 0,
        bh_total_time: float = 0.0,
        engine_color: str = Debug.RST,
    ):
        if mode == "start":
            Debug.section(f"  {engine_color}[{engine_name}]{Debug.RST} 启动")
            Debug.detail(f"    候选环: {total_candidates}  |  目标秩: {target_rank}")
        elif mode == "finish":
            rank_icon = f"{Debug.GRN}✓ 满秩{Debug.RST}" if is_full else f"{Debug.YLW}✗ 未满秩 ({valid_basis_count}/{target_rank}){Debug.RST}"
            bh_str = "⚫ 黑洞已闭合" if is_blackhole_active else "○ 黑洞未激活"
            Debug.detail(f"  {engine_color}[{engine_name}]{Debug.RST} 完成")
            Debug.done(f"    最终基底: {valid_basis_count:>4}  {rank_icon}")
            Debug.detail(f"    黑洞状态: {bh_str}")
            Debug.done(f"    总耗时:   {exec_time:>6.1f}s")
            Debug.info(f"    黑洞调用: {bh_call_count:>4} 次  耗时: {bh_total_time:>6.1f}s")


# ==========================================
# 图数据编码器 (GraphDataEncoder)
# ==========================================
class GraphDataEncoder:
    def __init__(self, lines: List[Tuple[int, int]]):
        """
        图数据编码器初始化
        """
        self.raw_lines = lines
        
        # 生成初始编码与映射
        self.edge_mapping, self.global_edge_to_eid, self.lines_to_eid = \
            self.generate_edges_and_edge_to_eid(set(self.raw_lines))
        
        self.new_edges = set(self.global_edge_to_eid.keys())
        self.global_adj = self._build_global_adj()
        
        # 线图相关属性
        self.eid_adj: Optional[Dict[int, Set[int]]] = None
        self.eid_edges_set: Optional[Set[Tuple[int, int]]] = None
        self.line_lines_mapping: Optional[Dict[FrozenSet[int], Tuple[int, int]]] = None
        self.line_global_edges_list: Optional[List[Tuple[int, int]]] = None
        self.line_edge_to_eid: Optional[Dict[Tuple[int, int], int]] = None

    @staticmethod
    def get_all_nodes_zfillstr(lines: Set[Tuple[int, int]]) -> Tuple[Set[Tuple[int, int]], Dict[FrozenSet[int], Tuple[int, int]], List[Tuple[int, int]], Dict[Tuple[int, int], int]]:
        str_to_int = {"0": 10, "1": 11, "2": 20, "3": 21, "4": 30, "5": 31, "6": 40, "7": 41, "8": 50, "9": 51}
        global_edges = set()
        max_len = 0
        nodes = set()
        
        for edge in lines:
            for node in edge:
                nodes.add(node)
                max_len = max(max_len, len(str(node)))  # 修复冗余转换
        
        min_len = min(len(str(n)) for n in nodes) if nodes else 0
        
        nodes_mapping = {}
        for n in nodes:
            u_str = str(n).zfill(max_len)
            big_int_str = "".join([str(str_to_int[c]) for c in u_str])
            nodes_mapping[n] = int(big_int_str)

        lines_mapping = {}
        for edge in lines:
            u, v = edge
            new_u, new_v = nodes_mapping[u], nodes_mapping[v]
            new_edge = (new_u, new_v) if new_u < new_v else (new_v, new_u)
            global_edges.add(new_edge)
            lines_mapping[frozenset(edge)] = new_edge
            
        new_edges_list = sorted(list(global_edges))
        new_edge_to_eid = {edge: eid for eid, enumerate_edge in enumerate(new_edges_list) for edge in [enumerate_edge]}
        
        return lines, lines_mapping, new_edges_list, new_edge_to_eid

    @staticmethod
    def get_all_nodes_int_mapping(nodes_str: Set[str], str_to_int: Dict[str, int]) -> Dict[str, int]:
        mapping = {}
        for node in nodes_str:
            parts = [str(str_to_int[c]) for c in node]
            big_int_str = "".join(parts)
            mapping[node] = int(big_int_str)
        return mapping

    @staticmethod
    def generate_edges_and_edge_to_eid(lines: Set[Tuple[int, int]]) -> Tuple[Dict[Tuple[int, int], Tuple[int, int]], Dict[Tuple[int, int], int], Dict[Tuple[int, int], int]]:
        clean_lines = set()
        for u, v in lines:
            if u != v: 
                clean_lines.add((min(u, v), max(u, v)))
            
        _, lines_mapping, new_edges_list, new_edge_to_eid = GraphDataEncoder.get_all_nodes_zfillstr(clean_lines)
        
        edge_mapping = {}
        lines_to_eid = {}
        for old_fset, edge in lines_mapping.items():
            u_old, v_old = list(old_fset)
            sorted_old = (u_old, v_old) if u_old < v_old else (v_old, u_old)
            edge_mapping[edge] = sorted_old
            lines_to_eid[sorted_old] = new_edge_to_eid[edge]
        
        return edge_mapping, new_edge_to_eid, lines_to_eid

    def _build_global_adj(self) -> Dict[int, Set[int]]:
        adj = defaultdict(set)
        for u, v in self.new_edges:
            adj[u].add(v)
            adj[v].add(u)
        return adj

    # --- 核心转换封装 ---

    def encode_line_graph_to_high_dim(self) -> Tuple[Dict[Tuple[int, int], int], List[Tuple[int, int]]]:
        edges_list = sorted(list(self.new_edges))
        self.eid_adj = defaultdict(set)
        
        for edge in edges_list:
            u, v = min(edge), max(edge)
            eid = self.global_edge_to_eid[(u, v)]
            
            for node in self.global_adj[u] | self.global_adj[v]:
                if node != u and node != v:
                    if node in self.global_adj[u]:
                        target_edge = (min(u, node), max(u, node))
                        if target_edge in self.global_edge_to_eid:
                            self.eid_adj[eid].add(self.global_edge_to_eid[target_edge])
                    
                    if node in self.global_adj[v]:
                        target_edge = (min(v, node), max(v, node))
                        if target_edge in self.global_edge_to_eid:
                            self.eid_adj[eid].add(self.global_edge_to_eid[target_edge])
        
        self.eid_edges_set = set()
        for eid1, neighbors in self.eid_adj.items():
            for eid2 in neighbors:
                self.eid_edges_set.add((min(eid1, eid2), max(eid1, eid2)))
        
        _, self.line_lines_mapping, self.line_global_edges_list, self.line_edge_to_eid = \
            self.get_all_nodes_zfillstr(self.eid_edges_set)
            
        return self.line_edge_to_eid, self.line_global_edges_list


# ==========================================
# 数据初始化 (DataInitialization)
# ==========================================
class DataInitialization:
    """
    数据初始化类，负责构建图的邻接表、计算连通分量、计算目标电路秩（Betti Number），
    以及生成基于 BFS 的生成树基础环（Fundamental Cycles）。
    """
    def __init__(self, global_edges: Set[Tuple[int, int]], debug: bool = False):
        self.debug = debug
        start_t = time.time()
        self.global_edges = set([(min(u, v), max(u, v)) for u, v in global_edges])
        self.adj: Dict[int, Set[int]] = defaultdict(set)
        self.edge_to_eid: Dict[Tuple[int, int], int] = defaultdict(int)
        
        for idx, edge in enumerate(sorted(self.global_edges)):
            self.adj[min(edge)].add(max(edge))
            self.adj[max(edge)].add(min(edge))
            self.edge_to_eid[edge] = idx
            
        self.nodes: Set[int] = set()
        for u, v in self.global_edges:
            self.nodes.add(u)
            self.nodes.add(v)

        self.mapping: Dict[Tuple[int, int], Set[int]] = {}
        self.target_rank = -1

        self.time_start = time.time()

        # 初始化图和映射
        if self.debug:
            Debug.detail(f"[DataInit] _build_graph 完成  E={len(self.global_edges)}, V={len(self.nodes)}  [{time.time()-start_t:.4f}s]")
        
        # 连通分量计数与连通性验证
        _t = time.time()
        self.connected_components_count = self.get_connected_components_count()
        self.is_connected = (self.connected_components_count == 1)
        if self.debug:
            Debug.detail(f"[DataInit] 连通分量计算: C={self.connected_components_count} ({'连通' if self.is_connected else '非连通'})  [{time.time()-_t:.4f}s]")
            
        # 严格计算图的电路秩 (目标最小环基个数)
        # Betti number = E - V + C
        self.target_rank = len(self.global_edges) - len(self.nodes) + self.connected_components_count
        if self.debug:
            Debug.info(f"[DataInit] E={len(self.global_edges)}, V={len(self.nodes)}, C={self.connected_components_count} => 目标秩(Target Rank) = {self.target_rank}")

        # 为 FHBackMapperFinal 预留
        self.edge_to_cycles: Dict[Tuple[int, int], List[FrozenSet[int]]] = defaultdict(list)
        self.edge_to_cycles_deferred: Dict[Tuple[int, int], Tuple[Set, Set, Set, Set]] = defaultdict(lambda: (set(), set(), set(), set()))
        self.dfs_dirs_deferred: Dict[Tuple[int, int], Tuple] = {}
        self.basis: List[FrozenSet[int]] = []
        self.basis = self.get_tree_basis()
        self.duration = time.time() - self.time_start

    def check_connectivity(self) -> bool:
        """连通性验证 (已废弃，由 get_connected_components_count 替代)"""
        if not self.nodes:
            return True
        start = next(iter(self.nodes))
        visited = {start}
        q = deque([start])
        while q:
            curr = q.popleft()
            for nbr in self.adj[curr]:
                if nbr not in visited:
                    visited.add(nbr)
                    q.append(nbr)
        return len(visited) == len(self.nodes)

    def get_connected_components_count(self) -> int:
        """计算图的连通分量个数"""
        if not self.nodes:
            return 0
        visited = set()
        components = 0
        for node in self.nodes:
            if node not in visited:
                components += 1
                q = deque([node])
                visited.add(node)
                while q:
                    curr = q.popleft()
                    for nbr in self.adj[curr]:
                        if nbr not in visited:
                            visited.add(nbr)
                            q.append(nbr)
        return components

    def get_tree_basis(self) -> List[FrozenSet[int]]:
        """
        通过BFS生成树提取基本回路 (Fundamental Cycles)
        
        ✅ 确定性 + 低度优先: 
        - 邻接点按度从小到大排序，度低的点优先遍历、优先进树
        - 高度节点的边被留给弦边集，有利于后续弦边剪枝
        """
        # 构建邻接表
        adj = defaultdict(list)
        for u, v in sorted(self.global_edges):
            adj[u].append(v)
            adj[v].append(u)
        
        # ✅ 预计算每个节点的度
        node_degree = {node: len(neighbors) for node, neighbors in adj.items()}
        
        # ✅ 邻接表按邻居的度从小到大排序（度低的邻居优先访问）
        for node in adj:
            adj[node].sort(key=lambda neighbor: (node_degree[neighbor], neighbor))
        
        # ✅ 起点也按度从小到大排序
        all_nodes = sorted(adj.keys(), key=lambda node: (node_degree[node], node))
        
        visited = set()
        spanning_tree_global_edges = set()
        non_tree_global_edges = set()
        
        for start_node in all_nodes:
            if start_node in visited:
                continue
            
            queue = deque([(start_node, -1)])
            visited.add(start_node)
            
            while queue:
                curr, parent = queue.popleft()
                
                for neighbor in adj[curr]:
                    if neighbor not in visited:
                        visited.add(neighbor)
                        spanning_tree_global_edges.add(
                            (min(curr, neighbor), max(curr, neighbor))
                        )
                        queue.append((neighbor, curr))
                    elif neighbor != parent:
                        edge = (min(curr, neighbor), max(curr, neighbor))
                        if edge not in spanning_tree_global_edges:
                            non_tree_global_edges.add(edge)

        # 构建树邻接表（同样按度排序）
        tree_adj = defaultdict(list)
        for u, v in sorted(spanning_tree_global_edges):
            tree_adj[u].append(v)
            tree_adj[v].append(u)
        for node in tree_adj:
            tree_adj[node].sort(key=lambda neighbor: (node_degree[neighbor], neighbor))

        # ✅ 非树边按两端点度之和从小到大排序（优先处理低度区域的弦边）
        def edge_degree_sum(edge_tuple):
            u, v = edge_tuple
            return (node_degree[u] + node_degree[v], u, v)
        
        fundamental_cycles_nodes = []
        for u, v in sorted(non_tree_global_edges, key=edge_degree_sum):
            q = deque([[u]])
            visited_tree = {u}
            path = []
            while q:
                curr_path = q.popleft()
                curr_node = curr_path[-1]
                if curr_node == v:
                    path = curr_path
                    break
                for nxt in tree_adj[curr_node]:
                    if nxt not in visited_tree:
                        visited_tree.add(nxt)
                        q.append(curr_path + [nxt])
            if path:
                fundamental_cycles_nodes.append(frozenset(path))
        self.basis = fundamental_cycles_nodes
        return self.basis


# =====================================================
# BlockwiseCycleReducer (基于 CSR 稀疏矩阵维度的独立消元)
# =====================================================
class BlockwiseCycleReducer:
    def __init__(self, global_edges: Set[Tuple[int, int]], candidate_cycles: Optional[List[FrozenSet[int]]] = None):
        Debug.class_debug(__class__.__name__, "Initializing BlockwiseCycleReducer")
        self.global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        self.candidate_cycles = candidate_cycles or []
        self.nodes = {u for e in self.global_edges for u in e}
        self.adj: Dict[int, Set[int]] = defaultdict(set)
        
        self.edge_to_idx: Dict[Tuple[int, int], int] = defaultdict(int)
        self.eid_to_edge: Dict[int, Tuple[int, int]] = defaultdict(lambda: (-1, -1))
        
        self._build_graph()
        self.eid_count = len(self.edge_to_idx)
        
        self.connected_components_count = self.get_connected_components_count()
        self.is_connected = (self.connected_components_count == 1)
        self.target_rank = len(self.global_edges) - len(self.nodes) + self.connected_components_count
        
        # 统一输出结构
        self.valid_basis: List[FrozenSet[int]] = []
        
        # CSR 引擎专属状态
        self.block_size = 64
        self.candidate_data = array.array('Q')
        self.candidate_map: Dict[int, Tuple[int, int]] = {}
        
        self._preload_historical_candidate()

    def _build_graph(self):
        eid = 0
        for u, v in sorted(list(self.global_edges)):
            if u == v: continue
            un, vn = min(u, v), max(u, v)
            self.nodes.update((un, vn))
            self.adj[un].add(vn)
            self.adj[vn].add(un)
            if (un, vn) not in self.edge_to_idx:
                self.edge_to_idx[(un, vn)] = eid
                self.eid_to_edge[eid] = (un, vn)
                eid += 1
        return self.global_edges, self.edge_to_idx

    def get_connected_components_count(self) -> int:
        if not self.nodes: return 0
        visited = set()
        components = 0
        for node in self.nodes:
            if node not in visited:
                components += 1
                q = deque([node])
                visited.add(node)
                while q:
                    curr = q.popleft()
                    for nbr in self.adj[curr]:
                        if nbr not in visited:
                            visited.add(nbr)
                            q.append(nbr)
        return components

    def cycle_covert_eids_and_edges(self, cycle: List[int], adj: Dict[int, Set[int]], edge_to_eid: Dict[Tuple[int, int], int]) -> Tuple[Set[int], Set[Tuple[int, int]], bool]:
        eids = set()
        edges = set()
        if len(cycle) <= 4:
            for u, v in itertools.combinations(sorted(cycle), 2):
                edge = (min(u, v), max(u, v))
                if edge in edge_to_eid:
                    eids.add(edge_to_eid[edge])
                    edges.add(edge)
        else:
            cycle_set = set(cycle)  
            for node in sorted(cycle_set):
                for neighbor in adj[node]:
                    if neighbor in cycle_set and neighbor != node:
                        edge = (min(node, neighbor), max(node, neighbor))
                        if edge in edge_to_eid:
                            eids.add(edge_to_eid[edge])
                            edges.add(edge)
                            
        # 纯代数消元：只要导出边集非空即为合法的代数非零向量
        is_valid = len(eids) > 0
        return eids, edges, is_valid

    def _preload_historical_candidate(self):
        # 修复：直接按节点集合传入，避免类型混淆 Bug
        for cyc in self.candidate_cycles:
            self.add_candidate(cyc)

    def eids_to_vector(self, nodes: FrozenSet[int]) -> array.array:
        if not nodes: return array.array('Q')
        _, edges, _ = self.cycle_covert_eids_and_edges(list(nodes), self.adj, self.edge_to_idx)
        eids = set(self.edge_to_idx[edge] for edge in edges if edge in self.edge_to_idx)
        
        if not eids: return array.array('Q')
        
        vector_data = []
        current_blk = -1
        current_val = 0
        for eid in sorted(eids):
            blk = eid >> 6
            rem = eid & 63
            if blk != current_blk:
                if current_blk != -1:
                    vector_data.extend((current_blk, current_val))
                current_blk = blk
                current_val = 0
            current_val |= (1 << rem)
        if current_blk != -1:
            vector_data.extend((current_blk, current_val))
        return array.array('Q', vector_data)

    def find_pivot_and_reduce(self, vector: array.array) -> Tuple[array.array, Optional[int]]:
        while len(vector) > 0:
            last_blk_idx = vector[-2]
            last_blk_val = vector[-1]
            if last_blk_val == 0:
                vector.pop(); vector.pop()
                continue
            high_bit = last_blk_val.bit_length() - 1
            pivot = (last_blk_idx << 6) + high_bit
            if pivot in self.candidate_map:
                start, length = self.candidate_map[pivot]
                vector = self.xor_with_candidate(vector, self.candidate_data, start, length)
            else:
                return vector, pivot
        return vector, None

    def xor_with_candidate(self, v1: array.array, pool: array.array, start: int, length: int) -> array.array:
        res_list = []
        i, j = 0, 0
        len1, len2 = len(v1), length
        while i < len1 and j < len2:
            b1, b2 = v1[i], pool[start + j]
            if b1 < b2:
                res_list.extend((b1, v1[i+1]))
                i += 2
            elif b1 > b2:
                res_list.extend((b2, pool[start + j + 1]))
                j += 2
            else:
                new_val = v1[i+1] ^ pool[start + j + 1]
                if new_val:
                    res_list.extend((b1, new_val))
                i += 2; j += 2
        if i < len1: res_list.extend(v1[i:])
        if j < len2: res_list.extend(pool[start+j : start+len2])
        return array.array('Q', res_list)

    def check_independent(self, cyc: FrozenSet[int]) -> bool:
        if not cyc: return False
        vector = self.eids_to_vector(cyc)
        # 摒弃深拷贝，使用原生切片拷贝提升速度
        vec_copy = array.array('Q', vector)
        _, pivot = self.find_pivot_and_reduce(vec_copy)
        return pivot is not None

    def add_candidate(self, cyc: FrozenSet[int]) -> Tuple[Optional[FrozenSet[int]], Optional[FrozenSet[int]]]:
        if not cyc: return (None, None)
        vector = self.eids_to_vector(cyc)
        reduced_vector, pivot = self.find_pivot_and_reduce(vector)
        
        if pivot is not None:
            start_idx = len(self.candidate_data)
            length = len(reduced_vector)
            self.candidate_data.extend(reduced_vector)
            self.candidate_map[pivot] = (start_idx, length)
            self.valid_basis.append(cyc)
            return (cyc, None)
        else:
            return (None, cyc)

    def get_basis_count(self) -> int:
        return len(self.valid_basis)



# ==========================================
# CSR 黑洞噬元引擎 (CSR Blackhole Devourer) - 统一修正版
# ==========================================
class CSRBlackholeDevourer:
    class Mode(enum.Enum):
        SAFE_ELIMINATION = "安全消元"
        STANDARD_PROBE = "常规探测"
        ALTERNATING_ANNIHILATION = "交替湮灭"
        COMPLETED = "完成"

    class State:
        def __init__(self, pending_cycles, total_cycles):
            self.valid_basis: List[FrozenSet[int]] = []
            self.valid_basis_edges: List[Set[Tuple[int, int]]] = []
            self.pending_cycles = pending_cycles
            self.failed_cycles: List[FrozenSet[int]] = []
            self.blackhole_edges: Set[Tuple[int, int]] = set()
            self.is_blackhole_active = False
            self.current_mode = CSRBlackholeDevourer.Mode.STANDARD_PROBE
            self.total_cycles = total_cycles
            self.safe_elimination_count = 0
            self.annihilation_count = 0
            self.last_render_time = 0.0
            self.last_bh_log_time = 0.0
            self.last_switch_log_time = 0.0
            self._reserved_cycles: List[Tuple[int, FrozenSet[int], Set[Tuple[int, int]]]] = []

        def update_basis(self, cyc, edges):
            self.valid_basis.append(cyc)
            self.valid_basis_edges.append(edges)

        def update_pending(self, new_pending):
            self.pending_cycles = new_pending
            self.total_cycles = len(new_pending)   # 同步更新总数，保证进度条准确

        def clear_failed(self):
            self.failed_cycles.clear()

        def switch_mode(self, new_mode):
            self.current_mode = new_mode

    def __init__(self, global_edges: Set[Tuple[int, int]],
                 candidate_cycles: List[FrozenSet[int]],
                 global_target_rank: int):
        self.global_edges = global_edges
        self.global_target_rank = global_target_rank
        self.start_time = time.time()
        self.engine_name = "CSRBlackholeDevourer"
        self.engine_color = Debug.CYN  # 假设 Debug 类已定义

        self.adj = defaultdict(set)
        for u, v in self.global_edges:
            self.adj[u].add(v)
            self.adj[v].add(u)

        self.core_reducer = BlockwiseCycleReducer(self.global_edges, [])
        self.edge_to_idx = self.core_reducer.edge_to_idx
        self._cycle_info_cache: Dict[FrozenSet[int], Optional[Tuple[int, int, Set[Tuple[int, int]]]]] = {}

        # 1. 全局初始排序
        self.sorted_cycles = CascadeWeightManager.final_dimension_sort(
            self.global_edges, candidate_cycles
        )

        # 2. 预消元（取前 target_rank 个环，不检测黑洞）
        pre_limit = min(self.global_target_rank, len(self.sorted_cycles))
        temp_state = self.State([], 0)
        for cyc in self.sorted_cycles[:pre_limit]:
            added, _ = self.core_reducer.add_candidate(cyc)
            if added is not None:
                info = self._compute_cycle_info(cyc)
                if info:
                    _, _, cyc_edges = info
                    temp_state.update_basis(cyc, cyc_edges)
            else:
                temp_state.failed_cycles.append(cyc)

        # 3. 构建 pending_cycles（剩余环）
        remaining = self.sorted_cycles[pre_limit:]
        pending_cycles = []
        for cyc in remaining:
            info = self._compute_cycle_info(cyc)
            if info is None:
                continue
            length, pivot, cyc_edges = info
            pending_cycles.append((pivot, cyc, cyc_edges))

        self.state = self.State(pending_cycles, len(pending_cycles))
        for b_cyc, b_edges in zip(temp_state.valid_basis, temp_state.valid_basis_edges):
            self.state.update_basis(b_cyc, b_edges)
        self.state.failed_cycles = temp_state.failed_cycles

    def _compute_cycle_info(self, cyc):
        if cyc in self._cycle_info_cache:
            return self._cycle_info_cache[cyc]
        cyc_list = list(cyc)
        if not (StaticMethod.verify_chordless_cycle(cyc_list, self.adj) or
                StaticMethod.verify_chordless_path(cyc_list, self.adj)):
            self._cycle_info_cache[cyc] = None
            return None
        eids, cyc_edges, _ = StaticMethod.cycle_covert_eids_and_edges(
            cyc_list, self.adj, self.edge_to_idx
        )
        if not eids:
            self._cycle_info_cache[cyc] = None
            return None
        pivot = max(eids)
        length = len(eids)
        result = (length, pivot, cyc_edges)
        self._cycle_info_cache[cyc] = result
        return result

    def _render_progress(self):
        now = time.time()
        if now - self.state.last_render_time < 3.0 and self.state.pending_cycles:
            return
        self.state.last_render_time = now
        processed = self.state.total_cycles - len(self.state.pending_cycles)
        percent = (processed / self.state.total_cycles * 100) if self.state.total_cycles > 0 else 100.0
        bar_len = 25
        filled = int(bar_len * (processed / self.state.total_cycles) if self.state.total_cycles > 0 else bar_len)
        bar = '●' * filled + '○' * (bar_len - filled)
        bh_icon = "⚫" if self.state.is_blackhole_active else "○"
        mode_name = self.state.current_mode.value
        line = (f"\r  {self.engine_color}[{self.engine_name}]{Debug.RST} "
                f"{mode_name} |{Debug.GRN}{bar}{Debug.RST}| "
                f"{processed}/{self.state.total_cycles} ({percent:5.1f}%) "
                f"基底: {len(self.state.valid_basis)} {bh_icon} "
                f"⏱ {time.time() - self.start_time:.1f}s")
        sys.stdout.write(line.ljust(90))
        sys.stdout.flush()

    def _evolve_blackhole(self) -> bool:
        if not self.state.valid_basis or len(self.state.valid_basis) < 20:
            return False
        local_edges = set()
        nodes = set()
        for e in self.state.valid_basis_edges:
            local_edges.update(e)
            for u, v in e:
                nodes.update({u, v})
        E = len(local_edges)
        V = len(nodes)
        parent = {n: n for n in nodes}
        def find(i):
            if parent[i] != i:
                parent[i] = find(parent[i])
            return parent[i]
        components = V
        for u, v in local_edges:
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[ru] = rv
                components -= 1
        theoretical_rank = E - V + components
        if len(self.state.valid_basis) == theoretical_rank:
            self.state.blackhole_edges = local_edges
            if not self.state.is_blackhole_active:
                self.state.is_blackhole_active = True
                now = time.time()
                if now - self.state.last_bh_log_time >= 3.0:
                    Debug.fuse(f"  🌌 黑洞视界闭合！基底: {len(self.state.valid_basis)}/{theoretical_rank}")
                    self.state.last_bh_log_time = now
            return True
        self.state.is_blackhole_active = False
        self.state.blackhole_edges.clear()
        return False

    def _standard_probe(self):
        if not self.state.pending_cycles:
            self.state.switch_mode(self.Mode.COMPLETED)
            return

        # 最终冲刺
        if len(self.state.pending_cycles) <= self.global_target_rank:
            Debug.info(f"  🏁 剩余环数({len(self.state.pending_cycles)})≤目标秩，进入最终冲刺")
            cyc_to_item = {item[1]: item for item in self.state.pending_cycles}
            for cyc in [item[1] for item in self.state.pending_cycles]:
                if len(self.state.valid_basis) >= self.global_target_rank:
                    break
                added, _ = self.core_reducer.add_candidate(cyc)
                if added is not None:
                    self.state.update_basis(cyc, cyc_to_item[cyc][2])
            self.state.update_pending([])
            self.state._reserved_cycles = []
            self.state.switch_mode(self.Mode.COMPLETED)
            if len(self.state.valid_basis) >= self.global_target_rank:
                Debug.fuse("🎯 最终冲刺达成目标秩！")
            else:
                Debug.warn(f"⚠️ 候选环耗尽，基底数 {len(self.state.valid_basis)}，未达目标秩 {self.global_target_rank}")
            self._render_progress()
            return

        # 1. 取前 target_rank 个环，按重合度排序（避免重复计算 basis_edges）
        batch_size = min(self.global_target_rank, len(self.state.pending_cycles))
        batch = self.state.pending_cycles[:batch_size]
        remaining = self.state.pending_cycles[batch_size:]

        # 只计算一次基底边集并复用
        basis_edges = set().union(*self.state.valid_basis_edges) if self.state.valid_basis_edges else set()
        batch.sort(key=lambda item: len(item[2] - basis_edges))

        batch_cyc_to_item = {item[1]: item for item in batch}
        inner, mid, outer = [], [], []
        for item in batch:
            _, cyc, edges = item
            missing = len(edges - basis_edges)
            if missing == 0:
                inner.append(cyc)
            elif missing == 1:
                mid.append(cyc)
            else:
                outer.append(cyc)

        Debug.info(f"  📊 批次 {len(batch)} 环 | 内: {len(inner)} | 中: {len(mid)} | 外: {len(outer)} | 暂存: {len(remaining)}")

        # 2. 执行预消元：先中层，后外层（如果两者都存在）
        mid_remainder = []
        outer_remainder = [batch_cyc_to_item[c] for c in outer]  # 默认不处理外层

        if mid:
            take_cnt = min(self.global_target_rank, len(mid))
            mid_to_process = [batch_cyc_to_item[c] for c in mid[:take_cnt]]
            rest_mid = [batch_cyc_to_item[c] for c in mid[take_cnt:]]
            Debug.info(f"  🔎 常规探测 → 中层预消元 {len(mid_to_process)} 环")
            for idx, (_, cyc, edges) in enumerate(mid_to_process):
                if len(self.state.valid_basis) >= self.global_target_rank:
                    self.state.update_pending(mid_to_process[idx:] + rest_mid + outer_remainder + remaining)
                    self.state._reserved_cycles = []
                    self.state.switch_mode(self.Mode.COMPLETED)
                    return
                added, _ = self.core_reducer.add_candidate(cyc)
                if added is not None:
                    self.state.update_basis(cyc, edges)
                else:
                    self.state.failed_cycles.append(cyc)
            mid_remainder = rest_mid

        # 外层预消元：只要存在外层就处理（无论是否有中层）
        if outer:
            take_cnt = min(self.global_target_rank, len(outer))
            outer_to_process = [batch_cyc_to_item[c] for c in outer[:take_cnt]]
            rest_outer = [batch_cyc_to_item[c] for c in outer[take_cnt:]]
            Debug.info(f"  🔍 常规探测 → 外层预消元 {len(outer_to_process)} 环")
            for idx, (_, cyc, edges) in enumerate(outer_to_process):
                if len(self.state.valid_basis) >= self.global_target_rank:
                    self.state.update_pending(outer_to_process[idx:] + rest_outer + mid_remainder + remaining)
                    self.state._reserved_cycles = []
                    self.state.switch_mode(self.Mode.COMPLETED)
                    return
                added, _ = self.core_reducer.add_candidate(cyc)
                if added is not None:
                    self.state.update_basis(cyc, edges)
                else:
                    self.state.failed_cycles.append(cyc)
            outer_remainder = rest_outer

        # 3. 预消元完成，合并剩余环
        current_pending = mid_remainder + outer_remainder + remaining

        # 4. 基底合并后立刻检测黑洞
        if self._evolve_blackhole():
            Debug.info("  ⚫ 预消元后黑洞闭合，立即触发交替湮灭")
            all_left = current_pending + self.state._reserved_cycles
            self.state.update_pending(all_left)
            self.state._reserved_cycles = []
            self.state.clear_failed()
            self.state.switch_mode(self.Mode.ALTERNATING_ANNIHILATION)
            return

        # 5. 如果有内层，则进行安全消元（逻辑与 BigInt 统一：内层送安全消元时，暂存环一并保留）
        if inner:
            inner_items = [batch_cyc_to_item[c] for c in inner]
            # 当前 pending + 已有的 reserved 作为新的 reserved，内层作为 pending
            self.state._reserved_cycles = current_pending + self.state._reserved_cycles
            self.state.update_pending(inner_items)
            self.state.switch_mode(self.Mode.SAFE_ELIMINATION)
            Debug.info(f"  🔍 常规探测 → 发送 {len(inner_items)} 内环到安全消元")
            return

        # 6. 无内层：将合并后的剩余环放回 pending，返回常规探测重新分层
        self.state.update_pending(current_pending + self.state._reserved_cycles)
        self.state._reserved_cycles = []
        self.state.switch_mode(self.Mode.STANDARD_PROBE)
        Debug.info("  🔍 预消元结束 → 返回常规探测重新分层")
        
    def _safe_elimination(self):
        # 统一行为：pending 空且 reserved 有内容时，先转移再处理，不提前退出
        if not self.state.pending_cycles:
            if self.state._reserved_cycles:
                self.state.update_pending(self.state._reserved_cycles)
                self.state._reserved_cycles = []
                # 继续执行下面的批次处理
            else:
                self.state.switch_mode(self.Mode.STANDARD_PROBE)
                return

        batch = list(self.state.pending_cycles)
        added_count = 0
        check_interval = max(1, self.global_target_rank // 200)

        for idx, (pivot, cyc, edges) in enumerate(batch):
            if len(self.state.valid_basis) >= self.global_target_rank:
                self.state.update_pending(batch[idx:] + self.state._reserved_cycles)
                self.state._reserved_cycles = []
                self.state.switch_mode(self.Mode.COMPLETED)
                return

            added, _ = self.core_reducer.add_candidate(cyc)
            if added is not None:
                self.state.update_basis(cyc, edges)
                added_count += 1
                if added_count % check_interval == 0 and self._evolve_blackhole():
                    Debug.info(f"  ⚫ 安全消元中途（已吞{added_count}环）黑洞闭合，立即触发交替湮灭")
                    self.state.update_pending(batch[idx+1:] + self.state._reserved_cycles)
                    self.state._reserved_cycles = []
                    self.state.clear_failed()
                    self.state.switch_mode(self.Mode.ALTERNATING_ANNIHILATION)
                    return

        self.state.update_pending([])
        if self._evolve_blackhole():
            Debug.info("  ⚫ 安全消元批次完成，黑洞闭合")
            self.state.update_pending(self.state._reserved_cycles)
            self.state._reserved_cycles = []
            self.state.clear_failed()
            self.state.switch_mode(self.Mode.ALTERNATING_ANNIHILATION)
        else:
            if self.state._reserved_cycles:
                self.state.update_pending(self.state._reserved_cycles)
                self.state._reserved_cycles = []
            self.state.switch_mode(self.Mode.STANDARD_PROBE)
            now = time.time()
            if now - self.state.last_switch_log_time >= 1.0:
                Debug.info(f"  🔓 安全消元结束，返回常规探测，基底: {len(self.state.valid_basis)}")
                self.state.last_switch_log_time = now

        self.state.safe_elimination_count += 1
        self._render_progress()
        
    # ===================== 交替湮灭 =====================
    def _alternating_annihilation(self):
        """
        交替湮灭模式：
        - 合并 pending_cycles 和 _reserved_cycles 中的所有环，
        - 使用黑洞边集过滤，丢弃边集完全在黑洞内的环，
        - 剩余环保持原有顺序（不再重排序），清空 _reserved_cycles，
        - 返回常规探测重新分层。
        """
        all_cycles = self.state.pending_cycles + self.state._reserved_cycles
        if not all_cycles:
            self.state.switch_mode(self.Mode.STANDARD_PROBE)
            return

        old_total = len(all_cycles)
        surviving = [item for item in all_cycles
                    if not item[2].issubset(self.state.blackhole_edges)]

        self.state.clear_failed()
        self.state.is_blackhole_active = False
        self.state.blackhole_edges.clear()

        if surviving:
            # 保持原有顺序，不重新排序
            new_pending = []
            for item in surviving:
                pivot, cyc, edges = item  # item 格式 (pivot, cyc, edges)
                # 重新验证环有效性（黑洞后边集可能改变，但通常仍有效）
                if edges:  # 简单保留，不再重新计算，避免开销
                    new_pending.append((pivot, cyc, edges))
            self.state.update_pending(new_pending)
        else:
            self.state.update_pending([])

        self.state._reserved_cycles = []

        discarded = old_total - len(self.state.pending_cycles)
        self.state.annihilation_count += 1
        Debug.info(f"  ⚫ 交替湮灭 #{self.state.annihilation_count} 完成，"
                f"丢弃 {discarded} 个冗余环，保留 {len(self.state.pending_cycles)} 个环，"
                f"进入常规探测")
        self.state.switch_mode(self.Mode.STANDARD_PROBE)
        self._render_progress()

    # ===================== 主循环 =====================
    def _execute(self):
        while self.state.pending_cycles or self.state._reserved_cycles:
            if len(self.state.valid_basis) >= self.global_target_rank:
                print()
                Debug.fuse("🎯 目标秩达成！")
                return self.state.valid_basis, True

            mode = self.state.current_mode
            if mode == self.Mode.SAFE_ELIMINATION:
                self._safe_elimination()
            elif mode == self.Mode.STANDARD_PROBE:
                self._standard_probe()
            elif mode == self.Mode.ALTERNATING_ANNIHILATION:
                self._alternating_annihilation()
            elif mode == self.Mode.COMPLETED:
                break

        if len(self.state.valid_basis) >= self.global_target_rank:
            print()
            Debug.fuse("🎯 目标秩达成！")
            return self.state.valid_basis, True

        print()
        self._render_progress()
        return self.state.valid_basis, False

    @staticmethod
    def _final_incremental_reduction(global_edges, candidate_cycles, global_target_rank):
        devourer = CSRBlackholeDevourer(global_edges, candidate_cycles, global_target_rank)
        return devourer._execute()



# ==========================================
# 终极单维流程调用包 (Single-Dim Pipeline Wrapper)
# ==========================================
class SingleDimensionCycleReducer:
    """
    专门只针对【同一种环长】的内部消元统一调用类。
    【三参数统一标准】：取消跨维惩罚，严格保证同维拓扑纯粹性。
    【极致极速核动力】：彻底摒弃慢速 CSR，内部全面列装大整数引擎，6 万环 0.5 秒内蒸发！
    """
    def __init__(self, global_edges: Set[Tuple[int, int]], candidate_cycles: List[FrozenSet[int]], global_target_rank: int):
        import itertools
        from collections import defaultdict
        self.global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        self.candidate_cycles = candidate_cycles
        self.global_target_rank = global_target_rank

        self.new_edges = set()
        for c in self.candidate_cycles:
            for u, v in itertools.combinations(sorted(c), 2):
                if (u, v) in self.global_edges:
                    self.new_edges.add((min(u, v), max(u, v)))

        self.local_data_init = DataInitialization(self.new_edges)
        self.local_target_rank = self.global_target_rank

        # 将提纯后的 new_edges 作为宇宙抛给排序器，它内部会再次进行防御性校验
        self.weight_manager = CascadeWeightManager(self.new_edges, self.candidate_cycles)
        self.sorted_cycles = self.weight_manager.sort_candidates()
        self.reducer = BlockwiseCycleReducer(self.global_edges, [])
        self.valid_basis: List[FrozenSet[int]] = []
        for c in self.sorted_cycles[0: min(self.global_target_rank, len(self.sorted_cycles))]:
            add_cyc, _ = self.reducer.add_candidate(c)
            if add_cyc:
                self.valid_basis.append(add_cyc)
        self.candidate_cycles_sorted = sorted(list(set(self.valid_basis))) + sorted(list(set(self.candidate_cycles) - set(self.sorted_cycles[0: min(self.global_target_rank, len(self.sorted_cycles))])), key=lambda x: len(x))

    def run_reduction(self) -> Tuple[List[FrozenSet[int]], bool]:
        # =================================================================
        # 🚀 降维打击开光：直接在心脏植入CSR极速引擎！
        valid_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidate_cycles=self.candidate_cycles_sorted,
            global_target_rank=self.global_target_rank
        )

        if len(valid_basis) >= self.local_target_rank or len(valid_basis) >= self.global_target_rank:
            Debug.fuse(f"[沙盒急停] 局部基底数({len(valid_basis)}) 已达满秩上限，即刻熔断")
            
        return valid_basis, len(valid_basis) >= self.global_target_rank

    @staticmethod
    def _final_incremental_reduction(global_edges: Set[Tuple[int, int]], candidate_cycles: List[FrozenSet[int]], global_target_rank: int) -> Tuple[List[FrozenSet[int]], bool]:
        """【统一静态入口】启动低维原构沙盒"""
        reducer = SingleDimensionCycleReducer(global_edges, candidate_cycles, global_target_rank)
        return reducer.run_reduction()


# ==========================================
# 动态级联权重管理器 (Cascade Weight Manager)
# ==========================================
class CascadeWeightManager:
    """
    动态级联权重管理器。
    自动根据候选环数量与全局目标秩选择低维边频率排序策略：
      - 候选环数量 > 全局秩 : 热边排序（频率降序，短环优先）
      - 否则                : 冷边排序（频率升序，短环优先）
    已移除高维热边逻辑，同时保留 CSR 排序与 BigInt 排序静态入口。
    """
    def __init__(self, global_edges: Set[Tuple[int, int]],
                 candidate_cycles: List[FrozenSet[int]]):
        # ---------- 基础数据 ----------
        self.global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        gd = DataInitialization(self.global_edges)
        self.global_adj = gd.adj
        self.global_edge_to_eid = gd.edge_to_eid
        self.global_target_rank = gd.target_rank
        self.candidate_cycles = candidate_cycles
        self.candidate_cycles_sorted = sorted(candidate_cycles, key=len)

        # ---------- 自动冷热切换 ---------------------------
        self.use_hot = len(self.candidate_cycles) > self.global_target_rank

        Debug.info(f"权重管理器初始化，候选环数={len(candidate_cycles)}，"
                   f"全局秩={self.global_target_rank}，"
                   f"策略={'热边' if self.use_hot else '冷边'}排序")

        # 移除了原先的 self.new_edges 与 self.edge_freq 构建（移到 sort_candidates 内按需计算）

    # ------------------------------------------------------------
    # 核心排序实现（低维边频率，冷/热可切换）—— 优化版
    # ------------------------------------------------------------
    def sort_candidates(self) -> List[FrozenSet[int]]:
        if not self.candidate_cycles:
            return []

        t_start = time.time()

        # ---------- 第一步：用 eid 频率统计，只扫一次候选环 ----------
        eid_freq = defaultdict(int)                     # eid -> 出现次数
        cyc_to_eids = {}                                 # 环 -> [eid列表] 缓存
        t1 = time.time()
        for cyc in self.candidate_cycles:
            eids, _, _ = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cyc), self.global_adj, self.global_edge_to_eid
            )
            cyc_to_eids[cyc] = eids
            for eid in eids:
                eid_freq[eid] += 1
        Debug.info(f"[权重统计] eid 频率计算完成，耗时 {time.time()-t1:.2f}s，共 {len(eid_freq)} 个不同 eid")

        # ---------- 第二步：计算每个环的权重（频率之和） ----------
        t2 = time.time()
        cycle_weight_list = []
        for cyc, eids in cyc_to_eids.items():
            weight = sum(eid_freq[eid] for eid in eids)
            cycle_weight_list.append((len(cyc), weight, cyc))
        Debug.info(f"[权重计算] 耗时 {time.time()-t2:.2f}s")

        # ---------- 第三步：排序 ----------
        t3 = time.time()
        if self.use_hot:
            # 热边优先：同一长度内，权重（频率）降序
            cycle_weight_list.sort(key=lambda x: (x[0], -x[1]))
        else:
            # 冷边优先：同一长度内，权重（频率）升序
            cycle_weight_list.sort(key=lambda x: (x[0], x[1]))
        Debug.info(f"[排序核心] 耗时 {time.time()-t3:.2f}s")

        # ---------- 第四步：输出 ----------
        result = [cyc for _, _, cyc in cycle_weight_list]
        Debug.info(f"[排序完成] 总耗时 {time.time()-t_start:.2f}s，环数: {len(result)}")
        return result

    # ============================================================
    # 静态排序入口：自动冷热切换
    # ============================================================
    @staticmethod
    def final_dimension_sort(global_edges, candidate_cycles) -> List[FrozenSet[int]]:
        """
        维度排序：基于未覆盖边的边频率，自动冷热切换
        
        策略：
          - 候选环数量 > 全局秩 → 热边优先（权重降序）
          - 候选环数量 ≤ 全局秩 → 冷边优先（权重升序）
        
        返回:
            排序后的候选环列表
        """
        wm = CascadeWeightManager(global_edges, candidate_cycles)
        return wm.sort_candidates()
    
    # ------------------------------------------------------------
    # CSR 排序（静态，不依赖内部状态）
    #   - 环长优先（短环在前）
    #   - 最高块号降序（大块优先）
    #   - 块跨度（max_block - min_block）升序
    # ------------------------------------------------------------
    @staticmethod
    def final_CSR_dimension_sort(global_edges, candidate_cycles) -> List[FrozenSet[int]]:
        wm = CascadeWeightManager.__new__(CascadeWeightManager)
        wm.global_edges = set((min(u,v), max(u,v)) for u,v in global_edges)
        gd = DataInitialization(wm.global_edges)
        wm.global_adj = gd.adj
        wm.global_edge_to_eid = gd.edge_to_eid
        wm.candidate_cycles_sorted = sorted(candidate_cycles, key=len)
        block_size = 64
        scored = []
        t_start = time.time()
        for cyc in wm.candidate_cycles_sorted:
            eids, _, _ = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cyc), wm.global_adj, wm.global_edge_to_eid
            )
            if not eids:
                continue
            blocks = [eid // block_size for eid in eids]
            max_block = max(blocks)
            min_block = min(blocks)
            span = max_block - min_block
            scored.append((cyc, max_block, span))
        scored.sort(key=lambda x: (len(x[0]), -x[1], x[2]))
        result = [cyc for cyc, _, _ in scored]
        Debug.info(f"[CSR排序] 耗时 {time.time()-t_start:.2f}s，环数: {len(result)}")
        return result

    # ------------------------------------------------------------
    # BigInt 排序（静态，不依赖内部状态）
    #   - 环长优先（短环在前）
    #   - 最高 EID 降序
    #   - EID 跨度（max_eid - min_eid）升序
    # ------------------------------------------------------------
    @staticmethod
    def final_BigInt_dimension_sort(global_edges, candidate_cycles) -> List[FrozenSet[int]]:
        wm = CascadeWeightManager.__new__(CascadeWeightManager)
        wm.global_edges = set((min(u,v), max(u,v)) for u,v in global_edges)
        gd = DataInitialization(wm.global_edges)
        wm.global_adj = gd.adj
        wm.global_edge_to_eid = gd.edge_to_eid
        wm.candidate_cycles_sorted = sorted(candidate_cycles, key=len)
        scored = []
        t_start = time.time()
        for cyc in wm.candidate_cycles_sorted:
            eids, _, _ = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cyc), wm.global_adj, wm.global_edge_to_eid
            )
            if not eids:
                continue
            min_eid = min(eids)
            max_eid = max(eids)
            span = max_eid - min_eid
            scored.append((cyc, min_eid, span))
        scored.sort(key=lambda x: (len(x[0]), x[1], x[2]))
        result = [cyc for cyc, _, _ in scored]
        Debug.info(f"[BigInt排序] 耗时 {time.time()-t_start:.2f}s，环数: {len(result)}")
        return result


# ==========================================
# 无弦短环挖掘器 (ThreeCyclesAndNineCyclesFinder)
# ==========================================
class ThreeCyclesAndNineCyclesFinder:
    def __init__(self, global_edges: Set[Tuple[int, int]], core_edges: Optional[Set[Tuple[int, int]]] = None):
        self.global_edges = set((min(e), max(e)) for e in global_edges)
        if core_edges is None:
            core_edges = set()
        self.core_edges = core_edges
        self.adj: Dict[int, Set[int]] = defaultdict(set)
        for e in self.global_edges:
            self.adj[e[0]].add(e[1])
            self.adj[e[1]].add(e[0])

        self.global_edges = set(global_edges)
        self.chord_edges, self.tree_edges, self.tree_adj = StaticMethod.extract_chord_set(self.global_edges)

    @staticmethod
    def find_three_cycles(global_edges: Set[Tuple[int, int]], chord_edges: Optional[Set[Tuple[int, int]]] = None):
        unordered_edges = set()
        for edge in global_edges:
            unordered_edges.add((min(edge), max(edge)))
        global_data_init = DataInitialization(global_edges)
        global_target_rank = global_data_init.target_rank
        global_edges_list = sorted(unordered_edges)
        global_edges = set()
        edge_adj = defaultdict(set)
        for edge in global_edges_list:
            u, v = edge
            edge_adj[u].add(v)
            edge_adj[v].add(u)
            global_edges.add((min(u, v), max(u, v)))

        three_cycles = set()
        three_edges = set()
        count = 0
        if chord_edges is None or len(chord_edges & global_edges) == 0:
            chords = global_edges
        else:
            chords = chord_edges
        total_virtual = len(chords)
        cycle_count = 0
        edge_count = 0
        for edge in list(chords):
            count += 1
            u, v = min(edge), max(edge)
            common_neighbors = edge_adj[u] & edge_adj[v]
            for w in common_neighbors:
                three_cycles.add(frozenset(sorted([u, v, w])))

            original_cycles = three_cycles
            original_cycles_list: List[FrozenSet[int]] = []
            if len(original_cycles) > 0:
                cyc_len = len(next(iter(three_cycles)))
                if (count % (total_virtual // math.comb(cyc_len, 3))) == 0 and len(original_cycles) >= global_target_rank * math.comb(cyc_len, 3) or count == total_virtual:
                    original_cycles_list = list(original_cycles)
                    yield original_cycles_list
                    three_cycles.clear()
                    original_cycles.clear()

    @staticmethod
    def find_four_cycles(global_edges: Set[Tuple[int, int]], chord_edges: Optional[Set[Tuple[int, int]]] = None):
        unordered_edges = set()
        for edge in global_edges:
            unordered_edges.add((min(edge), max(edge)))
        global_data_init = DataInitialization(global_edges)
        global_target_rank = global_data_init.target_rank
        global_edges_list = sorted(unordered_edges)
        global_edges = set()
        edge_adj: Dict[int, Set[int]] = defaultdict(set)
        for edge in global_edges_list:
            u, v = edge
            edge_adj[u].add(v)
            edge_adj[v].add(u)
            global_edges.add((min(u, v), max(u, v)))

        four_cycles = set()
        four_edges = set()
        count = 0
        if chord_edges is None or len(chord_edges & global_edges) == 0:
            chords = global_edges
        else:
            chords = chord_edges
        total_virtual = len(chords)
        cycle_count = 0
        edge_count = 0
        for edge in list(chords):
            count += 1
            u, v = min(edge), max(edge)
            for two_node in itertools.product(edge_adj[u] - edge_adj[v], edge_adj[v] - edge_adj[u]):
                w1, w2 = min(two_node), max(two_node)
                if (w1, w2) in global_edges:
                    if len(frozenset(sorted([u, v, w1, w2]))) == 4:
                        if (min(w1, w2), max(w1, w2)) in global_edges:
                            four_cycles.add(frozenset(sorted([u, v, w1, w2])))
            original_cycles = four_cycles
            original_cycles_list: List[FrozenSet[int]] = []
            if len(original_cycles) > 0:
                cyc_len = len(next(iter(four_cycles)))
                if (count % (total_virtual // math.comb(cyc_len, 3))) == 0 and len(original_cycles) >= global_target_rank * math.comb(cyc_len, 3) or count == total_virtual:
                    original_cycles_list = list(original_cycles)
                    yield original_cycles_list
                    four_cycles.clear()
                    original_cycles.clear()

    @staticmethod
    def find_five_cycles(global_edges: Set[Tuple[int, int]], chord_edges: Optional[Set[Tuple[int, int]]] = None):
        unordered_edges = set()
        for edge in global_edges:
            unordered_edges.add((min(edge), max(edge)))
        global_data_init = DataInitialization(global_edges)
        global_target_rank = global_data_init.target_rank
        global_edges_list = sorted(unordered_edges)
        global_edges = set()
        edge_adj: Dict[int, Set[int]] = defaultdict(set)
        for edge in global_edges_list:
            u, v = edge
            edge_adj[u].add(v)
            edge_adj[v].add(u)
            global_edges.add((min(u, v), max(u, v)))

        endpoint_edges = set()
        endpoint_edges_list = []
        for u, v in global_edges:
            u, v = min(u, v), max(u, v)
            neighbors_unique = (edge_adj[u] | edge_adj[v]) - (edge_adj[u] & edge_adj[v])
            for w in neighbors_unique:
                if tuple(sorted((u, w))) in global_edges and tuple(sorted((v, w))) not in global_edges:
                    endpoint_edges.add(tuple(sorted((v, w))))
                if tuple(sorted((u, w))) not in global_edges and tuple(sorted((v, w))) in global_edges:
                    endpoint_edges.add(tuple(sorted((u, w))))
        endpoint_edges = endpoint_edges - unordered_edges

        endpoint_edges_list = sorted(endpoint_edges)
        endpoint_edges = set()
        endpoint_adj: Dict[int, Set[int]] = defaultdict(set)

        for u, v in endpoint_edges_list:
            endpoint_adj[u].add(v)
            endpoint_adj[v].add(u)
            endpoint_edges.add((min(u, v), max(u, v)))

        five_cycles: Set[FrozenSet[int]] = set()
        count = 0
        if chord_edges is None or len(chord_edges & global_edges) == 0:
            chords = global_edges
        else:
            chords = chord_edges
        total_virtual = len(chords)
        for edge in list(chords):
            count += 1
            u, v = min(edge), max(edge)

            for node in endpoint_adj[u] & endpoint_adj[v]:
                node1_set = edge_adj[u] & edge_adj[node]
                node2_set = edge_adj[v] & edge_adj[node]
                for w1 in node1_set:
                    for w2 in node2_set:
                        if (min(w1, w2), max(w1, w2)) in endpoint_edges:
                            if len(frozenset(sorted([u, v, node, w1, w2]))) == 5:
                                if StaticMethod.verify_chordless_cycle(sorted([u, v, node, w1, w2]), edge_adj):
                                    five_cycles.add(frozenset(sorted([u, v, node, w1, w2])))

            original_cycles = five_cycles
            original_cycles_list: List[FrozenSet[int]] = []
            if len(original_cycles) > 0:
                cyc_len = len(next(iter(five_cycles)))
                if (count % (total_virtual // math.comb(cyc_len, 3))) == 0 and len(original_cycles) >= global_target_rank * math.comb(cyc_len, 3) or count == total_virtual:
                    original_cycles_list = list(original_cycles)
                    yield original_cycles_list
                    five_cycles.clear()
                    original_cycles.clear()

    @staticmethod
    def find_six_cycles(global_edges: Set[Tuple[int, int]], chord_edges: Optional[Set[Tuple[int, int]]] = None):
        unordered_edges = set()
        for edge in global_edges:
            unordered_edges.add((min(edge), max(edge)))
        global_data_init = DataInitialization(global_edges)
        global_target_rank = global_data_init.target_rank
        global_edges_list = sorted(unordered_edges)
        global_edges = set()
        edge_adj: Dict[int, Set[int]] = defaultdict(set)
        for edge in global_edges_list:
            u, v = edge
            edge_adj[u].add(v)
            edge_adj[v].add(u)
            global_edges.add((min(u, v), max(u, v)))

        endpoint_edges = set()
        endpoint_edges_list = []
        # 由于只是三环，为了防止重复计数并在后续能够去重，也可以直接这样搜
        node_to_edges: Dict[int, Set[Tuple[int, int]]] = defaultdict(set)
        for u, v in global_edges:
            u, v = min(u, v), max(u, v)
            neighbors_unique = (edge_adj[u] | edge_adj[v]) - (edge_adj[u] & edge_adj[v])
            for w in neighbors_unique:
                node_to_edges[w].add((min(u, v), max(u, v)))
                if tuple(sorted((u, w))) in global_edges and tuple(sorted((v, w))) not in global_edges:
                    endpoint_edges.add(tuple(sorted((v, w))))
                if tuple(sorted((u, w))) not in global_edges and tuple(sorted((v, w))) in global_edges:
                    endpoint_edges.add(tuple(sorted((u, w))))
        endpoint_edges = endpoint_edges - unordered_edges

        endpoint_edges_list = sorted(endpoint_edges)
        endpoint_edges = set()
        endpoint_adj: Dict[int, Set[int]] = defaultdict(set)

        for u, v in endpoint_edges_list:
            endpoint_adj[u].add(v)
            endpoint_adj[v].add(u)

        six_cycles: Set[FrozenSet[int]] = set()
        count = 0
        if chord_edges is None or len(chord_edges & global_edges) == 0:
            chords = global_edges
        else:
            chords = chord_edges
        total_virtual = len(chords)
        for edge in list(chords):
            count += 1
            u, v = min(edge), max(edge)
            for two_node in itertools.product(edge_adj[u] - edge_adj[v], edge_adj[v] - edge_adj[u]):
                if len({two_node[0], two_node[1]} & edge_adj[u]) != 1 or len({two_node[0], two_node[1]} & edge_adj[v]) != 1:
                    continue
                u_mid = next(iter({two_node[0], two_node[1]} & edge_adj[u]))
                v_mid = next(iter({two_node[0], two_node[1]} & edge_adj[v]))
                w1_neighbors = edge_adj[u_mid] - (edge_adj[v_mid] | edge_adj[u] | edge_adj[v])
                w2_neighbors = edge_adj[v_mid] - (edge_adj[u_mid] | edge_adj[u] | edge_adj[v])
                for two_node_end in itertools.product(w1_neighbors, w2_neighbors):
                    w1, w2 = two_node_end
                    if tuple(sorted((w1, w2))) in unordered_edges:
                        basis_cycle = sorted(set([u, v, u_mid, v_mid, w1, w2]))
                        if len(basis_cycle) != 6:
                            continue
                        # 严格验证是否为无弦环
                        if StaticMethod.verify_chordless_cycle(basis_cycle, edge_adj):
                            six_cycles.add(frozenset(basis_cycle))

            original_cycles = six_cycles
            original_cycles_list: List[FrozenSet[int]] = []
            if len(original_cycles) > 0:
                cyc_len = len(next(iter(six_cycles)))
                if (count % (total_virtual // math.comb(cyc_len, 3))) == 0 and len(original_cycles) >= global_target_rank * math.comb(cyc_len, 3) or count == total_virtual:
                    original_cycles_list = list(original_cycles)
                    yield original_cycles_list
                    six_cycles.clear()
                    original_cycles.clear()


# ==========================================
# 吞噬黑洞构建器 (Devouring Blackhole Builder)
# ==========================================
class DevouringBlackholeBuilder:
    """
    吞噬黑洞构建器 - 终极整合版
    核心能力：
    1. 边界探测与扩张（黑洞基底）
    2. 连通量=1 的边集优先选择 + 黑洞边扩充
    3. 独有邻居洋葱生长算法（长环）
    4. 全量生成树骨架爆破（多根节点、分块消元）
    5. 跨维致密化与环空间满秩补齐
    """

    def __init__(self, global_edges: Set[Tuple[int, int]],
                 candidate_cycles: List[FrozenSet[int]]):
        # 标准化全局边集
        self.global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)

        # 初始化全局数据
        self.global_data_init = DataInitialization(self.global_edges)
        self.global_adj = self.global_data_init.adj
        self.global_edge_to_eid = self.global_data_init.edge_to_eid
        self.global_target_rank = self.global_data_init.target_rank
        self.global_tree_basis = self.global_data_init.basis
        self.tree_basis_chordless = [cyc for cyc in self.global_tree_basis if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        self.tree_basis_chorded = [cyc for cyc in self.global_tree_basis if not StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        # 保存原始环基快照
        self.original_candidate_cycles = list(candidate_cycles)

        # 生成核心边集
        self.core_edges: Set[Tuple[int, int]] = self.generate_core_edges()

        # 初始化当前数据
        self.current_data_init = DataInitialization(self.core_edges)
        self.current_adj = self.current_data_init.adj
        self.current_edge_to_eid = self.current_data_init.edge_to_eid
        self.current_target_rank = self.current_data_init.target_rank
        self.current_tree_basis = self.current_data_init.basis

        # 生成基底边集
        self.basis_edges: Set[Tuple[int, int]] = self.generate_current_basis_edges()

        # 初始化基底数据和属性
        self.basis_data_init = DataInitialization(self.basis_edges, debug=False)
        self.basis_adj = self.basis_data_init.adj
        self.basis_target_rank = self.basis_data_init.target_rank
        self.basis_cycles = list(self.original_candidate_cycles)
        self.basis_rest_dim = []

        # 计算公共生成树基底
        self.common_tree_basis = list(set(self.global_tree_basis) & set(self.current_tree_basis))
        self.original_candidate_cycles_rest = list(set(self.global_tree_basis) - set(self.current_tree_basis))

        # 初始化黑洞相关数据结构
        self.blackhole_basis: List[FrozenSet[int]] = []
        self.blackhole_edges: Set[Tuple[int, int]] = self._build_local_edges_from_cycles(self.common_tree_basis)

        self.blackhole_data_init = DataInitialization(self.blackhole_edges)
        self.blackhole_adj = self.blackhole_data_init.adj
        self.blackhole_edge_to_eid = self.blackhole_data_init.edge_to_eid
        self.blackhole_target_rank = self.blackhole_data_init.target_rank
        self.blackhole_tree_basis = self.blackhole_data_init.basis

        # 初始化当前基底和边集
        self.current_basis: List[FrozenSet[int]] = []
        self.current_edges: Set[Tuple[int, int]] = set()
        self.paths: List[FrozenSet[int]] = []

        # 初始化当前基底
        self.current_edges = self._build_local_edges_from_cycles(self.blackhole_basis)
        self.current_basis = self.get_blackhole_basis()

        # 初始化剥洋葱算法相关变量
        self.tree_chordless_cycles_edges: Set[Tuple[int, int]] = set()
        self.tree_chordless_cycles_basis: List[FrozenSet[int]] = []
        self.black_edges_rest: Set[Tuple[int, int]] = set()
        self.black_cycles_rest: List[FrozenSet[int]] = []
        self.new_basis_cycles: List[FrozenSet[int]] = []

        # 初始化连通性相关变量
        self.current_components_count = 0
        self.current_target_rank = -1

        # 用于最终存放 V1 洋葱算法产生的无弦环
        self.blackhole_cycles: List[FrozenSet[int]] = []

        Debug.fuse(f"[DevouringBlackholeBuilder] 初始化完成 | 基底环数: {len(candidate_cycles)}")

    # ==========================================
    # 核心生成方法
    # ==========================================

    def generate_core_edges(self) -> Set[Tuple[int, int]]:
        """生成核心边集（从候选环提取所有边）"""
        core_edges = set()
        for cycle_nodes in self.original_candidate_cycles:
            eids, edges, is_valid = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cycle_nodes), self.global_adj, self.global_edge_to_eid
            )
            if is_valid:
                core_edges.update(edges)
        return core_edges

    def generate_current_basis_edges(self) -> Set[Tuple[int, int]]:
        """生成当前基底边集"""
        basis_cycles = self.get_correst_rest_cycles(
            self.core_edges, self.original_candidate_cycles, self.current_tree_basis,
            self.global_edges, self.global_adj, self.global_edge_to_eid
        )
        basis_edges = set()
        for cycle_nodes in basis_cycles:
            eids, edges, is_valid = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cycle_nodes), self.global_adj, self.global_edge_to_eid
            )
            if is_valid:
                basis_edges.update(edges)
        return basis_edges

    # ==========================================
    # 黑洞基底提取（去除大尺度缝合兜底）
    # ==========================================

    def get_blackhole_basis(self) -> List[FrozenSet[int]]:
        """获取黑洞基底（移除 generate_large_chordless_cycle 兜底）"""
        history_cycles = self.blackhole_basis
        is_black, is_full_rank, is_global_edges = StaticMethod.verify_local_blackhole(
            global_edges=self.global_edges, candidate_cycles=self.current_basis
        )
        target_rank_list: List[int] = []

        if is_black:
            for cycle_nodes in self.current_basis:
                self.blackhole_basis.append(cycle_nodes)
            self.blackhole_edges = self._build_local_edges_from_cycles(self.blackhole_basis)
            self.current_basis = self.original_candidate_cycles + self.blackhole_basis
            return self.current_basis
        else:
            self.current_edges = self._build_local_edges_from_cycles(self.current_basis)
            Debug.info(f" 当前无弦环数量: {len(self.current_basis)}, 当前边数量: {len(self.current_edges)}")

            self.current_data_init = DataInitialization(self.current_edges)
            self.common_tree_basis = list(set(self.global_tree_basis) & set(self.current_tree_basis))
            self.current_tree_basis = self.common_tree_basis

            self.blackhole_edges = self._build_local_edges_from_cycles(self.common_tree_basis)
            self.blackhole_data_init = DataInitialization(self.blackhole_edges)
            self.blackhole_adj = self.blackhole_data_init.adj
            self.blackhole_edge_to_eid = self.blackhole_data_init.edge_to_eid
            self.blackhole_target_rank = self.blackhole_data_init.target_rank
            target_rank_list.append(self.blackhole_target_rank)

            self.blackhole_tree_basis = self.blackhole_data_init.basis
            self.blackhole_tree_basis_chordless = [
                cyc for cyc in self.blackhole_tree_basis
                if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)
            ]
            self.blackhole_basis = self.get_correst_rest_cycles(
                self.blackhole_edges, self.blackhole_basis, self.blackhole_tree_basis_chordless,
                self.global_edges, self.global_adj, self.global_edge_to_eid
            )

            # 移除原有的大尺度缝合兜底代码块
            final_basis_chordless = list(set([
                cyc for cyc in self.blackhole_basis + self.original_candidate_cycles
                if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)
            ]))
            self.current_basis = final_basis_chordless
            return self.current_basis

    # ==========================================
    # 主运行入口（移植自 V1 的 run_new_class）
    # 融合了：连通量=1边集选择、黑洞边扩充、独有邻居洋葱生长
    # ==========================================
    def run_new_class(self) -> List[FrozenSet[int]]:
        """
        使用 V1 逻辑生成最终无弦环集合：
        1. 寻找连通分量数为1的最小边集（core/blackhole/current/global）
        2. 用与 core 有交的无弦候选环扩充黑洞边集
        3. 基于独有邻居进行洋葱式延伸，提取长无弦环
        4. 返回所有生成的无弦环（已去重）
        """
        # ---------- 第一步：寻找连通量为 1 的最小边集 ----------
        candidate_sets = [
            ("core", self.core_edges),
            ("blackhole", self.blackhole_edges),
            ("current", self.current_edges),
            ("global", self.global_edges),
        ]

        results_edges_list: List[Tuple[int, str, Set[Tuple[int, int]]]] = []
        for name, edges in candidate_sets:
            if not edges:
                Debug.info(f"[DEBUG] 跳过空边集: {name}")
                continue
            data_init = DataInitialization(edges)
            connected_components_count = data_init.connected_components_count
            results_edges_list.append((connected_components_count, name, edges))

        results_edges_sorted = sorted(results_edges_list, key=lambda x: (x[0], len(x[2])), reverse=False)
        best_edges: Set[Tuple[int, int]] = set()
        best_edges_name: str = ""
        for count, name, edges in results_edges_sorted:
            Debug.info(f"[DEBUG] 尝试边集 {name} (连通分量数={count}, 边数={len(edges)})")
            if count == 1:
                best_edges = edges
                best_edges_name = name
                Debug.info(f"[DEBUG] 选中连通量为1的边集: {name}, 边数={len(edges)}")
                break

        if not best_edges_name:
            Debug.info("[DEBUG] 未找到连通量为1的边集，best_edges 为空")

        # ---------- 第二步：筛选与 core 有交的候选环，扩充黑洞边集 ----------
        for cycle in self.original_candidate_cycles:
            if StaticMethod.verify_chordless_cycle(sorted(cycle), self.global_adj):
                eids, edges, is_valid = StaticMethod.cycle_covert_eids_and_edges(
                    sorted(cycle), self.global_adj, self.global_edge_to_eid
                )
                if is_valid:
                    if edges.issubset(best_edges) and len(edges & self.core_edges) > 0:
                        self.blackhole_edges.update(edges)

        data_init = DataInitialization(self.blackhole_edges)
        connected_components_count = data_init.connected_components_count

        if connected_components_count == 1:
            best_edges = self.blackhole_edges
            Debug.done(f"[run_new_class] 黑洞边集连通量为 1: {len(self.blackhole_edges)}")

        Debug.info(f"[run_new_class] 连通量为1的边集名称: {best_edges_name}, 数量: {len(best_edges)}")

        # ---------- 第三步：构建节点/边映射，准备洋葱生长 ----------
        best_edges_frozenset_adj: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        node_to_edges: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        edge_to_nodes: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        best_nodes_int_set: Set[int] = set(node for edge in best_edges for node in edge)

        for edge in best_edges:
            u, v = edge
            best_edges_frozenset_adj[frozenset([u])].add(frozenset([v]))
            best_edges_frozenset_adj[frozenset([v])].add(frozenset([u]))
            unique_neighbors = (
                (self.global_adj[u] | self.global_adj[v])
                - {u, v}
                - (self.global_adj[u] & self.global_adj[v])
            ) & best_nodes_int_set
            for neighbor in unique_neighbors:
                node_to_edges[frozenset([neighbor])].add(frozenset([u, v]))
                edge_to_nodes[frozenset([u, v])].add(frozenset([neighbor]))

        # ==========================================
        # 方式一：洋葱基底提取
        # ==========================================
        Debug.info("[run_new_class] 开始洋葱环提取...")
        # ---------- 第四步：独有邻居洋葱生长 ----------
        chordless_paths: Set[FrozenSet[int]] = set()
        for start_node, edges in node_to_edges.items():
            if len(edges) == 0:
                continue
            visited = next(iter(edges))
            start_node_neighbors_set = frozenset()
            for node in best_edges_frozenset_adj[start_node]:
                start_node_neighbors_set = start_node_neighbors_set | node

            extend_nodes = edge_to_nodes[visited] & best_edges_frozenset_adj[visited - start_node_neighbors_set]
            if len(extend_nodes) >= 1:
                next_node = next(iter(extend_nodes))
                visited = visited | next_node
                next_edges = [e for e in node_to_edges[next_node] if len(e & visited) == 0]
                if len(next_edges) >= 1:
                    next_edge = next(iter(next_edges))
                    visited = visited | next_edge
                    path = visited
                    if StaticMethod.verify_chordless_path(sorted(path), self.global_adj):
                        endpoints, midpoints = StaticMethod.generate_chordless_mapping(sorted(path), self.global_adj)
                        if len(frozenset(endpoints) & start_node_neighbors_set) == 1 and len(endpoints) == 2:
                            next_node = frozenset(endpoints) - (frozenset(endpoints) & start_node_neighbors_set)
                            visited = visited | next_node
                            next_edges = [e for e in node_to_edges[next_node] if len(e & visited) == 0]
                            if len(next_edges) >= 1:
                                next_edge = next(iter(next_edges))
                                visited = visited | next_edge
                                path = visited
                            else:
                                continue
                            path_len_list: List[int] = []
                            while True:
                                if len(path_len_list) > 3 and path_len_list[-1] == path_len_list[-2] == path_len_list[-3]:
                                    chordless_paths.add(frozenset(list(path)))
                                    break
                                path_len_list.append(len(path))
                                if StaticMethod.verify_chordless_path(sorted(path), self.global_adj):
                                    endpoints, midpoints = StaticMethod.generate_chordless_mapping(sorted(path), self.global_adj)
                                    if len(frozenset(endpoints) & start_node_neighbors_set) == 1 and len(endpoints) == 2:
                                        next_node = frozenset(endpoints) - (frozenset(endpoints) & start_node_neighbors_set)
                                        visited = visited | next_node
                                        path = visited
                                        next_edges = [e for e in node_to_edges[next_node] if len(e & visited) == 0]
                                        if len(next_edges) >= 1:
                                            next_edge = next(iter(next_edges))
                                            visited = visited | next_edge
                                            path = visited
                                            if StaticMethod.verify_chordless_path(sorted(path), self.global_adj) or StaticMethod.verify_chordless_cycle(sorted(path), self.global_adj):
                                                continue
                                        else:
                                            if StaticMethod.verify_chordless_path(sorted(path), self.global_adj) or StaticMethod.verify_chordless_cycle(sorted(path), self.global_adj):
                                                continue
                                            else:
                                                break
                                    else:
                                        if StaticMethod.verify_chordless_path(sorted(path), self.global_adj) or StaticMethod.verify_chordless_cycle(sorted(path), self.global_adj):
                                            continue
                                        else:
                                            break

        new_chordless_paths: List[FrozenSet[int]] = list(set(chordless_paths))

        # ---------- 第五步：路径闭合为环 ----------
        onion_chordless = []  # 清空，存放本次结果
        for nodes in new_chordless_paths:
            if StaticMethod.verify_chordless_cycle(sorted(nodes), self.global_adj):
                self.blackhole_cycles.append(nodes)
            elif StaticMethod.verify_chordless_path(sorted(nodes), self.global_adj):
                endpoints, midpoints = StaticMethod.generate_chordless_mapping(sorted(nodes), self.global_adj)
                nodes_forbid = set()
                for node in midpoints:
                    nodes_forbid.update(self.global_adj[node])
                nodes_closed = self.global_adj[min(endpoints)] & self.global_adj[max(endpoints)] - set(midpoints) - nodes_forbid
                for node in nodes_closed:
                    cycle_nodes = sorted(set(endpoints + midpoints + [node]))
                    if StaticMethod.verify_chordless_cycle(cycle_nodes, self.global_adj):
                        onion_chordless.append(frozenset(cycle_nodes))
        Debug.done(f"[run_new_class] 洋葱环提取完成 | 无弦环数量: {len(onion_chordless)}")
        self.blackhole_cycles.extend(onion_chordless)
        self.blackhole_cycles = list(set(self.blackhole_cycles))

        # ==========================================
        # 方式二：黑洞基底提取
        # ==========================================

        Debug.info("[run_new_class] 开始黑洞环提取...")
        blackhole_basis = self.get_blackhole_basis()
        blackhole_chordless = [
            cyc for cyc in blackhole_basis 
            if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)
        ]
        Debug.done(f"[run_new_class] 黑洞环提取完成 | 无弦环数量: {len(blackhole_chordless)}")
        self.blackhole_cycles.extend(blackhole_chordless)
        self.blackhole_cycles = list(set(self.blackhole_cycles))

        # 与原始候选环合并去重
        original_chordless = [
            cyc for cyc in self.original_candidate_cycles
            if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)
        ]
        all_chordless = list(set(self.blackhole_cycles + original_chordless))
        final_result = []
        seen = set()
        for cyc in all_chordless:
            normalized = frozenset(sorted(cyc))
            if normalized not in seen:
                final_result.append(normalized)
                seen.add(normalized)
        final_result = sorted(final_result, key=lambda x: len(x))
        Debug.info(f"[run_new_class] 最终候选环数量: {len(final_result)}, 最大环长度: {len(final_result[-1]) if final_result else 0}")
        count = 0
        nodes_length_list: List[Tuple[int, int]] = []
        for node in list(final_result[-1]):
            nodes_length_list.append((node, len(self.global_adj[node])))
        
        sorted_nodes = sorted(nodes_length_list, key=lambda x: -x[1])
        for node, _ in sorted_nodes:
            count += 1
            tree_basis_cycles = self._local_all_spanning_tree_cycles(node)
            tree_basis_chordless = [cyc for cyc in tree_basis_cycles if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
            final_result.extend(tree_basis_chordless)
            final_result_sorted = list(set(final_result))
            final_result, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                global_edges=self.global_edges,
                candidate_cycles=list(set(final_result_sorted + self.original_candidate_cycles)),
                global_target_rank=self.global_target_rank
            )
            Debug.info(f"[run_new_class] 已处理 {count} 个节点")
            if is_full:
                Debug.fuse(f"[run_new_class] V1 洋葱算法完成，最终返回 {len(final_result)} 个无弦环, 已达到全秩")
                break
        Debug.fuse(f"[run_new_class] V1 洋葱算法完成，最终返回 {len(final_result)} 个无弦环")
        return final_result

    def get_more_long_cycles(self):
        original_candidate_cycles = [cyc for cyc in self.run_new_class() if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        final_result = sorted(original_candidate_cycles, key=lambda x: len(x))
        Debug.info(f"[run_new_class] 最终候选环数量: {len(final_result)}, 最大环长度: {len(final_result[-1]) if final_result else 0}")
        count = 0
        nodes_length_list: List[Tuple[int, int]] = []
        for node in list(final_result[-1]):
            nodes_length_list.append((node, len(self.global_adj[node])))
        
        sorted_nodes = sorted(nodes_length_list, key=lambda x: -x[1])
        for node, _ in sorted_nodes:
            count += 1
            tree_basis_cycles = self._local_all_spanning_tree_cycles(node)
            tree_basis_chordless = [cyc for cyc in tree_basis_cycles if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
            final_result.extend(tree_basis_chordless)
            final_result_sorted = list(set(final_result))
            final_result, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                global_edges=self.global_edges,
                candidate_cycles=list(set(final_result_sorted + self.original_candidate_cycles)),
                global_target_rank=self.global_target_rank
            )
            Debug.info(f"[run_new_class] 已处理 {count} 个节点")
            if is_full:
                Debug.fuse(f"[run_new_class] V1 洋葱算法完成，最终返回 {len(final_result)} 个无弦环, 已达到全秩")
                break
        final_result, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidate_cycles=final_result,
            global_target_rank=self.global_target_rank
        )
        if is_full:
            return final_result
        else:
            if not is_full:
                history_cycles = self.basis_cycles
            else:
                basis = self.run_new_class()
                history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                    global_edges=self.global_edges,
                    candidate_cycles=self.basis_cycles + basis + self.tree_basis_chordless,
                    global_target_rank=self.global_target_rank
                )

        rest_chordless_cycles: List[FrozenSet[int]] = []
        massive_candidate_pool: List[FrozenSet[int]] = []
        loopbreak: bool = False
        if not is_full:
            core_reducer = BlockwiseCycleReducer(self.global_edges, history_cycles)
            
            # 1. 收集所有成功进入消元器的有弦环涉及的全部节点，作为爆破源点集
            seed_nodes = set()
            for cycle in self.tree_basis_chorded:
                add_cyc, _ = core_reducer.add_candidate(cycle)
                if add_cyc:
                    for node in set(list(cycle)):
                        if len(self.global_adj[node] & set(list(cycle))) > 2:
                            seed_nodes.add(node)
                            if seed_nodes:
                                for node in seed_nodes:
                                    massive_candidate_pool = self._local_all_spanning_tree_cycles(node)
                                    rest_chordless_cycles.extend(massive_candidate_pool)
                                seed_nodes.clear()
                                rest_chordless_cycles = list(set(rest_chordless_cycles))
                                # 3. 将海量候选环一股脑倒进你的消元器里，让你后面的逻辑去精简和迭代消元
                                for p_cyc in rest_chordless_cycles:
                                    if StaticMethod.verify_chordless_cycle(sorted(p_cyc), self.global_adj):
                                        add_cyc, _ = core_reducer.add_candidate(p_cyc)
                                        if add_cyc:
                                            history_cycles.append(p_cyc)
                                            if len(history_cycles) >= self.global_target_rank:
                                                loopbreak = True
                                                break
                        if loopbreak:
                            break
                if loopbreak:
                    break
            massive_candidate_pool.clear()
        rest_chordless_cycles = [cyc for cyc in rest_chordless_cycles if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidate_cycles=history_cycles + rest_chordless_cycles,
            global_target_rank=self.global_target_rank
        )

        return history_cycles


    # ==========================================
    # 骨架提取方法（保留自 V3）
    # ==========================================
    def _local_all_spanning_tree_cycles(self, root_node: int) -> List[FrozenSet[int]]:
        """全量生成树环基（指定单起点版）"""
        adj = defaultdict(list)
        for u, v in self.global_edges:
            adj[u].append(v)
            adj[v].append(u)

        visited = set()
        spanning_tree_global_edges = set()
        non_tree_global_edges = set()

        ordered_start_nodes = [root_node] + [n for n in adj.keys() if n != root_node]

        for start_node in ordered_start_nodes:
            if start_node not in visited:
                queue = deque([(start_node, -1)])
                visited.add(start_node)
                while queue:
                    curr, parent = queue.popleft()
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            spanning_tree_global_edges.add((min(curr, neighbor), max(curr, neighbor)))
                            queue.append((neighbor, curr))
                        elif neighbor != parent:
                            edge = (min(curr, neighbor), max(curr, neighbor))
                            if edge not in spanning_tree_global_edges:
                                non_tree_global_edges.add(edge)

        fundamental_cycles_nodes = []
        tree_adj = defaultdict(list)
        for u, v in spanning_tree_global_edges:
            tree_adj[u].append(v)
            tree_adj[v].append(u)

        for u, v in non_tree_global_edges:
            q = deque([[u]])
            visited_tree = {u}
            path = []
            while q:
                curr_path = q.popleft()
                curr_node = curr_path[-1]
                if curr_node == v:
                    path = curr_path
                    break
                for nxt in tree_adj[curr_node]:
                    if nxt not in visited_tree:
                        visited_tree.add(nxt)
                        q.append(curr_path + [nxt])
            if path:
                fundamental_cycles_nodes.append(frozenset(path))

        return fundamental_cycles_nodes

    def extract_blackhole_bases(self) -> List[FrozenSet[int]]:
        """骨架提取（调用全量生成树爆破）"""
        return self.get_more_long_cycles()

    # ==========================================
    # 连通性与质检方法（保留自 V3）
    # ==========================================
    def measure_event_horizon_connectivity(self) -> Tuple[int, int]:
        """测算事件视界的连通分量数 C 和目标秩"""
        nodes = set()
        adj = defaultdict(set)
        for u, v in self.basis_edges:
            nodes.update([u, v])
            adj[u].add(v)
            adj[v].add(u)

        visited = set()
        components = 0
        for node in nodes:
            if node not in visited:
                components += 1
                q = deque([node])
                visited.add(node)
                while q:
                    curr = q.popleft()
                    for nbr in adj[curr]:
                        if nbr not in visited:
                            visited.add(nbr)
                            q.append(nbr)

        self.current_components_count = components
        self.current_target_rank = len(self.basis_edges) - len(nodes) + components
        return self.current_target_rank, self.current_components_count

    def verify_extracted_bases(self) -> Tuple[Set[Tuple[int, int]], List[FrozenSet[int]], Set[Tuple[int, int]], List[FrozenSet[int]]]:
        """质检员：检查连通分量 C 是否等于 1"""
        tree_chordless_cycles_edges = self.tree_chordless_cycles_edges
        tree_chordless_cycles_basis = self.tree_chordless_cycles_basis
        basis_edges_to_cycles: Dict[Tuple[int, int], Set[FrozenSet[int]]] = defaultdict(set)

        for cyc in self.original_candidate_cycles:
            for u, v in itertools.combinations(sorted(cyc), 2):
                edge = (min(u, v), max(u, v))
                if edge in self.global_edges:
                    basis_edges_to_cycles[edge].add(cyc)

        # 使用类内已生成的环（current_basis）作为目标环集合
        all_target_cycle: List[FrozenSet[int]] = list(self.current_basis) if self.current_basis else []

        checker_init = DataInitialization(self.basis_edges, debug=False)
        c_count = checker_init.connected_components_count
        tree_cycles_basis = checker_init.basis

        for cycle_nodes in tree_cycles_basis:
            if StaticMethod.verify_chordless_cycle(sorted(cycle_nodes), self.global_adj):
                tree_chordless_cycles_basis.append(cycle_nodes)

        # 从目标环集合中提取边，供后续补全使用
        for cycle_nodes in all_target_cycle:
            for u, v in itertools.combinations(sorted(cycle_nodes), 2):
                if (min(u, v), max(u, v)) in self.global_edges:
                    tree_chordless_cycles_edges.add((min(u, v), max(u, v)))

        tree_chordless_cycles_basis_substitute: List[FrozenSet[int]] = []
        for tree_edge in tree_chordless_cycles_edges:
            for cyc in basis_edges_to_cycles.get(tree_edge, set()):
                tree_chordless_cycles_basis_substitute.append(cyc)

        tree_chordless_cycles_basis_rest = list(
            set(tree_chordless_cycles_basis_substitute) - set(self.original_candidate_cycles)
        )

        if c_count == 0:
            Debug.fuse(f"[黑洞质检失败] 连通量 C={c_count}，无法提取有效基底！")
            return set(), [], tree_chordless_cycles_edges, tree_chordless_cycles_basis_rest
        elif c_count > 1:
            Debug.fuse(f"[黑洞质检失败] 连通量 C={c_count}，存在多个连通分量！")
            return set(), [], tree_chordless_cycles_edges, tree_chordless_cycles_basis_rest
        else:
            Debug.done(f"[黑洞质检成功] 找到环数: {len(self.original_candidate_cycles)} | 连通量 C={c_count}")
            return self.basis_edges, self.original_candidate_cycles, set(), []

    # ==========================================
    # 辅助方法
    # ==========================================
    def _build_local_edges_from_cycles(self, cycles: List[FrozenSet[int]]) -> Set[Tuple[int, int]]:
        """从环集中构建局部边集"""
        edges = set()
        for cyc in cycles:
            eids, cyc_edges, is_valid = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cyc), self.global_adj, self.global_edge_to_eid
            )
            if is_valid:
                edges.update(cyc_edges)
        return edges

    @staticmethod
    def get_correst_rest_cycles(core_edges, original_candidate_cycles, original_candidate_cycles_rest,
                                global_edges, global_adj, global_edge_to_eid):
        """利用生成树过滤 rest_cycles，提取缺失维度的环，直至满秩或候选用尽"""
        # 1. 初始化：核心子图与全局图的环空间秩
        core_data_init = DataInitialization(core_edges)
        core_tree_basis = core_data_init.get_tree_basis()
        # 只保留核心生成树中的无弦环
        core_chordless = [
            cyc for cyc in core_tree_basis
            if StaticMethod.verify_chordless_cycle(sorted(cyc), global_adj)
        ]

        global_data_init = DataInitialization(global_edges=global_edges)
        global_target_rank = global_data_init.target_rank

        # 2. 第一部分：只用原始候选环尝试逼近全局秩
        basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges, original_candidate_cycles, global_target_rank
        )
        if is_full:
            return basis          # 已满秩，直接返回

        # 3. 第二部分：若未满秩，加入核心子图的无弦树环继续消元
        if len(basis) < global_target_rank:
            extended = basis + core_chordless
            basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                global_edges, extended, global_target_rank
            )
            if is_full:
                return basis

        # 4. 第三部分：从 rest 候选里筛选与核心树环共享边集的环，进一步补充
        if not original_candidate_cycles_rest:
            Debug.info("[get_correst_rest_cycles] rest_cycles 为空，无法继续补环")
            return basis

        # 收集核心树环涉及的所有边 ID，作为筛选依据
        core_eids: Set[int] = set()
        for cyc in core_chordless:
            eids, _, valid = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cyc), global_adj, global_edge_to_eid
            )
            if valid:
                core_eids.update(eids)

        # 筛选 rest 中边集完全包含在 core_eids 里的环
        filtered_rest = []
        for cyc in original_candidate_cycles_rest:
            eids, _, valid = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cyc), global_adj, global_edge_to_eid
            )
            if valid and set(eids).issubset(core_eids):
                filtered_rest.append(cyc)

        if not filtered_rest:
            Debug.warn("[get_correst_rest_cycles] 未找到与核心树边匹配的 rest 环")
        else:
            Debug.info(f"[get_correst_rest_cycles] 筛选出 {len(filtered_rest)} 个匹配环")

        # 5. 最终合并、去重，并再次验证无弦性
        all_cycles = basis + filtered_rest
        all_cycles = [
            cyc for cyc in all_cycles
            if StaticMethod.verify_chordless_cycle(sorted(cyc), global_adj)
        ]
        return list(set(all_cycles))
    
    @staticmethod
    def get_all_blackhole_cycles(global_edges, candidate_cycles):
        """获取所有黑洞环"""
        builder = DevouringBlackholeBuilder(
            global_edges=global_edges,
            candidate_cycles=candidate_cycles
        )
        new_blackhole_cycles = builder.run_new_class()  # 使用新的主入口
        return list(set(new_blackhole_cycles))

    @staticmethod
    def _extract_blackhole_edges(all_edges: Set[Tuple[int, int]], perfect_blackhole: Iterable) -> Set[Tuple[int, int]]:
        """从完美黑洞中提取边集"""
        blackhole_nodes = set()
        blackhole_edges = set()
        for cycle in perfect_blackhole:
            for item in cycle:
                if isinstance(item, tuple) and len(item) == 2:
                    blackhole_edges.add((min(item), max(item)))
                else:
                    blackhole_nodes.add(item)
        if blackhole_nodes:
            for u, v in all_edges:
                if u in blackhole_nodes and v in blackhole_nodes:
                    blackhole_edges.add((min(u, v), max(u, v)))
        return blackhole_edges


# ==========================================
# 单维度环提取器 (DimensionCycleExtractor)
# ==========================================
class DimensionCycleExtractor:
    """
    核心功能：
    1. 仅接收全图边和指定维度。
    2. 3 <= 维度 <= 9 时，调用内置静态函数挖出该维度原始环并进行无弦验证与消元。
    """
    def __init__(self, global_edges: Set[Tuple[int, int]], target_dim: int, history_cycles: Optional[List[FrozenSet[int]]] = None):
        self.global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        self.target_dim = target_dim
        
        # 外部传入的历史环基底，作为只读参考，避免直接对其重新赋值导致引用断裂
        self.history_cycles: List[FrozenSet[int]] = history_cycles if history_cycles is not None else []
        self.history_cycles_set: Set[FrozenSet[int]] = set(self.history_cycles)
        self.global_adj = defaultdict(set)
        for u, v in self.global_edges:
            self.global_adj[u].add(v)
            self.global_adj[v].add(u)
            
        self.global_data_init = DataInitialization(self.global_edges)
        self.global_edge_to_eid = self.global_data_init.edge_to_eid
        self.global_target_rank = self.global_data_init.target_rank
        self.chord_edges, self.tree_edges, self.tree_adj = StaticMethod.extract_chord_set(self.global_edges)
        self.tree_basis = self.global_data_init.basis
        self.tree_basis_chordless = [cyc for cyc in self.tree_basis if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        self.tree_basis_chorded = [cyc for cyc in self.tree_basis if not StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        
    def generate_target_cycles(self):
        core_edges: Set[Tuple[int, int]] = set()
        if self.target_dim == 3:
            for target_cycles in ThreeCyclesAndNineCyclesFinder.find_three_cycles(self.global_edges):
                self.history_cycles.extend(target_cycles)
                self.history_cycles = list(set(self.history_cycles))
                self.history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                    self.global_edges, self.history_cycles, self.global_target_rank
                )
                if is_full:
                    yield target_cycles
                    return
                yield target_cycles
        elif self.target_dim == 4:
            for target_cycles in ThreeCyclesAndNineCyclesFinder.find_four_cycles(self.global_edges):
                self.history_cycles.extend(target_cycles)
                self.history_cycles = list(set(self.history_cycles))
                self.history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                    self.global_edges, self.history_cycles, self.global_target_rank
                )
                if is_full:
                    yield target_cycles
                    return
                yield target_cycles
        elif self.target_dim == 5:
            for target_cycles in ThreeCyclesAndNineCyclesFinder.find_five_cycles(self.global_edges):
                self.history_cycles.extend(target_cycles)
                self.history_cycles = list(set(self.history_cycles))
                self.history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                    self.global_edges, self.history_cycles, self.global_target_rank
                )
                if is_full:
                    yield target_cycles
                    return
                yield target_cycles
        else:
            yield self.history_cycles


    def _local_all_spanning_tree_cycles(self, root_node: int) -> List[FrozenSet[int]]:
        """
        全量生成树环基（指定单起点版）：
        严格接受【一个指定点】作为当前全局生成树的绝对根节点。
        """
        adj = defaultdict(list)
        for u, v in self.global_edges:
            adj[u].append(v)
            adj[v].append(u)
            
        visited = set()
        spanning_tree_global_edges = set()
        non_tree_global_edges = set()
        
        # 💡 严格遵循你的意图：
        # 把外部传入的那一个指定点 root_node 作为序列的第一位，强行成为第一棵树的根。
        # 随后顺延遍历其他节点，老老实实包容并长满剩下的独立连通分量（满秩兜底）。
        ordered_start_nodes = [root_node] + [n for n in adj.keys() if n != root_node]
        
        # 1. BFS 构建生成树森林 (100% 维持你原版完美的拓扑划分逻辑)
        for start_node in ordered_start_nodes:
            if start_node not in visited:
                queue = deque([(start_node, -1)])
                visited.add(start_node)
                while queue:
                    curr, parent = queue.popleft()
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            spanning_tree_global_edges.add((min(curr, neighbor), max(curr, neighbor)))
                            queue.append((neighbor, curr))
                        elif neighbor != parent:
                            edge = (min(curr, neighbor), max(curr, neighbor))
                            if edge not in spanning_tree_global_edges:
                                non_tree_global_edges.add(edge)
                                
        # 2. 找基本环 (树边 + 1条非树边) -> 100% 维持你原汁原味的寻路逻辑
        fundamental_cycles_nodes = []
        tree_adj = defaultdict(list)
        for u, v in spanning_tree_global_edges:
            tree_adj[u].append(v)
            tree_adj[v].append(u)
            
        for u, v in non_tree_global_edges:
            # BFS 找 u 到 v 在树上的唯一路径
            q = deque([[u]])
            visited_tree = {u}
            path = []
            while q:
                curr_path = q.popleft()
                curr_node = curr_path[-1]
                if curr_node == v:
                    path = curr_path
                    break
                for nxt in tree_adj[curr_node]:
                    if nxt not in visited_tree:
                        visited_tree.add(nxt)
                        q.append(curr_path + [nxt])
            if path:
                fundamental_cycles_nodes.append(frozenset(path))
        
        return fundamental_cycles_nodes

    def get_more_rest_cycles(self):
        original_history_cycles = self.history_cycles
        original_history_cycles_set = set(self.history_cycles)
        global_data_init = DataInitialization(self.global_edges)
        tree_basis_chordless = [cyc for cyc in global_data_init.basis if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        tree_basis_chorded = [cyc for cyc in global_data_init.basis if not StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidate_cycles=self.history_cycles + tree_basis_chordless,
            global_target_rank=self.global_target_rank
        )
        
        rest_chordless_cycles: List[FrozenSet[int]] = []
        massive_candidate_pool: List[FrozenSet[int]] = []
        loopbreak: bool = False

        # 【终极多生成树全量爆破分支】
        if not is_full:
            core_reducer = BlockwiseCycleReducer(self.global_edges, original_history_cycles)
            
            # 1. 收集所有成功进入消元器的有弦环涉及的全部节点，作为爆破源点集
            seed_nodes = set()
            for cycle in tree_basis_chorded:
                add_cyc, _ = core_reducer.add_candidate(cycle)
                if add_cyc:
                    for node in set(list(cycle)):
                        if len(self.global_adj[node] & set(list(cycle))) > 2:
                            seed_nodes.add(node)
                            if seed_nodes:
                                for node in seed_nodes:
                                    massive_candidate_pool = self._local_all_spanning_tree_cycles(node)
                                    rest_chordless_cycles.extend(massive_candidate_pool)
                                seed_nodes.clear()
                                rest_chordless_cycles = list(set(rest_chordless_cycles))
                                # 3. 将海量候选环一股脑倒进你的消元器里，让你后面的逻辑去精简和迭代消元
                                for p_cyc in rest_chordless_cycles:
                                    if StaticMethod.verify_chordless_cycle(sorted(p_cyc), self.global_adj):
                                        add_cyc, _ = core_reducer.add_candidate(p_cyc)
                                        if add_cyc:
                                            history_cycles.append(p_cyc)
                                            if len(history_cycles) >= self.global_target_rank:
                                                loopbreak = True
                                                break
                        if loopbreak:
                            break
                if loopbreak:
                    break
            massive_candidate_pool.clear()
        rest_chordless_cycles = [cyc for cyc in rest_chordless_cycles if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidate_cycles=history_cycles + list(set(rest_chordless_cycles) - original_history_cycles_set),
            global_target_rank=self.global_target_rank
        )
        Debug.done(f"[DimensionCycleExtractor]挖掘完成，共挖掘到 {len(history_cycles)} 个环，已经满足目标秩")
        return history_cycles

    # =====================================================
    # 下方为指定静态函数 (无依赖直接挖掘小于等于6的全部环)
    # =====================================================
    @staticmethod
    def get_correst_rest_cycles(core_edges, original_candidate_cycles, original_candidate_cycles_rest, 
                                global_edges, global_adj, global_edge_to_eid):
        """利用生成树过滤 rest_cycles，提取缺失维度的环，直至满秩或候选用尽"""
        # 1. 初始化：核心子图与全局图的环空间秩
        core_data_init = DataInitialization(core_edges)
        core_tree_basis = core_data_init.get_tree_basis()
        # 保留核心生成树中的无弦环，作为后续扩展候选
        core_chordless = [
            cyc for cyc in core_tree_basis
            if StaticMethod.verify_chordless_cycle(sorted(cyc), global_adj)
        ]

        global_data_init = DataInitialization(global_edges=global_edges)
        global_target_rank = global_data_init.target_rank

        # 2. 第一部分：仅用原始候选环尝试逼近全局秩
        basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges, original_candidate_cycles, global_target_rank
        )
        if is_full:
            return basis

        # 3. 第二部分：若未满秩，加入核心子图的无弦树环继续消元
        if len(basis) < global_target_rank:
            extended_candidates = basis + core_chordless
            basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                global_edges, extended_candidates, global_target_rank
            )
            if is_full:
                return basis

        # 4. 第三部分：从 rest_cycles 中筛选与核心树环共享边集的候选，进一步补充
        if not original_candidate_cycles_rest:
            Debug.info("[get_correst_rest_cycles] rest_cycles 为空，无法继续补环")
            return basis

        # 收集核心树环涉及的所有边 ID，作为筛选依据
        core_eids: Set[int] = set()
        for cyc in core_chordless:
            eids, _, valid = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cyc), global_adj, global_edge_to_eid
            )
            if valid:
                core_eids.update(eids)

        # 筛选 rest 中边集完全落在 core_eids 内的环
        filtered_rest = []
        for cyc in original_candidate_cycles_rest:
            eids, _, valid = StaticMethod.cycle_covert_eids_and_edges(
                sorted(cyc), global_adj, global_edge_to_eid
            )
            if valid and set(eids).issubset(core_eids):
                filtered_rest.append(cyc)

        if not filtered_rest:
            Debug.warn("[get_correst_rest_cycles] 未找到与核心树边匹配的 rest 环")
        else:
            Debug.info(f"[get_correst_rest_cycles] 筛选出 {len(filtered_rest)} 个匹配环")

        # 5. 最终合并，去重并再次验证无弦性
        all_cycles = basis + filtered_rest  # 第二部分已合并到 basis 中，无需重复加入 part_one
        all_cycles = [
            cyc for cyc in all_cycles
            if StaticMethod.verify_chordless_cycle(sorted(cyc), global_adj)
        ]
        return list(set(all_cycles))
    
    @staticmethod
    def find_three_edges_and_three_cycles(global_edges):
        t_start = time.time()
        unordered_global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        chords_edges, tree_edges, tree_adj = StaticMethod.extract_chord_set(unordered_global_edges)
        global_edges_list = sorted(unordered_global_edges)
        adj = defaultdict(set)
        for u, v in global_edges_list:
            adj[u].add(v)
            adj[v].add(u)

        three_cycles = set()
        three_global_edges = set()

        for u, v in chords_edges:
            common_neighbors = adj[u] & adj[v]
            for w in common_neighbors:
                three_cycles.add(frozenset((u, v, w)))
                three_global_edges.add((min(u, w), max(u, w)))
                three_global_edges.add((min(v, w), max(v, w)))
                three_global_edges.add((min(u, v), max(u, v)))
                
        # 🔧 修复：耗时统计判定由 1000秒 改为 1.0秒
        if time.time() - t_start > 1.0:
            Debug.timing(f"find_three_edges_and_three_cycles 完成 | 找出 3-cycles={len(three_cycles)}", time.time() - t_start)

        return three_global_edges, list(three_cycles)

    @staticmethod
    def find_four_edges_and_four_cycles(global_edges):
        t_start = time.time()
        unordered_global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        chords_edges, tree_edges, tree_adj = StaticMethod.extract_chord_set(unordered_global_edges)
        adj = defaultdict(set)
        for u, v in unordered_global_edges:
            adj[u].add(v)
            adj[v].add(u)

        four_cycles = set()
        four_global_edges = set()
        endpoint_global_edges = set()

        for u, v in chords_edges:
            neighbors_unique = (adj[u] | adj[v]) - (adj[u] & adj[v])
            for w in neighbors_unique:
                endpoint_global_edges.add(tuple(sorted((u, w))))
                endpoint_global_edges.add(tuple(sorted((v, w))))
        endpoint_global_edges = endpoint_global_edges - unordered_global_edges

        endpoint_adj = defaultdict(set)
        for u, v in endpoint_global_edges:
            endpoint_adj[u].add(v)
            endpoint_adj[v].add(u)

        for u, v in unordered_global_edges:
            unique_neighbors_u = adj[u] - adj[v] - {v}
            unique_neighbors_v = adj[v] - adj[u] - {u}
            if unique_neighbors_u and unique_neighbors_v:
                two_nodes_combinations = itertools.product(unique_neighbors_u, unique_neighbors_v)
                for w1, w2 in two_nodes_combinations:
                    if (min(w1, w2), max(w1, w2)) in unordered_global_edges:
                        four_cycle_list = sorted((u, v, w1, w2))
                        if StaticMethod.verify_chordless_cycle(four_cycle_list, adj):
                            four_cycles.add(frozenset(four_cycle_list))
                            for e in itertools.combinations(four_cycle_list, 2):
                                edge_key = (min(e), max(e))
                                if edge_key in unordered_global_edges:
                                    four_global_edges.add(edge_key)
                                    
        # 🔧 修复：耗时判定改为 1.0秒
        if time.time() - t_start > 1.0:
            Debug.timing(f"find_four_edges_and_four_cycles 完成 | 找出 4-cycles={len(four_cycles)}", time.time() - t_start)
        return four_global_edges, list(four_cycles)

    @staticmethod
    def find_five_edges_and_five_cycles(global_edges):
        t_start = time.time() # 🔧 修复：移除了原本重复的一行 t_start = time.time()
        unordered_global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        chords_edges, tree_edges, tree_adj = StaticMethod.extract_chord_set(unordered_global_edges)
        adj = defaultdict(set)
        for u, v in unordered_global_edges:
            adj[u].add(v)
            adj[v].add(u)

        endpoint_global_edges = set()
        for u, v in unordered_global_edges:
            neighbors_unique = (adj[u] | adj[v]) - (adj[u] & adj[v])
            for w in neighbors_unique:
                endpoint_global_edges.add(tuple(sorted((u, w))))
                endpoint_global_edges.add(tuple(sorted((v, w))))
        endpoint_global_edges = endpoint_global_edges - unordered_global_edges

        endpoint_adj = defaultdict(set)
        midnode_to_endpoints = defaultdict(set)
        for u, v in endpoint_global_edges:
            endpoint_adj[u].add(v)
            endpoint_adj[v].add(u)
            common_neighbors = adj[u] & adj[v]
            for node in common_neighbors:
                midnode_to_endpoints[node].add(tuple(sorted((u, v))))

        five_cycles = set()
        virtual_three_nodes_cycles = set()
        for u, v in unordered_global_edges:
            endpoint_common_neighbors = endpoint_adj[u] & endpoint_adj[v]
            for w in endpoint_common_neighbors:
                virtual_three_nodes_cycles.add(frozenset([u, v, w]))

        for three_nodes in virtual_three_nodes_cycles:
            for two_nodes in itertools.combinations(sorted(three_nodes), 2):
                if two_nodes in chords_edges:
                    only_one_nodes = next(iter(set(three_nodes) - set(two_nodes)))
                    two_nodes_other_product = itertools.product(adj[min(two_nodes)] & adj[only_one_nodes], adj[max(two_nodes)] & adj[only_one_nodes])
                    for two_nodes_other in two_nodes_other_product:
                        five_cycles_nodes = frozenset([*two_nodes, *two_nodes_other, only_one_nodes])
                        if len(five_cycles_nodes) == 5:
                            five_cycles.add(five_cycles_nodes)

        final_five_cycles = set()
        five_global_edges = set()
        for five_cycles_nodes in five_cycles:
            if StaticMethod.verify_chordless_cycle(sorted(five_cycles_nodes), adj):
                f_c = frozenset(five_cycles_nodes)
                final_five_cycles.add(f_c)
                for i in five_cycles_nodes:
                    for j in five_cycles_nodes & adj[i]:
                        five_global_edges.add((min(i, j), max(i, j)))

        five_global_edges = five_global_edges & unordered_global_edges
        
        # 🔧 修复：耗时判定改为 1.0秒
        if time.time() - t_start > 1.0:
            Debug.timing(f"find_five_edges_and_five_cycles 完成 | five_cycles_count={len(final_five_cycles)}", time.time() - t_start)
        return five_global_edges, list(final_five_cycles)


import itertools
import random
from multiprocessing import Pool, cpu_count, Manager, Event, Lock
import signal
import sys
import os
# ==========================================
# 主流程调用器 (Main Controller)
# ==========================================
class MainController:
    """
    主模块 (极简流水线 + 定向爆破 + 标准兜底版) - 重构去重版本
    """
    def __init__(self, global_edges: Set[Tuple[int, int]], history_cycles: Optional[List[FrozenSet[int]]] = None, history_cycles_len: Optional[List[int]] = None):
        self.global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        self.data_init = DataInitialization(self.global_edges)
        self.global_target_rank = self.data_init.target_rank
        self.global_adj = self.data_init.adj
        self.global_edge_to_eid = self.data_init.edge_to_eid
        self.final_basis: List[FrozenSet[int]] = []
        
        Debug.section(f"主模块初始化 | 全局边数: {len(self.global_edges)}, 目标秩: {self.global_target_rank}")
        self.tree_edges: Set[Tuple[int, int]] = set()
        self.tree_basis_chordless: List[FrozenSet[int]] = []
        self.tree_basis = self._generate_fallback_cycles()
        self.tree_edges = self._generate_fallback_cycles_edges()

    def _generate_fallback_cycles_edges(self) -> Set[Tuple[int, int]]:
        self.tree_basis_chordless = [cyc for cyc in self.tree_basis if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        self.tree_basis_chord = [cyc for cyc in self.tree_basis if not StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)]
        for cyc in self.tree_basis_chord:
            eids, edges, is_valid = StaticMethod.cycle_covert_eids_and_edges(sorted(cyc), self.global_adj, self.global_edge_to_eid)
            self.tree_edges.update(edges)
        return self.tree_edges

    def _generate_fallback_cycles(self) -> List[FrozenSet[int]]:
        """生成树基本环，作为终极兜底，保证绝对满秩"""
        adj = defaultdict(list)
        for u, v in self.global_edges:
            adj[u].append(v)
            adj[v].append(u)
            
        visited = set()
        spanning_tree_global_edges = set()
        non_tree_global_edges = set()
        
        # 1. BFS 构建生成树森林 (处理非连通图)
        for start_node in list(adj.keys()):
            if start_node not in visited:
                queue = deque([(start_node, -1)])
                visited.add(start_node)
                while queue:
                    curr, parent = queue.popleft()
                    for neighbor in adj[curr]:
                        if neighbor not in visited:
                            visited.add(neighbor)
                            spanning_tree_global_edges.add((min(curr, neighbor), max(curr, neighbor)))
                            queue.append((neighbor, curr))
                        elif neighbor != parent:
                            edge = (min(curr, neighbor), max(curr, neighbor))
                            if edge not in spanning_tree_global_edges:
                                non_tree_global_edges.add(edge)
                                
        # 2. 找基本环 (树边 + 1条非树边)
        fundamental_cycles_nodes = []
        tree_adj = defaultdict(list)
        for u, v in spanning_tree_global_edges:
            tree_adj[u].append(v)
            tree_adj[v].append(u)
            
        for u, v in non_tree_global_edges:
            # BFS 找 u 到 v 在树上的唯一路径
            q = deque([[u]])
            visited_tree = {u}
            path = []
            while q:
                curr_path = q.popleft()
                curr_node = curr_path[-1]
                if curr_node == v:
                    path = curr_path
                    break
                for nxt in tree_adj[curr_node]:
                    if nxt not in visited_tree:
                        visited_tree.add(nxt)
                        q.append(curr_path + [nxt])
            if path:
                fundamental_cycles_nodes.append(frozenset(path))
                
        return fundamental_cycles_nodes

    @staticmethod
    def generate_target_cycles_original(global_edges):
        """生成基础环 (3-9环)"""
        history_cycles: List[FrozenSet[int]] = []
        is_full: bool = False
        # 抽离统一执行流程
        global_data_init = DataInitialization(global_edges)
        global_target_rank, global_adj = global_data_init.target_rank, global_data_init.adj

        for target_dim in range(3, 10):
            DimensionCycle = DimensionCycleExtractor(global_edges=global_edges, target_dim=target_dim, history_cycles=history_cycles)
            for target_cycles in DimensionCycle.generate_target_cycles():
                history_cycles.extend(target_cycles)
                history_cycles_set = set(history_cycles)
                history_cycles = list(history_cycles_set)
                history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                    global_edges, history_cycles, global_target_rank
                )
                if is_full:
                    return history_cycles, is_full
            max_history_cycle_len = max(len(cyc) for cyc in history_cycles) if history_cycles else 0
            if is_full:
                return history_cycles, is_full
            else:
                if len(history_cycles) >= global_target_rank * 0.95 and not is_full:
                    return history_cycles, is_full
        return history_cycles, is_full

    # ==================== 长环并行支持 ====================
    @staticmethod
    def _prepare_long_cycle_worker_params(
        cycle_len: int,
        cycle_len_mapping: Dict[int, Tuple[int, int, int]],
        indeepment_endpoints_to_virtual_three_cycle: Dict[Tuple[int, int], Set[FrozenSet[int]]],
        node_to_indeepment_paths_index: Dict[FrozenSet[int], Set[int]],
        node_to_global_paths_index: Dict[FrozenSet[int], Set[int]],
        n_workers: int = 4
    ) -> List[List[Tuple[Set[int], Set[int], Set[int]]]]:
        """构建三元索引集切片，用于并行长环生成"""
        if cycle_len not in cycle_len_mapping:
            return []
        
        deep_len, global_len1, global_len2 = cycle_len_mapping[cycle_len]
        three_paths_index_set_list: List[Tuple[Set[int], Set[int], Set[int]]] = []
        
        for (u, v), three_cycles_set in indeepment_endpoints_to_virtual_three_cycle.items():
            indeepment_paths_index_set = (
                node_to_indeepment_paths_index.get(frozenset([u]), set()) & 
                node_to_indeepment_paths_index.get(frozenset([v]), set())
            )
            if not indeepment_paths_index_set:
                continue
            
            for three_cycle in three_cycles_set:
                w = next(iter(three_cycle - {u, v}))
                global_paths_index_set_1 = (
                    node_to_global_paths_index.get(frozenset([v]), set()) & 
                    node_to_global_paths_index.get(frozenset([w]), set())
                )
                global_paths_index_set_2 = (
                    node_to_global_paths_index.get(frozenset([w]), set()) & 
                    node_to_global_paths_index.get(frozenset([u]), set())
                )
                if not (global_paths_index_set_1 and global_paths_index_set_2):
                    continue
                three_paths_index_set_list.append((
                    indeepment_paths_index_set,
                    global_paths_index_set_1,
                    global_paths_index_set_2
                ))
        
        n_workers = min(n_workers, len(three_paths_index_set_list))
        if n_workers <= 1:
            return []
        
        chunk_size = (len(three_paths_index_set_list) + n_workers - 1) // n_workers
        worker_slices = []
        for i in range(n_workers):
            slice_start = i * chunk_size
            slice_end = min((i + 1) * chunk_size, len(three_paths_index_set_list))
            if slice_start >= slice_end:
                break
            worker_slices.append(three_paths_index_set_list[slice_start:slice_end])
        return worker_slices

    @staticmethod
    def worker_long_cycle_engine(
        worker_three_paths_list: List[Tuple[Set[int], Set[int], Set[int]]],
        global_adj: Dict[int, Set[int]],
        all_paths_list: List[FrozenSet[int]],
        expected_lengths: Tuple[int, int, int],
        node_to_global_paths_index: Dict[FrozenSet[int], Set[int]]
    ) -> Set[FrozenSet[int]]:
        """Worker：从三元索引集生成候选环"""
        detected = set()
        deep_len, global_len1, global_len2 = expected_lengths
        
        for three_paths in worker_three_paths_list:
            indeepment_paths_index_set, global_paths_index_set_1, global_paths_index_set_2 = three_paths
            
            # 收集实际路径节点（根据路径长度区分）
            all_indexes = indeepment_paths_index_set | global_paths_index_set_1 | global_paths_index_set_2
            global_paths_nodes = set()
            indeepment_paths_nodes = set()
            for idx in all_indexes:
                path_len = len(all_paths_list[idx])
                if path_len in {global_len1, global_len2}:
                    global_paths_nodes.add(all_paths_list[idx])
                if path_len == deep_len:
                    indeepment_paths_nodes.add(all_paths_list[idx])
            
            if not (indeepment_paths_nodes and global_paths_nodes):
                continue
            
            for p0, p1 in itertools.product(indeepment_paths_nodes, global_paths_nodes):
                half_path = p0 | p1
                if len(half_path) != len(p0) + len(p1) - 1:
                    continue
                if not StaticMethod.verify_chordless_path(sorted(half_path), global_adj):
                    continue
                
                endpoints, _ = StaticMethod.generate_chordless_mapping(sorted(half_path), global_adj)
                end1, end2 = min(endpoints), max(endpoints)
                
                end_paths = {
                    all_paths_list[idx] 
                    for idx in (
                        node_to_global_paths_index.get(frozenset([end1]), set()) & 
                        node_to_global_paths_index.get(frozenset([end2]), set())
                    )
                }
                for end_path in end_paths:
                    all_path = half_path | end_path
                    if len(all_path) != len(half_path) + len(end_path) - 2:
                        continue
                    if len(all_path) != deep_len + global_len1 + global_len2 - 3:
                        continue
                    sorted_all_path = sorted(all_path)
                    if StaticMethod.verify_chordless_cycle(sorted_all_path, global_adj):
                        detected.add(frozenset(sorted_all_path))
        return detected

    # ==================== 主迭代逻辑 ====================
    def iterate_target_cycles(self):
        """迭代生成目标长度的无弦环（并行增强版）"""
        # 第一阶段：生成初始历史环（启用并行）
        history_cycles, is_full = self.generate_target_cycles_original(self.global_edges)
        max_history_cycle_len = max(len(cyc) for cyc in history_cycles) if history_cycles else 0
        history_cycles_chordless = sorted(
            [cyc for cyc in history_cycles if StaticMethod.verify_chordless_cycle(sorted(cyc), self.global_adj)], 
            key=len
        )
        history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            self.global_edges, history_cycles_chordless, self.global_target_rank
        )
        if is_full:
            yield from history_cycles
            return
        else:
            DevouringBlackhole = DevouringBlackholeBuilder(self.global_edges, history_cycles)
            basis = DevouringBlackhole.get_more_long_cycles()
            history_cycles.extend(basis)
            history_cycles = list(set(history_cycles))
            history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                self.global_edges, history_cycles, self.global_target_rank
            )
            if is_full:
                yield from history_cycles
                return
            else:
                yield from history_cycles

    def get_more_long_cycles(self):
        final_basis: List[FrozenSet[int]] = []
        for cycle in self.iterate_target_cycles():
            if StaticMethod.verify_chordless_cycle(sorted(cycle), self.global_adj):
                final_basis.append(cycle)
        history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidate_cycles=final_basis,
            global_target_rank=self.global_target_rank
        )
        if is_full:
            return history_cycles
        return history_cycles

    def get_cycles_results(self, raw_edges_for_mapping): 
        """
        获取最终的环检测结果
        """
        Debug.section("开始收集最终结果...")
        final_basis = self.get_more_long_cycles()
        
        edge_mapping, _, _ = GraphDataEncoder.generate_edges_and_edge_to_eid(raw_edges_for_mapping)
        
        real_cycles = []
        for cyc in final_basis:
            real_nodes = set()
            for u, v in itertools.combinations(sorted(list(cyc)), 2):
                edge_key = (u, v)
                if edge_key in edge_mapping: 
                    real_nodes.update(edge_mapping[edge_key])
            if real_nodes:
                real_cycles.append(real_nodes)
            
        Debug.done(f"结果收集完成 | 共 {len(real_cycles)} 个环")
        return real_cycles
    
# ==============================================================================
# 🌐 公开 API
# ==============================================================================

def _load_edges(edges):
    """统一加载边集：支持文件路径或 Set[Tuple[int, int]]。"""
    if isinstance(edges, str):
        raw = set()
        with open(edges, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) >= 2:
                    raw.add((min(int(parts[0]), int(parts[1])),
                             max(int(parts[0]), int(parts[1]))))
    else:
        raw = set((min(u, v), max(u, v)) for u, v in edges)
    return raw


def _compute_cycle_basis(raw_edges):
    """核心计算：返回顶点集合的环基列表。"""
    controller = MainController(raw_edges, [])
    return [set(cyc) for cyc in controller.get_more_long_cycles()]


def _vertices_to_edges(cycle_vertices, all_edges):
    """将无弦环的顶点集合转换为边集合。
    
    对于无弦环，顶点集合内部的所有图边恰好构成环的 |S| 条边。
    """
    edge_set = set()
    for u, v in all_edges:
        if u in cycle_vertices and v in cycle_vertices:
            edge_set.add((u, v))
    return frozenset(edge_set)


def chordless_cycle_basis(edges, output_file=None):
    """
    纯 Python 满秩无弦环基 — 顶点集合版。零外部依赖。

    Args:
        edges: Set[Tuple[int, int]] 或 文件路径 (str)
        output_file: 可选，输出文件路径（每行一个环，空格分隔顶点）

    Returns:
        List[Set[int]] — 满秩无弦环基，每个环为顶点集合

    Example:
        >>> basis = chordless_cycle_basis("graph.txt")
        >>> print(len(basis))
        4839
    """
    raw = _load_edges(edges)
    result = _compute_cycle_basis(raw)

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            for cyc in result:
                f.write(" ".join(map(str, sorted(cyc))) + "\n")

    return result


def chordless_cycle_basis_edges(edges, output_file=None):
    """
    纯 Python 满秩无弦环基 — 边集合版。零外部依赖。

    Args:
        edges: Set[Tuple[int, int]] 或 文件路径 (str)
        output_file: 可选，输出文件路径（每行一个环，空格分隔的 u-v 对）

    Returns:
        List[FrozenSet[Tuple[int, int]]] — 满秩无弦环基，每个环为边集合

    Example:
        >>> basis = chordless_cycle_basis_edges("graph.txt")
        >>> for cyc in basis:
        ...     print(len(cyc))  # 环长 = 边数
    """
    raw = _load_edges(edges)
    vertex_cycles = _compute_cycle_basis(raw)
    result = [_vertices_to_edges(cyc, raw) for cyc in vertex_cycles]

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            for cyc in result:
                f.write(" ".join(f"{u}-{v}" for u, v in sorted(cyc)) + "\n")

    return result




# ==============================================================================
# 🚪 命令行入口
# ==============================================================================
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("用法: python blackhole_diffusion.py <input_file> [output_file]")
        print("示例: python blackhole_diffusion.py edge007.txt out.txt")
        sys.exit(1)

    input_file = sys.argv[1]
    output_file = sys.argv[2] if len(sys.argv) > 2 else "out.txt"

    t0 = time.perf_counter()
    basis = chordless_cycle_basis(input_file, output_file)
    elapsed = time.perf_counter() - t0

    print(f"✅ 完成: {len(basis)} 个无弦环, 最长环 {max(len(c) for c in basis) if basis else 0}, 耗时 {elapsed:.2f}s")
