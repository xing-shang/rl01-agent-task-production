"""Offline Pro-review and candidate-only queue tests; no Docker or model is started."""
import copy
import json
import subprocess
import tempfile
import tomllib
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest import mock

import check_pro_golden_review as author
import vps_harbor as runtime
import vps_queue as scheduler
from test_check_rl01_package import write_package_fixture


def review_fixture(task):
    config = tomllib.loads((task / "task.toml").read_text())
    items = tomllib.loads((task / "tests/rubrics.toml").read_text())["criterion"]
    return {"mode": "author_simulation", "external_judge_executed": False,
            "task_id": config["metadata"]["task_id"], "task_version": config["task"]["version"],
            "task_toml_sha256": author.sha256(task / "task.toml"),
            "material_sha256": author.material_hashes(task), "simulated_score": 1.0,
            "unresolved_items": [], "criteria": [
                {"criterion_id": item["id"], "target_file": "output/report.txt",
                 "evidence": "report.txt line 1 contains the checked value",
                 "raw": 0 if item.get("negate") else 1, "value": 1.0,
                 "weight": item["weight"], "negate": item.get("negate", False),
                 "reason": "Offline fixture evidence only"} for item in items]}


class ProReviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="rl01-pro-review-test-")
        self.root = Path(self.directory.name).resolve()
        self.task = self.root / "source/FIN-QA-001"
        self.task.mkdir(parents=True)
        write_package_fixture(self.task)
        self.data = review_fixture(self.task)
        self.review = self.root / "pro-review.json"

    def tearDown(self):
        self.directory.cleanup()

    def write_review(self, data=None):
        self.review.write_text(json.dumps(self.data if data is None else data), encoding="utf-8")
        return self.review

    def test_accepts_complete_review_without_claiming_external_execution(self):
        receipt = author.validate(self.task, self.write_review())
        self.assertEqual(receipt["simulated_score"], 1)
        self.assertEqual(receipt["criteria_counted"], 25)
        self.assertFalse(receipt["external_judge_executed"])
        self.assertEqual(receipt["source"], "web_pro_self_review")

    def test_changed_inputs_answers_rules_or_source_config_reject_stale_review(self):
        self.write_review()
        for name in ("instruction.md", "environment/input_files/data.csv",
                     "solution/golden_output/report.txt", "tests/rubrics.toml", "task.toml"):
            with self.subTest(name=name):
                path = self.task / name
                original = path.read_bytes()
                path.write_bytes(original + b"\n# changed after author review\n")
                with self.assertRaises(ValueError):
                    author.validate(self.task, self.review)
                path.write_bytes(original)

    def test_missing_duplicate_and_unknown_criteria_are_rejected(self):
        for edit in (lambda rows: rows.pop(), lambda rows: rows.append(copy.deepcopy(rows[0])),
                     lambda rows: rows[0].update(criterion_id="unknown")):
            data = copy.deepcopy(self.data)
            edit(data["criteria"])
            with self.subTest(criteria=data["criteria"]):
                with self.assertRaises(ValueError):
                    author.validate(self.task, self.write_review(data))

    def test_false_external_execution_incomplete_evidence_and_fabricated_scores_reject(self):
        variants = [
            {"mode": "formal_judge"}, {"external_judge_executed": True},
            {"task_version": "1.0.1"}, {"unresolved_items": ["R1"]},
            {"simulated_score": 0.9}, {"simulated_score": float("nan")},
            {"simulated_score": float("inf")}, {"simulated_score": True}]
        for changes in variants:
            data = {**self.data, **changes}
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    author.validate(self.task, self.write_review(data))
        for changes in ({"value": None}, {"raw": 0}, {"negate": True},
                        {"weight": 3}, {"evidence": ""}, {"status": "UNVERIFIABLE"}):
            data = copy.deepcopy(self.data)
            data["criteria"][0].update(changes)
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError):
                    author.validate(self.task, self.write_review(data))

    def test_negative_criterion_is_inverted_once_and_score_is_recomputed(self):
        data = copy.deepcopy(self.data)
        data["criteria"][-1].update(raw=1, value=0)
        data["simulated_score"] = 171 / 174
        receipt = author.validate(self.task, self.write_review(data))
        self.assertAlmostEqual(receipt["simulated_score"], 171 / 174)
        data["criteria"][-1]["value"] = 1
        with self.assertRaisesRegex(ValueError, "raw/value"):
            author.validate(self.task, self.write_review(data))

    def test_raw_likert_highest_band_and_exact_threshold(self):
        path = self.task / "tests/rubrics.toml"
        original = path.read_text()
        path.write_text(original.replace('type="binary"', 'type="likert"', 1))
        data = review_fixture(self.task)
        data["criteria"][0]["raw"] = 5
        self.assertEqual(author.validate(self.task, self.write_review(data))["simulated_score"], 1)
        data["criteria"][0]["raw"] = 1
        with self.assertRaisesRegex(ValueError, "raw/value"):
            author.validate(self.task, self.write_review(data))
        path.write_text('[judge]\n[[criterion]]\nid="R1"\ntype="binary"\nweight=17\n'
                        '[[criterion]]\nid="R2"\ntype="binary"\nweight=3\n')
        data = review_fixture(self.task)
        data["criteria"][1].update(raw=0, value=0)
        data["simulated_score"] = 0.85
        with self.assertRaisesRegex(ValueError, "strictly above"):
            author.validate(self.task, self.write_review(data))

    def runtime_context(self):
        stack = ExitStack()
        for target, kwargs in (("PREFIX", {"new": self.root}),
                               ("bridge_ip", {"return_value": "127.0.0.1"}),
                               ("host_status", {"return_value": {}})):
            stack.enter_context(mock.patch.object(runtime, target, **kwargs))
        stack.enter_context(mock.patch.object(scheduler, "ensure_worker"))
        return stack

    def finish_candidates(self, queue, run):
        while (unit := queue.claim()) is not None:
            self.assertEqual(unit["kind"], "candidate")
            task = scheduler.run_manifest(run)["task"]
            trial = run / "jobs" / unit["id"] / "fixture-trial"
            (trial / "artifacts").mkdir(parents=True)
            (trial / "config.json").write_text(json.dumps({
                "task": {"path": task}, "agent": {"name": "claude-code"}}))
            (trial / "artifacts/manifest.json").write_text("[]")
            (trial / "artifacts/report.txt").write_text("offline saved candidate")
            queue.finish(unit["id"], True, {"trials": [str(trial)]})
            scheduler.refresh_run(queue, run)

    def test_pro_mode_queues_only_three_candidates_and_three_grades_idempotently(self):
        with self.runtime_context():
            run = runtime.prepare(self.task, 4, pro_review=self.write_review(), skip_formal_golden=True)
            manifest = scheduler.run_manifest(run)
            self.assertFalse(manifest["golden_valid"])
            self.assertFalse(manifest["local_golden_scoring_executed"])
            self.assertFalse((run / "golden.json").exists())
            queue = scheduler.Queue()
            scheduler.submit_runs([run])
            scheduler.submit_runs([run])
            self.assertEqual(len(queue.rows()), 3)
            self.finish_candidates(queue, run)
            self.assertEqual(scheduler.run_manifest(run)["status"], "CANDIDATES_AWAITING_REGRADE")
            with mock.patch.object(runtime.subprocess, "check_output",
                                   return_value=b'[{"Id":"sha256:fixture"}]'), \
                    mock.patch.object(runtime.subprocess, "run",
                                      return_value=subprocess.CompletedProcess([], 0)):
                with mock.patch.object(runtime, "prepare_verifier", wraps=runtime.prepare_verifier) as adapter:
                    # Supply the preserved image identity without building Docker.
                    current = scheduler.run_manifest(run)
                    current.update(cache_image_tag="fixture", cache_image_id="sha256:fixture")
                    scheduler.atomic_json(run / "manifest.json", current)
                    result = scheduler.submit_grades([run])
                    scheduler.submit_grades([run])
                    self.assertEqual(adapter.call_count, 1)
            rows = queue.rows()
            self.assertEqual(len(rows), 6)
            self.assertEqual(sum(row["kind"] == "regrade_candidate" for row in rows), 3)
            self.assertFalse(any("golden" in row["kind"] for row in rows))
            self.assertTrue(all(row["dependency"] is None for row in rows))
            self.assertEqual(result["status"], "CANDIDATE_REGRADE_PRO_REVIEW_ACCEPTED")
            self.assertEqual(queue.claim()["kind"], "regrade_candidate")
            self.assertFalse(scheduler.run_manifest(run)["golden_valid"])

    def test_frozen_review_is_checked_again_before_queueing_and_grading(self):
        with self.runtime_context():
            run = runtime.prepare(self.task, 4, pro_review=self.write_review(), skip_formal_golden=True)
            manifest = scheduler.run_manifest(run)
            frozen_review = Path(manifest["pro_golden_review"]["path"])
            original = frozen_review.read_text()
            frozen_review.write_text(original + "\n")
            with self.assertRaisesRegex(ValueError, "receipt changed"):
                scheduler.submit_runs([run])
            frozen_review.write_text(original)
            frozen = Path(manifest["task"])
            self.assertTrue(runtime.candidate_grade_allowed(manifest, frozen))
            (frozen / "tests/rubrics.toml").write_text(
                (frozen / "tests/rubrics.toml").read_text() + "\n# scoring changed\n")
            with self.assertRaisesRegex(ValueError, "hashes"):
                runtime.candidate_grade_allowed(manifest, frozen)

    def test_batch_imports_separate_pro_records_and_preserves_source_configs(self):
        records = self.root / "author-records"
        records.mkdir()
        (records / (self.task.name + ".json")).write_text(json.dumps(self.data))
        original = (self.task / "task.toml").read_bytes()
        with self.runtime_context():
            result = runtime.prepare_batch([self.task], 4, pro_review_dir=records, skip_formal_golden=True)
            runs = scheduler.batch_runs(Path(result["batch_dir"]))
            scheduler.submit_runs(runs)
            self.assertEqual(len(scheduler.Queue().rows()), 3)
            self.assertEqual((self.task / "task.toml").read_bytes(), original)
            self.assertEqual((runs[0] / "source-task.toml").read_bytes(), original)
            records.joinpath(self.task.name + ".json").unlink()
            with self.assertRaises(FileNotFoundError):
                runtime.prepare_batch([self.task], 4, pro_review_dir=records)

    def test_importing_pro_review_keeps_real_golden_and_grade_gate_by_default(self):
        with self.runtime_context():
            run = runtime.prepare(self.task, 4, pro_review=self.write_review())
            manifest = scheduler.run_manifest(run)
            self.assertEqual(manifest["golden_review_mode"], "formal_golden")
            self.assertTrue(manifest["formal_golden_required"])
            self.assertTrue((run / "golden.json").exists())
            self.assertFalse(runtime.candidate_grade_allowed(manifest, Path(manifest["task"])))
            scheduler.submit_runs([run])
            rows = scheduler.Queue().rows()
            self.assertEqual(len(rows), 4)
            self.assertEqual(sum(x["kind"] == "golden" for x in rows), 1)
            self.assertEqual(sum(x["kind"] == "candidate" for x in rows), 3)

    def test_explicit_skip_cannot_run_without_author_review(self):
        with self.assertRaisesRegex(ValueError, "explicit flag"):
            runtime.prepare(self.task, 4, skip_formal_golden=True)
        with self.assertRaisesRegex(ValueError, "explicit flag"):
            runtime.prepare_batch([self.task], 4, skip_formal_golden=True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
