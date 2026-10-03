#!/usr/bin/env python3
"""Generate task.toml and JSON/TOML rubrics from one explicit author specification."""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import re
from pathlib import Path, PurePosixPath

from check_rl01_package import ENGINEERING_VERSION, REQUIRED_METADATA, audit_expert_rubric, is_unresolved_template

LEVEL_ORDER = ("0", "0.25", "0.5", "0.75", "1")


def toml_value(value):
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return repr(value)
    if isinstance(value, list) and all(not isinstance(x, dict) for x in value):
        return "[" + ", ".join(toml_value(x) for x in value) + "]"
    raise ValueError("unsupported or nonfinite TOML value")


def render_toml(data):
    lines = []

    def table(values, path=(), header=None):
        if header:
            lines.extend(["", header])
        for key, value in values.items():
            if not isinstance(value, dict) and not (isinstance(value, list) and value and isinstance(value[0], dict)):
                lines.append(f"{key} = {toml_value(value)}")
        for key, value in values.items():
            child = (*path, key)
            name = ".".join(child)
            if isinstance(value, dict):
                table(value, child, f"[{name}]")
            elif isinstance(value, list) and value and isinstance(value[0], dict):
                if not all(isinstance(x, dict) for x in value):
                    raise ValueError("mixed array of tables")
                for entry in value:
                    table(entry, child, f"[[{name}]]")

    table(data)
    return "\n".join(lines).lstrip() + "\n"


def render_spec(spec, task_id):
    task = copy.deepcopy(spec["task"])
    rubrics = copy.deepcopy(spec["rubrics"])
    metadata = task["metadata"]
    task_fields = task["task"]
    if metadata.get("task_id") != task_id:
        raise ValueError("output directory name must equal metadata.task_id")
    if task.get("schema_version") != "1.4" or not set(REQUIRED_METADATA).issubset(metadata):
        raise ValueError("task specification needs schema_version=1.4 and all maintained metadata fields")
    if not isinstance(task_fields.get("description"), str) or not task_fields["description"].strip():
        raise ValueError("task.description must be a nonempty string")
    keywords = task_fields.get("keywords")
    if (not isinstance(keywords, list) or len(keywords) != 3 or not isinstance(keywords[0], str)
            or re.fullmatch(r"[A-Za-z][A-Za-z0-9 _-]*", keywords[0]) is None
            or keywords[1:] != ["office", metadata.get("difficulty")]):
        raise ValueError('task.keywords must be [<domain in English>, "office", <difficulty>]')
    if is_unresolved_template(metadata.get("environment_template")):
        raise ValueError("environment_template is unresolved; use an existing documented template identity")
    metadata.setdefault("tags", [])
    deliverables = metadata["deliverables"]
    if not isinstance(deliverables, list) or not deliverables:
        raise ValueError("metadata.deliverables must be a nonempty array")
    for entry in deliverables:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str) or not isinstance(entry.get("required"), bool):
            raise ValueError("deliverables need string path and boolean required")
        path = PurePosixPath(entry["path"])
        if path.is_absolute() or ".." in path.parts or "\\" in entry["path"] or not entry["path"].strip():
            raise ValueError("deliverable paths must be relative to /app/output")
        if entry["required"] and any(x in entry["path"] for x in "*?[{"):
            raise ValueError("required deliverables cannot use glob")
    task["artifacts"] = [f'/app/output/{x["path"]}' for x in deliverables if x["required"]]
    issues, warnings = audit_expert_rubric(rubrics, metadata.get("difficulty"))
    if issues:
        raise ValueError(json.dumps(issues, ensure_ascii=False))
    targets = spec["deliverables_to_inspect"]
    if set(targets) != {item["id"] for item in rubrics["items"]}:
        raise ValueError("deliverables_to_inspect must map every criterion ID exactly once")
    criteria = []
    for item in rubrics["items"]:
        paths = targets[item["id"]]
        if not isinstance(paths, list) or not paths or any(not isinstance(x, str) for x in paths):
            raise ValueError("each criterion needs a nonempty list of explicit output paths")
        for path in paths:
            relative = path.removeprefix("/app/")
            if not relative.startswith("output/") or ".." in PurePosixPath(relative).parts or any(x in path for x in "*?[{\\"):
                raise ValueError("criterion paths must be exact output/<file> or /app/output/<file> paths")
        description = item["description"].strip()
        if "Deliverables to inspect:" in description:
            raise ValueError("keep the generated path list in deliverables_to_inspect, without duplicating its prefix in description")
        kind = str(item["type"]).lower()
        criterion = {"id": item["id"], "name": item["id"], "type": "likert" if kind == "gradient" else "binary",
                     "weight": float(abs(item["weight"])), "negate": item["negate"]}
        if kind == "gradient":
            criterion["points"] = 5
            description += "\n" + "\n".join(f"{raw}: {item['levels'][level]}" for raw, level in enumerate(LEVEL_ORDER, 1))
        else:
            description += "\n评分输出：判据为真时score=yes；判据为假时score=no。负项是否扣分由negate处理一次。"
        criterion["description"] = description + "\nDeliverables to inspect: " + "; ".join(paths) + "."
        criteria.append(criterion)
    mirrored_issues, _ = audit_expert_rubric(rubrics, metadata.get("difficulty"), criteria)
    if mirrored_issues:
        raise ValueError(json.dumps(mirrored_issues, ensure_ascii=False))
    scoring = {"judge": {"judge": "claude-code", "prompt_template": "prompt.md", "model": "qwen3.7-plus",
                         "timeout": 7200, "mode": "individual", "weight": 1.0},
               "scoring": {"aggregation": "weighted_mean"}, "criterion": criteria}
    return {"task.toml": render_toml(task), "rubrics.json": json.dumps(rubrics, ensure_ascii=False, indent=2) + "\n",
            "tests/rubrics.toml": render_toml(scoring)}, warnings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", type=Path)
    parser.add_argument("task_dir", type=Path)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    try:
        files, warnings = render_spec(json.loads(args.spec.read_text(encoding="utf-8")), args.task_dir.name)
        existing = [name for name in files if (args.task_dir / name).exists()]
        if existing and not args.overwrite:
            raise ValueError("generated paths already exist; use --overwrite for an intentional regeneration")
        for name, content in files.items():
            path = args.task_dir / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8", newline="\n")
        print(json.dumps({"ok": True, "scope": "configuration_generation_only", "engineering_version": ENGINEERING_VERSION,
                          "files": {name: hashlib.sha256(content.encode()).hexdigest() for name, content in files.items()},
                          "warnings": warnings}, ensure_ascii=False, indent=2))
        return 0
    except (KeyError, TypeError, ValueError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error)}, ensure_ascii=False, indent=2))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
