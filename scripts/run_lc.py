#!/usr/bin/env python3
"""
run_lc.py — Run a practice file against its example cases, like LeetCode's
"Run" button. Cases live in cases/<name>.json (written by fetch_lc.py; add
your own there).

Usage:
    python scripts/run_lc.py arrays/001_two_sum.py

The practice file runs with LeetCode's usual names already imported
(List, Optional, ListNode, TreeNode, NestedInteger, collections, heapq, ...),
so it can stay exactly like the LeetCode editor.

stdlib only.
"""
from __future__ import annotations

import inspect
import json
import re
import sys
from collections import deque
from pathlib import Path
from typing import Any, Callable

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


class NestedInteger:
    def __init__(self, value):
        self._int = value if isinstance(value, int) else None
        self._list = None if isinstance(value, int) else [NestedInteger(v) for v in value]

    def isInteger(self) -> bool:
        return self._int is not None

    def getInteger(self):
        return self._int

    def getList(self):
        return self._list


# ---------------------------------------------------- JSON ↔ node helpers ---

def to_list_node(vals: list) -> ListNode | None:
    head = None
    for v in reversed(vals):
        head = ListNode(v, head)
    return head


def list_nodes(head) -> list:
    """All nodes of a list, in order. Stops at a cycle instead of looping forever."""
    out, seen = [], set()
    while head and id(head) not in seen:
        seen.add(id(head))
        out.append(head)
        head = head.next
    return out


def to_tree(vals: list, cls: type = TreeNode):
    """Level-order list with nulls (LeetCode format) → tree."""
    if not vals or vals[0] is None:
        return None
    root = cls(vals[0])
    queue, i = deque([root]), 1
    while queue and i < len(vals):
        node = queue.popleft()
        for side in ("left", "right"):
            if i < len(vals) and vals[i] is not None:
                child = cls(vals[i])
                setattr(node, side, child)
                queue.append(child)
            i += 1
    return root


def from_tree(root) -> list:
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


def find_val(root, val):
    return root if root is None or root.val == val else (
        find_val(root.left, val) or find_val(root.right, val))


def to_arg(lc_type: str, v: Any) -> Any:
    if lc_type == "ListNode":
        return to_list_node(v)
    if lc_type == "TreeNode":
        return to_tree(v)
    if lc_type == "ListNode[]":
        return [to_list_node(x) for x in v]
    if lc_type.startswith("list<NestedInteger>"):
        return [NestedInteger(x) for x in v]
    return v


def from_value(v: Any, lc_type: str = "") -> Any:
    if v is None and lc_type in ("ListNode", "TreeNode"):
        return []  # LeetCode prints an empty list/tree as []
    if isinstance(v, ListNode):
        return [n.val for n in list_nodes(v)]
    if isinstance(v, TreeNode):
        return from_tree(v)
    return v


# --------------------------------------- problems with a custom LeetCode harness --
# Each one gets the loaded namespace, the source and the case input, and returns
# a value comparable with the expected output (JSON value or LeetCode's text).

def node_class(ns: dict, src: str) -> type:
    """`Node` is only defined inside the starter code's docstring; load it from there."""
    if "Node" not in ns:
        # `[^{\n]*:$` skips Java/C++ `class Node {` that problem texts sometimes show.
        m = re.search(r'^class Node\b[^{\n]*:$.*?(?=^""")', src, re.MULTILINE | re.DOTALL)
        if not m:
            raise RuntimeError("no `class Node` definition found in the file")
        exec(m.group(0), ns)
    return ns["Node"]


def solve(ns: dict) -> Callable:
    """The one public method of Solution."""
    sol = ns["Solution"]()
    names = [n for n in vars(ns["Solution"]) if not n.startswith("_")]
    return getattr(sol, names[0])


def h_cycle(ns, src, args):
    vals, pos = args
    head = to_list_node(vals)
    nodes = list_nodes(head)
    if pos >= 0:
        nodes[-1].next = nodes[pos]
    got = solve(ns)(head)
    if isinstance(got, bool):
        return got
    return f"tail connects to node index {nodes.index(got)}" if got else "no cycle"


def h_intersection(ns, src, args):
    val, a, b, skip_a, skip_b = args
    nodes_a = list_nodes(to_list_node(a))
    nodes_b = list_nodes(to_list_node(b))
    if val:
        if skip_b:
            nodes_b[skip_b - 1].next = nodes_a[skip_a]
        else:
            nodes_b = nodes_a[skip_a:]
    got = solve(ns)(nodes_a[0] if nodes_a else None, nodes_b[0] if nodes_b else None)
    return f"Intersected at '{got.val}'" if got else "No intersection"


def h_guess(ns, src, args):
    n, pick = args
    ns["guess"] = lambda num: 0 if num == pick else (-1 if num > pick else 1)
    return solve(ns)(n)


def h_bad_version(ns, src, args):
    n, bad = args
    ns["isBadVersion"] = lambda v: v >= bad
    return solve(ns)(n)


def h_lca(ns, src, args):
    root = to_tree(args[0])
    got = solve(ns)(root, find_val(root, args[1]), find_val(root, args[2]))
    return got.val if got else None


def h_codec(ns, src, args):
    codec = ns["Codec"]
    return from_tree(codec().deserialize(codec().serialize(to_tree(args[0]))))


def h_nested_iterator(ns, src, args):
    it = ns["NestedIterator"]([NestedInteger(x) for x in args[0]])
    out = []
    while it.hasNext():
        out.append(it.next())
    return out


def h_clone_graph(ns, src, args):
    Node = node_class(ns, src)
    nodes = [Node(i + 1) for i in range(len(args[0]))]
    for node, nbrs in zip(nodes, args[0]):
        node.neighbors = [nodes[j - 1] for j in nbrs]
    got = solve(ns)(nodes[0] if nodes else None)
    if got is None:
        return []
    by_val, queue = {got.val: got}, deque([got])
    while queue:
        for nb in queue.popleft().neighbors:
            if nb.val not in by_val:
                by_val[nb.val] = nb
                queue.append(nb)
    if any(n in nodes for n in by_val.values()):
        return "returned the original nodes, not a copy"
    return [[nb.val for nb in by_val[v].neighbors] for v in sorted(by_val)]


def h_random_list(ns, src, args):
    Node = node_class(ns, src)
    nodes = [Node(v) for v, _ in args[0]]
    for i, (_, r) in enumerate(args[0]):
        nodes[i].next = nodes[i + 1] if i + 1 < len(nodes) else None
        nodes[i].random = nodes[r] if r is not None else None
    got = list_nodes(solve(ns)(nodes[0] if nodes else None))
    if any(n in nodes for n in got):
        return "returned the original nodes, not a copy"
    index = {id(n): i for i, n in enumerate(got)}
    return [[n.val, index[id(n.random)] if n.random else None] for n in got]


def h_next_pointers(ns, src, args):
    root = solve(ns)(to_tree(args[0], node_class(ns, src)))
    if root is None:
        return []
    out, level = [], root
    while level:
        node, level = level, None
        while node:
            out.append(str(node.val))
            level = level or node.left or node.right
            node = node.next
        out.append("#")
    return "[" + ",".join(out) + "]"


def h_k_nums(ns, src, args):
    """Answer printed as "k, nums = [first k values,_,_]"."""
    nums = list(args[0])
    k = solve(ns)(nums, *args[1:])
    return f"{k}, nums = [{','.join(map(str, nums[:k] + ['_'] * (len(nums) - k)))}]"


def h_nary(ns, src, args):
    """N-ary input: level order, each child group ends with null."""
    Node = node_class(ns, src)
    vals = args[0]
    if not vals:
        return from_value(solve(ns)(None))
    root = Node(vals[0], [])
    queue, i = deque([root]), 2
    while queue and i <= len(vals):
        parent = queue.popleft()
        while i < len(vals) and vals[i] is not None:
            child = Node(vals[i], [])
            parent.children.append(child)
            queue.append(child)
            i += 1
        i += 1
    return from_value(solve(ns)(root))


HANDLERS: dict[str, Callable] = {
    "linked-list-cycle": h_cycle,
    "linked-list-cycle-ii": h_cycle,
    "intersection-of-two-linked-lists": h_intersection,
    "guess-number-higher-or-lower": h_guess,
    "first-bad-version": h_bad_version,
    "lowest-common-ancestor-of-a-binary-tree": h_lca,
    "lowest-common-ancestor-of-a-binary-search-tree": h_lca,
    "serialize-and-deserialize-binary-tree": h_codec,
    "serialize-and-deserialize-bst": h_codec,
    "flatten-nested-list-iterator": h_nested_iterator,
    "remove-duplicates-from-sorted-array": h_k_nums,
    "remove-duplicates-from-sorted-array-ii": h_k_nums,
    "clone-graph": h_clone_graph,
    "copy-list-with-random-pointer": h_random_list,
    "populating-next-right-pointers-in-each-node": h_next_pointers,
    "populating-next-right-pointers-in-each-node-ii": h_next_pointers,
}


# ------------------------------------------------------------------ running --

def run_design(ns: dict, meta: dict, args: list) -> list:
    """Design problems: args = [op names, op args]; the first op builds the object."""
    ops, op_args = args
    types = {m["name"]: [p["type"] for p in m["params"]] for m in meta.get("methods", [])}
    ctor_types = [p["type"] for p in meta.get("constructor", {}).get("params", [])]
    conv = lambda ts, vs: [to_arg(t, v) for t, v in zip(ts, vs)] + list(vs[len(ts):])
    obj = ns[meta["classname"]](*conv(ctor_types, op_args[0]))
    return [None] + [from_value(getattr(obj, op)(*conv(types.get(op, []), a)))
                     for op, a in zip(ops[1:], op_args[1:])]


def call(ns: dict, meta: dict, slug: str, src: str, args: list) -> Any:
    if slug in HANDLERS:
        return HANDLERS[slug](ns, src, args)
    if "n-ary-tree" in slug:
        return h_nary(ns, src, args)
    if meta.get("systemdesign"):
        return run_design(ns, meta, args)
    params = meta.get("params", [])
    conv = [to_arg(p["type"], a) for p, a in zip(params, args)]
    method = getattr(ns["Solution"](), meta["name"])
    # Unknown custom harness: drop the extra inputs the method does not take.
    conv = conv[:len(inspect.signature(method).parameters)]
    got = method(*conv)
    # "Do not return anything, modify in-place" → LeetCode checks the first arg.
    ret_type = meta.get("return", {}).get("type", "")
    if ret_type == "void":
        return from_value(conv[0], params[0]["type"])
    return from_value(got, ret_type)


def same(got: Any, expected: Any, any_order: bool) -> bool:
    if isinstance(got, float) or isinstance(expected, float):
        try:
            return abs(got - expected) < 1e-5
        except TypeError:
            return False
    if got == expected:
        return True
    if not (any_order and isinstance(got, list) and isinstance(expected, list)):
        return False
    # Order ignored at every level (group anagrams); the distinct count still
    # catches duplicates such as the same permutation returned twice.
    distinct = lambda v: len({repr(x) for x in v})
    return canon(got) == canon(expected) and distinct(got) == distinct(expected)


def canon(v: Any) -> Any:
    return sorted((canon(x) for x in v), key=repr) if isinstance(v, list) else v


def load(path: Path) -> dict:
    src = path.read_text(encoding="utf-8")
    ns: dict[str, Any] = {"ListNode": ListNode, "TreeNode": TreeNode,
                          "NestedInteger": NestedInteger, "__name__": "solution"}
    exec(PRELUDE, ns)
    exec(compile(src, str(path), "exec"), ns)
    ns["__src__"] = src
    return ns


def main() -> int:
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    path = Path(sys.argv[1]).resolve()
    cases_path = REPO_ROOT / "cases" / f"{path.stem}.json"
    if not cases_path.exists():
        sys.exit(f"no cases file at {cases_path}")
    data = json.loads(cases_path.read_text(encoding="utf-8"))
    meta, slug = data["meta"], data.get("slug", "")
    if meta.get("manual") and slug not in HANDLERS and "n-ary-tree" not in slug:
        print("note: LeetCode runs this problem with a custom harness; "
              "results here may not match.\n")

    passed = checked = 0
    for i, case in enumerate(data["cases"], 1):
        # Fresh namespace per case: handlers inject APIs like guess() into it.
        ns = load(path)
        expected = case.get("output", case.get("output_text"))
        has_expected = "output" in case or "output_text" in case
        try:
            got = call(ns, meta, slug, ns["__src__"], case["input"])
        except Exception as e:  # show the error per case, like LeetCode's runtime error
            print(f"[ERROR] case {i}: {type(e).__name__}: {e}")
            checked += has_expected
            continue
        # Text output we cannot reproduce (no handler): show it, don't judge.
        if not has_expected or ("output" not in case and not isinstance(got, str)):
            shown = f"  expected (text)={expected}" if has_expected else ""
            print(f"[ ?? ] case {i}: got={got}{shown}")
            continue
        checked += 1
        ok = same(got, expected, data.get("any_order", False))
        passed += ok
        print(f"[{'PASS' if ok else 'FAIL'}] case {i}: expected={expected}  got={got}")
    print(f"\n{passed}/{checked} passed")
    return 0 if passed == checked else 1


if __name__ == "__main__":
    raise SystemExit(main())
