"""Generate a compilable Rust skeleton from conversion_manifest.json.

Every function body is `todo!("OXIDANT: …")`. Must pass `cargo build`.
Phase B replaces the stubs one node at a time.
"""

from __future__ import annotations

import re
import textwrap
from collections import defaultdict
from pathlib import Path

from oxidant.models.manifest import ConversionNode, Manifest, NodeKind

# TypeScript built-ins → Rust
_PRIMITIVES: dict[str, str] = {
    "number": "f64", "string": "String", "boolean": "bool",
    "void": "()", "undefined": "()", "null": "()",
    "never": "!", "any": "serde_json::Value", "unknown": "serde_json::Value",
    "object": "serde_json::Value",
}


# Web/DOM API types that have no Rust equivalent — map to serde_json::Value
_WEB_TYPES: frozenset[str] = frozenset({
    "PointerEvent", "MouseEvent", "KeyboardEvent", "TouchEvent", "Event",
    "EventTarget", "Element", "HTMLElement", "SVGElement", "SVGGElement",
    "SVGPathElement", "SVGCircleElement", "SVGTextElement", "Document",
    "Window", "Worker", "MessageEvent", "ErrorEvent", "ProgressEvent",
    "AbortSignal", "URL", "URLSearchParams", "Blob", "File", "FileList",
    "FormData", "Headers", "Request", "Response", "ReadableStream",
    "WritableStream", "TransformStream", "WebSocket", "XMLHttpRequest",
    "MutationObserver", "IntersectionObserver", "ResizeObserver",
    "CanvasRenderingContext2D", "WebGLRenderingContext",
    "AudioContext", "MediaStream", "RTCPeerConnection",
})


def map_ts_type(
    ts_type: str,
    known_classes: set[str] | None = None,
    class_module: dict[str, str] | None = None,
    known_interfaces: set[str] | None = None,
    interface_module: dict[str, str] | None = None,
    known_enums: set[str] | None = None,
    enum_module: dict[str, str] | None = None,
) -> str:
    """Map a TypeScript type string to a Rust type string.

    Uses fully-qualified `crate::module::Type` paths when module maps are
    provided, so cross-module references compile without `use` imports.
    """
    t = ts_type.strip()
    known = known_classes or set()
    cmod = class_module or {}
    ifaces = known_interfaces or set()
    imod = interface_module or {}
    enums = known_enums or set()
    emod = enum_module or {}

    def recurse(inner: str) -> str:
        return map_ts_type(inner, known, cmod, ifaces, imod, enums, emod)

    if t in _PRIMITIVES:
        return _PRIMITIVES[t]

    # Web/DOM types have no Rust equivalent
    if t in _WEB_TYPES:
        return "serde_json::Value"

    # T[]
    if t.endswith("[]"):
        return f"Vec<{recurse(t[:-2])}>"

    # Array<T>
    if m := re.fullmatch(r"Array<(.+)>", t):
        return f"Vec<{recurse(m.group(1))}>"

    # T | null / T | undefined
    parts = [p.strip() for p in t.split("|")]
    non_null = [p for p in parts if p not in ("null", "undefined")]
    if len(non_null) < len(parts):
        if len(non_null) == 1:
            return f"Option<{recurse(non_null[0])}>"
        return "Option<serde_json::Value>"

    # Map<K, V>
    if m := re.fullmatch(r"Map<(.+?),\s*(.+)>", t):
        return f"std::collections::HashMap<{recurse(m.group(1))}, {recurse(m.group(2))}>"

    # Set<T>
    if m := re.fullmatch(r"Set<(.+)>", t):
        return f"std::collections::HashSet<{recurse(m.group(1))}>"

    # Promise<T> — skeleton placeholder (no actual async runtime)
    if m := re.fullmatch(r"Promise<(.+)>", t):
        inner = recurse(m.group(1))
        return f"std::pin::Pin<Box<dyn std::future::Future<Output = {inner}>>>"

    # Function/callback types: (param: T) => R  →  Box<dyn Fn(T) -> R>
    # Handles: (a: T, b: T) => number, () => void, (x: Shape) => boolean, etc.
    fn_m = re.fullmatch(r"\(([^)]*)\)\s*=>\s*(.+)", t)
    if fn_m:
        raw_params = fn_m.group(1).strip()
        raw_ret = fn_m.group(2).strip()
        if raw_params:
            rust_params = ", ".join(
                recurse(p.split(":")[-1].strip()) if ":" in p else recurse(p.strip())
                for p in raw_params.split(",")
                if p.strip()
            )
        else:
            rust_params = ""
        rust_ret = recurse(raw_ret)
        if rust_ret in ("()", "void"):
            return f"Box<dyn Fn({rust_params})>"
        return f"Box<dyn Fn({rust_params}) -> {rust_ret}>"

    # Short names (≤3 chars) that are generic-param-like (Tr, Tp, PN, etc.)
    # or all-caps short names — skeleton can't declare these as generics
    if len(t) <= 3 and re.fullmatch(r"[A-Z][A-Za-z0-9]*", t):
        return "serde_json::Value"

    # Known interface → trait object Rc<dyn Trait>
    if t in ifaces:
        if t in imod:
            return f"Rc<dyn crate::{imod[t]}::{t}>"
        return f"Rc<dyn {t}>"

    # Known enum or type alias → plain path (no wrapping)
    if t in enums:
        if t in emod:
            return f"crate::{emod[t]}::{t}"
        # Type alias not in any module map — no Rust equivalent in skeleton
        return "serde_json::Value"

    # Known class (confirmed in manifest) → Rc<RefCell<Class>>
    if t in known:
        if t in cmod:
            return f"Rc<RefCell<crate::{cmod[t]}::{t}>>"
        return f"Rc<RefCell<{t}>>"

    # Unknown PascalCase type not in any manifest map → serde_json::Value
    # (could be from unexported files, node_modules, or missing extraction)
    return "serde_json::Value"


def _to_snake(name: str) -> str:
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
    s = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s)
    return s.lower()


_RUST_KEYWORDS: frozenset[str] = frozenset({
    "as", "break", "const", "continue", "crate", "else", "enum", "extern",
    "false", "fn", "for", "if", "impl", "in", "let", "loop", "match", "mod",
    "move", "mut", "pub", "ref", "return", "self", "Self", "static", "struct",
    "super", "trait", "true", "type", "unsafe", "use", "where", "while",
    "async", "await", "dyn", "abstract", "become", "box", "do", "final",
    "macro", "override", "priv", "try", "typeof", "unsized", "virtual", "yield",
})


def _escape_keyword(name: str) -> str:
    """Prefix Rust keywords with r# so they form valid raw identifiers."""
    if name in _RUST_KEYWORDS:
        return f"r#{name}"
    return name


def _module_name(source_file: str) -> str:
    stem = Path(source_file).stem
    raw = re.sub(r"[^a-z0-9_]", "_", _to_snake(stem))
    return _escape_keyword(raw)


def _struct_name(node_id: str) -> str:
    return node_id.split("__")[-1]


def _sanitize_param_name(name: str) -> str:
    """Sanitize a TypeScript parameter name for use as a Rust identifier.

    Handles destructuring patterns ({uniforms}, [a, b]) and Rust keywords.
    """
    stripped = name.strip()
    # Object or array destructuring — replace with a safe name
    if stripped.startswith("{") or stripped.startswith("["):
        # Extract first identifier from the pattern if possible
        inner = re.sub(r"[{}\[\]]", " ", stripped).strip()
        first = re.split(r"[\s,]+", inner)[0] if inner else ""
        safe = re.sub(r"[^a-zA-Z0-9_]", "_", first) if first else "_destructured"
        if not safe or not safe[0].isalpha() and safe[0] != "_":
            safe = f"_{safe}"
        return _escape_keyword(safe) if safe else "_destructured"
    # Strip any remaining non-identifier characters
    safe = re.sub(r"[^a-zA-Z0-9_]", "_", stripped)
    if not safe or (not safe[0].isalpha() and safe[0] != "_"):
        safe = f"_{safe}"
    return _escape_keyword(safe)


# ── Phase A helpers: enum variant + class field extraction ─────────────────────

def _parse_enum_variants(source_text: str) -> list[tuple[str, str | None]]:
    """Extract variant names from a TypeScript enum declaration.

    Returns list of (VariantName, int_discriminant_or_None).
    Only integer literal discriminants are kept; string/computed ones are dropped.
    """
    start = source_text.find("{")
    if start == -1:
        return []
    depth = 0
    end = -1
    for i in range(start, len(source_text)):
        ch = source_text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return []
    body = source_text[start + 1:end]
    variants: list[tuple[str, str | None]] = []
    for line in body.split("\n"):
        line = re.sub(r"//.*", "", line).strip().rstrip(",").strip()
        if not line:
            continue
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?:=\s*(.+))?$", line)
        if not m:
            continue
        name = m.group(1)
        val = (m.group(2) or "").strip()
        discrim = val if val and re.fullmatch(r"-?\d+", val) else None
        variants.append((name, discrim))
    return variants


# Field name fragments that strongly imply f64
_NUMERIC_NAME_FRAGMENTS: frozenset[str] = frozenset({
    "width", "height", "size", "length", "count", "index", "offset",
    "distance", "padding", "margin", "radius", "angle", "weight",
    "x", "y", "z", "dx", "dy", "scale", "ratio", "factor", "threshold",
    "min", "max", "slack", "cost", "priority", "depth", "level", "id",
})

# Field name fragments that strongly imply bool
_BOOL_NAME_FRAGMENTS: frozenset[str] = frozenset({
    "is_", "has_", "can_", "should_", "enabled", "visible", "active",
    "open", "closed", "reversed", "dirty", "ready", "initialized",
})


def _infer_rust_type_from_name(field_name: str) -> str:
    """Heuristic: infer a plausible Rust type from a field name alone.

    Used as last resort when there is no type annotation and no default value.
    Prefers concrete types over serde_json::Value for common patterns.
    """
    snake = _to_snake(field_name).lower()
    # Bool: name starts with is/has/can/should or ends with known bool suffix
    for frag in _BOOL_NAME_FRAGMENTS:
        if snake.startswith(frag) or snake.endswith(frag.rstrip("_")):
            return "bool"
    # Numeric: name contains a known numeric fragment as a whole word
    parts = set(re.split(r"_+", snake))
    if parts & _NUMERIC_NAME_FRAGMENTS:
        return "f64"
    return "serde_json::Value"


def _infer_rust_type_from_default(default: str) -> str:
    """Infer a Rust type from a TypeScript default-value expression."""
    d = default.strip()
    if d in ("true", "false"):
        return "bool"
    if re.fullmatch(r"-?\d+\.\d+([eE][+-]?\d+)?", d):
        return "f64"
    if re.fullmatch(r"-?\d+", d):
        return "f64"
    if d.startswith(('"', "'")):
        return "String"
    if d.startswith("["):
        return "Vec<serde_json::Value>"
    if "new Map" in d:
        return "std::collections::HashMap<serde_json::Value, serde_json::Value>"
    if "new Set" in d:
        return "std::collections::HashSet<serde_json::Value>"
    return "serde_json::Value"


def _parse_static_literal(default: str) -> str | None:
    """Return a Rust literal string for simple numeric/bool defaults, else None."""
    d = default.strip().rstrip(";")
    if d in ("true", "false"):
        return d
    if re.fullmatch(r"-?\d+", d):
        return d
    if re.fullmatch(r"-?\d+\.\d+([eE][+-]?\d+)?", d):
        return d
    return None


def _extract_class_top_level_lines(source_text: str) -> list[str]:
    """Return non-empty lines at brace-depth 1 (the class body level).

    Lines inside method/getter/setter bodies (depth ≥ 2) are skipped entirely.
    When '{' takes us from depth 1 → 2 the partial line is flushed first so
    method signatures (e.g. ``constructor(x: T) {``) still appear in the output.
    """
    start = source_text.find("{")
    if start == -1:
        return []
    result: list[str] = []
    depth = 0
    current: list[str] = []
    in_string = False
    string_char = ""
    in_line_comment = False
    i = start
    n = len(source_text)
    while i < n:
        ch = source_text[i]
        if ch == "\n":
            in_line_comment = False
            if depth == 1:
                line = "".join(current).strip()
                if line:
                    result.append(line)
                current = []
            i += 1
            continue
        if in_line_comment:
            i += 1
            continue
        if in_string:
            if ch == string_char and (i == 0 or source_text[i - 1] != "\\"):
                in_string = False
            if depth == 1:
                current.append(ch)
            i += 1
            continue
        # Block comment /*...*/
        if ch == "/" and i + 1 < n and source_text[i + 1] == "*":
            j = source_text.find("*/", i + 2)
            i = (j + 2) if j != -1 else n
            continue
        # Line comment //
        if ch == "/" and i + 1 < n and source_text[i + 1] == "/":
            in_line_comment = True
            i += 2
            continue
        if ch in ('"', "'", "`"):
            in_string = True
            string_char = ch
            if depth == 1:
                current.append(ch)
            i += 1
            continue
        if ch == "{":
            depth += 1
            if depth == 2:
                # Flush method signature before entering body
                line = "".join(current).strip()
                if line:
                    result.append(line)
                current = []
        elif ch == "}":
            depth -= 1
            if depth == 0:
                break
        else:
            if depth == 1:
                current.append(ch)
        i += 1
    return result


def _find_assignment_eq(s: str) -> int | None:
    """Return index of '=' that represents a default-value assignment in s.

    Skips '=' inside brackets/parens and the '=>' arrow token.
    """
    depth = 0
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in ("(", "<", "[", "{"):
            depth += 1
        elif ch in (")", ">", "]", "}"):
            if depth > 0:
                depth -= 1
        elif ch == "=" and depth == 0:
            nxt = s[i + 1] if i + 1 < len(s) else ""
            if nxt in ("=", ">"):
                i += 2
                continue
            return i
        i += 1
    return None


_FIELD_SKIP_WORDS: frozenset[str] = frozenset({
    "constructor", "get", "set", "extends", "implements",
    "return", "if", "else", "for", "while", "switch", "case", "break",
    "continue", "try", "catch", "finally", "throw",
    "new", "super", "class", "type", "interface",
    "import", "export", "namespace", "module",
    "default", "delete", "typeof", "instanceof", "in", "of",
    "yield", "async", "await",
})


def _parse_field_line(
    line: str,
) -> tuple[str, str | None, bool, str | None, bool] | None:
    """Parse a single TypeScript class top-level line as a field declaration.

    Returns ``(field_name, ts_type, is_optional, default_value, is_static)``
    or ``None`` if the line is not a field declaration.
    """
    line = line.strip()
    # Lines ending with ',' are method parameters, not field declarations
    if line.endswith(","):
        return None
    line = line.rstrip(";")
    if not line or line.startswith(("//", "*", "@", "}")):
        return None

    is_static = False
    mod_re = re.compile(
        r"^(public|private|protected|static|readonly|abstract|override|declare)\s+"
    )
    while True:
        m = mod_re.match(line)
        if not m:
            break
        if m.group(1) == "static":
            is_static = True
        line = line[m.end():]

    line = line.strip()
    if not line:
        return None

    id_m = re.match(r"^([a-zA-Z_$][a-zA-Z0-9_$]*)", line)
    if not id_m:
        return None
    name = id_m.group(1)
    if name in _FIELD_SKIP_WORDS:
        return None

    after = line[id_m.end():].lstrip()
    # Method or generic method — not a field
    if after.startswith(("(", "<")):
        return None

    optional = False
    if after.startswith("?"):
        optional = True
        after = after[1:].lstrip()
    elif after.startswith("!"):
        after = after[1:].lstrip()

    ts_type: str | None = None
    default: str | None = None

    if after.startswith(":"):
        rest = after[1:].strip()
        # Bare 'name:' with nothing after — split method parameter, not a field
        if not rest:
            return None
        eq_idx = _find_assignment_eq(rest)
        if eq_idx is not None:
            ts_type = rest[:eq_idx].strip().rstrip(";").strip() or None
            default = rest[eq_idx + 1:].strip().rstrip(";").strip() or None
        else:
            ts_type = rest.strip().rstrip(";").strip() or None
    elif after.startswith("="):
        default = after[1:].strip().rstrip(";").strip() or None
    elif not after:
        pass  # bare name with no type or default
    else:
        return None

    return (name, ts_type, optional, default, is_static)


def _extract_this_references(source_text: str, skip: frozenset[str] = frozenset()) -> list[str]:
    """Fallback: collect ``this.field`` names from source, excluding method calls."""
    pattern = re.compile(r"\bthis\.([a-zA-Z_$][a-zA-Z0-9_$]*)(?!\s*\()")
    return sorted(
        {m.group(1) for m in pattern.finditer(source_text) if m.group(1) not in skip}
    )


_CLASS_NAME_RE = re.compile(r'\bclass\s+(\w+)')
_EXTENDS_NAME_RE = re.compile(r'\bextends\s+(\w+)')


def _collect_class_fields(
    source_text: str,
    t_fn,
) -> list[tuple[str, str]]:
    """Extract (raw_field_name, rust_type) pairs from a class body.

    Used for emitting named fields in enum variants for hierarchy enums.
    Only instance fields are returned (static consts are skipped).
    """
    top_lines = _extract_class_top_level_lines(source_text)
    fields: list[tuple[str, str]] = []
    seen: set[str] = set()
    for tl in top_lines:
        parsed = _parse_field_line(tl)
        if parsed is None:
            continue
        fname, ftype, fopt, fdefault, fstatic = parsed
        if fstatic:
            continue
        snake = _to_snake(fname)
        if snake in seen:
            continue
        seen.add(snake)
        rust_t = (
            t_fn(ftype) if ftype
            else _infer_rust_type_from_default(fdefault) if fdefault
            else _infer_rust_type_from_name(fname)
        )
        if fopt and not rust_t.startswith("Option<"):
            rust_t = f"Option<{rust_t}>"
        fields.append((fname, rust_t))
    return fields


def generate_skeleton(manifest_path: Path, target_path: Path) -> None:
    """Write a compilable Rust project to target_path."""
    manifest = Manifest.load(manifest_path)
    from oxidant.analysis.hierarchy import build_hierarchy_map, KNOWN_HIERARCHIES
    hierarchy_map = build_hierarchy_map(manifest)
    target_path.mkdir(parents=True, exist_ok=True)

    known_classes = {
        _struct_name(nid)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.CLASS
    }

    # Build lookup tables: name → module for qualified cross-module paths
    class_module: dict[str, str] = {
        _struct_name(nid): _module_name(n.source_file)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.CLASS
    }
    known_interfaces = {
        _struct_name(nid)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.INTERFACE
    }
    interface_module: dict[str, str] = {
        _struct_name(nid): _module_name(n.source_file)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.INTERFACE
    }
    known_enums = {
        _struct_name(nid)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.ENUM
    }
    enum_module: dict[str, str] = {
        _struct_name(nid): _module_name(n.source_file)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.ENUM
    }

    # Type aliases have no direct Rust equivalent in the skeleton —
    # add them to the web_types blocklist effectively by treating them as enums
    # pointing to serde_json::Value (they won't appear in enum_module so the
    # fallback is handled in map_ts_type's unknown-type path below)
    known_type_aliases = {
        _struct_name(nid)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.TYPE_ALIAS
    }
    # Merge type aliases into the enums set so they get a defined mapping
    known_enums = known_enums | known_type_aliases

    # Build redirect table for enum hierarchy children.
    # When a class is now a variant inside a parent enum, any type reference to
    # that child name must resolve to the parent enum type instead (since the
    # child struct no longer exists as a standalone type).
    # Sub-enum bases (e.g. VertexEvent is a child of SweepEvent but also an enum)
    # redirect to THEMSELVES (their own enum type still exists).
    _enum_child_redirect: dict[str, str] = {}
    for _enum_base, _kind in KNOWN_HIERARCHIES.items():
        if _kind != "enum":
            continue
        _base_info = hierarchy_map.by_name.get(_enum_base)
        if not _base_info:
            continue
        _base_mod = _module_name(_base_info.source_file)
        for _child_name in hierarchy_map.children_of(_enum_base):
            if KNOWN_HIERARCHIES.get(_child_name) == "enum":
                # Child is itself an enum hierarchy base — redirect to its own type.
                _child_info = hierarchy_map.by_name.get(_child_name)
                if _child_info:
                    _cm = _module_name(_child_info.source_file)
                    _enum_child_redirect[_child_name] = f"crate::{_cm}::{_child_name}"
            else:
                # Leaf variant — redirect to the parent enum.
                _enum_child_redirect[_child_name] = (
                    f"crate::{_base_mod}::{_enum_base}"
                )
        # Also redirect grandchildren (leaf children of sub-enum bases like BasicVertexEvent)
        for _child_name in hierarchy_map.children_of(_enum_base):
            if KNOWN_HIERARCHIES.get(_child_name) != "enum":
                continue
            _child_info = hierarchy_map.by_name.get(_child_name)
            if not _child_info:
                continue
            _c_mod = _module_name(_child_info.source_file)
            for _grandchild in hierarchy_map.children_of(_child_name):
                if _grandchild not in _enum_child_redirect:
                    _enum_child_redirect[_grandchild] = (
                        f"crate::{_c_mod}::{_child_name}"
                    )

    def t(ts: str | None) -> str:
        if ts and ts.strip() in _enum_child_redirect:
            return _enum_child_redirect[ts.strip()]
        return map_ts_type(
            ts or "void", known_classes, class_module,
            known_interfaces, interface_module, known_enums, enum_module,
        )

    by_module: dict[str, list[ConversionNode]] = defaultdict(list)
    for node in manifest.nodes.values():
        by_module[_module_name(node.source_file)].append(node)

    modules = sorted(by_module)
    src = target_path / "src"
    src.mkdir(exist_ok=True)

    # Cargo.toml
    (target_path / "Cargo.toml").write_text(textwrap.dedent("""\
        [package]
        name = "msagl-rs"
        version = "0.1.0"
        edition = "2021"

        [dependencies]
        slotmap      = "1"
        petgraph     = "0.6"
        nalgebra     = "0.33"
        thiserror    = "2"
        itertools    = "0.13"
        ordered-float = "4"
        serde        = { version = "1", features = ["derive"] }
        serde_json   = "1"
    """))

    # lib.rs
    lib_lines = [
        "#![allow(dead_code, unused_variables, unused_imports, non_snake_case)]",
        "use std::rc::Rc;",
        "use std::cell::RefCell;",
        "",
    ]
    for mod_name in modules:
        lib_lines.append(f"pub mod {mod_name};")
    (src / "lib.rs").write_text("\n".join(lib_lines) + "\n")

    # One .rs file per module
    for mod_name, nodes in by_module.items():
        lines: list[str] = [
            "#![allow(dead_code, unused_variables, unused_imports, non_snake_case)]",
            "use std::rc::Rc;",
            "use std::cell::RefCell;",
            "use std::collections::{HashMap, HashSet};",
            "",
        ]

        # Enums
        seen_enums: set[str] = set()
        for node in nodes:
            if node.node_kind != NodeKind.ENUM:
                continue
            name = _struct_name(node.node_id)
            if name in seen_enums:
                continue
            seen_enums.add(name)
            variants = _parse_enum_variants(node.source_text)
            has_discrim = variants and any(d is not None for _, d in variants)
            derive = "#[derive(Debug, Clone, PartialEq)]"
            if has_discrim:
                lines += [derive, "#[repr(i32)]", f"pub enum {name} {{"]
            else:
                lines += [derive, f"pub enum {name} {{"]
            if variants:
                for vname, discrim in variants:
                    safe_vname = _escape_keyword(vname)
                    lines.append(f"    {safe_vname} = {discrim}," if discrim is not None else f"    {safe_vname},")
            else:
                lines.append("    _Placeholder, // OXIDANT: enum variants not yet translated")
            lines += ["}", ""]

        # Interfaces → traits
        seen_traits: set[str] = set()
        for node in nodes:
            if node.node_kind != NodeKind.INTERFACE:
                continue
            name = _struct_name(node.node_id)
            if name in seen_traits:
                continue
            seen_traits.add(name)
            lines += [
                f"pub trait {name}: std::fmt::Debug {{",
                "    // OXIDANT: trait methods not yet translated",
                "}",
                "",
            ]

        # ── Hierarchy class enums ───────────────────────────────────────────
        # For each known enum-hierarchy BASE class in this module, emit one
        # pub enum with all direct children as variants.  Children that are
        # themselves enum hierarchy bases are wrapped: Variant(SubEnum).
        # This must come before struct emission so the enum type exists in
        # the file before any cross-module references can use it.
        for node in nodes:
            if node.node_kind != NodeKind.CLASS:
                continue
            cls_name_m = _CLASS_NAME_RE.search(node.source_text[:300])
            if not cls_name_m:
                continue
            base_cls = cls_name_m.group(1)
            if KNOWN_HIERARCHIES.get(base_cls) != "enum":
                continue
            children = hierarchy_map.children_of(base_cls)
            if not children:
                continue
            lines += ["#[derive(Debug, Clone)]", f"pub enum {base_cls} {{"]
            for child_name in sorted(children):
                child_node = hierarchy_map.node_for(child_name)
                if child_node is None:
                    lines.append(
                        f"    {child_name}, // OXIDANT: child node not in manifest"
                    )
                    continue
                if KNOWN_HIERARCHIES.get(child_name) == "enum":
                    # Child is itself an enum hierarchy — wrap it as a variant.
                    # Use crate:: path since the sub-enum lives in its own module.
                    child_sf = hierarchy_map.source_file_of(child_name)
                    if child_sf and _module_name(child_sf) != mod_name:
                        child_mod = _module_name(child_sf)
                        lines.append(
                            f"    {child_name}(crate::{child_mod}::{child_name}),"
                        )
                    else:
                        lines.append(f"    {child_name}({child_name}),")
                else:
                    child_fields = _collect_class_fields(child_node.source_text, t)
                    if child_fields:
                        field_str = ", ".join(
                            f"{_escape_keyword(_to_snake(fn))}: {ft}"
                            for fn, ft in child_fields
                        )
                        lines.append(f"    {child_name} {{ {field_str} }},")
                    else:
                        lines.append(f"    {child_name},")
            lines += ["}", ""]

        # Classes → structs + impl
        methods_by_class: dict[str, list[ConversionNode]] = defaultdict(list)
        for node in nodes:
            if node.node_kind == NodeKind.METHOD and node.parent_class:
                methods_by_class[node.parent_class].append(node)

        seen_structs: set[str] = set()
        for node in nodes:
            if node.node_kind != NodeKind.CLASS:
                continue
            sname = _struct_name(node.node_id)
            # Deduplicate struct names within the module
            if sname in seen_structs:
                continue

            # Hierarchy checks: skip classes whose Rust representation is an enum.
            cls_name_m = _CLASS_NAME_RE.search(node.source_text[:300])
            cls_name = cls_name_m.group(1) if cls_name_m else ""
            parent_cls = hierarchy_map.parent_of(cls_name)
            child_info = hierarchy_map.classify_as_child(cls_name)

            # Skip the base class itself if it IS a known enum hierarchy base —
            # its representation is the pub enum emitted in the pre-pass above.
            if KNOWN_HIERARCHIES.get(cls_name) == "enum":
                continue

            # Skip children of enum hierarchies — they fold into the parent enum.
            if child_info and child_info[1] == "enum":
                continue  # variant lives in the parent enum, not its own struct

            seen_structs.add(sname)

            # Extract generic type parameters from the class declaration.
            # TS: class Foo<T, U extends Bar> → Rust: <T, U>
            # We strip constraints (e.g. "extends Bar") to keep it simple.
            generic_params: list[str] = []
            class_decl_m = re.search(
                r"\bclass\s+\w+\s*<([^>]+)>", node.source_text[:500]
            )
            if class_decl_m:
                for param in class_decl_m.group(1).split(","):
                    # Strip constraints: "T extends Foo" → "T"
                    pname = param.strip().split()[0].strip()
                    if pname and re.fullmatch(r"[A-Z][A-Za-z0-9]*", pname):
                        generic_params.append(pname)

            # Build a lookup set for quick "is this a generic param?" checks
            generic_param_set: frozenset[str] = frozenset(generic_params)

            # Parse explicit field declarations from the class body
            top_lines = _extract_class_top_level_lines(node.source_text)
            inst_fields: list[tuple[str, str | None, bool, str | None]] = []
            static_consts: list[tuple[str, str | None, str | None]] = []
            seen_field_names: set[str] = set()
            seen_const_names: set[str] = set()
            for tl in top_lines:
                parsed = _parse_field_line(tl)
                if parsed is None:
                    continue
                fname, ftype, fopt, fdefault, fstatic = parsed
                if fstatic:
                    if fname not in seen_const_names:
                        seen_const_names.add(fname)
                        static_consts.append((fname, ftype, fdefault))
                else:
                    snake = _to_snake(fname)
                    if snake not in seen_field_names:
                        seen_field_names.add(snake)
                        inst_fields.append((fname, ftype, fopt, fdefault))

            # Fallback: mine this.field references when no explicit fields found
            if not inst_fields:
                method_names: frozenset[str] = frozenset(
                    m.node_id.split("__")[-1]
                    for m in methods_by_class.get(node.node_id, [])
                )
                skip_names = method_names | seen_field_names | seen_const_names
                for ref in _extract_this_references(node.source_text, skip=skip_names):
                    inst_fields.append((ref, None, False, None))

            # Build struct/impl type-param suffix: "<T>" or "<T, U>" or ""
            tp_suffix = f"<{', '.join(generic_params)}>" if generic_params else ""
            # Bounds for generic params: require Clone so Vec<T> fields work
            tp_bounds = (
                f"<{', '.join(f'{p}: Clone' for p in generic_params)}>"
                if generic_params else ""
            )

            # Local type resolver: generic params pass through as-is
            def tg(ts: str | None) -> str:
                if ts and ts.strip() in generic_param_set:
                    return ts.strip()
                # Array<T> where T is a generic param → Vec<T>
                if ts:
                    arr_m = re.fullmatch(r"(?:Array|ReadonlyArray)<(.+)>", ts.strip())
                    if arr_m and arr_m.group(1).strip() in generic_param_set:
                        return f"Vec<{arr_m.group(1).strip()}>"
                return t(ts)

            # Emit struct definition
            lines += ["#[derive(Debug, Clone)]", f"pub struct {sname}{tp_suffix} {{"]

            # Struct-composition inheritance: add pub base field for known
            # struct-hierarchy children (e.g. SplineRouter → Algorithm).
            if child_info and child_info[1] == "struct":
                parent_name = child_info[0]
                parent_sf = hierarchy_map.source_file_of(parent_name)
                if parent_sf:
                    parent_mod = _module_name(parent_sf)
                    if parent_mod != mod_name:
                        lines.append(
                            f"    pub base: crate::{parent_mod}::{parent_name},"
                        )
                    else:
                        lines.append(f"    pub base: {parent_name},")
            # External parent not in the corpus — informational comment only
            elif parent_cls and parent_cls not in hierarchy_map.by_name:
                lines.append(
                    f"    // NOTE: extends {parent_cls} (external — not in corpus)"
                )

            if inst_fields:
                for fname, ftype, fopt, fdefault in inst_fields:
                    rust_t = (
                        tg(ftype) if ftype
                        else _infer_rust_type_from_default(fdefault) if fdefault
                        else _infer_rust_type_from_name(fname)
                    )
                    if fopt and not rust_t.startswith("Option<"):
                        rust_t = f"Option<{rust_t}>"
                    lines.append(f"    pub {_escape_keyword(_to_snake(fname))}: {rust_t},")
            else:
                lines.append("    _placeholder: (), // OXIDANT: fields not yet translated")
            lines += ["}", "", f"impl{tp_bounds} {sname}{tp_suffix} {{"]

            # Emit static constants at top of impl block
            for cname, ctype, cdefault in static_consts:
                lit = _parse_static_literal(cdefault) if cdefault else None
                if lit is None:
                    continue
                rust_ct = t(ctype) if ctype else _infer_rust_type_from_default(cdefault or "")
                # Integer literal for an f64 constant must be written as a float
                if rust_ct == "f64" and lit and re.fullmatch(r"-?\d+", lit):
                    lit = f"{lit}.0"
                const_ident = _to_snake(cname).upper()
                lines += [f"    pub const {const_ident}: {rust_ct} = {lit};", ""]

            # Constructor (only emit one)
            ctor_id = f"{node.node_id}__constructor"
            if ctor_id in manifest.nodes:
                ctor = manifest.nodes[ctor_id]
                params = ", ".join(
                    f"{_sanitize_param_name(k)}: {tg(v)}"
                    for k, v in ctor.parameter_types.items()
                )
                lines += [
                    f"    pub fn new({params}) -> Self {{",
                    f'        todo!("OXIDANT: not yet translated — {ctor_id}")',
                    "    }",
                    "",
                ]

            # Methods — deduplicate overloads with numeric suffix
            seen_methods: dict[str, int] = {}
            for m in methods_by_class.get(node.node_id, []):
                raw_name = m.node_id.split("__")[-1]
                if not raw_name:  # trailing __ in node_id → skip
                    continue
                base = _escape_keyword(_to_snake(raw_name))
                count = seen_methods.get(base, 0)
                seen_methods[base] = count + 1
                mname = base if count == 0 else f"{base}_{count}"
                params = ", ".join(
                    f"{_sanitize_param_name(k)}: {tg(v)}"
                    for k, v in m.parameter_types.items()
                )
                ret = tg(m.return_type)
                ret_str = f" -> {ret}" if ret != "()" else ""
                lines += [
                    f"    pub fn {mname}(&mut self, {params}){ret_str} {{",
                    f'        todo!("OXIDANT: not yet translated — {m.node_id}")',
                    "    }",
                    "",
                ]

            lines += ["}", ""]

        # Free functions — deduplicate overloads with numeric suffix
        seen_fns: dict[str, int] = {}
        for node in nodes:
            if node.node_kind != NodeKind.FREE_FUNCTION:
                continue
            base = _escape_keyword(_to_snake(node.node_id.split("__")[-1]))
            count = seen_fns.get(base, 0)
            seen_fns[base] = count + 1
            fname = base if count == 0 else f"{base}_{count}"
            params = ", ".join(
                f"{_sanitize_param_name(k)}: {t(v)}"
                for k, v in node.parameter_types.items()
            )
            ret = t(node.return_type)
            ret_str = f" -> {ret}" if ret != "()" else ""
            lines += [
                f"pub fn {fname}({params}){ret_str} {{",
                f'    todo!("OXIDANT: not yet translated — {node.node_id}")',
                "}",
                "",
            ]

        (src / f"{mod_name}.rs").write_text("\n".join(lines) + "\n")
