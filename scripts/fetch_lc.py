#!/usr/bin/env python3
"""
fetch_lc.py — Fetch a LeetCode problem via the public GraphQL endpoint and
emit a LeetCode-style practice file in the right topic subdirectory.

The practice file holds only the problem statement and LeetCode's own Python
starter code. Example cases go to cases/<name>.json; run them with run_lc.py.

Usage:
    python scripts/fetch_lc.py <slug-or-url> [--force] [--dir <subdir>]
    python scripts/run_lc.py <practice-file>

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
import re
import sys
import urllib.error
import urllib.request
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
    metaData
    topicTags { name slug }
    codeSnippets { langSlug code }
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

_TAG_RE = re.compile(r"<[^>]+>")
_BLANK_RE = re.compile(r"\n{3,}")
# Design problems print "Output" with no colon and the value on the next line.
_OUTPUT_RE = re.compile(r"^Output:?[ \t]*\n?(.+)$", re.MULTILINE)


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
    text = text.replace(" ", " ")
    cleaned = []
    for line in text.splitlines():
        line = line.lstrip("\t ")
        line = re.sub(r"[ \t]{2,}", " ", line)
        cleaned.append(line.rstrip())
    text = "\n".join(cleaned)
    text = _BLANK_RE.sub("\n\n", text).strip()
    return text


# ------------------------------------------------------------- test cases ---

def build_cases(q: dict[str, Any], description: str) -> list[dict[str, Any]]:
    """
    Inputs come from `exampleTestcases` (one JSON value per line, one line per
    param). Outputs are scraped from the "Output:" lines of the description.
    A case without "output" is still run; its result is printed, not checked.
    """
    n_params = len(json.loads(q["metaData"]).get("params", [])) or 1
    lines = [ln for ln in (q.get("exampleTestcases") or "").splitlines() if ln.strip()]
    inputs = [
        [json.loads(v) for v in lines[i:i + n_params]]
        for i in range(0, len(lines) - n_params + 1, n_params)
    ]
    outputs = _OUTPUT_RE.findall(description)
    if len(outputs) != len(inputs):
        print(f"warning: {len(inputs)} inputs but {len(outputs)} outputs; "
              f"expected values left out", file=sys.stderr)
        outputs = []
    cases: list[dict[str, Any]] = []
    for i, args in enumerate(inputs):
        case: dict[str, Any] = {"input": args}
        if outputs:
            try:
                case["output"] = json.loads(outputs[i].strip())
            except json.JSONDecodeError:
                pass
        cases.append(case)
    return cases


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


def snake_title(title: str) -> str:
    return re.sub(r"[^a-zA-Z0-9]+", "_", title.lower()).strip("_")


# -------------------------------------------------------- file rendering -----

def fill_bodies(code: str) -> str:
    """LeetCode leaves method bodies empty; add `pass` so the file parses."""
    lines = code.rstrip().splitlines()
    out: list[str] = []
    for i, line in enumerate(lines):
        out.append(line)
        if line.lstrip().startswith("def ") and line.rstrip().endswith(":"):
            indent = len(line) - len(line.lstrip())
            nxt = next((ln for ln in lines[i + 1:] if ln.strip()), "")
            if len(nxt) - len(nxt.lstrip()) <= indent:
                out.append(" " * (indent + 4) + "pass")
    return "\n".join(out) + "\n"


def render_file(q: dict[str, Any], description: str) -> str:
    snippet = next(
        (s["code"] for s in q.get("codeSnippets") or [] if s["langSlug"] == "python3"),
        None,
    )
    if snippet is None:
        sys.exit("no python3 starter code for this problem (SQL / shell problem?)")
    qid = q.get("questionFrontendId") or q.get("questionId") or "?"
    doc = f"LeetCode {qid}: {q['title']}\n\n{description}"
    doc = doc.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return f'"""\n{doc}\n"""\n\n{fill_bodies(snippet)}'


# ------------------------------------------------------------ slug parsing ---

def normalize_slug(arg: str) -> str:
    arg = arg.strip()
    m = re.match(r"https?://leetcode\.com/problems/([^/?#]+)", arg)
    if m:
        return m.group(1)
    return arg.rstrip("/")


# ------------------------------------------------------------------- main ----

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("slug", help="LeetCode title slug or full URL")
    ap.add_argument("--force", action="store_true", help="overwrite existing file")
    ap.add_argument("--dir", dest="dir_override", default=None,
                    help="override topic subdir (e.g. dynamic_programming)")
    ap.add_argument("--print", action="store_true",
                    help="print to stdout instead of writing a file")
    args = ap.parse_args()

    slug = normalize_slug(args.slug)
    q = fetch_question(slug)

    description = strip_html(q["content"])
    rendered = render_file(q, description)
    if args.print:
        sys.stdout.write(rendered)
        return 0

    subdir = pick_subdir(q.get("topicTags", []), args.dir_override)
    repo_root = Path(__file__).resolve().parent.parent
    qid = q.get("questionFrontendId") or q.get("questionId") or "0"
    fname = f"{int(qid):03d}_{snake_title(q['title'])}"
    out_path = repo_root / subdir / f"{fname}.py"
    cases_path = repo_root / "cases" / f"{fname}.json"

    if out_path.exists() and not args.force:
        print(f"file exists: {out_path} (use --force to overwrite)", file=sys.stderr)
        return 1

    cases = {
        "slug": q["titleSlug"],
        "meta": json.loads(q["metaData"]),
        "cases": build_cases(q, description),
    }
    for p in (out_path, cases_path):
        p.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")
    cases_path.write_text(json.dumps(cases, indent=2) + "\n", encoding="utf-8")

    rel = out_path.relative_to(repo_root)
    print(f"wrote {rel}  [{q.get('difficulty', '?')} · "
          f"{len(cases['cases'])} cases]")
    print(f"run:  python scripts/run_lc.py {rel}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
