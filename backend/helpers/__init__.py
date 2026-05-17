"""Helper modules extracted from ``app.py`` during v4 A6 C2 T13a.

Each submodule focuses on a single concern:

* ``files`` — registry CRUD + per-user directory + ownership filter.
* ``registry`` — disk persistence + background flusher thread.
* ``media`` — Whisper model cache + ffprobe + ffmpeg audio extract.
* ``render_options`` — render-job TTL eviction + render-options validator.

All helpers read/write the canonical singletons that live in ``managers``
so that monkeypatching ``managers._file_registry`` (or its app.py alias)
is observed by every call site.
"""
