"""Classify each manifest node into a translation tier using Claude Haiku."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import anthropic

from oxidant.models.manifest import Manifest, TranslationTier

logger = logging.getLogger(__name__)

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
    """Classify all untiered nodes in the manifest. Saves once after all nodes are processed."""
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
