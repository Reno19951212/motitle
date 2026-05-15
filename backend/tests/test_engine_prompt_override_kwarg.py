"""Tests that OllamaTranslationEngine.translate() accepts a per-call
prompt_overrides kwarg and that the kwarg takes priority over
self._config['prompt_overrides']."""
from unittest.mock import patch

from translation.ollama_engine import OllamaTranslationEngine


def make_engine(config_overrides=None):
    cfg = {"engine": "mock-test", "ollama_url": "http://localhost:11434"}
    if config_overrides is not None:
        cfg["prompt_overrides"] = config_overrides
    return OllamaTranslationEngine(cfg)


class TestKwargPrecedence:
    def test_kwarg_overrides_config(self):
        """When both kwarg and self._config carry a key, kwarg wins."""
        engine = make_engine({"single_segment_system": "FROM_CONFIG"})
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured["system"] = system_prompt
            return "中文輸出"

        segs = [{"start": 0, "end": 1, "text": "hello"}]
        with patch.object(OllamaTranslationEngine, "_call_ollama", fake_call):
            engine.translate(
                segs, batch_size=1,
                prompt_overrides={"single_segment_system": "FROM_KWARG"},
            )
        assert captured["system"].startswith("FROM_KWARG")

    def test_kwarg_none_falls_back_to_config(self):
        engine = make_engine({"single_segment_system": "FROM_CONFIG"})
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured["system"] = system_prompt
            return "中文"

        segs = [{"start": 0, "end": 1, "text": "hi"}]
        with patch.object(OllamaTranslationEngine, "_call_ollama", fake_call):
            engine.translate(segs, batch_size=1, prompt_overrides=None)
        assert captured["system"].startswith("FROM_CONFIG")

    def test_no_kwarg_no_config_falls_back_to_constant(self):
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        engine = make_engine(None)
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured["system"] = system_prompt
            return "中文"

        segs = [{"start": 0, "end": 1, "text": "hi"}]
        with patch.object(OllamaTranslationEngine, "_call_ollama", fake_call):
            engine.translate(segs, batch_size=1)
        # First 20 chars should match default constant prefix
        assert captured["system"].startswith(SINGLE_SEGMENT_SYSTEM_PROMPT[:20])

    def test_kwarg_key_missing_falls_back_to_config(self):
        """If kwarg dict has different key, lookup for missing key falls to config."""
        engine = make_engine({"single_segment_system": "FROM_CONFIG"})
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured["system"] = system_prompt
            return "中文"

        segs = [{"start": 0, "end": 1, "text": "hi"}]
        with patch.object(OllamaTranslationEngine, "_call_ollama", fake_call):
            engine.translate(
                segs, batch_size=1,
                prompt_overrides={"pass2_enrich_system": "unrelated"},
            )
        # Falls back to config for single_segment_system
        assert captured["system"].startswith("FROM_CONFIG")
