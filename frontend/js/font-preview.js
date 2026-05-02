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
  const _apiBase = (typeof API_BASE !== 'undefined' ? API_BASE : 'http://localhost:5001');
  const SVG_NS = 'http://www.w3.org/2000/svg';

  // Must match backend/renderer.py:73-74 (PlayResX / PlayResY in ASS [Script Info]).
  const PLAY_RES_X = 1920;
  const PLAY_RES_Y = 1080;

  // libass typical line height factor (≈1.2 of EM). Used for multi-line stacking.
  const LINE_HEIGHT_FACTOR = 1.2;

  let _svgEl = null;
  let _textEl = null;
  let _font = null;
  let _rawFontConfig = null;  // raw font config (includes subtitle_standard / line_wrap blocks)
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
    _rawFontConfig = font;
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

    // Step 1: split on existing line breaks (renderer-injected \\N or real \n)
    // because input may already be multi-line (e.g. bilingual EN+ZH stacked).
    const preLines = (raw || '').split(/\r?\n|\\N/);

    // Step 2: apply SubtitleWrap per pre-line if loaded.
    //   - cityu_hybrid preset (v3.9): use wrapHybrid (soft+hard cap, bottom-heavy)
    //   - other presets: use legacy wrapWithConfig
    // Falls back to no-wrap if SubtitleWrap script wasn't included.
    let lines = [];
    const standard = _rawFontConfig && _rawFontConfig.subtitle_standard;
    const useHybrid = standard === 'cityu_hybrid'
      && window.SubtitleWrap
      && typeof window.SubtitleWrap.wrapHybrid === 'function';

    if (useHybrid) {
      const lwCfg = (_rawFontConfig && _rawFontConfig.line_wrap) || {};
      preLines.forEach(pl => {
        const trimmed = (pl || '').trim();
        if (!trimmed) return;
        const wr = window.SubtitleWrap.wrapHybrid(trimmed, {
          soft_cap: lwCfg.soft_cap != null ? lwCfg.soft_cap : 14,
          hard_cap: lwCfg.hard_cap != null ? lwCfg.hard_cap : 16,
          max_lines: lwCfg.max_lines != null ? lwCfg.max_lines : 2,
          tail_tolerance: lwCfg.tail_tolerance != null ? lwCfg.tail_tolerance : 2,
          locked: null,  // Phase 1: preview omits V_R11 lock chain (visual approximation)
        });
        if (wr.lines.length > 0) lines = lines.concat(wr.lines);
      });
    } else if (window.SubtitleWrap && _rawFontConfig) {
      preLines.forEach(pl => {
        const wr = window.SubtitleWrap.wrapWithConfig(pl, _rawFontConfig);
        if (wr.lines.length === 0) {
          // empty/whitespace pre-line — keep as a placeholder for spacing? Skip.
        } else {
          lines = lines.concat(wr.lines);
        }
      });
    } else {
      lines = preLines;
    }

    if (lines.length === 0) {
      _textEl.style.opacity = '0';
      return;
    }

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
  let _fontsInjected = false;
  async function _injectBundledFonts() {
    if (_fontsInjected) return;
    _fontsInjected = true;
    try {
      const r = await fetch(`${_apiBase}/api/fonts`);
      if (!r.ok) return;
      const data = await r.json();
      const fonts = (data && data.fonts) || [];
      if (!fonts.length) return;
      const styleEl = document.createElement('style');
      styleEl.id = 'font-preview-bundled-faces';
      styleEl.textContent = fonts.map(f => {
        const url = `${_apiBase}/fonts/${encodeURIComponent(f.file)}`;
        const fmt = f.file.toLowerCase().endsWith('.otf') ? 'opentype' : 'truetype';
        // font-display:block holds rendering until the font loads (matters
        // because we draw the overlay immediately on segment switch and a
        // fallback flash would reveal the wrong glyph).
        return `@font-face{font-family:'${f.family}';src:url('${url}') format('${fmt}');font-display:block;}`;
      }).join('\n');
      document.head.appendChild(styleEl);

      // Eagerly load each face so the first overlay paint already has the
      // glyph in cache; otherwise the very first segment can flash with
      // fallback metrics for one frame.
      if (document.fonts && document.fonts.load) {
        await Promise.all(fonts.map(f =>
          document.fonts.load(`16px '${f.family}'`).catch(() => {})
        ));
        if (_font) applyFontConfig(_font);  // re-paint with correct metrics
      }
    } catch (err) {
      console.warn('[FontPreview] Failed to load bundled fonts:', err);
    }
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

  return { init, updateText, applyFontConfig };
})();
