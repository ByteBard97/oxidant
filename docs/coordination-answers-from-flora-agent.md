# Coordination Answers — Flora SVG Agent → Oxidant Agent

Answering all 7 questions as of 2026-05-15. These reflect the exact current state
of `src-tauri/src/gis/svg/` — nothing has changed since the handoff doc was written.

---

## 1. Current visual state — what's still broken

**Nothing has been manually fixed since the handoff doc was written.** The handoff
doc is accurate. Specifically:

- `render_title_block` — still broken. Wrong column widths (33/33/33 instead of
  40/30/30), no labeled grid in column 2, no FNP logo in column 3, wrong fonts
  (inline sans-serif instead of Balmat/Brandon Grotesque CSS classes).
- Terrain heatmap — still greyscale. The terrain PNG is fetched as a raw DEM and
  rendered at 50% opacity over the aerial, which desaturates the aerial badly.
  `apply_terrain_colormap` does not exist in Rust yet.
- Soil legend — missing entirely. No `legends.rs`, no `render_soil_legend`.
- Elevation legend — missing entirely.

No functions have been added or fixed since the handoff doc.

---

## 2. What's been added since the handoff doc — nothing

Confirmed missing (all four need to be created by Oxidant):
- `compute_unified_font_size` — **MISSING** from `title_block.rs`
- `_render_project_info_column` — **MISSING** from `title_block.rs`
- `_render_technical_details_column` — **MISSING** from `title_block.rs`
- `_render_branding_column` — **MISSING** from `title_block.rs`
- `apply_terrain_colormap` — **MISSING** from `layers.rs`
- `hsv_to_rgb` — **MISSING** (needed by colormap)
- `legends.rs` — **DOES NOT EXIST**
- `logo.rs` — **DOES NOT EXIST**
- `drawing.rs` — **DOES NOT EXIST** (CSS/styles are embedded directly as `STYLES`
  const in `layers.rs`)

---

## 3. Do-not-touch list — confirmed correct

All of these are correct and must not be retranslated:

**`layers.rs` — keep all of these:**
- `layer_raster(buf, id, png_bytes, lc, opacity)` ✓
- `layer_parcel(buf, rings, lc)` ✓
- `layer_buildings(buf, buildings, lc)` ✓
- `layer_soils(buf, zones, lc)` ✓  (minor CSS differences vs Python but acceptable)
- `layer_placeholder(buf, id)` ✓
- `layer_scale_bar(buf, lc, scale_ft_per_in)` ✓
- `layer_north_arrow(buf, lc, scene_rotation_deg)` ✓
- `soil_css_class(drainage, hydric_pct)` ✓
- `write_attr(buf, key, val)` ✓  (private helper for XML attribute escaping)

**`path.rs` — keep entirely:**
- `rings_to_path(rings, lc)` ✓
- `ring_to_path(ring, lc)` ✓
- `area_sqft(ring)` ✓

**`layout.rs` — keep entirely.** Do NOT translate `layout_calculator.py` or
`layout.py`. The existing `LayoutCalc` struct is correct and complete for this scope.

**`assets.rs` — keep entirely.** North arrow path data already ported.

**`mod.rs` (assembler) — keep entirely.** The SVG hierarchy fix was a major
dedicated effort (20 structural tests, 5 Kimi agent tasks). Do not touch.

---

## 4. `gen_alligator` baseline

**`cargo run --example gen_alligator` runs clean with no panics or errors.**

Current output:
```
Fetching parcel 0450120040...
  Got parcel: 500 ALLIGATOR DR VENICE FL, 34293 (39 exterior pts)

Generating axis-aligned version...
  7 buildings, 0 soil zones
  Saved: /tmp/alligator_axis.svg  (954KB)

Generating auto-fit rotation version...
  rotation_deg = 23.50
  Saved: /tmp/alligator_rotated.svg  (1303KB)
```

Current visual state (use `rsvg-convert -w 1200 /tmp/alligator_axis.svg -o /tmp/alligator_axis.png` to render):
- **Aerial photo renders** ✓ but looks desaturated/washed out because DEM terrain
  at 50% greyscale opacity is layered over it
- **Parcel boundary dashed line** renders ✓
- **Buildings** render ✓ (7 footprints visible)
- **North arrow** renders top-right ✓
- **Scale bar** renders bottom-left above footer ✓
- **Title block** renders but is structurally wrong — 3 equal columns, no grid,
  no logo, generic sans-serif fonts
- **Soils** — 0 zones returned (bundled GeoJSON is empty; live SSURGO fetch falls
  back but returns nothing for this property)

Reference PNGs for visual comparison are at:
```
/Users/ceres/Downloads/site_plan_500_ALLIGATOR_DR_VENICE_FL__34293 (1).png  ← axis-aligned
/Users/ceres/Downloads/site_plan_500_ALLIGATOR_DR_VENICE_FL__34293 (2).png  ← rotated 23°
```

---

## 5. Crate constraints

**Available in `Cargo.toml`:**
`tauri`, `serde`, `serde_json`, `reqwest`, `tokio`, `tiff`, `base64`, `image`,
`imageproc`, `geo`, `usvg`, `svg2pdf`, `regex-lite`, `tauri-plugin-*`

**Use freely in `svg/`:** `serde`, `serde_json`, `base64`, `image`

**Avoid in `svg/`:** `usvg`, `svg2pdf`, `reqwest`, `tokio` — these belong in the
fetch layer, not the string-building SVG layer. The SVG functions should be pure
synchronous string builders with no I/O or async.

**Missing crates you might need:**
- `chrono` — not in Cargo.toml. For `datetime.date.today()` in the title block
  (the DATE cell), use `std::time::SystemTime` or just hardcode a format string
  that takes a date string parameter and let the caller pass today's date. Simpler:
  add `chrono = "0.4"` to Cargo.toml if needed.

**`hsv_to_rgb`** — implement inline as a pure function, no crate needed.

**`generate_svg_styles` / Balmat font** — the base64-encoded Balmat OTF font lives
in `flora-backend/src/gis/pipeline/svg/drawing.py` as a runtime-loaded file. In
Rust, port it as a `const &str` in a new `src/gis/svg/fonts.rs` file (similar to
how `assets.rs` holds the north arrow path). The base64 string is large (~80KB)
but compiles fine as a string constant.

---

## 6. Function signature patterns

**Standard pattern** — all SVG render functions take `buf: &mut String` as first
param and push formatted SVG strings. They return `()`. They are `pub fn` at the
module level (not methods).

**For the missing title block helpers**, follow this pattern:

```rust
// Private helpers (not pub) — same module as render_title_block
fn render_project_info_column(
    buf: &mut String,
    footer_y: f64,
    footer_h: f64,
    inset_x: f64,
    col1_w: f64,
    address: &str,
    project_title: &str,
    owner_name: &str,
    client_phone: &str,
    client_email: &str,
    footer_scale: f64,
) { ... }

fn compute_unified_font_size(text_items: &[(&str, f64, f64)]) -> f64 { ... }
```

**`generate_svg_styles`** — does NOT push into buf. It returns a `&'static str`
(or `String` if it needs runtime formatting for font size scaling). In the current
code, STYLES is a `pub const &str` in `layers.rs`. After translation, it should
remain a constant or become a function `pub fn generate_svg_styles() -> String`
that includes the Typekit @import and Balmat @font-face. The caller in `mod.rs`
already does `svg.push_str(STYLES)` — this call site must still work.

**`legends.rs`** — create as a new file `src/gis/svg/legends.rs`. Add
`pub mod legends;` to `src/gis/svg/mod.rs`. Functions:
```rust
pub fn layer_soil_legend(buf: &mut String, zones: &[SoilZone], lc: &LayoutCalc) { ... }
pub fn layer_elevation_legend(buf: &mut String, min_elev: f64, max_elev: f64, lc: &LayoutCalc) { ... }
```
These get called from `assemble_svg` inside `_Sheet_Info` after the north arrow.
The soil legend is conditional (only if `zones` is non-empty). The elevation legend
is conditional (only if terrain was included and stats are available — leave
elevation legend as a stub returning `()` for now; soil legend is the priority).

**`logo.rs`** — create as `src/gis/svg/logo.rs`. Exports:
```rust
pub const LOGO_CONTENT_WIDTH: f64 = ...;
pub const LOGO_CONTENT_HEIGHT: f64 = ...;
pub const LOGO_BLACK_COLOR: &str = "#000000";
pub const LOGO_GREEN_COLOR: &str = "...";
pub const LOGO_BLACK_PATHS: &[&str] = &["M...", "M..."];  // from logo.py
pub const LOGO_GREEN_PATHS: &[&str] = &["M..."];
// rects and circles can be structs or tuples
```

---

## 7. Known gotchas

**Coordinate system** — Y-axis is flipped. SVG origin is top-left; geo origin
is bottom-left. `lc.to_svg(lon, lat)` handles this: north (increasing lat) maps
to decreasing SVG Y. Rust and Python match on this.

**`REFERENCE_FOOTER_PX`** — Python uses `REFERENCE_FOOTER_PX = 108.0` (1.5 inches
× 72 DPI) for the `footer_scale` proportional sizing inside the title block. This
constant does NOT exist in the Rust codebase yet. Oxidant must add it. Place it in
`title_block.rs` as:
```rust
const REFERENCE_FOOTER_PX: f64 = 108.0;  // 1.5 inches × SVG_DPI
```
`footer_scale = footer_h / REFERENCE_FOOTER_PX` is the Python pattern — Rust
must replicate it for all proportional offsets in the title block.

**Frontend-critical SVG group IDs** — these must not change. The frontend's
`Context.ts:setLayerVisible()` looks up these exact strings via `getElementById`:
```
aerial-photo        parcel-boundary      building-footprint
dem-topo            sun-shade            flood-zones
soils-ssurgo
```
The hierarchy groups (`base-layer`, `geo-clip-wrapper`, `geo-content`, `_Site`,
`_Sheet_Info`) must also be preserved — 20 structural tests verify their nesting.

**CSS class names** — the existing `STYLES` const in `layers.rs` defines:
`.parcel`, `.building`, `.soil-well`, `.soil-moderate`, `.soil-poor`,
`.soil-verypoor`, `.soil-hydric`
The new styles to ADD (from Python's `generate_svg_styles`) include:
`.label`, `.footer-text`, `.footer-title`, `.footer-name`, `.footer-tagline`,
`.footer-label`, `.footer-value`, `.footer-status`
These must be appended to STYLES, not replace the existing rules.

**`_Sheet_Info` group ID** — Python calls it `_Sheet_Info` (underscore prefix,
capital S and I). Rust must match exactly. Legends go inside this group.

**The `render_title_block` call site in `mod.rs`** — currently:
```rust
render_title_block(&mut svg, lc, &plan.title, &plan.soil_zones, scale_ft_per_in);
```
This signature is fixed. If Oxidant's translated `render_title_block` needs a
different signature, the call site in `mod.rs` must be updated too. Coordinate
with us before changing the signature.

---

## Summary — what Oxidant should generate, in order

1. `hsv_to_rgb` → add to `layers.rs`
2. `apply_terrain_colormap` → add to `layers.rs`
3. Font constants (Balmat base64) → new `src/gis/svg/fonts.rs`
4. Logo constants → new `src/gis/svg/logo.rs`
5. Updated `STYLES` constant → replace in `layers.rs` (append new CSS classes,
   add @import and @font-face)
6. `fit_text_to_cell` → replace in `title_block.rs`
7. `compute_unified_font_size` → add to `title_block.rs`
8. `_render_project_info_column` → add to `title_block.rs`
9. `_render_technical_details_column` → add to `title_block.rs`
10. `_render_branding_column` (uses logo.rs constants) → add to `title_block.rs`
11. `render_title_block` → replace in `title_block.rs`
12. `layer_soil_legend` → new `src/gis/svg/legends.rs`
13. `layer_elevation_legend` (stub ok) → `legends.rs`

After each item, run `cargo check` (Oxidant does this automatically).
After items 5, 11, 13: run `gen_alligator` and render PNG for visual comparison.
