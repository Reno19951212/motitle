"""
MT profile management — v4.0 Phase 1.

MT profiles are standalone entities (one file per profile in
config/mt_profiles/<uuid>.json) that describe a machine translation
configuration: qwen3.5-35b-a3b only (Phase 1 scope), same-lang
transformation, system_prompt and user_message_template with {text}
placeholder, batch_size, temperature, parallel_batches knobs.

Per design doc §3.2 — replaces the `translation` sub-block of the legacy
bundled profile schema. Legacy profiles continue to work via backend/profiles.py
during P1-P2; P3 migration script will auto-split bundled profiles into
asr_profile + mt_profile + pipeline triples.
"""
