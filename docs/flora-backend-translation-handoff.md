# Handoff: Using Oxidant (Python→Rust) on the Flora Backend

## Context

flora-studio is a Tauri desktop app with a Rust GIS pipeline that generates site plan
SVGs. The Python reference implementation lives in flora-backend. The Rust port exists
but was written by agents who simplified/rewrote rather than faithfully translating —
producing outputs that don't visually match the Python backend.

Once Oxidant supports Python→Rust, use it to retranslate the remaining Python files
faithfully. This document tells the agent what's already been done, what needs to be
redone, and how to handle the existing Rust codebase.

## Repository locations

```
Python source (reference):  /Users/ceres/Desktop/flora/flora-backend/src/gis/
Rust target (existing):     /Users/ceres/Desktop/flora/flora-studio/src-tauri/src/gis/
```

---

## The core problem with the existing Rust

The existing Rust files are NOT blank — they contain partial implementations. Some
functions are **correct** (fetch logic, coordinate math) and should be left alone.
Others are **wrong** (title block, terrain colormap, CSS styles) and must be replaced.

**Do not run Oxidant blindly on all Python files and overwrite everything.**

The strategy is: use Oxidant only for the specific functions listed below as NEEDS
RETRANSLATION. Mark the correct functions as DONE in the manifest so Oxidant skips them.

---

## Function-by-function status map

### `drawing.py` → embedded in `layers.rs` (STYLES constant)

| Python function | Status | Action |
|---|---|---|
| `generate_svg_styles()` | **WRONG** — Rust has ~7 CSS rules; Python has ~20 including font imports | **RETRANSLATE** |
| `apply_terrain_colormap(normalized)` | **MISSING** — Rust produces greyscale DEM; Python applies a warm/cool color ramp | **TRANSLATE** |
| `hsv_to_rgb(h, s, v)` | **MISSING** — helper for colormap | **TRANSLATE** |
| `_load_balmat_font_base64()` | **SKIP** — font embedding is handled differently | skip |
| `calculate_svg_dimensions()` | **CORRECT** — layout math is right in layout.rs | DONE |
| `geo_to_svg()` / `create_transform_closure()` | **CORRECT** — equivalent in layout.rs `to_svg()` | DONE |

### `title_block.py` → `title_block.rs`

| Python function | Status | Action |
|---|---|---|
| `render_title_block()` | **WRONG** — wrong column widths (33/33/33 vs 40/30/30), no grid, no logo | **RETRANSLATE** |
| `fit_text_to_cell()` | **PARTIALLY CORRECT** — logic is right but uses wrong constants | **RETRANSLATE** |
| `compute_unified_font_size()` | **MISSING** — Rust has no equivalent | **TRANSLATE** |
| `_render_project_info_column()` | **MISSING** — Rust col 1 has wrong content | **TRANSLATE** |
| `_render_technical_details_column()` | **MISSING** — Rust has no 3×2 labeled grid | **TRANSLATE** |
| `_render_branding_column()` | **MISSING** — Rust has no FNP logo or nursery info | **TRANSLATE** |

The FNP logo path data is in:
`/Users/ceres/Desktop/flora/flora-backend/src/gis/assets/logo.py`
It must be ported to a Rust constants file (parallel to `assets.rs` which already
has the north arrow). Create `src-tauri/src/gis/svg/logo.rs`.

### `layers.py` → `layers.rs`

| Python function | Status | Action |
|---|---|---|
| `geometry_to_path()` | **CORRECT** — equivalent in `path.rs` `rings_to_path()` | DONE |
| `_rotate_and_crop_raster()` | **CORRECT** — equivalent in `fetch/imagery.rs` `rotate_and_crop_imagery()` | DONE |
| `render_aerial_imagery()` | **CORRECT** — `layer_raster("aerial-photo", ...)` | DONE |
| `render_terrain_heatmap()` | **WRONG** — Rust renders greyscale DEM; Python uses `apply_terrain_colormap` to produce a colored heatmap | **RETRANSLATE** (depends on colormap being translated first) |
| `render_soils()` | **MOSTLY CORRECT** — IDs and classes slightly off | **RETRANSLATE** |
| `render_buildings()` | **MOSTLY CORRECT** — IDs updated to match layer panel | DONE |
| `render_parcel()` | **CORRECT** | DONE |
| `render_scale_bar()` | **CORRECT** — moved to `layers.rs` `layer_scale_bar()` | DONE |
| `render_north_arrow()` | **CORRECT** — `layer_north_arrow()` with ported path data | DONE |
| `render_contours()` | **MISSING** — contours not yet needed; skip | skip |
| `render_trees()` | **MISSING** — trees layer not needed in current scope; skip | skip |
| `render_roof_lines()` | **MISSING** — not needed; skip | skip |

### `legends.py` → (nothing exists yet)

| Python function | Status | Action |
|---|---|---|
| `render_soil_legend()` | **MISSING** | **TRANSLATE** — emit `<g id="soil-legend">` inside `_Sheet_Info` |
| `render_elevation_legend()` | **MISSING** | **TRANSLATE** — emit `<g id="elevation-legend">` inside `_Sheet_Info` |

---

## How to handle the existing Rust files

### Strategy: targeted replacement, not full overwrite

Oxidant generates complete files from stubs. The existing Rust files are NOT stubs —
they are partial implementations. Use this approach:

**Option A (recommended): Generate into a parallel directory, then diff-merge**

1. Set Oxidant's `target_repo` to a fresh directory:
   `src-tauri/src/gis/svg_oxidant/` (not `svg/`)
2. Run Oxidant on only the Python functions listed as RETRANSLATE/TRANSLATE above
3. Review the generated Rust functions one by one
4. Manually copy each verified function into the existing `svg/` files, replacing
   the wrong implementations

This keeps the correct existing Rust code intact and gives a clean review checkpoint
before anything is overwritten.

**Option B: Pre-populate the manifest with DONE nodes**

Before running Phase B, edit `conversion_manifest.json` to mark already-correct
functions as `status: "done"` with their existing Rust snippet filled in. Oxidant
will skip those and only process the remaining stubs. This requires more careful
manifest setup but produces a cleaner workflow.

---

## Oxidant config for this translation job

Create `oxidant.config.json` in the flora-studio working copy:

```json
{
  "manifest_path": "conversion_manifest.json",
  "source_repo": "/Users/ceres/Desktop/flora/flora-backend/src/gis/pipeline/svg",
  "target_repo": "/Users/ceres/Desktop/flora/flora-studio/src-tauri/src/gis/svg_oxidant",
  "source_language": "python",
  "target_language": "rust",
  "architectural_decisions": {
    "svg_output_strategy": "string_buffer",
    "error_handling": "result_string"
  },
  "crate_inventory": [
    "serde", "serde_json", "base64", "image", "reqwest", "tokio"
  ],
  "model_tiers": {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-6",
    "opus": "claude-opus-4-6"
  },
  "start_tier": "sonnet",
  "max_attempts": {"haiku": 1, "sonnet": 2, "opus": 1},
  "no_escalate": false,
  "parallelism": 1
}
```

Note `start_tier: "sonnet"` — the Python functions are complex enough that haiku
will produce poor translations.

---

## Critical architectural constraint for the translator agent

The Python code uses `svgwrite` objects (DOM-like API). The Rust code uses a
**string buffer pattern** — every render function takes `buf: &mut String` and
calls `buf.push_str(...)`. The translator agent must understand this mapping:

```python
# Python (svgwrite):
g = dwg.g(id='title_block')
g.add(dwg.rect(insert=(x, y), size=(w, h), fill='white'))
parent_grp.add(g)

# Rust (string buffer):
buf.push_str(r#"<g id="title-block">"#);
buf.push_str(&format!(r#"<rect x="{x:.2}" y="{y:.2}" width="{w:.2}" height="{h:.2}" fill="white"/>"#));
buf.push_str("</g>");
```

Include this mapping in the Python idiom dictionary
(`docs/idiom_dictionary_python.md`) under a `svgwrite` section. The translator
agent must apply it consistently across every render function.

---

## Priority order for translation

Run in this order (dependency order — earlier items are used by later ones):

1. `hsv_to_rgb` (helper, no deps)
2. `apply_terrain_colormap` (uses hsv_to_rgb)
3. `generate_svg_styles` / CSS classes (standalone)
4. `fit_text_to_cell` (helper, no deps)
5. `compute_unified_font_size` (uses fit_text_to_cell)
6. `_render_project_info_column` (uses fit_text_to_cell)
7. `_render_technical_details_column` (uses compute_unified_font_size)
8. `_render_branding_column` (uses FNP logo constants)
9. `render_title_block` (calls all of 4-8)
10. `render_terrain_heatmap` (uses apply_terrain_colormap)
11. `render_soils` (standalone)
12. `render_soil_legend` (standalone)
13. `render_elevation_legend` (standalone)

---

## Verification approach

After each function is translated, verify it visually:

```bash
# In flora-studio/src-tauri/:
cargo run --example gen_alligator 2>&1
# Opens /tmp/alligator_axis.svg and /tmp/alligator_rotated.svg

# Compare visually against backend reference:
# /Users/ceres/Downloads/site_plan_500_ALLIGATOR_DR_VENICE_FL__34293 (1).png  (axis-aligned)
# /Users/ceres/Downloads/site_plan_500_ALLIGATOR_DR_VENICE_FL__34293 (2).png  (rotated)
```

The `gen_alligator` example is already set up at
`src-tauri/examples/gen_alligator.rs` and generates both versions of the site plan
for parcel `0450120040` (500 Alligator Dr, Venice FL, Sarasota County).

`cargo check` passing is necessary but not sufficient — the visual comparison is
the real correctness test for rendering functions.
