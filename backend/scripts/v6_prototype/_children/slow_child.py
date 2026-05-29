#!/usr/bin/env python3
"""Child harness that writes 1 stderr line/sec for N seconds then exits.

Reads `{"duration_sec": int}` from stdin, sleeps that many seconds while
emitting stderr heartbeats, then writes `{"ok": true}` to stdout.

Used to verify that the parent's drain pattern doesn't hang on a healthy
long-running child.
"""
import json
import sys
import time


def main() -> None:
    raw = sys.stdin.read()
    params = json.loads(raw or "{}")
    duration_sec = int(params.get("duration_sec", 30))

    for i in range(duration_sec):
        sys.stderr.write(f"[heartbeat {i:4d}/{duration_sec}]\n")
        sys.stderr.flush()
        time.sleep(1)

    json.dump({"ok": True, "duration_sec": duration_sec},
              sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
