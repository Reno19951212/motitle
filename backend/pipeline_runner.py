"""Pipeline Runner — v4.0 A1.

Linear stage executor that chains ASR → N MT → Glossary, persisting per-stage
output to file registry. Per design doc §4.

T7: fail-fast — stage exception persists failed StageOutput + re-raises
T8: Socket.IO progress at 5% granularity
T9: cancel_event between stages + inside MT/Glossary per-segment
"""
import time
import threading
import traceback
from typing import Callable, List, Optional

from stages import StageContext, StageOutput
from stages.asr_stage import ASRStage
from stages.mt_stage import MTStage
from stages.glossary_stage import GlossaryStage


def _socketio_emit(event: str, payload: dict) -> None:
    """Thin wrapper around app.socketio.emit() to keep import lazy."""
    try:
        import app as app_mod
        app_mod.socketio.emit(event, payload)
    except Exception:
        pass  # Socket emit failure non-fatal


def _persist_stage_output(file_id: str, stage_output: StageOutput) -> None:
    """Write stage output to file registry under _registry_lock.

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


def _make_progress_callback(file_id: str, pipeline_id: str, stage_index: int, stage_type: str):
    """Build a per-segment progress callback that emits at 5% milestones."""
    last_milestone = {"v": -1}

    def cb(done: int, total: int) -> None:
        if total <= 0:
            return
        pct = int((done / total) * 100)
        milestone = (pct // 5) * 5
        if milestone > last_milestone["v"]:
            last_milestone["v"] = milestone
            _socketio_emit("pipeline_stage_progress", {
                "file_id": file_id, "pipeline_id": pipeline_id,
                "stage_index": stage_index, "stage_type": stage_type,
                "percent": milestone, "segments_done": done, "segments_total": total,
            })

    return cb


def _check_cancel(cancel_event: Optional[threading.Event]) -> None:
    if cancel_event is not None and cancel_event.is_set():
        from jobqueue.queue import JobCancelled
        raise JobCancelled("Pipeline cancelled by user")


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
        start_from_stage: int = 0,
    ) -> List[StageOutput]:
        """Execute stages sequentially. Returns full stage_outputs list.

        If start_from_stage > 0, earlier stages are skipped and their segments
        are loaded from file_registry.stage_outputs[start_from_stage - 1].
        The /rerun endpoint truncates stage_outputs[start_from_stage..] before
        enqueueing, so persisted outputs for prior stages remain intact.
        """
        stage_outputs: List[StageOutput] = []
        segments: List[dict] = []

        # If resuming mid-pipeline, load segments from the last completed stage.
        if start_from_stage > 0:
            import app as app_mod
            with app_mod._registry_lock:
                entry = app_mod._file_registry.get(self._file_id, {})
                prior = entry.get("stage_outputs", {}).get(str(start_from_stage - 1), {})
                segments = list(prior.get("segments", []))

        # Stage 0 — ASR (skip if resuming from a later stage)
        if start_from_stage <= 0:
            _check_cancel(cancel_event)
            asr_profile = self._asr_manager.get(self._pipeline["asr_profile_id"])
            if asr_profile is None:
                raise ValueError(f"ASR profile {self._pipeline['asr_profile_id']} not found")
            asr_stage = ASRStage(asr_profile, self._audio_path)
            stage_out, segments = self._run_stage(
                stage=asr_stage, segments_in=[], stage_index=0,
                stage_type="asr", cancel_event=cancel_event, user_id=user_id,
            )
            stage_outputs.append(stage_out)

        # Stages 1..N — MT (skip stages already completed before start_from_stage)
        for i, mt_id in enumerate(self._pipeline.get("mt_stages", [])):
            idx = i + 1
            if idx < start_from_stage:
                continue  # already persisted from prior run
            _check_cancel(cancel_event)
            mt_profile = self._mt_manager.get(mt_id)
            if mt_profile is None:
                raise ValueError(f"MT profile {mt_id} not found")
            mt_stage = MTStage(mt_profile)
            stage_out, segments = self._run_stage(
                stage=mt_stage, segments_in=segments, stage_index=idx,
                stage_type="mt", cancel_event=cancel_event, user_id=user_id,
            )
            stage_outputs.append(stage_out)

        # Final stage — Glossary (if enabled)
        gloss_config = self._pipeline.get("glossary_stage", {})
        if gloss_config.get("enabled"):
            idx = 1 + len(self._pipeline.get("mt_stages", []))
            if idx >= start_from_stage:
                _check_cancel(cancel_event)
                gloss_stage = GlossaryStage(gloss_config, self._glossary_manager)
                stage_out, segments = self._run_stage(
                    stage=gloss_stage, segments_in=segments, stage_index=idx,
                    stage_type="glossary", cancel_event=cancel_event, user_id=user_id,
                )
                stage_outputs.append(stage_out)

        return stage_outputs

    def _run_stage(
        self,
        stage,
        segments_in: List[dict],
        stage_index: int,
        stage_type: str,
        cancel_event: Optional[threading.Event],
        user_id: Optional[int],
    ):
        """Execute one stage with fail-fast persistence + progress emit.

        Returns (StageOutput, segments_out). Re-raises on stage exception
        (after persisting failed status).
        """
        _socketio_emit("pipeline_stage_start", {
            "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
            "stage_index": stage_index, "stage_type": stage_type,
        })
        # T10: load per-(file,pipeline) overrides from registry
        import app as app_mod
        with app_mod._registry_lock:
            file_entry = app_mod._file_registry.get(self._file_id, {})
            all_overrides = file_entry.get("pipeline_overrides", {})
            overrides_for_this_pipeline = all_overrides.get(self._pipeline["id"], {})
        ctx = StageContext(
            file_id=self._file_id, user_id=user_id,
            pipeline_id=self._pipeline["id"], stage_index=stage_index,
            cancel_event=cancel_event,
            progress_callback=_make_progress_callback(
                self._file_id, self._pipeline["id"], stage_index, stage_type),
            pipeline_overrides=overrides_for_this_pipeline,
        )
        start_t = time.time()
        try:
            segments_out = stage.transform(segments_in, ctx)
        except Exception as exc:
            failed_out: StageOutput = {
                "stage_index": stage_index, "stage_type": stage_type,
                "stage_ref": stage.stage_ref, "status": "failed",
                "ran_at": start_t, "duration_seconds": time.time() - start_t,
                "segments": [], "quality_flags": [],
            }
            failed_out["error"] = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            _persist_stage_output(self._file_id, failed_out)
            _socketio_emit("pipeline_stage_done", {
                "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
                "stage_index": stage_index, "stage_type": stage_type,
                "status": "failed", "duration_seconds": failed_out["duration_seconds"],
            })
            raise
        stage_out: StageOutput = {
            "stage_index": stage_index, "stage_type": stage_type,
            "stage_ref": stage.stage_ref, "status": "done",
            "ran_at": start_t, "duration_seconds": time.time() - start_t,
            "segments": segments_out, "quality_flags": getattr(stage, "quality_flags", []),
        }
        _persist_stage_output(self._file_id, stage_out)
        _socketio_emit("pipeline_stage_done", {
            "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
            "stage_index": stage_index, "stage_type": stage_type,
            "status": "done", "duration_seconds": stage_out["duration_seconds"],
        })
        return stage_out, segments_out
