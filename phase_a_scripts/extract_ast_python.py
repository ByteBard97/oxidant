#!/usr/bin/env python3
"""Phase A1 for Python sources: extract AST and emit conversion_manifest.json.

Walks all .py files under --source-root, parses with stdlib ast,
emits a manifest with the same schema as extract_ast.ts.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
from datetime import datetime, timezone
from pathlib import Path

# Directory names that are always skipped during tree walk.
_SKIP_DIRS: frozenset[str] = frozenset({
    "__pycache__", "tests", "test", "venv", ".venv", "node_modules",
    "dist", "build", ".git", ".mypy_cache", ".ruff_cache",
})


def _slug(path: str) -> str:
    """Convert a relative file path to a safe identifier prefix.

    Includes the full path (not just stem) to avoid collisions between files
    with the same name in different directories:
      'a/utils.py'   → 'a__utils'
      'svg/utils.py' → 'svg__utils'
    """
    no_ext = Path(path).with_suffix("").as_posix()
    return re.sub(r"[^a-z0-9_]", "_", no_ext.replace("/", "__").lower())


def _annotation_str(node: ast.expr | None) -> str | None:
    if node is None:
        return None
    try:
        return ast.unparse(node)
    except Exception:
        return None


_FLOAT_FUNCS = frozenset({
    "sqrt", "abs", "round", "ceil", "floor", "radians", "degrees",
    "sin", "cos", "tan", "atan2", "asin", "acos", "log", "exp",
    "haversine_distance", "haversine_distance2", "vincenty_distance",
    "distance", "get_bearing",
})
_STR_NAME_FRAGMENTS = frozenset({"str", "text", "kml", "path", "html", "xml", "json", "name"})
_FLOAT_NAME_FRAGMENTS = frozenset({
    "distance", "length", "speed", "angle", "lat", "lon", "alt", "time",
    "hours", "miles", "meters", "feet", "rate", "ratio", "area",
    "width", "height", "bearing", "hue", "factor", "phi", "theta",
    "rho", "lambda", "delta", "alpha", "beta", "gamma", "sigma",
    "radius", "scale", "offset", "weight", "score", "value",
})
_LIST_NAME_FRAGMENTS = frozenset({"mtx", "matrix", "array", "coords", "points", "geoms", "nodes"})
# Short single-letter variable names commonly used for coordinates/math
_FLOAT_SINGLE_LETTERS = frozenset({"x", "y", "z", "s", "t", "r", "h", "a", "b", "c", "n"})


def _classify_expr(node: ast.expr) -> str:
    """Return a Python type name for an expression node."""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool):
            return "bool"
        if isinstance(node.value, int):
            return "int"
        if isinstance(node.value, float):
            return "float"
        if isinstance(node.value, str):
            return "str"
        return "Any"
    if isinstance(node, (ast.List, ast.ListComp)):
        return "list"
    if isinstance(node, (ast.Dict, ast.DictComp)):
        return "dict"
    if isinstance(node, ast.JoinedStr):
        return "str"
    if isinstance(node, (ast.Compare, ast.BoolOp)):
        return "bool"
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return "bool"
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                  ast.Mod, ast.Pow, ast.FloorDiv)):
            # If operands look numeric, the result is float
            lo = _classify_expr(node.left)
            ro = _classify_expr(node.right)
            if lo in ("float", "int") or ro in ("float", "int"):
                return "float"
        return "Any"
    if isinstance(node, ast.Call):
        fname = None
        if isinstance(node.func, ast.Name):
            fname = node.func.id
        elif isinstance(node.func, ast.Attribute):
            fname = node.func.attr
        if fname:
            if fname in _FLOAT_FUNCS:
                return "float"
            if fname in ("format", "join", "replace", "strip", "lower", "upper"):
                return "str"
            if fname in ("int",):
                return "int"
            if fname in ("list",):
                return "list"
            if any(frag in fname.lower() for frag in _FLOAT_NAME_FRAGMENTS):
                return "float"
        return "Any"
    if isinstance(node, ast.Name):
        n = node.id.lower()
        if any(frag in n for frag in _LIST_NAME_FRAGMENTS):
            return "list"
        if any(frag in n for frag in _STR_NAME_FRAGMENTS):
            return "str"
        if any(frag in n for frag in _FLOAT_NAME_FRAGMENTS):
            return "float"
        if node.id in _FLOAT_SINGLE_LETTERS:
            return "float"
        return "Any"
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, (ast.Add, ast.Sub, ast.Mult, ast.Div,
                                  ast.Mod, ast.Pow, ast.FloorDiv)):
            lo = _classify_expr(node.left)
            ro = _classify_expr(node.right)
            if "float" in (lo, ro) or "int" in (lo, ro):
                return "float"
            # Both Any — could still be numeric (e.g. radius_earth * c)
            if isinstance(node.op, (ast.Mult, ast.Div, ast.Sub)):
                return "float"
        return "Any"
    return "Any"


def _infer_return_type(func: ast.FunctionDef | ast.AsyncFunctionDef) -> str | None:
    """Infer a Python type hint string from return statements when no annotation exists.

    Scans return statements in the function body (not nested functions).
    Returns a Python type string compatible with map_python_type(), or None.
    """
    return_values: list[ast.expr] = []
    for node in ast.walk(func):
        if node is not func and isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if isinstance(node, ast.Return) and node.value is not None:
            return_values.append(node.value)

    if not return_values:
        return None

    inferred: set[str] = set()
    for rv in return_values:
        if isinstance(rv, ast.Tuple):
            elems = [_classify_expr(e) for e in rv.elts]
            inferred.add(f"tuple[{', '.join(elems)}]" if elems else "tuple")
        else:
            inferred.add(_classify_expr(rv))

    inferred.discard("Any")
    if not inferred:
        return "Any"
    if len(inferred) == 1:
        return inferred.pop()
    return "Any"


def _cyclomatic_complexity(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    count = 1
    for node in ast.walk(func_node):
        if isinstance(node, (ast.If, ast.For, ast.While, ast.With,
                              ast.ExceptHandler, ast.AsyncFor, ast.AsyncWith)):
            count += 1
        elif isinstance(node, ast.BoolOp):
            count += len(node.values) - 1
        elif isinstance(node, ast.Match):
            count += len(node.cases)
    return count


def _collect_calls(func_node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    names: list[str] = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                names.append(node.func.id)
            elif isinstance(node.func, ast.Attribute):
                names.append(node.func.attr)
    return list(dict.fromkeys(names))


def _extract_file(py_path: Path, source_root: Path) -> list[dict]:
    try:
        source_text = py_path.read_text(encoding="utf-8")
        tree = ast.parse(source_text, filename=str(py_path))
    except SyntaxError:
        return []

    rel_path = str(py_path.relative_to(source_root))
    file_slug = _slug(rel_path)
    lines = source_text.splitlines()
    nodes: list[dict] = []

    def _source_segment(node: ast.AST) -> str:
        # Use the first decorator's line when present so the translating agent
        # sees the full decorated signature (e.g. @property, @classmethod).
        dlist = getattr(node, "decorator_list", [])
        start_line = dlist[0].lineno if dlist else getattr(node, "lineno", 1)
        start = start_line - 1
        end = getattr(node, "end_lineno", start + 1)
        return "\n".join(lines[start:end])

    def _make_node(node_id, node_kind, ast_node, param_types, return_type,
                   parent_class, complexity, call_deps) -> dict:
        return {
            "node_id": node_id,
            "source_file": rel_path,
            "line_start": getattr(ast_node, "lineno", 1),
            "line_end": getattr(ast_node, "end_lineno", getattr(ast_node, "lineno", 1)),
            "source_text": _source_segment(ast_node),
            "node_kind": node_kind,
            "parameter_types": {k: v or "Any" for k, v in param_types.items()},
            "return_type": return_type,
            "type_dependencies": [],
            "call_dependencies": call_deps,
            "callers": [],
            "parent_class": parent_class,
            "cyclomatic_complexity": complexity,
            "idioms_needed": [],
        }

    def _params(func: ast.FunctionDef | ast.AsyncFunctionDef) -> dict[str, str | None]:
        params: dict[str, str | None] = {}
        _skip = {"self", "cls"}
        # Positional-only args (def f(a, b, /, c))
        for arg in func.args.posonlyargs:
            if arg.arg not in _skip:
                params[arg.arg] = _annotation_str(arg.annotation)
        # Regular args
        for arg in func.args.args:
            if arg.arg not in _skip:
                params[arg.arg] = _annotation_str(arg.annotation)
        # Keyword-only args (def f(*, d: int))
        for arg in func.args.kwonlyargs:
            if arg.arg not in _skip:
                params[arg.arg] = _annotation_str(arg.annotation)
        if func.args.vararg:
            params[f"*{func.args.vararg.arg}"] = _annotation_str(func.args.vararg.annotation)
        if func.args.kwarg:
            params[f"**{func.args.kwarg.arg}"] = _annotation_str(func.args.kwarg.annotation)
        return params

    for top_node in ast.iter_child_nodes(tree):
        if isinstance(top_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            nid = f"{file_slug}__{top_node.name}"
            nodes.append(_make_node(
                node_id=nid, node_kind="free_function", ast_node=top_node,
                param_types=_params(top_node),
                return_type=_annotation_str(top_node.returns) or _infer_return_type(top_node),
                parent_class=None,
                complexity=_cyclomatic_complexity(top_node),
                call_deps=_collect_calls(top_node),
            ))

        elif isinstance(top_node, ast.ClassDef):
            class_nid = f"{file_slug}__{top_node.name}"
            nodes.append(_make_node(
                node_id=class_nid, node_kind="class", ast_node=top_node,
                param_types={}, return_type=None, parent_class=None,
                complexity=1, call_deps=[],
            ))
            for method in ast.iter_child_nodes(top_node):
                if not isinstance(method, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if method.name == "__init__":
                    kind = "constructor"
                else:
                    decorators = [ast.unparse(d) for d in method.decorator_list]
                    if "property" in decorators:
                        kind = "getter"
                    elif any(d.endswith(".setter") for d in decorators):
                        kind = "setter"
                    else:
                        kind = "method"
                nodes.append(_make_node(
                    node_id=f"{class_nid}__{method.name}",
                    node_kind=kind, ast_node=method,
                    param_types=_params(method),
                    return_type=_annotation_str(method.returns) or _infer_return_type(method),
                    parent_class=class_nid,
                    complexity=_cyclomatic_complexity(method),
                    call_deps=_collect_calls(method),
                ))

    return nodes


def _walk_python_files(source_root: Path, include_files: list[str] | None = None):
    """Yield .py files under source_root, skipping _SKIP_DIRS.

    If include_files is given, only files whose stem matches one of the listed
    names (with or without .py extension) are yielded.
    """
    allowed: set[str] | None = None
    if include_files:
        allowed = {Path(f).stem for f in include_files}

    for py_file in sorted(source_root.rglob("*.py")):
        parts = py_file.relative_to(source_root).parts[:-1]  # exclude filename
        if any(part in _SKIP_DIRS or part.startswith(".") for part in parts):
            continue
        if allowed is not None and py_file.stem not in allowed:
            continue
        yield py_file


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument(
        "--include-files",
        default=None,
        help="Comma-separated list of .py filenames (or stems) to include. "
             "If omitted, all .py files under source-root are extracted.",
    )
    args = parser.parse_args()

    source_root = Path(args.source_root).resolve()
    out_path = Path(args.out)
    include_files = (
        [f.strip() for f in args.include_files.split(",") if f.strip()]
        if args.include_files
        else None
    )

    all_nodes: dict[str, dict] = {}
    for py_file in _walk_python_files(source_root, include_files=include_files):
        for node in _extract_file(py_file, source_root):
            all_nodes[node["node_id"]] = node

    # Resolve call_dependencies to actual node_ids.
    # Only resolve unambiguous names (exactly one node with that bare name).
    # Same-named functions across different files are left unresolved rather
    # than silently misdirected to whichever node happened to be inserted last.
    from collections import defaultdict
    name_to_nids: dict[str, list[str]] = defaultdict(list)
    for nid in all_nodes:
        name_to_nids[nid.split("__")[-1]].append(nid)
    known_names: dict[str, str] = {
        name: nids[0]
        for name, nids in name_to_nids.items()
        if len(nids) == 1
    }
    for node in all_nodes.values():
        node["call_dependencies"] = [
            known_names[call]
            for call in node["call_dependencies"]
            if call in known_names and known_names[call] != node["node_id"]
        ]

    out_path.write_text(json.dumps({
        "version": "1.0",
        "source_language": "python",
        "source_repo": str(source_root),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "nodes": all_nodes,
    }, indent=2))
    print(f"Extracted {len(all_nodes)} nodes → {out_path}")


if __name__ == "__main__":
    main()
