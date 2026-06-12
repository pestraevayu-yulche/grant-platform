"""Sync manually edited pt2035_projects.json into data/all_projects.json.

Usage:
    python sync_pt2035_contacts.py --pt data/pt2035_projects.json --all data/all_projects.json --backup
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any, Dict, List

from contact_channels import enrich_project_contacts


def load_json(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected list in {path}")
    return data


def project_key(p: Dict[str, Any]) -> str:
    return str(p.get("id") or p.get("url") or p.get("title") or "").strip().lower()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pt", default="data/pt2035_projects.json")
    parser.add_argument("--all", default="data/all_projects.json")
    parser.add_argument("--backup", action="store_true")
    args = parser.parse_args()

    pt_path = Path(args.pt)
    all_path = Path(args.all)

    pt_projects = [enrich_project_contacts(dict(p)) for p in load_json(pt_path)]
    all_projects = load_json(all_path)

    if args.backup and all_path.exists():
        shutil.copy2(all_path, all_path.with_suffix(all_path.suffix + ".contacts.bak"))

    index = {project_key(p): i for i, p in enumerate(all_projects) if project_key(p)}
    added = 0
    updated = 0

    for project in pt_projects:
        project["source"] = "pt.2035.university"
        key = project_key(project)
        if key and key in index:
            all_projects[index[key]].update(project)
            updated += 1
        else:
            all_projects.append(project)
            added += 1

    with all_path.open("w", encoding="utf-8") as f:
        json.dump(all_projects, f, ensure_ascii=False, indent=2)

    with pt_path.open("w", encoding="utf-8") as f:
        json.dump(pt_projects, f, ensure_ascii=False, indent=2)

    print(f"Saved {all_path}: total={len(all_projects)}, added={added}, updated={updated}")
    print(f"Normalized {pt_path}: projects={len(pt_projects)}")


if __name__ == "__main__":
    main()
