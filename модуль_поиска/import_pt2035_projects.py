
from __future__ import annotations
import argparse, json
from pathlib import Path

def norm_id(p):
    return p.get("id") or p.get("url") or p.get("title")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", default="data/pt2035_projects.json")
    ap.add_argument("--all", default="data/all_projects.json")
    ap.add_argument("--backup", action="store_true")
    args = ap.parse_args()

    inp = Path(args.input)
    allp = Path(args.all)
    new_projects = json.loads(inp.read_text(encoding="utf-8"))
    existing = json.loads(allp.read_text(encoding="utf-8")) if allp.exists() else []

    if args.backup and allp.exists():
        allp.with_suffix(allp.suffix + ".bak").write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")

    by_id = {norm_id(p): p for p in existing}
    added = 0
    updated = 0
    for p in new_projects:
        key = norm_id(p)
        if key in by_id:
            by_id[key].update(p)
            updated += 1
        else:
            by_id[key] = p
            added += 1

    merged = list(by_id.values())
    allp.parent.mkdir(parents=True, exist_ok=True)
    allp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved {allp}: total={len(merged)}, added={added}, updated={updated}")

if __name__ == "__main__":
    main()
