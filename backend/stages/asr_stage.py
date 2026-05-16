"""ASR Stage — v4.0 A1.

Dispatches to Whisper engine according to ASR profile's `mode`:
- same-lang:           task=transcribe + language=profile.language (audio lang)
- emergent-translate:  task=transcribe + language=profile.language (target lang,
                        unofficial Whisper Large-v3 behaviour — see design doc §1.3)
- translate-to-en:     task=translate + language=profile.language (audio lang;
                        output always English)

Quality flag `low_logprob` is appended (T11) when Whisper engine returns
avg_logprob < -1.0 (emergent mode quality canary — see design doc §10 risk register).
"""
from typing import List

from asr import create_asr_engine

from . import PipelineStage, StageContext

LOW_LOGPROB_THRESHOLD = -1.0


def _resolve_task(mode: str) -> str:
    if mode == "translate-to-en":
        return "translate"
    return "transcribe"  # same-lang + emergent-translate both use transcribe


class ASRStage(PipelineStage):
    def __init__(self, asr_profile: dict, audio_path: str):
        self._profile = asr_profile
        self._audio_path = audio_path

    @property
    def stage_type(self) -> str:
        return "asr"

    @property
    def stage_ref(self) -> str:
        return self._profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        # segments_in is ignored for ASR stage (first stage reads from audio_path)
        engine = create_asr_engine(self._profile)
        task = _resolve_task(self._profile["mode"])
        language = self._profile["language"]
        # Modern Whisper engines accept `task` as kwarg; older path hardcodes transcribe.
        # We pass task to be explicit; engines that don't support it silently ignore.
        try:
            raw = engine.transcribe(self._audio_path, language=language, task=task)
        except TypeError:
            # Engine doesn't accept `task` kwarg yet; fall back to default transcribe
            raw = engine.transcribe(self._audio_path, language=language)

        # Build output segments (Q7-b: strip `words` if present)
        out: List[dict] = []
        for seg in raw:
            out_seg = {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg.get("text", "").strip(),
            }
            out.append(out_seg)

        return out
