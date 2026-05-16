# Merge Handoff — Oxidant → Flora SVG Agent

All 14 functions have been translated, reviewed by Kimi, bugs fixed, and
`cargo check` passes clean in `svg_oxidant/`. Ready for diff-merge into the
live `svg/` files.

**Source:** `/Users/ceres/Desktop/flora/flora-studio/src-tauri/src/gis/svg_oxidant/src/`
**Target:** `/Users/ceres/Desktop/flora/flora-studio/src-tauri/src/gis/svg/`

---

## What was translated and reviewed

| File | Functions | Status |
|---|---|---|
| `drawing.rs` | `hsv_to_rgb`, `apply_terrain_colormap`, `generate_svg_styles` | ✅ all reviewed, PASS |
| `layers.rs` | `render_soils`, `render_terrain_heatmap` | ✅ reviewed, 1 bug fixed (hydric threshold `>` not `>=`) |
| `legends.rs` | `get_terrain_color`, `calculate_soil_legend_height`, `layer_soil_legend`, `layer_elevation_legend` | ✅ reviewed, y_offset param added |
| `title_block.rs` | `fit_text_to_cell`, `compute_unified_font_size`, `render_project_info_column`, `render_technical_details_column`, `render_branding_column`, `render_title_block` | ✅ reviewed, unified font size propagation fixed |

---

## Merge instructions, in order

### Step 1: Add to `svg/layers.rs` — colormap helpers

Copy `hsv_to_rgb` and `apply_terrain_colormap` from `svg_oxidant/src/drawing.rs`
into `svg/layers.rs` (or a new `svg/drawing.rs` — your choice, just make it
accessible where `render_terrain_heatmap` can call it).

These are pure math functions, no SVG output. No conflicts with existing code.

Run `cargo check` after.

### Step 2: Update `STYLES` in `svg/layers.rs`

The existing `STYLES` const has parcel/building/soil CSS. The new
`generate_svg_styles` function in `svg_oxidant/src/drawing.rs` produces the
ADDITIONAL classes needed: `.label`, `.footer-text`, `.footer-title`,
`.footer-name`, `.footer-tagline`, `.footer-label`, `.footer-value`,
`.footer-status`, plus `@import` for Typekit and `@font-face` for Balmat.

**APPEND** these new rules to the existing `STYLES` string — do NOT replace
the existing rules or the parcel/soil/building CSS breaks.

The new classes are at the bottom of `generate_svg_styles` in `drawing.rs`.
Since the styles are scaled by `footer_height_px`, you can either:
- Keep them as a static string at reference size (108px footer), or
- Make `STYLES` a function `pub fn styles(footer_px: f64) -> String` that
  calls `generate_svg_styles` — more faithful to Python

Run `gen_alligator` after and check fonts render correctly in the title block.

### Step 3: Replace `svg/title_block.rs` — all title block functions

The entire `svg_oxidant/src/title_block.rs` replaces the contents of
`svg/title_block.rs`. Key things to verify before replacing:

- The `render_title_block` signature matches the call in `svg/mod.rs` line 117:
  `render_title_block(&mut svg, lc, &plan.title, &plan.soil_zones, scale_ft_per_in)`
  **It does — verified.**
- `REFERENCE_FOOTER_PX = 108.0` is defined as a const — **it is.**
- Helper functions are private (`fn` not `pub fn`) — **they are.**
- All user text goes through `xml_escape()` — **verified.**

After replacing, run `cargo check`, then `gen_alligator`. This is the big
visual checkpoint — title block should now show correct 40/30/30 columns,
labeled grid in col 2, and nursery branding in col 3.

### Step 4: Replace `render_soils` in `svg/layers.rs`

Copy `render_soils` and its helpers (`ring_to_path`, `rings_to_path`,
`soil_css_class`) from `svg_oxidant/src/layers.rs`.

Note: `svg/layers.rs` already has `soil_css_class` and path helpers — diff
carefully and replace only what's changed. The key fix is the hydric threshold
(`> 50.0` not `>= 50.0`).

SVG group ID must be `"soils-ssurgo"` — verified correct.

Run `cargo check` after.

### Step 5: Replace `render_terrain_heatmap` in `svg/layers.rs`

Copy `render_terrain_heatmap` from `svg_oxidant/src/layers.rs`.

This function now colorizes the DEM rather than rendering it greyscale.
Requires `apply_terrain_colormap` (added in Step 1) and the `image` crate
(already in `Cargo.toml`). Also needs `base64` crate (already in
`Cargo.toml`).

Run `gen_alligator` after — terrain should now show a warm/cool color ramp
instead of greyscale.

### Step 6: Create `svg/legends.rs` and wire into `svg/mod.rs`

Copy `svg_oxidant/src/legends.rs` to `svg/legends.rs`.

Add to `svg/mod.rs`:
```rust
pub mod legends;
```

Update `assemble_svg` in `svg/mod.rs` to call the legends inside `_Sheet_Info`
after the north arrow:

```rust
// Soil legend (conditional)
if !plan.soil_zones.is_empty() {
    legends::layer_soil_legend(&mut svg, &plan.soil_zones, lc, 0.0);
}

// Elevation legend (conditional — pass actual min/max elev when terrain is included)
// legends::layer_elevation_legend(&mut svg, min_elev, max_elev, lc, soil_legend_h);
```

Note the `y_offset` parameter: pass `0.0` for soil legend (top), and
`calculate_soil_legend_height(&plan.soil_zones)` for elevation legend
(stacked below). The elevation legend call site depends on whether you have
min/max elevation data available from the terrain fetch — stub it for now.

Run `gen_alligator` after.

---

## Visual verification checkpoints

After Step 3 (title block):
- Compare `/tmp/alligator_axis.svg` against reference PNG
- Check: 40/30/30 column split, labeled grid in col 2 (DATE/SCALE/DESIGNER),
  nursery name + details in col 3, Balmat font in use

After Step 5 (terrain heatmap):
- Aerial photo should no longer look washed out/desaturated
- DEM layer should show a blue-to-red elevation color ramp

After Step 6 (legends):
- No legends visible on this property (0 soil zones, no terrain stats)
- Test with a property that has soils data to see legends appear

---

## Notes on signature changes

The `layer_soil_legend` and `layer_elevation_legend` signatures in
`svg_oxidant/` have a `y_offset: f64` parameter that wasn't in the original
spec. This was added during review to prevent legend overlap. Pass `0.0` for
the first legend and `calculate_soil_legend_height(zones)` for the second.

---

## What NOT to touch

Everything else in `svg/` — `mod.rs` structure, `layout.rs`, `path.rs`,
`assets.rs`, `layers.rs` functions other than those listed above — is correct
and must not be changed.
