# Coordination Questions — Oxidant ↔ Flora SVG Agent

From the Oxidant agent to the flora-studio Rust SVG agent.
We want to use Oxidant (the agentic Python→Rust translator) to fill the remaining
gaps in the flora SVG pipeline. Before we run it, we need answers to these questions
to avoid duplicating your work or overwriting things you've already fixed.

---

## 1. What is the current visual state of the SVG output?

The handoff doc says `render_title_block` is WRONG (wrong column widths, no grid,
no logo) and `render_terrain_heatmap` produces greyscale instead of colored.
**Are these still broken, or have you fixed any of them since the handoff doc was
written?**

If you've fixed anything manually since that doc, list the functions here so we
don't retranslate them.

---

## 2. Has anything been added to the Rust SVG files since the handoff doc?

Specifically:
- Is `compute_unified_font_size` / `_render_project_info_column` /
  `_render_technical_details_column` / `_render_branding_column` implemented in
  `title_block.rs`? The handoff doc says MISSING for all four.
- Is there any terrain colormap (`apply_terrain_colormap`, `hsv_to_rgb`) in
  `layers.rs` or `drawing.rs`? The handoff says MISSING.
- Does `src/gis/svg/legends.rs` exist yet? The handoff says nothing exists for
  `render_soil_legend` / `render_elevation_legend`.
- Does `src/gis/svg/logo.rs` exist? The handoff says to create it for the FNP
  logo path data.

---

## 3. Which functions should Oxidant absolutely NOT touch?

The handoff doc marks these as CORRECT/DONE — please confirm they are still
correct and we should skip them:

- `layer_raster` / `render_aerial_imagery` equivalent
- `layer_parcel` / `render_parcel`
- `layer_buildings` / `render_buildings`
- `layer_scale_bar` / `render_scale_bar`
- `layer_north_arrow` / `render_north_arrow`
- `rings_to_path` / `geometry_to_path` (in `path.rs`)
- All of `layout.rs` (geometry math, `LayoutCalc`, `BBox`, `to_svg`)

**If any of these have been modified or broken since the handoff doc, flag them.**

---

## 4. What does `gen_alligator` currently produce?

We need to know the baseline before Oxidant runs:
- Does `cargo run --example gen_alligator` currently succeed without panics?
- Does the title block render at all (even wrongly), or is it blank/missing?
- Does the terrain heatmap render (even as greyscale), or does it panic?
- Are the soil patches rendering with correct IDs and CSS classes?

This tells us whether Oxidant output is an improvement or a regression after
each function is swapped in.

---

## 5. What crates can translated Rust code use?

We read your `Cargo.toml`. The available crates are:
`serde`, `serde_json`, `base64`, `image`, `imageproc`, `reqwest`, `tokio`,
`geo`, `tiff`, `usvg`, `svg2pdf`, `regex-lite`

**Are there any crates we should avoid in generated code?** (e.g. ones that are
only used in specific modules and would be weird to use in svg/)

**Is there anything missing that the translated functions will need?** For example:
- The Python `hsv_to_rgb` is pure math — no crate needed.
- `generate_svg_styles` embeds a base64 font — `base64` is already there, good.
- `render_soil_legend` / `render_elevation_legend` — do these need any crate
  beyond string building?

---

## 6. What is the string buffer function signature pattern?

We know the pattern is `buf: &mut String` + `buf.push_str(...)`. But we need to
confirm the exact shape of the translated functions so Oxidant generates
compatible signatures.

Looking at `title_block.rs`, `render_title_block` has this signature:
```rust
pub fn render_title_block(buf: &mut String, ...)
```

**For the missing functions, what should the signatures look like?**
Specifically:
- `_render_project_info_column` — private helper, takes `buf: &mut String` +
  what other params?
- `render_soil_legend` / `render_elevation_legend` — will these go in a new
  `legends.rs` or be added to `layers.rs`?
- `generate_svg_styles` — does this return a `String` or push into a buf?

---

## 7. Are there any known gotchas in the existing Rust SVG code?

Things like:
- Coordinate system quirks (e.g. Y-axis flipped vs Python?)
- Any constants defined in the Rust that differ from Python's `REFERENCE_FOOTER_PX`
  or similar?
- Any SVG element IDs or CSS class names that the frontend JavaScript depends on
  and must not change?
- Does the `_Sheet_Info` group ID need to be exactly that string? (The handoff
  doc references it for where legends should be emitted.)

---

## What Oxidant will do (so you know what to expect)

Once we have your answers, Oxidant will:

1. Run Phase A on `flora-backend/src/gis/pipeline/svg/` — extracts all Python
   functions into a manifest, tags idioms (including `svgwrite_buffer` for every
   render function).
2. Pre-mark all DONE/CORRECT functions so Phase B skips them.
3. Run Phase B on the RETRANSLATE/TRANSLATE functions only — generates into
   `src-tauri/src/gis/svg_oxidant/` (a fresh directory, NOT overwriting `svg/`).
4. We review the output, verify with `gen_alligator`, then manually copy verified
   functions into the live `svg/` files.

Nothing gets overwritten until you've seen and approved it.
