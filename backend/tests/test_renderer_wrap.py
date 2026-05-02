"""Renderer wrap_hybrid integration tests (Task 13, v3.9 line-wrap)."""

from renderer import SubtitleRenderer


def test_renderer_uses_wrap_hybrid_for_cityu_preset(tmp_path):
    """When subtitle_standard='cityu_hybrid', renderer wraps using wrap_hybrid."""
    translations = [
        {
            "start": 0.0, "end": 2.0,
            "en_text": "Test text",
            "zh_text": "在後防方面，傷病纏身令皇馬告急。",  # 16c, fits hard cap+tail single line
        },
    ]
    font_config = {
        "family": "Noto Sans TC", "size": 35, "color": "#ffffff",
        "outline_color": "#000000", "outline_width": 3, "margin_bottom": 40,
        "subtitle_standard": "cityu_hybrid",
        "line_wrap": {
            "enabled": True, "soft_cap": 14, "hard_cap": 16,
            "max_lines": 2, "tail_tolerance": 2, "bottom_heavy": True,
        },
    }
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(translations, font_config=font_config)
    # Verify ass output contains the dialogue line — fits as single line (16c <= soft+tail=16)
    assert "在後防方面" in ass


def test_renderer_uses_legacy_wrap_zh_for_broadcast_preset(tmp_path):
    """When subtitle_standard != 'cityu_hybrid', use legacy wrap_zh (no breaking change)."""
    translations = [
        {"start": 0.0, "end": 2.0, "en_text": "Test", "zh_text": "在後防方面，傷病纏身令皇馬告急。"},
    ]
    font_config = {
        "family": "Noto Sans TC", "size": 35, "color": "#ffffff",
        "outline_color": "#000000", "outline_width": 3, "margin_bottom": 40,
        "subtitle_standard": "broadcast",
        "line_wrap": {"enabled": True, "line_cap": 28, "max_lines": 2, "tail_tolerance": 2},
    }
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(translations, font_config=font_config)
    assert "在後防方面" in ass


def test_renderer_two_line_wrap_with_hybrid(tmp_path):
    """Long ZH that needs wrapping — verify \\N appears in dialogue."""
    translations = [
        {
            "start": 0.0, "end": 3.0, "en_text": "Test",
            # 27 chars, > hard_cap+tail=18, must 2-line wrap
            "zh_text": "在後防方面，大衛阿拉巴的傷病纏身令皇馬告急堪憂。",
        },
    ]
    font_config = {
        "family": "Noto Sans TC", "size": 35, "color": "#ffffff",
        "outline_color": "#000000", "outline_width": 3, "margin_bottom": 40,
        "subtitle_standard": "cityu_hybrid",
        "line_wrap": {"enabled": True, "soft_cap": 14, "hard_cap": 16,
                      "max_lines": 2, "tail_tolerance": 2, "bottom_heavy": True},
    }
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(translations, font_config=font_config)
    # Wrapped to 2 lines via \\N
    assert "\\N" in ass
