# Design System Strategy: The Salvaged Terminal

## 1. Overview & Creative North Star
**Creative North Star: "The Salvaged Terminal"**
This design system rejects the polished, sterile perfection of modern SaaS. Instead, it embraces the raw, functional beauty of reclaimed industrial hardware. It is software that feels like it was unearthed, repaired, and re-commissioned. 

The aesthetic is "Rusty Ramshackle"—an intentional friction between high-density information (code) and low-fidelity physical artifacts (weathered surfaces). We break the "template" look through **intentional asymmetry**, heavy use of **monospaced typography**, and a **layered tonal depth** that mimics stacked metal plates. The interface should feel heavy, tactile, and undeniably functional, prioritizing information density over "airy" whitespace.

---

## 2. Colors & Surface Logic
The palette is a dialogue between the cold, inert `Deep Iron Greys` and the volatile, organic tones of `Oxidized Copper` and `Rust`.

### The "No-Line" Rule
Standard 1px solid borders are strictly prohibited for layout sectioning. Boundaries must be defined through **Background Color Shifts**. For example, a code editor (`surface-container-lowest`) should be inset directly into a main workspace (`surface-container-low`) without a stroke. The contrast between these shades is the divider.

### Surface Hierarchy & Nesting
Treat the UI as a series of physical "sheets" of metal:
*   **Base Layer (`surface`):** The heavy machinery chassis.
*   **The Inset (`surface-container-low`):** Used for primary workspace backgrounds.
*   **The Component (`surface-container-high`):** For active panels or persistent sidebars.
*   **The High-Focus (`surface-container-highest`):** For popovers or active "salvaged" modules.

### Signature Textures & Gradients
To avoid a flat "vector" feel, use subtle gradients for CTAs. A Primary Button should not be a flat `#ffb59d`; it should transition from `primary` to `primary-container`. This mimics the way light hits a curved, rusted pipe or an old incandescent bulb.

---

## 3. Typography
The typography system is built on a "Hard/Soft" contrast: technical monospaced precision for the "machine" and sturdy sans-serif for the "operator."

*   **Display & Headlines (Space Grotesk):** Chosen for its architectural, slightly idiosyncratic letterforms. Use `display-lg` and `headline-md` sparingly to anchor sections with an authoritative, industrial voice.
*   **Body & Utility (Inter):** High-readability sans-serif for long-form documentation and instructions.
*   **The Terminal Soul (Monospace - System/JetBrains):** While not explicitly in the scale, all code blocks and "readout" labels must use a monospaced font. This reinforces the "Salvaged Terminal" aesthetic, making every data point feel like a line of telemetry.

---

## 4. Elevation & Depth
In an industrial environment, depth is physical. We replace "Digital Elevation" (shadows) with "Material Stacking" (tones).

*   **The Layering Principle:** Rather than lifting a card with a shadow, "cut it out" of the background. Use `surface-container-lowest` for deep insets and `surface-bright` for elements that need to feel "closer" to the user's eye.
*   **The "Ghost Border" Fallback:** If a container requires a boundary (e.g., a code snippet or terminal input), use a **dashed path** or **double line** using `outline-variant` at 20% opacity. This mimics weathered mechanical etchings rather than clean digital lines.
*   **Glassmorphism (The "Oil-Slick" Blur):** For floating overlays (Tooltips, Modals), use semi-transparent `surface-container-highest` with a high `backdrop-blur` (12px-20px). This creates a "smoked glass" effect common in old industrial control panels.

---

## 5. Components

### Buttons
*   **Primary:** Solid `primary` background. 0px corner radius. Text in `on-primary`.
*   **Secondary (Patina):** `secondary-container` background with `on-secondary-container` text. Use a dashed `outline` to suggest a "bolted-on" module.
*   **Tertiary:** No background. Text in `primary`. Hover state triggers a `surface-container-highest` subtle background shift.

### Inputs & Text Areas
*   **Styling:** Background set to `surface-container-lowest`. No rounded corners.
*   **Focus State:** A 2px solid "rust" (`primary`) left-side border only. This avoids the "boxy" feel of a full border while providing high-contrast feedback.

### Cards & Lists
*   **No Dividers:** Prohibit the use of horizontal rules. Separate list items using `8px` of vertical space or by alternating background tones between `surface-container-low` and `surface-container-high`.
*   **The "Tag" (Chips):** Small, monospaced text. High contrast (e.g., `tertiary` background with `on-tertiary` text). These should look like metal stamps or dymo-labels.

### Additional Industrial Components
*   **The Status Gauge:** Instead of a standard progress bar, use a segmented "LED" bar where each segment is a discrete square block, using `secondary` (Patina) for progress and `surface-container-highest` for the empty track.
*   **The "Telemetry" Feed:** A dedicated vertical sidebar for code translation logs, using `label-sm` monospaced text in `on-surface-variant`.

---

## 6. Do's and Don'ts

### Do
*   **DO** use 0px border radii everywhere. This system is built on hard angles.
*   **DO** lean into high-density layouts. Think "Instrument Cluster," not "Landing Page."
*   **DO** use `primary` (Rust) and `secondary` (Patina) as functional indicators (e.g., Rust for errors/warnings, Patina for successful translations).

### Don't
*   **DON'T** use soft, rounded corners or "friendly" bubble shapes.
*   **DON'T** use 100% opaque, high-contrast borders. They break the illusion of a weathered, integrated machine.
*   **DON'T** use standard blue for links. Use `tertiary` (Burnt Orange) to maintain the industrial warmth.