"""Build a static Pages artifact, without npm or model inference."""
import json
import shutil
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]

def build(root=ROOT):
    data = json.loads((root / "data/catalog.json").read_text(encoding="utf-8"))
    if not isinstance(data.get("items"), list) or not data.get("generated_at"):
        raise ValueError("Catalog schema is invalid")
    ids = [row["id"] for row in data["items"]]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate record IDs")
    output = root / "dist"
    if output.exists():
        shutil.rmtree(output)
    shutil.copytree(root / "web", output)
    shutil.copytree(root / "data", output / "data")
    if (root / "daily").exists():
        shutil.copytree(root / "daily", output / "daily")
    (output / ".nojekyll").touch()
    print(f"Built {len(ids)} records")

if __name__ == "__main__":
    build()
