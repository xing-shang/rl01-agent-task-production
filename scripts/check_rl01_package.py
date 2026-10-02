#!/usr/bin/env python3
"""Static preflight for one RL0-1 rewardkit task directory."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import stat
import sys
import tomllib
from pathlib import Path

REQUIRED_TOP_LEVEL = (
    "instruction.md",
    "task.toml",
    "rubrics.json",
    "environment",
    "solution",
    "tests",
)
REQUIRED_FILES = (
    "instruction.md",
    "task.toml",
    "rubrics.json",
    "environment/Dockerfile",
    "environment/requirements.txt",
    "solution/solve.sh",
    "tests/test.sh",
    "tests/finalize.py",
    "tests/rubrics.toml",
    "tests/prompt.md",
)
REQUIRED_DIRS = (
    "environment/input_files",
    "solution/golden_output",
    "tests/__golden_output",
)
REQUIRED_METADATA = (
    "task_id",
    "author_organization",
    "category",
    "domain",
    "domain_l2",
    "domain_l3",
    "domain_l4",
    "capabilities",
    "difficulty",
    "vl_dependency",
    "source_note",
    "tools",
    "task_complexity",
    "weakness_tag",
    "environment_template",
    "tool_set",
    "skill_set",
    "expected_tool_dependencies",
    "expected_skill_dependencies",
)
# S02 (26-page edition), pages 5-13: column B names. Old example labels and
# task-specific bad-pattern descriptions are not formal labels. Keep aligned
# with references/weakness-catalog.md; the platform enum question is unresolved.
WEAKNESS_TAGS = {
    "长文档下的硬约束遵循较差",
    "关键冲突下自行选边/修改输入，而不是模糊澄清或是说明具体冲突情况",
    "阻塞状态的识别与恢复能力较差",
    "多要求/多交付物下缺少Requirement Coverage Accounting",
    "关键信息缺失时“该问不问”",
    "用户补充信息后只局部更新，没有Global Re-planning",
    "长表格/多Sheet下的数据覆盖与抗干扰能力弱",
    "启动Subagent后把“已派发”当成“已完成”",
    "Skill被形式化调用，但没有真正改变关键判断",
    "大Workspace下缺少Coverage Accounting，读了一部分材料就开始形成完整结论",
    "无据自造数据与口径",
    "跨源交叉核对缺失",
    "规划与策略调整失当",
    "脱敏与合规疏漏",
}
FORBIDDEN_NAMES = {
    ".DS_Store",
    "__MACOSX",
    "__pycache__",
    ".git",
    ".venv",
    "reward.json",
    "reward-details.json",
    "jobs",
    "logs",
}
SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._-]{20,}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
)
TEXT_SUFFIXES = {".md", ".toml", ".json", ".py", ".sh", ".txt", ".cfg", ".yaml", ".yml"}
DIMENSIONS = {
    "指令遵循", "内容质量-结论正确性", "内容质量-数值与计算准确性",
    "内容质量-专业规范", "内容质量-分析与论证质量", "内容质量-事实忠实性",
    "结构与组织", "操作与交付安全", "安全合规", "超预期贡献", "视觉美感",
}
DOMAIN_ANCHORS = {
    "内容质量-结论正确性", "内容质量-数值与计算准确性",
    "内容质量-专业规范", "内容质量-事实忠实性",
}
MIN_CRITERIA = {"A1": 8, "A2": 12, "A3": 25}
LEVELS = {"0", "0.25", "0.5", "0.75", "1"}
RAW_LEVELS = {"1", "2", "3", "4", "5"}
ANCHOR_LINE = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?([0-9]+(?:\.[0-9]+)?)\s*(?:分)?(?:\*\*)?\s*[:：]\s*(.*)$", re.MULTILINE)


def audit_likert_anchors(item: dict, original: dict | None = None) -> list[dict]:
    """Check the actual judge-facing ladder, not just type/points metadata.

    Canonical anchor lines are `1: ...` through `5: ...`. Business semantics
    still need review; exact swapped JSON texts are a detectable conversion bug.
    """
    if item.get("type") != "likert" or not isinstance(item.get("description"), str):
        return []
    cid = item.get("id")
    anchors = ANCHOR_LINE.findall(item["description"])
    labels = [label for label, _ in anchors]
    issues = []
    if len(labels) != 5 or set(labels) != RAW_LEVELS or any(not text.strip() for _, text in anchors):
        issues.append(fail("rubric-likert-scale", f"{cid} needs exactly five nonempty raw integer anchor lines 1: through 5:; normalized 0/0.25/0.5/0.75/1 labels are not judge output scores"))
        return issues
    if original and isinstance(original.get("levels"), dict):
        levels = original["levels"]
        normalize = lambda value: re.sub(r"\s+", "", value) if isinstance(value, str) else None
        for raw, text in anchors:
            expected_key = format((int(raw) - 1) / 4, "g")
            actual = normalize(text)
            expected = normalize(levels.get(expected_key))
            if actual != expected and any(actual == normalize(value) for value in levels.values()):
                issues.append(fail("rubric-likert-scale", f"{cid} raw {raw} uses another JSON level's wording; expected normalized level {expected_key}"))
    return issues


def numeric(value: object) -> bool:
    if isinstance(value, bool):
        return False
    return isinstance(value, int) or (isinstance(value, float) and math.isfinite(value))


def table_field(value: object, rule: str, field: str, issues: list) -> dict:
    if not isinstance(value, dict):
        issues.append(fail(rule, f"{field} must be a table"))
        return {}
    return value


def string_list_field(value: object, rule: str, field: str, issues: list) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() for x in value):
        issues.append(fail(rule, f"{field} must be an array of nonempty strings"))
        return []
    return value


def table_list_field(value: object, rule: str, field: str, issues: list) -> list[dict]:
    if not isinstance(value, list) or any(not isinstance(x, dict) for x in value):
        issues.append(fail(rule, f"{field} must be an array of tables"))
        return []
    return value


def audit_expert_rubric(data: object, difficulty: object, criteria: object = None):
    """20260928 QA checks; does not infer semantic correctness from labels."""
    issues, warnings = [], []
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        return [fail("rubrics.json", "root must be an object with an items array")], warnings
    items = data["items"]
    minimum = MIN_CRITERIA.get(difficulty) if isinstance(difficulty, str) else None
    if minimum is not None and len(items) < minimum:
        issues.append(fail("rubric-count", f"{difficulty} requires at least {minimum} criteria; found {len(items)}"))
    if not items:
        issues.append(fail("rubrics.json", "items must be nonempty"))
    positive, negative, anchor = 0.0, 0.0, 0.0
    critical, weights, ids, by_id = 0, set(), [], {}
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            issues.append(fail("rubrics.json", f"item {index} must be an object"))
            continue
        cid = item.get("id")
        label = cid if isinstance(cid, str) and cid else f"item {index}"
        if not isinstance(cid, str) or not cid.strip():
            issues.append(fail("rubrics.json", f"item {index} needs a nonempty string id"))
        else:
            ids.append(cid)
            by_id[cid] = item
        description = item.get("description")
        if not isinstance(description, str) or not description.strip():
            issues.append(fail("rubrics.json", f"{label} needs a description"))
        elif re.search(r"\bR\d+[A-Za-z]?\b", description):
            warnings.append(f"{label}: check cross-criterion references; each criterion must stand alone")
        dimension = item.get("dimension")
        if not isinstance(dimension, str) or dimension not in DIMENSIONS:
            issues.append(fail("rubric-dimension", f"{label} has an unrecognized dimension"))
        if not isinstance(item.get("criterion_type"), str) or item["criterion_type"] not in {"Objective", "Subjective"}:
            issues.append(fail("rubrics.json", f"{label} needs Objective or Subjective"))
        if not isinstance(item.get("criterion_necessity"), str) or item["criterion_necessity"] not in {"Explicit", "Implicit"}:
            issues.append(fail("rubrics.json", f"{label} needs Explicit or Implicit"))
        kind = str(item.get("type", "")).lower()
        if kind not in {"binary", "gradient"}:
            issues.append(fail("rubrics.json", f"{label} type must be binary/gradient"))
        if kind == "gradient":
            levels = item.get("levels")
            if (not isinstance(levels, dict) or set(levels) != LEVELS
                    or any(not isinstance(v, str) or not v.strip() for v in levels.values())):
                issues.append(fail("rubric-levels", f"{label} needs five nonempty levels 0/0.25/0.5/0.75/1"))
        weight = item.get("weight")
        if not numeric(weight) or weight not in {-10, -7, -3, 3, 7, 10}:
            issues.append(fail("rubric-weight", f"{label} needs a finite signed weight from ±3/±7/±10"))
            continue
        if not isinstance(item.get("negate"), bool) or item["negate"] != (weight < 0):
            issues.append(fail("rubric-negate", f"{label} negate must be boolean and agree with signed weight"))
        weights.add(abs(weight))
        if weight > 0:
            positive += weight
            critical += weight == 10
            if isinstance(dimension, str) and dimension in DOMAIN_ANCHORS:
                anchor += weight
        else:
            negative += abs(weight)
    if len(ids) != len(set(ids)):
        issues.append(fail("rubrics.json", "item IDs are not unique"))
    if positive <= 0:
        issues.append(fail("rubric-weight", "positive weight pool must be nonzero"))
    if critical < 2:
        issues.append(fail("rubric-weight", "at least two positive weight-10 items are required"))
    if items and len(weights) < 2:
        issues.append(fail("rubric-weight", "weights must reflect different business importance, not one repeated tier"))
    if anchor < 0.30 * positive:
        issues.append(fail("domain-anchor", f"four QA anchor dimensions contribute {anchor:g}/{positive:g}, below 30%"))
    if negative > 0.50 * positive:
        issues.append(fail("negative-pool", f"negative pool {negative:g} exceeds 50% of positive pool {positive:g}"))
    metadata = data.get("metadata")
    scoring = metadata.get("scoring") if isinstance(metadata, dict) else None
    s_max = scoring.get("s_max") if isinstance(scoring, dict) else None
    if not numeric(s_max) or s_max != positive:
        issues.append(fail("rubric-s-max", f"metadata.scoring.s_max must equal positive pool {positive:g}"))
    if criteria is not None:
        if not isinstance(criteria, list) or any(not isinstance(x, dict) for x in criteria):
            issues.append(fail("rubric-mirror", "TOML criterion must be an array of tables"))
        else:
            toml_ids = [x.get("id") for x in criteria]
            if (any(not isinstance(x, str) for x in toml_ids)
                    or len(toml_ids) != len(set(toml_ids))
                    or set(ids) != set(toml_ids)):
                issues.append(fail("rubric-mirror", "JSON and TOML criterion IDs must correspond one-to-one"))
            for item in criteria:
                cid = item.get("id")
                original = by_id.get(cid) if isinstance(cid, str) else None
                if original is None or not numeric(original.get("weight")):
                    continue
                if item.get("weight") != abs(original["weight"]):
                    issues.append(fail("rubric-mirror", f"{cid} weight differs between JSON and TOML"))
                negate = item.get("negate", False)
                if not isinstance(negate, bool) or negate != (original["weight"] < 0):
                    issues.append(fail("rubric-mirror", f"{cid} penalty direction differs between JSON and TOML"))
                expected = {"binary": "binary", "gradient": "likert"}.get(str(original.get("type", "")).lower())
                if item.get("type") != expected:
                    issues.append(fail("rubric-mirror", f"{cid} type conversion differs between JSON and TOML"))
    return issues, warnings


def fail(rule: str, detail: str) -> dict[str, str]:
    return {"rule": rule, "detail": f"{detail}"}


def is_executable(path: Path) -> bool:
    return bool(path.stat().st_mode & stat.S_IXUSR)


def has_cr(path: Path) -> bool:
    return b"\r" in path.read_bytes()


def normalized_name(name: str) -> str:
    return name.lower().replace("_", "-")


def is_semver(value: object) -> bool:
    return isinstance(value, str) and re.fullmatch(
        r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value
    ) is not None


def has_invisible_whitespace(text: str) -> bool:
    return any(ch in text for ch in ("\u00a0", "\u3000"))


def is_unresolved_template(value: object) -> bool:
    if not isinstance(value, str) or not value.strip():
        return True
    label = value.strip()
    return (
        (label.startswith("<") and label.endswith(">"))
        or label.lower() in {"todo", "tbd", "placeholder"}
        or label.upper().startswith("REPLACE_WITH_")
        or any(term in label for term in ("占位", "待填"))
    )


def validate(root: Path) -> tuple[list[dict[str, str]], list[str]]:
    issues: list[dict[str, str]] = []
    warnings: list[str] = []
    root = root.resolve()
    metadata = {}
    expert_rubric = None
    expert_rubric_loaded = False
    criteria = None

    if not root.is_dir():
        return [fail("root", "not a directory")], warnings

    for item in REQUIRED_TOP_LEVEL:
        if not (root / item).exists():
            issues.append(fail("structure", f"missing required path {item}"))
    for item in REQUIRED_FILES:
        if not (root / item).is_file():
            issues.append(fail("structure", f"missing required file {item}"))
    for item in REQUIRED_DIRS:
        if not (root / item).is_dir():
            issues.append(fail("structure", f"missing required directory {item}"))

    for path in root.rglob("*"):
        if path.is_symlink():
            issues.append(fail("safety", f"symlink is forbidden: {path.relative_to(root)}"))
        if path.name in FORBIDDEN_NAMES:
            issues.append(fail("residue", f"forbidden path: {path.relative_to(root)}"))

    for rel in ("instruction.md", "task.toml"):
        path = root / rel
        if path.is_file() and path.stat().st_size > 1024 * 1024:
            issues.append(fail("size", f"{rel} exceeds 1 MiB"))
    rubrics_toml = root / "tests/rubrics.toml"
    if rubrics_toml.is_file() and rubrics_toml.stat().st_size > 2 * 1024 * 1024:
        issues.append(fail("size", "tests/rubrics.toml exceeds 2 MiB"))

    for rel in ("solution/solve.sh", "tests/test.sh"):
        path = root / rel
        if path.is_file():
            if has_cr(path):
                issues.append(fail("line-ending", f"{rel} contains CR bytes"))
            if not is_executable(path):
                issues.append(fail("permission", f"{rel} is not executable"))
    finalize_py = root / "tests/finalize.py"
    if finalize_py.is_file():
        if has_cr(finalize_py):
            issues.append(fail("line-ending", "tests/finalize.py contains CR bytes"))
        if not is_executable(finalize_py):
            issues.append(fail("permission", "tests/finalize.py is not executable"))

    task_toml_path = root / "task.toml"
    if task_toml_path.is_file():
        try:
            task = tomllib.loads(task_toml_path.read_text(encoding="utf-8"))
            metadata = table_field(task.get("metadata", {}), "task.toml", "metadata", issues)
            task_block = table_field(task.get("task", {}), "task.toml", "task", issues)
            if task.get("schema_version") != "1.4":
                issues.append(fail("task.toml", 'schema_version must be "1.4"'))
            if not is_semver(task_block.get("version")):
                issues.append(fail("task.toml", "task.version must be valid SemVer"))
            task_id = metadata.get("task_id")
            task_name = task_block.get("name")
            if isinstance(task_id, str) and isinstance(task_name, str) and "/" in task_name:
                if normalized_name(task_name.rsplit("/", 1)[1]) != normalized_name(task_id):
                    issues.append(fail("task.toml", "task.name name segment does not normalize to metadata.task_id"))
            string_list_field(task_block.get("keywords"), "task.toml", "task.keywords", issues)
            if metadata.get("task_id") != root.name:
                issues.append(fail("task.toml", "metadata.task_id must equal directory name"))
            for field in REQUIRED_METADATA:
                if field not in metadata:
                    issues.append(fail("task.toml", f"missing metadata.{field}"))
            if is_unresolved_template(metadata.get("environment_template")):
                issues.append(fail("task.toml", "metadata.environment_template is unresolved"))
            if not isinstance(metadata.get("difficulty"), str) or metadata["difficulty"] not in {"A1", "A2", "A3"}:
                issues.append(fail("task.toml", "metadata.difficulty must be A1, A2, or A3"))
            if not isinstance(metadata.get("task_complexity"), str) or metadata["task_complexity"] not in {"C1", "C2", "C3", "C4", "C5"}:
                issues.append(fail("task.toml", "metadata.task_complexity must be C1 through C5"))
            expected_pass_rate = metadata.get("expected_pass_rate")
            if expected_pass_rate is not None and (
                not numeric(expected_pass_rate)
                or not 0 <= expected_pass_rate <= 1
            ):
                issues.append(fail("task.toml", "metadata.expected_pass_rate must be between 0 and 1"))
            weakness_tags = string_list_field(metadata.get("weakness_tag", []), "task.toml", "metadata.weakness_tag", issues)
            if not weakness_tags:
                issues.append(fail("task.toml", "metadata.weakness_tag must contain at least one tag"))
            for tag in weakness_tags:
                if tag not in WEAKNESS_TAGS:
                    issues.append(fail("weakness-tag", f"metadata.weakness_tag value {tag!r} is not a current S02 column-B name; use references/weakness-catalog.md and verify its actual task trigger"))
            dependency_sets = {
                key: set(string_list_field(metadata.get(key, []), "task.toml", f"metadata.{key}", issues))
                for key in ("skill_set", "expected_skill_dependencies", "tool_set", "expected_tool_dependencies")
            }
            skill_set = dependency_sets["skill_set"]
            expected_skills = dependency_sets["expected_skill_dependencies"]
            if not expected_skills.issubset(skill_set):
                issues.append(fail("task.toml", "expected_skill_dependencies must be a subset of skill_set"))
            tool_set = dependency_sets["tool_set"]
            expected_tools = dependency_sets["expected_tool_dependencies"]
            if not expected_tools.issubset(tool_set):
                issues.append(fail("task.toml", "expected_tool_dependencies must be a subset of tool_set"))

            environment = table_field(task.get("environment", {}), "task.toml", "environment", issues)
            allowed_environment_keys = {
                "os",
                "network_mode",
                "allowed_hosts",
                "build_timeout_sec",
                "docker_image",
                "cpus",
                "memory_mb",
                "storage_mb",
                "env",
                "healthcheck",
            }
            if "workdir" in environment:
                issues.append(fail("task.toml", "environment.workdir is forbidden"))
            if set(environment) - allowed_environment_keys:
                issues.append(fail("task.toml", "environment contains unsupported keys"))
            if not isinstance(environment.get("network_mode"), str) or environment["network_mode"] not in {"public", "no-network", "allowlist"}:
                issues.append(fail("task.toml", 'environment.network_mode must be "public", "no-network", or "allowlist"'))
            elif environment.get("network_mode") != "public":
                warnings.append("Non-public network mode needs a case-specific client/platform adaptation; runtime enum validity is not authorization")
            environment_env = table_field(environment.get("env", {}), "task.toml", "environment.env", issues)
            if any(str(key).startswith("JUDGE_") for key in environment_env):
                issues.append(fail("task.toml", "JUDGE_* variables are forbidden in environment.env"))

            verifier = table_field(task.get("verifier", {}), "task.toml", "verifier", issues)
            verifier_env = table_field(verifier.get("env", {}), "task.toml", "verifier.env", issues)
            for required_key in ("JUDGE_API_KEY", "JUDGE_BASE_URL"):
                if required_key not in verifier_env:
                    issues.append(fail("task.toml", f"verifier.env missing required {required_key}"))

            artifacts = string_list_field(task.get("artifacts", []), "task.toml", "artifacts", issues)
            deliverables = table_list_field(metadata.get("deliverables", []), "task.toml", "metadata.deliverables", issues)
            for index, item in enumerate(deliverables):
                path = item.get("path")
                if not isinstance(path, str) or not path.strip():
                    issues.append(fail("task.toml", f"deliverable {index} path must be a nonempty string"))
                    continue
                if not isinstance(item.get("required"), bool):
                    issues.append(fail("task.toml", f"deliverable {index} required must be boolean"))
                if item.get("required") and any(ch in path for ch in "*?[{"):
                    issues.append(fail("task.toml", f"required deliverable {index} uses glob"))
                expected_artifact = f"/app/output/{path}"
                if item.get("required") and expected_artifact not in artifacts:
                    issues.append(fail("task.toml", f"artifacts missing /app/output/{path}"))
            expected_artifacts = {f"/app/output/{item['path']}" for item in deliverables
                                  if item.get("required") is True and isinstance(item.get("path"), str) and item["path"].strip()}
            if set(artifacts) - expected_artifacts:
                warnings.append("artifacts has entries beyond required deliverables; reconcile section 3.2 with the source example before submission")
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            issues.append(fail("task.toml", f"cannot parse: {exc}"))
        if has_invisible_whitespace(task_toml_path.read_text(encoding="utf-8", errors="ignore")):
            issues.append(fail("task.toml", "contains U+00A0 or U+3000 invisible whitespace"))

    rubrics_json_path = root / "rubrics.json"
    if rubrics_json_path.is_file():
        try:
            expert_rubric = json.loads(rubrics_json_path.read_text(encoding="utf-8"))
            expert_rubric_loaded = True
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            issues.append(fail("rubrics.json", f"cannot parse: {exc}"))

    if rubrics_toml.is_file():
        try:
            rubric = tomllib.loads(rubrics_toml.read_text(encoding="utf-8"))
            judge = table_field(rubric.get("judge", {}), "rubrics.toml", "judge", issues)
            if judge.get("judge") != "claude-code":
                issues.append(fail("rubrics.toml", 'judge must be "claude-code"'))
            if judge.get("prompt_template") != "prompt.md":
                issues.append(fail("rubrics.toml", 'prompt_template must be "prompt.md"'))
            if judge.get("timeout") != 7200:
                issues.append(fail("rubrics.toml", "judge timeout must be 7200"))
            if judge.get("mode") != "individual":
                issues.append(fail("rubrics.toml", 'judge mode must be "individual"'))
            if not numeric(judge.get("weight")) or judge["weight"] != 1.0:
                issues.append(fail("rubrics.toml", "judge weight must be 1.0"))
            scoring = table_field(rubric.get("scoring", {}), "rubrics.toml", "scoring", issues)
            if scoring.get("aggregation") != "weighted_mean":
                issues.append(fail("rubrics.toml", 'aggregation must be "weighted_mean"'))
            criteria = table_list_field(rubric.get("criterion", []), "rubrics.toml", "criterion", issues)
            ids: list[str] = []
            for index, item in enumerate(criteria):
                cid = item.get("id")
                valid_id = isinstance(cid, str) and bool(cid.strip())
                ids.append(cid if valid_id else f"<invalid-{index}>")
                if not valid_id or item.get("name") != cid:
                    issues.append(fail("rubrics.toml", f"criterion {index} must have name equal to id"))
                if not isinstance(item.get("type"), str) or item["type"] not in {"binary", "likert"}:
                    issues.append(fail("rubrics.toml", f"criterion {cid} has invalid type"))
                if not numeric(item.get("weight")) or item["weight"] not in {3.0, 7.0, 10.0}:
                    issues.append(fail("rubrics.toml", f"criterion {cid} has invalid weight"))
                if not isinstance(item.get("negate", False), bool):
                    issues.append(fail("rubrics.toml", f"criterion {cid} negate must be boolean"))
                if item.get("type") == "likert" and item.get("points") != 5:
                    issues.append(fail("rubrics.toml", f"likert criterion {cid} must have points = 5"))
                description = item.get("description")
                if not isinstance(description, str) or not description.strip():
                    issues.append(fail("rubrics.toml", f"criterion {cid} description must be a nonempty string"))
                elif "Deliverables to inspect:" not in description:
                    issues.append(fail("rubrics.toml", f"criterion {cid} lacks deliverable path list"))
                elif description.count("Deliverables to inspect:") > 1:
                    warnings.append(f"rubrics.toml criterion {cid} repeats its deliverable path list")
            if len(ids) != len(set(ids)):
                issues.append(fail("rubrics.toml", "criterion IDs are not unique"))
            if sum(item.get("weight") == 10.0 and not item.get("negate") for item in criteria) < 2:
                issues.append(fail("rubrics.toml", "at least two positive weight-10 criteria are required"))
        except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
            issues.append(fail("rubrics.toml", f"cannot parse: {exc}"))
        if has_invisible_whitespace(rubrics_toml.read_text(encoding="utf-8", errors="ignore")):
            issues.append(fail("rubrics.toml", "contains U+00A0 or U+3000 invisible whitespace"))

    prompt_path = root / "tests/prompt.md"
    if expert_rubric_loaded:
        extra_issues, extra_warnings = audit_expert_rubric(expert_rubric, metadata.get("difficulty"), criteria)
        issues.extend(extra_issues)
        warnings.extend(extra_warnings)
    original_items = expert_rubric.get("items", []) if isinstance(expert_rubric, dict) else []
    originals = {x["id"]: x for x in original_items
                 if isinstance(x, dict) and isinstance(x.get("id"), str)} if isinstance(original_items, list) else {}
    for item in criteria or []:
        original = originals.get(item.get("id")) if isinstance(item.get("id"), str) else None
        issues.extend(audit_likert_anchors(item, original))
    template_root = Path(__file__).resolve().parent.parent / "assets/templates"
    for filename in ("test.sh", "finalize.py"):
        actual, expected = root / "tests" / filename, template_root / filename
        if actual.is_file() and expected.is_file() and actual.read_bytes() != expected.read_bytes():
            issues.append(fail("fixed-template", f"tests/{filename} differs from the maintained appendix template"))
    if prompt_path.is_file():
        prompt_text = prompt_path.read_text(encoding="utf-8", errors="replace")
        if "{criteria}" not in prompt_text:
            issues.append(fail("prompt.md", "missing {criteria} placeholder"))
        if has_invisible_whitespace(prompt_text):
            issues.append(fail("prompt.md", "contains U+00A0 or U+3000 invisible whitespace"))
        if criteria is not None:
            prompt_total = len(prompt_text.encode("utf-8"))
            prompt_total += sum(len(item["description"].encode("utf-8")) for item in criteria
                                if isinstance(item.get("description"), str))
            if prompt_total >= 100 * 1024:
                issues.append(fail("prompt.md", "prompt plus criterion descriptions must be below 100 KB"))

    golden_source = root / "solution/golden_output"
    golden_tests = root / "tests/__golden_output"
    if golden_source.is_dir() and golden_tests.is_dir():
        source_files = sorted(path.relative_to(golden_source) for path in golden_source.rglob("*") if path.is_file())
        test_files = sorted(path.relative_to(golden_tests) for path in golden_tests.rglob("*") if path.is_file())
        if not source_files or not test_files:
            issues.append(fail("golden", "both golden_output directories must be nonempty"))
        if source_files != test_files:
            issues.append(fail("golden", "golden_output directory file lists differ"))
        elif source_files:
            for name in source_files:
                source = golden_source / name
                target = golden_tests / name
                if source.read_bytes() != target.read_bytes():
                    issues.append(fail("golden", f"golden bytes differ: {name}"))

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if len(path.name.encode("utf-8")) > 200:
            issues.append(fail("naming", f"filename exceeds 200 bytes: {path.relative_to(root)}"))
        if path.suffix.lower() in TEXT_SUFFIXES or path.name in {"Dockerfile", "requirements.txt"}:
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            if any(pattern.search(text) for pattern in SECRET_PATTERNS):
                issues.append(fail("credential", f"credential-shaped residue in {path.relative_to(root)}"))

    return issues, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("task_dir", type=Path)
    args = parser.parse_args()
    issues, warnings = validate(args.task_dir)
    result = {"ok": not issues, "issues": issues, "warnings": warnings}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not issues else 1


if __name__ == "__main__":
    sys.exit(main())
