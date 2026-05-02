"""G2 integration: full A3 pipeline on cached corpus, asserts metrics."""
import json
import os
import sys
import pytest

THIS_DIR = os.path.dirname(__file__)
BACKEND_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
sys.path.insert(0, BACKEND_DIR)


@pytest.mark.integration
def test_a3_pipeline_on_dbf_corpus():
    """Run A3 ensemble on first 10 segs of golden Real Madrid corpus.

    Requires OPENROUTER_API_KEY env or prod-default.json. Skipped if missing.
    """
    corpus_path = os.path.join(BACKEND_DIR, "tests", "validation", "corpora",
                               "golden_dbf9f8a6bda7.json")
    if not os.path.exists(corpus_path):
        pytest.skip(f"Golden corpus not generated: {corpus_path}")

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        prof_path = os.path.join(BACKEND_DIR, "config", "profiles", "prod-default.json")
        if os.path.exists(prof_path):
            api_key = json.load(open(prof_path))["translation"].get("api_key")
    if not api_key:
        pytest.skip("OPENROUTER_API_KEY not set")

    corpus = json.load(open(corpus_path))
    # Use subset for speed (10 segs)
    segments = corpus["segments"][:10]

    from translation.sentence_pipeline import translate_with_a3_ensemble
    from tests.validation.metrics import compute_kpis

    profile_config = {
        "engine": "openrouter",
        "openrouter_model": "qwen/Qwen3.5-35B-A3B",
        "openrouter_reasoning": False,
        "api_key": api_key,
        "a3_ensemble": True,
        "batch_size": 10,
        "temperature": 0.1,
    }
    result = translate_with_a3_ensemble(segments, glossary=[], profile_config=profile_config)

    assert len(result) == len(segments), f"segment count mismatch: {len(result)} vs {len(segments)}"
    kpis = compute_kpis(result, "K4")
    # Looser thresholds for 10-seg subset (variance)
    assert kpis["M2_pct_le16_le2lines"] >= 80.0, f"M2 too low: {kpis['M2_pct_le16_le2lines']}"
    assert kpis["L1_name_split_count"] == 0, f"Lock violated: {kpis['L1_name_split_count']}"
    # Check source distribution — should have at least some k4 (most common winner)
    src_counts = {}
    for r in result:
        s = r.get("source", "?")
        src_counts[s] = src_counts.get(s, 0) + 1
    assert "k4" in src_counts or "k4_unrescuable" in src_counts, f"No K4 source: {src_counts}"
