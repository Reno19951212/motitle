# resolve_repo_local_first — offline-safe model resolution（2026-06-10 HF SSL 事故）
import pytest

from asr import mlx_whisper_engine as mwe


def test_returns_local_path_when_cached(monkeypatch):
    monkeypatch.setattr("huggingface_hub.snapshot_download",
                        lambda repo, local_files_only: "/local/snap/" + repo)
    assert mwe.resolve_repo_local_first("org/model") == "/local/snap/org/model"


def test_falls_back_to_repo_id_when_not_cached(monkeypatch):
    def boom(repo, local_files_only):
        raise FileNotFoundError("not cached")
    monkeypatch.setattr("huggingface_hub.snapshot_download", boom)
    assert mwe.resolve_repo_local_first("org/model") == "org/model"


def test_engine_uses_resolved_repo(monkeypatch):
    monkeypatch.setattr(mwe, "resolve_repo_local_first", lambda repo: "/snap/x")
    eng = mwe.MlxWhisperEngine({"model_size": "large-v3"})
    assert eng._repo == "/snap/x"
