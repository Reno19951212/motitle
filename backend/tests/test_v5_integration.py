"""v5-A1 integration: load a v5 pipeline JSON end-to-end through profile managers + schema."""
import json
from pathlib import Path


def test_v5_full_pipeline_load_end_to_end(tmp_path):
    """Build profiles in all 5 managers, save v5 pipeline JSON, load and verify all refs resolve."""
    from llm_profiles import LLMProfileManager
    from transcribe_profiles import TranscribeProfileManager
    from translator_profiles import TranslatorProfileManager
    from refiner_profiles import RefinerProfileManager
    from verifier_profiles import VerifierProfileManager
    from pipelines import PipelineManager
    from pipeline_schema_v5 import check_cascade_refs

    # Set up isolated managers (one dir each under tmp_path)
    llm = LLMProfileManager(tmp_path / "llm")
    tr = TranscribeProfileManager(tmp_path / "transcribe")
    xl = TranslatorProfileManager(tmp_path / "translator")
    rf = RefinerProfileManager(tmp_path / "refiner")
    vf = VerifierProfileManager(tmp_path / "verifier")
    pl = PipelineManager(tmp_path / "pipeline")

    # Create one of each profile
    llm_id = llm.create({
        "name": "ollama qwen", "backend": "ollama",
        "model": "qwen3.5:35b-a3b-mlx-bf16",
        "base_url": "http://localhost:11434",
    }, user_id=1)
    tp_primary = tr.create({
        "name": "whisper", "engine": "whisper",
        "model_size": "large-v3", "language": "zh",
    }, user_id=1)
    tp_secondary = tr.create({
        "name": "qwen3", "engine": "qwen3-asr", "language": "zh",
    }, user_id=1)
    rp = rf.create({
        "name": "zh-broadcast", "lang": "zh", "style": "broadcast-hk",
        "llm_profile_id": llm_id,
        "prompt_template_id": "refiner/zh_broadcast_hk_default",
    }, user_id=1)
    tr_id = xl.create({
        "name": "zh->en", "source_lang": "zh", "target_lang": "en",
        "llm_profile_id": llm_id,
        "prompt_template_id": "translator/zh_to_en_default",
    }, user_id=1)
    vf_id = vf.create({
        "name": "zh-verifier", "lang": "zh",
        "llm_profile_id": llm_id,
        "prompt_template_id": "verifier/zh_default",
    }, user_id=1)

    # Build complete v5 pipeline referencing all profiles
    v5 = {
        "name": "HK broadcast (ZH+EN) with dual ASR",
        "version": 5,
        "user_id": 1,
        "asr_primary": {"transcribe_profile_id": tp_primary, "source_lang": "zh"},
        "asr_secondary": {"transcribe_profile_id": tp_secondary, "source_lang": "zh"},
        "asr_verifier": {"llm_profile_id": llm_id, "prompt_template_id": "verifier/zh_default"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": [{"refiner_profile_id": rp}], "en": []},
        "translators": {"en": {"translator_profile_id": tr_id}},
        "glossary_stages": {},
        "font_config": {"family": "Noto Sans TC", "color": "white", "outline_color": "black"},
    }
    pid = pl.create(v5, user_id=1, validate_refs=False)
    loaded = pl.get(pid, as_v5=True)
    assert loaded["version"] == 5
    assert loaded["asr_secondary"]["transcribe_profile_id"] == tp_secondary
    assert loaded["target_languages"] == ["zh", "en"]
    assert loaded["translators"]["en"]["translator_profile_id"] == tr_id

    # Build refs dict from managers and verify cascade check passes
    refs = {
        "transcribe": {p["id"] for p in tr.list_visible(1, True)},
        "translator": {p["id"] for p in xl.list_visible(1, True)},
        "refiner": {p["id"] for p in rf.list_visible(1, True)},
        "verifier": {p["id"] for p in vf.list_visible(1, True)},
        "glossary": set(),
        "llm": {p["id"] for p in llm.list_visible(1, True)},
    }
    broken = check_cascade_refs(loaded, refs)
    assert broken == [], f"unexpected broken refs: {broken}"


def test_v5_minimal_pipeline_zh_source_only(tmp_path):
    """Pipeline with only source-lang target (no translator needed) validates clean."""
    from transcribe_profiles import TranscribeProfileManager
    from refiner_profiles import RefinerProfileManager
    from llm_profiles import LLMProfileManager
    from pipelines import PipelineManager
    from pipeline_schema_v5 import check_cascade_refs

    llm = LLMProfileManager(tmp_path / "llm")
    tr = TranscribeProfileManager(tmp_path / "transcribe")
    rf = RefinerProfileManager(tmp_path / "refiner")
    pl = PipelineManager(tmp_path / "pipeline")

    llm_id = llm.create({"name": "x", "backend": "ollama", "model": "m", "base_url": "http://x"}, user_id=1)
    tp = tr.create({"name": "w", "engine": "whisper", "model_size": "large-v3", "language": "zh"}, user_id=1)
    rp = rf.create({
        "name": "r", "lang": "zh", "style": "broadcast",
        "llm_profile_id": llm_id, "prompt_template_id": "refiner/zh_broadcast_hk_default",
    }, user_id=1)

    v5 = {
        "name": "ZH only",
        "version": 5,
        "asr_primary": {"transcribe_profile_id": tp, "source_lang": "zh"},
        "target_languages": ["zh"],  # source = only target -> no translator
        "refinements": {"zh": [{"refiner_profile_id": rp}]},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    pid = pl.create(v5, user_id=1, validate_refs=False)
    loaded = pl.get(pid, as_v5=True)
    refs = {
        "transcribe": {p["id"] for p in tr.list_visible(1, True)},
        "translator": set(),
        "refiner": {p["id"] for p in rf.list_visible(1, True)},
        "verifier": set(),
        "glossary": set(),
        "llm": {p["id"] for p in llm.list_visible(1, True)},
    }
    assert check_cascade_refs(loaded, refs) == []
