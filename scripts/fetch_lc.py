#!/usr/bin/env python3
"""
fetch_lc.py — Fetch a LeetCode problem via the public GraphQL endpoint and
emit a practice file in the right topic subdirectory.

Usage:
    python scripts/fetch_lc.py <slug-or-url> [--force] [--dir <subdir>]

Examples:
    python scripts/fetch_lc.py interleaving-string
    python scripts/fetch_lc.py https://leetcode.com/problems/two-sum/
    python scripts/fetch_lc.py longest-substring-without-repeating-characters --force
    python scripts/fetch_lc.py word-break --dir dynamic_programming

stdlib only.
"""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

LC_GRAPHQL = "https://leetcode.com/graphql"

QUERY = """
query getQuestion($titleSlug: String!) {
  question(titleSlug: $titleSlug) {
    questionId
    questionFrontendId
    title
    titleSlug
    content
    difficulty
    exampleTestcases
    sampleTestCase
    metaData
    topicTags { name slug }
    hints
  }
}
"""

# Tag → project subdirectory. First matching tag wins; checked in priority order.
TAG_TO_DIR = [
    ("Dynamic Programming", "dynamic_programming"),
    ("Backtracking", "backtracking"),
    ("Greedy", "greedy"),
    ("Sliding Window", "sliding_window"),
    ("Two Pointers", "two_pointers"),
    ("Binary Search", "binary_search"),
    ("Tree", "trees"),
    ("Binary Tree", "trees"),
    ("Binary Search Tree", "trees"),
    ("Graph", "graphs"),
    ("Topological Sort", "graphs"),
    ("Union Find", "graphs"),
    ("Depth-First Search", "graphs"),
    ("Breadth-First Search", "graphs"),
    ("Matrix", "graphs"),
    ("Linked List", "linked_lists"),
    ("Stack", "stack_queue"),
    ("Queue", "stack_queue"),
    ("Monotonic Stack", "stack_queue"),
    ("Bit Manipulation", "math_bit"),
    ("Math", "math_bit"),
    ("Hash Table", "hash_map"),
    ("String", "strings"),
    ("Array", "arrays"),
]

# LeetCode metaData type → Python type hint
TYPE_MAP = {
    "integer": "int",
    "integer[]": "List[int]",
    "integer[][]": "List[List[int]]",
    "long": "int",
    "double": "float",
    "boolean": "bool",
    "string": "str",
    "string[]": "List[str]",
    "string[][]": "List[List[str]]",
    "character": "str",
    "character[]": "List[str]",
    "character[][]": "List[List[str]]",
    "ListNode": "Optional[ListNode]",
    "TreeNode": "Optional[TreeNode]",
    "void": "None",
}

NEEDS_LIST_IMPORT = ("List[",)
NEEDS_OPTIONAL_IMPORT = ("Optional[",)


# --------------------------------------------------------------------- HTTP --

def fetch_question(slug: str) -> dict[str, Any]:
    body = json.dumps({
        "query": QUERY,
        "variables": {"titleSlug": slug},
        "operationName": "getQuestion",
    }).encode("utf-8")
    req = urllib.request.Request(
        LC_GRAPHQL,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Referer": f"https://leetcode.com/problems/{slug}/",
            "User-Agent": "fetch_lc/1.0 (+local script)",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as e:
        sys.exit(f"network error talking to LeetCode: {e}")
    if "errors" in payload:
        sys.exit(f"GraphQL errors: {payload['errors']}")
    q = payload.get("data", {}).get("question")
    if not q:
        sys.exit(f"no question returned for slug {slug!r}. Check the slug.")
    if q.get("content") is None:
        sys.exit(
            f"slug {slug!r} appears to be a LeetCode Premium problem — its "
            f"`content` is null on the public GraphQL endpoint. Hand-write the "
            f"stub or fetch via an authenticated session."
        )
    return q


# ---------------------------------------------------------------- HTML utils --

_PRE_RE = re.compile(r"<pre>(.*?)</pre>", re.DOTALL | re.IGNORECASE)
_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_RE = re.compile(r"\n{3,}")


def strip_html(text: str) -> str:
    """Crude but adequate HTML → plain text for LC content."""
    # <sup>X</sup> → ^X (constraints like 10^4)
    text = re.sub(r"<sup>(.*?)</sup>", r"^\1", text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<sub>(.*?)</sub>", r"_\1", text, flags=re.IGNORECASE | re.DOTALL)
    # Preserve list items as "- "
    text = re.sub(r"<li>\s*", "- ", text, flags=re.IGNORECASE)
    text = re.sub(r"</li>", "\n", text, flags=re.IGNORECASE)
    # Paragraph + line breaks
    text = re.sub(r"</p>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    # Drop the remaining tags
    text = _TAG_RE.sub("", text)
    text = html.unescape(text)
    # Tidy whitespace: strip <ul>/<li> indent, collapse runs.
    text = text.replace("\u00a0", " ")
    cleaned = []
    for line in text.splitlines():
        line = line.lstrip("\t ")
        line = re.sub(r"[ \t]{2,}", " ", line)
        cleaned.append(line.rstrip())
    text = "\n".join(cleaned)
    text = _BLANK_RE.sub("\n\n", text).strip()
    return text


def extract_examples(content_html: str) -> list[dict[str, str]]:
    """
    Pull (input, output, explanation?) from each <pre> block in the content.
    Returns list of dicts with keys input/output/explanation (strings).
    """
    examples: list[dict[str, str]] = []
    for block in _PRE_RE.findall(content_html):
        clean = strip_html(block)
        ex: dict[str, str] = {}
        for label in ("Input", "Output", "Explanation"):
            m = re.search(
                rf"{label}:\s*(.*?)(?=\n\s*(?:Input|Output|Explanation):|\Z)",
                clean, re.DOTALL,
            )
            if m:
                ex[label.lower()] = m.group(1).strip()
        if "input" in ex and "output" in ex:
            examples.append(ex)
    return examples



_BOOL_RE = re.compile(r"\b(true|false|null)\b")
_LITERAL_FIX = {"true": "True", "false": "False", "null": "None"}


def to_py_literal(raw: str) -> str:
    """Translate JSON-ish literals (true/false/null) to Python equivalents."""
    return _BOOL_RE.sub(lambda m: _LITERAL_FIX[m.group(1)], raw)

# --------------------------------------------------------- input arg parser --

# Matches "name = value" where value can be a list, quoted string, number, etc.
# Splits on top-level commas only (depth-tracking — bracket-/quote-aware).

def split_args(arg_str: str) -> list[tuple[str, str]]:
    """Parse 'nums = [2,7,11,15], target = 9' → [('nums','[2,7,11,15]'), ('target','9')]."""
    pairs: list[tuple[str, str]] = []
    depth = 0
    in_str: str | None = None
    buf: list[str] = []
    for ch in arg_str:
        if in_str:
            buf.append(ch)
            if ch == in_str and (len(buf) < 2 or buf[-2] != "\\"):
                in_str = None
            continue
        if ch in ("'", '"'):
            in_str = ch
            buf.append(ch)
            continue
        if ch in "[({":
            depth += 1
            buf.append(ch)
            continue
        if ch in "])}":
            depth -= 1
            buf.append(ch)
            continue
        if ch == "," and depth == 0:
            chunk = "".join(buf).strip()
            if "=" in chunk:
                k, _, v = chunk.partition("=")
                pairs.append((k.strip(), v.strip()))
            buf = []
            continue
        buf.append(ch)
    tail = "".join(buf).strip()
    if "=" in tail:
        k, _, v = tail.partition("=")
        pairs.append((k.strip(), v.strip()))
    return pairs


# ---------------------------------------------------------- topic detection --

def pick_subdir(topic_tags: list[dict[str, str]], override: str | None) -> str:
    if override:
        return override
    names = {t["name"] for t in topic_tags}
    for tag, subdir in TAG_TO_DIR:
        if tag in names:
            return subdir
    # Unknown topic → land at repo root so it's noticed
    return "."


# ------------------------------------------------------- filename / typing ---

def snake_title(title: str) -> str:
    out = re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_")
    return out


def py_type(lc_type: str) -> str:
    return TYPE_MAP.get(lc_type, "Any")


@dataclass
class Param:
    name: str
    py: str


@dataclass
class Signature:
    method: str
    params: list[Param]
    ret: str


def parse_meta(meta_json: str) -> Signature:
    m = json.loads(meta_json)
    params = [Param(p["name"], py_type(p["type"])) for p in m.get("params", [])]
    ret_obj = m.get("return", {})
    ret_type = ret_obj.get("type", "void") if isinstance(ret_obj, dict) else "void"
    return Signature(
        method=m.get("name", "solve"),
        params=params,
        ret=py_type(ret_type),
    )


def needed_imports(sig: Signature) -> list[str]:
    blob = sig.ret + "|" + "|".join(p.py for p in sig.params)
    imports: list[str] = []
    if any(s in blob for s in NEEDS_LIST_IMPORT):
        imports.append("from typing import List")
    if any(s in blob for s in NEEDS_OPTIONAL_IMPORT):
        imports.append("from typing import Optional")
    if "Any" in blob:
        imports.append("from typing import Any")
    return sorted(set(imports))


# -------------------------------------------------------- file rendering -----

TEMPLATE = '''"""
LeetCode {qid}: {title}

{description}
"""
{imports_block}

class Solution:
    def {method}(self, {param_sig}) -> {ret}:
        pass


# ---------- Test runner ----------

TEST_CASES = [
    # ({test_header})
{test_rows}
]


def run():
    sol = Solution()
    passed = 0
    failed = 0
    for case in TEST_CASES:
        *args, expected, note = case
        got = sol.{method}(*args)
        ok = got == expected
        status = "PASS" if ok else "FAIL"
        print(f"[{{status}}] expected={{expected}}  got={{got}}  ({{note}})")
        if ok:
            passed += 1
        else:
            failed += 1
    print(f"\\n{{passed}}/{{len(TEST_CASES)}} passed, {{failed}} failed")


if __name__ == "__main__":
    run()
'''


def render_test_row(arg_names: list[str], values: list[str], output: str, note: str) -> str:
    arg_repr = ", ".join(to_py_literal(v) if v else "None" for v in values)
    output_py = to_py_literal(output) if output else "None"
    note_escaped = note.replace('"', '\\"')
    return f'    ({arg_repr}, {output_py}, "{note_escaped}"),'


def render_file(q: dict[str, Any]) -> tuple[str, Signature]:
    sig = parse_meta(q["metaData"])
    description = strip_html(q["content"])
    examples = extract_examples(q["content"])

    arg_names = [p.name for p in sig.params]
    test_rows_lines: list[str] = []
    if examples:
        for idx, ex in enumerate(examples, 1):
            pairs = dict(split_args(ex["input"]))
            values = [pairs.get(name, "None") for name in arg_names]
            output = ex["output"].strip()
            note = f"Example {idx}"
            test_rows_lines.append(render_test_row(arg_names, values, output, note))
    else:
        # No examples parseable — emit one placeholder.
        values = ["None"] * len(arg_names)
        test_rows_lines.append(render_test_row(arg_names, values, "None", "TODO: add cases"))

    test_header = ", ".join(arg_names + ["expected", "note"])

    param_sig = ", ".join(f"{p.name}: {p.py}" for p in sig.params)

    imports = needed_imports(sig)
    imports_block = ("\n".join(imports) + "\n") if imports else ""

    return TEMPLATE.format(
        qid=q.get("questionFrontendId") or q.get("questionId") or "?",
        title=q["title"],
        description=description,
        imports_block=imports_block,
        method=sig.method,
        param_sig=param_sig,
        ret=sig.ret,
        test_header=test_header,
        test_rows="\n".join(test_rows_lines),
    ), sig


# ------------------------------------------------------------ slug parsing ---

def normalize_slug(arg: str) -> str:
    arg = arg.strip()
    m = re.match(r"https?://leetcode\.com/problems/([^/?#]+)", arg)
    if m:
        return m.group(1)
    return arg.rstrip("/")


# ------------------------------------------------------------------- main ----

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("slug", help="LeetCode title slug or full URL")
    ap.add_argument("--force", action="store_true", help="overwrite existing file")
    ap.add_argument("--dir", dest="dir_override", default=None,
                    help="override topic subdir (e.g. dynamic_programming)")
    ap.add_argument("--print", action="store_true",
                    help="print to stdout instead of writing a file")
    args = ap.parse_args()

    slug = normalize_slug(args.slug)
    q = fetch_question(slug)

    rendered, _sig = render_file(q)
    if args.print:
        sys.stdout.write(rendered)
        return 0

    subdir = pick_subdir(q.get("topicTags", []), args.dir_override)
    repo_root = Path(__file__).resolve().parent.parent
    qid = q.get("questionFrontendId") or q.get("questionId") or "0"
    fname = f"{int(qid):03d}_{snake_title(q['title'])}.py"
    out_dir = repo_root / subdir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / fname

    if out_path.exists() and not args.force:
        print(f"file exists: {out_path} (use --force to overwrite)", file=sys.stderr)
        return 1

    out_path.write_text(rendered, encoding="utf-8")
    rel = out_path.relative_to(repo_root)
    print(f"wrote {rel}  [{q.get('difficulty', '?')} · {len(q.get('topicTags', []))} tags]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
