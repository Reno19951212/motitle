// frontend/js/subtitle-wrap.js
// Subtitle line-wrap algorithm. Mirror of backend/subtitle_wrap.py (Option D).
// Exposes window.SubtitleWrap.wrapZh + wrapEn + wrapWithConfig + resolveWrapConfig + isZhText + PRESETS

(function () {
  "use strict";

  const HARD_BREAKS = "。！？!?";
  const SOFT_BREAKS = "，、；：,;:";
  const PAREN_CLOSE = "）」』)]";
  const PAREN_OPEN = "（「『([";

  const EN_HARD = ".!?";
  const EN_SOFT = ",;:";
  const EN_CONNECTORS = new Set([
    "and", "but", "or", "nor", "so", "yet", "when", "after", "before",
    "while", "because", "although", "since", "though", "if", "unless",
    "until", "as",
  ]);
  const EN_PREPOSITIONS = new Set([
    "to", "of", "in", "on", "at", "with", "for", "from", "by", "into",
    "onto", "upon", "about", "between", "through", "over", "under", "against",
  ]);

  const HAS_ZH = /[一-鿿　-〿＀-￯]/;

  function isZhText(text) {
    return HAS_ZH.test(text || "");
  }

  const PRESETS = {
    netflix_originals: {
      zh: { line_cap: 16, max_lines: 2, tail_tolerance: 2 },
      en: { line_cap: 42, max_lines: 2, tail_tolerance: 4 },
    },
    netflix_general: {
      zh: { line_cap: 23, max_lines: 2, tail_tolerance: 3 },
      en: { line_cap: 42, max_lines: 2, tail_tolerance: 4 },
    },
    broadcast: {
      zh: { line_cap: 28, max_lines: 3, tail_tolerance: 3 },
      en: { line_cap: 50, max_lines: 3, tail_tolerance: 5 },
    },
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

  function isTitlecaseWord(word) {
    const stripped = (word || "").replace(/[^\w]/g, "");
    if (!stripped) return false;
    if (stripped.length === 1) return /[A-Z]/.test(stripped[0]);
    return /[A-Z]/.test(stripped[0]) && stripped.slice(1) === stripped.slice(1).toLowerCase();
  }

  function detectTitlecasePairs(words) {
    const pairs = new Set();
    for (let i = 1; i < words.length; i++) {
      const prev = words[i - 1];
      if (prev && EN_HARD.includes(prev[prev.length - 1])) continue;
      if (isTitlecaseWord(prev) && isTitlecaseWord(words[i])) pairs.add(i);
    }
    return pairs;
  }

  function remainingFits(words, start, linesLeft, cap, tailTolerance) {
    if (start >= words.length) return true;
    if (linesLeft <= 0) return false;
    const budget = cap + tailTolerance;
    let used = 0;
    let cur = 0;
    for (let k = start; k < words.length; k++) {
      const wl = words[k].length;
      if (cur === 0) {
        cur = wl;
      } else if (cur + 1 + wl <= budget) {
        cur += 1 + wl;
      } else {
        used++;
        cur = wl;
        if (used >= linesLeft) return false;
      }
    }
    return used + (cur > 0 ? 1 : 0) <= linesLeft;
  }

  function wrapEn(text, options) {
    const cap = (options && options.cap) || 42;
    const maxLines = (options && options.maxLines) || 2;
    const tailTolerance = (options && options.tailTolerance != null) ? options.tailTolerance : 4;

    const trimmed = (text || "").trim();
    if (!trimmed) return { lines: [], hardCut: false };
    if (trimmed.length <= cap + tailTolerance) return { lines: [trimmed], hardCut: false };

    const words = trimmed.split(/\s+/);
    const lockedPairs = detectTitlecasePairs(words);
    const lines = [];
    let i = 0;
    let hardCut = false;

    while (i < words.length && lines.length < maxLines) {
      if (lines.length === maxLines - 1) {
        lines.push(words.slice(i).join(" "));
        i = words.length;
        break;
      }

      let bestJ = -1;
      let bestScore = -Infinity;
      let curLen = 0;
      let latestFittingJ = i + 1;

      for (let j = i; j < words.length; j++) {
        const wl = words[j].length;
        const newLen = curLen + (j > i ? 1 : 0) + wl;
        if (newLen > cap + tailTolerance) {
          if (j === i) {
            curLen = wl;
            latestFittingJ = i + 1;
          }
          break;
        }
        curLen = newLen;
        latestFittingJ = j + 1;

        if (j + 1 >= words.length) continue;

        const distance = Math.abs(curLen - cap);
        let score = 10;
        const lastCh = words[j].length ? words[j][words[j].length - 1] : "";
        if (EN_HARD.includes(lastCh)) score = 100;
        else if (EN_SOFT.includes(lastCh)) score = 70;

        const nxtClean = words[j + 1].replace(/[^\w]/g, "").toLowerCase();
        if (EN_CONNECTORS.has(nxtClean)) score = Math.max(score, 50);
        else if (EN_PREPOSITIONS.has(nxtClean)) score = Math.max(score, 30);

        if (lockedPairs.has(j + 1)) score -= 80;
        score -= distance * 2;

        const linesLeft = maxLines - lines.length - 1;
        if (!remainingFits(words, j + 1, linesLeft, cap, tailTolerance)) continue;

        if (score > bestScore) {
          bestScore = score;
          bestJ = j + 1;
        }
      }

      if (bestJ <= i) {
        bestJ = latestFittingJ;
        const linesLeft = maxLines - lines.length - 1;
        if (!remainingFits(words, bestJ, linesLeft, cap, tailTolerance)) hardCut = true;
      }

      lines.push(words.slice(i, bestJ).join(" "));
      i = bestJ;
    }

    if (i < words.length && lines.length > 0) {
      lines[lines.length - 1] = lines[lines.length - 1] + " " + words.slice(i).join(" ");
    }

    if (lines.some(l => l.length > cap + tailTolerance)) hardCut = true;
    return { lines, hardCut };
  }

  function resolveWrapConfig(fontConfig) {
    fontConfig = fontConfig || {};
    const standard = fontConfig.subtitle_standard;
    const basePreset = PRESETS[standard] || PRESETS[DEFAULT_PRESET];
    const zhCfg = Object.assign({}, basePreset.zh);
    const enCfg = Object.assign({}, basePreset.en);
    const explicit = fontConfig.line_wrap || {};
    const enabled = explicit.enabled != null ? explicit.enabled : true;
    // Explicit overrides apply to BOTH sub-configs (legacy single-cap compat)
    ["line_cap", "max_lines", "tail_tolerance"].forEach(key => {
      if (explicit[key] != null) {
        zhCfg[key] = explicit[key];
        enCfg[key] = explicit[key];
      }
    });
    return { enabled, zh: zhCfg, en: enCfg };
  }

  function wrapWithConfig(text, fontConfig) {
    const cfg = resolveWrapConfig(fontConfig);
    if (!cfg.enabled) {
      const trimmed = (text || "").trim();
      return { lines: trimmed ? [trimmed] : [], hardCut: false };
    }
    const sub = isZhText(text) ? cfg.zh : cfg.en;
    if (isZhText(text)) {
      return wrapZh(text, {
        cap: sub.line_cap,
        maxLines: sub.max_lines,
        tailTolerance: sub.tail_tolerance,
      });
    }
    return wrapEn(text, {
      cap: sub.line_cap,
      maxLines: sub.max_lines,
      tailTolerance: sub.tail_tolerance,
    });
  }

  window.SubtitleWrap = { wrapZh, wrapEn, wrapWithConfig, resolveWrapConfig, isZhText, PRESETS };
})();
