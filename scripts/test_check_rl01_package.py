import tempfile
import unittest
import copy
import json
import shutil
import subprocess
import sys
from textwrap import dedent
from pathlib import Path

from check_rl01_package import audit_expert_rubric, audit_likert_anchors, is_unresolved_template, validate


def rubric_fixture(weights=None):
    weights = weights or [10, 10] + [7] * 22 + [-3]
    items = [{
        "id": f"R{i+1}", "description": "核对交付表中的指定独立数值及其原始依据。",
        "dimension": "内容质量-数值与计算准确性", "criterion_type": "Objective",
        "criterion_necessity": "Explicit", "type": "binary", "weight": w,
        "negate": w < 0,
    } for i, w in enumerate(weights)]
    return {"metadata": {"scoring": {"s_max": sum(w for w in weights if w > 0)}}, "items": items}


def mirror(data):
    return [{"id": x["id"], "type": "binary", "weight": abs(x["weight"]),
             "negate": x["weight"] < 0} for x in data["items"]]


def write_package_fixture(root):
    """A locally valid package fixture, without running Docker or a model."""
    for name in ("environment/input_files", "solution/golden_output", "tests/__golden_output"):
        (root / name).mkdir(parents=True)
    (root / "instruction.md").write_text("Read /app/input_files/data.csv; write /app/output/report.txt.")
    (root / "environment/input_files/data.csv").write_text("value\n1\n")
    (root / "environment/requirements.txt").write_text("")
    for name in ("solution/golden_output", "tests/__golden_output"):
        (root / name / "report.txt").write_text("1\n")
    templates = Path(__file__).resolve().parent.parent / "assets/templates"
    for relative in ("environment/Dockerfile", "solution/solve.sh", "tests/test.sh", "tests/finalize.py", "tests/prompt.md"):
        target = root / relative
        shutil.copy2(templates / target.name, target)
        if target.suffix in (".sh", ".py"):
            target.chmod(0o755)
    (root / "task.toml").write_text(dedent('''\
        schema_version = "1.4"
        artifacts = ["/app/output/report.txt"]
        [task]
        name = "qa/fin-qa-001"
        version = "1.0.0"
        description = "Static checker fixture, not a production task"
        keywords = ["finance", "office", "A3"]
        [metadata]
        task_id = "FIN-QA-001"
        author_organization = "qa"
        category = "weakness-driven"
        domain = "金融"
        domain_l2 = "Fin2-股票研究"
        domain_l3 = "校验夹具"
        domain_l4 = "校验夹具"
        capabilities = "static fixture"
        difficulty = "A3"
        vl_dependency = "否"
        source_note = "Local fixture only"
        tools = "Python"
        task_complexity = "C1"
        weakness_tag = ["跨源交叉核对缺失"]
        environment_template = "local-validation-fixture"
        tool_set = ["python"]
        skill_set = []
        expected_tool_dependencies = ["python"]
        expected_skill_dependencies = []
        tags = ["static-fixture"]
        [[metadata.deliverables]]
        path = "report.txt"
        required = true
        desc = "fixture"
        [agent]
        timeout_sec = 72000
        [verifier]
        timeout_sec = 18000
        user = "root"
        [verifier.env]
        JUDGE_API_KEY = "${JUDGE_API_KEY:-}"
        JUDGE_BASE_URL = "${JUDGE_BASE_URL:-}"
        [environment]
        os = "linux"
        network_mode = "public"
    '''), encoding="utf-8")
    data = rubric_fixture()
    (root / "rubrics.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    lines = ['[judge]', 'judge="claude-code"', 'prompt_template="prompt.md"',
             'model="qwen3.7-plus"', 'timeout=7200', 'mode="individual"', 'weight=1.0',
             '[scoring]', 'aggregation="weighted_mean"']
    for item in mirror(data):
        lines.extend(['', '[[criterion]]', f'id="{item["id"]}"', f'name="{item["id"]}"',
                      f'type="{item["type"]}"', f'weight={item["weight"]}.0',
                      f'negate={str(item["negate"]).lower()}',
                      'description="Independent fixture criterion. Deliverables to inspect: output/report.txt."'])
    (root / "tests/rubrics.toml").write_text("\n".join(lines) + "\n", encoding="utf-8")


class CurrentQAContractTests(unittest.TestCase):
    def rules(self, data, difficulty="A3", toml=None):
        issues, _ = audit_expert_rubric(data, difficulty, toml)
        return {x["rule"] for x in issues}

    def test_a3_count_boundary_and_total_weight(self):
        data = rubric_fixture()
        self.assertEqual(set(), self.rules(data, toml=mirror(data)))
        data["items"].pop()
        self.assertEqual({"rubric-count"}, self.rules(data))

    def test_negative_pool_boundary_includes_exactly_half(self):
        data = rubric_fixture([10, 10, 10, 10, 10, 7, 3, -10, -10, -10])
        self.assertEqual(set(), self.rules(data, "A1"))
        extra = copy.deepcopy(data["items"][-1])
        extra.update(id="R11", weight=-3)
        data["items"].append(extra)
        self.assertEqual({"negative-pool"}, self.rules(data, "A1"))

    def test_analysis_dimension_does_not_count_as_domain_anchor(self):
        data = rubric_fixture()
        for item in data["items"]:
            item["dimension"] = "内容质量-分析与论证质量"
        self.assertEqual({"domain-anchor"}, self.rules(data))

    def test_s_max_excludes_penalties(self):
        data = rubric_fixture()
        data["metadata"]["scoring"]["s_max"] -= 3
        self.assertEqual({"rubric-s-max"}, self.rules(data))

    def test_equal_count_different_id_is_not_a_valid_mirror(self):
        data = rubric_fixture()
        toml = mirror(data)
        toml[-1]["id"] = "R26"
        self.assertIn("rubric-mirror", self.rules(data, toml=toml))

    def test_repeated_toml_criterion_is_not_a_valid_mirror(self):
        data = rubric_fixture()
        toml = mirror(data)
        toml.append(copy.deepcopy(toml[0]))
        self.assertIn("rubric-mirror", self.rules(data, toml=toml))

    def test_penalty_direction_and_weight_must_survive_conversion(self):
        data = rubric_fixture()
        for field, value in (("negate", False), ("weight", 7)):
            toml = mirror(data)
            toml[-1][field] = value
            with self.subTest(field=field):
                self.assertIn("rubric-mirror", self.rules(data, toml=toml))

    def test_gradient_requires_complete_five_bands_and_likert_conversion(self):
        data = rubric_fixture()
        item = data["items"][0]
        item.update(type="Gradient", levels={"0": "零覆盖", "0.25": "四分之一", "0.5": "一半", "0.75": "四分之三", "1": "全部"})
        toml = mirror(data)
        toml[0]["type"] = "likert"
        self.assertEqual(set(), self.rules(data, toml=toml))
        del item["levels"]["0"]
        self.assertIn("rubric-levels", self.rules(data))

    def test_unusable_json_is_rejected_and_nonfinite_is_not_accepted(self):
        for bad in (None, [], {"criteria": []}, {"items": [None]}):
            with self.subTest(bad=bad):
                self.assertIn("rubrics.json", self.rules(bad))
        for bad in (True, float("nan"), float("inf"), 10 ** 400):
            data = rubric_fixture()
            data["items"][0]["weight"] = bad
            with self.subTest(bad=bad):
                self.assertIn("rubric-weight", self.rules(data))


class PackagePreflightTests(unittest.TestCase):
    def test_actual_judge_ladder_rejects_normalized_anchors(self):
        # FIN8-DW-001 returned raw=1 for a complete answer, normalized to zero.
        item = {"id": "R02", "type": "likert", "points": 5,
                "description": "Deliverables to inspect: output/report.txt.\n" +
                "\n".join(f"{x}: coverage {x}" for x in (0, .25, .5, .75, 1))}
        self.assertEqual(["rubric-likert-scale"], [x["rule"] for x in audit_likert_anchors(item)])
        item["description"] = "\n".join(f"{x}: coverage {x}" for x in range(1, 6))
        self.assertEqual([], audit_likert_anchors(item))

    def test_raw_ladder_missing_duplicate_mixed_and_empty_anchors(self):
        good = [f"{x}: band {x}" for x in range(1, 6)]
        for lines in (good[:-1], good + [good[-1]], good + ["0.75: normalized"], good[:-1] + ["5: "]):
            with self.subTest(lines=lines):
                self.assertTrue(audit_likert_anchors({"id": "R1", "type": "likert", "description": "\n".join(lines)}))

    def test_raw_ladder_preserves_json_level_meaning_for_both_directions(self):
        levels = {"0": "未完成", "0.25": "少量完成", "0.5": "半数完成", "0.75": "大部分完成", "1": "全部完成"}
        for negate in (False, True):
            item = {"id": "R1", "type": "likert", "negate": negate,
                    "description": "\n".join(f"{i}: {text}" for i, text in enumerate(levels.values(), 1))}
            self.assertEqual([], audit_likert_anchors(item, {"levels": levels}))
            item["description"] = item["description"].replace("1: 未完成", "1: 全部完成").replace("5: 全部完成", "5: 未完成")
            self.assertEqual(2, len(audit_likert_anchors(item, {"levels": levels})))

    def test_package_checks_ladder_even_when_points_is_five(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            write_package_fixture(root)
            path = root / "tests/rubrics.toml"
            original = path.read_text()
            changed = original.replace('type="binary"', 'type="likert"\npoints=5', 1)
            path.write_text(changed)
            issues, _ = validate(root)
            self.assertIn("rubric-likert-scale", {x["rule"] for x in issues})

    def test_valid_package_and_mutated_template_cli(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "FIN-QA-001"
            write_package_fixture(root)
            checker = Path(__file__).with_name("check_rl01_package.py")
            command = [sys.executable, "-B", str(checker), str(root)]
            good = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(0, good.returncode, good.stdout + good.stderr)
            self.assertTrue(json.loads(good.stdout)["ok"])
            (root / "tests/test.sh").write_text((root / "tests/test.sh").read_text() + "\n# mutation\n")
            bad = subprocess.run(command, capture_output=True, text=True, check=False)
            self.assertEqual(1, bad.returncode, bad.stdout + bad.stderr)
            self.assertEqual({"fixed-template"}, {x["rule"] for x in json.loads(bad.stdout)["issues"]})

    def test_malformed_task_fields_report_diagnostics(self):
        cases = (
            ("metadata=[]", "metadata must be a table"),
            ("task=[]", "task must be a table"),
            ("environment=[]", "environment must be a table"),
            ("verifier=[]", "verifier must be a table"),
            ('artifacts=[{}]', "artifacts must be an array of nonempty strings"),
            ('[metadata]\nskill_set=[[]]', "metadata.skill_set must be an array of nonempty strings"),
            ('[metadata]\ndeliverables=["report.txt"]', "metadata.deliverables must be an array of tables"),
            ('[metadata]\ndifficulty=[]', "metadata.difficulty must be A1, A2, or A3"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for contents, expected in cases:
                with self.subTest(contents=contents):
                    (root / "task.toml").write_text(contents + "\n")
                    issues, _ = validate(root)
                    self.assertIn(expected, [x["detail"] for x in issues if x["rule"] == "task.toml"])

    def test_malformed_rubric_fields_report_diagnostics(self):
        cases = (
            ('judge=[]', "judge must be a table"),
            ('scoring=[]', "scoring must be a table"),
            ('criterion=["R1"]', "criterion must be an array of tables"),
            ('[[criterion]]\nid="R1"\ndescription=17', "criterion R1 description must be a nonempty string"),
            ('[[criterion]]\nid="R1"\nweight=[]', "criterion R1 has invalid weight"),
            ('[[criterion]]\nid="R1"\ntype=[]', "criterion R1 has invalid type"),
            ('[[criterion]]\nid=["R1"]', "criterion 0 must have name equal to id"),
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tests").mkdir()
            (root / "tests/prompt.md").write_text("{criteria}\n")
            for contents, expected in cases:
                with self.subTest(contents=contents):
                    (root / "tests/rubrics.toml").write_text(contents + "\n")
                    issues, _ = validate(root)
                    self.assertIn(expected, [x["detail"] for x in issues if x["rule"] == "rubrics.toml"])

    def test_environment_template_placeholders(self):
        for value in (None, "", "<platform template>", "REPLACE_WITH_PLATFORM_APPROVED_TEMPLATE", "TODO", "待填写占位", "python:3.12-slim; pending confirmation", "模板未确认", "unconfirmed-template"):
            with self.subTest(value=value):
                self.assertTrue(is_unresolved_template(value))
        self.assertFalse(is_unresolved_template("python:3.12-slim"))

    def test_contract_description_keywords_and_pending_template_are_enforced(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "FIN-QA-001"
            write_package_fixture(root)
            path = root / "task.toml"
            baseline = path.read_text()
            for changed, expected in (
                (baseline.replace('description = "Static checker fixture, not a production task"\n', ''), "task.description must be a nonempty string (S03 section 3.2)"),
                (baseline.replace('["finance", "office", "A3"]', '["medical", "research", "A3"]'), 'task.keywords must be'),
                (baseline.replace('local-validation-fixture', 'python:3.12-slim; pending confirmation'), 'metadata.environment_template is unresolved'),
            ):
                with self.subTest(expected=expected):
                    path.write_text(changed)
                    issues, _ = validate(root)
                    self.assertTrue(any(x['detail'].startswith(expected) for x in issues), issues)
            path.write_text(baseline.replace('tags = ["static-fixture"]\n', ''))
            issues, warnings = validate(root)
            self.assertFalse(issues, issues)
            self.assertTrue(any('metadata.tags is absent' in x for x in warnings))

    def test_complete_five_values_do_not_hide_adu_or_bsi_serialization_errors(self):
        for levels in (
            {"0.0": "零", "0.25": "少", "0.5": "半", "0.75": "多", "1.0": "全"},
            [{"value": value, "description": "判据"} for value in (0, .25, .5, .75, 1)],
        ):
            with self.subTest(levels=levels):
                data = rubric_fixture()
                data['items'][0].update(type='Gradient', levels=levels)
                issues, _ = audit_expert_rubric(data, 'A3')
                self.assertIn('rubric-levels', {x['rule'] for x in issues})
        data = rubric_fixture()
        first = data['items'][0]
        first['objectivity'] = first.pop('criterion_type')
        first['visibility'] = first.pop('criterion_necessity')
        issues, _ = audit_expert_rubric(data, 'A3')
        self.assertEqual(2, sum(x['rule'] == 'rubrics.json' for x in issues))

    def test_golden_mirror_compares_relative_paths(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "solution/golden_output/north"
            mirror = root / "tests/__golden_output/south"
            source.mkdir(parents=True)
            mirror.mkdir(parents=True)
            (source / "report.txt").write_text("same bytes", encoding="utf-8")
            (mirror / "report.txt").write_text("same bytes", encoding="utf-8")

            issues, _ = validate(root)
            self.assertIn("golden_output directory file lists differ", [item["detail"] for item in issues])

            (root / "tests/__golden_output/north").mkdir()
            (mirror / "report.txt").unlink()
            (root / "tests/__golden_output/north/report.txt").write_text("same bytes", encoding="utf-8")
            issues, _ = validate(root)
            self.assertFalse(any(item["rule"] == "golden" for item in issues))


if __name__ == "__main__":
    unittest.main()
