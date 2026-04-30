// frontend/js/subtitle-wrap.js
// Pure ZH subtitle line-wrap algorithm. Mirror of backend/subtitle_wrap.py.
// Exposes window.SubtitleWrap.wrapZh + window.SubtitleWrap.wrapWithConfig

(function () {
  "use strict";

  const HARD_BREAKS = "。！？!?";
  const SOFT_BREAKS = "，、；：,;:";
  const PAREN_CLOSE = "）」』)]";
  const PAREN_OPEN = "（「『([";

  const PRESETS = {
    netflix_originals: { line_cap: 16, max_lines: 2, tail_tolerance: 2 },
    netflix_general:   { line_cap: 23, max_lines: 2, tail_tolerance: 3 },
    broadcast:         { line_cap: 28, max_lines: 3, tail_tolerance: 3 },
  };
  const DEFAULT_PRESET = "broadcast";

  function findBreak(remaining, cap, tailTolerance) {
    let best = -1;
    let bestScore = -1;
    const primaryLimit = Math.min(cap, remaining.length);
    const extendedLimit = Math.min(cap + tailTolerance, remaining.length);

    for (let i = 1; i <= primaryLimit; i++) {
      const ch = remaining[i - 1];
      let score = 0;
      if (HARD_BREAKS.includes(ch)) score = 100;
      else if (SOFT_BREAKS.includes(ch)) score = 50;
      else if (PAREN_CLOSE.includes(ch)) score = 30;
      else if (i < remaining.length && PAREN_OPEN.includes(remaining[i])) score = 25;
      if (score > 0) {
        score += i;
        if (score > bestScore) {
          bestScore = score;
          best = i;
        }
      }
    }
    if (best !== -1) return best;

    for (let i = primaryLimit + 1; i <= extendedLimit; i++) {
      const ch = remaining[i - 1];
      if (HARD_BREAKS.includes(ch) || SOFT_BREAKS.includes(ch)) return i;
    }
    return -1;
  }

  function wrapZh(text, options) {
    const cap = (options && options.cap) || 23;
    const maxLines = (options && options.maxLines) || 3;
    const tailTolerance = (options && options.tailTolerance != null) ? options.tailTolerance : 3;

    const trimmed = (text || "").trim();
    if (!trimmed) return { lines: [], hardCut: false };
    if (trimmed.length <= cap + tailTolerance) return { lines: [trimmed], hardCut: false };

    const lines = [];
    let remaining = trimmed;
    let hardCut = false;

    while (remaining && lines.length < maxLines) {
      if (remaining.length <= cap + tailTolerance) {
        lines.push(remaining);
        remaining = "";
        break;
      }
      let best = findBreak(remaining, cap, tailTolerance);
      if (best === -1) {
        best = cap;
        hardCut = true;
      }
      lines.push(remaining.slice(0, best).replace(/\s+$/, ""));
      remaining = remaining.slice(best).replace(/^\s+/, "");
    }

    if (remaining && lines.length > 0) {
      lines[lines.length - 1] = lines[lines.length - 1] + remaining;
    }

    return { lines, hardCut };
  }

  function resolveWrapConfig(fontConfig) {
    fontConfig = fontConfig || {};
    const standard = fontConfig.subtitle_standard;
    const base = Object.assign({}, PRESETS[standard] || PRESETS[DEFAULT_PRESET]);
    const explicit = fontConfig.line_wrap || {};
    const enabled = explicit.enabled != null ? explicit.enabled : true;
    base.enabled = enabled;
    if (explicit.line_cap != null) base.line_cap = explicit.line_cap;
    if (explicit.max_lines != null) base.max_lines = explicit.max_lines;
    if (explicit.tail_tolerance != null) base.tail_tolerance = explicit.tail_tolerance;
    return base;
  }

  function wrapWithConfig(text, fontConfig) {
    const cfg = resolveWrapConfig(fontConfig);
    if (!cfg.enabled) {
      const trimmed = (text || "").trim();
      return { lines: trimmed ? [trimmed] : [], hardCut: false };
    }
    return wrapZh(text, {
      cap: cfg.line_cap,
      maxLines: cfg.max_lines,
      tailTolerance: cfg.tail_tolerance,
    });
  }

  window.SubtitleWrap = { wrapZh, wrapWithConfig, resolveWrapConfig, PRESETS };
})();
