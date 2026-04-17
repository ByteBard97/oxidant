/**
 * Singleton Shiki highlighter, lazily initialised once and reused.
 * Colours are mapped to the Salvaged Terminal design palette.
 */
import { createHighlighter, type Highlighter } from 'shiki'

// ── Custom theme ─────────────────────────────────────────────────────────────
// Token → palette mapping:
//   #ffb59d  primary   (rust orange)    keywords, storage modifiers
//   #94d2c7  secondary (patina teal)    types, interfaces, classes
//   #e6a96a  tertiary  (burnt amber)    functions, methods
//   #a8cc8c  --        (muted green)    strings (readable on dark)
//   #7dcfb6  --        (aqua)           numbers, booleans, constants
//   #9e8a7e  --        (muted rust)     comments
//   #dcd7d0  --        (warm white)     identifiers / default text
//   #b8a09a  --        (dim rose)       punctuation, operators

const salvatedTerminal = {
  name: 'salvaged-terminal',
  type: 'dark' as const,
  colors: {
    'editor.background':          '#0e0c0a',
    'editor.foreground':          '#dcd7d0',
    'editorLineNumber.foreground': '#3d3330',
  },
  tokenColors: [
    // ── Structural keywords ──────────────────────────────────────────────────
    {
      scope: [
        'keyword', 'keyword.control', 'keyword.other',
        'storage.type', 'storage.modifier',
        'keyword.declaration',
      ],
      settings: { foreground: '#ffb59d' },
    },
    // ── Types, interfaces, enums, traits ────────────────────────────────────
    {
      scope: [
        'entity.name.type', 'entity.name.class', 'entity.name.interface',
        'entity.name.enum', 'entity.name.trait',
        'support.type', 'support.class',
        'meta.type.annotation', 'storage.type.ts',
      ],
      settings: { foreground: '#94d2c7' },
    },
    // ── Functions & methods ──────────────────────────────────────────────────
    {
      scope: [
        'entity.name.function', 'meta.function-call',
        'support.function', 'entity.name.method',
        'variable.function',
      ],
      settings: { foreground: '#e6a96a' },
    },
    // ── Strings ─────────────────────────────────────────────────────────────
    {
      scope: ['string', 'string.quoted', 'string.template'],
      settings: { foreground: '#a8cc8c' },
    },
    // ── Numbers, booleans, constants ────────────────────────────────────────
    {
      scope: [
        'constant.numeric', 'constant.language',
        'constant.other', 'variable.language',
      ],
      settings: { foreground: '#7dcfb6' },
    },
    // ── Comments ────────────────────────────────────────────────────────────
    {
      scope: ['comment', 'punctuation.definition.comment'],
      settings: { foreground: '#6b5a52', fontStyle: 'italic' },
    },
    // ── Operators ───────────────────────────────────────────────────────────
    {
      scope: ['keyword.operator', 'punctuation.separator', 'punctuation.accessor'],
      settings: { foreground: '#b8a09a' },
    },
    // ── Attributes / decorators / macros ────────────────────────────────────
    {
      scope: [
        'meta.attribute', 'entity.name.attribute',
        'keyword.other.attribute', 'meta.decorator',
        'entity.name.function.macro',
      ],
      settings: { foreground: '#c9a97a' },
    },
    // ── Variable names ───────────────────────────────────────────────────────
    {
      scope: ['variable', 'variable.other.readwrite', 'meta.definition.variable'],
      settings: { foreground: '#dcd7d0' },
    },
    // ── Object properties ────────────────────────────────────────────────────
    {
      scope: ['variable.other.property', 'support.variable.property', 'meta.property.object'],
      settings: { foreground: '#c4b8b2' },
    },
  ],
}

// ── Singleton ────────────────────────────────────────────────────────────────
let instance: Highlighter | null = null
let pending: Promise<Highlighter> | null = null

export async function getHighlighter(): Promise<Highlighter> {
  if (instance) return instance
  if (pending)  return pending

  pending = createHighlighter({
    themes: [salvatedTerminal],
    langs:  ['typescript', 'rust'],
  }).then(h => {
    instance = h
    return h
  })

  return pending
}
