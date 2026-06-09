/**
 * FontPreview — canonical live subtitle overlay used by both the Dashboard
 * (index.html) and the Proofread page (proofread.html).
 *
 * Goal: visually match the FFmpeg/libass burnt-in output as closely as
 * possible so what the user sees during proof-reading equals the final
 * rendered video.
 *
 * Approach:
 *   1. Draw via SVG <text> + paint-order: stroke fill, which mirrors libass
 *      FT_Stroker geometry (true outside-glyph contour, round joins/caps).
 *   2. Use a viewBox sized to the renderer's PlayResX/PlayResY (1920×1080,
 *      hardcoded to match backend/renderer.py). Every coordinate inside the
 *      SVG is therefore one ASS pixel — font_config.size, outline_width and
 *      margin_bottom are passed through as raw libass values, no scaling.
 *      The browser handles fit-to-container automatically.
 *   3. Stroke-width is doubled because SVG strokes are centered on the path;
 *      libass renders Outline=N as N px OUTSIDE the glyph, so stroke-width
 *      = 2N + paint-order:stroke fill (fill draws on top) reproduces it.
 *   4. text-rendering: geometricPrecision + grayscale font smoothing, to
 *      flatten browser LCD subpixel AA closer to libass grayscale output.
 *
 * Pages must provide:
 *   <svg id="subtitleSvg" class="..." aria-hidden="true">
 *     <text id="subtitleSvgText"></text>
 *   </svg>
 *
 * Usage:
 *   FontPreview.init(socketOrNull)   // call on page init; socket may be null
 *   FontPreview.updateText(text)     // call from timeupdate / segment switch
 */
const FontPreview = (() => {
  // Same-origin relative base. Must NOT fall back to http://localhost:5001 — when
  // the page is viewed from a machine that runs its own server on :5001, the font
  // fetch + socket would hit THAT server (no session there) → 401 → login loop.
  const _apiBase = (typeof API_BASE !== 'undefined' ? API_BASE : '');
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // Must match backend/renderer.py:73-74 (PlayResX / PlayResY in ASS [Script Info]).
  const PLAY_RES_X = 1920;
  const PLAY_RES_Y = 1080;

  // libass typical line height factor (≈1.2 of EM). Used for multi-line stacking.
  const LINE_HEIGHT_FACTOR = 1.2;

  let _svgEl = null;
  let _textEl = null;
  let _font = null;
  let _listenerRegistered = false;

  function _resolveFont(font) {
    return {
      family: font.family || 'Noto Sans TC',
      size: Number(font.size) || 48,
      color: font.color || '#FFFFFF',
      outline_color: font.outline_color || '#000000',
      // ASS Outline=N → SVG stroke-width = 2N because SVG strokes are
      // centered on the path; with paint-order:stroke fill the inner half
      // is over-painted by the fill, leaving N px of outline outside.
      outline_width: (font.outline_width != null ? Number(font.outline_width) : 2),
      margin_bottom: font.margin_bottom != null ? Number(font.margin_bottom) : 40,
    };
  }

  function applyFontConfig(font) {
    if (!font || !_svgEl || !_textEl) return;
    _font = _resolveFont(font);

    _svgEl.setAttribute('viewBox', `0 0 ${PLAY_RES_X} ${PLAY_RES_Y}`);
    _svgEl.setAttribute('preserveAspectRatio', 'xMidYMid meet');

    _textEl.setAttribute('text-anchor', 'middle');
    _textEl.setAttribute('paint-order', 'stroke fill');
    _textEl.setAttribute('stroke-linejoin', 'round');
    _textEl.setAttribute('stroke-linecap', 'round');
    _textEl.setAttribute(
      'font-family',
      `'${_font.family}', 'Microsoft JhengHei', 'PingFang TC', system-ui, sans-serif`,
    );
    _textEl.setAttribute('font-size', _font.size);
    _textEl.setAttribute('fill', _font.color);
    _textEl.setAttribute('stroke', _font.outline_color);
    _textEl.setAttribute('stroke-width', _font.outline_width * 2);

    _textEl.style.textRendering = 'geometricPrecision';
    _textEl.style.webkitFontSmoothing = 'antialiased';
    _textEl.style.mozOsxFontSmoothing = 'grayscale';

    // Re-render whatever text is currently shown so size/outline edits
    // take effect immediately without waiting for the next segment switch.
    if (_textEl.dataset.lastText !== undefined) _renderText(_textEl.dataset.lastText);
  }

  function _renderText(raw) {
    if (!_textEl || !_font) return;
    _textEl.dataset.lastText = raw;
    while (_textEl.firstChild) _textEl.removeChild(_textEl.firstChild);

    const text = (raw || '').trim();
    if (!text) {
      _textEl.style.opacity = '0';
      return;
    }
    _textEl.style.opacity = '1';

    // Split on real newlines or the literal ASS escape "\N" so multi-line
    // segments preview the same way the renderer will burn them in
    // (renderer.py converts "\n" → "\\N" before writing to ASS Events).
    const lines = (raw || '').split(/\r?\n|\\N/);
    const lineH = _font.size * LINE_HEIGHT_FACTOR;
    const baseY = PLAY_RES_Y - _font.margin_bottom;
    const x = PLAY_RES_X / 2;

    // Anchor BOTTOM line at baseY (matches ASS Alignment=2 + MarginV semantics)
    // and stack earlier lines upward.
    lines.forEach((line, i) => {
      const tspan = document.createElementNS(SVG_NS, 'tspan');
      tspan.setAttribute('x', x);
      tspan.setAttribute('y', baseY - lineH * (lines.length - 1 - i));
      tspan.textContent = line;
      _textEl.appendChild(tspan);
    });
  }

  // Inject one @font-face per file the backend exposes via /api/fonts so
  // the live preview uses the exact same TTF/OTF the renderer will hand to
  // libass via :fontsdir=. Without this, the browser falls back to whichever
  // system font matches the family name (often a different cut, sometimes
  // a different family entirely) and preview glyphs drift from burn-in.
  // Cache of the /api/fonts list (each {file, family}) so the subtitle-
  // settings panels can build their font picker from the SAME set the
  // overlay actually has @font-face rules for — guaranteeing every option
  // renders (and matches the burn-in) instead of silently falling back.
  let _fonts = [];
  // CJK system fonts the BURN-IN renderer can actually use on the server host
  // (from /api/fonts `system_fonts`). Server-verified so the picker never
  // offers a family that would tofu (e.g. macOS PingFang on a daemon, or an
  // uninstalled Noto). Replaces the old hard-coded per-page font lists.
  let _systemFonts = [];

  function _injectFaces(fonts) {
    // Replace (not append) the style element so a refresh after upload/delete
    // never accumulates stale @font-face rules.
    let styleEl = document.getElementById('font-preview-bundled-faces');
    if (!styleEl) {
      styleEl = document.createElement('style');
      styleEl.id = 'font-preview-bundled-faces';
      document.head.appendChild(styleEl);
    }
    // font-display:block holds rendering until the font loads (matters because
    // we draw the overlay immediately on segment switch and a fallback flash
    // would reveal the wrong glyph).
    styleEl.textContent = fonts.map(f => {
      const url = `${_apiBase}/fonts/${encodeURIComponent(f.file)}`;
      const fmt = f.file.toLowerCase().endsWith('.otf') ? 'opentype' : 'truetype';
      return `@font-face{font-family:'${f.family}';src:url('${url}') format('${fmt}');font-display:block;}`;
    }).join('\n');
  }

  async function _loadFonts() {
    try {
      const r = await fetch(`${_apiBase}/api/fonts`);
      if (!r.ok) return _fonts;
      const data = await r.json();
      _fonts = (data && data.fonts) || [];
      _systemFonts = (data && data.system_fonts) || [];
      _injectFaces(_fonts);
      // Eagerly load each face so the first overlay paint already has the glyph
      // in cache; otherwise the very first segment can flash fallback metrics.
      if (document.fonts && document.fonts.load && _fonts.length) {
        await Promise.all(_fonts.map(f =>
          document.fonts.load(`16px '${f.family}'`).catch(() => {})
        ));
        if (_font) applyFontConfig(_font);  // re-paint with correct metrics
      }
    } catch (err) {
      console.warn('[FontPreview] Failed to load fonts:', err);
    }
    return _fonts;
  }

  let _fontsInjected = false;
  async function _injectBundledFonts() {
    if (_fontsInjected) return;
    _fontsInjected = true;
    await _loadFonts();
  }

  function init(socketOrNull) {
    _svgEl = document.getElementById('subtitleSvg');
    _textEl = document.getElementById('subtitleSvgText');
    if (!_svgEl || !_textEl) return;

    _injectBundledFonts();

    fetch(`${_apiBase}/api/profiles/active`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.profile && data.profile.font) applyFontConfig(data.profile.font);
      })
      .catch((err) => { console.warn('[FontPreview] Failed to fetch active profile:', err); });

    const sock = socketOrNull || (typeof io !== 'undefined' ? io(_apiBase) : null);
    if (sock && !_listenerRegistered) {
      _listenerRegistered = true;
      sock.on('profile_updated', (data) => {
        if (data && data.font) applyFontConfig(data.font);
      });
    }
  }

  function updateText(text) {
    _renderText(text || '');
  }

  // Snapshot of the available uploaded/bundled fonts (each {file, family}),
  // for the subtitle-settings font pickers.
  function getFonts() { return _fonts.slice(); }

  function _esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g,
      c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  // Build <optgroup>/<option> HTML for a subtitle font <select>, shared by the
  // Dashboard + Proofread settings panels so both pickers behave identically:
  //   - "已上載字型": uploaded fonts (real @font-face + libass :fontsdir →
  //     guaranteed to render AND match the burn-in)
  //   - "系統字型": CJK families the SERVER reports the burn-in renderer can
  //     actually use on this host (`system_fonts` from /api/fonts) — so the
  //     picker never offers a family that would tofu in the rendered video.
  // `systemFonts` arg is optional and only overrides the server list (callers
  // should omit it and let the server be the source of truth).
  // The current value is always present + selected even if it is neither.
  function fontOptionsHtml(current, systemFonts) {
    const cur = current || '';
    const uploaded = [];
    const seen = new Set();
    _fonts.forEach((f) => {
      if (f.family && !seen.has(f.family)) { seen.add(f.family); uploaded.push(f.family); }
    });
    const sys = (systemFonts || _systemFonts || []).filter((s) => !seen.has(s));
    const opt = (fam) => `<option value="${_esc(fam)}"${fam === cur ? ' selected' : ''}>${_esc(fam)}</option>`;
    let html = '';
    if (uploaded.length) html += `<optgroup label="已上載字型">${uploaded.map(opt).join('')}</optgroup>`;
    if (sys.length) html += `<optgroup label="系統字型">${sys.map(opt).join('')}</optgroup>`;
    if (cur && !seen.has(cur) && !sys.includes(cur)) {
      html = `<option value="${_esc(cur)}" selected>${_esc(cur)}</option>` + html;
    }
    return html;
  }

  // Snapshot of the server-verified usable CJK system fonts (families).
  function getSystemFonts() { return _systemFonts.slice(); }

  // Re-fetch /api/fonts + re-inject @font-face. Call after a font upload or
  // delete so the new face is live in the overlay and getFonts() is current.
  async function refreshFonts() { return _loadFonts(); }

  return { init, updateText, applyFontConfig, getFonts, getSystemFonts, refreshFonts, fontOptionsHtml };
})();
