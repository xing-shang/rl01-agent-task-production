#!/usr/bin/env python3
"""Validate a web Pro author review without calling a model or claiming Judge execution."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import tomllib
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def material_hashes(task: Path) -> dict[str, str]:
    """Files reviewed by the author, stable across the separate-Verifier adapter."""
    files = [task / name for name in (
        "instruction.md", "rubrics.json", "tests/rubrics.toml", "tests/prompt.md",
        "tests/test.sh", "tests/finalize.py")]
    for name in ("environment", "solution/golden_output", "tests/__golden_output"):
        files.extend(path for path in (task / name).rglob("*") if path.is_file())
    if any(path.is_symlink() for path in files):
        raise ValueError("Pro review materials may not contain symlinks")
    return {path.relative_to(task).as_posix(): sha256(path) for path in sorted(files)}


def number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def validate(task: Path, review: Path, source_task_toml: Path | None = None) -> dict:
    task, review = task.resolve(strict=True), review.resolve(strict=True)
    data = json.loads(review.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or data.get("mode") != "author_simulation":
        raise ValueError("Pro review must identify mode=author_simulation")
    if data.get("external_judge_executed") is not False:
        raise ValueError("Pro self-review must identify external_judge_executed=false")
    config = tomllib.loads((task / "task.toml").read_text())
    if (data.get("task_id") != config["metadata"]["task_id"] or
            data.get("task_version") != config["task"]["version"]):
        raise ValueError("Pro review belongs to a different task or version")
    if data.get("task_toml_sha256") != sha256(source_task_toml or task / "task.toml"):
        raise ValueError("Pro review task.toml hash does not match its source version")
    materials = material_hashes(task)
    if data.get("material_sha256") != materials:
        raise ValueError("Pro review material hashes do not match the final task")
    if data.get("unresolved_items"):
        raise ValueError("Pro review has unresolved items")
    rows = data.get("criteria")
    if not isinstance(rows, list) or not rows:
        raise ValueError("Pro review needs a complete criteria list")
    expected = tomllib.loads((task / "tests/rubrics.toml").read_text())["criterion"]
    by_id = {item["id"]: item for item in expected}
    seen, numerator, denominator = set(), 0.0, 0.0
    for row in rows:
        if not isinstance(row, dict):
            raise ValueError("Every Pro review criterion must be an object")
        cid = row.get("criterion_id")
        if not isinstance(cid, str) or cid not in by_id or cid in seen:
            raise ValueError("Pro review contains a missing, duplicate or unknown criterion ID")
        seen.add(cid)
        item = by_id[cid]
        weight, negate = item["weight"], item.get("negate", False)
        if (not number(row.get("weight")) or abs(row["weight"]) != weight or
                type(row.get("negate")) is not bool or row["negate"] != negate):
            raise ValueError("Pro review weight/negate disagrees with " + cid)
        if row.get("error") or row.get("status") == "UNVERIFIABLE":
            raise ValueError("Pro review criterion is unverifiable: " + cid)
        if not all(isinstance(row.get(key), str) and row[key].strip()
                   for key in ("target_file", "evidence", "reason")):
            raise ValueError("Pro review needs a target file, evidence and reason for " + cid)
        raw = row.get("raw")
        if item["type"] == "likert":
            if not number(raw) or raw not in (1, 2, 3, 4, 5):
                raise ValueError("Pro review Likert raw must be 1 through 5 for " + cid)
            value = (raw - 1) / 4
        else:
            if type(raw) is bool:
                value = float(raw)
            elif number(raw) and raw in (0, 1):
                value = float(raw)
            elif isinstance(raw, str) and raw.lower() in ("yes", "no"):
                value = float(raw.lower() == "yes")
            else:
                raise ValueError("Pro review Binary raw must be yes/no or 0/1 for " + cid)
        if negate:
            value = 1 - value
        if not number(row.get("value")) or abs(row["value"] - value) > 1e-9:
            raise ValueError("Pro review raw/value conversion is inconsistent for " + cid)
        if negate:
            numerator -= weight * (1 - value)
        else:
            numerator += weight * value
            denominator += weight
    if seen != set(by_id):
        raise ValueError("Pro review must cover every final criterion ID")
    if denominator <= 0:
        raise ValueError("Pro review has no positive score pool")
    score = min(1.0, max(0.0, numerator / denominator))
    declared = data.get("simulated_score")
    if not number(declared) or abs(declared - score) > 1e-6:
        raise ValueError("Pro review simulated_score disagrees with its criterion scores")
    if score <= 0.85:
        raise ValueError("Web Pro Golden self-review must score strictly above 0.85")
    return {"source": "web_pro_self_review", "mode": "author_simulation",
            "external_judge_executed": False, "task_id": data["task_id"],
            "task_version": data["task_version"], "simulated_score": score,
            "criteria_counted": len(seen), "review_sha256": sha256(review),
            "material_sha256": materials, "task_toml_sha256": data["task_toml_sha256"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task", type=Path)
    parser.add_argument("review", type=Path, nargs="?")
    parser.add_argument("--material-hashes", action="store_true")
    args = parser.parse_args()
    if args.material_hashes:
        result = {"task_toml_sha256": sha256(args.task / "task.toml"),
                  "material_sha256": material_hashes(args.task)}
    elif args.review is not None:
        result = validate(args.task, args.review)
    else:
        parser.error("supply a review file or --material-hashes")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
