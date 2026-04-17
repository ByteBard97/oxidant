import {
  Project, SourceFile, Node, SyntaxKind, ts,
} from "ts-morph";
import * as path from "path";
import * as fs from "fs";

// ── CLI args ────────────────────────────────────────────────────────────────

const args = process.argv.slice(2);
function getArg(flag: string): string {
  const idx = args.indexOf(flag);
  if (idx === -1 || idx + 1 >= args.length) throw new Error(`Missing ${flag}`);
  return args[idx + 1];
}
const tsconfigPath = path.resolve(getArg("--tsconfig"));
const sourceRoot   = path.resolve(getArg("--source-root"));
const outPath      = getArg("--out");

// ── Node ID ─────────────────────────────────────────────────────────────────

function fileSlug(sf: SourceFile): string {
  const rel = path.relative(sourceRoot, sf.getFilePath());
  return rel.replace(/\.tsx?$/, "").replace(/[/\\]/g, "__").replace(/[^a-zA-Z0-9_]/g, "_");
}

function nodeId(...parts: string[]): string {
  return parts.join("__").replace(/[^a-zA-Z0-9_]/g, "_");
}

// ── Cyclomatic complexity ────────────────────────────────────────────────────

function complexity(root: Node): number {
  let n = 1;
  root.forEachDescendant((d) => {
    switch (d.getKind()) {
      case SyntaxKind.IfStatement:
      case SyntaxKind.ConditionalExpression:
      case SyntaxKind.CaseClause:
      case SyntaxKind.WhileStatement:
      case SyntaxKind.ForStatement:
      case SyntaxKind.ForInStatement:
      case SyntaxKind.ForOfStatement:
      case SyntaxKind.CatchClause:
        n++; break;
      case SyntaxKind.BinaryExpression: {
        const op = (d as any).getOperatorToken().getKind();
        if (op === SyntaxKind.AmpersandAmpersandToken ||
            op === SyntaxKind.BarBarToken ||
            op === SyntaxKind.QuestionQuestionToken) n++;
        break;
      }
    }
  });
  return n;
}

// ── Type text ────────────────────────────────────────────────────────────────

function typeStr(n: Node): string {
  try {
    return n.getType().getText(n as any, ts.TypeFormatFlags.NoTruncation);
  } catch { return "unknown"; }
}

// ── Main ─────────────────────────────────────────────────────────────────────

const project = new Project({ tsConfigFilePath: tsconfigPath });
const resultNodes: Record<string, any> = {};
// callee → set of callers
const callerMap = new Map<string, Set<string>>();

// Pass 1: index all declaration names → nodeId
const declIndex = new Map<string, string>(); // "filePath::name" or "filePath::class::method" → nodeId

for (const sf of project.getSourceFiles()) {
  const slug = fileSlug(sf);
  const fp   = sf.getFilePath();

  for (const cls of sf.getClasses()) {
    const name = cls.getName(); if (!name) continue;
    declIndex.set(`${fp}::${name}`, nodeId(slug, name));
    for (const m of cls.getMethods())
      declIndex.set(`${fp}::${name}::${m.getName()}`, nodeId(slug, name, m.getName()));
    if (cls.getConstructors().length)
      declIndex.set(`${fp}::${name}::constructor`, nodeId(slug, name, "constructor"));
  }
  for (const fn of sf.getFunctions()) {
    const name = fn.getName(); if (!name) continue;
    declIndex.set(`${fp}::${name}`, nodeId(slug, name));
  }
  for (const iface of sf.getInterfaces())
    declIndex.set(`${fp}::${iface.getName()}`, nodeId(slug, iface.getName()));
  for (const en of sf.getEnums())
    declIndex.set(`${fp}::${en.getName()}`, nodeId(slug, en.getName()));
}

function resolveDepId(sym: any): string | null {
  if (!sym) return null;
  const symName = sym.getName();
  for (const decl of (sym.getDeclarations?.() ?? [])) {
    const fp = decl.getSourceFile().getFilePath();

    // For class methods/constructors the declIndex key is filePath::ClassName::methodName.
    // Try the class-aware key first so this.foo() and ClassName.foo() resolve correctly.
    try {
      const parent = decl.getParent?.();
      if (parent) {
        const parentName: string | undefined = (parent as any).getName?.();
        if (parentName) {
          const methodKey = `${fp}::${parentName}::${symName}`;
          if (declIndex.has(methodKey)) return declIndex.get(methodKey)!;
        }
      }
    } catch { /* skip */ }

    // Fallback: top-level name (free functions, interfaces, enums, classes)
    const key = `${fp}::${symName}`;
    if (declIndex.has(key)) return declIndex.get(key)!;
  }
  return null;
}

function typeDepsOf(root: Node): string[] {
  const out: string[] = [];
  root.forEachDescendant((d) => {
    if (d.getKind() === SyntaxKind.TypeReference) {
      const sym = (d as any).getType().getSymbol();
      const id  = resolveDepId(sym);
      if (id && !out.includes(id)) out.push(id);
    }
  });
  return out;
}

function callDepsOf(root: Node, selfId: string, registerCaller = true): string[] {
  const out: string[] = [];
  root.forEachDescendant((d) => {
    if (d.getKind() !== SyntaxKind.CallExpression) return;
    const sym = (d as any).getExpression().getSymbol?.();
    const id  = resolveDepId(sym);
    if (!id || id === selfId || out.includes(id)) return;
    out.push(id);
    if (registerCaller) {
      if (!callerMap.has(id)) callerMap.set(id, new Set());
      callerMap.get(id)!.add(selfId);
    }
  });
  return out;
}

function baseNode(
  id: string, sf: SourceFile, decl: Node, kind: string, parentClass: string | null = null,
): any {
  return {
    node_id: id,
    source_file: path.relative(sourceRoot, sf.getFilePath()),
    line_start: decl.getStartLineNumber(),
    line_end: decl.getEndLineNumber(),
    source_text: decl.getText(),
    node_kind: kind,
    parameter_types: {},
    return_type: null,
    type_dependencies: [],
    call_dependencies: [],
    callers: [],
    parent_class: parentClass,
    cyclomatic_complexity: 1,
    idioms_needed: [],
    topological_order: null,
    bfs_level: null,
    tier: null,
    tier_reason: null,
    status: "not_started",
    snippet_path: null,
    attempt_count: 0,
    last_error: null,
  };
}

// Pass 2: extract
for (const sf of project.getSourceFiles()) {
  const slug = fileSlug(sf);

  // Classes
  for (const cls of sf.getClasses()) {
    const name = cls.getName(); if (!name) continue;
    const classId = nodeId(slug, name);
    const cn = baseNode(classId, sf, cls, "class");
    cn.type_dependencies = typeDepsOf(cls).filter((id: string) => id !== classId);
    resultNodes[classId] = cn;

    // Constructor
    const ctors = cls.getConstructors();
    if (ctors.length) {
      const ctor   = ctors[0];
      const ctorId = nodeId(slug, name, "constructor");
      const cn2    = baseNode(ctorId, sf, ctor, "constructor", classId);
      for (const p of ctor.getParameters()) cn2.parameter_types[p.getName()] = typeStr(p);
      cn2.return_type        = name;
      cn2.type_dependencies  = typeDepsOf(ctor).filter((id: string) => id !== ctorId);
      cn2.call_dependencies  = callDepsOf(ctor, ctorId);
      cn2.cyclomatic_complexity = complexity(ctor);
      resultNodes[ctorId]    = cn2;
    }

    // Methods
    for (const m of cls.getMethods()) {
      const mId = nodeId(slug, name, m.getName());
      const mn  = baseNode(mId, sf, m, "method", classId);
      for (const p of m.getParameters()) mn.parameter_types[p.getName()] = typeStr(p);
      mn.return_type        = m.getReturnType().getText(m as any, ts.TypeFormatFlags.NoTruncation);
      mn.type_dependencies  = typeDepsOf(m).filter((id: string) => id !== mId);
      mn.call_dependencies  = callDepsOf(m, mId);
      mn.cyclomatic_complexity = complexity(m);
      resultNodes[mId]      = mn;
    }
  }

  // Free functions
  for (const fn of sf.getFunctions()) {
    const name = fn.getName(); if (!name) continue;
    const fnId = nodeId(slug, name);
    const fn2  = baseNode(fnId, sf, fn, "free_function");
    for (const p of fn.getParameters()) fn2.parameter_types[p.getName()] = typeStr(p);
    fn2.return_type        = fn.getReturnType().getText(fn as any, ts.TypeFormatFlags.NoTruncation);
    fn2.type_dependencies  = typeDepsOf(fn).filter((id: string) => id !== fnId);
    fn2.call_dependencies  = callDepsOf(fn, fnId);
    fn2.cyclomatic_complexity = complexity(fn);
    resultNodes[fnId]      = fn2;
  }

  // Interfaces
  for (const iface of sf.getInterfaces()) {
    const id = nodeId(slug, iface.getName());
    const n  = baseNode(id, sf, iface, "interface");
    n.type_dependencies = typeDepsOf(iface).filter((i: string) => i !== id);
    resultNodes[id] = n;
  }

  // Enums
  for (const en of sf.getEnums()) {
    const id = nodeId(slug, en.getName());
    resultNodes[id] = baseNode(id, sf, en, "enum");
  }
}

// Backfill callers
for (const [calleeId, callers] of callerMap.entries()) {
  if (resultNodes[calleeId]) resultNodes[calleeId].callers = Array.from(callers);
}

const manifest = {
  version: "1.0",
  source_repo: sourceRoot,
  generated_at: new Date().toISOString(),
  nodes: resultNodes,
};

fs.writeFileSync(outPath, JSON.stringify(manifest, null, 2));
console.log(`Wrote manifest: ${outPath} (${Object.keys(resultNodes).length} nodes)`);
