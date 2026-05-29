"""
Pipeline management — v4.0 Phase 1.

Pipelines are standalone entities (one file per pipeline in
config/pipelines/<uuid>.json) that compose ASR + MT stages into an
end-to-end workflow: asr_profile_id + mt_stages[] + glossary_stage +
font_config. Includes cascade ref check and annotate_broken_refs for
cross-user visibility.

Per design doc §3.4 — replaces the legacy bundled profile schema.
Legacy profiles continue to work via backend/profiles.py during P1-P2;
P3 migration script will auto-split bundled profiles into asr_profile +
mt_profile + pipeline triples.
"""

import json
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from pipeline_schema_v5 import validate_v5_pipeline, promote_v4_to_v5

VALID_SUBTITLE_SOURCES = {"auto", "source", "target", "bilingual"}
VALID_BILINGUAL_ORDERS = {"source_top", "target_top"}
VALID_GLOSSARY_APPLY_ORDERS = {"explicit"}
VALID_GLOSSARY_APPLY_METHODS = {"string-match-then-llm"}
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 256
MAX_MT_STAGES = 8

_PIPE_LOCKS: dict = {}
_PIPE_MASTER_LOCK = threading.Lock()


def _get_pipe_lock(pipeline_id: str) -> threading.Lock:
    with _PIPE_MASTER_LOCK:
        lock = _PIPE_LOCKS.get(pipeline_id)
        if lock is None:
            lock = threading.Lock()
            _PIPE_LOCKS[pipeline_id] = lock
        return lock


def _validate_font(font: Any) -> list:
    errors: list = []
    if not isinstance(font, dict):
        return ["font_config must be object"]
    for key in ("family", "color", "outline_color"):
        if not isinstance(font.get(key), str) or not font.get(key).strip():
            errors.append(f"font_config.{key} required (string)")
    for key in ("size", "outline_width", "margin_bottom"):
        if not isinstance(font.get(key), int) or font.get(key) < 0:
            errors.append(f"font_config.{key} required (non-negative int)")
    src = font.get("subtitle_source")
    if src not in VALID_SUBTITLE_SOURCES:
        errors.append(f"font_config.subtitle_source must be one of {sorted(VALID_SUBTITLE_SOURCES)}")
    order = font.get("bilingual_order")
    if order not in VALID_BILINGUAL_ORDERS:
        errors.append(f"font_config.bilingual_order must be one of {sorted(VALID_BILINGUAL_ORDERS)}")
    return errors


def _validate_glossary_stage(stage: Any) -> list:
    errors: list = []
    if not isinstance(stage, dict):
        return ["glossary_stage must be object"]
    enabled = stage.get("enabled")
    if not isinstance(enabled, bool):
        errors.append("glossary_stage.enabled must be bool")
    glossary_ids = stage.get("glossary_ids", [])
    if not isinstance(glossary_ids, list):
        errors.append("glossary_stage.glossary_ids must be list")
    elif enabled is True and len(glossary_ids) == 0:
        errors.append("glossary_stage.glossary_ids must be non-empty when enabled=true")
    elif any(not isinstance(g, str) or not g for g in glossary_ids):
        errors.append("glossary_stage.glossary_ids entries must be non-empty strings")
    if stage.get("apply_order") not in VALID_GLOSSARY_APPLY_ORDERS:
        errors.append(f"glossary_stage.apply_order must be one of {sorted(VALID_GLOSSARY_APPLY_ORDERS)}")
    if stage.get("apply_method") not in VALID_GLOSSARY_APPLY_METHODS:
        errors.append(f"glossary_stage.apply_method must be one of {sorted(VALID_GLOSSARY_APPLY_METHODS)}")
    return errors


def validate_pipeline(data: Any, asr_manager=None, mt_manager=None, glossary_manager=None) -> list:
    """Module-level convenience helper — defers cross-ref check to managers if provided."""
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be object"]

    name = data.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        errors.append("name is required")
    elif len(name) > MAX_NAME_CHARS:
        errors.append(f"name must be {MAX_NAME_CHARS} chars or less")

    desc = data.get("description", "")
    if desc and (not isinstance(desc, str) or len(desc) > MAX_DESCRIPTION_CHARS):
        errors.append(f"description must be string of {MAX_DESCRIPTION_CHARS} chars or less")

    asr_id = data.get("asr_profile_id")
    if not asr_id or not isinstance(asr_id, str):
        errors.append("asr_profile_id is required")
    elif asr_manager is not None and asr_manager.get(asr_id) is None:
        errors.append(f"asr_profile_id refers to unknown ASR profile: {asr_id}")

    mt_stages = data.get("mt_stages", [])
    if not isinstance(mt_stages, list):
        errors.append("mt_stages must be list of MT profile ids")
    elif len(mt_stages) > MAX_MT_STAGES:
        errors.append(f"mt_stages must be {MAX_MT_STAGES} entries or fewer")
    else:
        for idx, mt_id in enumerate(mt_stages):
            if not isinstance(mt_id, str) or not mt_id:
                errors.append(f"mt_stages[{idx}] must be non-empty string")
            elif mt_manager is not None and mt_manager.get(mt_id) is None:
                errors.append(f"mt_stages[{idx}] refers to unknown MT profile: {mt_id}")

    gloss_stage = data.get("glossary_stage")
    if gloss_stage is None:
        errors.append("glossary_stage is required")
    else:
        gloss_errors = _validate_glossary_stage(gloss_stage)
        errors.extend(gloss_errors)
        if not gloss_errors and gloss_stage.get("enabled") and glossary_manager is not None:
            for idx, g_id in enumerate(gloss_stage.get("glossary_ids", [])):
                if glossary_manager.get(g_id) is None:
                    errors.append(f"glossary_stage.glossary_ids[{idx}] refers to unknown glossary: {g_id}")

    font = data.get("font_config")
    if font is None:
        errors.append("font_config is required")
    else:
        errors.extend(_validate_font(font))

    return errors


class PipelineManager:
    """Pipeline CRUD + cascade ref validation against ASR/MT/Glossary managers."""

    DIRNAME = "pipelines"
    SETTINGS_FILENAME = "settings.json"

    def __init__(self, config_dir, asr_manager=None, mt_manager=None, glossary_manager=None):
        # v5-A1 T24: manager args default to None so the manager can be used
        # for v5-only test contexts (where v4 cascade refs aren't checked).
        # When None, v4 validation `validate_pipeline` only runs schema-level
        # checks (still required for v4 path). v5 path uses
        # ``validate_v5_pipeline`` instead.
        self._config_dir = Path(config_dir)
        self._dir = self._config_dir / self.DIRNAME
        self._dir.mkdir(parents=True, exist_ok=True)
        self._settings_path = self._config_dir / self.SETTINGS_FILENAME
        self._asr_manager = asr_manager
        self._mt_manager = mt_manager
        self._glossary_manager = glossary_manager
        # v5-A1 T24: expose `dir` attr for v5-aware test fixtures that write
        # JSON directly (mirrors v5 manager modules which use `.dir`).
        self.dir = self._dir
        self._cache: dict = {}
        self._load_all()

    def _load_all(self):
        for fpath in self._dir.glob("*.json"):
            try:
                data = json.loads(fpath.read_text())
                if isinstance(data, dict) and data.get("id"):
                    self._cache[data["id"]] = data
            except Exception as exc:
                print(f"[pipelines] skip malformed file {fpath}: {exc}")

    def validate(self, data: Any) -> list:
        """Validate using injected managers for cross-ref check."""
        return validate_pipeline(
            data,
            asr_manager=self._asr_manager,
            mt_manager=self._mt_manager,
            glossary_manager=self._glossary_manager,
        )

    def _save(self, pipeline: dict):
        (self._dir / f"{pipeline['id']}.json").write_text(
            json.dumps(pipeline, ensure_ascii=False, indent=2)
        )

    def create(self, data: dict, user_id: Optional[int] = None, *, validate_refs: bool = True):
        """Create a pipeline.

        v4 path (default): validates name/description/asr_profile_id/mt_stages/
        glossary_stage/font_config and (when ``validate_refs=True`` AND
        managers were injected) cross-checks profile/glossary IDs. Returns
        the persisted v4 dict.

        v5 path (``data["version"] == 5``): validates against
        ``pipeline_schema_v5.validate_v5_pipeline`` (always — v5 has no
        opt-out at the manager layer; cross-ref check is owned by the
        route handler via ``check_cascade_refs``). Returns the pipeline_id
        string (matches the v5 test contract; v4 callers continue to
        receive the full dict).

        ``validate_refs=False`` (v4 only): skip ALL validation, store
        the payload as-is. Test seed shortcut for fixture data that doesn't
        need to pass the schema — production callers should always leave
        this True.
        """
        # v6 branch — store as-is (no separate schema validation; route handler is
        # the gatekeeper for v6-specific rules). Returns pipeline_id string like v5.
        if isinstance(data, dict) and data.get("pipeline_type") == "v6_vad_dual_asr":
            pid = str(uuid.uuid4())
            now = time.time()
            payload = {
                **data,
                "id": pid,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            }
            (self._dir / f"{pid}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._cache[pid] = payload
            return pid

        # v5 branch — store as-is after schema validation
        if isinstance(data, dict) and data.get("version") == 5:
            errors, _warnings = validate_v5_pipeline(data)
            if errors:
                raise ValueError("; ".join(errors))
            pid = str(uuid.uuid4())
            now = time.time()
            payload = {
                **data,
                "id": pid,
                "user_id": user_id,
                "created_at": now,
                "updated_at": now,
            }
            (self._dir / f"{pid}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            self._cache[pid] = payload
            return pid

        # v4 path
        if validate_refs:
            errors = self.validate(data)
            if errors:
                raise ValueError("; ".join(errors))
        now = int(time.time())
        # Defensive shape for fixture data with missing fields — only when
        # ``validate_refs=False`` AND fields absent. Production v4 callers
        # always provide the full dict.
        #
        # For ``validate_refs=False`` callers, preserve all extra keys so
        # v4→v5 promote (which reads ``asr_profile.language`` etc.) sees
        # the original payload. Validated production v4 callers already
        # pass the canonical keys, so the projection below is equivalent.
        pipeline = {
            **(data if not validate_refs else {}),
            "id": str(uuid.uuid4()),
            "name": (data.get("name") or "").strip(),
            "description": data.get("description", ""),
            "asr_profile_id": data.get("asr_profile_id"),
            "mt_stages": list(data.get("mt_stages", [])),
            "glossary_stage": dict(data.get("glossary_stage", {})),
            "font_config": dict(data.get("font_config", {})),
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }
        self._save(pipeline)
        self._cache[pipeline["id"]] = pipeline
        return dict(pipeline)

    def get(self, pipeline_id: str, *, as_v5: bool = False) -> Optional[dict]:
        """Return pipeline dict.

        Default (``as_v5=False``): backward-compatible v4 shape — returns
        the stored JSON as-is (whether it was written as v4 or v5). Existing
        callers (PipelineRunner, broken-refs annotation, routes that read
        ``mt_stages`` / ``asr_profile_id`` / ``glossary_stage``) keep working.

        Opt-in (``as_v5=True``): if the stored pipeline is v4 shape, run
        ``promote_v4_to_v5`` so the caller receives a v5 dict. v5 stored
        pipelines pass through unchanged. Malformed v4 data (e.g. missing
        ``id`` / ``name`` / ``asr_profile_id``) falls back to the raw stored
        dict — caller responsibility to handle.
        """
        cached = self._cache.get(pipeline_id)
        if cached is None:
            return None
        data = dict(cached)
        if as_v5 and data.get("version") != 5:
            try:
                data = promote_v4_to_v5(data)
            except ValueError:
                # v4 data too malformed to promote — return raw shape
                pass
        return data

    def list_all(self) -> list:
        return [dict(p) for p in self._cache.values()]

    def list_visible(self, user_id: Optional[int], is_admin: bool) -> list:
        if is_admin:
            return self.list_all()
        return [dict(p) for p in self._cache.values()
                if p.get("user_id") is None or p.get("user_id") == user_id]

    def can_view(self, pipeline_id: str, user_id: Optional[int], is_admin: bool) -> bool:
        p = self._cache.get(pipeline_id)
        if p is None:
            return False
        if is_admin:
            return True
        owner = p.get("user_id")
        return owner is None or owner == user_id

    def can_edit(self, pipeline_id: str, user_id: Optional[int], is_admin: bool) -> bool:
        p = self._cache.get(pipeline_id)
        if p is None:
            return False
        if is_admin:
            return True
        owner = p.get("user_id")
        return owner is not None and owner == user_id

    def update_if_owned(self, pipeline_id: str, user_id: Optional[int], is_admin: bool, patch: dict):
        with _get_pipe_lock(pipeline_id):
            if not self.can_edit(pipeline_id, user_id, is_admin):
                return False, ["permission denied"]
            current = self._cache.get(pipeline_id)
            # Extract free-form fields that bypass v4 schema validation.
            # refiner_prompt_override: {lang: str | None} — pipeline-level refiner
            # prompt override (v6); stored as-is, no content validation.
            extra_fields: dict = {}
            if "refiner_prompt_override" in patch:
                extra_fields["refiner_prompt_override"] = patch.pop("refiner_prompt_override")
            merged = {**current, **patch}
            # v5/v6 pipelines use their own validators; skip the v4 schema check
            # (v5 path: version==5; v6 path: pipeline_type present).
            is_v5_or_v6 = (
                merged.get("version") == 5
                or bool(merged.get("pipeline_type"))
            )
            if not is_v5_or_v6:
                errors = self.validate(merged)
                if errors:
                    # Restore patched key before returning so caller can inspect
                    if extra_fields:
                        patch["refiner_prompt_override"] = extra_fields.get("refiner_prompt_override")
                    return False, errors
            merged.update(extra_fields)
            merged["updated_at"] = int(time.time())
            merged["id"] = current["id"]
            merged["user_id"] = current["user_id"]
            merged["created_at"] = current["created_at"]
            self._save(merged)
            self._cache[pipeline_id] = merged
            return True, []

    def delete_if_owned(self, pipeline_id: str, user_id: Optional[int], is_admin: bool) -> bool:
        with _get_pipe_lock(pipeline_id):
            if not self.can_edit(pipeline_id, user_id, is_admin):
                return False
            fpath = self._dir / f"{pipeline_id}.json"
            if fpath.exists():
                fpath.unlink()
            self._cache.pop(pipeline_id, None)
            return True

    # ------------------------------------------------------------------
    # Active pipeline
    # ------------------------------------------------------------------

    def set_active(self, pipeline_id: str) -> Optional[dict]:
        """Set the active pipeline by id.

        Writes active_kind='pipeline_v6' + active_id to the shared
        config/settings.json (same file ProfileManager uses — only one
        entity is active at a time).

        Returns the pipeline dict, or None if pipeline_id is not found.
        """
        pipeline = self.get(pipeline_id)
        if pipeline is None:
            return None
        settings = self._read_settings()
        self._write_settings({
            **settings,
            "active_kind": "pipeline_v6",
            "active_id": pipeline_id,
        })
        return pipeline

    def _read_settings(self) -> dict:
        try:
            return json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"active_profile": None}

    def _write_settings(self, settings: dict) -> None:
        tmp_path = self._settings_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        import os
        os.replace(tmp_path, self._settings_path)

    def annotate_broken_refs(self, pipeline: dict, user_id: Optional[int], is_admin: bool) -> dict:
        """Return pipeline dict with extra `broken_refs` key listing
        sub-resources the requesting user cannot view.

        broken_refs shape:
        {
            "asr_profile_id": "<id>",    # only present if not visible
            "mt_stages": ["<id>", ...],  # subset of mt_stages user can't see
            "glossary_ids": ["<id>", ...],
        }
        """
        out = dict(pipeline)
        broken: dict = {}
        if is_admin:
            out["broken_refs"] = broken
            return out
        # v3.19 B-2: guard against None managers — PipelineManager may be
        # constructed without asr/mt/glossary managers for V6-only use.
        # When a manager is None, skip that ref-check (treat refs as visible).
        asr_id = pipeline.get("asr_profile_id")
        if asr_id and self._asr_manager is not None:
            if not self._asr_manager.can_view(asr_id, user_id, is_admin):
                broken["asr_profile_id"] = asr_id
        if self._mt_manager is not None:
            broken_mt = [
                mt_id for mt_id in pipeline.get("mt_stages", [])
                if not self._mt_manager.can_view(mt_id, user_id, is_admin)
            ]
            if broken_mt:
                broken["mt_stages"] = broken_mt
        if self._glossary_manager is not None:
            gloss_ids = pipeline.get("glossary_stage", {}).get("glossary_ids", [])
            broken_gloss = [
                g_id for g_id in gloss_ids
                if not self._glossary_manager.can_view(g_id, user_id, is_admin)
            ]
            if broken_gloss:
                broken["glossary_ids"] = broken_gloss
        out["broken_refs"] = broken
        return out
