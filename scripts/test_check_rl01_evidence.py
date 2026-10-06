import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from check_rl01_archive import check_archive
from check_rl01_evidence import audit_evidence, build_manifest, compare_manifest
from test_check_rl01_package import write_package_fixture


class EvidenceChecks(unittest.TestCase):
    def make_batch(self, temporary):
        batch = Path(temporary) / "batch"
        write_package_fixture(batch / "FIN-QA-001")
        (batch / "交付文档.md").write_text("Synthetic fixture only.\n")
        group = batch / "evidence/FIN-QA-001/golden"
        group.mkdir(parents=True)
        return batch, group

    def test_corrupted_external_evidence_blocks_archive(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch, group = self.make_batch(temporary)
            (group / "reward.json").write_text('{"reward":0.[REDACTED]99}')
            archive = Path(temporary) / "final.zip"
            with zipfile.ZipFile(archive, "w") as z:
                for p in batch.rglob("*"):
                    if p.is_file():
                        z.write(p, p.relative_to(batch.parent))
            result = check_archive(archive)
            self.assertFalse(result["ok"])
            self.assertTrue(result["tasks"][0]["ok"])
            self.assertIn("evidence-json", {x["rule"] for x in result["issues"]})

    def test_artifact_manifest_detects_missing_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch, group = self.make_batch(temporary)
            output = group / "output/report.md"
            output.parent.mkdir()
            output.write_text("complete output")
            import hashlib
            (group / "artifact-manifest.json").write_text(json.dumps({"artifacts": [
                {"path": "output/report.md", "bytes": output.stat().st_size,
                 "sha256": hashlib.sha256(output.read_bytes()).hexdigest()}]}))
            self.assertTrue(audit_evidence(batch)["ok"])
            output.unlink()
            result = audit_evidence(batch)
            self.assertFalse(result["ok"])
            self.assertEqual("evidence-artifact", result["issues"][0]["rule"])

    def test_manifest_detects_input_deletion_and_byte_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch, _ = self.make_batch(temporary)
            source = batch / "FIN-QA-001/environment/input_files/extra.txt"
            source.write_text("original source")
            manifest = build_manifest(batch)
            self.assertEqual([], compare_manifest(batch, manifest))
            source.unlink()
            self.assertEqual("archive-manifest-missing", compare_manifest(batch, manifest)[0]["rule"])
            source.write_text("changed source")
            self.assertEqual("archive-manifest-changed", compare_manifest(batch, manifest)[0]["rule"])

    def test_index_requires_declared_trajectory_or_explanation(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch, group = self.make_batch(temporary)
            index = group.parent / "index.json"
            data = {"evidence": {"golden": "golden/"},
                    "required_evidence_files": ["trajectory.json"]}
            index.write_text(json.dumps(data))
            self.assertFalse(audit_evidence(batch)["ok"])
            data["trajectory_not_applicable"] = {"golden": {
                "required": False, "reason": "Artifacts were copied; no model generation was executed.",
                "generation_record": "generation-record.json"}}
            index.write_text(json.dumps(data))
            self.assertFalse(audit_evidence(batch)["ok"])
            (group / "generation-record.json").write_text('{"action":"copy","status":"completed"}')
            self.assertTrue(audit_evidence(batch)["ok"])

    def test_candidate_only_trajectory_does_not_invent_golden_requirement(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch, group = self.make_batch(temporary)
            candidate = group.parent / "gpt"
            candidate.mkdir()
            (candidate / "trajectory.json").write_text('{"steps":[]}')
            (group.parent / "index.json").write_text(json.dumps({
                "evidence": {"golden": "golden/", "gpt": "gpt/"},
                "required_evidence_files": ["trajectory.json for each candidate"]}))
            self.assertTrue(audit_evidence(batch)["ok"])
            (candidate / "trajectory.json").unlink()
            self.assertFalse(audit_evidence(batch)["ok"])

    def test_negative_raw_value_and_reason_are_reviewed_without_score_rewrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch, group = self.make_batch(temporary)
            import tomllib
            path = batch / "FIN-QA-001/tests/rubrics.toml"
            text = path.read_text()
            # Add one independent negative item to the fixture's actual rule set.
            text += '\n[[criterion]]\nid="N29"\nname="N29"\ntype="binary"\nweight=10.0\nnegate=true\ndescription="Fabricated execution claims. Deliverables to inspect: output/report.txt."\n'
            path.write_text(text)
            rules = tomllib.loads(text)["criterion"]
            rows = [{"id": r["id"], "raw": "no" if r.get("negate") else "yes", "value": 1.0,
                     "weight": r["weight"], "reasoning": "All requirements satisfied."}
                    for r in rules if r["id"] != "N29"]
            rows.append({"id": "N29", "raw": "yes", "value": 0.0,
                         "weight": 10.0, "reasoning": "No N29 violation."})
            detail = group / "reward-details.json"
            detail.write_text(json.dumps({"reward": {"criteria": rows}}))
            before = detail.read_bytes()
            result = audit_evidence(batch)
            self.assertTrue(result["ok"], result)
            self.assertTrue(result["review_required"])
            self.assertIn("evidence-judge-reason", {x["rule"] for x in result["warnings"]})
            self.assertEqual(before, detail.read_bytes())
            rows[-1]["value"] = 1.0
            detail.write_text(json.dumps({"reward": {"criteria": rows}}))
            self.assertIn("evidence-score-row", {x["rule"] for x in audit_evidence(batch)["issues"]})

    def test_score_carriers_must_match_full_aggregation(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch, group = self.make_batch(temporary)
            import tomllib
            rules = tomllib.loads((batch / "FIN-QA-001/tests/rubrics.toml").read_text())["criterion"]
            rows = [{"id": r["id"], "raw": "no" if r.get("negate") else "yes", "value": 1.0, "weight": r["weight"]}
                    for r in rules]
            (group / "reward-details.json").write_text(json.dumps({"reward": {"criteria": rows}}))
            main = group / "reward.json"
            main.write_text(json.dumps({"reward": 1.0, "graded_score": 1.0,
                                        "criteria_counted": len(rows), "verifier_error": 0}))
            (group / "reward.txt").write_text("1.0")
            self.assertTrue(audit_evidence(batch)["ok"])
            main.write_text(json.dumps({"reward": 0.8, "criteria_counted": len(rows), "verifier_error": 0}))
            self.assertIn("evidence-score-total", {x["rule"] for x in audit_evidence(batch)["issues"]})

    def test_duplicate_keys_nonfinite_and_unsafe_manifest_paths_are_blocked(self):
        with tempfile.TemporaryDirectory() as temporary:
            batch, group = self.make_batch(temporary)
            bad = group / "record.json"
            for text in ('{"score":1,"score":0}', '{"score":NaN}'):
                bad.write_text(text)
                self.assertIn("evidence-json", {x["rule"] for x in audit_evidence(batch)["issues"]})
            bad.write_text(json.dumps({"artifacts": [{"path": "../../../../escape", "sha256": "a" * 64}]}))
            self.assertIn("evidence-artifact", {x["rule"] for x in audit_evidence(batch)["issues"]})


if __name__ == "__main__":
    unittest.main()
