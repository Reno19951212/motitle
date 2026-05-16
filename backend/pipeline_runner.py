"""Pipeline Runner — v4.0 A1.

Linear stage executor that chains ASR → N MT → Glossary, persisting per-stage
output to file registry. Per design doc §4.
"""
import time
import threading
from typing import Callable, List, Optional

from stages import StageContext, StageOutput
from stages.asr_stage import ASRStage
from stages.mt_stage import MTStage
from stages.glossary_stage import GlossaryStage


def _persist_stage_output(file_id: str, stage_output: StageOutput) -> None:
    """Write stage output to file registry.

    Uses string keys for stage_outputs dict so JSON round-trip is identity-preserving
    (json.dumps converts int keys to strings anyway, so we use str() upfront).
    """
    import app as app_mod
    with app_mod._registry_lock:
        entry = app_mod._file_registry.get(file_id)
        if entry is None:
            return
        outputs = entry.setdefault("stage_outputs", {})
        outputs[str(stage_output["stage_index"])] = dict(stage_output)
        app_mod._save_registry()


class PipelineRunner:
    def __init__(self, pipeline: dict, file_id: str, audio_path: str, managers: dict):
        self._pipeline = pipeline
        self._file_id = file_id
        self._audio_path = audio_path
        self._asr_manager = managers["asr_manager"]
        self._mt_manager = managers["mt_manager"]
        self._glossary_manager = managers["glossary_manager"]

    def run(
        self,
        user_id: Optional[int],
        cancel_event: Optional[threading.Event] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[StageOutput]:
        """Execute all stages sequentially. Returns full stage_outputs list."""
        stage_outputs: List[StageOutput] = []
        segments: List[dict] = []  # accumulates between stages

        # Stage 0 — ASR
        asr_profile = self._asr_manager.get(self._pipeline["asr_profile_id"])
        if asr_profile is None:
            raise ValueError(f"ASR profile {self._pipeline['asr_profile_id']} not found")
        ctx = StageContext(file_id=self._file_id, user_id=user_id,
                           pipeline_id=self._pipeline["id"], stage_index=0,
                           cancel_event=cancel_event,
                           progress_callback=progress_callback,
                           pipeline_overrides={})
        asr_stage = ASRStage(asr_profile, self._audio_path)
        start_t = time.time()
        segments = asr_stage.transform([], ctx)
        stage_out: StageOutput = {
            "stage_index": 0, "stage_type": "asr",
            "stage_ref": asr_stage.stage_ref, "status": "done",
            "ran_at": start_t, "duration_seconds": time.time() - start_t,
            "segments": segments, "quality_flags": [],
        }
        stage_outputs.append(stage_out)
        _persist_stage_output(self._file_id, stage_out)

        # Stages 1..N — MT
        for i, mt_id in enumerate(self._pipeline.get("mt_stages", [])):
            mt_profile = self._mt_manager.get(mt_id)
            if mt_profile is None:
                raise ValueError(f"MT profile {mt_id} not found")
            idx = i + 1
            ctx = StageContext(file_id=self._file_id, user_id=user_id,
                               pipeline_id=self._pipeline["id"], stage_index=idx,
                               cancel_event=cancel_event,
                               progress_callback=progress_callback,
                               pipeline_overrides={})
            mt_stage = MTStage(mt_profile)
            start_t = time.time()
            segments = mt_stage.transform(segments, ctx)
            stage_out = {
                "stage_index": idx, "stage_type": "mt",
                "stage_ref": mt_stage.stage_ref, "status": "done",
                "ran_at": start_t, "duration_seconds": time.time() - start_t,
                "segments": segments, "quality_flags": [],
            }
            stage_outputs.append(stage_out)
            _persist_stage_output(self._file_id, stage_out)

        # Final stage — Glossary (if enabled)
        gloss_config = self._pipeline.get("glossary_stage", {})
        if gloss_config.get("enabled"):
            idx = 1 + len(self._pipeline.get("mt_stages", []))
            ctx = StageContext(file_id=self._file_id, user_id=user_id,
                               pipeline_id=self._pipeline["id"], stage_index=idx,
                               cancel_event=cancel_event,
                               progress_callback=progress_callback,
                               pipeline_overrides={})
            gloss_stage = GlossaryStage(gloss_config, self._glossary_manager)
            start_t = time.time()
            segments = gloss_stage.transform(segments, ctx)
            stage_out = {
                "stage_index": idx, "stage_type": "glossary",
                "stage_ref": gloss_stage.stage_ref, "status": "done",
                "ran_at": start_t, "duration_seconds": time.time() - start_t,
                "segments": segments, "quality_flags": [],
            }
            stage_outputs.append(stage_out)
            _persist_stage_output(self._file_id, stage_out)

        return stage_outputs
