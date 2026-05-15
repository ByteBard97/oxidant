# Flora Backend — Python Idiom Addendum

Companion to `idiom_dictionary_python.md`. Covers patterns found by scanning the
actual target files (`drawing.py`, `title_block.py`, `layers.py`, `legends.py`).

Pattern frequency in the 4 target files:
  f-strings            55 occurrences  ← dominant pattern
  Tuple return types   20 occurrences
  Optional[T]          15 occurrences
  isinstance checks     5 occurrences
  try/except            2 occurrences
  list comprehension    1 occurrence

---

## fstring (55 occurrences — most common pattern)

Python f-strings with format specs map directly to Rust `format!()`.

```python
# Python
f'<rect x="{x:.2f}" y="{y:.2f}" width="{w:.2f}"/>'
f'1" = {ft_per_inch:.0f}\''
f"font-size: {font_size}px;"
```

```rust
// Rust
format!(r#"<rect x="{:.2}" y="{:.2}" width="{:.2}"/>"#, x, y, w)
format!("1&quot; = {:.0}&apos;", ft_per_inch)
format!("font-size: {}px;", font_size)
```

**SVG attribute quotes**: When the format string itself contains double quotes (common
in SVG), use raw string literals `r#"..."#`. If the SVG content contains `#`
(e.g. `fill="#000000"`), step up the delimiter: `r##"..."##`.

**Escaped characters in SVG text**: Python embeds `"` and `'` directly in SVG text
content. In Rust push these as XML entities:
- `"` → `&quot;`
- `'` → `&apos;`
- `<` → `&lt;`
- `>` → `&gt;`
- `&` → `&amp;`

---

## typing_tuple (20 occurrences)

Python functions that return tuples of mixed types.

```python
def fit_text_to_cell(...) -> Tuple[List[str], float]:
    return (lines, font_size)

def render_scale_bar(...) -> Tuple[str, str]:
    return (label, units)
```

```rust
// Small tuples: return as tuple
fn fit_text_to_cell(...) -> (Vec<String>, f64) {
    (lines, font_size)
}

// Tuples used as return types throughout a module: consider a small struct
// if the tuple has > 2 elements or is returned from multiple functions.
struct TextFit { lines: Vec<String>, font_size: f64 }
```

**Rule of thumb**: 2-element tuples → Rust tuple. 3+ elements or used in > 2
places → named struct.

---

## Library substitutions (non-1:1 — read carefully)

These are NOT drop-in replacements. The data model changes when you cross this
boundary, so the function signatures change too.

### svgwrite → String buffer

**This is the most important substitution.** Python SVG functions receive a
`dwg: svgwrite.Drawing` and add elements to it. Rust SVG functions receive
`buf: &mut String` and push formatted strings.

```python
# Python
def render_title_block(dwg, parent_grp, dimensions, ...):
    g = dwg.g(id='title_block')
    g.add(dwg.rect(insert=(x, y), size=(w, h), fill='white', stroke='black'))
    g.add(dwg.text('HELLO', insert=(x, y), class_='footer-title'))
    parent_grp.add(g)
```

```rust
// Rust
pub fn render_title_block(buf: &mut String, lc: &LayoutCalc, params: &TitleBlockParams, ...) {
    buf.push_str(r#"<g id="title-block">"#);
    buf.push_str(&format!(
        r#"<rect x="{:.2}" y="{:.2}" width="{:.2}" height="{:.2}" fill="white" stroke="black"/>"#,
        x, y, w, h
    ));
    buf.push_str(&format!(
        r#"<text x="{:.2}" y="{:.2}" class="footer-title">HELLO</text>"#,
        x, y
    ));
    buf.push_str("</g>");
}
```

Key mappings:
| svgwrite call | Rust string push |
|---|---|
| `dwg.g(id='foo')` + `parent.add(g)` | `buf.push_str(r#"<g id="foo">"#)` ... `buf.push_str("</g>")` |
| `dwg.rect(insert=(x,y), size=(w,h), fill='white')` | `format!(r#"<rect x="{:.2}" y="{:.2}" width="{:.2}" height="{:.2}" fill="white"/>"#, x,y,w,h)` |
| `dwg.text('str', insert=(x,y), class_='cls')` | `format!(r#"<text x="{:.2}" y="{:.2}" class="cls">str</text>"#, x, y)` |
| `dwg.line((x1,y1),(x2,y2), stroke='black', stroke_width=1)` | `format!(r#"<line x1="{:.2}" y1="{:.2}" x2="{:.2}" y2="{:.2}" stroke="black" stroke-width="1"/>"#, x1,y1,x2,y2)` |
| `dwg.path(d=path_d, fill='#000')` | `format!(r#"<path d="{}" fill="#000"/>"#, path_d)` |
| `elem['style'] = 'font-size: 10px'` | embed style inline in the format string |
| `elem['transform'] = f'translate({x},{y})'` | embed transform inline |

### GeoDataFrame / shapely → pre-parsed structs

**The Rust code does NOT use GeoDataFrames.** Geometry is pre-parsed from GeoJSON
into typed Rust structs before the SVG functions are called. Function signatures
change as follows:

| Python parameter | Rust parameter | Type |
|---|---|---|
| `soils: gpd.GeoDataFrame` | `zones: &[SoilZone]` | slice of pre-parsed structs |
| `buildings: gpd.GeoDataFrame` | `buildings: &[Building]` | slice of pre-parsed structs |
| `parcel: gpd.GeoDataFrame` | `rings: &Rings` | pre-parsed ring struct |
| `to_svg: Callable[[float,float], Tuple[float,float]]` | `lc: &LayoutCalc` | layout calculator with `to_svg()` method |

When translating, replace `geom.exterior.coords` / `geom.bounds` / shapely
geometry operations with calls to `lc.to_svg(lon, lat)` and iteration over
`rings.exterior: Vec<[f64; 2]>`.

### colorsys → inline HSV

Python's `colorsys.hsv_to_rgb(h, s, v)` returns `(r, g, b)` as floats 0–1.
The Rust equivalent is a small inline function — do not reach for a crate:

```rust
fn hsv_to_rgb(h: f64, s: f64, v: f64) -> (u8, u8, u8) {
    let i = (h * 6.0) as u32;
    let f = h * 6.0 - i as f64;
    let p = v * (1.0 - s);
    let q = v * (1.0 - f * s);
    let t = v * (1.0 - (1.0 - f) * s);
    let (r, g, b) = match i % 6 {
        0 => (v, t, p),
        1 => (q, v, p),
        2 => (p, v, t),
        3 => (p, p, v),  // note: Python colorsys has (p, q, v) here
        4 => (t, p, v),
        _ => (v, p, q),
    };
    ((r * 255.0) as u8, (g * 255.0) as u8, (b * 255.0) as u8)
}
```

### PIL.Image → `image` crate

Already used in `src-tauri/src/gis/fetch/imagery.rs` and `terrain.rs`.
Use `image::DynamicImage` and `image::ImageBuffer`. BytesIO → `std::io::Cursor<Vec<u8>>`.

### datetime → inline

`datetime.date.today().strftime("%m.%d.%Y")` → use `chrono` crate if already
in Cargo.toml, otherwise format manually from `std::time::SystemTime`. Check
`src-tauri/Cargo.toml` for what's already present.

### numpy → plain iterators

The only numpy in these files is in `apply_terrain_colormap` (array normalization).
Replace `np.interp(value, [0,1], [a,b])` with `a + value * (b - a)`.

---

## Pre-existing Rust implementations — what to keep vs replace

The Rust files already exist at:
`/Users/ceres/Desktop/flora/flora-studio/src-tauri/src/gis/svg/`

**DO NOT overwrite the entire files.** Generate translated functions one at a time
and splice them in. Here is the verdict for each function:

### `layers.rs` — keep these, they're correct:
- `soil_css_class()` — correct
- `layer_raster()` — correct (id param already correct)
- `layer_parcel()` — correct
- `layer_buildings()` — correct
- `layer_soils()` — mostly correct, minor CSS class differences
- `layer_placeholder()` — correct
- `layer_scale_bar()` — correct
- `layer_north_arrow()` — correct

**New functions to ADD to `layers.rs`** (don't exist yet):
- `apply_terrain_colormap(normalized: f64) -> (u8, u8, u8)` — from `drawing.py`
- `hsv_to_rgb(h: f64, s: f64, v: f64) -> (u8, u8, u8)` — helper for above
- `layer_terrain_heatmap(buf, terrain_png, lc, opacity)` — replace current greyscale approach

**Update `STYLES` constant** — currently missing font imports and all footer-* CSS classes.
Translate `generate_svg_styles()` from `drawing.py` and replace the STYLES string.

### `title_block.rs` — replace entirely:
The current implementation is structurally wrong (wrong column widths, no grid,
no logo, no CSS classes). Translate all of these from `title_block.py`:
- `fit_text_to_cell()` — retranslate (logic correct but constants wrong)
- `compute_unified_font_size()` — translate (missing)
- `_render_project_info_column()` — translate (missing)
- `_render_technical_details_column()` — translate (missing, this is the 3×2 grid)
- `_render_branding_column()` — translate (missing, FNP logo + contact info)
- `render_title_block()` — retranslate (wrong structure)

**FNP logo**: The logo SVG path data lives at:
`/Users/ceres/Desktop/flora/flora-backend/src/gis/assets/logo.py`
Port the constants (`LOGO_BLACK_PATHS`, `LOGO_GREEN_PATHS`, `LOGO_BLACK_RECTS`,
`LOGO_BLACK_CIRCLES`, `LOGO_CONTENT_WIDTH`, `LOGO_CONTENT_HEIGHT`) to a new file:
`src-tauri/src/gis/svg/logo.rs`

### `layout.rs` — keep entirely:
The coordinate math and layout calculations are correct. Do not retranslate.

### `mod.rs` (assembler) — keep entirely:
The hierarchy fix was done correctly in a previous session. Do not retranslate.

---

## Verification

After each function is translated, run:

```bash
# Generates /tmp/alligator_axis.svg and /tmp/alligator_rotated.svg
cd /Users/ceres/Desktop/flora/flora-studio/src-tauri
cargo run --example gen_alligator

# Convert to PNG for visual comparison
rsvg-convert -w 1200 /tmp/alligator_axis.svg -o /tmp/alligator_axis.png
rsvg-convert -w 1200 /tmp/alligator_rotated.svg -o /tmp/alligator_rotated.png
```

Compare against the reference backend PNGs:
```
/Users/ceres/Downloads/site_plan_500_ALLIGATOR_DR_VENICE_FL__34293 (1).png
/Users/ceres/Downloads/site_plan_500_ALLIGATOR_DR_VENICE_FL__34293 (2).png
```

`cargo check` passing is necessary but not sufficient. The visual comparison
is the real correctness test.
