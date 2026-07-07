"""apply-item 括號：prompt 條款 + ensure_brackets 機械兜底。"""
import glossary_review as gr


def test_prompt_without_brackets_unchanged():
    p = gr.build_apply_system_prompt("中文", "target")
    assert "「」括住" not in p


def test_prompt_with_brackets_has_rule():
    p = gr.build_apply_system_prompt("中文", "target", brackets=True)
    assert "「」括住" in p


def test_ensure_brackets_wraps():
    assert gr.ensure_brackets("巴閉佬出色", "巴閉佬") == "「巴閉佬」出色"


def test_ensure_brackets_idempotent():
    assert gr.ensure_brackets("「巴閉佬」出色", "巴閉佬") == "「巴閉佬」出色"


def test_ensure_brackets_absent_canonical_noop():
    assert gr.ensure_brackets("其他句子", "巴閉佬") == "其他句子"


def test_validate_applied_accepts_wrapped():
    assert gr.validate_applied("「巴閉佬」表現出色", "巴閉佬", "巴閉老表現出色") is None
