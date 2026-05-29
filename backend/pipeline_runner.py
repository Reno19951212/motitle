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

# v5-A2 imports
from stages.v5.asr_primary_stage import ASRPrimaryStage
from stages.v5.asr_secondary_stage import ASRSecondaryStage
from stages.v5.asr_verifier_stage import ASRVerifierStage
from stages.v5.refiner_stage import RefinerStage
from stages.v5.translator_stage import TranslatorStage


# Module-level alias used by _run_v6 for qwen3_context resolution.
# In production this is always None and app._file_registry is used.
# Tests patch this to inject a fake registry without importing app.
_file_registry: Optional[dict] = None


def _app_module():
    """Return the *running* app module — handles being launched as __main__.

    When backend is started via `python app.py`, app.py is loaded under the
    module name '__main__'. A later `import app` triggers Python to load
    app.py AGAIN as a separate module 'app', creating a second
    `_file_registry` that's completely disjoint from the live one. Any V6
    write that goes through the 'app' module silently no-ops because the
    entry only exists in __main__'s registry.

    This helper returns __main__ when it carries the registry, otherwise
    falls back to the normal import (covers the case where another script
    imports pipeline_runner without launching the Flask app).
    """
    import sys
    main = sys.modules.get('__main__')
    if main is not None and hasattr(main, '_file_registry') and hasattr(main, '_save_registry'):
        return main
    return sys.modules.get('app') or __import__('app')


def _socketio_emit(event: str, payload: dict) -> None:
    """Thin wrapper around app.socketio.emit() to keep import lazy."""
    try:
        app_mod = _app_module()
        app_mod.socketio.emit(event, payload)
    except Exception:
        pass  # Socket emit failure non-fatal
    # ── unified progress contract bridge ──
    if event in ("pipeline_stage_progress", "pipeline_stage_done"):
        try:
            from progress_adapter import get_adapter, report_from_v6_stage
            stage_pct = 100 if event == "pipeline_stage_done" else int(payload.get("percent", 0))
            report_from_v6_stage(
                get_adapter(),
                file_id=payload["file_id"],
                job_id=str(payload.get("pipeline_id", "")),
                stage_index=int(payload.get("stage_index", 0)),
                stage_type=str(payload.get("stage_type", "")),
                stage_percent=stage_pct,
                total_stages=5,
            )
        except Exception:
            pass


def _persist_stage_output(file_id: str, stage_output: StageOutput) -> None:
    """Write stage output to file registry under _registry_lock.

    Uses string keys for stage_outputs dict so JSON round-trip is identity-preserving
    (json.dumps converts int keys to strings anyway, so we use str() upfront).
    """
    app_mod = _app_module()
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
        # v4 managers (may be None for v5-only pipelines)
        self._asr_manager = managers.get("asr_manager")
        self._mt_manager = managers.get("mt_manager")
        self._glossary_manager = managers.get("glossary_manager")
        # v5 managers (may be None for v4-only pipelines)
        self._transcribe_profile_manager = managers.get("transcribe_profile_manager")
        self._translator_profile_manager = managers.get("translator_profile_manager")
        self._refiner_profile_manager = managers.get("refiner_profile_manager")
        self._verifier_profile_manager = managers.get("verifier_profile_manager")
        self._llm_profile_manager = managers.get("llm_profile_manager")

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

        v5 dispatch: when pipeline.version == 5, delegate to _run_v5 (DAG).
        """
        if self._pipeline.get("pipeline_type") == "v6_vad_dual_asr":
            if start_from_stage != 0:
                raise NotImplementedError("v6 resume from stage not yet supported")
            return self._run_v6(user_id=user_id, cancel_event=cancel_event)

        if self._pipeline.get("version") == 5:
            if start_from_stage != 0:
                raise NotImplementedError("v5 resume from stage not yet supported (A2 scope)")
            return self._run_v5(user_id=user_id, cancel_event=cancel_event)

        stage_outputs: List[StageOutput] = []
        segments: List[dict] = []

        # If resuming mid-pipeline, load segments from the last completed stage.
        if start_from_stage > 0:
            app_mod = _app_module()
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
        app_mod = _app_module()
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

    # ------------------------------------------------------------------
    # v5-A2 DAG executor
    # ------------------------------------------------------------------
    def _run_v5(
        self,
        user_id: Optional[int],
        cancel_event: Optional[threading.Event] = None,
    ) -> List[StageOutput]:
        """Execute v5 DAG pipeline.

        Returns flat list of StageOutput (same shape as v4); persists each
        stage to file registry as it completes.
        """
        stage_outputs: List[StageOutput] = []
        stage_index = 0
        source_lang = self._pipeline["asr_primary"]["source_lang"]

        # 1. ASR primary (always)
        _check_cancel(cancel_event)
        primary_profile = self._transcribe_profile_manager.get(
            self._pipeline["asr_primary"]["transcribe_profile_id"]
        )
        if primary_profile is None:
            raise ValueError("asr_primary transcribe profile not found")
        primary_stage = ASRPrimaryStage(primary_profile, self._audio_path)
        primary_out, primary_segments = self._run_stage(
            stage=primary_stage, segments_in=[], stage_index=stage_index,
            stage_type="asr_primary", cancel_event=cancel_event, user_id=user_id,
        )
        stage_outputs.append(primary_out)
        stage_index += 1

        # 2. ASR secondary (optional)
        secondary_segments: List[dict] = []
        secondary_cfg = self._pipeline.get("asr_secondary")
        if secondary_cfg:
            _check_cancel(cancel_event)
            secondary_profile = self._transcribe_profile_manager.get(
                secondary_cfg["transcribe_profile_id"]
            )
            if secondary_profile is None:
                raise ValueError("asr_secondary transcribe profile not found")
            secondary_stage = ASRSecondaryStage(secondary_profile, self._audio_path)
            secondary_out, secondary_segments = self._run_stage(
                stage=secondary_stage, segments_in=[], stage_index=stage_index,
                stage_type="asr_secondary", cancel_event=cancel_event, user_id=user_id,
            )
            stage_outputs.append(secondary_out)
            stage_index += 1

        # 3. ASR verifier (optional; requires secondary)
        canonical_source = primary_segments
        verifier_cfg = self._pipeline.get("asr_verifier")
        if verifier_cfg and secondary_segments:
            _check_cancel(cancel_event)
            llm_profile = self._llm_profile_manager.get(verifier_cfg["llm_profile_id"])
            if llm_profile is None:
                raise ValueError("asr_verifier llm_profile not found")
            # Build synthetic verifier profile from inline config
            verifier_inline = {
                "id": verifier_cfg["llm_profile_id"],
                "lang": source_lang,
                "llm_profile_id": verifier_cfg["llm_profile_id"],
                "prompt_template_id": verifier_cfg["prompt_template_id"],
            }
            verifier_stage = ASRVerifierStage(
                verifier_profile=verifier_inline,
                llm_profile=llm_profile,
            )
            # Pass secondary segments via reserved override key (see ASRVerifierStage)
            from stages.v5.asr_verifier_stage import SECONDARY_KEY
            verifier_overrides = {SECONDARY_KEY: secondary_segments}
            verified_out, canonical_source = self._run_stage_v5(
                stage=verifier_stage, segments_in=primary_segments, stage_index=stage_index,
                stage_type="asr_verifier", cancel_event=cancel_event, user_id=user_id,
                extra_overrides=verifier_overrides,
            )
            stage_outputs.append(verified_out)
            stage_index += 1

        # 4. For each target_lang: refinement chain → (if lang != source) translator
        by_lang: dict = {}
        for target_lang in self._pipeline.get("target_languages", []):
            if target_lang == source_lang:
                lang_segments = list(canonical_source)
            else:
                translator_cfg = self._pipeline.get("translators", {}).get(target_lang)
                if translator_cfg is None:
                    raise ValueError(f"translator for target_languages '{target_lang}' missing")
                translator_profile = self._translator_profile_manager.get(
                    translator_cfg["translator_profile_id"]
                )
                if translator_profile is None:
                    raise ValueError(f"translator profile for {target_lang} not found")
                llm_profile = self._llm_profile_manager.get(translator_profile["llm_profile_id"])
                if llm_profile is None:
                    raise ValueError(f"translator's llm_profile not found ({target_lang})")
                _check_cancel(cancel_event)
                translator_stage = TranslatorStage(translator_profile=translator_profile, llm_profile=llm_profile)
                tr_out, lang_segments = self._run_stage(
                    stage=translator_stage, segments_in=canonical_source, stage_index=stage_index,
                    stage_type=translator_stage.stage_type,
                    cancel_event=cancel_event, user_id=user_id,
                )
                stage_outputs.append(tr_out)
                stage_index += 1

            # Refinement chain for this lang
            for refiner_entry in self._pipeline.get("refinements", {}).get(target_lang, []):
                refiner_profile = self._refiner_profile_manager.get(refiner_entry["refiner_profile_id"])
                if refiner_profile is None:
                    raise ValueError(f"refiner profile for {target_lang} not found")
                llm_profile = self._llm_profile_manager.get(refiner_profile["llm_profile_id"])
                if llm_profile is None:
                    raise ValueError(f"refiner's llm_profile not found ({target_lang})")
                _check_cancel(cancel_event)
                refiner_stage = RefinerStage(refiner_profile=refiner_profile, llm_profile=llm_profile)
                rf_out, lang_segments = self._run_stage(
                    stage=refiner_stage, segments_in=lang_segments, stage_index=stage_index,
                    stage_type=refiner_stage.stage_type,
                    cancel_event=cancel_event, user_id=user_id,
                )
                stage_outputs.append(rf_out)
                stage_index += 1

            by_lang[target_lang] = lang_segments

        # Persist by_lang dict to file registry for downstream consumers
        self._persist_by_lang(by_lang, source_lang=source_lang, source_segments=canonical_source)
        return stage_outputs

    def _run_stage_v5(
        self, stage, segments_in, stage_index, stage_type,
        cancel_event, user_id, extra_overrides: dict,
    ):
        """Same as _run_stage but merges extra_overrides into context.pipeline_overrides."""
        app_mod = _app_module()
        with app_mod._registry_lock:
            file_entry = app_mod._file_registry.get(self._file_id, {})
            all_overrides = file_entry.get("pipeline_overrides", {})
            overrides_for_this_pipeline = dict(all_overrides.get(self._pipeline["id"], {}))
        overrides_for_this_pipeline.update(extra_overrides)
        _socketio_emit("pipeline_stage_start", {
            "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
            "stage_index": stage_index, "stage_type": stage_type,
        })
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

    # ------------------------------------------------------------------
    # v6 DAG executor
    # ------------------------------------------------------------------
    def _run_v6(
        self,
        user_id: Optional[int],
        cancel_event: Optional[threading.Event] = None,
    ) -> List[StageOutput]:
        """Execute v6 DAG: VAD → qwen3/region → mlx → merge → refiner(s) → persist.

        Pipeline JSON shape (pipeline_type == "v6_vad_dual_asr"):
          vad:         VAD params dict
          qwen3_asr:   language / context / post_s2hk
          asr_primary: {transcribe_profile_id, source_lang}  — mlx-whisper full audio
          refinements: {lang: [{refiner_profile_id}]}
          target_languages: [lang]
        """
        from stages.v6.silero_vad_stage import SileroVadStage
        from stages.v6.qwen3_per_region_stage import Qwen3PerRegionStage
        from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage
        from stages.v5.refiner_stage import RefinerStage

        stage_outputs: List[StageOutput] = []
        stage_index = 0
        source_lang = self._pipeline.get("source_lang", "zh")
        audio_path = self._audio_path
        # Used by VAD and qwen3 stages to locate the audio file
        audio_overrides = {"audio_path": audio_path}

        # Stage 0: VAD
        _check_cancel(cancel_event)
        vad_stage = SileroVadStage(dict(self._pipeline.get("vad", {})))
        vad_out, vad_regions = self._run_stage_v5(
            stage=vad_stage, segments_in=[], stage_index=stage_index,
            stage_type="vad", cancel_event=cancel_event, user_id=user_id,
            extra_overrides=audio_overrides,
        )
        stage_outputs.append(vad_out)
        stage_index += 1

        # Stage 1A: qwen3 per-region (receives VAD regions, returns char-level segs)
        # --- qwen3_context 3-level resolution ---
        # Priority: file_override > pipeline_default > ""
        qwen3_profile = dict(self._pipeline.get("qwen3_asr", {}))
        # Resolve file-level registry (test-patchable module alias takes precedence)
        import pipeline_runner as _self_mod
        _registry = _self_mod._file_registry
        if _registry is None:
            _app_mod = _app_module()
            with _app_mod._registry_lock:
                _file_entry = dict(_app_mod._file_registry.get(self._file_id, {}))
        else:
            _file_entry = dict(_registry.get(self._file_id, {}))
        _file_overrides = _file_entry.get("prompt_overrides") or {}
        _file_qwen3_ctx = _file_overrides.get("qwen3_context", "")
        if _file_qwen3_ctx:
            qwen3_profile["context"] = _file_qwen3_ctx
        # -----------------------------------------
        _check_cancel(cancel_event)
        qwen3_stage = Qwen3PerRegionStage(qwen3_profile)
        qwen3_out, qwen3_chars = self._run_stage_v5(
            stage=qwen3_stage, segments_in=vad_regions, stage_index=stage_index,
            stage_type="qwen3_per_region", cancel_event=cancel_event, user_id=user_id,
            extra_overrides=audio_overrides,
        )
        stage_outputs.append(qwen3_out)
        stage_index += 1

        # Stage 1B: mlx-whisper full audio (time grid; text is discarded by merge stage)
        _check_cancel(cancel_event)
        primary_profile = self._transcribe_profile_manager.get(
            self._pipeline["asr_primary"]["transcribe_profile_id"]
        )
        if primary_profile is None:
            raise ValueError("v6: asr_primary transcribe profile not found")
        mlx_stage = ASRPrimaryStage(primary_profile, audio_path)
        mlx_out, mlx_segs = self._run_stage(
            stage=mlx_stage, segments_in=[], stage_index=stage_index,
            stage_type="asr_primary", cancel_event=cancel_event, user_id=user_id,
        )
        stage_outputs.append(mlx_out)
        stage_index += 1

        # Stage 2: Time-anchored merge (mlx time grid + qwen3 chars → subtitle segs)
        _check_cancel(cancel_event)
        merge_stage = TimeAnchoredMergeStage({})
        merge_overrides = {"__qwen3_chars": qwen3_chars}
        merge_out, merged_segs = self._run_stage_v5(
            stage=merge_stage, segments_in=mlx_segs, stage_index=stage_index,
            stage_type="time_anchored_merge", cancel_event=cancel_event, user_id=user_id,
            extra_overrides=merge_overrides,
        )
        stage_outputs.append(merge_out)
        stage_index += 1

        canonical_source = merged_segs

        # Stage 3+: Per target_lang refinement chain (no translator in v6 — qwen3 is sole
        # authority; cross-lingual targets may be added in a future sub-phase)
        by_lang: dict = {}
        for target_lang in self._pipeline.get("target_languages", []):
            lang_segments = list(canonical_source)

            for refiner_entry in self._pipeline.get("refinements", {}).get(target_lang, []):
                refiner_profile = self._refiner_profile_manager.get(
                    refiner_entry["refiner_profile_id"]
                )
                if refiner_profile is None:
                    raise ValueError(f"v6: refiner profile for {target_lang} not found")
                llm_profile = self._llm_profile_manager.get(refiner_profile["llm_profile_id"])
                if llm_profile is None:
                    raise ValueError(f"v6: refiner's llm_profile not found ({target_lang})")
                _check_cancel(cancel_event)

                # --- Refiner prompt 3-level resolution ---
                # Priority: file_override > pipeline_override > template_default (empty)
                # File-level override: file_registry[fid]["prompt_overrides"]["refiners.<lang>"]
                # Pipeline-level: pipeline["refiner_prompt_override"][lang]
                # Template default: loaded by RefinerStage.transform() from prompt_template_id
                _override_key = f"refiners.{target_lang}"
                _resolved_refiner_prompt = None
                # Level 1: file-level override
                # Mirror qwen3_context pattern: module-level alias first, then app fallback
                import pipeline_runner as _self_mod2
                _reg = _self_mod2._file_registry
                if _reg is None:
                    _app_mod2 = _app_module()
                    with _app_mod2._registry_lock:
                        _fentry_refiner = dict(_app_mod2._file_registry.get(self._file_id, {}))
                else:
                    _fentry_refiner = dict(_reg.get(self._file_id, {}))
                _fentry_overrides = _fentry_refiner.get("prompt_overrides") or {}
                _resolved_refiner_prompt = _fentry_overrides.get(_override_key) or None
                if not _resolved_refiner_prompt:
                    # Level 2: pipeline-level override
                    _pipe_override = self._pipeline.get("refiner_prompt_override") or {}
                    _resolved_refiner_prompt = _pipe_override.get(target_lang) or None
                # Level 3: template default — RefinerStage handles this automatically when
                # no override is injected (empty/absent key in extra_overrides)
                # RefinerStage.transform() reads:
                #   context.pipeline_overrides.get("refiners", {}).get(lang)
                # So we must use nested format {"refiners": {lang: prompt}}, not flat
                # dot-notation {"refiners.zh": prompt} which RefinerStage cannot see.
                refiner_extra: dict = {}
                if _resolved_refiner_prompt:
                    refiner_extra["refiners"] = {target_lang: _resolved_refiner_prompt}
                # -----------------------------------------

                refiner_stage = RefinerStage(
                    refiner_profile=refiner_profile,
                    llm_profile=llm_profile,
                )
                rf_out, lang_segments = self._run_stage_v5(
                    stage=refiner_stage, segments_in=lang_segments,
                    stage_index=stage_index, stage_type=refiner_stage.stage_type,
                    cancel_event=cancel_event, user_id=user_id,
                    extra_overrides=refiner_extra,
                )
                stage_outputs.append(rf_out)
                stage_index += 1

            by_lang[target_lang] = lang_segments

        self._persist_by_lang(
            by_lang, source_lang=source_lang, source_segments=canonical_source
        )
        return stage_outputs

    def _persist_by_lang(
        self, by_lang: dict, source_lang: str, source_segments: List[dict],
    ) -> None:
        """Persist v5 multi-lang translations to file registry.

        Shape: file_registry[fid]['translations'] = [
            {idx, start, end, source_lang, source_text,
             by_lang: {lang: {text, status, flags}}},
            ...
        ]
        """
        app_mod = _app_module()
        if not by_lang:
            return
        n = len(source_segments)
        rows: list = []
        for i in range(n):
            src_seg = source_segments[i]
            row = {
                "idx": i,
                "start": src_seg.get("start"),
                "end": src_seg.get("end"),
                "source_lang": source_lang,
                "source_text": src_seg.get("text", ""),
                "by_lang": {},
            }
            for lang, segs in by_lang.items():
                if i < len(segs):
                    row["by_lang"][lang] = {
                        "text": segs[i].get("text", ""),
                        "status": "pending",
                        "flags": list(segs[i].get("flags", []) or []),
                    }
            # v3.19 Sprint 1 — mirror by_lang.<source_lang>.* to top-level legacy
            # fields so /api/files/<id>/translations + subtitle exports +
            # approve-all + render (which all still read t["zh_text"] / t["status"])
            # work for V6 files.  Mirroring at write time (vs reading both at every
            # site) keeps the change surface minimal and Profile-mode untouched.
            primary_lang = source_lang  # for 賽馬 pipeline this is "zh"
            primary = row["by_lang"].get(primary_lang)
            if primary is not None:
                row[f"{primary_lang}_text"] = primary.get("text", "")
                row["status"] = primary.get("status", "pending")
                if primary.get("flags"):
                    row["flags"] = list(primary["flags"])
            rows.append(row)
        with app_mod._registry_lock:
            entry = app_mod._file_registry.get(self._file_id)
            if entry is None:
                return
            entry["translations"] = rows
            app_mod._save_registry()
        _socketio_emit("pipeline_complete_v5", {
            "file_id": self._file_id, "pipeline_id": self._pipeline["id"],
            "languages": list(by_lang.keys()),
            "segments_per_lang": {lang: len(segs) for lang, segs in by_lang.items()},
        })
