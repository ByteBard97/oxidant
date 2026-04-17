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


def generate_skeleton(manifest_path: Path, target_path: Path) -> None:
    """Write a compilable Rust project to target_path."""
    manifest = Manifest.load(manifest_path)
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

    def t(ts: str | None) -> str:
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
            lines += [
                "#[derive(Debug, Clone, PartialEq)]",
                f"pub enum {name} {{",
                "    _Placeholder, // OXIDANT: enum variants not yet translated",
                "}",
                "",
            ]

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
                f"pub trait {name} {{",
                "    // OXIDANT: trait methods not yet translated",
                "}",
                "",
            ]

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
            seen_structs.add(sname)
            lines += [
                "#[derive(Debug, Clone)]",
                f"pub struct {sname} {{",
                "    _placeholder: (), // OXIDANT: fields not yet translated",
                "}",
                "",
                f"impl {sname} {{",
            ]

            # Constructor (only emit one)
            ctor_id = f"{node.node_id}__constructor"
            if ctor_id in manifest.nodes:
                ctor = manifest.nodes[ctor_id]
                params = ", ".join(
                    f"{_sanitize_param_name(k)}: {t(v)}"
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
                    f"{_sanitize_param_name(k)}: {t(v)}"
                    for k, v in m.parameter_types.items()
                )
                ret = t(m.return_type)
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
