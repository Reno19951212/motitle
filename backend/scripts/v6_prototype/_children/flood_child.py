#!/usr/bin/env python3
"""Child harness that floods stderr by N KB then writes a tiny stdout JSON.

Reads `{"stderr_kb": int}` from stdin, writes that many KB to stderr (line-buffered),
then writes `{"ok": true, "wrote_kb": N}` to stdout and exits 0.

Simulates the production deadlock condition where Qwen3 subprocess
accumulates per-region stderr logs that exceed the macOS pipe buffer (~16 KB).
"""
import json
import sys


def main() -> None:
    raw = sys.stdin.read()
    params = json.loads(raw or "{}")
    stderr_kb = int(params.get("stderr_kb", 0))

    # Each line ~50 chars + newline ≈ 64 bytes (incl. ANSI/space). 16 lines per KB.
    line = ("X" * 60) + "\n"
    lines_per_kb = max(1, 1024 // len(line))
    total_lines = stderr_kb * lines_per_kb

    written = 0
    for i in range(total_lines):
        sys.stderr.write(f"[line {i:6d}] {line}")
        sys.stderr.flush()
        written += len(line) + 16  # approx prefix overhead

    json.dump({"ok": True, "wrote_kb": stderr_kb, "wrote_bytes": written},
              sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
