from output_lang_router import route_output, whisper_direct_params, content_asr_lang


def test_route_same_dialect_is_whisper():
    assert route_output("yue", "yue") == "whisper"
    assert route_output("cmn", "cmn") == "whisper"
    assert route_output("en", "en") == "whisper"
    assert route_output("ja", "ja") == "whisper"


def test_route_zh_output_accepts_yue_and_cmn():
    assert route_output("yue", "zh") == "whisper"
    assert route_output("cmn", "zh") == "whisper"
    assert route_output("yue", "cmn") == "whisper"
    assert route_output("cmn", "yue") == "asr_mt"   # ★ 普→口語廣東話 must be MT


def test_route_cross_language_is_asr_mt():
    assert route_output("yue", "en") == "asr_mt"
    assert route_output("yue", "ja") == "asr_mt"
    assert route_output("en", "zh") == "asr_mt"
    assert route_output("en", "yue") == "asr_mt"
    assert route_output("ja", "zh") == "asr_mt"
    assert route_output("ja", "en") == "asr_mt"


def test_route_unknown_defaults_asr_mt():
    assert route_output("xx", "zh") == "asr_mt"


def test_whisper_direct_params():
    assert whisper_direct_params("yue") == {"lang_override": "yue", "task_override": "transcribe"}
    assert whisper_direct_params("zh") == {"lang_override": "zh", "task_override": "transcribe"}
    assert whisper_direct_params("cmn") == {"lang_override": "zh", "task_override": "transcribe"}
    assert whisper_direct_params("ja") == {"lang_override": "ja", "task_override": "transcribe"}
    assert whisper_direct_params("en") == {"lang_override": "en", "task_override": "transcribe"}


def test_content_asr_lang():
    assert content_asr_lang("yue") == "yue"
    assert content_asr_lang("cmn") == "zh"
    assert content_asr_lang("en") == "en"
    assert content_asr_lang("ja") == "ja"
