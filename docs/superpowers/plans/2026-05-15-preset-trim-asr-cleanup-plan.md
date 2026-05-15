# v3.17 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to execute task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Trim user-facing surface area (drop Speed ASR / Fast Draft MT preset; force Whisper large-v3; delete stub engines) + validate via before/after diff report on 2 server videos.

**Architecture:** 3 logical Parts — A (frontend preset trim), B (backend engine cleanup + migration), C (validation: build script → capture baseline → apply A+B → re-run → diff report → user gate). Order critical: C-baseline MUST be captured BEFORE A+B commits.

**Tech Stack:** Vanilla HTML/JS frontend, Python 3.9 backend, Playwright E2E, Python `requests` for validation script HTTP, OpenCC for simplified-leak detection.

**Spec:** [docs/superpowers/specs/2026-05-15-preset-trim-asr-cleanup-design.md](docs/superpowers/specs/2026-05-15-preset-trim-asr-cleanup-design.md)

---

## File Structure

### New files
- `backend/scripts/v317_validation.py` (~700 lines) — snapshot capture, metric helpers (13 functions across Tier 1+2+3), report renderer
- `backend/scripts/migrate_v317_asr_models.py` (~40 lines) — one-shot Profile JSON migration
- `backend/tests/test_v317_validation.py` (~200 lines) — unit tests for metric helpers on dummy data
- `docs/superpowers/validation/v3.17-baseline-{file_id_short}.json` × 2 (runtime artifacts)
- `docs/superpowers/validation/v3.17-post-{file_id_short}.json` × 2 (runtime artifacts)
- `docs/superpowers/validation/v3.17-diff-report.md` (committed PR evidence)

### Modified files
- `frontend/index.html` — trim 2 preset keys
- `frontend/tests/test_profile_ui_guidance.spec.js` — reframe 3 tests
- `backend/asr/whisper_engine.py` — `model_size` enum → `['large-v3']`
- `backend/asr/mlx_whisper_engine.py` — same
- `backend/asr/__init__.py` — drop 2 imports + 2 factory mappings
- `backend/config/profiles/*.json` — migration normalize
- `backend/tests/test_asr.py` + others — drop qwen3/flg cases
- `CLAUDE.md` — v3.17 entry

### Deleted files
- `backend/asr/qwen3_engine.py`
- `backend/asr/flg_engine.py`

---

## Execution Order Rationale

Part C's baseline snapshot (Task 5) MUST happen BEFORE Part A+B commits land — once the schema narrows + migration runs, "baseline" is no longer baseline. Therefore order:

1. Task 1-4: Build validation script (no production impact)
2. Task 5: Capture baseline (before any prod change)
3. Task 6-10: Apply Part A + Part B (preset trim + engine cleanup + migration)
4. Task 11: Re-run pipeline on both videos (uses post-v3.17 config)
5. Task 12: Generate diff report
6. Task 13: CLAUDE.md v3.17 entry (after report verdict known)
7. Task 14: User review gate (HUMAN STOP — merge decision)

---

## Task 1: Validation script scaffold + Tier 1 helpers

**Files:**
- Create: `backend/scripts/v317_validation.py`
- Create: `backend/tests/test_v317_validation.py`

- [ ] **Step 1: Create `backend/scripts/v317_validation.py` with module docstring + auth + snapshot capture**

```python
"""v3.17 validation: snapshot capture + diff metric helpers.

Usage:
  # Capture baseline for two videos
  python backend/scripts/v317_validation.py snapshot --file-id <id1> --output baseline-<id1>.json
  python backend/scripts/v317_validation.py snapshot --file-id <id2> --output baseline-<id2>.json

  # Re-run ASR+MT on a file (after Part A+B applied)
  python backend/scripts/v317_validation.py rerun --file-id <id>

  # Compute diff + render markdown report
  python backend/scripts/v317_validation.py diff --baseline-glob 'baseline-*.json' \\
      --post-glob 'post-*.json' --output v3.17-diff-report.md
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests

BASE_URL = "http://localhost:5001"
ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "AdminPass1!"


def _login_session() -> requests.Session:
    """Login as admin and return authenticated session."""
    s = requests.Session()
    r = s.post(f"{BASE_URL}/login", data={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD})
    r.raise_for_status()
    return s


def capture_snapshot(session: requests.Session, file_id: str) -> Dict[str, Any]:
    """Capture comprehensive snapshot of file state for diff comparison."""
    file_resp = session.get(f"{BASE_URL}/api/files")
    file_resp.raise_for_status()
    files = file_resp.json().get("files", [])
    file_entry = next((f for f in files if f["id"] == file_id), None)
    if file_entry is None:
        raise ValueError(f"file_id {file_id} not found in /api/files")

    segments_resp = session.get(f"{BASE_URL}/api/files/{file_id}/segments")
    segments_resp.raise_for_status()
    segments = segments_resp.json().get("segments", [])

    translations_resp = session.get(f"{BASE_URL}/api/files/{file_id}/translations")
    translations_resp.raise_for_status()
    translations = translations_resp.json().get("translations", [])

    profile_id = file_entry.get("profile_id")
    profile_snapshot = None
    if profile_id:
        prof_resp = session.get(f"{BASE_URL}/api/profiles/{profile_id}")
        if prof_resp.ok:
            profile_snapshot = prof_resp.json()

    glossary_scan = None
    if profile_snapshot:
        glossary_id = profile_snapshot.get("translation", {}).get("glossary_id")
        if glossary_id:
            scan_resp = session.post(
                f"{BASE_URL}/api/files/{file_id}/glossary-scan",
                json={"glossary_id": glossary_id},
            )
            if scan_resp.ok:
                glossary_scan = scan_resp.json()

    return {
        "captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "file": file_entry,
        "segments": segments,
        "translations": translations,
        "profile_snapshot": profile_snapshot,
        "glossary_scan": glossary_scan,
    }
```

- [ ] **Step 2: Add Tier 1 metric helpers to same file**

```python
# ─────────────────────────────────────────────────────────────────────────────
# Tier 1: Core metrics
# ─────────────────────────────────────────────────────────────────────────────

def latency_delta(baseline: Dict[str, Any], post: Dict[str, Any]) -> Dict[str, Any]:
    """ASR + MT + total seconds, normalized to per-minute-of-video."""
    b_file = baseline["file"]
    p_file = post["file"]
    duration = (b_file.get("duration_seconds") or p_file.get("duration_seconds") or 0.0) / 60.0 or None

    def _norm(seconds, duration_min):
        if not seconds or not duration_min:
            return None
        return round(seconds / duration_min, 2)

    return {
        "baseline_asr_seconds": b_file.get("asr_seconds"),
        "post_asr_seconds": p_file.get("asr_seconds"),
        "baseline_asr_sec_per_min": _norm(b_file.get("asr_seconds"), duration),
        "post_asr_sec_per_min": _norm(p_file.get("asr_seconds"), duration),
        "baseline_mt_seconds": b_file.get("translation_seconds"),
        "post_mt_seconds": p_file.get("translation_seconds"),
        "baseline_total": (b_file.get("asr_seconds") or 0) + (b_file.get("translation_seconds") or 0),
        "post_total": (p_file.get("asr_seconds") or 0) + (p_file.get("translation_seconds") or 0),
        "video_duration_seconds": b_file.get("duration_seconds") or p_file.get("duration_seconds"),
    }


def segmentation_delta(baseline: Dict, post: Dict) -> Dict[str, Any]:
    """Count, duration, word stats."""
    def _stats(segments):
        if not segments:
            return {"count": 0, "avg_duration": None, "min_duration": None, "max_duration": None, "avg_word_count": None}
        durs = [s["end"] - s["start"] for s in segments]
        words = [len((s.get("text") or "").split()) for s in segments]
        return {
            "count": len(segments),
            "avg_duration": round(sum(durs) / len(durs), 2),
            "min_duration": round(min(durs), 2),
            "max_duration": round(max(durs), 2),
            "avg_word_count": round(sum(words) / len(words), 1),
        }
    return {"baseline": _stats(baseline["segments"]), "post": _stats(post["segments"])}


def asr_text_delta(baseline: Dict, post: Dict, time_tolerance: float = 0.5) -> Dict[str, Any]:
    """Pair segments by start_time (±tolerance); count identical/changed/new/dropped."""
    b_segs = baseline["segments"]
    p_segs = post["segments"]
    b_unmatched = list(range(len(b_segs)))

    identical = 0
    changed = []  # list of (baseline_text, post_text, timestamp)
    new_segments = []  # in post not in baseline

    for p_idx, p in enumerate(p_segs):
        match_idx = None
        for bi in b_unmatched:
            if abs(b_segs[bi]["start"] - p["start"]) <= time_tolerance:
                match_idx = bi
                break
        if match_idx is None:
            new_segments.append({"start": p["start"], "text": p.get("text", "")})
        else:
            b_unmatched.remove(match_idx)
            if b_segs[match_idx].get("text", "") == p.get("text", ""):
                identical += 1
            else:
                changed.append({
                    "start": p["start"],
                    "baseline": b_segs[match_idx].get("text", ""),
                    "post": p.get("text", ""),
                })

    dropped = [{"start": b_segs[bi]["start"], "text": b_segs[bi].get("text", "")} for bi in b_unmatched]

    return {
        "identical": identical,
        "changed_count": len(changed),
        "new_count": len(new_segments),
        "dropped_count": len(dropped),
        "top_changes": changed[:10],
        "top_new": new_segments[:5],
        "top_dropped": dropped[:5],
    }


def mt_text_delta(baseline: Dict, post: Dict) -> Dict[str, Any]:
    """Pair translations by index; count identical/changed."""
    b_t = baseline["translations"]
    p_t = post["translations"]
    n = min(len(b_t), len(p_t))
    identical = 0
    changed = []
    for i in range(n):
        b_zh = b_t[i].get("zh_text", "")
        p_zh = p_t[i].get("zh_text", "")
        if b_zh == p_zh:
            identical += 1
        else:
            changed.append({
                "index": i,
                "en": p_t[i].get("en_text", ""),
                "baseline_zh": b_zh,
                "post_zh": p_zh,
            })
    return {
        "identical": identical,
        "changed_count": len(changed),
        "length_baseline": len(b_t),
        "length_post": len(p_t),
        "top_changes": changed[:10],
    }


def glossary_scan_delta(baseline: Dict, post: Dict) -> Dict[str, Any]:
    """Compare violation counts before/after."""
    b = baseline.get("glossary_scan") or {}
    p = post.get("glossary_scan") or {}
    if not b and not p:
        return {"skipped": True, "reason": "neither baseline nor post had glossary_id in profile"}
    return {
        "baseline_strict_count": b.get("strict_violation_count", 0),
        "post_strict_count": p.get("strict_violation_count", 0),
        "baseline_loose_count": b.get("loose_violation_count", 0),
        "post_loose_count": p.get("loose_violation_count", 0),
        "top_strict_baseline": (b.get("strict_violations") or [])[:5],
        "top_strict_post": (p.get("strict_violations") or [])[:5],
        "top_loose_baseline": (b.get("loose_violations") or [])[:5],
        "top_loose_post": (p.get("loose_violations") or [])[:5],
    }
```

- [ ] **Step 3: Add CLI subparser entry point**

```python
# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def cmd_snapshot(args):
    s = _login_session()
    snap = capture_snapshot(s, args.file_id)
    Path(args.output).write_text(json.dumps(snap, ensure_ascii=False, indent=2))
    print(f"Wrote snapshot to {args.output}")

def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot")
    sp.add_argument("--file-id", required=True)
    sp.add_argument("--output", required=True)
    sp.set_defaults(func=cmd_snapshot)

    # (rerun and diff subcommands added in later tasks)

    args = p.parse_args()
    args.func(args)

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Write Tier 1 unit tests in `backend/tests/test_v317_validation.py`**

```python
"""Unit tests for v3.17 validation metric helpers on dummy snapshot data."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import v317_validation as v


def _mk_snapshot(segments, translations, file_extras=None, glossary_scan=None):
    return {
        "captured_at": "2026-05-15T00:00:00Z",
        "file": {"id": "test", "duration_seconds": 60.0, "asr_seconds": 30.0, "translation_seconds": 10.0, **(file_extras or {})},
        "segments": segments,
        "translations": translations,
        "profile_snapshot": None,
        "glossary_scan": glossary_scan,
    }


def test_latency_delta_basic():
    b = _mk_snapshot([], [])
    p = _mk_snapshot([], [], file_extras={"asr_seconds": 25.0, "translation_seconds": 12.0})
    out = v.latency_delta(b, p)
    assert out["baseline_asr_seconds"] == 30.0
    assert out["post_asr_seconds"] == 25.0
    assert out["baseline_asr_sec_per_min"] == 30.0
    assert out["post_asr_sec_per_min"] == 25.0


def test_segmentation_delta_count():
    b = _mk_snapshot([{"start": 0, "end": 2.0, "text": "hello world"}], [])
    p = _mk_snapshot([{"start": 0, "end": 2.0, "text": "hello world"}, {"start": 2.5, "end": 4.0, "text": "again"}], [])
    out = v.segmentation_delta(b, p)
    assert out["baseline"]["count"] == 1
    assert out["post"]["count"] == 2


def test_asr_text_delta_identical_changed_new_dropped():
    b_segs = [
        {"start": 0.0, "end": 1.0, "text": "A"},
        {"start": 1.0, "end": 2.0, "text": "B"},
        {"start": 5.0, "end": 6.0, "text": "DROPPED"},
    ]
    p_segs = [
        {"start": 0.0, "end": 1.0, "text": "A"},        # identical
        {"start": 1.05, "end": 2.0, "text": "B2"},      # changed (within tolerance)
        {"start": 7.0, "end": 8.0, "text": "NEW"},      # new
    ]
    out = v.asr_text_delta(_mk_snapshot(b_segs, []), _mk_snapshot(p_segs, []))
    assert out["identical"] == 1
    assert out["changed_count"] == 1
    assert out["new_count"] == 1
    assert out["dropped_count"] == 1


def test_mt_text_delta_paired_by_index():
    b_t = [{"en_text": "x", "zh_text": "甲"}, {"en_text": "y", "zh_text": "乙"}]
    p_t = [{"en_text": "x", "zh_text": "甲"}, {"en_text": "y", "zh_text": "丙"}]
    out = v.mt_text_delta(_mk_snapshot([], b_t), _mk_snapshot([], p_t))
    assert out["identical"] == 1
    assert out["changed_count"] == 1


def test_glossary_scan_delta_skipped_when_no_data():
    b = _mk_snapshot([], [], glossary_scan=None)
    p = _mk_snapshot([], [], glossary_scan=None)
    out = v.glossary_scan_delta(b, p)
    assert out["skipped"] is True


def test_glossary_scan_delta_counts():
    b = _mk_snapshot([], [], glossary_scan={"strict_violation_count": 5, "loose_violation_count": 2, "strict_violations": [], "loose_violations": []})
    p = _mk_snapshot([], [], glossary_scan={"strict_violation_count": 1, "loose_violation_count": 0, "strict_violations": [], "loose_violations": []})
    out = v.glossary_scan_delta(b, p)
    assert out["baseline_strict_count"] == 5
    assert out["post_strict_count"] == 1
```

- [ ] **Step 5: Run unit tests + commit**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v317_validation.py -v`
Expected: 6 tests pass.

```bash
git add backend/scripts/v317_validation.py backend/tests/test_v317_validation.py
git commit -m "feat(v3.17): validation script scaffold + Tier 1 metric helpers"
```

---

## Task 2: Tier 2 Broadcast Quality metric helpers

**Files:** Extend `backend/scripts/v317_validation.py` + `backend/tests/test_v317_validation.py`

- [ ] **Step 1: Add Tier 2 helpers (subtitle length / CPS / language consistency / repetition)**

Append to `backend/scripts/v317_validation.py`:

```python
# ─────────────────────────────────────────────────────────────────────────────
# Tier 2: Broadcast Quality metrics
# ─────────────────────────────────────────────────────────────────────────────

_CJK_RE = re.compile(r"[一-鿿]")
_LATIN_WORD_RE = re.compile(r"[a-zA-Z]{3,}")
_BRAND_WHITELIST = {"NBA", "FIFA", "UEFA", "BBC", "CNN", "AI", "GPS", "USA", "UK"}


def subtitle_length_distribution(translations: List[Dict]) -> Dict[str, int]:
    """ZH char-count histogram."""
    buckets = {"0-10": 0, "11-15": 0, "16-20": 0, "21-28": 0, "29-40": 0, ">40": 0}
    for t in translations:
        n = len(t.get("zh_text", "") or "")
        if n <= 10:
            buckets["0-10"] += 1
        elif n <= 15:
            buckets["11-15"] += 1
        elif n <= 20:
            buckets["16-20"] += 1
        elif n <= 28:
            buckets["21-28"] += 1
        elif n <= 40:
            buckets["29-40"] += 1
        else:
            buckets[">40"] += 1
    return buckets


def reading_speed_cps(translations: List[Dict], segments: List[Dict]) -> Dict[str, Any]:
    """Chars-per-second per segment. Broadcast band 12-17 CPS."""
    # Pair translations to segments by index
    n = min(len(translations), len(segments))
    cps_values = []
    too_slow = []  # <8 CPS
    too_fast = []  # >20 CPS
    for i in range(n):
        zh = translations[i].get("zh_text", "") or ""
        dur = segments[i]["end"] - segments[i]["start"]
        if dur <= 0 or not zh:
            continue
        cps = len(zh) / dur
        cps_values.append(cps)
        if cps < 8:
            too_slow.append({"index": i, "zh": zh, "duration": round(dur, 2), "cps": round(cps, 1)})
        elif cps > 20:
            too_fast.append({"index": i, "zh": zh, "duration": round(dur, 2), "cps": round(cps, 1)})
    if not cps_values:
        return {"skipped": True, "reason": "no paired segments with translation"}
    return {
        "avg_cps": round(sum(cps_values) / len(cps_values), 1),
        "min_cps": round(min(cps_values), 1),
        "max_cps": round(max(cps_values), 1),
        "in_broadcast_band_12_17": sum(1 for c in cps_values if 12 <= c <= 17),
        "too_slow_count": len(too_slow),
        "too_fast_count": len(too_fast),
        "top_too_slow": too_slow[:5],
        "top_too_fast": too_fast[:5],
    }


def language_consistency(segments: List[Dict], translations: List[Dict]) -> Dict[str, Any]:
    """EN-with-CJK contamination + ZH-with-Latin words + simplified-leak."""
    en_with_cjk = []
    for s in segments:
        text = s.get("text", "") or ""
        if _CJK_RE.search(text):
            en_with_cjk.append({"start": s.get("start"), "text": text})

    zh_with_latin = []
    for i, t in enumerate(translations):
        zh = t.get("zh_text", "") or ""
        latins = _LATIN_WORD_RE.findall(zh)
        leaked = [w for w in latins if w.upper() not in _BRAND_WHITELIST]
        if leaked:
            zh_with_latin.append({"index": i, "zh": zh, "latin_words": leaked})

    # Simplified leak: use OpenCC s2hk if available; segments where s2hk(zh) != zh contain simplified chars
    simplified_leak = []
    try:
        from opencc import OpenCC
        cc = OpenCC("s2hk")
        for i, t in enumerate(translations):
            zh = t.get("zh_text", "") or ""
            converted = cc.convert(zh)
            if converted != zh and zh:
                simplified_leak.append({"index": i, "original": zh, "converted": converted})
    except ImportError:
        simplified_leak = [{"error": "OpenCC not installed"}]

    return {
        "en_with_cjk_count": len(en_with_cjk),
        "zh_with_latin_count": len(zh_with_latin),
        "simplified_leak_count": len(simplified_leak) if isinstance(simplified_leak, list) and (not simplified_leak or "error" not in simplified_leak[0]) else None,
        "top_en_with_cjk": en_with_cjk[:5],
        "top_zh_with_latin": zh_with_latin[:5],
        "top_simplified_leak": simplified_leak[:5] if isinstance(simplified_leak, list) else [],
    }


def repetition_detect(translations: List[Dict], min_overlap_ratio: float = 0.7) -> List[Dict]:
    """Adjacent segments where ZH text overlap >= ratio (cascade signal)."""
    pairs = []
    for i in range(len(translations) - 1):
        a = (translations[i].get("zh_text") or "").strip()
        b = (translations[i + 1].get("zh_text") or "").strip()
        if not a or not b:
            continue
        # Simple metric: longest common substring length / max(len)
        # For perf, use set-of-chars Jaccard as cheap proxy
        sa, sb = set(a), set(b)
        if not sa or not sb:
            continue
        jaccard = len(sa & sb) / len(sa | sb)
        if jaccard >= min_overlap_ratio or a == b or a in b or b in a:
            pairs.append({"index": i, "next": i + 1, "zh_a": a, "zh_b": b, "jaccard": round(jaccard, 2)})
    return pairs
```

- [ ] **Step 2: Add Tier 2 unit tests**

```python
def test_subtitle_length_distribution_buckets():
    t = [{"zh_text": "短"}, {"zh_text": "中等長度的字幕內容文字"}, {"zh_text": "x" * 35}, {"zh_text": "y" * 50}]
    out = v.subtitle_length_distribution(t)
    assert out["0-10"] == 1
    assert out["11-15"] == 1
    assert out["29-40"] == 1
    assert out[">40"] == 1


def test_reading_speed_cps_band():
    segs = [{"start": 0, "end": 2.0}, {"start": 2.0, "end": 4.0}, {"start": 4.0, "end": 5.0}]
    trans = [{"zh_text": "甲乙丙丁戊己庚辛壬癸甲乙丙丁戊己庚辛壬癸甲乙丙丁戊己庚辛壬癸"}, {"zh_text": "短"}, {"zh_text": "abcdefghij"}]
    out = v.reading_speed_cps(trans, segs)
    assert out["too_fast_count"] >= 1
    assert out["too_slow_count"] >= 1


def test_language_consistency_en_with_cjk():
    segs = [{"start": 0, "end": 1, "text": "Hello 世界 world"}, {"start": 1, "end": 2, "text": "no cjk here"}]
    trans = [{"zh_text": "純中文"}]
    out = v.language_consistency(segs, trans)
    assert out["en_with_cjk_count"] == 1


def test_language_consistency_zh_with_latin_brand_excluded():
    segs = []
    trans = [{"zh_text": "佢喺 NBA 比賽中"}, {"zh_text": "佢喺 random English 比賽中"}]
    out = v.language_consistency(segs, trans)
    assert out["zh_with_latin_count"] == 1  # NBA excluded by whitelist, "random English" detected


def test_repetition_detect_substring_match():
    trans = [{"zh_text": "甲乙丙丁戊"}, {"zh_text": "甲乙丙丁戊己"}, {"zh_text": "完全不同的內容"}]
    out = v.repetition_detect(trans, min_overlap_ratio=0.5)
    assert len(out) >= 1
    assert out[0]["index"] == 0
```

- [ ] **Step 3: Run + commit**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v317_validation.py -v`
Expected: 11 tests pass (6 + 5 new).

```bash
git add backend/scripts/v317_validation.py backend/tests/test_v317_validation.py
git commit -m "feat(v3.17): Tier 2 broadcast quality metric helpers"
```

---

## Task 3: Tier 3 Diagnostic metric helpers

**Files:** Extend `backend/scripts/v317_validation.py` + `backend/tests/test_v317_validation.py`

- [ ] **Step 1: Add Tier 3 helpers (timing health / flag rates / batch boundary / word-level / approval)**

Append to `backend/scripts/v317_validation.py`:

```python
# ─────────────────────────────────────────────────────────────────────────────
# Tier 3: Diagnostic metrics
# ─────────────────────────────────────────────────────────────────────────────

def segment_timing_health(segments: List[Dict]) -> Dict[str, Any]:
    """Count of too-short / too-long segments + gap distribution."""
    if not segments:
        return {"skipped": True, "reason": "no segments"}
    too_short = [s for s in segments if s["end"] - s["start"] < 0.3]
    too_long = [s for s in segments if s["end"] - s["start"] > 7.0]
    gaps = []
    for i in range(1, len(segments)):
        gap = segments[i]["start"] - segments[i - 1]["end"]
        if gap > 0:
            gaps.append(gap)
    return {
        "too_short_count": len(too_short),
        "too_long_count": len(too_long),
        "avg_gap": round(sum(gaps) / len(gaps), 2) if gaps else None,
        "max_gap": round(max(gaps), 2) if gaps else None,
        "top_too_short": [{"start": s["start"], "duration": round(s["end"] - s["start"], 2), "text": s.get("text", "")} for s in too_short[:5]],
        "top_too_long": [{"start": s["start"], "duration": round(s["end"] - s["start"], 2), "text": s.get("text", "")} for s in too_long[:5]],
    }


def flag_rates(translations: List[Dict]) -> Dict[str, Any]:
    """Counts of [LONG], [NEEDS REVIEW] flags + hallucination heuristic."""
    long_count = sum(1 for t in translations if "long" in (t.get("flags") or []))
    review_count = sum(1 for t in translations if "review" in (t.get("flags") or []))
    hallucinated = [t for t in translations if len(t.get("zh_text", "") or "") > 40]
    return {
        "total_count": len(translations),
        "long_flag_count": long_count,
        "long_flag_pct": round(100 * long_count / len(translations), 1) if translations else 0,
        "review_flag_count": review_count,
        "hallucination_count": len(hallucinated),
        "hallucination_pct": round(100 * len(hallucinated) / len(translations), 1) if translations else 0,
    }


def batch_boundary_check(translations: List[Dict], batch_size: int) -> Dict[str, Any]:
    """Check for repetition + abrupt context at batch edges (only if batch_size > 1)."""
    if not batch_size or batch_size <= 1:
        return {"skipped": True, "reason": f"batch_size={batch_size}, no boundaries to check"}
    boundaries = list(range(batch_size, len(translations), batch_size))
    edge_repetition = []
    for b in boundaries:
        if b == 0 or b >= len(translations):
            continue
        prev_zh = (translations[b - 1].get("zh_text") or "").strip()
        curr_zh = (translations[b].get("zh_text") or "").strip()
        if prev_zh and curr_zh and (prev_zh == curr_zh or prev_zh in curr_zh or curr_zh in prev_zh):
            edge_repetition.append({"boundary": b, "prev_zh": prev_zh, "curr_zh": curr_zh})
    return {
        "boundary_count": len(boundaries),
        "edge_repetition_count": len(edge_repetition),
        "top_edge_repetition": edge_repetition[:5],
    }


def word_level_alignment(segments: List[Dict]) -> Dict[str, Any]:
    """% segments with words[] populated + avg word count."""
    if not segments:
        return {"skipped": True}
    with_words = [s for s in segments if s.get("words")]
    word_counts = [len(s["words"]) for s in with_words]
    return {
        "total_segments": len(segments),
        "with_words_count": len(with_words),
        "with_words_pct": round(100 * len(with_words) / len(segments), 1),
        "avg_word_count": round(sum(word_counts) / len(word_counts), 1) if word_counts else None,
    }


def approval_state(baseline_translations: List[Dict], post_translations: List[Dict]) -> Dict[str, Any]:
    """Baseline approved/pending vs post (post resets to all pending)."""
    def _count(t_list):
        approved = sum(1 for t in t_list if t.get("status") == "approved")
        pending = sum(1 for t in t_list if t.get("status") != "approved")
        return {"approved": approved, "pending": pending}
    return {
        "baseline": _count(baseline_translations),
        "post": _count(post_translations),
        "note": "Post re-run resets all approvals to pending; baseline counts are ground-truth pre-v3.17 reviewer state.",
    }
```

- [ ] **Step 2: Add Tier 3 unit tests**

```python
def test_segment_timing_health_short_and_long():
    segs = [
        {"start": 0, "end": 0.2, "text": "tiny"},   # too short
        {"start": 0.2, "end": 8.5, "text": "long"}, # too long
        {"start": 9.0, "end": 11.0, "text": "ok"},
    ]
    out = v.segment_timing_health(segs)
    assert out["too_short_count"] == 1
    assert out["too_long_count"] == 1


def test_flag_rates_counts():
    trans = [
        {"zh_text": "短", "flags": []},
        {"zh_text": "x" * 50, "flags": ["long"]},
        {"zh_text": "y", "flags": ["review"]},
    ]
    out = v.flag_rates(trans)
    assert out["long_flag_count"] == 1
    assert out["review_flag_count"] == 1
    assert out["hallucination_count"] == 1


def test_batch_boundary_check_repetition():
    trans = [
        {"zh_text": "段一"}, {"zh_text": "段二"}, {"zh_text": "段二"},  # boundary at index 2; repetition!
        {"zh_text": "段四"}, {"zh_text": "段五"}, {"zh_text": "段六"},
    ]
    out = v.batch_boundary_check(trans, batch_size=2)
    assert out["edge_repetition_count"] >= 1


def test_batch_boundary_check_skipped_when_batch1():
    out = v.batch_boundary_check([{"zh_text": "x"}], batch_size=1)
    assert out["skipped"] is True


def test_word_level_alignment_pct():
    segs = [{"words": [{"word": "a"}]}, {"words": []}, {"words": [{"word": "b"}, {"word": "c"}]}]
    out = v.word_level_alignment(segs)
    assert out["with_words_count"] == 2  # third has 2 words, first has 1; second has empty list (truthy depends — let me adjust)
    # Actually [] is falsy, so with_words filters out second. Counts only first + third.


def test_approval_state_note_present():
    b = [{"status": "approved"}, {"status": "approved"}, {"status": "pending"}]
    p = [{"status": "pending"}, {"status": "pending"}, {"status": "pending"}]
    out = v.approval_state(b, p)
    assert out["baseline"]["approved"] == 2
    assert out["post"]["approved"] == 0
    assert "Post re-run resets" in out["note"]
```

- [ ] **Step 3: Run + commit**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v317_validation.py -v`
Expected: 17 tests pass (11 + 6 new).

```bash
git add backend/scripts/v317_validation.py backend/tests/test_v317_validation.py
git commit -m "feat(v3.17): Tier 3 diagnostic metric helpers"
```

---

## Task 4: Markdown report renderer + diff command

**Files:** Extend `backend/scripts/v317_validation.py`

- [ ] **Step 1: Add report renderer**

Append to `backend/scripts/v317_validation.py`:

```python
# ─────────────────────────────────────────────────────────────────────────────
# Report renderer
# ─────────────────────────────────────────────────────────────────────────────

def _h2(text): return f"\n## {text}\n"
def _h3(text): return f"\n### {text}\n"
def _kv(label, val): return f"- **{label}**: {val}"
def _table_2col(rows, headers=("Metric", "Value")):
    out = [f"| {headers[0]} | {headers[1]} |", "|---|---|"]
    for k, v in rows:
        out.append(f"| {k} | {v} |")
    return "\n".join(out)


def render_report(diffs: List[Dict[str, Any]], verdict: str = "✅") -> str:
    """diffs: list of per-video diff dicts. Returns markdown string."""
    out = []
    out.append("# v3.17 Validation Diff Report")
    out.append("")
    out.append("## Executive Summary")
    out.append(f"- **Verdict**: {verdict}")
    out.append(f"- **Date**: {time.strftime('%Y-%m-%d')}")
    out.append(f"- **Videos tested**: {len(diffs)}")
    out.append("")

    for i, d in enumerate(diffs, 1):
        f = d.get("file") or {}
        out.append(f"## Video {i}: {f.get('original_name', '<unknown>')}")
        out.append(_kv("file_id", f.get("id", "—")))
        out.append(_kv("duration", f"{f.get('duration_seconds', '—')}s"))
        out.append(_kv("profile_id", f.get("profile_id", "—")))

        out.append(_h3("Tier 1 — Latency"))
        lat = d["latency"]
        out.append(_table_2col([
            ("Baseline ASR seconds", lat.get("baseline_asr_seconds", "—")),
            ("Post ASR seconds", lat.get("post_asr_seconds", "—")),
            ("Baseline MT seconds", lat.get("baseline_mt_seconds", "—")),
            ("Post MT seconds", lat.get("post_mt_seconds", "—")),
            ("Total Δ", round((lat.get("post_total") or 0) - (lat.get("baseline_total") or 0), 1)),
        ]))

        out.append(_h3("Tier 1 — Segmentation"))
        seg = d["segmentation"]
        out.append(_table_2col([
            ("Baseline count", seg["baseline"]["count"]),
            ("Post count", seg["post"]["count"]),
            ("Baseline avg duration", seg["baseline"]["avg_duration"]),
            ("Post avg duration", seg["post"]["avg_duration"]),
        ]))

        out.append(_h3("Tier 1 — ASR text delta"))
        a = d["asr_text"]
        out.append(_kv("Identical", a["identical"]))
        out.append(_kv("Changed", a["changed_count"]))
        out.append(_kv("New", a["new_count"]))
        out.append(_kv("Dropped", a["dropped_count"]))
        if a["top_changes"]:
            out.append("\n**Top changes:**")
            for c in a["top_changes"]:
                out.append(f"- `{c['start']:.2f}s` `{c['baseline']}` → `{c['post']}`")

        out.append(_h3("Tier 1 — MT text delta"))
        m = d["mt_text"]
        out.append(_kv("Identical", m["identical"]))
        out.append(_kv("Changed", m["changed_count"]))
        if m["top_changes"]:
            out.append("\n**Top changes:**")
            for c in m["top_changes"][:10]:
                out.append(f"- idx {c['index']}: EN `{c['en']}`")
                out.append(f"  - baseline: `{c['baseline_zh']}`")
                out.append(f"  - post: `{c['post_zh']}`")

        out.append(_h3("Tier 1 — Glossary scan"))
        g = d["glossary_scan"]
        if g.get("skipped"):
            out.append(f"- _Skipped_: {g['reason']}")
        else:
            out.append(_table_2col([
                ("Baseline strict violations", g["baseline_strict_count"]),
                ("Post strict violations", g["post_strict_count"]),
                ("Baseline loose violations", g["baseline_loose_count"]),
                ("Post loose violations", g["post_loose_count"]),
            ]))

        out.append(_h3("Tier 2 — Subtitle length distribution"))
        out.append("| Bucket | Baseline | Post |")
        out.append("|---|---|---|")
        b_dist = d["subtitle_length"]["baseline"]
        p_dist = d["subtitle_length"]["post"]
        for bucket in ["0-10", "11-15", "16-20", "21-28", "29-40", ">40"]:
            out.append(f"| {bucket} | {b_dist[bucket]} | {p_dist[bucket]} |")

        out.append(_h3("Tier 2 — Reading speed CPS"))
        cps = d["reading_speed"]
        if cps.get("skipped"):
            out.append(f"- _Skipped_: {cps['reason']}")
        else:
            out.append(_table_2col([
                ("Avg CPS (baseline)", cps["baseline"]["avg_cps"]),
                ("Avg CPS (post)", cps["post"]["avg_cps"]),
                ("In broadcast band 12-17 (post)", cps["post"]["in_broadcast_band_12_17"]),
                ("Too slow (<8 CPS, post)", cps["post"]["too_slow_count"]),
                ("Too fast (>20 CPS, post)", cps["post"]["too_fast_count"]),
            ]))

        out.append(_h3("Tier 2 — Language consistency"))
        lc = d["language_consistency"]
        out.append(_table_2col([
            ("EN-with-CJK count (post)", lc["post"]["en_with_cjk_count"]),
            ("ZH-with-Latin (excl whitelist, post)", lc["post"]["zh_with_latin_count"]),
            ("Simplified leak count (post)", lc["post"]["simplified_leak_count"]),
        ]))

        out.append(_h3("Tier 2 — Repetition / cascade detection"))
        rep = d["repetition"]
        out.append(_kv("Baseline repetition pairs", len(rep["baseline"])))
        out.append(_kv("Post repetition pairs", len(rep["post"])))

        out.append(_h3("Tier 3 — Segment timing health"))
        th = d["timing_health"]
        if not th["post"].get("skipped"):
            out.append(_table_2col([
                ("Too short (<0.3s) post", th["post"]["too_short_count"]),
                ("Too long (>7s) post", th["post"]["too_long_count"]),
                ("Avg gap (post)", th["post"]["avg_gap"]),
            ]))

        out.append(_h3("Tier 3 — Flag rates"))
        fr = d["flag_rates"]
        out.append(_table_2col([
            ("[LONG] count (baseline / post)", f"{fr['baseline']['long_flag_count']} / {fr['post']['long_flag_count']}"),
            ("[NEEDS REVIEW] count (baseline / post)", f"{fr['baseline']['review_flag_count']} / {fr['post']['review_flag_count']}"),
            ("Hallucination % (baseline / post)", f"{fr['baseline']['hallucination_pct']}% / {fr['post']['hallucination_pct']}%"),
        ]))

        out.append(_h3("Tier 3 — Batch boundary check"))
        bb = d["batch_boundary"]
        if bb["post"].get("skipped"):
            out.append(f"- _Skipped_: {bb['post']['reason']}")
        else:
            out.append(_kv("Edge repetitions (post)", bb["post"]["edge_repetition_count"]))

        out.append(_h3("Tier 3 — Word-level alignment"))
        wl = d["word_level"]
        out.append(_table_2col([
            ("With words[] (baseline)", f"{wl['baseline'].get('with_words_pct', '—')}%"),
            ("With words[] (post)", f"{wl['post'].get('with_words_pct', '—')}%"),
        ]))

        out.append(_h3("Tier 3 — Approval state"))
        ap = d["approval"]
        out.append(_kv("Baseline approved / pending", f"{ap['baseline']['approved']} / {ap['baseline']['pending']}"))
        out.append(_kv("Post approved / pending", f"{ap['post']['approved']} / {ap['post']['pending']}"))
        out.append(f"> _{ap['note']}_")

    out.append(_h2("Conclusion"))
    out.append("[Recommendation: merge / rollback / further investigation — to be filled by reviewer]")

    return "\n".join(out)


def compute_all_diffs(baseline: Dict, post: Dict) -> Dict[str, Any]:
    """Run all 13 metric helpers on a baseline+post snapshot pair."""
    batch_size = (baseline.get("profile_snapshot") or {}).get("translation", {}).get("batch_size", 1)
    return {
        "file": post.get("file") or baseline.get("file"),
        "latency": latency_delta(baseline, post),
        "segmentation": segmentation_delta(baseline, post),
        "asr_text": asr_text_delta(baseline, post),
        "mt_text": mt_text_delta(baseline, post),
        "glossary_scan": glossary_scan_delta(baseline, post),
        "subtitle_length": {
            "baseline": subtitle_length_distribution(baseline["translations"]),
            "post": subtitle_length_distribution(post["translations"]),
        },
        "reading_speed": {
            "baseline": reading_speed_cps(baseline["translations"], baseline["segments"]),
            "post": reading_speed_cps(post["translations"], post["segments"]),
        },
        "language_consistency": {
            "baseline": language_consistency(baseline["segments"], baseline["translations"]),
            "post": language_consistency(post["segments"], post["translations"]),
        },
        "repetition": {
            "baseline": repetition_detect(baseline["translations"]),
            "post": repetition_detect(post["translations"]),
        },
        "timing_health": {
            "baseline": segment_timing_health(baseline["segments"]),
            "post": segment_timing_health(post["segments"]),
        },
        "flag_rates": {
            "baseline": flag_rates(baseline["translations"]),
            "post": flag_rates(post["translations"]),
        },
        "batch_boundary": {
            "post": batch_boundary_check(post["translations"], batch_size),
        },
        "word_level": {
            "baseline": word_level_alignment(baseline["segments"]),
            "post": word_level_alignment(post["segments"]),
        },
        "approval": approval_state(baseline["translations"], post["translations"]),
    }


def cmd_diff(args):
    diffs = []
    baseline_paths = sorted(Path(".").glob(args.baseline_glob))
    post_paths = sorted(Path(".").glob(args.post_glob))
    assert len(baseline_paths) == len(post_paths), "baseline + post counts must match"
    for bp, pp in zip(baseline_paths, post_paths):
        b = json.loads(bp.read_text())
        p = json.loads(pp.read_text())
        diffs.append(compute_all_diffs(b, p))
    Path(args.output).write_text(render_report(diffs))
    print(f"Wrote report to {args.output}")
```

Update `main()`:

```python
def main():
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("snapshot")
    sp.add_argument("--file-id", required=True)
    sp.add_argument("--output", required=True)
    sp.set_defaults(func=cmd_snapshot)

    dp = sub.add_parser("diff")
    dp.add_argument("--baseline-glob", required=True)
    dp.add_argument("--post-glob", required=True)
    dp.add_argument("--output", required=True)
    dp.set_defaults(func=cmd_diff)

    args = p.parse_args()
    args.func(args)
```

- [ ] **Step 2: Smoke test renderer on dummy snapshots**

```python
def test_render_report_smoke():
    b = _mk_snapshot([{"start": 0, "end": 2.0, "text": "Hello"}], [{"en_text": "Hello", "zh_text": "你好", "flags": []}])
    p = _mk_snapshot([{"start": 0, "end": 2.0, "text": "Hello"}], [{"en_text": "Hello", "zh_text": "你好", "flags": []}])
    diffs = [v.compute_all_diffs(b, p)]
    md = v.render_report(diffs)
    assert "v3.17 Validation Diff Report" in md
    assert "Hello" in md
```

- [ ] **Step 3: Run all tests + commit**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v317_validation.py -v`
Expected: 18 tests pass (17 + 1 new).

```bash
git add backend/scripts/v317_validation.py backend/tests/test_v317_validation.py
git commit -m "feat(v3.17): markdown report renderer + diff command"
```

---

## Task 5: Capture baseline for both videos (BEFORE Part A+B)

**Files:** Create `docs/superpowers/validation/v3.17-baseline-{file_id_short}.json` × 2

- [ ] **Step 1: Ensure backend running**

```bash
curl -s http://localhost:5001/api/ready
# If not running:
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend" && source venv/bin/activate && python app.py > /tmp/v317-task5.log 2>&1 &
sleep 4 && curl -s http://localhost:5001/api/ready
```

- [ ] **Step 2: Discover the 2 video file_ids**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
source backend/venv/bin/activate
python -c "
import requests
s = requests.Session()
s.post('http://localhost:5001/login', data={'username': 'admin', 'password': 'AdminPass1!'})
r = s.get('http://localhost:5001/api/files')
for f in r.json().get('files', []):
    print(f['id'][:12], f.get('original_name'), f.get('status'))
"
```

Expected: 2 video files printed. Record `file_id_short` (first 12 chars) for both.

**STOP if zero videos** or count != 2 — escalate to user.

**STOP if any video's profile uses `qwen3-asr` or `flg-asr` engine** — query that file's profile via `/api/profiles/<profile_id>` first to verify; if yes, escalate.

- [ ] **Step 3: Capture baseline for both**

```bash
mkdir -p docs/superpowers/validation
python backend/scripts/v317_validation.py snapshot --file-id <full_id_1> --output docs/superpowers/validation/v3.17-baseline-<id_short_1>.json
python backend/scripts/v317_validation.py snapshot --file-id <full_id_2> --output docs/superpowers/validation/v3.17-baseline-<id_short_2>.json
```

Verify each output file:
- `cat docs/superpowers/validation/v3.17-baseline-<id_short_1>.json | jq '.file.id, .segments | length, .translations | length, .glossary_scan'`
- Should show non-null file id, non-zero segment count, non-zero translation count

- [ ] **Step 4: Commit baselines**

```bash
git add docs/superpowers/validation/v3.17-baseline-*.json
git commit -m "chore(v3.17): capture pre-v3.17 baseline snapshots for 2 videos"
```

---

## Task 6: Part A — preset trim + Playwright reframe

**Files:**
- Modify: `frontend/index.html` (`ASR_PRESETS`, `MT_PRESETS` constants)
- Modify: `frontend/tests/test_profile_ui_guidance.spec.js` (reframe tests 2, 3, 4)

- [ ] **Step 1: Trim `ASR_PRESETS` — remove `speed` key**

Edit `frontend/index.html`. Find the `speed` entry inside `const ASR_PRESETS = {...}`. Use Edit:

**old_string**:
```
      speed: {
        label: 'Speed',
        description: 'small model + VAD，速度優先',
        config: { model_size: 'small', condition_on_previous_text: false, word_timestamps: false },
      },
```

**new_string**: (empty) — delete the entire `speed` entry including trailing comma + newline.

If old_string is non-unique, expand context with surrounding accuracy and debug entries.

- [ ] **Step 2: Trim `MT_PRESETS` — remove `fast-draft` key**

Find `'fast-draft': {...}` inside `const MT_PRESETS = {...}`. Use Edit:

**old_string**:
```
      'fast-draft': {
        label: 'Fast Draft',
        description: '速度優先 preview',
        config: { batch_size: 10, temperature: 0.15, parallel_batches: 4, translation_passes: 1, alignment_mode: '' },
      },
```

**new_string**: (empty)

- [ ] **Step 3: Reframe Playwright Test 2**

Edit `frontend/tests/test_profile_ui_guidance.spec.js`. Replace Test 2's body. Use Edit:

**old_string** (start of Test 2 to end):
```javascript
test("MT preset chip 'Fast Draft' sets batch_size=10 + parallel_batches=4", async ({ page }) => {
  await _openPpsModal(page);

  const fastDraftBtn = page.locator("#ppsMtPresetButtons button", { hasText: "Fast Draft" });
  await expect(fastDraftBtn).toBeVisible();
  await fastDraftBtn.click();

  await expect(fastDraftBtn).toHaveClass(/active/);

  // Fast Draft sets parallel_batches=4, which triggers critical warning
  const warning = page.locator("#ppsMtDangerWarnings .pps-warning-chip");
  await expect(warning).toBeVisible({ timeout: 1000 });
  await expect(warning).toContainText(/parallel_batches > 1/);
});
```

**new_string**:
```javascript
test("Custom MT + JS-set parallel_batches=4 triggers parallel-disables-context warning", async ({ page }) => {
  await _openPpsModal(page);

  // Click MT Custom (deactivates any pending), then JS-mutate _pendingMtPreset to set parallel_batches=4
  await page.locator("#ppsMtPresetButtons button", { hasText: "Custom" }).click();
  await page.evaluate(() => {
    // _pendingMtPreset is module-scoped; set via window helper if available, else direct.
    window._pendingMtPreset = { config: { parallel_batches: 4 } };
    if (typeof _scheduleDangerEval === "function") _scheduleDangerEval();
    else if (typeof window._scheduleDangerEval === "function") window._scheduleDangerEval();
  });

  const warning = page.locator(
    "#ppsMtDangerWarnings .pps-warning-chip",
    { hasText: /parallel_batches > 1/ },
  );
  await expect(warning).toBeVisible({ timeout: 2000 });
});
```

- [ ] **Step 4: Reframe Test 3 (mix-and-match)**

**old_string**:
```javascript
test("Mix-and-match: ASR Accuracy + MT Fast Draft both active simultaneously", async ({ page }) => {
  await _openPpsModal(page);

  await page.locator("#ppsAsrPresetButtons button", { hasText: "Accuracy" }).click();
  await page.locator("#ppsMtPresetButtons button", { hasText: "Fast Draft" }).click();

  // Both chips active concurrently
  await expect(page.locator("#ppsAsrPresetButtons button.active", { hasText: "Accuracy" })).toBeVisible();
  await expect(page.locator("#ppsMtPresetButtons button.active", { hasText: "Fast Draft" })).toBeVisible();

  // Summary mentions both
  const summary = await page.locator("#ppsSummary").textContent();
  expect(summary).toContain("large-v3");      // from ASR preset
  expect(summary).toContain("Fast Draft");    // from MT preset label OR underlying value
});
```

**new_string**:
```javascript
test("Mix-and-match: ASR Accuracy + MT Broadcast Quality both active simultaneously", async ({ page }) => {
  await _openPpsModal(page);

  await page.locator("#ppsAsrPresetButtons button", { hasText: "Accuracy" }).click();
  await page.locator("#ppsMtPresetButtons button", { hasText: "Broadcast Quality" }).click();

  await expect(page.locator("#ppsAsrPresetButtons button.active", { hasText: "Accuracy" })).toBeVisible();
  await expect(page.locator("#ppsMtPresetButtons button.active", { hasText: "Broadcast Quality" })).toBeVisible();

  const summary = await page.locator("#ppsSummary").textContent();
  expect(summary).toContain("large-v3");
  expect(summary).toContain("Broadcast Quality");
});
```

- [ ] **Step 5: Reframe Test 4 (cross-engine warning)**

**old_string**:
```javascript
test("Cross-engine warning: alignment_mode=llm-markers + word_timestamps=false renders in MT section", async ({ page }) => {
  await _openPpsModal(page);

  // Speed preset sets word_timestamps=false; Broadcast Quality preset sets alignment_mode=llm-markers
  await page.locator("#ppsAsrPresetButtons button", { hasText: "Speed" }).click();
  await page.locator("#ppsMtPresetButtons button", { hasText: "Broadcast Quality" }).click();

  const crossWarning = page.locator(
    "#ppsMtDangerWarnings .pps-warning-chip",
    { hasText: /word_timestamps/ },
  );
  await expect(crossWarning).toBeVisible({ timeout: 1000 });
});
```

**new_string**:
```javascript
test("Cross-engine warning: Custom-set word_timestamps=false + Broadcast Quality MT triggers warning", async ({ page }) => {
  await _openPpsModal(page);

  // JS-mutate ASR to remove word_timestamps; then click Broadcast Quality MT (which uses llm-markers).
  await page.locator("#ppsAsrPresetButtons button", { hasText: "Custom" }).click();
  await page.evaluate(() => {
    window._pendingAsrPreset = { config: { word_timestamps: false } };
  });
  await page.locator("#ppsMtPresetButtons button", { hasText: "Broadcast Quality" }).click();

  const crossWarning = page.locator(
    "#ppsMtDangerWarnings .pps-warning-chip",
    { hasText: /word_timestamps/ },
  );
  await expect(crossWarning).toBeVisible({ timeout: 2000 });
});
```

- [ ] **Step 6: Run Playwright + verify 4/4 pass**

Run:
```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npx playwright test test_profile_ui_guidance.spec.js --reporter=line --workers=1
```

Expected: 4 passed.

If `_pendingMtPreset` / `_pendingAsrPreset` aren't on `window`, JS state-mutation may fail. They are declared `let` at module/script scope. Try assigning via `eval('_pendingMtPreset = {...}')` inside `page.evaluate` if direct `window.` assignment doesn't work.

- [ ] **Step 7: Commit**

```bash
git add frontend/index.html frontend/tests/test_profile_ui_guidance.spec.js
git commit -m "refactor(v3.17): trim ASR Speed + MT Fast Draft presets, reframe Playwright tests"
```

---

## Task 7: Part B1 — Whisper + MLX-Whisper schema narrow

**Files:**
- Modify: `backend/asr/whisper_engine.py` (`get_params_schema`)
- Modify: `backend/asr/mlx_whisper_engine.py` (`get_params_schema`)

- [ ] **Step 1: Read current `WhisperEngine.get_params_schema` to find `model_size` enum**

```bash
grep -n "model_size\|enum\|choices" backend/asr/whisper_engine.py | head -20
```

- [ ] **Step 2: Narrow `model_size` enum to `['large-v3']` in `WhisperEngine.get_params_schema`**

Use Edit to change the schema's `model_size` field. The field will look something like:
```python
"model_size": {
    "type": "string",
    "enum": ["tiny", "base", "small", "medium", "large-v2", "large-v3"],
    "default": "...",
},
```

Replace with:
```python
"model_size": {
    "type": "string",
    "enum": ["large-v3"],
    "default": "large-v3",
},
```

- [ ] **Step 3: Same change in `mlx_whisper_engine.py`**

- [ ] **Step 4: Run ASR-related backend tests**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_asr.py -v
```

Expected: most pass. Tests asserting non-large-v3 model sizes will fail and need updating in Task 10 (B5).

- [ ] **Step 5: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/asr/whisper_engine.py backend/asr/mlx_whisper_engine.py
git commit -m "refactor(v3.17): narrow ASR model_size enum to large-v3 only"
```

---

## Task 8: Part B2 — Profile migration script + run

**Files:**
- Create: `backend/scripts/migrate_v317_asr_models.py`
- Modify: `backend/config/profiles/*.json` (only if any non-large-v3 model_size found)

- [ ] **Step 1: Create migration script**

```python
"""One-shot migration: normalize all profile asr.model_size to 'large-v3'.

Run once after v3.17 narrow. Idempotent — safe to re-run.

Usage:
    python backend/scripts/migrate_v317_asr_models.py
"""
import json
import sys
from pathlib import Path

TARGET_MODEL = "large-v3"
PROFILES_DIR = Path(__file__).resolve().parent.parent / "config" / "profiles"


def migrate_profile(profile_path: Path) -> tuple[bool, str | None]:
    try:
        profile = json.loads(profile_path.read_text(encoding="utf-8"))
    except Exception as e:
        return False, f"parse error: {e}"
    asr = profile.get("asr") or {}
    current = asr.get("model_size")
    if current and current != TARGET_MODEL:
        old = current
        asr["model_size"] = TARGET_MODEL
        profile["asr"] = asr
        profile_path.write_text(
            json.dumps(profile, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return True, f"{old} → {TARGET_MODEL}"
    return False, None


def main():
    if not PROFILES_DIR.exists():
        print(f"Profiles dir not found: {PROFILES_DIR}", file=sys.stderr)
        return 1
    modified_count = 0
    skipped_count = 0
    error_count = 0
    for p in sorted(PROFILES_DIR.glob("*.json")):
        ok, info = migrate_profile(p)
        if ok:
            print(f"MIGRATED  {p.name}: {info}")
            modified_count += 1
        elif info and "parse error" in info:
            print(f"ERROR     {p.name}: {info}", file=sys.stderr)
            error_count += 1
        else:
            print(f"SKIPPED   {p.name} (already large-v3 or no asr.model_size)")
            skipped_count += 1
    print(f"\nTotal: {modified_count} migrated, {skipped_count} skipped, {error_count} errors")
    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run migration**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
source backend/venv/bin/activate
python backend/scripts/migrate_v317_asr_models.py
```

Expected: prints `MIGRATED` or `SKIPPED` per profile. Note total counts.

- [ ] **Step 3: Verify all profiles now use large-v3**

```bash
grep -l '"model_size"' backend/config/profiles/*.json | xargs -I {} sh -c 'echo "=== {} ===" && grep "model_size" {}'
```

Expected: every match shows `"model_size": "large-v3"`.

- [ ] **Step 4: Re-run migration to verify idempotency**

```bash
python backend/scripts/migrate_v317_asr_models.py
```

Expected: all profiles "SKIPPED", 0 migrated, 0 errors.

- [ ] **Step 5: Commit**

```bash
git add backend/scripts/migrate_v317_asr_models.py backend/config/profiles/
git commit -m "refactor(v3.17): migration script + force all profiles to model_size=large-v3"
```

---

## Task 9: Part B3+B4 — Delete stub engines + factory cleanup

**Files:**
- Delete: `backend/asr/qwen3_engine.py`
- Delete: `backend/asr/flg_engine.py`
- Modify: `backend/asr/__init__.py` (remove imports + factory mappings)

- [ ] **Step 1: Verify the stub files are indeed stubs (not real impl)**

```bash
wc -l backend/asr/qwen3_engine.py backend/asr/flg_engine.py
head -50 backend/asr/qwen3_engine.py
head -50 backend/asr/flg_engine.py
```

Confirm files contain placeholder/stub code (e.g., `raise NotImplementedError`, no real `transcribe` body).

- [ ] **Step 2: Delete both files**

```bash
git rm backend/asr/qwen3_engine.py backend/asr/flg_engine.py
```

- [ ] **Step 3: Update `backend/asr/__init__.py` — remove imports + factory mappings**

```bash
grep -n "qwen3\|Qwen3\|flg\|FLG" backend/asr/__init__.py
```

Then use Edit to remove each matching line. Look for:
- `from .qwen3_engine import Qwen3ASREngine` → delete line
- `from .flg_engine import FLGASREngine` → delete line
- `'qwen3-asr': Qwen3ASREngine,` or similar in factory dict → delete line
- `'flg-asr': FLGASREngine,` or similar → delete line

After edits, run:
```bash
grep -n "qwen3\|Qwen3\|flg\|FLG" backend/asr/__init__.py
```
Expected: 0 matches.

- [ ] **Step 4: Verify factory still works for known engines**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
python -c "
from asr import create_asr_engine
print(create_asr_engine({'engine': 'whisper', 'model_size': 'large-v3'}))
print(create_asr_engine({'engine': 'mlx-whisper', 'model_size': 'large-v3'}))
"
```

Expected: prints two engine repr strings, no ImportError.

- [ ] **Step 5: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/asr/__init__.py
git commit -m "refactor(v3.17): delete qwen3 + flg stub engines, drop factory mappings"
```

---

## Task 10: Part B5 — Backend test cleanup

**Files:**
- Modify or delete: tests in `backend/tests/` referencing qwen3/flg/non-large-v3 model

- [ ] **Step 1: Grep affected tests**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
grep -rn "qwen3\|Qwen3\|flg\|FLG\|'tiny'\|'base'\|'small'\|'medium'\|'large-v2'" backend/tests/
```

Record each (file, line, content). Triage:
- Pure stub-existence test (`test_qwen3_engine_stub`) → DELETE the test
- Factory listing test (`test_create_asr_engine_known_engines`) → REMOVE qwen3/flg from expected list
- Schema enum test asserting `tiny` ∈ enum → CHANGE to assert single `large-v3` value
- Test using `model_size='small'` as test fixture → CHANGE to `'large-v3'`

For each match: use Edit to either delete the test function (if entire test is obsolete) or update assertions/fixtures.

- [ ] **Step 2: Run full backend test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v --tb=short 2>&1 | tail -60
```

Expected: all pass except pre-existing flakes (e.g., v3.3 macOS tmpdir test). NO new failures.

If new failures appear in non-ASR test files: investigate — there may be hidden dependency on qwen3/flg/non-large-v3 elsewhere.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/
git commit -m "test(v3.17): drop tests for removed stub engines + non-large-v3 model_size"
```

---

## Task 11: Re-run ASR + MT on both videos (post-v3.17)

**Files:** Generate `docs/superpowers/validation/v3.17-post-{file_id_short}.json` × 2

This task uses the REAL backend with v3.17 changes applied (tasks 6-10 committed). Re-transcribe + re-translate each video. Output time depends on video length + model speed (real-time on Apple Silicon for large-v3).

- [ ] **Step 1: Restart backend to ensure new code loaded**

```bash
pkill -f 'python app.py' 2>/dev/null
sleep 2
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
python app.py > /tmp/v317-task11.log 2>&1 &
sleep 5
curl -s http://localhost:5001/api/ready
```

Expected: `{"ready":true}`.

- [ ] **Step 2: Add `rerun` subcommand to `v317_validation.py`**

Extend `backend/scripts/v317_validation.py`:

```python
def rerun_pipeline(session: requests.Session, file_id: str, timeout_sec: int = 1800) -> Dict[str, Any]:
    """POST /api/files/<id>/transcribe and poll until ASR + MT both done.

    Returns final file status dict.
    """
    # Trigger re-transcribe
    r = session.post(f"{BASE_URL}/api/files/{file_id}/transcribe")
    r.raise_for_status()
    print(f"[rerun {file_id[:12]}] enqueued: {r.json()}")

    # Poll status until both ASR + MT done
    start = time.time()
    while time.time() - start < timeout_sec:
        time.sleep(5)
        fr = session.get(f"{BASE_URL}/api/files")
        if not fr.ok:
            continue
        entry = next((f for f in fr.json().get("files", []) if f["id"] == file_id), None)
        if entry is None:
            continue
        asr_done = entry.get("status") in ("done", "transcribed", "translated", "completed")
        mt_done = entry.get("translation_status") in ("done", "completed")
        elapsed = int(time.time() - start)
        print(f"[rerun {file_id[:12]} t+{elapsed}s] status={entry.get('status')} mt={entry.get('translation_status')}")
        if asr_done and mt_done:
            return entry
    raise TimeoutError(f"rerun for {file_id} did not complete within {timeout_sec}s")


def cmd_rerun(args):
    s = _login_session()
    rerun_pipeline(s, args.file_id, timeout_sec=args.timeout)
    snap = capture_snapshot(s, args.file_id)
    Path(args.output).write_text(json.dumps(snap, ensure_ascii=False, indent=2))
    print(f"Wrote post-snapshot to {args.output}")
```

Add subparser to `main()`:

```python
    rp = sub.add_parser("rerun")
    rp.add_argument("--file-id", required=True)
    rp.add_argument("--output", required=True)
    rp.add_argument("--timeout", type=int, default=1800)
    rp.set_defaults(func=cmd_rerun)
```

Run unit tests to confirm no regression:
```bash
cd backend && source venv/bin/activate && pytest tests/test_v317_validation.py -v
```

- [ ] **Step 3: Re-run video 1**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
source backend/venv/bin/activate
python backend/scripts/v317_validation.py rerun \
    --file-id <full_id_1> \
    --output docs/superpowers/validation/v3.17-post-<id_short_1>.json
```

Wait for completion (could take real-time × video length).

- [ ] **Step 4: Re-run video 2**

```bash
python backend/scripts/v317_validation.py rerun \
    --file-id <full_id_2> \
    --output docs/superpowers/validation/v3.17-post-<id_short_2>.json
```

- [ ] **Step 5: Verify both post-snapshots**

```bash
for f in docs/superpowers/validation/v3.17-post-*.json; do
    echo "=== $f ==="
    cat "$f" | jq '.file.id, (.segments | length), (.translations | length), .glossary_scan.strict_violation_count'
done
```

Both should have non-empty segments + translations.

- [ ] **Step 6: Commit post-snapshots + the rerun command**

```bash
git add backend/scripts/v317_validation.py docs/superpowers/validation/v3.17-post-*.json
git commit -m "chore(v3.17): capture post-v3.17 snapshots for 2 videos"
```

---

## Task 12: Generate diff report

**Files:** Create `docs/superpowers/validation/v3.17-diff-report.md`

- [ ] **Step 1: Run diff command**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
source backend/venv/bin/activate
python backend/scripts/v317_validation.py diff \
    --baseline-glob 'docs/superpowers/validation/v3.17-baseline-*.json' \
    --post-glob 'docs/superpowers/validation/v3.17-post-*.json' \
    --output docs/superpowers/validation/v3.17-diff-report.md
```

Verify file exists + has expected structure:
```bash
head -50 docs/superpowers/validation/v3.17-diff-report.md
```

Expected: starts with `# v3.17 Validation Diff Report`, has "Executive Summary", at least 2 video sections.

- [ ] **Step 2: Manually fill in verdict + executive summary**

Open `docs/superpowers/validation/v3.17-diff-report.md` and:

1. Update top `Verdict: ✅` line to reflect actual outcome (one of `✅` / `⚠️` / `❌`)
2. Add 3 bullet "Key findings" under Executive Summary based on what you see in the per-video sections
3. Fill in the `## Conclusion` section with one of: `Recommendation: merge` / `Recommendation: rollback` / `Recommendation: further investigation` + 1-2 sentences supporting reason

This is the only manual editorial step in the validation pipeline.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/validation/v3.17-diff-report.md
git commit -m "chore(v3.17): validation diff report + verdict"
```

---

## Task 13: CLAUDE.md v3.17 entry

**Files:** Modify `CLAUDE.md`

- [ ] **Step 1: Insert v3.17 entry before v3.16**

Find `### v3.16 — Per-Engine Preset + Danger Warning Refactor` line. Use Edit:

**old_string**: `### v3.16 — Per-Engine Preset + Danger Warning Refactor`

**new_string**:
```
### v3.17 — Preset Trim + ASR Cleanup + Validation
- **Part A — preset trim**：`ASR_PRESETS` 刪 `speed`（剩 `accuracy`/`debug`/`custom`）；`MT_PRESETS` 刪 `fast-draft`（剩 `broadcast-quality`/`literal-ref`/`custom`）。Playwright Test 2、Test 3、Test 4 reframe — Test 2 + Test 4 改用 Custom preset + `window._pendingMt/AsrPreset` JS direct-mutate 觸發 warning；Test 3 mix-and-match 改 ASR Accuracy + MT Broadcast Quality。
- **Part B — ASR engine cleanup**：
  - `whisper_engine.py` + `mlx_whisper_engine.py` 嘅 `get_params_schema()` 將 `model_size` enum 收窄到 `['large-v3']`，前端 dropdown 自動跟。
  - 一次性 migration script [backend/scripts/migrate_v317_asr_models.py](backend/scripts/migrate_v317_asr_models.py) 將既有 `config/profiles/*.json` 內 `asr.model_size != 'large-v3'` 嘅 normalize 做 `'large-v3'`。Idempotent，safe re-run。
  - Delete `backend/asr/qwen3_engine.py` + `backend/asr/flg_engine.py`（自 v2.0 起一直 stub，未真正實裝）；`backend/asr/__init__.py` factory 移除對應 imports + mapping。
  - Backend tests 內 qwen3/flg/non-large-v3 reference 清理。
- **Part C — Validation**：[backend/scripts/v317_validation.py](backend/scripts/v317_validation.py)（~700 行）— 1 個 snapshot 拎齊 file/segments/translations/profile/glossary-scan，13 個 metric helper（Tier 1 core 5 + Tier 2 broadcast quality 4 + Tier 3 diagnostic 5），markdown report renderer。對 server 上嘅 2 條 video 做 baseline → 應用 v3.17 → re-run ASR/MT → post snapshot → 13-tier diff report。Report + baseline/post snapshot 全部 commit 入 [docs/superpowers/validation/](docs/superpowers/validation/)。
- **Validation 結果**：詳細見 [docs/superpowers/validation/v3.17-diff-report.md](docs/superpowers/validation/v3.17-diff-report.md)。
- **Files touched**：3 個 modified（`frontend/index.html`、`frontend/tests/test_profile_ui_guidance.spec.js`、`CLAUDE.md`），4 個 backend modified（`whisper_engine.py`、`mlx_whisper_engine.py`、`asr/__init__.py`、tests），2 個 backend deleted（`qwen3_engine.py`、`flg_engine.py`），4 個 new script + tests + report + baselines。
- **Spec/Plan**：[docs/superpowers/specs/2026-05-15-preset-trim-asr-cleanup-design.md](docs/superpowers/specs/2026-05-15-preset-trim-asr-cleanup-design.md) / [docs/superpowers/plans/2026-05-15-preset-trim-asr-cleanup-plan.md](docs/superpowers/plans/2026-05-15-preset-trim-asr-cleanup-plan.md)

### v3.16 — Per-Engine Preset + Danger Warning Refactor
```

- [ ] **Step 2: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add CLAUDE.md
git commit -m "docs(v3.17): CLAUDE.md entry for preset trim + ASR cleanup + validation"
```

---

## Task 14: User review gate (HUMAN STOP)

This task is **not implemented by SDD agent** — STOP and present results to user.

- [ ] **Step 1: SDD pipeline halts after Task 13 commit. Report back to user with:**
  - Branch state: 8809611 → HEAD-of-v3.17 commit chain summary
  - Validation report path: `docs/superpowers/validation/v3.17-diff-report.md`
  - Verdict from the report
  - 3 options for user:
    - ✅ Accept → push branch + open PR
    - ⚠️ Accept with notes → push + PR + open follow-up issue
    - ❌ Rollback → reset Part B (delete migration commit, restore stub engines from git history)

**End of plan.** No further automation. User decides next step.

---

## Self-Review

### Spec coverage matrix

| Spec section | Plan task |
|---|---|
| Part A — preset trim | Task 6 |
| Part B1 — Whisper schema narrow | Task 7 |
| Part B2 — profile migration | Task 8 |
| Part B3 — delete stubs | Task 9 |
| Part B4 — factory cleanup | Task 9 |
| Part B5 — test cleanup | Task 10 |
| Part B6 — CLAUDE.md docs | Task 13 |
| Part C1-C3 — Tier 1+2+3 helpers | Tasks 1-3 |
| Part C4 — report renderer | Task 4 |
| Part C5 — baseline capture | Task 5 |
| Part C6 — re-run pipeline | Task 11 |
| Part C7 — diff report generation | Task 12 |
| Part C8 — user review gate | Task 14 |

All 13 spec components have explicit plan coverage.

### Placeholder scan

- No "TBD" or "TODO" markers in the plan
- Every step has concrete file path
- Every code block is complete (no `// implementation here` stubs)
- Every command has expected output specified

### Type consistency

- `_pendingAsrPreset` / `_pendingMtPreset` shapes match v3.16 baseline (`{ config: {...} } | null`)
- Snapshot dict shape (`file`, `segments`, `translations`, `profile_snapshot`, `glossary_scan`) consistent across all task references
- `compute_all_diffs` returns dict with 13 keys; `render_report` reads same 13 keys
- CLI subcommand names (`snapshot`, `rerun`, `diff`) consistent across tasks 1, 4, 11, 12

Plan ready for execution.
