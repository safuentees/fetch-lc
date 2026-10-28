#!/usr/bin/env python3
"""
run_lc.py — Run a practice file against its example cases, like LeetCode's
"Run" button. Cases live in cases/<name>.json (written by fetch_lc.py; add
your own there).

Usage:
    python scripts/run_lc.py arrays/001_two_sum.py

The practice file runs with LeetCode's usual names already imported
(List, Optional, ListNode, TreeNode, collections, heapq, ...), so it can stay
exactly like the LeetCode editor.

stdlib only.
"""
from __future__ import annotations

import json
import sys
from collections import deque
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

# What LeetCode's Python 3 judge has in scope before your code runs.
PRELUDE = """
from typing import *
from collections import *
from heapq import *
from bisect import *
from functools import *
from itertools import *
from math import *
import collections, heapq, bisect, functools, itertools, math, re, string
"""


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


# ---------------------------------------------------- JSON ↔ node helpers ---

def to_list_node(vals: list) -> ListNode | None:
    head = None
    for v in reversed(vals):
        head = ListNode(v, head)
    return head


def from_list_node(node: ListNode | None) -> list:
    out = []
    while node:
        out.append(node.val)
        node = node.next
    return out


def to_tree(vals: list) -> TreeNode | None:
    """Level-order list with nulls (LeetCode format) → tree."""
    if not vals or vals[0] is None:
        return None
    root = TreeNode(vals[0])
    queue, i = deque([root]), 1
    while queue and i < len(vals):
        node = queue.popleft()
        for side in ("left", "right"):
            if i < len(vals) and vals[i] is not None:
                child = TreeNode(vals[i])
                setattr(node, side, child)
                queue.append(child)
            i += 1
    return root


def from_tree(root: TreeNode | None) -> list:
    out: list = []
    queue = deque([root])
    while queue:
        node = queue.popleft()
        out.append(node.val if node else None)
        if node:
            queue.extend((node.left, node.right))
    while out and out[-1] is None:
        out.pop()
    return out


def to_arg(lc_type: str, v: Any) -> Any:
    if lc_type == "ListNode":
        return to_list_node(v)
    if lc_type == "TreeNode":
        return to_tree(v)
    if lc_type == "ListNode[]":
        return [to_list_node(x) for x in v]
    return v


def from_value(v: Any) -> Any:
    if isinstance(v, ListNode):
        return from_list_node(v)
    if isinstance(v, TreeNode):
        return from_tree(v)
    return v


# ------------------------------------------------------------------ running --

def call(ns: dict, meta: dict, args: list) -> Any:
    if meta.get("systemdesign"):
        # Design problems: args = [op names, op args]; first op is the constructor.
        ops, op_args = args
        obj = ns[meta["classname"]](*op_args[0])
        return [None] + [from_value(getattr(obj, op)(*a)) for op, a in zip(ops[1:], op_args[1:])]
    params = meta.get("params", [])
    conv = [to_arg(p["type"], a) for p, a in zip(params, args)]
    got = getattr(ns["Solution"](), meta["name"])(*conv)
    # "Do not return anything, modify in-place" → LeetCode checks the first arg.
    if meta.get("return", {}).get("type") == "void":
        got = conv[0]
    return from_value(got)


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1]).resolve()
    cases_path = REPO_ROOT / "cases" / f"{path.stem}.json"
    if not cases_path.exists():
        sys.exit(f"no cases file at {cases_path}")
    data = json.loads(cases_path.read_text(encoding="utf-8"))

    ns: dict[str, Any] = {"ListNode": ListNode, "TreeNode": TreeNode, "__name__": "solution"}
    exec(PRELUDE, ns)
    exec(compile(path.read_text(encoding="utf-8"), str(path), "exec"), ns)

    passed = checked = 0
    for i, case in enumerate(data["cases"], 1):
        try:
            got = call(ns, data["meta"], case["input"])
        except Exception as e:  # show the error per case, like LeetCode's runtime error
            print(f"[ERROR] case {i}: {type(e).__name__}: {e}")
            checked += "output" in case
            continue
        if "output" not in case:
            print(f"[ ?? ] case {i}: got={got}")
            continue
        checked += 1
        ok = got == case["output"]
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] case {i}: expected={case['output']}  got={got}")
    print(f"\n{passed}/{checked} passed")
    return 0 if passed == checked else 1


if __name__ == "__main__":
    raise SystemExit(main())
