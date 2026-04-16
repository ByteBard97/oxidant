import { Project, Node, SyntaxKind } from "ts-morph";
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
