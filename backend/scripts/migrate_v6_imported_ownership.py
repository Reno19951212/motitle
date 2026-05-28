"""One-shot: rewrite user_id=null on V6 imported pipeline + child profile JSONs.

The feat/frontend-redesign branch authored these under admin_p3 (id=627).
On dev, admin_p3 has id=627 in app.db but anyone should be able to use
shared V6 pipelines, so we mark them user_id=null (= shared)."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "config"
DIRS = ["pipelines", "refiner_profiles", "transcribe_profiles", "llm_profiles"]

for d in DIRS:
    for f in (ROOT / d).glob("*.json"):
        data = json.loads(f.read_text(encoding="utf-8"))
        if data.get("user_id") == 627:
            data["user_id"] = None
            f.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  rewrote user_id null: {f.relative_to(ROOT)}")
print("done")
