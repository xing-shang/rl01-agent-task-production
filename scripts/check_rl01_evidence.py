#!/usr/bin/env python3
"""Read-only checks of packaged evidence; never execute a task or edit scores."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import tomllib
from pathlib import Path, PurePosixPath


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value)


def strict_json(path: Path):
    def pairs(items):
        result = {}
        for key, value in items:
            if key in result:
                raise ValueError("duplicate JSON key: " + key)
            result[key] = value
        return result

    def constant(value):
        raise ValueError("non-finite JSON value: " + value)

    return json.loads(path.read_text(encoding="utf-8-sig"),
                      object_pairs_hook=pairs, parse_constant=constant)


def safe_relative(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value:
        raise ValueError("file reference must be a relative POSIX path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or value.rstrip("/") != path.as_posix():
        raise ValueError("unsafe file reference: " + value)
    return value.rstrip("/")


def build_manifest(batch: Path) -> dict:
    batch = batch.resolve(strict=True)
    if not batch.is_dir():
        raise ValueError("manifest source must be the final staging batch directory")
    files = []
    for path in sorted(batch.rglob("*")):
        if path.is_symlink():
            raise ValueError("symlink in staging batch")
        if path.is_file():
            files.append({"path": path.relative_to(batch.parent).as_posix(),
                          "bytes": path.stat().st_size, "sha256": sha256(path)})
    if not files:
        raise ValueError("cannot freeze an empty staging batch")
    return {"kind": "local_delivery_file_manifest", "batch_name": batch.name,
            "files": files}


def compare_manifest(batch: Path, manifest: dict) -> list[dict]:
    issues = []
    if (not isinstance(manifest, dict) or
            manifest.get("kind") != "local_delivery_file_manifest" or
            manifest.get("batch_name") != batch.name or
            not isinstance(manifest.get("files"), list) or not manifest["files"]):
        return [{"rule": "archive-manifest", "detail": "invalid staging manifest or batch name"}]
    expected = {}
    for item in manifest["files"]:
        try:
            name = safe_relative(item["path"])
            if name in expected or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
                raise ValueError("duplicate path or invalid SHA-256")
            expected[name] = item
        except (KeyError, TypeError, ValueError) as error:
            issues.append({"rule": "archive-manifest", "detail": str(error)})
    actual = {p.relative_to(batch.parent).as_posix(): p
              for p in batch.rglob("*") if p.is_file()}
    for name in sorted(expected.keys() - actual.keys()):
        issues.append({"rule": "archive-manifest-missing", "detail": name})
    for name in sorted(actual.keys() - expected.keys()):
        issues.append({"rule": "archive-manifest-added", "detail": name})
    for name in sorted(expected.keys() & actual.keys()):
        if (sha256(actual[name]) != expected[name]["sha256"] or
                actual[name].stat().st_size != expected[name].get("bytes")):
            issues.append({"rule": "archive-manifest-changed", "detail": name})
    return issues


def audit_evidence(batch: Path) -> dict:
    batch = batch.resolve(strict=True)
    result = {"ok": False, "scope": "packaged_evidence_static_only", "issues": [],
              "warnings": [], "json_files_checked": 0, "score_sets_checked": 0,
              "negative_judgments_for_review": []}

    def fail(rule, path, detail):
        result["issues"].append({"rule": rule, "path": path.relative_to(batch).as_posix(),
                                 "detail": detail})

    def reference(base, value):
        target = base / safe_relative(value)
        if not target.resolve().is_relative_to(batch):
            raise ValueError("reference escapes the batch")
        if not target.exists() or target.is_symlink():
            raise ValueError("missing or symlink file reference: " + str(value))
        return target

    task_rules = {}
    for config_path in batch.rglob("task.toml"):
        try:
            config = tomllib.loads(config_path.read_text(encoding="utf-8"))
            task_id = config["metadata"]["task_id"]
            rules = tomllib.loads((config_path.parent / "tests/rubrics.toml").read_text())
            task_rules[task_id] = {x["id"]: x for x in rules["criterion"]}
        except (OSError, ValueError, KeyError, TypeError):
            # The task checker owns configuration failures.
            continue

    parsed = {}
    for path in sorted(batch.rglob("*.json")):
        relative = path.relative_to(batch)
        if not {"evidence", "author_evidence"}.intersection(relative.parts):
            continue
        try:
            parsed[path] = strict_json(path)
            result["json_files_checked"] += 1
        except (OSError, UnicodeError, ValueError) as error:
            fail("evidence-json", path, str(error))

    for path, data in parsed.items():
        if not isinstance(data, dict):
            continue
        # Only hash-bearing file manifests have this meaning; runtime virtual
        # source/destination paths are not interpreted as local file claims.
        for key in ("files", "artifacts"):
            records = data.get(key)
            if not isinstance(records, list):
                continue
            base = batch if path.name == "material_manifest.json" else path.parent
            for item in records:
                if not isinstance(item, dict) or "path" not in item or "sha256" not in item:
                    continue
                try:
                    target = reference(base, item["path"])
                    if not target.is_file() or sha256(target) != item["sha256"]:
                        raise ValueError("declared artifact hash does not match: " + item["path"])
                    if "bytes" in item and target.stat().st_size != item["bytes"]:
                        raise ValueError("declared artifact size does not match: " + item["path"])
                except (OSError, TypeError, ValueError) as error:
                    fail("evidence-artifact", path, str(error))

        groups = data.get("evidence")
        required = data.get("required_evidence_files")
        if isinstance(groups, dict) and isinstance(required, list):
            for label, directory in groups.items():
                if not isinstance(directory, str):
                    continue
                try:
                    base = reference(path.parent, directory)
                    if not base.is_dir():
                        raise ValueError("evidence group is not a directory: " + directory)
                except (OSError, ValueError) as error:
                    fail("evidence-index", path, str(error))
                    continue
                exemptions = data.get("trajectory_not_applicable", {})
                exemption = exemptions.get(label) if isinstance(exemptions, dict) else None
                for declaration in required:
                    if not isinstance(declaration, str):
                        continue
                    candidate_only = declaration.endswith(" for each candidate")
                    name = declaration.removesuffix(" for each candidate")
                    if candidate_only and ("golden" in label.lower() or "oracle" in label.lower()):
                        continue
                    if name == "trajectory.json" and isinstance(exemption, dict):
                        if exemption.get("required") is False and str(exemption.get("reason", "")).strip():
                            if exemption.get("generation_record"):
                                try:
                                    reference(base, exemption["generation_record"])
                                except (OSError, ValueError) as error:
                                    fail("evidence-index", path, str(error))
                            continue
                    try:
                        reference(base, name)
                    except (OSError, ValueError) as error:
                        fail("evidence-index", path, label + ": " + str(error))

        if path.name != "reward-details.json" or "history" in path.relative_to(batch).parts:
            continue
        nested = data.get("reward", {})
        rows = data.get("criteria")
        if rows is None and isinstance(nested, dict):
            rows = nested.get("criteria")
        if not isinstance(rows, list):
            continue
        task_id = next((part for part in path.relative_to(batch).parts if part in task_rules), None)
        rules = task_rules.get(task_id, {})
        if not rules:
            result["warnings"].append({"rule": "evidence-score-context", "path": str(path.relative_to(batch)),
                                       "detail": "cannot bind criterion definitions; manual score review required"})
            continue
        seen, numerator, denominator = set(), 0.0, 0.0
        valid = True
        for row in rows:
            if not isinstance(row, dict):
                fail("evidence-score-row", path, "criterion must be an object")
                valid = False
                continue
            cid = row.get("criterion_id", row.get("id", row.get("name")))
            if not isinstance(cid, str):
                fail("evidence-score-row", path, "criterion ID must be a string")
                valid = False
                continue
            item = rules.get(cid)
            if item is None or cid in seen:
                fail("evidence-score-row", path, "duplicate or unknown criterion: " + str(cid))
                valid = False
                continue
            seen.add(cid)
            negate, weight = item.get("negate", False), item["weight"]
            raw, value = row.get("raw"), row.get("value")
            try:
                if item["type"] == "likert":
                    raw_number = float(raw) if type(raw) is not bool else float("nan")
                    if raw_number not in (1, 2, 3, 4, 5):
                        raise ValueError("invalid Likert raw")
                    expected = (raw_number - 1) / 4
                elif isinstance(raw, str) and raw.lower() in ("yes", "no"):
                    expected = float(raw.lower() == "yes")
                elif type(raw) is bool or (number(raw) and raw in (0, 1)):
                    expected = float(raw)
                else:
                    raise ValueError("invalid Binary raw")
                if negate:
                    expected = 1 - expected
                if not number(value) or abs(value - expected) > 1e-9:
                    raise ValueError("raw/value normalization disagrees")
                if not number(row.get("weight")) or abs(row["weight"]) != weight:
                    raise ValueError("weight disagrees with final criterion")
                if "negate" in row and (type(row["negate"]) is not bool or row["negate"] != negate):
                    raise ValueError("negate disagrees with final criterion")
                if row.get("error"):
                    raise ValueError("criterion contains a verifier error")
            except (TypeError, ValueError) as error:
                fail("evidence-score-row", path, str(cid) + ": " + str(error))
                valid = False
                continue
            numerator += -weight * (1 - value) if negate else weight * value
            denominator += 0 if negate else weight
            if negate:
                reason = row.get("reasoning", row.get("reason", ""))
                review = {"path": str(path.relative_to(batch)), "id": cid,
                          "raw": raw, "value": value, "reason": reason}
                result["negative_judgments_for_review"].append(review)
                denial = (re.search(r"\bno\s+(?:" + re.escape(cid) + r"\s+)?violation\b|\bnot triggered\b", str(reason), re.I)
                          or re.search(r"均未虚构|未虚构任何|没有已交易、已审批或已联络的断言", str(reason)))
                if value == 0 and denial:
                    result["warnings"].append({"rule": "evidence-judge-reason", "path": review["path"],
                                               "detail": cid + ": penalty with a denial phrase; review original artifacts and judgment; do not auto-correct"})
        if seen != set(rules):
            fail("evidence-score-count", path, "criteria do not cover the final ID set")
            valid = False
        if not valid or denominator <= 0:
            continue
        aggregate = min(1.0, max(0.0, numerator / denominator))
        result["score_sets_checked"] += 1
        main_path = path.with_name("reward.json")
        main = parsed.get(main_path)
        if (isinstance(main, dict) and "criteria_counted" in main and
                "graded" not in path.relative_to(batch).parts):
            if main.get("criteria_counted") != len(rules) or main.get("verifier_error") != 0:
                fail("evidence-score-validity", main_path, "incomplete criterion count or verifier error")
            for key in ("reward", "graded_score"):
                if key in main and (not number(main[key]) or abs(main[key] - aggregate) > 1e-6):
                    fail("evidence-score-total", main_path, key + " does not match criterion aggregation")
            text_path = path.with_name("reward.txt")
            try:
                text_score = float(text_path.read_text().strip())
                if not math.isfinite(text_score) or abs(text_score - aggregate) > 1e-6:
                    raise ValueError("reward.txt does not match criterion aggregation")
            except (OSError, ValueError) as error:
                fail("evidence-score-total", text_path, str(error))
    result["ok"] = not result["issues"]
    result["review_required"] = bool(result["warnings"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("batch", type=Path)
    args = parser.parse_args()
    result = audit_evidence(args.batch)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
