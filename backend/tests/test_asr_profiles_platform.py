import asr_profiles


def test_available_engines_excludes_mlx_off_apple(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "win32")
    assert "mlx-whisper" not in asr_profiles.available_engines()
    assert "whisper" in asr_profiles.available_engines()


def test_available_engines_includes_mlx_on_apple(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "darwin")
    assert "mlx-whisper" in asr_profiles.available_engines()


def test_validate_rejects_mlx_engine_off_apple(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "linux")
    errors = asr_profiles.validate_asr_profile(
        {"name": "x", "engine": "mlx-whisper", "model_size": "large-v3", "mode": "same-lang"}
    )
    assert any("mlx-whisper" in e and "platform" in e.lower() for e in errors)


def test_validate_allows_mlx_engine_on_apple(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "darwin")
    errors = asr_profiles.validate_asr_profile(
        {"name": "x", "engine": "mlx-whisper", "model_size": "large-v3", "mode": "same-lang"}
    )
    assert not any("platform" in e.lower() for e in errors)
