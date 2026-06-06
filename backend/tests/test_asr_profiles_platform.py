import asr_profiles
import platform_backend


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


# --- Fix #3: whispercpp (Linux/GB10-only placeholder) ---------------------

def test_available_engines_includes_whispercpp_on_linux(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "linux")
    engines = asr_profiles.available_engines()
    assert "whispercpp" in engines
    assert "mlx-whisper" not in engines  # linux excludes mlx


def test_available_engines_excludes_whispercpp_off_linux(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "darwin")
    assert "whispercpp" not in asr_profiles.available_engines()


def test_validate_rejects_whispercpp_off_linux(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "darwin")
    errors = asr_profiles.validate_asr_profile(
        {
            "name": "x",
            "engine": "whispercpp",
            "model_size": "large-v3",
            "mode": "same-lang",
            "language": "en",
        }
    )
    assert any("whispercpp" in e and "platform" in e.lower() for e in errors)


def test_validate_allows_whispercpp_on_linux(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "linux")
    errors = asr_profiles.validate_asr_profile(
        {
            "name": "x",
            "engine": "whispercpp",
            "model_size": "large-v3",
            "mode": "same-lang",
            "language": "en",
        }
    )
    assert not any("platform" in e.lower() for e in errors)


def test_create_asr_engine_whispercpp_not_implemented():
    from asr import create_asr_engine
    import pytest

    with pytest.raises(NotImplementedError) as exc:
        create_asr_engine({"engine": "whispercpp"})
    assert "GB10" in str(exc.value)


# --- Fix #4: device cuda validation ---------------------------------------

def test_validate_rejects_cuda_when_no_gpu(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "linux")
    monkeypatch.setattr(
        platform_backend, "detect_platform",
        lambda: {"os": "linux", "arch": "x86_64", "has_cuda": False},
    )
    errors = asr_profiles.validate_asr_profile(
        {
            "name": "x",
            "engine": "whisper",
            "model_size": "large-v3",
            "mode": "same-lang",
            "language": "en",
            "device": "cuda",
        }
    )
    assert any("NVIDIA GPU" in e for e in errors)


def test_validate_allows_cuda_when_gpu_present(monkeypatch):
    monkeypatch.setattr(asr_profiles, "_detect_os", lambda: "linux")
    monkeypatch.setattr(
        platform_backend, "detect_platform",
        lambda: {"os": "linux", "arch": "x86_64", "has_cuda": True},
    )
    errors = asr_profiles.validate_asr_profile(
        {
            "name": "x",
            "engine": "whisper",
            "model_size": "large-v3",
            "mode": "same-lang",
            "language": "en",
            "device": "cuda",
        }
    )
    assert not any("NVIDIA GPU" in e for e in errors)


def test_validate_auto_and_cpu_always_pass(monkeypatch):
    monkeypatch.setattr(
        platform_backend, "detect_platform",
        lambda: {"os": "darwin", "arch": "arm64", "has_cuda": False},
    )
    for dev in ("auto", "cpu"):
        errors = asr_profiles.validate_asr_profile(
            {
                "name": "x",
                "engine": "whisper",
                "model_size": "large-v3",
                "mode": "same-lang",
                "language": "en",
                "device": dev,
            }
        )
        assert not any("NVIDIA GPU" in e for e in errors)
