"""
ASR profile management — v4.0 Phase 1.

ASR profiles are standalone entities (one file per profile in
config/asr_profiles/<uuid>.json) that describe a Whisper configuration:
engine, model_size, mode (same-lang / emergent-translate / translate-to-en),
language hint, initial_prompt, etc.

Per design doc §3.1 — replaces the `asr` sub-block of the legacy bundled
profile schema. Legacy profiles continue to work via backend/profiles.py
during P1-P2; P3 migration script will auto-split bundled profiles into
asr_profile + mt_profile + pipeline triples.
"""
