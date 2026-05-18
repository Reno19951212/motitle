"""BUG-030: stage_outputs bridge to legacy segments/translations/status fields.

After PipelineRunner.run() completes, stage outputs are stored under
entry['stage_outputs']. But downstream consumers (/segments, /translations,
/render, GET /api/files) read from the legacy entry['segments'] /
entry['translations'] / entry['status'] fields.

The bridge function _bridge_stage_outputs_to_legacy() must be called after
runner.run() to propagate data from the new stage_outputs structure to the
legacy fields that the rest of the app depends on.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_bridge_stage_outputs_populates_legacy_fields():
    """After bridge, entry has segments + translations + status='completed' + pipeline_id."""
    from app import _bridge_stage_outputs_to_legacy

    entry = {
        "id": "test-file-1",
        "stage_outputs": {
            "0": {
                "stage_index": 0,
                "stage_type": "asr",
                "status": "done",
                "segments": [
                    {"start": 0.0, "end": 2.0, "text": "Hello world"},
                    {"start": 2.0, "end": 4.0, "text": "Test pipeline"},
                ],
                "quality_flags": [],
            },
            "1": {
                "stage_index": 1,
                "stage_type": "mt",
                "status": "done",
                "segments": [
                    {"start": 0.0, "end": 2.0, "text": "你好世界"},
                    {"start": 2.0, "end": 4.0, "text": "測試管線"},
                ],
                "quality_flags": [],
            },
        },
        "status": "running",
    }

    _bridge_stage_outputs_to_legacy(entry, pipeline_id="p-test-1")

    assert entry["status"] == "completed"
    assert entry["pipeline_id"] == "p-test-1"

    # Segments (from ASR stage)
    assert len(entry["segments"]) == 2
    assert entry["segments"][0]["text"] == "Hello world"
    assert entry["segments"][1]["text"] == "Test pipeline"
    assert entry["segment_count"] == 2
    assert "Hello world" in entry["text"]

    # Translations (en_text from ASR, zh_text from MT, status=pending)
    assert len(entry["translations"]) == 2
    t0 = entry["translations"][0]
    assert t0["en_text"] == "Hello world"
    assert t0["zh_text"] == "你好世界"
    assert t0["status"] == "pending"
    assert t0["start"] == 0.0
    assert t0["end"] == 2.0

    t1 = entry["translations"][1]
    assert t1["en_text"] == "Test pipeline"
    assert t1["zh_text"] == "測試管線"
    assert t1["status"] == "pending"


def test_bridge_handles_asr_only_pipeline():
    """If only ASR stage ran (no MT stage), segments populated but translations empty."""
    from app import _bridge_stage_outputs_to_legacy

    entry = {
        "id": "test-2",
        "stage_outputs": {
            "0": {
                "stage_index": 0,
                "stage_type": "asr",
                "status": "done",
                "segments": [{"start": 0, "end": 1, "text": "Hi"}],
                "quality_flags": [],
            },
        },
        "status": "running",
    }

    _bridge_stage_outputs_to_legacy(entry, pipeline_id="p2")

    assert entry["status"] == "completed"
    assert entry["pipeline_id"] == "p2"
    assert len(entry["segments"]) == 1
    assert entry["segments"][0]["text"] == "Hi"
    # No MT stage → no translations generated
    assert entry.get("translations", []) == []


def test_bridge_handles_empty_stage_outputs():
    """No-op if stage_outputs missing/empty — status should NOT change."""
    from app import _bridge_stage_outputs_to_legacy

    entry = {"id": "test-3", "status": "running"}
    _bridge_stage_outputs_to_legacy(entry, pipeline_id="p3")

    # Nothing was bridged — status must remain unchanged
    assert entry["status"] == "running"
    assert "segments" not in entry
    assert "translations" not in entry


def test_bridge_sets_seg_idx_on_translations():
    """Each translation gets a seg_idx field so PATCH /segments/<id> can update en_text."""
    from app import _bridge_stage_outputs_to_legacy

    entry = {
        "id": "test-4",
        "stage_outputs": {
            "0": {
                "stage_index": 0, "stage_type": "asr", "status": "done",
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "A"},
                    {"start": 1.0, "end": 2.0, "text": "B"},
                    {"start": 2.0, "end": 3.0, "text": "C"},
                ],
                "quality_flags": [],
            },
            "1": {
                "stage_index": 1, "stage_type": "mt", "status": "done",
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "甲"},
                    {"start": 1.0, "end": 2.0, "text": "乙"},
                    {"start": 2.0, "end": 3.0, "text": "丙"},
                ],
                "quality_flags": [],
            },
        },
        "status": "running",
    }

    _bridge_stage_outputs_to_legacy(entry, pipeline_id="p4")

    for i, t in enumerate(entry["translations"]):
        assert t.get("seg_idx") == i, (
            f"translations[{i}].seg_idx should be {i}, got {t.get('seg_idx')}"
        )


def test_bridge_assigns_numeric_ids_to_segments():
    """Segments from ASR stage get an integer 'id' field for PATCH /segments/<id>."""
    from app import _bridge_stage_outputs_to_legacy

    entry = {
        "id": "test-5",
        "stage_outputs": {
            "0": {
                "stage_index": 0, "stage_type": "asr", "status": "done",
                "segments": [
                    {"start": 0.0, "end": 1.0, "text": "X"},
                    {"start": 1.0, "end": 2.0, "text": "Y"},
                ],
                "quality_flags": [],
            },
        },
        "status": "running",
    }

    _bridge_stage_outputs_to_legacy(entry, pipeline_id="p5")

    for i, seg in enumerate(entry["segments"]):
        assert "id" in seg, f"segments[{i}] missing 'id' field"
        assert isinstance(seg["id"], int), f"segments[{i}]['id'] should be int"


def test_bridge_uses_last_mt_stage_for_translations():
    """With multiple MT stages, the last MT stage output is used for translations."""
    from app import _bridge_stage_outputs_to_legacy

    entry = {
        "id": "test-6",
        "stage_outputs": {
            "0": {
                "stage_index": 0, "stage_type": "asr", "status": "done",
                "segments": [{"start": 0.0, "end": 1.0, "text": "Hello"}],
                "quality_flags": [],
            },
            "1": {
                "stage_index": 1, "stage_type": "mt", "status": "done",
                "segments": [{"start": 0.0, "end": 1.0, "text": "你好（初稿）"}],
                "quality_flags": [],
            },
            "2": {
                # Glossary stage — modifies segments but still stage_type="glossary"
                # The last MT stage is still stage "1"
                "stage_index": 2, "stage_type": "glossary", "status": "done",
                "segments": [{"start": 0.0, "end": 1.0, "text": "你好（詞彙校正版）"}],
                "quality_flags": [],
            },
        },
        "status": "running",
    }

    _bridge_stage_outputs_to_legacy(entry, pipeline_id="p6")

    assert len(entry["translations"]) == 1
    # MT stage (index 1) is the last MT stage — use that for zh_text
    assert entry["translations"][0]["zh_text"] == "你好（初稿）"
