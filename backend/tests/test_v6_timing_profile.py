"""D3 — V6 mlx timing track must run condition_on_previous_text=False."""
from pipeline_runner import _v6_timing_profile


def test_forces_cond_false_when_profile_true():
    prof = {"engine": "mlx-whisper", "model_size": "large-v3",
            "condition_on_previous_text": True, "initial_prompt": "x"}
    out = _v6_timing_profile(prof)
    assert out["condition_on_previous_text"] is False
    assert out["model_size"] == "large-v3" and out["initial_prompt"] == "x"
    assert prof["condition_on_previous_text"] is True   # input not mutated


def test_forces_cond_false_when_absent():
    out = _v6_timing_profile({"engine": "mlx-whisper"})
    assert out["condition_on_previous_text"] is False
