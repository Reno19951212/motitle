from app import _select_translation_strategy as pick


def test_english_llm_markers_keeps_alignment():
    assert pick("llm-markers", False, True) == "alignment"


def test_nonenglish_llm_markers_routes_to_single():
    assert pick("llm-markers", False, False) == "single_1to1"


def test_nonenglish_sentence_mode_routes_to_single():
    assert pick("sentence", False, False) == "single_1to1"


def test_nonenglish_use_sentence_flag_routes_to_single():
    assert pick("", True, False) == "single_1to1"


def test_english_sentence_mode_keeps_sentence():
    assert pick("sentence", False, True) == "sentence"


def test_english_use_sentence_flag_keeps_sentence():
    assert pick("", True, True) == "sentence"


def test_english_default_is_batched():
    assert pick("", False, True) == "batched"


def test_nonenglish_default_stays_batched():
    assert pick("", False, False) == "batched"


def test_case_insensitive_alignment_mode():
    assert pick("LLM-MARKERS", False, False) == "single_1to1"
