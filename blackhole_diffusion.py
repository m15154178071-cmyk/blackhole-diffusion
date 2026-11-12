import os
os.environ["PYDEVD_DISABLE_FILE_VALIDATION"] = "1"

# ── 标准库 ──
import array
import base64
import bisect
import collections
import collections.abc
import contextlib
import csv
import ctypes
import datetime
import enum
import functools
import gc
import importlib
import itertools
import json
import math
import os
import re
import stat
import subprocess
import sys
import tempfile
import threading
import time
import heapq
import unicodedata
from collections import Counter, defaultdict, deque
from functools import lru_cache
from typing import (
    Any,
    Callable,
    DefaultDict,
    Deque,
    Dict,
    FrozenSet,
    Generator,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Set,
    Tuple,
    Union,
)

# 立即禁用自动垃圾回收，防止程序退出时卡顿
gc.disable()


# ── 平台特定 ──
try:
    from ctypes import wintypes
except Exception:
    wintypes = None

from debug_util import Debug



# ==========================================
# 数据编码器 (IntPairBijectiveCodec)
# ==========================================
class IntPairBijectiveCodec:
    """
    整数二元组双射编解码器。

    编码分层：
      第一层：字符 -> 按 UTF-8 编码大小排序 -> 非负索引 0..N-1
              虚拟补位字符 -> UTF-8 最大编码 + 1 -> 索引固定 -1
      第二层：索引 -> 定长字符串片段（'-' 作为前导补位）
              真实索引 i  -> str(i).rjust(L, '-')    例如 ---0, -156, -355
              补位索引 -1 -> '-' * L                 例如 ----
      拼接所有片段 -> 唯一编码字符串。

    反解分层：
      1. 把编码串里的 '-' 替换为空格；
      2. split 得到索引列表（补位段全 '-'，替换后自动消失）；
      3. 索引 -> idx_to_char -> char_to_utf8hex -> bytes.fromhex -> 原始字符；
      4. 拼接得到 raw_str；
      5. 先查 original_str_cache；未命中再 int(raw_str) 查 original_int_cache。

    自环与边计数：
      归一化 (min, max) 会把 (u, v) 和 (v, u) 合并，原始边数量会变少。
      因此用 edge_count 记录每条归一化边在原始 set 中的出现次数。
      规则（按需求）：
        edge_count[key] == 1  -> 不是自环
        edge_count[key] == 2  -> 是自环
      同时保留真实 u == v 判断作为辅助：self_loop_keys_by_uv。
    """

    PAD_INDEX = -1

    def __init__(self, edges: Set[Tuple[int, int]]):
        self.edges: Set[Tuple[int, int]] = edges

        # ---------- 原始数据分类备份 ----------
        self.original_str_cache: Dict[str, Any] = {}
        self.original_int_cache: Dict[int, Any] = {}

        # ---------- 边计数与自环标记 ----------
        self.edge_count: Dict[Tuple[int, int], int] = {}
        self.self_loop_keys: Set[Tuple[int, int]] = set()          # 按计数规则：count == 2
        self.self_loop_keys_by_uv: Set[Tuple[int, int]] = set()    # 按真实 u == v
        self.normal_keys: Set[Tuple[int, int]] = set()             # 按计数规则：count == 1

        # ---------- 整数 <-> 字符串 ----------
        self.int_to_str: Dict[int, str] = {}
        self.str_to_int: Dict[str, int] = {}

        # ---------- 字符 <-> 索引 ----------
        self.char_to_idx: Dict[str, int] = {}
        self.idx_to_char: Dict[int, str] = {}

        # ---------- 字符 <-> UTF-8 十六进制 ----------
        self.char_to_utf8hex: Dict[str, str] = {}
        self.utf8hex_to_char: Dict[str, str] = {}

        # ---------- 补位字符 ----------
        self.pad_char_hex: str = ""
        self.pad_index: int = self.PAD_INDEX

        # ---------- 编码参数 ----------
        self.max_str_len: int = 0
        self.index_str_len: int = 0
        self.encoded_str_len: int = 0
        self.full_pad_str: str = ""

        # ---------- 编码对 <-> ID ----------
        self.encoded_pair_to_id: Dict[Tuple[str, str], int] = {}
        self.id_to_encoded_pair: Dict[int, Tuple[str, str]] = {}
        self.original_pair_to_id: Dict[Tuple[int, int], int] = {}
        self.id_to_original_pair: Dict[int, Tuple[int, int]] = {}

        # ---------- 关系映射 ----------
        self.relation_map: Dict[int, Set[int]] = defaultdict(set)

        # ---------- 构建 ----------
        self._build_original_value_backup()
        self._build_all()

    # ================================================================
    # 原始数据分类备份
    # ================================================================

    def _build_original_value_backup(self) -> None:
        self.original_str_cache.clear()
        self.original_int_cache.clear()

        for e in self.edges:
            for v in e:
                if isinstance(v, bool):
                    self.original_str_cache[str(v)] = v
                elif isinstance(v, int):
                    self.original_int_cache[v] = v
                    self.original_str_cache[str(v)] = v
                elif isinstance(v, str):
                    self.original_str_cache[v] = v
                    try:
                        iv = int(v)
                    except (TypeError, ValueError):
                        pass
                    else:
                        self.original_int_cache.setdefault(iv, v)
                else:
                    self.original_str_cache[str(v)] = v

    # ================================================================
    # 边计数构建
    # ================================================================

    def _build_edge_count(self) -> None:
        """
        统计归一化 (min, max) 边在原始 set 中的出现次数。
          - 普通边 (u, v) 和 (v, u) 在 set 中是两个不同元素，
            归一化到同一个 key，计数为 2；
          - 自环 (u, u) 在 set 中只有一个元素，
            归一化到同一个 key，计数为 1。
        按需求规则：
          count == 1 -> 不是自环，加入 normal_keys
          count == 2 -> 是自环，加入 self_loop_keys
        同时按真实 u == v 记录 self_loop_keys_by_uv。
        """
        self.edge_count.clear()
        self.self_loop_keys.clear()
        self.self_loop_keys_by_uv.clear()
        self.normal_keys.clear()

        for u, v in self.edges:
            key = (min(u, v), max(u, v))
            self.edge_count[key] = self.edge_count.get(key, 0) + 1

        for key, cnt in self.edge_count.items():
            if cnt == 1:
                self.normal_keys.add(key)
            elif cnt == 2:
                self.self_loop_keys.add(key)

            if key[0] == key[1]:
                self.self_loop_keys_by_uv.add(key)

    # ================================================================
    # 构建
    # ================================================================

    def _build_all(self) -> None:
        # 0. 统计边计数与自环
        self._build_edge_count()

        # 1. 整数 -> 字符串
        all_ints = sorted({x for e in self.edges for x in e})
        all_strs: List[str] = []
        for x in all_ints:
            s = str(x)
            self.int_to_str[x] = s
            self.str_to_int[s] = x
            all_strs.append(s)

        # 2. 最长字符串长度
        self.max_str_len = max((len(s) for s in all_strs), default=0)

        # 3. 汇总所有字符
        chars: Set[str] = set()
        for s in all_strs:
            chars.update(s)

        # 4. 每个字符的 UTF-8 16 进制编码
        for ch in chars:
            h = ch.encode("utf-8").hex()
            self.char_to_utf8hex[ch] = h
            self.utf8hex_to_char[h] = ch

        # 5. 按 UTF-8 编码数值排序，分配非负索引 0..N-1
        sorted_chars = sorted(
            chars, key=lambda c: int(self.char_to_utf8hex[c], 16)
        )
        for i, ch in enumerate(sorted_chars):
            self.char_to_idx[ch] = i
            self.idx_to_char[i] = ch

        # 6. 补位字符：UTF-8 超限编码 = 最大编码 + 1
        if sorted_chars:
            max_code = max(
                int(self.char_to_utf8hex[c], 16) for c in sorted_chars
            )
            self.pad_char_hex = format(max_code + 1, "x")
        else:
            self.pad_char_hex = "0"

        # 7. 二级编码片段长度 L = len(str(N-1)) + 1
        n = len(sorted_chars)
        if n == 0:
            self.index_str_len = 1
        else:
            self.index_str_len = len(str(n - 1)) + 1
        self.full_pad_str = "-" * self.index_str_len
        self.encoded_str_len = self.max_str_len * self.index_str_len

        # 8. 编码所有边
        self._encode_edges()

    # ================================================================
    # 一级：字符串 <-> 索引向量
    # ================================================================

    def _str_to_index_vec(self, s: str) -> Tuple[int, ...]:
        idxs = [self.char_to_idx[ch] for ch in s]
        pad_len = self.max_str_len - len(s)
        return tuple(idxs + [self.PAD_INDEX] * pad_len)

    def _index_vec_to_str(self, vec: Tuple[int, ...]) -> str:
        return "".join(
            self.idx_to_char[i] for i in vec if i != self.PAD_INDEX
        )

    # ================================================================
    # 二级：索引 <-> 定长字符串片段
    # ================================================================

    def _index_to_segment(self, idx: int) -> str:
        L = self.index_str_len
        if idx == self.PAD_INDEX:
            return "-" * L
        return str(idx).rjust(L, "-")

    # ================================================================
    # 字符串 <-> 编码字符串
    # ================================================================

    def encode_str(self, s: str) -> str:
        vec = self._str_to_index_vec(s)
        return "".join(self._index_to_segment(i) for i in vec)

    def decode_to_index_list(self, encoded: str) -> List[int]:
        s = encoded.replace(self.full_pad_str, " ")
        s = s.replace("-", " ")
        return [int(p) for p in s.split()]

    def decode_to_string(self, encoded: str) -> str:
        indices = self.decode_to_index_list(encoded)
        chars: List[str] = []
        for idx in indices:
            if idx not in self.idx_to_char:
                raise KeyError(
                    f"索引 {idx} 不在 idx_to_char 中（共 {len(self.idx_to_char)} 个字符）"
                )
            ch = self.idx_to_char[idx]
            hex_str = self.char_to_utf8hex[ch]
            real_ch = bytes.fromhex(hex_str).decode("utf-8")
            chars.append(real_ch)
        return "".join(chars)

    def decode_to_value(self, encoded: str) -> Any:
        raw_str = self.decode_to_string(encoded)

        if raw_str in self.original_str_cache:
            return self.original_str_cache[raw_str]

        try:
            iv = int(raw_str)
        except (TypeError, ValueError):
            iv = None

        if iv is not None and iv in self.original_int_cache:
            return self.original_int_cache[iv]

        raise KeyError(f"拼接结果 {raw_str!r} 在原始数据备份中不存在")

    # ================================================================
    # 边编码
    # ================================================================

    @staticmethod
    def _normalize_pair(pair: Tuple[int, int]) -> Tuple[int, int]:
        u, v = pair
        if u == v:
            raise ValueError(f"自配对 ({u}, {v}) 不在编码域内")
        return (min(u, v), max(u, v))

    def _encode_edges(self) -> None:
        # 保留归一化 + 去重 + 排序
        normalized = sorted({
            (min(u, v), max(u, v))
            for u, v in self.edges
            if u != v
        })

        for eid, (u, v) in enumerate(normalized):
            enc_u = self.encode_str(self.int_to_str[u])
            enc_v = self.encode_str(self.int_to_str[v])

            self.original_pair_to_id[(u, v)] = eid
            self.id_to_original_pair[eid] = (u, v)
            self.encoded_pair_to_id[(enc_u, enc_v)] = eid
            self.id_to_encoded_pair[eid] = (enc_u, enc_v)

        for u, v in normalized:
            self.relation_map[u].add(v)
            self.relation_map[v].add(u)

    # ================================================================
    # 静态反解函数（参数统一用 set 输入）
    # ================================================================

    @staticmethod
    def decode_encoded_pairs_static(
        encoded_pairs: Set[Tuple[str, str]],
        utf8_hex_set: Set[str],
        full_pad_str: str,
        single_dash: str = "-",
        original_str_cache: Optional[Dict[str, Any]] = None,
        original_int_cache: Optional[Dict[int, Any]] = None,
    ) -> Set[Tuple[Any, Any]]:
        index_str_len = len(full_pad_str)
        if index_str_len <= 0:
            raise ValueError("full_pad_str 长度必须大于 0")
        if full_pad_str != single_dash * index_str_len:
            raise ValueError(
                f"full_pad_str({full_pad_str!r}) 必须由 {index_str_len} 个 "
                f"single_dash({single_dash!r}) 组成"
            )
        if not isinstance(utf8_hex_set, (set, frozenset)):
            raise TypeError(
                f"utf8_hex_set 必须是 set，实际收到 {type(utf8_hex_set).__name__}"
            )

        sorted_utf8_hex_list: List[str] = sorted(
            utf8_hex_set, key=lambda h: int(h, 16)
        )

        idx_to_char: Dict[int, str] = {}
        for i, hex_str in enumerate(sorted_utf8_hex_list):
            idx_to_char[i] = bytes.fromhex(hex_str).decode("utf-8")

        def _decode_one(encoded: str) -> Any:
            s = encoded.replace(full_pad_str, " ")
            s = s.replace(single_dash, " ")
            parts = s.split()

            chars: List[str] = []
            for p in parts:
                idx = int(p)
                if idx not in idx_to_char:
                    raise KeyError(
                        f"索引 {idx} 超出字符集合范围（共 {len(idx_to_char)} 个字符）"
                    )
                chars.append(idx_to_char[idx])
            raw_str = "".join(chars)

            if original_str_cache is not None and raw_str in original_str_cache:
                return original_str_cache[raw_str]

            if original_int_cache is not None:
                try:
                    iv = int(raw_str)
                except (TypeError, ValueError):
                    iv = None
                if iv is not None and iv in original_int_cache:
                    return original_int_cache[iv]

            raise KeyError(f"拼接结果 {raw_str!r} 在原始数据备份中不存在")

        result: Set[Tuple[Any, Any]] = set()
        for enc_u, enc_v in encoded_pairs:
            u = _decode_one(enc_u)
            v = _decode_one(enc_v)
            if u == v:
                continue
            if isinstance(u, int) and isinstance(v, int):
                result.add((min(u, v), max(u, v)))
            else:
                result.add((u, v))
        return result

    # ================================================================
    # 实例级反解接口
    # ================================================================

    def decode_encoded_pair(self, enc_pair: Tuple[str, str]) -> Tuple[Any, Any]:
        u = self.decode_to_value(enc_pair[0])
        v = self.decode_to_value(enc_pair[1])
        return (u, v)

    def decode_all_encoded_pairs(self) -> Set[Tuple[Any, Any]]:
        return self.decode_encoded_pairs_static(
            encoded_pairs=set(self.encoded_pair_to_id.keys()),
            utf8_hex_set=set(self.char_to_utf8hex.values()),
            full_pad_str=self.full_pad_str,
            single_dash="-",
            original_str_cache=self.original_str_cache,
            original_int_cache=self.original_int_cache,
        )

    # ================================================================
    # 查询接口
    # ================================================================

    def get_char_index_map(self) -> Dict[str, int]:
        m = dict(self.char_to_idx)
        m["<PAD>"] = self.PAD_INDEX
        return m

    def get_char_utf8_map(self) -> Dict[str, str]:
        return dict(self.char_to_utf8hex)

    def get_pad_info(self) -> Dict[str, Any]:
        return {
            "pad_char_hex": self.pad_char_hex,
            "pad_index": self.pad_index,
            "index_str_len": self.index_str_len,
            "max_str_len": self.max_str_len,
            "encoded_str_len": self.encoded_str_len,
            "full_pad_str": self.full_pad_str,
        }

    def get_edge_count_info(self) -> Dict[str, Any]:
        """返回边计数、自环、普通边信息。"""
        return {
            "edge_count": dict(self.edge_count),
            "self_loop_keys": set(self.self_loop_keys),
            "self_loop_keys_by_uv": set(self.self_loop_keys_by_uv),
            "normal_keys": set(self.normal_keys),
        }

    def encode_transitive_pair_index(
        self, pair_ids: List[Tuple[int, int]]
    ) -> Dict[Tuple[int, int], int]:
        transitive_index: Dict[Tuple[int, int], int] = {}
        for idx, (id_a, id_b) in enumerate(sorted(set(pair_ids))):
            transitive_index[(id_a, id_b)] = idx
        return transitive_index


    # ================================================================
    # 静态反解一条龙
    # ================================================================

    @staticmethod
    def decode_encoded_pairs_one_shot(
        encoded_pairs: Set[Tuple[str, str]],
        raw_edges: Set[Tuple[int, int]],
        single_dash: str = "-",
    ) -> Set[Tuple[Any, Any]]:
        """
        静态一条龙反解：内部实例化 codec，取变量，再反解。

        Args:
            encoded_pairs:
                编码后的字符串对集合 {(enc_u, enc_v), ...}
            raw_edges:
                原始边集合，用于内部重新构造 codec，
                从而拿到 utf8_hex_set、full_pad_str、original_str_cache、
                original_int_cache。
            single_dash: 单字符 '-'，默认 "-"

        Returns:
            还原后的原始数据对集合。两端都是 int 时按 (min, max) 规范化。
        """
        # 1. 内部实例化 codec，取全部所需变量
        codec = IntPairBijectiveCodec(set(raw_edges))

        utf8_hex_set: Set[str] = set(codec.char_to_utf8hex.values())
        full_pad_str: str = codec.full_pad_str
        original_str_cache: Dict[str, Any] = codec.original_str_cache
        original_int_cache: Dict[int, Any] = codec.original_int_cache

        # 2. 参数自检
        index_str_len = len(full_pad_str)
        if index_str_len <= 0:
            raise ValueError("full_pad_str 长度必须大于 0")
        if full_pad_str != single_dash * index_str_len:
            raise ValueError(
                f"full_pad_str({full_pad_str!r}) 必须由 {index_str_len} 个 "
                f"single_dash({single_dash!r}) 组成"
            )
        if not isinstance(utf8_hex_set, (set, frozenset)):
            raise TypeError(
                f"utf8_hex_set 必须是 set，实际收到 {type(utf8_hex_set).__name__}"
            )

        # 3. 按 UTF-8 hex 数值排序，索引与编码时一致
        sorted_utf8_hex_list: List[str] = sorted(
            utf8_hex_set, key=lambda h: int(h, 16)
        )

        # 4. 索引 -> 原始字符
        idx_to_char: Dict[int, str] = {}
        for i, hex_str in enumerate(sorted_utf8_hex_list):
            idx_to_char[i] = bytes.fromhex(hex_str).decode("utf-8")

        # 5. 单个编码串 -> 原始值
        def _decode_one(encoded: str) -> Any:
            # 5.1 全长补位段替换为空格
            s = encoded.replace(full_pad_str, " ")
            # 5.2 单个 '-' 替换为空格
            s = s.replace(single_dash, " ")
            # 5.3 split 得到真实索引
            parts = s.split()

            # 5.4 索引 -> 字符 -> 拼接
            chars: List[str] = []
            for p in parts:
                idx = int(p)
                if idx not in idx_to_char:
                    raise KeyError(
                        f"索引 {idx} 超出字符集合范围（共 {len(idx_to_char)} 个字符）"
                    )
                chars.append(idx_to_char[idx])
            raw_str = "".join(chars)

            # 5.5 先查字符串备份
            if raw_str in original_str_cache:
                return original_str_cache[raw_str]

            # 5.6 再转整数查整数备份
            try:
                iv = int(raw_str)
            except (TypeError, ValueError):
                iv = None
            if iv is not None and iv in original_int_cache:
                return original_int_cache[iv]

            raise KeyError(f"拼接结果 {raw_str!r} 在原始数据备份中不存在")

        # 6. 遍历反解
        result: Set[Tuple[Any, Any]] = set()
        for enc_u, enc_v in encoded_pairs:
            u = _decode_one(enc_u)
            v = _decode_one(enc_v)
            if u == v:
                continue
            if isinstance(u, int) and isinstance(v, int):
                result.add((min(u, v), max(u, v)))
            else:
                result.add((u, v))

        return result




# ==========================================
# 静态方法类 (StaticMethod)
# ==========================================
class StaticMethod:
    @staticmethod
    def input_file_lines(input_file: str) -> List[Tuple[int, int]]:
        """从文件读取边数据"""
        with open(input_file, "r", encoding="utf-8", errors="ignore") as f:
            raw_lines = [line.strip() for line in f if line.strip()]
        parts_list = [parts for line in raw_lines for parts in [re.split(r"[,\s]+", line)] if len(parts) >= 2]
        lines: List[Tuple[int, int]] = []
        for parts in parts_list:
            try:
                u, v = int(parts[0]), int(parts[1])
                lines.append((min(u, v), max(u, v)))
            except (ValueError, IndexError):
                continue
        return lines


    @staticmethod
    def compute_components_and_rank(
        global_edges: Set[Tuple[int, int]]
    ) -> Tuple[int, int, bool, int, int]:
        """
        静态计算连通分量数量与目标秩 target_rank。

        返回:
            (components, target_rank, is_connected, V, E)

        其中:
            components   = 连通分量数量 C
            target_rank  = E - V + C，即电路秩 / Betti Number / 基本环数量
            is_connected = 是否只有一个连通分量
            V            = 出现在边中的节点数
            E            = 去重、去自环后的无向边数
        """
        # 无向边规范化，去掉自环
        edges = {(min(u, v), max(u, v)) for u, v in global_edges if u != v}

        adj: Dict[int, Set[int]] = defaultdict(set)
        nodes: Set[int] = set()

        for u, v in edges:
            adj[u].add(v)
            adj[v].add(u)
            nodes.add(u)
            nodes.add(v)

        visited: Set[int] = set()
        components = 0

        # BFS 计算连通分量
        for start in nodes:
            if start in visited:
                continue

            components += 1
            q = deque([start])
            visited.add(start)

            while q:
                cur = q.popleft()
                for nxt in adj[cur]:
                    if nxt not in visited:
                        visited.add(nxt)
                        q.append(nxt)

        E = len(edges)
        V = len(nodes)
        target_rank = E - V + components
        is_connected = (components == 1)

        return components, target_rank, is_connected, V, E

    @staticmethod
    def get_connected_components_edges(
        global_edges: Set[Tuple[int, int]]
    ) -> List[Set[Tuple[int, int]]]:
        """
        利用 BFS 探索连通分量，并将全局图物理切分成多个连通量为 1 的子图边集。
        返回: List[Set[Tuple[int, int]]]
        """
        edges = {(min(u, v), max(u, v)) for u, v in global_edges if u != v}
        if not edges:
            return []

        adj: Dict[int, Set[int]] = defaultdict(set)
        nodes: Set[int] = set()
        for u, v in edges:
            adj[u].add(v)
            adj[v].add(u)
            nodes.add(u)
            nodes.add(v)

        visited: Set[int] = set()
        components_edges: List[Set[Tuple[int, int]]] = []

        for start in nodes:
            if start in visited:
                continue

            comp_nodes: Set[int] = set()
            q = deque([start])
            visited.add(start)

            while q:
                cur = q.popleft()
                comp_nodes.add(cur)
                for nxt in adj[cur]:
                    if nxt not in visited:
                        visited.add(nxt)
                        q.append(nxt)

            comp_edges = {
                (u, v)
                for u in comp_nodes
                for v in adj[u]
                if u < v
            }
            if comp_edges:
                components_edges.append(comp_edges)

        return components_edges

    @staticmethod
    def cycle_convert_eids_and_edges(
        cycle: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]],
        adj: Dict[int, Set[int]],
        edge_to_eid: Dict[Tuple[int, int], int]
    ) -> Tuple[Set[int], Set[Tuple[int, int]], bool]:
        """将三元组转换为边ID集合和边集合，并返回有效性（简单无弦环）"""
        nodes = cycle[2]
        if len(nodes) < 3:
            return set(), set(), False
        for n in nodes:
            if len(adj[n] & nodes) != 2:
                return set(), set(), False
        edges_set = set()
        for n in nodes:
            neighbors = adj[n] & nodes
            for nb in neighbors:
                if nb > n:
                    edges_set.add((n, nb))
        eids_set = {edge_to_eid[e] for e in edges_set if e in edge_to_eid}
        if len(edges_set) != len(nodes):
            return set(), set(), False
        return eids_set, edges_set, True

    @staticmethod
    def extract_chord_set(global_edges: Set[Tuple[int, int]]):
        """确定性地提取弦边集和树边集（低度优先策略）"""
        normalized_global = set()
        full_adj = defaultdict(list)
        nodes_set = set()
        for u, v in global_edges:
            u, v = (u, v) if u < v else (v, u)
            normalized_global.add((u, v))
            full_adj[u].append(v)
            full_adj[v].append(u)
            nodes_set.add(u)
            nodes_set.add(v)
        node_degree = {node: len(neighbors) for node, neighbors in full_adj.items()}
        for node in full_adj:
            full_adj[node].sort(key=lambda neighbor: (node_degree[neighbor], neighbor))
        visited = set()
        tree_edges = set()
        tree_adj = defaultdict(list)
        all_nodes = sorted(nodes_set, key=lambda node: (node_degree[node], node))
        for start_node in all_nodes:
            if start_node not in visited:
                queue = deque([(start_node, -1)])
                visited.add(start_node)
                while queue:
                    curr, parent = queue.popleft()
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
    def _validate_and_build_local_path(
        path: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]],
        adj: Dict[int, Set[int]],
        expected_edge_count_diff: int,
    ) -> Optional[Tuple[Set[int], Dict[int, Set[int]]]]:
        """通用路径/环基础校验。路径 diff=-1，环 diff=0。返回 (path_set, local_adj) 或 None。"""
        path_set = set(path[2])
        path_edges = set(path[1])
        if len(path_set) < 3 or len(path_edges) != len(path_set) + expected_edge_count_diff:
            return None
        for u, v in path_edges:
            if u == v or u not in path_set or v not in path_set:
                return None
        local_adj: Dict[int, Set[int]] = defaultdict(set)
        for u, v in path_edges:
            local_adj[u].add(v)
            local_adj[v].add(u)
        start = next(iter(path_set))
        visited = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in local_adj.get(node, set()):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        if len(visited) != len(path_set):
            return None
        return (path_set, local_adj)

    @staticmethod
    def verify_chordless_path(path: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]], adj: Dict[int, Set[int]]) -> bool:
        """验证给定路径是否为无弦路径。"""
        result = StaticMethod._validate_and_build_local_path(path, adj, -1)
        if result is None:
            return False
        path_set, local_adj = result
        endpoints = 0
        for node in path_set:
            local_deg = len(local_adj.get(node, set()))
            global_induced_deg = len(adj.get(node, set()) & path_set)
            if local_deg != global_induced_deg:
                return False
            if local_deg == 1:
                endpoints += 1
            elif local_deg != 2:
                return False
        return endpoints == 2

    @staticmethod
    def verify_chordless_cycle(path: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]], adj: Dict[int, Set[int]]) -> bool:
        """验证给定结构是否为无弦环。"""
        result = StaticMethod._validate_and_build_local_path(path, adj, 0)
        if result is None:
            return False
        path_set, local_adj = result
        for node in path_set:
            local_deg = len(local_adj.get(node, set()))
            global_induced_deg = len(adj.get(node, set()) & path_set)
            if local_deg != 2 or global_induced_deg != 2:
                return False
        return True

    @staticmethod
    def generate_chordless_mapping(
        path: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]], adj: Dict[int, Set[int]]
    ) -> Tuple[List[int], List[int]]:
        """生成给定无弦路径的端点与中间节点分类。"""
        result = StaticMethod._validate_and_build_local_path(path, adj, -1)
        if result is None:
            return [], []
        path_set, local_adj = result
        endpoints: List[int] = []
        midpoints: List[int] = []
        for node in path_set:
            local_deg = len(local_adj.get(node, set()))
            global_induced_deg = len(adj.get(node, set()) & path_set)
            if local_deg != global_induced_deg:
                return [], []
            if local_deg == 1:
                endpoints.append(node)
            elif local_deg == 2:
                midpoints.append(node)
            else:
                return [], []
        return (endpoints, midpoints) if len(endpoints) == 2 else ([], [])

    @staticmethod
    def generate_chordless_cycle_list(
        path: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]],
        adj: Dict[int, Set[int]],
        edge_to_eid: Dict[Tuple[int, int], int],
    ) -> Tuple[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]], bool]:
        """基于无弦路径的两个端点，寻找公共邻居闭合成无弦环。"""
        empty_cycle: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]] = (frozenset(), frozenset(), frozenset())
        result = StaticMethod._validate_and_build_local_path(path, adj, -1)
        if result is None:
            return [empty_cycle], False
        path_set, local_adj = result
        endpoints: List[int] = []
        for node in path_set:
            local_deg = len(local_adj.get(node, set()))
            global_induced_deg = len(adj.get(node, set()) & path_set)
            if local_deg != global_induced_deg:
                return [empty_cycle], False
            if local_deg == 1:
                endpoints.append(node)
            elif local_deg != 2:
                return [empty_cycle], False
        if len(endpoints) != 2:
            return [empty_cycle], False
        endpoint_a, endpoint_b = endpoints
        candidate_nodes = (adj.get(endpoint_a, set()) & adj.get(endpoint_b, set())) - path_set
        forbidden_nodes: Set[int] = set()
        for node in path_set:
            if len(local_adj.get(node, set())) == 2:
                forbidden_nodes.update(adj.get(node, set()))
        candidate_nodes -= forbidden_nodes
        cycles_list: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        for node in candidate_nodes:
            cycle_nodes = path_set | {node}
            if any(len(adj.get(n, set()) & cycle_nodes) != 2 for n in cycle_nodes):
                continue
            edges_set = {
                (min(u, v), max(u, v))
                for u in cycle_nodes
                for v in adj.get(u, set()) & cycle_nodes
                if u < v
            }
            if len(edges_set) != len(cycle_nodes):
                continue
            eids_set: Set[int] = set()
            all_valid = True
            for edge in edges_set:
                eid = edge_to_eid.get(edge)
                if eid is None:
                    all_valid = False
                    break
                eids_set.add(eid)
            if not all_valid:
                continue
            cycles_list.append((frozenset(eids_set), frozenset(edges_set), frozenset(cycle_nodes)))
        return (cycles_list, True) if cycles_list else ([empty_cycle], False)



    @staticmethod
    def _final_incremental_reduction(global_edges: Set[Tuple[int, int]], candidates: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]], global_target_rank: int, initial_basis: Optional[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]] = None
                                     ) -> Tuple[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]], List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]], Set[Tuple[int, int]], bool]:
        """统一增量消元接口"""
        Debug.info(f"🚀 _final_incremental_reduction 启动 | 候选数: {len(candidates)} | 初始基: {len(initial_basis) if initial_basis else 0}")
        global_edges = {(min(u, v), max(u, v)) for u, v in global_edges}
        initial_basis_candidates = initial_basis if initial_basis else []
        candidates = candidates if candidates else []
        cycle_candidates, path_candidates = [], []
        all_candidates = candidates + initial_basis_candidates
        for cyc in all_candidates:
            if not cyc or len(cyc) < 3:
                continue
            node_count, edge_count = len(cyc[2]), len(cyc[1])
            if edge_count == node_count:
                cycle_candidates.append(cyc)
            elif edge_count + 1 == node_count:
                path_candidates.append(cyc)
        Debug.info(f"📊 候选分类 | 环: {len(cycle_candidates)} | 路径: {len(path_candidates)}")

        def bucket_and_sort(candidates):
            buckets = defaultdict(list)
            for cyc in candidates:
                buckets[len(cyc[2])].append(cyc)
            result = []
            for length in sorted(buckets):
                unique = list(set(buckets[length]))
                unique.sort(key=lambda c: max(c[2]) if c[2] else -1, reverse=True)
                result.extend(unique)
            return result

        sorted_cycle_candidates = bucket_and_sort(cycle_candidates)
        sorted_path_candidates = bucket_and_sort(path_candidates)
        reducer = BlockwiseCycleReducer(global_edges, [])
        cycles_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []

        if sorted_cycle_candidates:
            cycles_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(global_edges, sorted_cycle_candidates, global_target_rank)
        cycles_basis_sorted = sorted(cycles_basis, key=lambda c: len(c[2]), reverse=False)
        final_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        final_paths: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        path_edges = set()
        for cycle in cycles_basis_sorted:
            if reducer.add_candidate(cycle):
                final_cycles.append(cycle)
                if len(final_cycles) >= global_target_rank:
                    break
        for path in sorted_path_candidates:
            if reducer.check_independent(path):
                final_paths.append(path)
                path_edges.update(path[1])
        is_full = len(final_cycles) >= global_target_rank
        Debug.info(f"✅ _final_incremental_reduction 完成 | 环基: {len(final_cycles)} | 路径边: {len(path_edges)} | 满秩: {is_full}")
        return final_cycles, final_paths, path_edges, is_full


    # ================================================================
    # 3. 黑洞反查探针
    # ================================================================
    @staticmethod
    def verify_local_blackhole(
        global_edges: Set[Tuple[int, int]],
        candidates: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]
    ) -> Tuple[bool, bool, bool]:
        if not candidates:
            return False, False, False

        global_edges = {(min(u, v), max(u, v)) for u, v in global_edges}
        global_data_init = DataInitialization(global_edges)
        global_target_rank = global_data_init.target_rank

        local_edges = set()
        for cyc in candidates:
            local_edges.update(cyc[1])
        local_edges = {(min(u, v), max(u, v)) for u, v in local_edges}

        if not local_edges:
            return False, False, False

        local_nodes, adj = set(), defaultdict(set)
        for u, v in local_edges:
            local_nodes.update([u, v])
            adj[u].add(v)
            adj[v].add(u)

        visited, components = set(), 0
        for node in local_nodes:
            if node in visited:
                continue
            components += 1
            q = deque([node])
            visited.add(node)
            while q:
                curr = q.popleft()
                for nbr in adj[curr]:
                    if nbr not in visited:
                        visited.add(nbr)
                        q.append(nbr)

        local_target_rank = len(local_edges) - len(local_nodes) + components
        is_black = components == 1

        cycle_candidates = [cyc for cyc in candidates if len(cyc[2]) == len(cyc[1])]
        reduced_basis, _ = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges, cycle_candidates, local_target_rank
        )
        actual_rank = len(reduced_basis)
        is_full_local = actual_rank == local_target_rank
        is_global_edges = local_edges == global_edges and local_target_rank == global_target_rank

        Debug.info(
            f"🔍 verify_local_blackhole | "
            f"局部边={len(local_edges)} | 局部点={len(local_nodes)} | "
            f"components={components} | 目标秩={local_target_rank} | "
            f"实际秩={actual_rank} | black={is_black} | "
            f"full={is_full_local} | global={is_global_edges}"
        )
        return is_black, is_full_local, is_global_edges



# ==========================================
# 数据初始化 (DataInitialization)
# ==========================================
class DataInitialization:
    """
    数据初始化类，负责构建图的邻接表、计算连通分量、计算目标电路秩（Betti Number），
    以及生成基于 BFS 的生成树基础环（Fundamental Cycles）。

    ✅ 所有图算法逻辑已下沉到 StaticMethod，本类只负责组装与调用。
    """
    def __init__(self, global_edges: Set[Tuple[int, int]], debug: bool = True):
        self.debug = debug
        start_t = time.time()

        # ---- 边规范化（去自环 + min/max） ----
        self.global_edges: Set[Tuple[int, int]] = {
            (min(u, v), max(u, v)) for u, v in global_edges if u != v
        }

        # ---- 构建邻接表 + 边 ID ----
        self.adj: Dict[int, Set[int]] = defaultdict(set)
        self.edge_to_eid: Dict[Tuple[int, int], int] = defaultdict(int)
        self.node_to_edges: Dict[int, Set[Tuple[int, int]]] = defaultdict(set)
        for idx, edge in enumerate(sorted(self.global_edges)):
            u, v = min(edge), max(edge)
            self.adj[u].add(v)
            self.adj[v].add(u)
            self.edge_to_eid[(u, v)] = idx
            self.node_to_edges[u].add((u, v))
            self.node_to_edges[v].add((u, v))

        # ---- 节点集 ----
        self.nodes: Set[int] = set()
        for u, v in self.global_edges:
            self.nodes.add(u)
            self.nodes.add(v)

        self.mapping: Dict[Tuple[int, int], Set[int]] = {}
        self.target_rank = -1

        self.time_start = time.time()

        if self.debug:
            Debug.detail(
                f"[DataInit] _build_graph 完成  E={len(self.global_edges)}, "
                f"V={len(self.nodes)}  [{time.time() - start_t:.4f}s]"
            )

        # ============================================================
        # ✅ 调用 StaticMethod：连通分量数量 + 目标秩 + 连通性
        #    (C, target_rank, is_connected, V, E)
        # ============================================================
        _t = time.time()
        (
            self.connected_components_count,
            self.target_rank,
            self.is_connected,
            _V,
            _E,
        ) = StaticMethod.compute_components_and_rank(self.global_edges)

        if self.debug:
            Debug.detail(
                f"[DataInit] 连通分量计算: C={self.connected_components_count} "
                f"({'连通' if self.is_connected else '非连通'})  [{time.time() - _t:.4f}s]"
            )
            Debug.info(
                f"[DataInit] E={_E}, V={_V}, C={self.connected_components_count} "
                f"=> 目标秩(Target Rank) = {self.target_rank}"
            )

        # ============================================================
        # ✅ 调用 StaticMethod：拆分每个连通分量的边集
        #    供 FHBackMapperFinal 等下游使用
        # ============================================================
        self.connected_components_edges: List[Set[Tuple[int, int]]] = (
            StaticMethod.get_connected_components_edges(self.global_edges)
        )

        # ---- 为 FHBackMapperFinal 预留 ----
        self.edge_to_cycles: Dict[
            Tuple[int, int],
            List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]
        ] = defaultdict(list)
        self.edge_to_cycles_deferred: Dict[
            Tuple[int, int], Tuple[Set, Set, Set, Set]
        ] = defaultdict(lambda: (set(), set(), set(), set()))
        self.dfs_dirs_deferred: Dict[Tuple[int, int], Tuple] = {}

        # ---- 弦边到基本环的映射 ----
        self.basis: List[
            Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]
        ] = []
        self.chord_to_cycle: Dict[
            Tuple[int, int],
            Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]
        ] = defaultdict(lambda: (frozenset(), frozenset(), frozenset()))

        self.node_to_other_edges: Dict[int, Set[Tuple[int, int]]] = defaultdict(set)
        self.edges_closed_cycles_len_mapping: Dict[int, Set[Tuple[int, int]]] = defaultdict(set)

        # ---- 生成全局生成树基本环 ----
        self.basis, self.chord_to_cycle = self.build_global_spanning_tree_basis()
        self.duration = time.time() - self.time_start

    def generate_node_to_other_edges(self) -> Dict[int, Set[Tuple[int, int]]]:
        """
        构建 node → 该节点与“不在其任一相邻节点邻域中”的节点组成的边。

        对每条边 (u, v)：
            - node ∈ adj[u] \\ adj[v] → 记下 (u, node)
            - node ∈ adj[v] \\ adj[u] → 记下 (v, node)
        """
        self.node_to_other_edges = defaultdict(set)
        for u, v in self.global_edges:
            for node in self.adj[u] - self.adj[v]:
                self.node_to_other_edges[u].add((min(node, u), max(node, u)))
            for node in self.adj[v] - self.adj[u]:
                self.node_to_other_edges[v].add((min(node, v), max(node, v)))
        return self.node_to_other_edges


    # ================================================================
    # 全局生成树基本环
    #   - 起点选择 + 低度优先 BFS 建树：类内闭包，完全自包含
    #   - 本方法只做：弦边 → 树上唯一路径 → 基本环三元组
    # ================================================================
    def build_global_spanning_tree_basis(
        self,
        edges_closed_cycles_len_mapping: Optional[Dict[int, Set[Tuple[int, int]]]] = None,
    ) -> Tuple[
        List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
        Dict[Tuple[int, int],
            Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]
    ]:
        """
        全局生成树基本环生成器。

        参数:
            edges_closed_cycles_len_mapping:
                - 外部传入的“环长 → 边集”映射。
                - 若为 None，则回退使用 self.edges_closed_cycles_len_mapping。
                - 生成树起点选择规则：
                    取该映射中最大的 key（最长环长）对应的边集，
                    收集其全部端点，在该边集构成的子图内，
                    选“邻接数最少（并列取节点号最小）”的点作为 BFS 根。
                - 若映射为空 / None 且 self 里也为空，则退化为纯低度优先。
        """
        t0 = time.time()

        normalized_global = self.global_edges
        if not normalized_global:
            Debug.info("🌲 全局生成树 | 空图")
            return [], {}

        # ✅ 外部优先，其次回退 self
        mapping_source: Dict[int, Set[Tuple[int, int]]] = (
            edges_closed_cycles_len_mapping
            if edges_closed_cycles_len_mapping is not None
            else self.edges_closed_cycles_len_mapping
        )

        # ============================================================
        # 闭包 1：选生成树根节点
        #   - 从 mapping_source 的最长环长桶子图里取邻接数最少的端点
        # ============================================================
        def _pick_preferred_start() -> Optional[int]:
            if not mapping_source:
                return None
            longest_len = max(mapping_source.keys())
            longest_edges = mapping_source[longest_len]

            # ✅ 在 longest_edges 这个子图里统计每个端点的邻接数
            sub_deg: Dict[int, int] = defaultdict(int)
            for eu, ev in longest_edges:
                sub_deg[eu] += 1
                sub_deg[ev] += 1

            if not sub_deg:
                return None

            # 桶内邻接最少；并列取节点号最小
            preferred = min(sub_deg.keys(), key=lambda n: (sub_deg[n], n))
            Debug.info(
                f"🌲 生成树起点偏好 | 最长环长={longest_len} | "
                f"候选节点数={len(sub_deg)} | "
                f"起点={preferred} (桶内邻接数={sub_deg[preferred]})"
            )
            return preferred

        # ============================================================
        # 闭包 2：低度优先 BFS 建树（支持指定根）
        # ============================================================
        def _build_tree(
            root: Optional[int],
        ) -> Tuple[
            Set[Tuple[int, int]],                       # chord_edges
            Set[Tuple[int, int]],                       # tree_edges
            Dict[int, List[int]],                       # tree_adj
        ]:
            full_adj: Dict[int, List[int]] = defaultdict(list)
            nodes_set: Set[int] = set()
            for u, v in normalized_global:
                full_adj[u].append(v)
                full_adj[v].append(u)
                nodes_set.add(u)
                nodes_set.add(v)

            node_degree = {n: len(full_adj[n]) for n in nodes_set}
            for n in full_adj:
                full_adj[n].sort(key=lambda nb: (node_degree[nb], nb))

            order = sorted(nodes_set, key=lambda n: (node_degree[n], n))
            # ✅ 若指定根且存在，提到最前，其余保持原序
            if root is not None and root in nodes_set:
                order.remove(root)
                order.insert(0, root)

            visited: Set[int] = set()
            tree_edges: Set[Tuple[int, int]] = set()
            tree_adj: Dict[int, List[int]] = defaultdict(list)

            for start in order:
                if start in visited:
                    continue
                visited.add(start)
                q = deque([start])
                while q:
                    curr = q.popleft()
                    for nb in full_adj[curr]:
                        if nb in visited:
                            continue
                        visited.add(nb)
                        edge = (min(curr, nb), max(curr, nb))
                        tree_edges.add(edge)
                        tree_adj[curr].append(nb)
                        tree_adj[nb].append(curr)
                        q.append(nb)

            chord_edges = normalized_global - tree_edges
            return chord_edges, tree_edges, tree_adj

        # ============================================================
        # 执行闭包：先选根，再建树
        # ============================================================
        root = _pick_preferred_start()
        chord_edges, tree_edges, tree_adj = _build_tree(root)

        # ---- 边 ID 映射（保持与 self.edge_to_eid 一致） ----
        edge_to_eid = self.edge_to_eid

        # ---- 生成基本环 ----
        fundamental_cycles: List[
            Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]
        ] = []
        chord_to_cycle: Dict[
            Tuple[int, int],
            Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]
        ] = {}

        def bfs_path(src: int, dst: int) -> Optional[List[int]]:
            """在生成树中查找 src → dst 的唯一路径"""
            if src == dst:
                return [src]
            parent_in_tree: Dict[int, int] = {}
            q = deque([src])
            parent_in_tree[src] = -1
            found = False
            while q:
                curr = q.popleft()
                if curr == dst:
                    found = True
                    break
                for nb in tree_adj[curr]:
                    if nb not in parent_in_tree:
                        parent_in_tree[nb] = curr
                        q.append(nb)
            if not found:
                return None
            path: List[int] = []
            cur = dst
            while cur != -1:
                path.append(cur)
                cur = parent_in_tree[cur]
            path.reverse()
            return path

        for u, v in sorted(chord_edges):
            path = bfs_path(u, v)
            if path is None or len(path) < 2:
                Debug.warn(f"⚠️ 路径查找失败：边 ({u},{v})")
                continue

            full_path = path
            if len(full_path) < 3:
                continue

            # 构建环边集（路径边 + 弦边）
            cycle_edges: Set[Tuple[int, int]] = set()
            for i in range(len(full_path) - 1):
                a, b = full_path[i], full_path[i + 1]
                cycle_edges.add((min(a, b), max(a, b)))

            chord_edge = (min(u, v), max(u, v))
            cycle_edges.add(chord_edge)

            # 校验所有边都在全局边集中
            missing = [e for e in cycle_edges if e not in edge_to_eid]
            if missing:
                Debug.warn(
                    f"⚠️ 边缺失：{missing}，弦边=({u},{v})，路径={full_path}"
                )
                continue

            cycle_nodes = frozenset(full_path)
            cycle_eids = frozenset(edge_to_eid[e] for e in cycle_edges)

            cycle_tuple = (cycle_eids, frozenset(cycle_edges), cycle_nodes)
            fundamental_cycles.append(cycle_tuple)
            chord_to_cycle[chord_edge] = cycle_tuple

        # ---- 与理论秩对比 ----
        theoretical_rank = (
            len(normalized_global)
            - len(self.nodes)
            + self.connected_components_count
        )
        if len(fundamental_cycles) != theoretical_rank:
            Debug.warn(
                f"⚠️ 全局生成树环数异常 | 实际={len(fundamental_cycles)} "
                f"理论秩={theoretical_rank}"
            )

        self.basis = fundamental_cycles
        self.chord_to_cycle = chord_to_cycle

        Debug.info(
            f"🌲 全局生成树完成 | 边={len(normalized_global)} 点={len(self.nodes)} "
            f"分量={self.connected_components_count} | "
            f"树边={len(tree_edges)} 弦边={len(chord_edges)} | "
            f"基本环={len(fundamental_cycles)} (理论秩={theoretical_rank})"
        )
        Debug.timing("✔ 全局生成树完成", time.time() - t0)
        return self.basis, self.chord_to_cycle




# =====================================================
# BlockwiseCycleReducer (基于 CSR 稀疏矩阵维度的独立消元)
# =====================================================
class BlockwiseCycleReducer:
    def __init__(
        self,
        global_edges: Set[Tuple[int, int]],
        candidates: Optional[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]] = None
    ) -> None:
        Debug.class_debug(__class__.__name__, "Initializing BlockwiseCycleReducer")
        self.global_edges: Set[Tuple[int, int]] = {(u, v) if u < v else (v, u) for u, v in global_edges if u != v}
        self.candidates: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = candidates or []
        self.nodes: Set[int] = {u for e in self.global_edges for u in e}
        self.adj: Dict[int, Set[int]] = defaultdict(set)

        # ✅ 缺失键返回 -1，与合法 eid 不冲突
        self.edge_to_idx: Dict[Tuple[int, int], int] = defaultdict(lambda: -1)
        self.eid_to_edge: Dict[int, Tuple[int, int]] = defaultdict(lambda: (-1, -1))

        self.global_edges, self.edge_to_idx = self._build_graph()
        self.eid_count: int = len(self.edge_to_idx)

        self.connected_components_count: int = self.get_connected_components_count()
        self.is_connected: bool = (self.connected_components_count == 1)
        self.target_rank: int = len(self.global_edges) - len(self.nodes) + self.connected_components_count

        # 统一输出结构
        self.valid_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []

        # CSR 引擎专属状态
        self.block_size: int = 64
        self.candidate_data: array.array = array.array('Q')
        self.candidate_map: Dict[int, Tuple[int, int]] = {}

        self._preload_historical_candidate()

    def _build_graph(self) -> Tuple[Set[Tuple[int, int]], Dict[Tuple[int, int], int]]:
        """
        构建邻接表与局部 EID 映射。
        - 规范化边：(min, max)
        - 跳过自环
        - 去重
        - 返回的边集与 edge_to_idx 的键集完全一致
        """
        filtered_edges: Set[Tuple[int, int]] = set()

        eid: int = 0
        for u, v in sorted(self.global_edges):
            if u == v:
                # 跳过自环
                continue
            un, vn = min(u, v), max(u, v)
            edge = (un, vn)

            # 去重（sorted 后重复边会相邻，但直接用 set 判断更稳）
            if edge in self.edge_to_idx:
                continue

            filtered_edges.add(edge)
            self.nodes.update((un, vn))
            self.adj[un].add(vn)
            self.adj[vn].add(un)

            self.edge_to_idx[edge] = eid
            self.eid_to_edge[eid] = edge
            eid += 1

        return filtered_edges, self.edge_to_idx

    def get_connected_components_count(self) -> int:
        if not self.nodes:
            return 0
        visited: Set[int] = set()
        components: int = 0
        for node in self.nodes:
            if node not in visited:
                components += 1
                q: deque = deque([node])
                visited.add(node)
                while q:
                    curr: int = q.popleft()
                    for nbr in self.adj[curr]:
                        if nbr not in visited:
                            visited.add(nbr)
                            q.append(nbr)
        return components

    def _preload_historical_candidate(self) -> None:
        for cyc in self.candidates:
            self.add_candidate(cyc)

    def eids_to_vector(
        self,
        cycle: Tuple[
            FrozenSet[int],
            FrozenSet[Tuple[int, int]],
            FrozenSet[int]
        ]
    ) -> array.array:
        """
        根据 cycle[1] 的真实边集合构建 CSR 块压缩向量。

        cycle[0] 仅作为缓存，不参与 GF(2) 向量构造。
        当前 Reducer 使用自己的 edge_to_idx，避免 EID 空间不一致。
        """

        if not isinstance(cycle, tuple) or len(cycle) != 3:
            return array.array('Q')

        edges = cycle[1]
        nodes = cycle[2]

        if not edges or not nodes:
            return array.array('Q')

        # 简单环 / 简单路径的基本边数约束
        if len(edges) not in {
            len(nodes) - 1,
            len(nodes)
        }:
            return array.array('Q')

        # --------------------------------------------------
        # 真实边 → 当前 Reducer 的局部 EID
        # --------------------------------------------------
        local_eids = []

        for edge in edges:
            u, v = edge
            edge = (min(u, v), max(u, v))

            eid = self.edge_to_idx[edge]

            if eid == -1:
                # 候选边不属于当前全局图
                return array.array('Q')

            local_eids.append(eid)

        if not local_eids:
            return array.array('Q')

        # --------------------------------------------------
        # 构建 CSR block vector
        # 格式：
        # [block_id, block_value, block_id, block_value, ...]
        # --------------------------------------------------
        vector_data: List[int] = []

        current_blk = -1
        current_val = 0

        for eid in sorted(local_eids):
            blk = eid >> 6
            rem = eid & 63

            if blk != current_blk:
                if current_blk != -1:
                    vector_data.extend(
                        (current_blk, current_val)
                    )

                current_blk = blk
                current_val = 0

            current_val |= (1 << rem)

        if current_blk != -1:
            vector_data.extend(
                (current_blk, current_val)
            )

        return array.array('Q', vector_data)

    def find_pivot_and_reduce(self, vector: array.array) -> Tuple[array.array, Optional[int]]:
        while len(vector) > 0:
            last_blk_idx: int = vector[-2]
            last_blk_val: int = vector[-1]
            if last_blk_val == 0:
                vector.pop()
                vector.pop()
                continue
            high_bit: int = last_blk_val.bit_length() - 1
            pivot: int = (last_blk_idx << 6) + high_bit
            if pivot in self.candidate_map:
                start, length = self.candidate_map[pivot]
                vector = self.xor_with_candidate(vector, self.candidate_data, start, length)
            else:
                return vector, pivot
        return vector, None

    def xor_with_candidate(self, v1: array.array, pool: array.array, start: int, length: int) -> array.array:
        res_list: List[int] = []
        i: int = 0
        j: int = 0
        len1: int = len(v1)
        len2: int = length
        while i < len1 and j < len2:
            b1: int = v1[i]
            b2: int = pool[start + j]
            if b1 < b2:
                res_list.extend((b1, v1[i + 1]))
                i += 2
            elif b1 > b2:
                res_list.extend((b2, pool[start + j + 1]))
                j += 2
            else:
                new_val: int = v1[i + 1] ^ pool[start + j + 1]
                if new_val:
                    res_list.extend((b1, new_val))
                i += 2
                j += 2
        if i < len1:
            res_list.extend(v1[i:])
        if j < len2:
            res_list.extend(pool[start + j : start + len2])
        return array.array('Q', res_list)

    def check_independent(self, cyc: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]) -> bool:
        # 用真实边集 cyc[1] 判断；eids_to_vector 内部已校验简单环/路径边数并重新映射
        if not isinstance(cyc, tuple) or len(cyc) != 3 or not cyc[1]:
            return False
        vector: array.array = self.eids_to_vector(cyc)
        vec_copy: array.array = array.array('Q', vector)
        _, pivot = self.find_pivot_and_reduce(vec_copy)
        return pivot is not None

    def add_candidate(self, cyc: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]) -> Optional[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        if not isinstance(cyc, tuple) or len(cyc) != 3:
            return None
        if not cyc[1]:  # 用真实边集判断，不再用 cyc[0]
            return None
        vector: array.array = self.eids_to_vector(cyc)
        reduced_vector, pivot = self.find_pivot_and_reduce(vector)

        if pivot is not None:
            start_idx: int = len(self.candidate_data)
            length: int = len(reduced_vector)
            self.candidate_data.extend(reduced_vector)
            self.candidate_map[pivot] = (start_idx, length)
            self.valid_basis.append(cyc)
            return cyc
        return None





# ==========================================
# 动态级联权重管理器 (Cascade Weight Manager)
# ==========================================
class CascadeWeightManager:
    """
    动态级联权重管理器。
    核心排序：基于未覆盖边的边频率排序
    自动冷热切换：候选环数量 > 全局秩 → 热边优先，否则冷边优先
    """
    def __init__(self, global_edges: Set[Tuple[int, int]],
                 candidates: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
                 new_edges: Optional[Set[Tuple[int, int]]] = None):
        # ---------- 基础数据 ----------
        self.global_edges = {(u, v) if u < v else (v, u) for u, v in global_edges if u != v}
        gd = DataInitialization(self.global_edges)
        self.global_adj = gd.adj
        self.global_edge_to_eid = gd.edge_to_eid
        self.global_target_rank = gd.target_rank

        # ---------- 无弦环校验过滤 ----------
        original_count = len(candidates)
        candidates = [cyc for cyc in candidates
                            if StaticMethod.verify_chordless_cycle(cyc, self.global_adj) or StaticMethod.verify_chordless_path(cyc, self.global_adj)]
        filtered_count = len(candidates)
        if original_count != filtered_count:
            Debug.info(f"无弦环过滤: {original_count} -> {filtered_count}")

        self.candidates = candidates
        self.sort_candidates_list: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []

        # ---------- 未覆盖边 ----------
        if new_edges is None:
            self.new_edges = self.global_edges.copy()
        else:
            self.new_edges = {(u, v) if u < v else (v, u) for u, v in new_edges if u != v}

        # ---------- 边频率统计 ----------
        self.edge_freq: Dict[Tuple[int, int], int] = defaultdict(int)

        # ---------- 自动冷热切换 ----------
        self.use_hot = len(self.candidates) > self.global_target_rank
        self.descending_weight = self.use_hot  # True=热边优先，False=冷边优先

        Debug.info(f"权重管理器初始化，候选环数={len(candidates)}，"
                   f"全局秩={self.global_target_rank}，"
                   f"未覆盖边数={len(self.new_edges)}，"
                   f"策略={'热边' if self.use_hot else '冷边'}排序")

    # ============================================================
    # 构建热度图：统计未覆盖边的频率（直接使用 cycle[1]）
    # ============================================================
    def _build_heat_map(self):
        """构建热度图：统计每个未覆盖边在候选环中出现的频率"""
        if not self.new_edges:
            Debug.warn("  ⚠️ 未覆盖边集合为空，跳过热度图构建")
            return

        t_start = time.time()
        self.edge_freq.clear()

        for c in self.candidates:
            for edge in c[1]:          # 直接使用存储的边集合
                if edge in self.new_edges:
                    self.edge_freq[edge] += 1

        elapsed = time.time() - t_start
        Debug.info(f"  [热度图] 统计完成，耗时 {elapsed:.2f}s，"
                  f"有热度的边数: {len(self.edge_freq)}")

    # ============================================================
    # 核心排序实现：只按边频率排序（直接使用三元组）
    # ============================================================
    def sort_candidates(self) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """根据包含未覆盖边的冷热程度排序（自动冷热切换）"""
        if not self.candidates:
            return []

        self._build_heat_map()

        # 计算每个环的权重（基于未覆盖边的频率）
        cycle_weight_list = []
        for c in self.candidates:
            n_len = len(c[2])          # 节点数
            weight = 0
            for edge in c[1]:          # 边集合
                if edge in self.new_edges:
                    weight += self.edge_freq.get(edge, 0)
            cycle_weight_list.append(((n_len, weight), c))

        # 自动冷热切换排序
        if self.descending_weight:
            # 热边优先：长度升序 → 权重降序
            cycle_weight_list.sort(key=lambda x: (x[0][0], -x[0][1]))
            sort_type = "热边优先"
        else:
            # 冷边优先：长度升序 → 权重升序
            cycle_weight_list.sort(key=lambda x: (x[0][0], x[0][1]))
            sort_type = "冷边优先"

        # 按长度分桶（可选）
        buckets = defaultdict(list)
        for _, cycle in cycle_weight_list:
            buckets[len(cycle[2])].append(cycle)

        self.sort_candidates_list = []
        for len_key in sorted(buckets.keys()):
            self.sort_candidates_list.extend(buckets[len_key])

        Debug.info(f"  [{sort_type}排序] 完成，环数: {len(self.sort_candidates_list)}")
        return self.sort_candidates_list

    # ============================================================
    # 静态排序入口：自动冷热切换（直接使用三元组）
    # ============================================================
    @staticmethod
    def final_dimension_sort(global_edges, candidates) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        wm = CascadeWeightManager(global_edges, candidates)
        return wm.sort_candidates()


    # ============================================================
    # CSR 排序（静态）—— 从真实边集重新映射 EID，保证 pivot 正确
    # ============================================================
    @staticmethod
    def final_CSR_dimension_sort(global_edges, candidates) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        t_start = time.time()

        # ✅ 统一 EID 空间：按 (min,max) 标准化 + 排序后编号
        normalized_edges = sorted((min(u, v), max(u, v)) for u, v in global_edges if u != v)
        edge_to_eid: Dict[Tuple[int, int], int] = {edge: i for i, edge in enumerate(normalized_edges)}

        scored = []
        for cyc in candidates:
            # ✅ 用 cycle[1]（权威真实边集）重新映射，绝不使用 cyc[0] 的缓存 EID
            eids = {
                edge_to_eid[(min(u, v), max(u, v))]
                for u, v in cyc[1]
                if (min(u, v), max(u, v)) in edge_to_eid
            }
            if eids:
                pivot = max(eids)
                scored.append((len(cyc[2]), pivot, cyc))

        scored.sort(key=lambda x: (x[0], -x[1]))
        result = [cyc for _, _, cyc in scored]

        Debug.info(f"[CSR排序] 耗时 {time.time()-t_start:.2f}s，环数: {len(result)}")
        return result

    # ============================================================
    # BigInt 排序（静态）—— 从真实边集重新映射 EID，保证 pivot 正确
    # ============================================================
    @staticmethod
    def final_BigInt_dimension_sort(global_edges, candidates) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        t_start = time.time()

        # ✅ 统一 EID 空间
        normalized_edges = sorted((min(u, v), max(u, v)) for u, v in global_edges if u != v)
        edge_to_eid: Dict[Tuple[int, int], int] = {edge: i for i, edge in enumerate(normalized_edges)}

        cyc_with_pivot = []
        for cyc in candidates:
            # ✅ 用 cycle[1] 重新映射
            eids = {
                edge_to_eid[(min(u, v), max(u, v))]
                for u, v in cyc[1]
                if (min(u, v), max(u, v)) in edge_to_eid
            }
            if eids:
                pivot = max(eids)
                cyc_with_pivot.append((cyc, pivot))

        # 统计主元频率
        pivot_freq = defaultdict(int)
        for _, pivot in cyc_with_pivot:
            pivot_freq[pivot] += 1

        scored = []
        for cyc, pivot in cyc_with_pivot:
            scored.append((len(cyc[2]), pivot_freq[pivot], pivot, cyc))

        scored.sort(key=lambda x: (x[0], -x[1], -x[2]))
        result = [cyc for _, _, _, cyc in scored]

        Debug.info(f"[BigInt排序] 耗时 {time.time()-t_start:.2f}s，环数: {len(result)}")
        return result



# ==========================================
# 终极单维流程调用包 (Single-Dim Pipeline Wrapper)
# ==========================================
class SingleDimensionCycleReducer:
    """单环长维度消元器：historical_basis 只作初始状态，消元只发生在 run_reduction()。"""

    def __init__(
        self,
        global_edges,
        candidates,        # 三元组列表，须同一环长
        global_target_rank: int,
        historical_basis=None,   # 三元组列表
    ):
        self.global_edges = {(min(u, v), max(u, v)) for u, v in global_edges if u != v}
        self.global_target_rank = global_target_rank
        self.candidates = list(dict.fromkeys(candidates))
        self.historical_basis = list(dict.fromkeys(historical_basis or []))
        self.weight_manager = CascadeWeightManager(self.global_edges, self.candidates)
        self.sorted_cycles = self.weight_manager.sort_candidates()
        self.reducer = BlockwiseCycleReducer(self.global_edges, [])
        self.valid_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        for c in self.sorted_cycles[0: min(self.global_target_rank, len(self.sorted_cycles))]:
            add_cyc = self.reducer.add_candidate(c)
            if add_cyc:
                self.valid_basis.append(add_cyc)
        self.candidates_sorted = sorted(list(set(self.valid_basis))) + sorted(list(set(self.candidates) - set(self.sorted_cycles[0: min(self.global_target_rank, len(self.sorted_cycles))])), key=lambda x: len(x))

    def run_reduction(self) -> Tuple[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]], bool]:
        # =================================================================
        # 🚀 降维打击开光：直接在心脏植入CSR极速引擎！
        self.valid_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidates=self.candidates_sorted,
            global_target_rank=self.global_target_rank
        )

        if len(self.valid_basis) >= self.global_target_rank:
            Debug.fuse(f"[沙盒急停] 局部基底数({len(self.valid_basis)}) 已达满秩上限，即刻熔断")
            
        return self.valid_basis, len(self.valid_basis) >= self.global_target_rank


    @staticmethod
    def _final_incremental_reduction(global_edges, candidates, global_target_rank, historical_basis=None):
        reducer = SingleDimensionCycleReducer(
            global_edges=global_edges,
            candidates=candidates,
            global_target_rank=global_target_rank,
            historical_basis=historical_basis,
        )
        return reducer.run_reduction()


# ==========================================
# CSR 黑洞噬元引擎 (CSR Blackhole Devourer)
# ==========================================
class CSRBlackholeDevourer:
    class Mode(enum.Enum):
        SAFE_ELIMINATION = "安全消元"
        STANDARD_PROBE = "常规探测"
        ALTERNATING_ANNIHILATION = "交替湮灭"
        COMPLETED = "完成"

    DEFAULT_ENABLE_PROGRESS_BAR = True

    class State:
        def __init__(self, pending_cycles: List[Tuple[int, Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]], total_cycles: int):
            self.valid_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
            self.valid_basis_edges: List[FrozenSet[Tuple[int, int]]] = []   # frozenset
            self.pending_cycles = pending_cycles          # (pivot, cycle)
            self.failed_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
            self.blackhole_edges: Set[Tuple[int, int]] = set()
            self.is_blackhole_active: bool = False
            self.current_mode = CSRBlackholeDevourer.Mode.STANDARD_PROBE
            self.total_cycles: int = total_cycles
            self.safe_elimination_count: int = 0
            self.annihilation_count: int = 0
            self.last_render_time: float = 0.0
            self.last_bh_log_time: float = 0.0
            self.last_switch_log_time: float = 0.0
            self._reserved_cycles: List[Tuple[int, Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]] = []
            self._processed_count: int = 0
            self._rejected_count: int = 0
            self._bh_call_count: int = 0
            self._bh_total_time: float = 0.0

        def add_basis(self, cycle: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]], edges: FrozenSet[Tuple[int, int]]):
            self.valid_basis.append(cycle)
            self.valid_basis_edges.append(edges)

        def switch_mode(self, new_mode):
            self.current_mode = new_mode
            return new_mode

        def update_pending(self, new_pending) -> int:
            self.pending_cycles = new_pending
            return len(new_pending)

        def clear_failed(self):
            self.failed_cycles.clear()

    def __init__(self,
                 global_edges: Set[Tuple[int, int]],
                 candidates: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
                 global_target_rank: int,
                 enable_progress_bar: Optional[bool] = None):
        self.global_edges: Set[Tuple[int, int]] = {(u, v) if u < v else (v, u) for u, v in global_edges if u != v}
        self.global_target_rank = global_target_rank
        self.enable_progress_bar = (
            self.DEFAULT_ENABLE_PROGRESS_BAR
            if enable_progress_bar is None
            else enable_progress_bar
        )
        self.start_time = time.time()
        self.engine_name = "\nCSRBlackholeDevourer"

        self.adj = defaultdict(set)
        for u, v in self.global_edges:
            self.adj[u].add(v)
            self.adj[v].add(u)

        self.reducer = BlockwiseCycleReducer(self.global_edges, [])
        self.edge_to_idx = self.reducer.edge_to_idx

        # 初始排序（使用统一的排序器）
        self.sorted_cycles = CascadeWeightManager.final_CSR_dimension_sort(
            self.global_edges, candidates
        )


        self.total_candidate_count = len(self.sorted_cycles)

        # 预消元
        pre_limit = min(self.global_target_rank, len(self.sorted_cycles))
        temp_state = self.State([], 0)
        for cycle in self.sorted_cycles[:pre_limit]:
            added = self.reducer.add_candidate(cycle)
            if added is not None:
                edges = added[1]   # frozenset
                if edges:
                    temp_state.add_basis(added, edges)
            else:
                temp_state.failed_cycles.append(cycle)

        # 构建 pending 三元组 (pivot, cycle)
        remaining = self.sorted_cycles[pre_limit:]
        pending_cycles = []
        for cycle in remaining:
            if cycle[0]:   # 有 eids
                pivot = max(cycle[0])
                pending_cycles.append((pivot, cycle))

        self.state = self.State(pending_cycles, self.total_candidate_count)
        for basis_cycle, basis_edges in zip(temp_state.valid_basis, temp_state.valid_basis_edges):
            self.state.add_basis(basis_cycle, basis_edges)
        self.state.failed_cycles = temp_state.failed_cycles

    # ---------- 委托方法 ----------
    def switch_mode(self, new_mode) -> 'CSRBlackholeDevourer.Mode':
        return self.state.switch_mode(new_mode)

    def update_pending(self, new_pending) -> int:
        return self.state.update_pending(new_pending)

    # ---------- 直接使用 cycle[1] 获取边集 ----------
    def _get_cycle_edges(self, cycle: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]) -> FrozenSet[Tuple[int, int]]:
        return cycle[1]

    def _render_progress(self):
        if not self.enable_progress_bar:
            return
        now = time.time()
        if now - self.state.last_render_time < 3.0 and self.state.pending_cycles:
            return
        self.state.last_render_time = now
        processed = self.state.total_cycles - len(self.state.pending_cycles)
        total = self.state.total_cycles
        mode_name = self.state.current_mode.value
        bh_icon = "⚫" if self.state.is_blackhole_active else "○"
        msg = f"{self.engine_name} {mode_name} | 基底: {len(self.state.valid_basis)} {bh_icon}"
        Debug.progress(msg, processed, total)
    

    @staticmethod
    def _compute_blackhole(edges: Set[Tuple[int, int]],
                           nodes: Set[int],
                           basis_edges_list: List[FrozenSet[Tuple[int, int]]]):
        local_basis_count = sum(1 for bes in basis_edges_list if bes.issubset(edges))
        parent = {n: n for n in nodes}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        comps = len(nodes)
        for u, v in edges:
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[ru] = rv
                comps -= 1
        rank = len(edges) - len(nodes) + comps
        is_closed = (local_basis_count >= rank) and (comps == 1)
        return is_closed, rank, comps, local_basis_count

    # ---------- 前置路由（统一接口） ----------
    def _handle_probe(self):
        state = self.state
        if state is None:
            return
        if not state.pending_cycles:
            self.switch_mode(self.Mode.COMPLETED)
            return

        # 最终冲刺
        if len(state.pending_cycles) <= self.global_target_rank:
            Debug.info(f"  🏁 剩余环数({len(state.pending_cycles)})≤目标秩，进入最终冲刺")
            cycle_to_item = {item[1]: item for item in state.pending_cycles}
            for pivot, cycle in state.pending_cycles:
                if len(state.valid_basis) >= self.global_target_rank:
                    break
                added = self.reducer.add_candidate(cycle)
                if added is not None:
                    edges = added[1]
                    if edges:
                        state.add_basis(added, edges)
                    else:
                        state.failed_cycles.append(cycle)
                else:
                    state.failed_cycles.append(cycle)
            self.update_pending([])
            state._reserved_cycles = []
            self.switch_mode(self.Mode.COMPLETED)
            if len(state.valid_basis) >= self.global_target_rank:
                Debug.done("🎯 最终冲刺达成目标秩！")
            else:
                Debug.warn(f"⚠️ 候选环耗尽，基底数 {len(state.valid_basis)}，未达目标秩 {self.global_target_rank}")
            self._render_progress()
            return

        # 切片
        state.pending_cycles = sorted(state.pending_cycles, key=lambda x: len(x[1]))
        batch_size = min(max(self.global_target_rank // 10, 1), len(state.pending_cycles))
        batch = state.pending_cycles[:batch_size]
        remaining = state.pending_cycles[batch_size:]

        # 计算 basis_edges 并排序分层
        basis_edges = set().union(*state.valid_basis_edges) if state.valid_basis_edges else set()
        batch.sort(key=lambda item: len(item[1][1] - basis_edges))   # cycle[1] 是 edges

        batch_cycle_to_item = {item[1]: item for item in batch}
        inner, mid, outer = [], [], []
        for pivot, cycle in batch:
            edges = cycle[1]
            missing = len(edges - basis_edges)
            if missing == 0:
                inner.append(cycle)
            elif missing == 1:
                mid.append(cycle)
            else:
                outer.append(cycle)

        # 消元细节（改用 elimination 类别）
        Debug.elimination(f"  📊 批次 {len(batch)} 环 | 内: {len(inner)} | 中: {len(mid)} | 外: {len(outer)} | 暂存: {len(remaining)}")

        # 调用标准探测逻辑
        self._standard_probe_logic(inner, mid, outer, batch_cycle_to_item, remaining)

        # ---------- 标准探测逻辑 ----------
    def _standard_probe_logic(self,
                            inner_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
                            mid_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
                            outer_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
                            cycle_to_item: Dict[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]], Tuple[int, Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]],
                            remaining: List[Tuple[int, Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]]):
        state = self.state
        if state is None:
            return

        # 转换为 (pivot, cycle) 列表
        mid_items = [cycle_to_item[c] for c in mid_cycles]
        outer_items = [cycle_to_item[c] for c in outer_cycles]

        # ---------- 1. 处理中环（mid），分批处理直到耗尽或达标 ----------
        mid_remaining = list(mid_items)
        while mid_remaining:
            if len(state.valid_basis) >= self.global_target_rank:
                self.update_pending(mid_remaining + outer_items + remaining)
                state._reserved_cycles = []
                self.switch_mode(self.Mode.COMPLETED)
                return
            batch_size = min(max(self.global_target_rank // 10, 1), len(mid_remaining))
            batch = mid_remaining[:batch_size]
            mid_remaining = mid_remaining[batch_size:]
            Debug.elimination(f"  🔎 常规探测 → 中层预消元 {len(batch)} 环（剩余 {len(mid_remaining)}）")
            for idx, (pivot, cycle) in enumerate(batch):
                if len(state.valid_basis) >= self.global_target_rank:
                    leftover_batch = batch[idx:]
                    self.update_pending(leftover_batch + mid_remaining + outer_items + remaining)
                    state._reserved_cycles = []
                    self.switch_mode(self.Mode.COMPLETED)
                    return
                added = self.reducer.add_candidate(cycle)
                if added is not None:
                    edges = added[1]
                    if edges:
                        state.add_basis(added, edges)
                    else:
                        state.failed_cycles.append(cycle)
                else:
                    state.failed_cycles.append(cycle)
            # 批次结束后检查黑洞闭合
            if self._evolve_blackhole():
                Debug.info("  ⚫ 中层批次处理完毕，黑洞闭合，触发交替湮灭")
                self.update_pending(mid_remaining + outer_items + remaining)
                state._reserved_cycles = []
                state.clear_failed()
                self.switch_mode(self.Mode.ALTERNATING_ANNIHILATION)
                return

        # ---------- 2. 处理外环（outer），分批处理直到耗尽或达标 ----------
        outer_remaining = list(outer_items)
        while outer_remaining:
            if len(state.valid_basis) >= self.global_target_rank:
                self.update_pending(outer_remaining + remaining)
                state._reserved_cycles = []
                self.switch_mode(self.Mode.COMPLETED)
                return
            batch_size = min(max(self.global_target_rank // 10, 1), len(outer_remaining))
            batch = outer_remaining[:batch_size]
            outer_remaining = outer_remaining[batch_size:]
            Debug.elimination(f"  🔍 常规探测 → 外层预消元 {len(batch)} 环（剩余 {len(outer_remaining)}）")
            for idx, (pivot, cycle) in enumerate(batch):
                if len(state.valid_basis) >= self.global_target_rank:
                    leftover_batch = batch[idx:]
                    self.update_pending(leftover_batch + outer_remaining + remaining)
                    state._reserved_cycles = []
                    self.switch_mode(self.Mode.COMPLETED)
                    return
                added = self.reducer.add_candidate(cycle)
                if added is not None:
                    edges = added[1]
                    if edges:
                        state.add_basis(added, edges)
                    else:
                        state.failed_cycles.append(cycle)
                else:
                    state.failed_cycles.append(cycle)
            # 批次结束后检查黑洞闭合
            if self._evolve_blackhole():
                Debug.info("  ⚫ 外层批次处理完毕，黑洞闭合，触发交替湮灭")
                self.update_pending(outer_remaining + remaining)
                state._reserved_cycles = []
                state.clear_failed()
                self.switch_mode(self.Mode.ALTERNATING_ANNIHILATION)
                return

        # ---------- 3. 中环和外环已全部处理完，剩余仅有批次外 remaining ----------
        current_pending = list(remaining)

        # ---------- 4. 黑洞闭合检测 ----------
        if self._evolve_blackhole():
            Debug.info("  ⚫ 预消元后黑洞闭合，立即触发交替湮灭")
            all_left = current_pending + state._reserved_cycles
            self.update_pending(all_left)
            state._reserved_cycles = []
            state.clear_failed()
            self.switch_mode(self.Mode.ALTERNATING_ANNIHILATION)
            return

        # ---------- 5. 处理内环 ----------
        if inner_cycles:
            inner_items = [cycle_to_item[c] for c in inner_cycles]
            state._reserved_cycles = current_pending + state._reserved_cycles
            self.update_pending(inner_items)
            self.switch_mode(self.Mode.SAFE_ELIMINATION)
            Debug.elimination(f"  🔍 常规探测 → 发送 {len(inner_items)} 内环到安全消元")
            return

        # ---------- 6. 无内环，返回常规探测 ----------
        self.update_pending(current_pending + state._reserved_cycles)
        state._reserved_cycles = []
        self.switch_mode(self.Mode.STANDARD_PROBE)
        Debug.elimination("  🔍 预消元结束 → 返回常规探测重新分层")

        
    # ---------- 自适应探测 ----------
    def _adaptive_probe_logic(self,
                              inner_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
                              mid_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
                              outer_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
                              cycle_to_item: Dict[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]], Tuple[int, Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]],
                              remaining: List[Tuple[int, Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]]):
        state = self.state
        if state is None:
            return

        p0 = deque(cycle_to_item[c] for c in inner_cycles)
        p1 = deque(cycle_to_item[c] for c in mid_cycles)
        p2 = deque(cycle_to_item[c] for c in outer_cycles)

        def handle(cyc: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]) -> bool:
            if len(state.valid_basis) >= self.global_target_rank:
                return False
            if state.is_blackhole_active and cyc[1].issubset(state.blackhole_edges):
                return False
            added = self.reducer.add_candidate(cyc)
            if added is not None:
                edges = added[1]
                if edges:
                    state.add_basis(added, edges)
                    return True
                else:
                    state.failed_cycles.append(cyc)
                    return False
            else:
                state.failed_cycles.append(cyc)
                return False

        def current_basis_edges():
            if state.valid_basis_edges:
                return set().union(*state.valid_basis_edges)
            return set()

        def current_basis_nodes():
            nodes = set()
            for edges in state.valid_basis_edges:
                for u, v in edges:
                    nodes.add(u); nodes.add(v)
            return nodes

        def phase2_residual_mining(trigger_edges: FrozenSet[Tuple[int, int]]) -> bool:
            nonlocal p0, p1
            local_edges = current_basis_edges()
            local_edges.update(trigger_edges)
            local_nodes = current_basis_nodes()
            for u, v in trigger_edges:
                local_nodes.add(u); local_nodes.add(v)

            is_closed, local_rank, comps, local_basis_count = self._compute_blackhole(
                local_edges, local_nodes, state.valid_basis_edges
            )
            if is_closed:
                return True

            active_new_edges = set(trigger_edges)
            while True:
                still_p1 = deque()
                p1_to_p0 = []
                for pivot, c in p1:
                    if c[1].issubset(local_edges):
                        p1_to_p0.append(c)
                    else:
                        still_p1.append((pivot, c))
                p1 = still_p1
                p1_to_p0.sort(key=lambda c: len(c[2]))

                p1_added_edges = set()
                for c in p1_to_p0:
                    if handle(c):
                        p1_added_edges.update(c[1])
                        local_basis_count += 1
                        if local_basis_count >= local_rank and comps == 1:
                            is_closed = True
                            break
                if is_closed:
                    break

                wake_up_edges = set(active_new_edges)
                wake_up_edges.update(p1_added_edges)
                if not wake_up_edges:
                    break

                still_p0 = deque()
                new_p0 = []
                for pivot, c in p0:
                    if c[1] & wake_up_edges:
                        new_p0.append(c)
                    else:
                        still_p0.append((pivot, c))
                p0 = still_p0
                new_p0.sort(key=lambda c: len(c[2]))

                active_new_edges.clear()
                for c in new_p0:
                    if handle(c):
                        active_new_edges.update(c[1])
                        local_edges.update(c[1])
                        for u, v in c[1]:
                            local_nodes.add(u); local_nodes.add(v)
                        _closed, local_rank, comps, local_basis_count = self._compute_blackhole(
                            local_edges, local_nodes, state.valid_basis_edges
                        )
                        if _closed:
                            is_closed = True
                            break
                if is_closed:
                    break
                if not active_new_edges:
                    break
            return is_closed

        while (p0 or p1 or p2) and len(state.valid_basis) < self.global_target_rank:
            total_pending = len(p0) + len(p1) + len(p2)
            rank_gap = self.global_target_rank - len(state.valid_basis)

            if total_pending <= rank_gap:
                all_sprint = list(p1) + list(p2) + list(p0)
                p1.clear(); p2.clear(); p0.clear()
                for pivot, cyc in all_sprint:
                    if len(state.valid_basis) >= self.global_target_rank:
                        break
                    handle(cyc)
                break

            if not p0 and not p1:
                for pivot, cyc in list(p2):
                    if len(state.valid_basis) >= self.global_target_rank:
                        break
                    handle(cyc)
                p2.clear()
                break

            is_local_closed, _, _, _ = self._compute_blackhole(
                current_basis_edges(), current_basis_nodes(), state.valid_basis_edges
            )
            if is_local_closed:
                p0.clear()

            trigger_edges = set()
            p1_to_p2s = {}
            for _, c1 in p1:
                for _, c2 in p2:
                    if c1[1] & c2[1]:
                        key = (c1, frozenset(c1[1]))
                        if key not in p1_to_p2s:
                            p1_to_p2s[key] = []
                        p1_to_p2s[key].append(c2)

            if p1_to_p2s:
                best_key = max(p1_to_p2s.keys(), key=lambda k: (len(p1_to_p2s[k]), -len(k[0])))
                linked_p2s = p1_to_p2s[best_key]
                linked_p2s.sort(key=lambda c: len(c[2]))

                p1_target = None
                for pivot, c in p1:
                    if c == best_key[0] and frozenset(c[1]) == best_key[1]:
                        p1_target = (pivot, c)
                        break
                if p1_target:
                    p1.remove(p1_target)
                    if handle(p1_target[1]):
                        trigger_edges.update(p1_target[1][1])

                linked_ids = {id(c) for c in linked_p2s}
                p2 = deque(x for x in p2 if id(x) not in linked_ids)
                for c in linked_p2s:
                    if handle(c):
                        trigger_edges.update(c[1])
            else:
                if p2:
                    basis_nodes = current_basis_nodes()
                    p2_list = list(p2)
                    p2_list.sort(key=lambda x: (len(set(x[1][2]) - basis_nodes), len(x[1][2])))
                    target = p2_list[0]
                    p2.remove(target)
                    if handle(target[1]):
                        trigger_edges.update(target[1][1])

            if trigger_edges:
                phase2_residual_mining(frozenset(trigger_edges))
            elif p1:
                basis_edges = current_basis_edges()
                p1_list = list(p1)
                p1_list.sort(key=lambda x: (-len(x[1][1] - basis_edges), len(x[1][2])))
                target = p1_list[0]
                p1 = deque(p1_list[1:])
                if handle(target[1]):
                    phase2_residual_mining(target[1][1])
            elif p0:
                target = p0.popleft()
                if handle(target[1]):
                    phase2_residual_mining(target[1][1])
            else:
                break

        residual = list(p0) + list(p1) + list(p2)
        combined_pending = residual + list(remaining)
        if combined_pending:
            self.update_pending(combined_pending)
        else:
            self.update_pending([])

    # ---------- 安全消元 ----------
    def _safe_elimination(self):
        state = self.state
        if state is None:
            return

        if not state.pending_cycles:
            if state._reserved_cycles:
                self.update_pending(state._reserved_cycles)
                state._reserved_cycles = []
            else:
                self.switch_mode(self.Mode.STANDARD_PROBE)
            return

        batch = list(state.pending_cycles)
        added_count = 0
        check_interval = max(1, self.global_target_rank // 50)

        for idx, (pivot, cycle) in enumerate(batch):
            if len(state.valid_basis) >= self.global_target_rank:
                self.update_pending(batch[idx:] + state._reserved_cycles)
                state._reserved_cycles = []
                self.switch_mode(self.Mode.COMPLETED)
                return
            state._processed_count += 1
            added = self.reducer.add_candidate(cycle)
            if added is not None:
                edges = added[1]
                if edges:
                    state.add_basis(added, edges)
                    added_count += 1
                    if added_count % check_interval == 0 and self._evolve_blackhole():
                        Debug.elimination(f"  ⚫ 安全消元中途（已吞{added_count}环）黑洞闭合，立即触发交替湮灭")
                        self.update_pending(batch[idx+1:] + state._reserved_cycles)
                        state._reserved_cycles = []
                        state.clear_failed()
                        self.switch_mode(self.Mode.ALTERNATING_ANNIHILATION)
                        return
                else:
                    state.failed_cycles.append(cycle)
            else:
                state.failed_cycles.append(cycle)

        self.update_pending([])
        if self._evolve_blackhole():
            Debug.elimination("  ⚫ 安全消元批次完成，黑洞闭合")
            self.update_pending(state._reserved_cycles)
            state._reserved_cycles = []
            state.clear_failed()
            self.switch_mode(self.Mode.ALTERNATING_ANNIHILATION)
        else:
            if state._reserved_cycles:
                self.update_pending(state._reserved_cycles)
                state._reserved_cycles = []
            self.switch_mode(self.Mode.STANDARD_PROBE)
            now = time.time()
            if now - state.last_switch_log_time >= 1.0:
                Debug.elimination(f"  🔓 安全消元结束，返回常规探测，基底: {len(state.valid_basis)}")
                state.last_switch_log_time = now

        state.safe_elimination_count += 1
        self._render_progress()

    # ---------- 黑洞演化 ----------
    def _evolve_blackhole(self) -> bool:
        state = self.state
        if not state.valid_basis or len(state.valid_basis) < 20:
            if state:
                state.is_blackhole_active = False
            return False
        t0 = time.time()
        basis_edges = set()
        nodes = set()
        for edges in state.valid_basis_edges:
            if not edges:
                continue
            basis_edges.update(edges)
            for u, v in edges:
                nodes.update({u, v})
        if not basis_edges:
            return False
        E = len(basis_edges)
        V = len(nodes)
        parent = {n: n for n in nodes}
        def find(i):
            if parent[i] != i:
                parent[i] = find(parent[i])
            return parent[i]
        components = V
        for u, v in basis_edges:
            ru, rv = find(u), find(v)
            if ru != rv:
                parent[ru] = rv
                components -= 1
        theoretical_rank = E - V + components
        state._bh_call_count += 1
        state._bh_total_time += (time.time() - t0)
        if len(state.valid_basis) == theoretical_rank:
            state.blackhole_edges = basis_edges
            if not state.is_blackhole_active:
                state.is_blackhole_active = True
                now = time.time()
                if now - state.last_bh_log_time >= 3.0:
                    Debug.fuse(f"  🌌 黑洞视界闭合！基底: {len(state.valid_basis)}/{theoretical_rank}")
                    state.last_bh_log_time = now
            return True
        state.is_blackhole_active = False
        state.blackhole_edges.clear()
        return False

    # ---------- 交替湮灭 ----------
    def _alternating_annihilation(self):
        state = self.state
        if state is None:
            return

        all_cycles = state.pending_cycles + state._reserved_cycles
        if not all_cycles:
            self.switch_mode(self.Mode.STANDARD_PROBE)
            return

        old_total = len(all_cycles)
        surviving = [item for item in all_cycles
                     if item[1][1] and not item[1][1].issubset(state.blackhole_edges)]

        state.clear_failed()
        state.is_blackhole_active = False
        state.blackhole_edges.clear()

        self.update_pending(surviving)
        state._reserved_cycles = []

        discarded = old_total - len(state.pending_cycles)
        state.annihilation_count += 1
        Debug.elimination(f"  ⚫ 交替湮灭 #{state.annihilation_count} 完成，"
                   f"丢弃 {discarded} 个冗余环，保留 {len(state.pending_cycles)} 个环，"
                   f"进入常规探测")
        self.switch_mode(self.Mode.STANDARD_PROBE)
        self._render_progress()

    def _execute(self) -> Tuple[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]], bool]:
        while self.state.pending_cycles or self.state._reserved_cycles:
            if len(self.state.valid_basis) >= self.global_target_rank:
                if self.enable_progress_bar:
                    Debug.newline()
                Debug.done("🎯 目标秩达成！")
                return self.state.valid_basis, True

            mode = self.state.current_mode
            if mode == self.Mode.SAFE_ELIMINATION:
                self._safe_elimination()
            elif mode == self.Mode.STANDARD_PROBE:
                self._handle_probe()
            elif mode == self.Mode.ALTERNATING_ANNIHILATION:
                self._alternating_annihilation()
            elif mode == self.Mode.COMPLETED:
                break

        if len(self.state.valid_basis) >= self.global_target_rank:
            if self.enable_progress_bar:
                Debug.newline()
            Debug.done("🎯 目标秩达成！")
            return self.state.valid_basis, True

        if self.enable_progress_bar:
            Debug.newline()
        self._render_progress()
        return self.state.valid_basis, False
    
    @staticmethod
    def _final_incremental_reduction(global_edges, candidates, global_target_rank):
        start_time = time.time()
        Debug.info(f"🚀 CSRBlackholeDevourer 启动，候选环数: {len(candidates)}，目标秩: {global_target_rank}")
        
        devourer = CSRBlackholeDevourer(
            global_edges,
            candidates,
            global_target_rank,
            enable_progress_bar=False,
        )
        result = devourer._execute()
        
        elapsed = time.time() - start_time
        Debug.timing(f"CSRBlackholeDevourer 完成，耗时 {elapsed:.3f}s", elapsed)
        return result




# ==========================================
# 无弦环和无弦路径挖掘器 (CyclesAndPathsFinder)
# ==========================================
class CyclesAndPathsFinder:
    """图环与路径查找器 - 自包含版（所有辅助函数已内联）"""

    # =========================================================
    # 辅助函数（原样保留，仅作类内静态方法）
    # =========================================================

    @staticmethod
    def cycle_convert_eids_and_edges(
        cycle: List[int],
        adj: Dict[int, Set[int]],
        edge_to_eid: Dict[Tuple[int, int], int]
    ) -> Tuple[Set[int], Set[Tuple[int, int]], bool]:
        """将一个节点环转换为边ID集合"""
        eids_set = set()
        edges_set = set()
        edges_list: List[Tuple[int, int]] = []
        cycle_set = set(cycle)
        if len(cycle) < 3:
            return eids_set, edges_set, False
        else:
            for node in sorted(cycle_set):
                if len(cycle_set & adj[node]) < 2:
                    return eids_set, edges_set, False
        for node in sorted(cycle_set):
            if len(cycle_set & adj[node]) >= 2:
                node_neighbors = cycle_set & adj[node]
                for neighbor in node_neighbors:
                    if neighbor != node:
                        edge = (min(node, neighbor), max(node, neighbor))
                        if edge in edge_to_eid:
                            edges_list.append(edge)
        edges_list_count = Counter(edges_list)
        count_sum = 0
        count_list: List[int] = []
        for edge, count in edges_list_count.items():
            count_list.append(count)
            count_sum += count
        count_list_count = Counter(count_list)
        num_count_list: List[int] = []
        for count_one, count in count_list_count.items():
            if count == len(cycle):
                num_count_list.append(count_one)
        count = 0
        if len(num_count_list) == 1:
            count = num_count_list[0]
        for edge, edge_count in edges_list_count.items():
            if edge_count == count:
                edges_set.add(edge)
        for edge in edges_set:
            if edge in edge_to_eid:
                eids_set.add(edge_to_eid[edge])
        if count_sum == len(cycle) * count:
            return eids_set, edges_set, True
        return eids_set, edges_set, False

    @staticmethod
    def extract_chord_set(global_edges: Set[Tuple[int, int]]):
        """
        确定性地提取弦边集和树边集。

        ✅ 低度优先策略: 邻接点按度从小到大排序，度低的点优先遍历、优先进树
        """
        normalized_global = set()
        full_adj: DefaultDict[int, List[int]] = defaultdict(list)

        nodes_set = set()
        for u, v in global_edges:
            u, v = (u, v) if u < v else (v, u)
            normalized_global.add((u, v))
            full_adj[u].append(v)
            full_adj[v].append(u)
            nodes_set.add(u)
            nodes_set.add(v)

        node_degree = {node: len(neighbors) for node, neighbors in full_adj.items()}

        for node in full_adj:
            full_adj[node].sort(key=lambda neighbor: (node_degree[neighbor], neighbor))

        visited = set()
        tree_edges = set()
        tree_adj: DefaultDict[int, List[int]] = defaultdict(list)

        all_nodes = sorted(nodes_set, key=lambda node: (node_degree[node], node))

        for start_node in all_nodes:
            if start_node not in visited:
                queue = deque([(start_node, -1)])
                visited.add(start_node)

                while queue:
                    curr, parent = queue.popleft()

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
        if len(path_set) < 3:
            return False

        # 连通性检查（内联 BFS）
        start = next(iter(path_set))
        visited = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in adj[node]:
                if neighbor in path_set and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        if len(visited) != len(path_set):
            return False

        midpoints = []
        endpoints = []
        for node in path_set:
            deg = len(adj[node] & path_set - {node})
            if deg > 2:
                return False
            elif deg == 2:
                midpoints.append(node)
            elif deg == 1:
                endpoints.append(node)

        if len(endpoints) != 2:
            return False
        if len(midpoints) != len(path_set) - len(endpoints):
            return False
        return True

    @staticmethod
    def verify_chordless_cycle(path: List[int], adj: Dict[int, Set[int]]) -> bool:
        """验证给定路径是否为无弦环"""
        path_set = set(path)
        if len(path_set) < 3:
            return False

        # 连通性检查（内联 BFS）
        start = next(iter(path_set))
        visited = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in adj[node]:
                if neighbor in path_set and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        if len(visited) != len(path_set):
            return False

        midpoints = []
        endpoints = []
        for node in path_set:
            deg = len(adj[node] & path_set - {node})
            if deg > 2:
                return False
            elif deg == 2:
                midpoints.append(node)
            elif deg == 1:
                endpoints.append(node)

        if len(endpoints) != 0:
            return False
        if len(midpoints) != len(path_set):
            return False
        return True

    @staticmethod
    def generate_chordless_mapping(path: List[int], adj: Dict[int, Set[int]]) -> Tuple[List[int], List[int]]:
        """生成给定路径的无弦路径映射"""
        path_set = set(path)
        if len(path_set) < 3:
            return [], []

        # 连通性检查（内联 BFS）
        start = next(iter(path_set))
        visited = {start}
        queue = deque([start])
        while queue:
            node = queue.popleft()
            for neighbor in adj[node]:
                if neighbor in path_set and neighbor not in visited:
                    visited.add(neighbor)
                    queue.append(neighbor)
        if len(visited) != len(path_set):
            return [], []

        midpoints = []
        endpoints = []
        for node in path_set:
            deg = len(adj[node] & path_set - {node})
            if deg > 2:
                return [], []
            elif deg == 2:
                midpoints.append(node)
            elif deg == 1:
                endpoints.append(node)

        if len(endpoints) != 2:
            return [], []
        if len(midpoints) != len(path_set) - len(endpoints):
            return [], []
        return endpoints, midpoints

    @staticmethod
    def _make_triplet_inline(
        nodes: List[int],
        adj: Dict[int, Set[int]],
        edge_to_eid: Dict[Tuple[int, int], int]
    ) -> Optional[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """内联版三元组构造器（严格校验模式）"""
        node_set = frozenset(nodes)
        if len(node_set) < 2:
            return (frozenset(), frozenset(), frozenset())

        edges_set = frozenset(
            (u, v) for u in node_set
            for v in adj[u] if v in node_set and u < v
        )

        eids_list = []
        missing_edges = []
        for e in edges_set:
            eid = edge_to_eid.get(e)
            if eid is None:
                missing_edges.append(e)
            else:
                eids_list.append(eid)

        if missing_edges:
            Debug.warn(
                f"⚠️ 三元组构造失败 | 节点集大小={len(node_set)} | "
                f"诱导边数={len(edges_set)} | 缺失边数={len(missing_edges)} | "
                f"缺失边样本={missing_edges[:5]}"
            )
            return None

        return (frozenset(eids_list), edges_set, node_set)


    # =========================================================
    # 生成器：3-环 / 3-路径
    # =========================================================

    @staticmethod
    def find_three_cycles_and_paths(
        global_edges: Set[Tuple[int, int]],
        chord_edges: Optional[Set[Tuple[int, int]]] = None,
        choice: Optional[str] = None,
        adj: Optional[Dict[int, Set[int]]] = None,
        edge_to_eid: Optional[Dict[Tuple[int, int], int]] = None,
        global_target_rank: Optional[int] = None,
    ) -> Generator[Tuple[bool, List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]], None, None]:
        """生成所有长度为3的无弦环（True）或无弦路径（False）"""
        start_time = time.time()
        normalized = {(min(u, v), max(u, v)) for u, v in global_edges if u != v}
        chords = chord_edges if chord_edges is not None else normalized

        Debug.info(f"🚀 find_three_cycles_and_paths 启动 | 边数: {len(normalized)}, 弦边数: {len(chords)}, 选择: {choice}")
        count = 0
        loop_count = 0
        target_len = 10
        cycles_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        paths_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []

        if adj is None or edge_to_eid is None or global_target_rank is None:
            data_init = DataInitialization(global_edges)
            adj = adj or data_init.adj
            edge_to_eid = edge_to_eid or data_init.edge_to_eid
            global_target_rank = global_target_rank or data_init.target_rank

        if choice == "path":
            for u, v in chords:
                edge0 = (min(u, v), max(u, v))
                for w in adj[u] - adj[v]:
                    edge1 = (min(u, w), max(u, w))
                    triplet = (frozenset([edge_to_eid[edge0], edge_to_eid[edge1]]), frozenset([edge0, edge1]), frozenset([u, v, w]))
                    paths_basis.append(triplet)
                for w in adj[v] - adj[u]:
                    edge2 = (min(v, w), max(v, w))
                    triplet = (frozenset([edge_to_eid[edge0], edge_to_eid[edge2]]), frozenset([edge0, edge2]), frozenset([u, v, w]))
                    paths_basis.append(triplet)
                    count += 1
                    if count >= global_target_rank * target_len:   # 只保留分批阈值
                        paths_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                            global_edges=global_edges,
                            candidates=list(set(paths_basis)),
                            global_target_rank=global_target_rank,
                        )
                        if is_full:
                            yield False, list(paths_basis)
                            return
                        yield False, list(paths_basis)
                        count = 0

            if paths_basis:
                yield False, list(paths_basis)

        else:
            for u, v in chords:
                edge0 = (min(u, v), max(u, v))
                for w in adj[u] & adj[v]:
                    edge1 = (min(u, w), max(u, w))
                    edge2 = (min(v, w), max(v, w))
                    triplet = (frozenset([edge_to_eid[edge0], edge_to_eid[edge1], edge_to_eid[edge2]]), frozenset([edge0, edge1, edge2]), frozenset([u, v, w]))
                    cycles_basis.append(triplet)
                    count += 1
                    if count >= global_target_rank * target_len:
                        cycles_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                            global_edges=global_edges,
                            candidates=list(set(cycles_basis)),
                            global_target_rank=global_target_rank,
                        )
                        if is_full:
                            yield True, list(cycles_basis)
                            return
                        yield True, list(cycles_basis)
                        count = 0
                            
            if cycles_basis:
                yield True, list(cycles_basis)

    # =========================================================
    # 生成器：4-环 / 4-路径
    # =========================================================

    @staticmethod
    def find_four_cycles_and_paths(
        global_edges: Set[Tuple[int, int]],
        chord_edges: Optional[Set[Tuple[int, int]]] = None,
        choice: Optional[str] = None,
        adj: Optional[Dict[int, Set[int]]] = None,
        edge_to_eid: Optional[Dict[Tuple[int, int], int]] = None,
        global_target_rank: Optional[int] = None,
    ) -> Generator[Tuple[bool, List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]], None, None]:
        """生成所有长度为3的无弦环（True）或无弦路径（False）"""
        start_time = time.time()
        normalized = {(min(u, v), max(u, v)) for u, v in global_edges if u != v}
        chords = chord_edges if chord_edges is not None else normalized
        if adj is None or edge_to_eid is None or global_target_rank is None:
            data_init = DataInitialization(global_edges)
            adj = adj or data_init.adj
            edge_to_eid = edge_to_eid or data_init.edge_to_eid
            global_target_rank = global_target_rank or data_init.target_rank

        Debug.info(f"🚀 find_four_cycles_and_paths 启动 | 边数: {len(normalized)}, 弦边数: {len(chords)}, 选择: {choice}")
        count = 0

        target_len = 10
        cycles_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        paths_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []


        if choice == "path":
            for u, v in chords:
                unique_neighbors_u = adj[u] - (adj[u] & adj[v])
                unique_neighbors_v = adj[v] - (adj[u] & adj[v])
                for u_mid, v_mid in itertools.product(unique_neighbors_u, unique_neighbors_v):
                    if (min(u_mid, v_mid), max(u_mid, v_mid)) in normalized:
                        continue
                    nodes = [u, u_mid, v_mid, v]
                    if len(set(nodes)) == 4:
                        edge1 = (min(u, v), max(u, v))
                        edge2 = (min(u, u_mid), max(u, u_mid))
                        edge3 = (min(v, v_mid), max(v, v_mid))
                        triplet = (frozenset([edge_to_eid[edge1], edge_to_eid[edge2], edge_to_eid[edge3]]), frozenset([edge1, edge2, edge3]), frozenset([u, u_mid, v_mid, v]))
                        paths_basis.append(triplet)
                        count += 1
                        if count >= global_target_rank * target_len:   # 只保留分批阈值
                            paths_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                                global_edges=global_edges,
                                candidates=list(set(paths_basis)),
                                global_target_rank=global_target_rank,
                            )
                            if is_full:
                                yield False, list(paths_basis)
                                return
                            yield False, list(paths_basis)
                            count = 0

            if paths_basis:                                              # 末尾无条件 flush
                yield False, list(paths_basis)
        else:
            for u, v in chords:
                unique_neighbors_u = adj[u] - (adj[u] & adj[v])
                unique_neighbors_v = adj[v] - (adj[u] & adj[v])
                for u_mid, v_mid in itertools.product(unique_neighbors_u, unique_neighbors_v):
                    if (min(u_mid, v_mid), max(u_mid, v_mid)) not in normalized:
                        continue
                    nodes = [u, u_mid, v_mid, v]
                    if len(set(nodes)) == 4:
                        edge1 = (min(u, v), max(u, v))
                        edge2 = (min(u, u_mid), max(u, u_mid))
                        edge3 = (min(v, v_mid), max(v, v_mid))
                        edge4 = (min(u_mid, v_mid), max(u_mid, v_mid))

                        triplet = (frozenset([edge_to_eid[edge1], edge_to_eid[edge2], edge_to_eid[edge3], edge_to_eid[edge4]]), frozenset([edge1, edge2, edge3, edge4]), frozenset([u, u_mid, v_mid, v]))
                        cycles_basis.append(triplet)
                        count += 1
                        if count >= global_target_rank * target_len:   # 只保留分批阈值
                            cycles_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                                global_edges=global_edges,
                                candidates=list(set(cycles_basis)),
                                global_target_rank=global_target_rank,
                            )
                            if is_full:
                                yield True, list(cycles_basis)
                                return
                            yield True, list(cycles_basis)
                            count = 0
                                    
            if cycles_basis:
                yield True, list(cycles_basis)

    # =========================================================
    # 生成器：5-环 / 5-路径
    # =========================================================


    @staticmethod
    def find_five_cycles_and_paths(
        global_edges: Set[Tuple[int, int]],
        chord_edges: Optional[Set[Tuple[int, int]]] = None,
        choice: Optional[str] = None,
        adj: Optional[Dict[int, Set[int]]] = None,
        edge_to_eid: Optional[Dict[Tuple[int, int], int]] = None,
        global_target_rank: Optional[int] = None,
    ) -> Generator[Tuple[bool, List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]], None, None]:
        """生成所有长度为5的无弦环（True）或无弦路径（False）"""
        start_time = time.time()
        normalized = {(min(u, v), max(u, v)) for u, v in global_edges}
        chords = chord_edges if chord_edges is not None else normalized
        if adj is None or edge_to_eid is None or global_target_rank is None:
            normalized = {(min(u, v), max(u, v)) for u, v in global_edges}
            data_init = DataInitialization(normalized)
            adj, edge_to_eid, global_target_rank = data_init.adj, data_init.edge_to_eid, data_init.target_rank

        Debug.info(f"🚀 find_five_cycles_and_paths 启动 | 边数: {len(normalized)}, 弦边数: {len(chords)}, 选择: {choice}")
        count = 0


        cycles_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        paths_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        mid_paths_set: Set[Tuple[Tuple[int, int], Tuple[int, ...]]] = set()
        target_len = 15
        node_to_paths_frozenset_mapping: Dict[int, Set[FrozenSet[int]]] = defaultdict(set)
        endpoints_set: Set[Tuple[int, int]] = set()
        chords_nodes: Set[int] = set(node for u, v in chords for node in (u, v))

        # 1. 构建全量无弦 5 节点路径 mid_paths_set
        for u, v in normalized:
            unique_neighbors_u = adj[u] - (adj[u] & adj[v])
            unique_neighbors_v = adj[v] - (adj[u] & adj[v])
            for node in unique_neighbors_u:
                endpoints_set.add((min(v, node), max(v, node)))
                mid_paths_set.add(((min(v, node), max(v, node)), (u,)))
                node_to_paths_frozenset_mapping[node].add(frozenset([u, v]))
            for node in unique_neighbors_v:
                endpoints_set.add((min(u, node), max(u, node)))
                mid_paths_set.add(((min(u, node), max(u, node)), (v,)))
                node_to_paths_frozenset_mapping[node].add(frozenset([u, v]))

        if choice == "path":
            for endpoints, midpoints in mid_paths_set:
                paths_u = node_to_paths_frozenset_mapping[min(endpoints)]
                paths_v = node_to_paths_frozenset_mapping[max(endpoints)]
                for path in (paths_u | paths_v) - (paths_u & paths_v):
                    if (min(path), max(path)) in chords:
                        nodes = list(set(list(path) + list(midpoints) + list(endpoints)))
                        if len(nodes) == 5:
                            if CyclesAndPathsFinder.verify_chordless_path(nodes, adj):
                                triplet = CyclesAndPathsFinder._make_triplet_inline(nodes, adj, edge_to_eid)
                                if triplet is not None:
                                    paths_basis.append(triplet)
                                    count += 1
                                    if count >= global_target_rank * target_len:   # 只保留分批阈值
                                        paths_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                                            global_edges=global_edges,
                                            candidates=list(set(paths_basis)),
                                            global_target_rank=global_target_rank,
                                        )
                                        if is_full:
                                            yield False, list(paths_basis)
                                            return
                                        yield False, list(paths_basis)
                                        count = 0

            if paths_basis:
                yield False, list(paths_basis)

        else:
            for endpoints, midpoints in mid_paths_set:
                paths_u = node_to_paths_frozenset_mapping[min(endpoints)]
                paths_v = node_to_paths_frozenset_mapping[max(endpoints)]
                for path in paths_u & paths_v:
                    if (min(path), max(path)) in chords:
                        nodes = list(set(list(path) + list(midpoints) + list(endpoints)))
                        if len(nodes) == 5:
                            if CyclesAndPathsFinder.verify_chordless_cycle(nodes, adj):
                                triplet = CyclesAndPathsFinder._make_triplet_inline(nodes, adj, edge_to_eid)
                                if triplet is not None:
                                    cycles_basis.append(triplet)
                                    count += 1
                                    if count >= global_target_rank * target_len:
                                        cycles_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                                            global_edges=global_edges,
                                            candidates=list(set(cycles_basis)),
                                            global_target_rank=global_target_rank,
                                        )
                                        if is_full:
                                            yield True, list(cycles_basis)
                                            return
                                        yield True, list(cycles_basis)
                                        count = 0
                                    
            if cycles_basis:
                yield True, list(cycles_basis)


    # =========================================================
    # 生成器：6-环 / 6-路径
    # =========================================================

    @staticmethod
    def find_six_cycles_and_paths(
        global_edges: Set[Tuple[int, int]],
        chord_edges: Optional[Set[Tuple[int, int]]] = None,
        choice: Optional[str] = None,
        adj: Optional[Dict[int, Set[int]]] = None,
        edge_to_eid: Optional[Dict[Tuple[int, int], int]] = None,
        global_target_rank: Optional[int] = None,
    ) -> Generator[Tuple[bool, List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]], None, None]:
        """生成所有长度为6的无弦环（True）或无弦路径（False）"""
        start_time = time.time()
        normalized = {(min(u, v), max(u, v)) for u, v in global_edges if u != v}
        chords = chord_edges if chord_edges is not None else normalized
        if adj is None or edge_to_eid is None or global_target_rank is None:
            data_init = DataInitialization(global_edges)
            adj = adj or data_init.adj
            edge_to_eid = edge_to_eid or data_init.edge_to_eid
            global_target_rank = global_target_rank or data_init.target_rank

        Debug.info(f"🚀 find_six_cycles_and_paths 启动 | 边数: {len(normalized)}, 弦边数: {len(chords)}, 选择: {choice}")
        count = 0

        cycles_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        paths_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        mid_paths_set: Set[Tuple[Tuple[int, int], Tuple[int, ...]]] = set()
        target_len = 10
        node_to_paths_frozenset_mapping: Dict[int, Set[FrozenSet[int]]] = defaultdict(set)
        endpoints_set: Set[Tuple[int, int]] = set()

        # 1. 构建全量无弦 6 节点路径 mid_paths_set
        for u, v in normalized:
            unique_neighbors_u = adj[u] - (adj[u] & adj[v])
            unique_neighbors_v = adj[v] - (adj[u] & adj[v])
            for node in unique_neighbors_u:
                endpoints_set.add((min(v, node), max(v, node)))
            for node in unique_neighbors_v:
                endpoints_set.add((min(u, node), max(u, node)))
            for u_neighbor, v_neighbor in itertools.product(unique_neighbors_u, unique_neighbors_v):
                endpoint1, endpoint2 = (min(u_neighbor, v_neighbor), max(u_neighbor, v_neighbor))
                if (endpoint1, endpoint2) not in normalized:
                    endpoints_set.add((endpoint1, endpoint2))
                    mid_paths_set.add(((endpoint1, endpoint2), tuple(sorted([u, v]))))
                    node_to_paths_frozenset_mapping[endpoint1].add(frozenset([u, v]))
                    node_to_paths_frozenset_mapping[endpoint2].add(frozenset([u, v]))


        if choice == "path":
            # 6 路径 = 4 路径 + 非共同两节点路径（对称差）
            for endpoints, midpoints in mid_paths_set:
                if (min(midpoints), max(midpoints)) not in chords:
                    continue
                paths_a = node_to_paths_frozenset_mapping[endpoints[0]]
                paths_b = node_to_paths_frozenset_mapping[endpoints[1]]
                for path_frozenset in (paths_a | paths_b) - (paths_a & paths_b):
                    nodes = list(set(list(path_frozenset) + list(endpoints) + list(midpoints)))
                    if len(set(nodes)) == 6:
                        if CyclesAndPathsFinder.verify_chordless_path(nodes, adj):
                            triplet = CyclesAndPathsFinder._make_triplet_inline(nodes, adj, edge_to_eid)
                            if triplet is not None:
                                paths_basis.append(triplet)
                                count += 1
                                if count >= global_target_rank * target_len:   # 只保留分批阈值
                                    paths_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                                        global_edges=global_edges,
                                        candidates=list(set(paths_basis)),
                                        global_target_rank=global_target_rank,
                                    )
                                    if is_full:
                                        yield False, list(paths_basis)
                                        return
                                    yield False, list(paths_basis)
                                    count = 0
            if paths_basis:
                yield False, list(paths_basis)
        else:
            # 6 环 = 4 路径 + 共同两节点路径（交集）
            for endpoints, midpoints in mid_paths_set:
                if (min(midpoints), max(midpoints)) not in chords:
                    continue
                paths_a = node_to_paths_frozenset_mapping[endpoints[0]]
                paths_b = node_to_paths_frozenset_mapping[endpoints[1]]
                for path_frozenset in (paths_a & paths_b):
                    nodes = list(set(list(path_frozenset) + list(endpoints) + list(midpoints)))
                    if len(set(nodes)) == 6:
                        if CyclesAndPathsFinder.verify_chordless_cycle(nodes, adj):
                            triplet = CyclesAndPathsFinder._make_triplet_inline(nodes, adj, edge_to_eid)
                            if triplet is not None:
                                cycles_basis.append(triplet)
                                count += 1
                                if count >= global_target_rank * target_len:
                                    cycles_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                                        global_edges=global_edges,
                                        candidates=list(set(cycles_basis)),
                                        global_target_rank=global_target_rank,
                                    )
                                    if is_full:
                                        yield True, list(cycles_basis)
                                        return
                                    yield True, list(cycles_basis)
                                    count = 0
                                    
            if cycles_basis:
                yield True, list(cycles_basis)



# ==========================================
# 单维度环提取器 (DimensionCycleExtractor)
# ==========================================
class DimensionCycleExtractor:
    """
    核心功能：
    1. 仅接收全图边和指定维度。
    2. 3 <= 维度 <= 9 时，调用内置静态函数挖出该维度原始环并进行无弦验证与消元。
    """
    def __init__(self, global_edges: Set[Tuple[int, int]], target_dim: int, history_cycles: Optional[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]] = None):
        self.global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        self.target_dim = target_dim
        
        # 外部传入的历史环基底，作为只读参考，避免直接对其重新赋值导致引用断裂
        self.history_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = history_cycles if history_cycles is not None else []
        self.history_cycles_set: Set[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = set(self.history_cycles)
        self.global_adj = defaultdict(set)
        for u, v in self.global_edges:
            self.global_adj[u].add(v)
            self.global_adj[v].add(u)
            
        self.global_data_init = DataInitialization(self.global_edges)
        self.global_edge_to_eid = self.global_data_init.edge_to_eid
        self.global_target_rank = self.global_data_init.target_rank
        self.chord_edges, self.tree_edges, self.tree_adj = StaticMethod.extract_chord_set(self.global_edges)
        self.tree_basis = self.global_data_init.basis
        self.tree_basis_chordless = [cyc for cyc in self.tree_basis if StaticMethod.verify_chordless_cycle(cyc, self.global_adj)]
        self.tree_basis_chorded = [cyc for cyc in self.tree_basis if not StaticMethod.verify_chordless_cycle(cyc, self.global_adj)]

    def generate_target_cycles(self):
        core_edges: Set[Tuple[int, int]] = set()
        if self.target_dim == 3:
            for is_cycle, target_cycles in CyclesAndPathsFinder.find_three_cycles_and_paths(self.global_edges, self.chord_edges, "cycle"):
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
            for is_cycle, target_cycles in CyclesAndPathsFinder.find_four_cycles_and_paths(self.global_edges, self.chord_edges, "cycle"):
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
            for is_cycle, target_cycles in CyclesAndPathsFinder.find_five_cycles_and_paths(self.global_edges, self.chord_edges, "cycle"):
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

    # ================================================================
    # 5. 生成目标弦边集合（剔除冗余边后）
    # ================================================================

    @staticmethod
    def generate_target_chord_edges(
        global_edges: Set[Tuple[int, int]],
        current_tree_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
        history_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
        global_target_rank: int,
    ) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]], List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]]:
        edge_to_tree_cycles_mapping: Dict[Tuple[int, int], Set[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]] = defaultdict(set)
        for cycle in current_tree_basis:
            for edge in cycle[1]:
                edge_to_tree_cycles_mapping[edge].add(cycle)

        chord_to_tree_cycle_mapping: Dict[Tuple[int, int], Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = defaultdict(lambda: (frozenset(), frozenset(), frozenset()))
        chord_edges: Set[Tuple[int, int]] = set()
        for edge, cycles in edge_to_tree_cycles_mapping.items():
            if len(cycles) == 1:
                chord_edges.add(edge)
                chord_to_tree_cycle_mapping[edge] = cycles.pop()
        tree_edges = global_edges - chord_edges

        final_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        redundant_edges: Set[Tuple[int, int]] = set()
        remind_edges: Set[Tuple[int, int]] = set()
        history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(global_edges, history_cycles, global_target_rank)
        core_reducer = BlockwiseCycleReducer(global_edges, history_cycles)

        current_tree_basis_set = set(current_tree_basis)
        for edge, cycle in chord_to_tree_cycle_mapping.items():
            if cycle not in current_tree_basis_set:
                continue
            if core_reducer.check_independent(cycle):
                final_basis.append(cycle)
                remind_edges.add(edge)
            else:
                redundant_edges.update(cycle[1])

        final_chord_edges = remind_edges
        final_tree_edges = redundant_edges

        Debug.info(
            f"🚀 generate_target_chord_edges 完成 | "
            f"弦边有效边：{len(final_chord_edges)} | "
            f"树边有效边：{len(final_tree_edges)}"
        )

        return final_chord_edges, final_tree_edges, final_basis




# ==========================================
# 吞噬黑洞构建器 (Devouring Blackhole Builder)
# ==========================================
class DevouringBlackholeBuilder:
    """吞噬黑洞构建器 - FrozenSet[int] 逻辑标准的 Tuple 环存储统一版"""

    def __init__(self, global_edges: Set[Tuple[int, int]], candidates: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]) -> None:
        start_time = time.time()
        Debug.info(f"🚀 DevouringBlackholeBuilder 初始化 | 候选环数: {len(candidates)} | 边数: {len(global_edges)}")

        # 1. 全局图
        self.global_edges = self._normalize_edges(global_edges)
        self.global_data_init = DataInitialization(self.global_edges)
        self.global_adj = self.global_data_init.adj
        self.global_edge_to_eid = self.global_data_init.edge_to_eid
        self.global_target_rank = self.global_data_init.target_rank
        self.global_tree_basis = self._normalize_cycle_list(self.global_data_init.basis)

        # =========================================================
        # 闭包绑定：将依赖 global_adj 的验证函数绑定为实例方法（完全内联实现）
        # =========================================================

        _adj = self.global_adj

        def _verify_chordless_cycle(
            cycle: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]
        ) -> bool:
            """验证给定环是否为无弦环（完全内联，不调用外部函数）"""
            if not cycle:
                return False

            path_set = set(cycle[2])
            path_edges = set(cycle[1])

            # 0. 基本结构检查
            if len(path_set) < 3:
                return False
            if len(path_edges) != len(path_set):
                return False

            # 所有边必须完全属于 path_set
            for u, v in path_edges:
                if u == v:
                    return False
                if u not in path_set or v not in path_set:
                    return False

            # 1. 构建局部邻接
            local_adj: Dict[int, Set[int]] = defaultdict(set)
            for u, v in path_edges:
                local_adj[u].add(v)
                local_adj[v].add(u)

            # 2. 连通性检查
            start = next(iter(path_set))
            visited = {start}
            queue = deque([start])
            while queue:
                node = queue.popleft()
                for neighbor in local_adj.get(node, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            if len(visited) != len(path_set):
                return False

            # 3. 环结构 + 无弦检查
            for node in path_set:
                local_deg = len(local_adj.get(node, set()))
                global_induced_deg = len(_adj.get(node, set()) & path_set)
                # 环中每个节点局部度数必须为2
                if local_deg != 2:
                    return False
                # 无弦要求全局诱导度数也必须为2
                if global_induced_deg != 2:
                    return False

            return True

        def _verify_chordless_path(
            cycle: Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]
        ) -> bool:
            """验证给定路径是否为无弦路径（完全内联，不调用外部函数）"""
            path_set = set(cycle[2])
            path_edges = set(cycle[1])

            # 0. 基本结构检查
            if len(path_set) < 3:
                return False
            if len(path_edges) != len(path_set) - 1:
                return False

            # 所有边必须完全落在 path_set 内
            for u, v in path_edges:
                if u == v:
                    return False
                if u not in path_set or v not in path_set:
                    return False

            # 1. 构建局部邻接
            local_adj: Dict[int, Set[int]] = defaultdict(set)
            for u, v in path_edges:
                local_adj[u].add(v)
                local_adj[v].add(u)

            # 2. 连通性检查
            start = next(iter(path_set))
            visited = {start}
            queue = deque([start])
            while queue:
                node = queue.popleft()
                for neighbor in local_adj.get(node, set()):
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
            if len(visited) != len(path_set):
                return False

            # 3. 局部路径结构 + 全局无弦检查
            endpoints = 0
            for node in path_set:
                local_deg = len(local_adj.get(node, set()))
                global_induced_deg = len(_adj.get(node, set()) & path_set)

                # 无弦要求：全局诱导度数 == 局部路径度数
                if local_deg != global_induced_deg:
                    return False

                # 路径端点
                if local_deg == 1:
                    endpoints += 1
                # 路径内部节点
                elif local_deg == 2:
                    pass
                # 其它度数全部非法
                else:
                    return False

            return endpoints == 2

        # 其余三个闭包保持不变（仍依赖 StaticMethod 或已内联）
        def _verify_chordless_path_nodes(nodes: FrozenSet[int]) -> bool:
            node_set = set(nodes)
            if len(node_set) < 2:
                return False
            local_edges = {(u, v) for u in node_set for v in _adj.get(u, set()) if v in node_set and u < v}
            if len(local_edges) != len(node_set) - 1:
                return False
            local_adj = defaultdict(set)
            for u, v in local_edges:
                local_adj[u].add(v)
                local_adj[v].add(u)
            endpoints = 0
            for node in node_set:
                local_degree = len(local_adj[node])
                induced_degree = len(_adj.get(node, set()) & node_set)
                if local_degree != induced_degree:
                    return False
                if local_degree == 1:
                    endpoints += 1
                elif local_degree != 2:
                    return False
            return endpoints == 2

        def _verify_chordless_cycle_nodes(nodes: FrozenSet[int]) -> bool:
            node_set = set(nodes)
            if len(node_set) < 3:
                return False
            return all(len(_adj.get(n, set()) & node_set) == 2 for n in node_set)

        def _generate_chordless_mapping_nodes(nodes: FrozenSet[int]) -> Tuple[List[int], List[int]]:
            node_set = set(nodes)
            local_adj = defaultdict(set)
            for u in node_set:
                for v in _adj.get(u, set()):
                    if v in node_set:
                        local_adj[u].add(v)
            endpoints, midpoints = [], []
            for node in node_set:
                degree = len(local_adj[node])
                induced_degree = len(_adj.get(node, set()) & node_set)
                if degree != induced_degree:
                    return [], []
                if degree == 1:
                    endpoints.append(node)
                elif degree == 2:
                    midpoints.append(node)
                else:
                    return [], []
            return (endpoints, midpoints) if len(endpoints) == 2 else ([], [])

        # 绑定到实例
        self._verify_chordless_cycle = _verify_chordless_cycle
        self._verify_chordless_path = _verify_chordless_path
        self._verify_chordless_path_nodes = _verify_chordless_path_nodes
        self._verify_chordless_cycle_nodes = _verify_chordless_cycle_nodes
        self._generate_chordless_mapping_nodes = _generate_chordless_mapping_nodes

        # 2. 全局生成树基分类
        self.tree_basis_chordless: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        self.tree_basis_chorded: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        for cyc in self.global_tree_basis:
            if self._verify_chordless_cycle(cyc):
                self.tree_basis_chordless.append(cyc)
            else:
                self.tree_basis_chorded.append(cyc)

        # 3. 保存原始候选环
        self.original_candidates = self._normalize_cycle_list(candidates)
        original_candidates_edges: Set[Tuple[int, int]] = {edge for cycle in self.original_candidates for edge in cycle[1]}
        self.original_candidates_edges = self._normalize_edges(original_candidates_edges)
        self.core_tree_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        self.current_tree_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        self.blackhole_tree_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []

        self.core_edges: Set[Tuple[int, int]] = set()
        self.current_edges: Set[Tuple[int, int]] = set()
        self.blackhole_edges: Set[Tuple[int, int]] = set()
        self.onion_edges: Set[Tuple[int, int]] = set()
        self.all_edges: Set[Tuple[int, int]] = set()

        # 4. 由候选环构造 core_edges
        self.core_edges, self.current_edges, self.blackhole_edges, self.onion_edges = self.generate_core_edges(self.original_candidates)
        self.all_edges = self.original_candidates_edges | self.onion_edges

        self.all_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        self.all_cycles = self.get_correst_rest_cycles()

        # 核心图 —— 核心中的核心
        if len(self.core_edges) > 0:
            self.core_data_init = DataInitialization(self.core_edges)
            self.core_adj = self.core_data_init.adj
            self.core_edge_to_eid = self.core_data_init.edge_to_eid
            self.core_target_rank = self.core_data_init.target_rank
            self.core_tree_basis = self._normalize_cycle_list(self.core_data_init.basis)

        # 当前图 —— 核心中的候选
        if len(self.current_edges) > 0:
            self.current_data_init = DataInitialization(self.current_edges)
            self.current_adj = self.current_data_init.adj
            self.current_edge_to_eid = self.current_data_init.edge_to_eid
            self.current_target_rank = self.current_data_init.target_rank
            self.current_tree_basis = self._normalize_cycle_list(self.current_data_init.basis)

        # 黑洞图 —— 核心中的生成树
        if len(self.blackhole_edges) > 0:
            self.blackhole_data_init = DataInitialization(self.blackhole_edges)
            self.blackhole_adj = self.blackhole_data_init.adj
            self.blackhole_edge_to_eid = self.blackhole_data_init.edge_to_eid
            self.blackhole_target_rank = self.blackhole_data_init.target_rank
            self.blackhole_tree_basis = self._normalize_cycle_list(self.blackhole_data_init.basis)

        # 洋葱辅助结构
        self.onion_node_to_edges: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        self.onion_edge_to_nodes: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        self.onion_best_edges_adj: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        self.tree_chordless_cycles_edges: Set[Tuple[int, int]] = set()
        self.tree_chordless_cycles_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        self.current_components_count: int = 0

        Debug.fuse(f"[DevouringBlackholeBuilder] 初始化完成 | 基底环数: {len(self.original_candidates)}")
        Debug.timing("DevouringBlackholeBuilder 初始化完成", time.time() - start_time)

    # =========================================================
    # 一、辅助工具函数（类方法 / 静态方法 / 不依赖实例状态的辅助）
    # =========================================================

    @classmethod
    def _make_cycle(cls, eids: Iterable[int], edges: Iterable[Tuple[int, int]], nodes: Iterable[int]) -> Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]:
        normalized_edges = frozenset((min(u, v), max(u, v)) for u, v in edges)
        return frozenset(eids), normalized_edges, frozenset(nodes)

    @classmethod
    def _cycle_from_nodes(cls, nodes: Iterable[int], adj: Dict[int, Set[int]], edge_to_eid: Dict[Tuple[int, int], int]) -> Optional[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """FrozenSet[int] 节点环 → Tuple 环"""
        node_set = frozenset(nodes)
        if len(node_set) < 3:
            return None
        edges = {(u, v) for u in node_set for v in adj.get(u, set()) if v in node_set and u < v}
        if len(edges) != len(node_set):
            return None
        if any(len(adj.get(n, set()) & node_set) != 2 for n in node_set):
            return None
        eids = set()
        for edge in edges:
            eid = edge_to_eid.get(edge)
            if eid is None:
                return None
            eids.add(eid)
        return cls._make_cycle(eids, edges, node_set)

    @classmethod
    def _normalize_cycle(cls, cycle) -> Optional[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """统一将输入环转换成 Tuple 三元组"""
        if isinstance(cycle, tuple) and len(cycle) == 3:
            return (
                frozenset(cycle[0]),
                frozenset((min(u, v), max(u, v)) for u, v in cycle[1]),
                frozenset(cycle[2])
            )
        return None

    @classmethod
    def _normalize_cycle_list(cls, cycles) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        result = []
        for cycle in cycles or []:
            normalized = cls._normalize_cycle(cycle)
            if normalized is not None:
                result.append(normalized)
        return list(set(result))

    @staticmethod
    def _normalize_edges(edges: Set[Tuple[int, int]]) -> Set[Tuple[int, int]]:
        return {(min(u, v), max(u, v)) for u, v in edges if u != v}

    @staticmethod
    def _normalize_edge(u: int, v: int) -> Tuple[int, int]:
        return min(u, v), max(u, v)

    @staticmethod
    def _edges_to_cycles_mapping(global_edges: Set[Tuple[int, int]], global_tree_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]
        ) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]], Dict[int, Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]], Dict[Tuple[int, int], Set[int]]]:
        """从黑洞资产提取真实边集"""
        edges: Set[Tuple[int, int]] = set()
        
        # 建立 Cycle 到 EID 的映射
        cycle_to_eid: Dict[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]], int] = {
            cycle: i for i, cycle in enumerate(sorted(global_tree_basis))
        }
        eid_to_cycle: Dict[int, Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = {
            i: cycle for cycle, i in cycle_to_eid.items()
        }
        
        # 初始化所有全局边的映射集合
        edges_to_cycles_eids_mapping: Dict[Tuple[int, int], Set[int]] = {edge: set() for edge in global_edges}
        
        # 填充映射
        for cycle in global_tree_basis:
            if isinstance(cycle, tuple) and len(cycle) == 3:
                for u, v in cycle[1]:
                    edge = (min(u, v), max(u, v))
                    edges.add(edge)
                    edges_to_cycles_eids_mapping[edge].add(cycle_to_eid[cycle])
                    
        chord_edges: Set[Tuple[int, int]] = set()
        tree_edges: Set[Tuple[int, int]] = set()
        
        # 修正：精确分离 弦边、树边、游离边
        for edge, cycle_eids in edges_to_cycles_eids_mapping.items():
            if len(cycle_eids) > 1:
                tree_edges.add(edge)
            elif len(cycle_eids) == 1:
                chord_edges.add(edge)
                
        return chord_edges, tree_edges, eid_to_cycle, edges_to_cycles_eids_mapping

    def _extract_edges_from_cycles(self, cycles: Iterable[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]) -> Set[Tuple[int, int]]:
        """以真实 edge 集 cycle[1] 为权威"""
        edges: Set[Tuple[int, int]] = set()
        for cycle in cycles or []:
            if isinstance(cycle, tuple) and len(cycle) == 3:
                for u, v in cycle[1]:
                    edges.add(self._normalize_edge(u, v))
        return edges

    def generate_core_edges(self, candidates: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]) -> Tuple[Set[Tuple[int, int]], Set[Tuple[int, int]], Set[Tuple[int, int]], Set[Tuple[int, int]]]:
        """从候选环得到核心边集（加入连通性自愈机制）"""
        start_time = time.time()  # 计时开始

        self.core_edges: Set[Tuple[int, int]] = set()
        self.current_edges: Set[Tuple[int, int]] = set()
        self.blackhole_edges: Set[Tuple[int, int]] = set()
        self.onion_edges: Set[Tuple[int, int]] = set()

        current_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            self.global_edges, list(set(candidates + self.tree_basis_chordless)), self.global_target_rank
        )
        current_cycles_sorted = sorted(current_basis, key=lambda c: len(c[2]))
        Debug.info(f"[DEBUG] 当前基底数量: {len(current_cycles_sorted)}, 原始候选环数量: {len(candidates)}")
        if is_full:
            elapsed = time.time() - start_time
            Debug.info(f"[⏱️ 耗时] generate_core_edges: {elapsed:.4f} 秒")
            return self.core_edges, self.current_edges, self.blackhole_edges, self.global_edges

        global_chord_edges, global_tree_edges, global_eid_to_cycle, global_edges_to_cycles_eids_mapping = self._edges_to_cycles_mapping(self.global_edges, self.global_tree_basis)
        _, _, original_eid_to_cycle, original_edges_to_cycles_eids_mapping = self._edges_to_cycles_mapping(self.global_edges, self.original_candidates)
        
        core_edges_list: List[Set[Tuple[int, int]]] = []
        core_reducer = BlockwiseCycleReducer(self.global_edges, current_cycles_sorted)
        for edge in global_chord_edges:
            temp_core_edges: Set[Tuple[int, int]] = set()
            for cycle_eid in global_edges_to_cycles_eids_mapping[edge]:
                if core_reducer.check_independent(global_eid_to_cycle[cycle_eid]):
                    temp_core_edges.add(edge)
            if len(temp_core_edges) > 0:
                core_edges_list.append(temp_core_edges)
                
        core_edges_count: Dict[Tuple[int, int], int] = {edge: 0 for edge in self.global_edges}
        core_edge_list: List[Tuple[int, int]] = [edge for edges in core_edges_list for edge in edges]
        core_edges_count = Counter(core_edge_list)
        
        # 1. 原始聚合
        raw_core = set()
        for edge, count in core_edges_count.items():
            if original_edges_to_cycles_eids_mapping[edge]:
                for cycle_eid in original_edges_to_cycles_eids_mapping[edge]:
                    raw_core.update(original_eid_to_cycle[cycle_eid][1])
                    
        raw_current = set()
        raw_blackhole = set()
        for edge in raw_core:
            raw_current.add(edge)
            for cycle_eid in original_edges_to_cycles_eids_mapping[edge]:
                raw_current.update(original_eid_to_cycle[cycle_eid][1])
                
            raw_blackhole.add(edge)
            if edge in global_chord_edges:
                for cycle_eid in global_edges_to_cycles_eids_mapping[edge]:
                    raw_blackhole.update(global_eid_to_cycle[cycle_eid][1])

        # =================================================================
        # 🛡️ 连通性自愈机制 (Topological Self-Healing)
        # =================================================================
        def heal_edge_set(edges: Set[Tuple[int, int]], mapping: Dict, eid_to_cycle: Dict, name: str) -> Set[Tuple[int, int]]:
            if not edges:
                return edges
                
            # 如果连通量为 1，直接放行
            if DataInitialization(edges).connected_components_count == 1:
                return edges
                
            Debug.warn(f"[{name}] 连通分量 > 1 (已碎裂)！启动最长无弦环自愈重建...")
            
            # 找到最长的无弦环（定海神针）
            if not self.tree_basis_chordless:
                return edges  # 兜底：如果没有无弦环则返回原状
            longest_cyc = max(self.tree_basis_chordless, key=lambda c: len(c[2]))
            
            # 以最长环的边为骨架，吸附所有相关环
            healed_edges = set(longest_cyc[1])
            for e in longest_cyc[1]:
                if e in mapping:
                    for cycle_eid in mapping[e]:
                        healed_edges.update(eid_to_cycle[cycle_eid][1])
                        
            Debug.done(f"[{name}] 🩹 自愈完成！利用长为 {len(longest_cyc[1])} 的骨架环，重构为连通边集 (边数={len(healed_edges)})")
            return healed_edges

        # 2. 执行自愈检查，生成最终的绝对连通集
        self.core_edges = heal_edge_set(
            raw_core, original_edges_to_cycles_eids_mapping, original_eid_to_cycle, "CoreEdges"
        )
        self.current_edges = heal_edge_set(
            raw_current, original_edges_to_cycles_eids_mapping, original_eid_to_cycle, "CurrentEdges"
        )
        self.blackhole_edges = heal_edge_set(
            raw_blackhole, global_edges_to_cycles_eids_mapping, global_eid_to_cycle, "BlackholeEdges"
        )

        self.onion_edges: Set[Tuple[int, int]] = set()
        for two_edges in itertools.combinations([self.core_edges, self.current_edges, self.blackhole_edges], 2):
            if two_edges[0] & two_edges[1]:
                self.onion_edges = self.onion_edges | (two_edges[0] | two_edges[1])


        elapsed = time.time() - start_time
        Debug.info(f"[⏱️ 耗时] generate_core_edges: {elapsed:.4f} 秒, 汇总连通边集：{len(self.onion_edges)}")
        return self.core_edges, self.current_edges, self.blackhole_edges, self.onion_edges

    def local_all_spanning_tree_cycles(
        self,
        root_node: int,
    ) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """
        以指定根节点构建生成树，返回基本回路三元组列表。

        Args:
            global_edges: 全局边集
            root_node: 根节点

        Returns:
            基本回路列表
        """
        start_time = time.time()  # 计时开始

        self.global_adj_list: Dict[int, List[int]] = defaultdict(list)
        for u, v in self.global_edges:
            self.global_adj_list[u].append(v)
            self.global_adj_list[v].append(u)

        # BFS 生成树
        visited: Set[int] = set()
        tree_edges: Set[Tuple[int, int]] = set()
        non_tree_edges: Set[Tuple[int, int]] = set()

        ordered_starts = [root_node] + [n for n in self.global_adj_list if n != root_node]
        for start in ordered_starts:
            if start in visited:
                continue
            queue = deque([(start, -1)])
            visited.add(start)
            while queue:
                curr, parent = queue.popleft()
                for nb in self.global_adj_list[curr]:
                    if nb not in visited:
                        visited.add(nb)
                        edge = (min(curr, nb), max(curr, nb))
                        tree_edges.add(edge)
                        queue.append((nb, curr))
                    elif nb != parent:
                        edge = (min(curr, nb), max(curr, nb))
                        if edge not in tree_edges:
                            non_tree_edges.add(edge)

        # 树邻接表
        tree_adj: Dict[int, List[int]] = defaultdict(list)
        for u, v in tree_edges:
            tree_adj[u].append(v)
            tree_adj[v].append(u)

        # 构造基本回路
        result = []
        for u, v in non_tree_edges:
            q: Any = deque([[u]])
            vis = {u}
            path: List[int] = []
            while q:
                p = q.popleft()
                node = p[-1]
                if node == v:
                    path = p
                    break
                for nxt in tree_adj[node]:
                    if nxt not in vis:
                        vis.add(nxt)
                        q.append(p + [nxt])

            if not path:
                continue

            cycle_nodes = frozenset(path)
            cycle_edges = frozenset(
                {(min(path[i], path[i + 1]), max(path[i], path[i + 1]))
                 for i in range(len(path) - 1)}
                | {(min(u, v), max(u, v))}
            )
            cycle_eids = frozenset(self.global_edge_to_eid[e] for e in cycle_edges)
            result.append((cycle_eids, cycle_edges, cycle_nodes))

        elapsed = time.time() - start_time
        Debug.info(f"[⏱️ 耗时] local_all_spanning_tree_cycles: {elapsed:.4f} 秒")
        return result

    def run_localized_horton(
        self,
        seed_nodes: Set[int],
        current_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
    ) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """
        局部定向 Horton 扫尾探测。

        Args:
            global_edges: 全局边集
            seed_nodes: 种子节点集合
            current_cycles: 当前环基

        Returns:
            更新后的环基
        """
        start_time = time.time()  # 计时开始

        if not seed_nodes:
            elapsed = time.time() - start_time
            Debug.info(f"[⏱️ 耗时] run_localized_horton: {elapsed:.4f} 秒")
            return current_cycles

        # 构建邻接与 EID
        g_adj: Dict[int, Set[int]] = defaultdict(set)
        nodes: Set[int] = set()
        for u, v in self.global_edges:
            g_adj[u].add(v)
            g_adj[v].add(u)
            nodes.update((u, v))

        edge_to_eid = {e: i for i, e in enumerate(sorted(self.global_edges))}

        # 连通分量 & 目标秩
        visited: Set[int] = set()
        components = 0
        for n in nodes:
            if n not in visited:
                components += 1
                q = deque([n])
                visited.add(n)
                while q:
                    c = q.popleft()
                    for nb in g_adj[c]:
                        if nb not in visited:
                            visited.add(nb)
                            q.append(nb)
        target_rank = len(self.global_edges) - len(nodes) + components

        Debug.info(f"▶ Horton精准点杀 | 种子点数: {len(seed_nodes)}")

        # 全源 BFS
        all_paths: Dict[int, Dict[int, List[int]]] = {}
        for s in seed_nodes:
            paths: Dict[int, List[int]] = {s: [s]}
            q = deque([s])
            while q:
                v = q.popleft()
                for w in g_adj[v]:
                    if w not in paths:
                        paths[w] = paths[v] + [w]
                        q.append(w)
            all_paths[s] = paths

        # 枚举环
        horton_cycles = []
        seen: Set[FrozenSet[int]] = set()
        for x, y in self.global_edges:
            for s in seed_nodes:
                px = all_paths[s].get(x)
                py = all_paths[s].get(y)
                if px is None or py is None:
                    continue

                # LCA 必须为种子点本身
                last_common = None
                for i in range(min(len(px), len(py))):
                    if px[i] == py[i]:
                        last_common = px[i]
                    else:
                        break
                if last_common != s:
                    continue

                sig = frozenset(px + py)
                if len(sig) < 3 or sig in seen:
                    continue
                seen.add(sig)

                c_edges = frozenset(e for e in self.global_edges if e[0] in sig and e[1] in sig)
                c_eids = frozenset(edge_to_eid[e] for e in c_edges)
                temp = (c_eids, c_edges, sig)

                if StaticMethod.verify_chordless_cycle(temp, g_adj):
                    horton_cycles.append(temp)

        horton_cycles.sort(key=lambda c: len(c[2]))

        result, _ = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidates=current_cycles + horton_cycles,
            global_target_rank=target_rank,
        )
        elapsed = time.time() - start_time
        Debug.info(f"[⏱️ 耗时] run_localized_horton: {elapsed:.4f} 秒")
        return result

    # =========================================================
    # 二、核心逻辑函数
    # =========================================================
    def get_correst_rest_cycles(self) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """
        【合并重构版】增量消元与基底提纯（实例方法）
        """
        start_time = time.time()  # 计时开始
        
        is_connected, is_local_rank, is_global_edges = StaticMethod.verify_local_blackhole(
            global_edges=self.global_edges, candidates=self.all_cycles,
        )
        if is_connected and (is_local_rank or is_global_edges):
            return list(set(self.all_cycles))
        if len(self.all_edges) < len(self.original_candidates_edges) + len(self.onion_edges) and len(self.all_edges) < len(self.global_edges):
            all_data_init = DataInitialization(self.all_edges)
            all_adj = all_data_init.adj
            all_edge_to_eid = all_data_init.edge_to_eid
            all_target_rank = all_data_init.target_rank
            all_tree_basis = self._normalize_cycle_list(all_data_init.basis)
            all_tree_basis_chordless = [cyc for cyc in all_tree_basis if self._verify_chordless_cycle(cyc)]
            self.all_cycles.extend(all_tree_basis_chordless)
            self.all_cycles = list(set(self.all_cycles))
            self.core_edges, self.current_edges, self.blackhole_edges, self.onion_edges = self.generate_core_edges(self.all_cycles)

        elapsed = time.time() - start_time
        Debug.info(f"[⏱️ 耗时] get_correst_rest_cycles: {elapsed:.4f} 秒")
        return list(set(self.all_cycles))

    def get_blackhole_basis(self) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """黑洞基底提取 - 重复调用 generate_core_edges + get_correst_rest_cycles 直至无弦环数量稳定"""
        start_time = time.time()
        Debug.info(f"[DEBUG] 开始提取黑洞基底 (迭代精炼版)")

        # 初始化候选环池：原始候选环 + 全局树基中的无弦环
        self.all_cycles = list(set(self.original_candidates + self.tree_basis_chordless))

        prev_chordless_count = -1
        iteration = 0

        while True:
            iteration += 1
            Debug.info(f"--- 黑洞提取迭代 {iteration} ---")

            # ① 用当前候选环重新生成核心/当前/黑洞/洋葱边集
            self.core_edges, self.current_edges, self.blackhole_edges, self.onion_edges = \
                self.generate_core_edges(self.all_cycles)

            # ② 扩展候选环（内部可能再次调用 generate_core_edges）
            self.all_cycles = self.get_correst_rest_cycles()

            # ③ 统计当前无弦环数量
            chordless_count = len([c for c in self.all_cycles if self._verify_chordless_cycle(c)])
            Debug.info(f"    当前无弦环数量: {chordless_count}")

            # ④ 无弦环数量不再增长则收敛退出
            if chordless_count == prev_chordless_count:
                Debug.info(f"✅ 无弦环数量稳定在 {chordless_count}，停止迭代")
                break

            prev_chordless_count = chordless_count

        # 最终筛选无弦环并进行线性无关约简
        chordless_pool = [c for c in self.all_cycles if self._verify_chordless_cycle(c)]
        final_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            self.global_edges, chordless_pool, self.global_target_rank
        )

        Debug.info(f"📈 [环数量追踪 - 黑洞] 最终确认纯净无弦环总数: {len(final_basis)}")
        Debug.timing("get_blackhole_basis 完成", time.time() - start_time)
        return final_basis

    def get_chorded_seeds_for_onion(
        self,
        candidates: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]],
    ) -> Tuple[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]], Set[Tuple[int, int]]]:
        """
        【缺失维度侦测器】
        当局部无弦环无法满秩时，寻找那些“占用了关键维度”的【有弦环】，
        提取它们的边，作为触发洋葱生长的绝对精准种子点！
        """
        # 1. 提取当前候选环的局部边界
        cycle_candidates = [cyc for cyc in candidates if len(cyc[2]) == len(cyc[1])]
        local_edges = set()
        for cyc in cycle_candidates:
            local_edges.update(cyc[1])
            
        if not local_edges:
            return [], set()
            
        local_data = DataInitialization(local_edges)
        local_target_rank = local_data.target_rank
        
        reducer = BlockwiseCycleReducer(self.global_edges, cycle_candidates)
        current_basis = list(reducer.valid_basis)
        
        if len(current_basis) >= local_target_rank:
            return [], set()
            
        # 筛选出完全落在局部范围内的全局树基底
        local_tree_cycles = []
        for cyc in self.global_tree_basis:
            if len(cyc[2]) == len(cyc[1]) and cyc[1].issubset(local_edges):
                local_tree_cycles.append(cyc)
                
        # 核心：严格分为两大梯队
        local_chordless = [cyc for cyc in local_tree_cycles if self._verify_chordless_cycle(cyc)]
        local_chorded = [cyc for cyc in local_tree_cycles if not self._verify_chordless_cycle(cyc)]
        
        new_chordless_cycles = []
        seed_edges = set()
        
        # 🥇 第一阶段：先无弦环！(尽最大可能用完美环填满空间)
        for cyc in local_chordless:
            if len(current_basis) >= local_target_rank:
                break
            added = reducer.add_candidate(cyc)
            if added is not None:
                current_basis.append(added)
                new_chordless_cycles.append(added)
                
        # 🥈 第二阶段：再有弦环！(如果无弦环填不满，用有弦环测出缺失维度的坐标)
        if len(current_basis) < local_target_rank:
            for cyc in local_chorded:
                if len(current_basis) >= local_target_rank:
                    break
                added = reducer.add_candidate(cyc)
                if added is not None:
                    current_basis.append(added)
                    seed_edges.update(added[1])  # 提取其边缘作为洋葱生长的绝对种子！
                    
        if new_chordless_cycles or seed_edges:
            Debug.info(f"🧩 局部维度侦测完成！捡漏无弦环 {len(new_chordless_cycles)} 个，锁定有弦环种子边 {len(seed_edges)} 条")
            
        return new_chordless_cycles, seed_edges

    def get_onion_basis(self) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        """洋葱式生长提取 (自适应形态：密集边界直接重构，稀疏断桥贪心延长)"""
        start_time = time.time()
        Debug.info("\n" + "="*60)
        Debug.info("🧅 get_onion_basis 启动")
        Debug.info(f"  当前 all_cycles 数量: {len(self.all_cycles)}")
        Debug.info(f"  全局边数: {len(self.global_edges)}, 目标秩: {self.global_target_rank}")

        # =================================================================
        # 1. 提取维度空洞，试探外部边界 (3节点探针)
        # =================================================================
        Debug.info("\n[阶段1] 提取锚点边（弦边）...")
        chord_edges, tree_edges, global_tree_basis = (
            DimensionCycleExtractor.generate_target_chord_edges(
                self.global_edges, self.global_tree_basis, self.all_cycles, self.global_target_rank,
            )
        )
        anchor_edges = chord_edges
        Debug.info(f"  锚点边数量: {len(anchor_edges)}, 树边数量: {len(tree_edges)}")

        # =================================================================
        # 2. 策略 B：贪心延长路径 (针对“独木桥”稀疏断桥)
        # =================================================================
        Debug.info("\n[阶段2] 查找独立路径（长度4）...")
        independent_paths: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        for is_cycle, paths_batch in CyclesAndPathsFinder.find_four_cycles_and_paths(self.global_edges, anchor_edges, "path"):
            if not is_cycle and len(paths_batch) > 0:
                independent_paths.extend(paths_batch)
        Debug.info(f"  原始路径数量: {len(independent_paths)}")

        best_edges: Set[Tuple[int, int]] = set()
        _, independent_paths, _, is_full = StaticMethod._final_incremental_reduction(
            self.global_edges, independent_paths, self.global_target_rank,
        )
        Debug.info(f"  约简后独立路径数量: {len(independent_paths)}, 满秩: {is_full}")
        if not is_full:
            Debug.info(f"⚠️ 警告：独立路径尚未满秩，差额: {self.global_target_rank - len(independent_paths)}")
        for path in independent_paths:
            best_edges.update(path[1])
        Debug.info(f"  收集到的种子边数量: {len(best_edges)}")

        # ---------- 第三步：构建节点/边映射，准备洋葱生长 ----------
        Debug.info("\n[阶段3] 构建拓扑映射...")
        best_edges_frozenset_adj: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        node_to_edges: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        edge_to_nodes: Dict[FrozenSet[int], Set[FrozenSet[int]]] = defaultdict(set)
        best_nodes_int_set: Set[int] = set(node for edge in best_edges for node in edge)
        Debug.info(f"  种子边覆盖节点数: {len(best_nodes_int_set)}")
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
        Debug.info("\n[阶段4] 洋葱路径生长...")
        chordless_paths: Set[FrozenSet[int]] = set()
        total_start_nodes = len(node_to_edges)
        processed_nodes = 0
        for start_node, edges in node_to_edges.items():
            processed_nodes += 1
            if len(edges) == 0:
                continue
            if processed_nodes % 10 == 0 or processed_nodes == total_start_nodes:
                Debug.info(f"  处理节点 {processed_nodes}/{total_start_nodes}, 已发现无弦路径: {len(chordless_paths)}")

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
                    if CyclesAndPathsFinder.verify_chordless_path(list(path), self.global_adj):
                        endpoints, midpoints = CyclesAndPathsFinder.generate_chordless_mapping(list(path), self.global_adj)
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
                                if CyclesAndPathsFinder.verify_chordless_path(list(path), self.global_adj):
                                    endpoints, midpoints = CyclesAndPathsFinder.generate_chordless_mapping(list(path), self.global_adj)
                                    if len(frozenset(endpoints) & start_node_neighbors_set) == 1 and len(endpoints) == 2:
                                        next_node = frozenset(endpoints) - (frozenset(endpoints) & start_node_neighbors_set)
                                        visited = visited | next_node
                                        path = visited
                                        next_edges = [e for e in node_to_edges[next_node] if len(e & visited) == 0]
                                        if len(next_edges) >= 1:
                                            next_edge = next(iter(next_edges))
                                            visited = visited | next_edge
                                            path = visited
                                            if CyclesAndPathsFinder.verify_chordless_path(list(path), self.global_adj) or CyclesAndPathsFinder.verify_chordless_cycle(list(path), self.global_adj):
                                                continue
                                        else:
                                            if CyclesAndPathsFinder.verify_chordless_path(list(path), self.global_adj) or CyclesAndPathsFinder.verify_chordless_cycle(list(path), self.global_adj):
                                                continue
                                            else:
                                                break
                                    else:
                                        if CyclesAndPathsFinder.verify_chordless_path(list(path), self.global_adj) or CyclesAndPathsFinder.verify_chordless_cycle(list(path), self.global_adj):
                                            continue
                                        else:
                                            break
        Debug.info(f"  洋葱路径生长完成，共找到无弦路径: {len(chordless_paths)}")

        # 将节点集合转换为标准三元组
        new_chordless_paths: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        for path in chordless_paths:
            triplet = CyclesAndPathsFinder._make_triplet_inline(list(path), self.global_adj, self.global_edge_to_eid)
            if triplet is not None:
                new_chordless_paths.append(triplet)
        Debug.info(f"  转换为三元组的路径数量: {len(new_chordless_paths)}")

        # ---------- 第五步：路径闭合为环 ----------
        Debug.info("\n[阶段5] 路径闭合为环...")
        onion_chordless = []
        for idx, nodes in enumerate(new_chordless_paths):
            if CyclesAndPathsFinder.verify_chordless_cycle(list(nodes[2]), self.global_adj):
                triplet = CyclesAndPathsFinder._make_triplet_inline(list(nodes[2]), self.global_adj, self.global_edge_to_eid)
                if triplet is not None:
                    onion_chordless.append(triplet)
            elif CyclesAndPathsFinder.verify_chordless_path(list(nodes[2]), self.global_adj):
                endpoints, midpoints = CyclesAndPathsFinder.generate_chordless_mapping(list(nodes[2]), self.global_adj)
                nodes_forbid = set()
                for node in midpoints:
                    nodes_forbid.update(self.global_adj[node])
                nodes_closed = self.global_adj[min(endpoints)] & self.global_adj[max(endpoints)] - set(midpoints) - nodes_forbid
                for node in nodes_closed:
                    cycle_nodes = sorted(set(endpoints + midpoints + [node]))
                    if CyclesAndPathsFinder.verify_chordless_cycle(cycle_nodes, self.global_adj):
                        triplet = CyclesAndPathsFinder._make_triplet_inline(cycle_nodes, self.global_adj, self.global_edge_to_eid)
                        if triplet is not None:
                            onion_chordless.append(triplet)
        Debug.info(f"  最终生成洋葱无弦环数量: {len(onion_chordless)}")
        Debug.info("="*60 + "\n")

        Debug.done(f"[run_new_class] 洋葱环提取完成 | 无弦环数量: {len(onion_chordless)}")
        return onion_chordless

    def get_more_long_cycles(self) -> List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]:
        # =====================================================================
        # 阶段一：黑洞吞噬
        # =====================================================================
        start_time = time.time()  # 计时开始

        original_candidates = [cyc for cyc in self.get_blackhole_basis() if self._verify_chordless_cycle(cyc)]
        final_result, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidates=list(set(original_candidates)),
            global_target_rank=self.global_target_rank
        )
        if is_full:
            elapsed = time.time() - start_time
            Debug.info(f"[⏱️ 耗时] get_more_long_cycles: {elapsed:.4f} 秒")
            return final_result

        # =====================================================================
        # 阶段二：洋葱爆破 (附带状态强制同步)
        # =====================================================================

        # 否则洋葱算法内部会读到空的 blackhole_edges！
        self.blackhole_basis = final_result
        Debug.info(f"🎯 [黑洞吞噬] 数量: {len(self.blackhole_basis)}")

        onion_assets = self.get_onion_basis()
        Debug.info(f"🎯 [洋葱爆破] 数量: {len(onion_assets)}")
        # 收集洋葱资产的节点，交给后续 Horton 作为最强诱饵，决不直接塞进 final_result 污染基底！
        onion_seed_nodes = set()
        for asset in onion_assets:
            onion_seed_nodes.update(asset[2])
        final_result = onion_assets + self.blackhole_basis
        final_result = list(set(final_result))
        final_result, is_full = CSRBlackholeDevourer._final_incremental_reduction(
            global_edges=self.global_edges,
            candidates=list(set(final_result + self.original_candidates)),
            global_target_rank=self.global_target_rank
        )
        Debug.fuse(f"黑洞算法和洋葱算法最终返回 {len(final_result)} 个无弦环")
        # =====================================================================
        # 阶段三：高维枢纽树扩展
        # =====================================================================
        chordless_cycles_only = [cyc for cyc in final_result if self._verify_chordless_cycle(cyc)]
        if chordless_cycles_only:
            tree_basis_chordless: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
            final_result_sorted = sorted(chordless_cycles_only, key=lambda x: len(x[2]))
            nodes_length_list = [(node, len(self.global_adj[node])) for node in list(final_result_sorted[-1][2])]
            sorted_nodes = sorted(nodes_length_list, key=lambda x: -x[1])
            nodes_set: Set[int] = set(node for node, _ in sorted_nodes)
            for node in nodes_set:
                tree_basis_cycles = self.local_all_spanning_tree_cycles(node)
                final_result.extend(tree_basis_cycles)
                final_result = list(set(final_result))
                final_result_chordless = [cyc for cyc in final_result if self._verify_chordless_cycle(cyc)]            
                final_result, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                    global_edges=self.global_edges,
                    candidates=list(set(final_result_chordless)),
                    global_target_rank=self.global_target_rank
                )
                if is_full:
                    Debug.fuse(f"[BFS Hub Expansion] 枢纽扩展完成，最终返回 {len(final_result)} 个无弦环, 已达到全秩")
                    elapsed = time.time() - start_time
                    Debug.info(f"[⏱️ 耗时] get_more_long_cycles: {elapsed:.4f} 秒")
                    return final_result
                    
        if is_full:
            elapsed = time.time() - start_time
            Debug.info(f"[⏱️ 耗时] get_more_long_cycles: {elapsed:.4f} 秒")
            return final_result
            
        # =====================================================================
        # 阶段四：Horton 弦环定位与精准扫尾 (最强闭合)
        # =====================================================================
        history_cycles = final_result
        massive_candidate_pool = []
        
        if not is_full:
            core_reducer = BlockwiseCycleReducer(self.global_edges, history_cycles)
            seed_nodes = set()
            
            # 1. 收集弦环提供的坐标诱饵
            for cycle in self.tree_basis_chorded:
                if core_reducer.add_candidate(cycle):
                    for node in set(list(cycle[2])):
                        if len(self.global_adj[node] & set(list(cycle[2]))) > 2:
                            seed_nodes.add(node)
                            
            # 2. 🎯 将洋葱提取的终极坐标，一并喂给 Horton！
            seed_nodes.update(onion_seed_nodes)
            
            if seed_nodes:
                Debug.info(f"🚀 [Horton精准扫尾] 接收到弦环与洋葱坐标诱饵共 {len(seed_nodes)} 个节点，发动最终闭合！")
                massive_candidate_pool = self.run_localized_horton(seed_nodes, history_cycles)
                history_cycles.extend(massive_candidate_pool)
                history_cycles = list(set(history_cycles))

                history_cycles_chordless = [cyc for cyc in history_cycles if self._verify_chordless_cycle(cyc)]
                history_cycles, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                global_edges=self.global_edges,
                candidates=history_cycles_chordless,
                global_target_rank=self.global_target_rank
            )
            Debug.info(f"🚀 [Horton扫尾结果] 已生成 {len(history_cycles)} 个无弦环，差额: {self.global_target_rank - len(history_cycles)}")
        
        elapsed = time.time() - start_time
        Debug.info(f"[⏱️ 耗时] get_more_long_cycles: {elapsed:.4f} 秒")
        return history_cycles

    @staticmethod
    def get_all_cycles(global_edges, candidates):
        """统一入口"""
        builder = DevouringBlackholeBuilder(global_edges=global_edges, candidates=candidates)
        return builder.get_more_long_cycles() 



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
    def __init__(self, global_edges: Set[Tuple[int, int]], history_cycles: Optional[List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]]] = None, history_cycles_len: Optional[List[int]] = None):
        self.global_edges = set((min(u, v), max(u, v)) for u, v in global_edges)
        self.data_init = DataInitialization(self.global_edges)
        self.global_target_rank = self.data_init.target_rank
        self.global_adj = self.data_init.adj
        self.global_edge_to_eid = self.data_init.edge_to_eid
        self.final_basis: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        
        Debug.section(f"主模块初始化 | 全局边数: {len(self.global_edges)}, 目标秩: {self.global_target_rank}")
        self.tree_edges: Set[Tuple[int, int]] = set()
        self.tree_basis_chordless: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
        self.tree_basis = self.data_init.basis

    @staticmethod
    def generate_target_cycles_original(global_edges):
        """生成基础环 (3-9环)"""
        history_cycles: List[Tuple[FrozenSet[int], FrozenSet[Tuple[int, int]], FrozenSet[int]]] = []
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


    # ==================== 主迭代逻辑 ====================
    def iterate_target_cycles(self):
        """迭代生成目标长度的无弦环（并行增强版）"""
        # 第一阶段：生成初始历史环（启用并行）
        history_cycles, is_full = self.generate_target_cycles_original(self.global_edges)
        max_history_cycle_len = max(len(cyc) for cyc in history_cycles) if history_cycles else 0
        history_cycles_chordless = sorted(
            [cyc for cyc in history_cycles if StaticMethod.verify_chordless_cycle(cyc, self.global_adj)], 
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



    # ═════════════════════════════════════════════════════════
    # 清洗 + 最终交付
    # ═════════════════════════════════════════════════════════
    def get_more_long_cycles(self):
        start_time = time.time()
        Debug.section("MORE 进入")
        generated_basis = list(self.iterate_target_cycles())
        Debug.section(f"MORE iterate 返回 basis={len(generated_basis)}")
        final_basis = []
        for cycle in generated_basis:
            if not isinstance(cycle, tuple) or len(cycle) != 3:
                continue
            if not cycle[1] or not cycle[2]:
                continue
            if StaticMethod.verify_chordless_cycle(cycle, self.global_adj):
                final_basis.append(cycle)
        final_basis = list(set(final_basis))

        if len(final_basis) >= self.global_target_rank:
            final_basis.sort(key=lambda cycle: len(cycle[2]))
            final_basis, is_full = CSRBlackholeDevourer._final_incremental_reduction(
                global_edges=self.global_edges,
                candidates=final_basis,
                global_target_rank=self.global_target_rank,
            )
        else:
            is_full = False

        from collections import Counter
        dist = Counter(len(c[2]) for c in final_basis)
        elapsed = time.time() - start_time

        if is_full:
            Debug.timing(
                f"[MORE][EXIT-01][满秩交付] 🎯 "
                f"环数={len(final_basis)} 分布={dict(sorted(dist.items()))}",
                elapsed,
            )
        else:
            Debug.timing(
                f"[MORE][EXIT-02][未满秩交付] ⚠️ "
                f"环数={len(final_basis)}/{self.global_target_rank} "
                f"gap={self.global_target_rank - len(final_basis)} "
                f"分布={dict(sorted(dist.items()))}",
                elapsed,
            )
        return final_basis



# ==============================================================================
# 🌐 公开 API
# ==============================================================================

def _load_edges(edges):
    """统一加载边集：支持文件路径或 Set[Tuple[int, int]]。"""
    if isinstance(edges, str):
        return set(StaticMethod.input_file_lines(edges))
    return set((min(u, v), max(u, v)) for u, v in edges)



def get_cycles_results(raw_edges):
    start_time = time.time()
    Debug.section("开始收集最终结果...")

    codec = IntPairBijectiveCodec(set(raw_edges))

    edges = set()
    for u, neighbors in codec.relation_map.items():
        for v in neighbors:
            edges.add((min(u, v), max(u, v)))

    controller = MainController(edges)
    final_basis = controller.get_more_long_cycles()

    real_cycles = []
    for cyc in final_basis:
        if not cyc or len(cyc) < 3:
            continue
        real_nodes = set()
        for node in cyc[2]:
            if isinstance(node, str):
                node = codec.decode_to_value(node)
            real_nodes.add(node)
        if real_nodes:
            real_cycles.append(real_nodes)

    Debug.timing(
        f"get_cycles_results 完成 | 共 {len(real_cycles)} 个环",
        time.time() - start_time
    )
    Debug.done(f"RESULT EXIT=01 共 {len(real_cycles)} 个环")
    return real_cycles



def chordless_cycle_basis(edges, output_file=None):
    """
    纯 Python 满秩无弦环基 —— 顶点集合版。

    完全依赖三层实现：
      - GraphDataEncoder  : 原始边 -> 大整数编码
      - DataInitialization: 邻接表 / 目标秩 / 生成树基础环
      - MainController    : 主环生成 + 反解回原始节点（get_cycles_results）

    Args:
        edges: Set[Tuple[int, int]] 或 文件路径 (str)
        output_file: 可选，输出文件路径（每行一个环，空格分隔顶点）

    Returns:
        List[Set[int]] — 满秩无弦环基，每个环为原始节点集合
    """
    raw = _load_edges(edges)
    result = get_cycles_results(raw)

    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            for cyc in result:
                f.write(" ".join(map(str, sorted(cyc))) + "\n")

    return result


def chordless_cycle_basis_edges(edges, output_file=None):
    """
    纯 Python 满秩无弦环基 —— 边集合版。

    顶点集合由 MainController.get_cycles_results 提供，
    再根据原始边集过滤出环内边。

    Args:
        edges: Set[Tuple[int, int]] 或 文件路径 (str)
        output_file: 可选，输出文件路径（每行一个环，u-v 空格分隔）

    Returns:
        List[FrozenSet[Tuple[int, int]]] — 满秩无弦环基，每个环为原始边集合
    """
    raw = _load_edges(edges)
    vertex_cycles = get_cycles_results(raw)

    result = []
    for cyc in vertex_cycles:
        edge_set = frozenset(
            (min(u, v), max(u, v))
            for u, v in raw
            if u in cyc and v in cyc
        )
        result.append(edge_set)

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

