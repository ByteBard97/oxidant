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


def map_ts_type(ts_type: str, known_classes: set[str] | None = None) -> str:
    """Map a TypeScript type string to a Rust type string."""
    t = ts_type.strip()
    known = known_classes or set()

    if t in _PRIMITIVES:
        return _PRIMITIVES[t]

    # T[]
    if t.endswith("[]"):
        return f"Vec<{map_ts_type(t[:-2], known)}>"

    # Array<T>
    if m := re.fullmatch(r"Array<(.+)>", t):
        return f"Vec<{map_ts_type(m.group(1), known)}>"

    # T | null / T | undefined
    parts = [p.strip() for p in t.split("|")]
    non_null = [p for p in parts if p not in ("null", "undefined")]
    if len(non_null) < len(parts):
        if len(non_null) == 1:
            return f"Option<{map_ts_type(non_null[0], known)}>"
        return "Option<serde_json::Value>"

    # Map<K, V>
    if m := re.fullmatch(r"Map<(.+?),\s*(.+)>", t):
        return f"std::collections::HashMap<{map_ts_type(m.group(1), known)}, {map_ts_type(m.group(2), known)}>"

    # Set<T>
    if m := re.fullmatch(r"Set<(.+)>", t):
        return f"std::collections::HashSet<{map_ts_type(m.group(1), known)}>"

    # Promise<T>
    if m := re.fullmatch(r"Promise<(.+)>", t):
        return f"impl std::future::Future<Output = {map_ts_type(m.group(1), known)}>"

    # Generic type parameter (single capital or all caps)
    if re.fullmatch(r"[A-Z][A-Z0-9]*", t):
        return t

    # Known or guessed class → Rc<RefCell<Foo>>
    if t in known or re.fullmatch(r"[A-Z][a-zA-Z0-9]*", t):
        return f"Rc<RefCell<{t}>>"

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
    """Escape Rust keywords used as parameter names."""
    return _escape_keyword(name)


def generate_skeleton(manifest_path: Path, target_path: Path) -> None:
    """Write a compilable Rust project to target_path."""
    manifest = Manifest.load(manifest_path)
    target_path.mkdir(parents=True, exist_ok=True)

    known_classes = {
        _struct_name(nid)
        for nid, n in manifest.nodes.items()
        if n.node_kind == NodeKind.CLASS
    }

    def t(ts: str | None) -> str:
        return map_ts_type(ts or "void", known_classes)

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
        for node in nodes:
            if node.node_kind != NodeKind.ENUM:
                continue
            name = _struct_name(node.node_id)
            lines += [
                "#[derive(Debug, Clone, PartialEq)]",
                f"pub enum {name} {{",
                "    _Placeholder, // OXIDANT: enum variants not yet translated",
                "}",
                "",
            ]

        # Interfaces → traits
        for node in nodes:
            if node.node_kind != NodeKind.INTERFACE:
                continue
            name = _struct_name(node.node_id)
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

        for node in nodes:
            if node.node_kind != NodeKind.CLASS:
                continue
            sname = _struct_name(node.node_id)
            lines += [
                "#[derive(Debug, Clone)]",
                f"pub struct {sname} {{",
                "    _placeholder: (), // OXIDANT: fields not yet translated",
                "}",
                "",
                f"impl {sname} {{",
            ]

            # Constructor
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

            # Methods
            for m in methods_by_class.get(node.node_id, []):
                mname = _escape_keyword(_to_snake(m.node_id.split("__")[-1]))
                params = ", ".join(
                    f"{_sanitize_param_name(k)}: {t(v)}"
                    for k, v in m.parameter_types.items()
                )
                ret = t(m.return_type)
                ret_str = f" -> {ret}" if ret != "()" else ""
                lines += [
                    f"    pub fn {mname}(&self, {params}){ret_str} {{",
                    f'        todo!("OXIDANT: not yet translated — {m.node_id}")',
                    "    }",
                    "",
                ]

            lines += ["}", ""]

        # Free functions
        for node in nodes:
            if node.node_kind != NodeKind.FREE_FUNCTION:
                continue
            fname = _escape_keyword(_to_snake(node.node_id.split("__")[-1]))
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
