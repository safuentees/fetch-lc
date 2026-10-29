"""Offline self-checks for fetch_lc / run_lc. Run: python scripts/test_lc.py"""
import json

from fetch_lc import build_cases, fill_bodies, strip_html
from run_lc import from_tree, to_tree

# Empty LeetCode bodies get `pass`; bodies with a docstring are left alone.
code = "class S:\n    def a(self) -> int:\n        \n\n    def b(self) -> None:\n        \"\"\"doc\"\"\"\n"
assert fill_bodies(code).count("pass") == 1, fill_bodies(code)
compile(fill_bodies(code), "<stub>", "exec")

# Trees round-trip through LeetCode's level-order format.
for vals in ([3, 9, 20, None, None, 15, 7], [1, None, 2], []):
    assert from_tree(to_tree(vals)) == vals, vals

# Both example layouts (inline <code> and <pre>) yield the outputs.
q = {
    "metaData": json.dumps({"params": [{"name": "a"}, {"name": "b"}]}),
    "exampleTestcases": "[1,2]\n3\n\"true\"\nnull",
}
content = (
    "<p><strong>Output:</strong> <code>[0,1]</code></p>"
    "<pre><strong>Input:</strong> x\n<strong>Output:</strong> false\n</pre>"
)
assert build_cases(q, strip_html(content)) == [
    {"input": [[1, 2], 3], "output": [0, 1]},
    {"input": ["true", None], "output": False},
]

# Design problems: two lines per case even when metaData has no "params".
design = {"metaData": json.dumps({"classname": "D", "systemdesign": True}),
          "exampleTestcases": '["D","add"]\n[[],[[3,10]]]'}
assert build_cases(design, "Output\n[null, null]") == [
    {"input": [["D", "add"], [[], [[3, 10]]]], "output": [None, None]}]

# "Any order" ignores order at every level but still catches duplicates.
from run_lc import same
assert same([["b"], ["a", "c"]], [["c", "a"], ["b"]], True)
assert not same([[1, 2], [1, 2]], [[1, 2], [2, 1]], True)
assert not same([1, 2], [2, 1], False)
assert same(0.30000001, 0.3, False)
print("ok")
