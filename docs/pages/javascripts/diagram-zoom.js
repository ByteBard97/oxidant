/**
 * Diagram zoom — click any Mermaid diagram to open it full-screen.
 *
 * MkDocs Material 9.x renders mermaid blocks into a `div.mermaid` that uses
 * a *closed* Shadow DOM to hold the SVG.  A closed shadow root is opaque to
 * querySelector, so we monkey-patch attachShadow to force mode:"open" on
 * `.mermaid` elements before Material's async mermaid handler fires.
 */
(function () {
  // ── Force open shadow roots on .mermaid elements ──────────────────────────
  // Material calls attachShadow({mode:"closed"}) inside an async subscribe,
  // but this patch runs synchronously at script load — so we win the race.
  const _attachShadow = Element.prototype.attachShadow;
  Element.prototype.attachShadow = function (init) {
    if (this.classList && this.classList.contains('mermaid')) {
      init = Object.assign({}, init, { mode: 'open' });
    }
    return _attachShadow.call(this, init);
  };

  // ── Build modal DOM ────────────────────────────────────────────────────────
  const overlay = document.createElement('div');
  overlay.id = 'dz-overlay';
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('role', 'dialog');
  overlay.innerHTML = `
    <div id="dz-modal">
      <div id="dz-toolbar">
        <span id="dz-hint">scroll to zoom · drag to pan · ESC to close</span>
        <button id="dz-close" aria-label="Close diagram">✕ CLOSE</button>
      </div>
      <div id="dz-content"></div>
    </div>
  `;
  document.body.appendChild(overlay);

  // ── Pan / zoom state ───────────────────────────────────────────────────────
  let scale = 1, panX = 0, panY = 0, dragging = false, startX = 0, startY = 0;

  function applyTransform(el) {
    el.style.transform = `translate(${panX}px, ${panY}px) scale(${scale})`;
  }

  function resetTransform() { scale = 1; panX = 0; panY = 0; }

  // ── Open / close ──────────────────────────────────────────────────────────
  function openModal(svg) {
    resetTransform();
    const clone = svg.cloneNode(true);
    clone.dataset.dzSvg = '';
    // Don't removeAttribute('style') — Mermaid sets inline background/theme styles on the SVG root.
    // Just override the specific layout properties we need.
    clone.style.cursor = 'grab';
    clone.style.transformOrigin = 'center center';
    clone.style.userSelect = 'none';
    clone.style.maxWidth = 'none';
    clone.style.width = 'auto';
    clone.style.height = 'auto';

    const content = document.getElementById('dz-content');
    content.innerHTML = '';
    content.appendChild(clone);
    applyTransform(clone);
    overlay.classList.add('active');
    overlay.focus();

    content.onwheel = (e) => {
      e.preventDefault();
      scale = Math.min(Math.max(scale * (e.deltaY > 0 ? 0.9 : 1.1), 0.3), 8);
      applyTransform(clone);
    };

    clone.onmousedown = (e) => {
      dragging = true;
      startX = e.clientX - panX;
      startY = e.clientY - panY;
      clone.style.cursor = 'grabbing';
      e.preventDefault();
    };
    content.onmousemove = (e) => {
      if (!dragging) return;
      panX = e.clientX - startX;
      panY = e.clientY - startY;
      applyTransform(clone);
    };
    content.onmouseup = () => { dragging = false; clone.style.cursor = 'grab'; };
    content.onmouseleave = () => { dragging = false; };
  }

  function closeModal() {
    overlay.classList.remove('active');
    document.getElementById('dz-content').innerHTML = '';
  }

  document.getElementById('dz-close').addEventListener('click', closeModal);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

  // ── Helper: get SVG from a .mermaid element (shadow root or direct) ────────
  function getSvg(mermaidEl) {
    // Material uses a Shadow DOM — accessible via shadowRoot after our patch
    if (mermaidEl.shadowRoot) {
      return mermaidEl.shadowRoot.querySelector('svg');
    }
    // Fallback for any renderer that inlines the SVG directly
    return mermaidEl.querySelector('svg');
  }

  // ── Event delegation — catches clicks in any .mermaid element ─────────────
  document.addEventListener('click', function (e) {
    // Don't intercept modal clicks
    if (overlay.contains(e.target)) return;

    const mermaidEl = e.target.closest('.mermaid');
    if (!mermaidEl) return;

    const svg = getSvg(mermaidEl);
    if (svg) {
      e.preventDefault();
      openModal(svg);
    }
  });

  // ── cursor:zoom-in — applied once Mermaid renders ─────────────────────────
  function styleDiagrams() {
    document.querySelectorAll('.mermaid').forEach(el => {
      const svg = getSvg(el);
      if (svg && !svg.dataset.dzStyled) {
        svg.dataset.dzStyled = 'true';
        svg.style.cursor = 'zoom-in';
      }
    });
  }

  const observer = new MutationObserver(styleDiagrams);
  observer.observe(document.body, { childList: true, subtree: true });

  // Poll for a few seconds after load as a belt-and-suspenders measure
  let polls = 0;
  const poll = setInterval(() => {
    styleDiagrams();
    if (++polls >= 20) clearInterval(poll);
  }, 500);
})();
