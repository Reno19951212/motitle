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
