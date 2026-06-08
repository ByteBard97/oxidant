#!/usr/bin/env python3
"""Phase A2 for Python sources: tag idioms on an existing manifest.

Reads conversion_manifest.json, walks each node's source_text with ast,
appends detected idioms to idioms_needed, writes manifest back in place.
"""
from __future__ import annotations

import argparse
import ast
import json
from pathlib import Path


def _detect_idioms(
    source_text: str,
    param_types: dict,
    return_type: str | None = None,
) -> list[str]:
    """Return list of idiom tags for a single node's source text."""
    try:
        tree = ast.parse(source_text)
    except SyntaxError:
        return []

    idioms: set[str] = set()

    for node in ast.walk(tree):
        if isinstance(node, (ast.ListComp, ast.SetComp, ast.DictComp)):
            idioms.add("list_comprehension")
        if isinstance(node, (ast.GeneratorExp, ast.Yield, ast.YieldFrom)):
            idioms.add("generator_function")
        if isinstance(node, ast.JoinedStr):
            idioms.add("format_string")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "isinstance":
                idioms.add("isinstance_check")
        if isinstance(node, ast.Compare):
            for op, comp in zip(node.ops, node.comparators):
                if isinstance(op, (ast.Is, ast.IsNot)) and isinstance(comp, ast.Constant) and comp.value is None:
                    idioms.add("none_check")

    # shapely geometry — any function that imports or calls shapely types/methods
    _SHAPELY_MODULES = {"shapely", "shapely.geometry", "shapely.affinity", "shapely.ops"}
    _SHAPELY_TYPES_SET = {"Polygon", "LineString", "MultiLineString", "Point",
                          "MultiPoint", "MultiPolygon", "GeometryCollection"}
    _SHAPELY_ATTRS = {"intersection", "bounds", "exterior", "interiors", "coords",
                      "geoms", "intersects", "area", "centroid", "minimum_rotated_rectangle",
                      "buffer", "rotate", "unary_union"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name in _SHAPELY_MODULES or alias.name.startswith("shapely.")
                   for alias in node.names):
                idioms.add("shapely_geometry")
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module in _SHAPELY_MODULES
                                or node.module.startswith("shapely.")):
                idioms.add("shapely_geometry")
            if node.module and node.module.startswith("shapely"):
                for alias in node.names:
                    if alias.name in _SHAPELY_TYPES_SET:
                        idioms.add("shapely_geometry")
        elif isinstance(node, ast.Attribute):
            if node.attr in _SHAPELY_ATTRS:
                idioms.add("shapely_geometry")

    # svgwrite DOM-style API — any function that builds SVG via svgwrite objects
    # needs to be rewritten as a string-buffer function in Rust.
    # Detect via: import of svgwrite, or attribute calls like dwg.add/dwg.g/dwg.rect.
    _SVGWRITE_ATTRS = {"add", "g", "rect", "text", "line", "circle", "path", "use",
                       "defs", "symbol", "image", "tostring", "saveas"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(alias.name == "svgwrite" or alias.name.startswith("svgwrite.") for alias in node.names):
                idioms.add("svgwrite_buffer")
        elif isinstance(node, ast.ImportFrom):
            if node.module and (node.module == "svgwrite" or node.module.startswith("svgwrite.")):
                idioms.add("svgwrite_buffer")
        elif isinstance(node, ast.Attribute):
            if node.attr in _SVGWRITE_ATTRS and isinstance(node.value, ast.Name):
                idioms.add("svgwrite_buffer")

    # Check only annotation strings (params + return type), NOT the full source_text
    # body — scanning source_text would produce false positives from comments/docstrings.
    annotation_strs = [t for t in param_types.values() if t] + ([return_type] if return_type else [])
    for t in annotation_strs:
        if "Optional[" in t or "| None" in t or "None |" in t:
            idioms.add("optional_type")

    if return_type and ("tuple[" in return_type or "Tuple[" in return_type):
        idioms.add("multiple_return")

    # DRF @action decorator on any function in this node
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                dec_name = None
                if isinstance(dec, ast.Name):
                    dec_name = dec.id
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Name):
                    dec_name = dec.func.id
                elif isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                    dec_name = dec.func.attr
                if dec_name == "action":
                    idioms.add("drf_action")

    # DRF lifecycle hook methods — detected by reserved method name
    _DRF_HOOK_NAMES = {
        "get_queryset", "perform_create", "perform_update", "perform_destroy",
        "get_object", "get_serializer", "get_serializer_class", "get_permissions",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name in _DRF_HOOK_NAMES:
            idioms.add("drf_hook")

    # DRF SerializerMethodField assignment or validate_* methods
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            if node.name.startswith("validate_") or node.name == "validate":
                idioms.add("drf_method_field")
        if isinstance(node, ast.Assign):
            val = node.value
            if isinstance(val, ast.Call):
                func = val.func
                fname = func.id if isinstance(func, ast.Name) else (
                    func.attr if isinstance(func, ast.Attribute) else None
                )
                if fname == "SerializerMethodField":
                    idioms.add("drf_method_field")

    # Django ORM queryset operations
    _ORM_METHODS = {
        "filter", "exclude", "get", "all", "create", "save", "delete", "update",
        "select_related", "prefetch_related", "annotate", "values", "values_list",
        "order_by", "first", "last", "exists", "count", "bulk_create",
        "get_or_create", "update_or_create", "objects",
    }
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in _ORM_METHODS:
            idioms.add("django_orm_query")

    # Django CHOICES constants — name ending in _CHOICES, or choices= kwarg
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id.endswith("_CHOICES"):
                    idioms.add("django_choices")
        if isinstance(node, ast.keyword) and node.arg == "choices":
            idioms.add("django_choices")

    # @property decorator — model computed properties
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Name) and dec.id == "property":
                    idioms.add("django_property")

    return sorted(idioms)


_FILE_LEVEL_IDIOMS: dict[str, str] = {
    # library → idiom tag propagated to every node in any file that imports it
    "shapely": "shapely_geometry",
    "svgwrite": "svgwrite_buffer",
    "rest_framework": "drf_viewset",
}


def _file_level_idioms(source_file: str) -> set[str]:
    """Return idioms that apply to every node in source_file based on its imports.

    Reads the actual file (not just a single node's source_text) so that
    module-level imports are visible even when processing individual methods.
    """
    p = Path(source_file)
    if not p.exists():
        return set()
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except SyntaxError:
        return set()

    idioms: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = (
                [alias.name for alias in node.names]
                if isinstance(node, ast.Import)
                else ([node.module] if node.module else [])
            )
            for name in names:
                if name is None:
                    continue
                for lib, tag in _FILE_LEVEL_IDIOMS.items():
                    if name == lib or name.startswith(f"{lib}."):
                        idioms.add(tag)
    return idioms


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument(
        "--source-root", default=None,
        help="Root directory of the source repo, used to resolve relative source_file paths.",
    )
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    manifest = json.loads(manifest_path.read_text())
    nodes = manifest.get("nodes", {})

    # Resolve the source root: prefer --source-root, then manifest metadata, then cwd.
    source_root = Path(args.source_root) if args.source_root else None
    if source_root is None:
        source_root = Path(manifest.get("source_repo", "."))

    # Pre-compute file-level idioms so we read each file at most once.
    file_idiom_cache: dict[str, set[str]] = {}

    tagged = 0
    for node in nodes.values():
        existing = set(node.get("idioms_needed", []))

        # Per-function idioms from the node's own source text
        detected = set(_detect_idioms(
            node.get("source_text", ""),
            node.get("parameter_types", {}),
            return_type=node.get("return_type"),
        ))

        # File-level idioms propagated from module imports
        rel_path = node.get("source_file", "")
        if rel_path not in file_idiom_cache:
            abs_path = (source_root / rel_path) if not Path(rel_path).is_absolute() else Path(rel_path)
            file_idiom_cache[rel_path] = _file_level_idioms(str(abs_path))
        detected |= file_idiom_cache[rel_path]

        node["idioms_needed"] = sorted(existing | detected)
        if detected:
            tagged += 1

    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"Tagged idioms on {tagged}/{len(nodes)} nodes → {manifest_path}")


if __name__ == "__main__":
    main()
