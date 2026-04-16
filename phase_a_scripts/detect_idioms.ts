import { Project, Node, SyntaxKind, TypeFlags } from "ts-morph";
import * as fs from "fs";

const args = process.argv.slice(2);
function getArg(flag: string): string {
  const idx = args.indexOf(flag);
  if (idx === -1 || idx + 1 >= args.length) throw new Error(`Missing ${flag}`);
  return args[idx + 1];
}
const manifestPath = getArg("--manifest");
const manifest     = JSON.parse(fs.readFileSync(manifestPath, "utf8"));

const ARRAY_METHODS = new Set(["map","filter","reduce","find","some","every","forEach","flatMap","findIndex"]);

// Primitive TS type names that do NOT warrant arena treatment
const PRIMITIVE_TYPE_NAMES = new Set([
  "string","number","boolean","bigint","symbol","undefined","null","void","never","any","unknown","object",
  "String","Number","Boolean","Array","Object","Function","Promise","Date","RegExp","Error",
]);

type Detector = (n: Node) => boolean;

const IDIOMS: Record<string, Detector> = {
  // Fallback: check full text for ?. since QuestionDotToken is unreliable as a descendant
  optional_chaining: (n) =>
    n.getFullText().includes("?."),

  null_undefined: (n) =>
    n.getDescendantsOfKind(SyntaxKind.NullKeyword).length > 0 ||
    n.getFullText().includes("undefined") ||
    n.getDescendantsOfKind(SyntaxKind.QuestionQuestionToken).length > 0,

  array_method_chain: (n) =>
    n.getDescendantsOfKind(SyntaxKind.CallExpression).some((call) => {
      const expr = call.getExpression();
      return Node.isPropertyAccessExpression(expr) && ARRAY_METHODS.has(expr.getName());
    }),

  closure_capture: (n) =>
    n.getDescendantsOfKind(SyntaxKind.ArrowFunction).length > 0 ||
    n.getDescendantsOfKind(SyntaxKind.FunctionExpression).length > 0,

  map_usage: (n) =>
    n.getFullText().includes("Map<") || n.getFullText().includes("new Map("),

  set_usage: (n) =>
    n.getFullText().includes("Set<") || n.getFullText().includes("new Set("),

  async_await: (n) =>
    n.getDescendantsOfKind(SyntaxKind.AwaitExpression).length > 0 ||
    n.getFullText().includes("async "),

  class_inheritance: (n) =>
    n.getDescendantsOfKind(SyntaxKind.ExtendsKeyword).length > 0,

  number_as_index: (n) => {
    const text = n.getFullText();
    return /\[\s*\w+\s*\]/.test(text) && text.includes("number");
  },

  dynamic_property_access: (n) =>
    n.getDescendantsOfKind(SyntaxKind.ElementAccessExpression).length > 0,

  mutable_shared_state: (n) =>
    n.getDescendantsOfKind(SyntaxKind.BinaryExpression).some((b) => {
      const left = b.getLeft().getFullText().trim();
      return left.includes(".") && b.getOperatorToken().getKind() === SyntaxKind.EqualsToken;
    }),

  generator_function: (n) =>
    n.getDescendantsOfKind(SyntaxKind.YieldExpression).length > 0,

  static_members: (n) =>
    n.getDescendantsOfKind(SyntaxKind.StaticKeyword).length > 0,

  union_type: (n) =>
    n.getDescendantsOfKind(SyntaxKind.UnionType).length > 0,

  // ── New idioms ────────────────────────────────────────────────────────────

  // TypeScript interfaces → Rust traits. Fire on interface declarations and
  // on classes that implement an interface (the impl block needs a trait impl).
  interface_trait: (n) =>
    n.getDescendantsOfKind(SyntaxKind.InterfaceDeclaration).length > 0 ||
    n.getDescendantsOfKind(SyntaxKind.ImplementsKeyword).length > 0,

  // abstract class / abstract method → enum dispatch or Box<dyn Trait>
  abstract_class: (n) =>
    n.getDescendantsOfKind(SyntaxKind.AbstractKeyword).length > 0,

  // TypeScript getter/setter accessors → plain Rust methods with different
  // signatures: `fn field(&self) -> T` and `fn set_field(&mut self, v: T)`.
  getter_setter: (n) =>
    n.getDescendantsOfKind(SyntaxKind.GetAccessor).length > 0 ||
    n.getDescendantsOfKind(SyntaxKind.SetAccessor).length > 0,

  // throw / try-catch → Result<T, E> + the ? operator
  error_handling: (n) =>
    n.getDescendantsOfKind(SyntaxKind.ThrowStatement).length > 0 ||
    n.getDescendantsOfKind(SyntaxKind.TryStatement).length > 0,

  // Classes that hold fields typed as other user-defined class/interface types
  // (i.e., non-primitive object references). These are candidates for arena
  // allocation (Vec<T> + usize indices) rather than Rc<RefCell<T>> in Rust.
  arena_allocation: (n) => {
    const props = n.getDescendantsOfKind(SyntaxKind.PropertyDeclaration);
    return props.some((prop) => {
      const typeNode = prop.getTypeNode();
      if (!typeNode) return false;
      const text = typeNode.getText().trim();
      // Strip Array<...> / T[] wrappers to get the element type name
      const inner = text.replace(/Array<|>|\[\]/g, "").trim();
      // Strip nullability: T | null | undefined
      const base = inner.split("|")[0].trim();
      return base.length > 0 && !PRIMITIVE_TYPE_NAMES.has(base) && /^[A-Z]/.test(base);
    });
  },
};

// Build in-memory project, one source file per node
const project = new Project({ useInMemoryFileSystem: true });

for (const [nodeId, node] of Object.entries(manifest.nodes) as [string, any][]) {
  if (!node.source_text) continue;
  project.createSourceFile(`/${nodeId}.ts`, node.source_text, { overwrite: true });
}

for (const [nodeId, node] of Object.entries(manifest.nodes) as [string, any][]) {
  const sf = project.getSourceFile(`/${nodeId}.ts`);
  if (!sf) continue;

  const idioms: string[] = [];
  for (const [name, detect] of Object.entries(IDIOMS)) {
    try { if (detect(sf)) idioms.push(name); } catch { /* skip */ }
  }
  manifest.nodes[nodeId].idioms_needed = idioms;
}

fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2));
console.log(`Idiom detection complete: ${manifestPath}`);
