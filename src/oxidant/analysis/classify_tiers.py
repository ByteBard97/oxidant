"""Classify each manifest node into a translation tier.

Two modes:
- API mode (default): sends each node to Claude Haiku for LLM-based classification.
  Requires ANTHROPIC_API_KEY in the environment.
- Heuristic mode (--heuristic-tiers / classify_manifest_heuristic): uses deterministic
  rules on complexity + idioms. No API calls. Useful for subscription-auth environments.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from oxidant.models.manifest import Manifest, TranslationTier

logger = logging.getLogger(__name__)

# Idioms that indicate non-trivial Rust translation effort
_SONNET_IDIOMS = frozenset({
    "async_await",
    "generator_function",
    "class_inheritance",
    "closure_capture",
})

_OPUS_IDIOMS = frozenset({
    # none currently detected in the msagl-js corpus; reserved for future use
})

_STRUCTURAL_KINDS = frozenset({"enum", "interface", "type_alias"})

def _heuristic_tier(node_kind: str, complexity: int, idioms: list[str]) -> TranslationTier:
    """Return a tier without an API call.

    Rules (conservative — err toward sonnet over haiku):
    - Structural nodes with no logic (enum/interface/type_alias) → haiku
    - Complexity ≤ 2 with no idioms → haiku
    - Any OPUS idiom present → opus
    - Complexity ≥ 10 → opus
    - Otherwise → sonnet
    """
    idiom_set = set(idioms)

    if idiom_set & _OPUS_IDIOMS:
        return TranslationTier.OPUS
    if complexity >= 10:
        return TranslationTier.OPUS

    if node_kind in _STRUCTURAL_KINDS and not idioms:
        return TranslationTier.HAIKU
    if complexity <= 2 and not idioms:
        return TranslationTier.HAIKU

    return TranslationTier.SONNET


def classify_manifest_heuristic(manifest_path: Path) -> None:
    """Classify all untiered nodes using deterministic heuristic rules. No API calls."""
    manifest = Manifest.load(manifest_path)
    changed = 0
    for node_id, node in manifest.nodes.items():
        if node.tier is not None:
            continue
        tier = _heuristic_tier(
            node.node_kind.value,
            node.cyclomatic_complexity,
            node.idioms_needed,
        )
        manifest.nodes[node_id] = node.model_copy(
            update={"tier": tier, "tier_reason": "heuristic"}
        )
        changed += 1
        logger.debug("%-60s → %s (heuristic)", node_id, tier.value)

    manifest.save(manifest_path)
    logger.info("classify_manifest_heuristic: assigned tiers to %d nodes.", changed)


_SYSTEM = """You are a TypeScript-to-Rust translation difficulty classifier.

Tiers:
- haiku: simple getters/setters, basic type definitions, pure arithmetic, no complex idioms
- sonnet: moderate complexity, async conversions, 1-3 complex idioms, non-trivial ownership
- opus: complex algorithms where a wrong simplified version is plausible, cyclic references,
        heavy generics, 4+ complex idioms, deep Rust ownership reasoning required

Respond with ONLY valid JSON on one line: {"tier": "haiku"|"sonnet"|"opus", "reason": "..."}"""

_USER = """\
Node ID: {node_id}
Kind: {node_kind}
Cyclomatic complexity: {complexity}
Idioms: {idioms}

```typescript
{source_text}
```"""


def classify_manifest(manifest_path: Path, model: str) -> None:
    """Classify all untiered nodes in the manifest. Saves once after all nodes are processed.

    Requires ANTHROPIC_API_KEY in the environment. For subscription-auth environments,
    use classify_manifest_heuristic instead.
    """
    import anthropic  # imported here so heuristic path doesn't require it
    manifest = Manifest.load(manifest_path)
    client = anthropic.Anthropic()

    for node_id, node in manifest.nodes.items():
        if node.tier is not None:
            continue

        prompt = _USER.format(
            node_id=node_id,
            node_kind=node.node_kind.value,
            complexity=node.cyclomatic_complexity,
            idioms=", ".join(node.idioms_needed) or "none",
            source_text=node.source_text[:2000],
        )
        try:
            resp = client.messages.create(
                model=model, max_tokens=128, system=_SYSTEM,
                messages=[{"role": "user", "content": prompt}],
            )
            data = json.loads(resp.content[0].text.strip())
            tier   = TranslationTier(data["tier"])
            reason = data.get("reason", "")
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            logger.warning("classify failed for %s (%s) — defaulting to sonnet", node_id, exc)
            tier, reason = TranslationTier.SONNET, f"parse error: {exc}"

        manifest.nodes[node_id] = node.model_copy(update={"tier": tier, "tier_reason": reason})
        logger.info("%-60s → %s", node_id, tier.value)

    manifest.save(manifest_path)
