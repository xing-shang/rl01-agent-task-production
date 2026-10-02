#!/usr/bin/env python3
"""Offline multi-process queue tests. No provider, Docker or live job is used."""
import concurrent.futures
import importlib.util
import json
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import tomllib
import unittest
from contextlib import closing
from pathlib import Path
from unittest import mock

import vps_harbor as runtime
import vps_queue as scheduler
from test_check_rl01_package import write_package_fixture


class QueueTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="rl01-queue-test-")
        self.root = Path(self.directory.name)
        self.queue = scheduler.Queue(self.root)

    def tearDown(self):
        self.directory.cleanup()

    def add_run(self, name, cap=4):
        path = self.root / "runs" / name
        self.queue.add(path, name, cap,
                       [{"key": "golden", "kind": "golden"}] +
                       [{"key": str(number), "kind": "candidate", "model": str(number)} for number in range(3)])
        return path

    def test_distinct_tasks_share_eight_slots_and_rotate(self):
        for name in ("task-a", "task-b", "task-c"):
            self.add_run(name)
        claimed = [self.queue.claim() for _ in range(8)]
        self.assertEqual(len({row["run_dir"] for row in claimed}), 3)
        self.assertIsNone(self.queue.claim())
        self.assertEqual(sum(row["state"] == "RUNNING" for row in self.queue.rows()), 8)
        self.queue.finish(claimed[0]["id"], True, {"golden_valid": True})
        self.assertIsNotNone(self.queue.claim())

    def test_cap_two_is_per_task_and_capacity_ceiling_is_global(self):
        first = self.add_run("first", cap=2)
        self.queue.claim()
        self.queue.claim()
        self.assertIsNone(self.queue.claim())
        second = self.add_run("second")
        third = self.queue.claim(capacity=3)
        self.assertEqual(third["run_dir"], str(second))
        self.assertIsNone(self.queue.claim(capacity=3))
        self.assertEqual(sum(r["run_dir"] == str(first) and r["state"] == "RUNNING"
                             for r in self.queue.rows()), 2)

    def test_large_batch_advances_started_tasks_before_opening_more(self):
        for number in range(20):
            self.add_run(f"task-{number:02}")
        claimed = [self.queue.claim() for _ in range(8)]
        self.assertEqual(len({r["run_dir"] for r in claimed}), 8)
        self.queue.finish(claimed[0]["id"], True, {"golden_valid": True})
        next_unit = self.queue.claim()
        self.assertEqual(next_unit["run_dir"], claimed[0]["run_dir"])
        self.assertEqual(next_unit["kind"], "candidate")

    def test_duplicate_submissions_do_not_duplicate_execution(self):
        self.add_run("same")
        self.add_run("same")
        self.assertEqual(len(self.queue.rows()), 4)

    def test_concurrent_processes_cannot_exceed_eight_claims(self):
        self.add_run("a")
        self.add_run("b")
        self.add_run("c")
        code = ("import sys,json; from pathlib import Path; "
                "sys.path.insert(0,sys.argv[1]); from vps_queue import Queue; "
                "r=Queue(Path(sys.argv[2])).claim(); print(json.dumps(r and r['id']))")
        def claim():
            return json.loads(subprocess.check_output(
                [sys.executable, "-B", "-c", code, str(Path(__file__).parent), str(self.root)]))
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
            results = list(pool.map(lambda _: claim(), range(12)))
        identifiers = [result for result in results if result]
        self.assertEqual((len(identifiers), len(set(identifiers))), (8, 8))

    def test_two_tasks_each_hold_four_claims(self):
        self.add_run('one')
        self.add_run('two')
        claimed = [self.queue.claim() for _ in range(8)]
        self.assertEqual(sorted(sum(r['run_dir'] == str(self.root/'runs'/name) for r in claimed)
                                for name in ('one', 'two')), [4, 4])
        self.assertIsNone(self.queue.claim())

    def test_api_slots_are_shared_across_twelve_proxy_processes(self):
        stats = self.root / "api-stats.sqlite3"
        with closing(sqlite3.connect(stats)) as db:
            db.execute("CREATE TABLE stats(active INTEGER,peak INTEGER,total INTEGER)")
            db.execute("INSERT INTO stats VALUES(0,0,0)")
            db.commit()
        release = self.root / "release"
        code = """
import sys,sqlite3,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from vps_request_proxy import ProxyConfig
root=Path(sys.argv[2])
config=ProxyConfig('http://unused','test-upstream','test-client',root/'unused-audit',
                   shared_slot_dir=root/'api-slots')
with config.request_slot():
    with sqlite3.connect(root/'api-stats.sqlite3',timeout=10) as db:
        db.execute('UPDATE stats SET active=active+1,peak=max(peak,active+1),total=total+1')
    deadline=time.monotonic()+8
    while not (root/'release').exists() and time.monotonic()<deadline:
        time.sleep(0.01)
    with sqlite3.connect(root/'api-stats.sqlite3',timeout=10) as db:
        db.execute('UPDATE stats SET active=active-1')
"""
        children = [subprocess.Popen([sys.executable, "-B", "-c", code,
                    str(Path(__file__).parent), str(self.root)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    for _ in range(12)]
        try:
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                with closing(sqlite3.connect(stats)) as db:
                    active, peak, total = db.execute("SELECT * FROM stats").fetchone()
                if active == 8:
                    break
                time.sleep(0.01)
            self.assertEqual((active, peak, total), (8, 8, 8))
        finally:
            release.touch()
            for child in children:
                output, error = child.communicate(timeout=10)
                self.assertEqual(child.returncode, 0, output + error)
        with closing(sqlite3.connect(stats)) as db:
            self.assertEqual(db.execute("SELECT * FROM stats").fetchone(), (0, 8, 12))

    def test_failure_frees_slot_without_replaying_that_unit(self):
        self.add_run("task")
        claims = [self.queue.claim() for _ in range(4)]
        self.queue.finish(claims[0]["id"], False, {"reason": "local failure"})
        self.assertIsNone(self.queue.claim())
        self.add_run("another")
        self.assertNotEqual(self.queue.claim()["id"], claims[0]["id"])

    def test_golden_dependencies_are_per_task_and_invalid_goldens_block(self):
        for name in ("a", "b"):
            path = self.root / name
            self.queue.add(path, name, 4, [
                {"key": "golden-score", "kind": "regrade_golden"},
                {"key": "candidate-score", "kind": "regrade_candidate", "dependency": "golden-score"}])
        a = self.queue.claim()
        b = self.queue.claim()
        self.assertIsNone(self.queue.claim())
        self.queue.finish(a["id"], True, {"golden_valid": False})
        self.queue.finish(b["id"], True, {"golden_valid": True})
        candidate = self.queue.claim()
        self.assertEqual(candidate["run_dir"], b["run_dir"])
        self.assertEqual(sum(row["state"] == "BLOCKED" for row in self.queue.rows()), 1)

    def test_candidate_added_after_invalid_golden_is_immediately_blocked(self):
        path = self.root / "task"
        self.queue.add(path, "task", 4, [{"key": "g", "kind": "regrade_golden"}])
        golden = self.queue.claim()
        self.queue.finish(golden["id"], True, {"golden_valid": False})
        self.queue.add(path, "task", 4, [{"key": "c", "kind": "regrade_candidate", "dependency": "g"}])
        self.assertEqual(self.queue.rows()[-1]["state"], "BLOCKED")
        self.assertIsNone(self.queue.claim())

    def test_restart_preserves_interrupted_units_and_orphans(self):
        self.add_run("task")
        unit = self.queue.claim()
        self.queue.child(unit["id"], 123456789)
        with self.queue.connect() as db:
            db.execute('UPDATE units SET owner_pid=NULL,owner_start=NULL WHERE id=?', (unit['id'],))
        with mock.patch.object(scheduler, "process_alive", side_effect=lambda pid, _: pid == 123456789):
            self.queue.recover()
        self.assertEqual(self.queue.rows()[0]["state"], "ORPHANED")
        other = self.queue.claim()
        with mock.patch.object(scheduler, "process_alive", return_value=False):
            self.queue.reap_orphans()
        rows = {r["id"]: r for r in self.queue.rows()}
        self.assertEqual(rows[unit["id"]]["state"], "INTERRUPTED")
        self.assertEqual(rows[other["id"]]["state"], "RUNNING")

    def test_live_owner_keeps_running_claims_without_replay_during_handoff(self):
        self.add_run('draining-owner')
        with mock.patch.object(scheduler, 'process_start', return_value='owner-start'):
            unit = self.queue.claim()
            self.queue.recover()
        rows = {r['id']: r for r in self.queue.rows()}
        self.assertEqual(rows[unit['id']]['state'], 'RUNNING')
        self.assertEqual(rows[unit['id']]['owner_pid'], unit['owner_pid'])
        self.assertIsNone(rows[unit['id']]['child_pid'])

    def test_existing_harbor_and_high_cpu_load_allow_spare_slots(self):
        path = self.add_run("own")
        self.queue.claim()
        (path / "jobs/golden/OWNED__TrIal").mkdir(parents=True)
        host = {"cpu_count": 2, "load": (99, 99, 99), "memory_available_mb": 6000,
                "free_disk_gb": 50, "foreign_harbor_pids": [100, 200]}
        with mock.patch.object(runtime, "host_status", return_value=host), \
                mock.patch.object(scheduler.subprocess, "check_output",
                                  return_value=b"legacy__env\nlegacy__verifier__trial\nowned__trial__env\n"):
            snapshot = scheduler.capacity_snapshot(self.queue)
        self.assertEqual(snapshot["capacity"], 8)
        self.assertEqual(snapshot["external_trial_projects"], ["legacy__env", "legacy__verifier__trial"])
        self.assertIsNone(snapshot["waiting_reason"])

    def test_resource_pressure_defers_new_work_without_losing_queue(self):
        self.add_run("own")
        host = {"cpu_count": 2, "load": (0, 0, 0), "memory_available_mb": 1000,
                "free_disk_gb": 50, "foreign_harbor_pids": []}
        with mock.patch.object(runtime, "host_status", return_value=host), \
                mock.patch.object(scheduler.subprocess, "check_output", return_value=b""):
            snapshot = scheduler.capacity_snapshot(self.queue)
        self.assertIsNone(self.queue.claim(snapshot["capacity"]))
        self.assertEqual(snapshot["waiting_reason"], "MEMORY_AVAILABLE_BELOW_1536_MB")
        self.assertEqual({r["state"] for r in self.queue.rows()}, {"QUEUED"})

    def test_prepare_and_submit_two_tasks_have_independent_manifests(self):
        tasks = []
        for number in (1, 2):
            task = self.root / "inputs" / f"FIN-QA-00{number}"
            task.mkdir(parents=True)
            write_package_fixture(task)
            if number == 2:
                config = task / "task.toml"
                config.write_text(config.read_text().replace("FIN-QA-001", "FIN-QA-002").replace("fin-qa-001", "fin-qa-002"))
            tasks.append(task)
        with mock.patch.object(runtime, "PREFIX", self.root), \
                mock.patch.object(runtime, "bridge_ip", return_value="127.0.0.1"), \
                mock.patch.object(runtime, "host_status", return_value={}), \
                mock.patch.object(scheduler, "ensure_worker"):
            batch = runtime.prepare_batch(tasks, 4)
            paths = scheduler.batch_runs(Path(batch["batch_dir"]))
            self.assertEqual(len(paths), 2)
            scheduler.submit_runs(paths)
            scheduler.submit_runs(paths)
            self.assertEqual(len(self.queue.rows()), 8)
            manifests = [json.loads((path / "manifest.json").read_text()) for path in paths]
            self.assertEqual(len({manifest["task"] for manifest in manifests}), 2)
            self.assertEqual({manifest["status"] for manifest in manifests}, {"QUEUED"})
            self.assertEqual({manifest["resource_policy"]["memory_mb"] for manifest in manifests}, {2048})
            for manifest in manifests:
                config = tomllib.loads((Path(manifest["task"]) / "task.toml").read_text())
                self.assertEqual(config["environment"]["memory_mb"], 2048)
            while (unit := self.queue.claim()) is not None:
                path = Path(unit["run_dir"])
                task = json.loads((path / "manifest.json").read_text())["task"]
                trial = path / "jobs" / unit["id"] / ("fixture__" + unit["id"])
                (trial / "artifacts").mkdir(parents=True)
                (trial / "config.json").write_text(json.dumps({
                    "task": {"path": task},
                    "agent": {"name": "oracle" if unit["kind"] == "golden" else "claude-code"}}))
                (trial / "artifacts/manifest.json").write_text("[]")
                (trial / "artifacts/report.txt").write_text("saved output")
                receipt = {"trials": [str(trial)]}
                if unit["kind"] == "golden":
                    receipt["golden_valid"] = True
                self.queue.finish(unit["id"], True, receipt)
                scheduler.refresh_run(self.queue, path)
            def adapter(path, _):
                return {"verifier_task": json.loads((path / "manifest.json").read_text())["task"]}
            with mock.patch.object(runtime, "prepare_verifier", side_effect=adapter) as prepare_verifier:
                scheduler.submit_grades(paths)
                scheduler.submit_grades(paths)
                self.assertEqual(prepare_verifier.call_count, 2)
            rows = self.queue.rows()
            self.assertEqual(len(rows), 16)
            self.assertEqual(sum(r["kind"] == "regrade_golden" for r in rows), 2)
            self.assertEqual(sum(r["kind"] == "regrade_candidate" for r in rows), 6)
            by_id = {row["id"]: row for row in rows}
            for row in rows:
                if row["kind"] == "regrade_candidate":
                    self.assertEqual(by_id[row["dependency"]]["run_dir"], row["run_dir"])
            candidate = next(r for r in rows if r["kind"] == "regrade_candidate")
            payload = json.loads(candidate["payload"])
            (Path(payload["source"]) / "artifacts/report.txt").write_text("tampered after queuing")
            with self.assertRaisesRegex(ValueError, "artifacts changed"):
                scheduler.execute_unit(self.queue, candidate)
            policy = paths[0] / "runtime-compose.yaml"
            policy.write_text(policy.read_text() + "\n# modified after freezing\n")
            with self.assertRaisesRegex(ValueError, "runtime policy changed"):
                scheduler.run_manifest(paths[0])

    def test_resource_freeze_preserves_source_and_records_distinct_versions(self):
        task = self.root / "input/FIN-QA-001"
        task.mkdir(parents=True)
        write_package_fixture(task)
        config = task / "task.toml"
        config.write_text(config.read_text() + 'memory_mb = 8192\n[verifier.environment]\nmemory_mb = 8192\n')
        original, source_digest = config.read_bytes(), runtime.tree_hash(task)
        with mock.patch.object(runtime, "PREFIX", self.root), \
                mock.patch.object(runtime, "bridge_ip", return_value="127.0.0.1"), \
                mock.patch.object(runtime, "host_status", return_value={}):
            default_run = runtime.prepare(task, 4)
            larger_run = runtime.prepare(task, 4, memory_mb=4096)
            with self.assertRaisesRegex(ValueError, "positive integer"):
                runtime.prepare(task, 4, memory_mb=0)
        self.assertEqual(config.read_bytes(), original)
        manifests = [json.loads((run / "manifest.json").read_text()) for run in (default_run, larger_run)]
        for run, manifest, memory in zip((default_run, larger_run), manifests, (2048, 4096)):
            frozen = Path(manifest["task"])
            effective = tomllib.loads((frozen / "task.toml").read_text())
            self.assertEqual(effective["environment"]["memory_mb"], memory)
            self.assertEqual(effective["verifier"]["environment"]["memory_mb"], memory)
            self.assertEqual((run / "source-task.toml").read_bytes(), original)
            self.assertEqual(manifest["source_task_digest"], source_digest)
            restored = self.root / f"restored-{memory}"
            shutil.copytree(frozen, restored)
            shutil.copy2(run / "source-task.toml", restored / "task.toml")
            self.assertEqual(runtime.tree_hash(restored), source_digest)
        self.assertNotEqual(manifests[0]["agent_visible_digest"], manifests[1]["agent_visible_digest"])
        self.assertNotEqual(manifests[0]["agent_visible_digest"], runtime.tree_hash(task, True))

    def test_verifier_adapter_inherits_frozen_limits_including_legacy_runs(self):
        task = self.root / "input/FIN-QA-001"
        task.mkdir(parents=True)
        write_package_fixture(task)
        with mock.patch.object(runtime, "PREFIX", self.root), \
                mock.patch.object(runtime, "bridge_ip", return_value="127.0.0.1"), \
                mock.patch.object(runtime, "host_status", return_value={}):
            for memory in (2048, 8192):
                run = runtime.prepare(task, 4, memory_mb=memory)
                manifest = json.loads((run / "manifest.json").read_text())
                if memory == 8192:
                    manifest.pop("resource_policy")
                    manifest.pop("source_task_digest")
                    manifest.pop('judge_execution')
                    (run / "manifest.json").write_text(json.dumps(manifest))
                image = b'[{"Id":"sha256:fixture-image"}]'
                with mock.patch.object(runtime.subprocess, "check_output", return_value=image), \
                        mock.patch.object(runtime.subprocess, "run", return_value=mock.Mock(returncode=0)):
                    adapter = runtime.prepare_verifier(run, "fixture-image")
                effective = tomllib.loads((Path(adapter["verifier_task"]) / "task.toml").read_text())
                self.assertEqual(effective["environment"]["memory_mb"], memory)
                self.assertNotIn("environment", effective["verifier"])
                self.assertEqual(adapter["agent_visible_digest"], manifest["agent_visible_digest"])
                self.assertEqual(adapter['judge_execution']['criterion_workers'], 1 if memory == 8192 else 2)

    def test_parallel_verifier_preserves_fixed_templates_and_frozen_agent_configuration(self):
        task = self.root / 'input/FIN-QA-001'
        task.mkdir(parents=True)
        write_package_fixture(task)
        with mock.patch.object(runtime, 'PREFIX', self.root), \
                mock.patch.object(runtime, 'bridge_ip', return_value='127.0.0.1'), \
                mock.patch.object(runtime, 'host_status', return_value={}):
            run = runtime.prepare(task, 4)
            manifest = json.loads((run / 'manifest.json').read_text())
            frozen = Path(manifest['task'])
            original = {name: (frozen / name).read_bytes() for name in
                        ('task.toml', 'tests/test.sh', 'tests/finalize.py', 'tests/prompt.md', 'tests/rubrics.toml')}
            with mock.patch.object(runtime.subprocess, 'check_output', return_value=b'[{"Id":"sha256:fixture"}]'), \
                    mock.patch.object(runtime.subprocess, 'run', return_value=mock.Mock(returncode=0)):
                receipt = runtime.prepare_verifier(run, 'fixture')
            verifier = Path(receipt['verifier_task'])
            for name, content in original.items():
                self.assertEqual((frozen / name).read_bytes(), content)
                if name != 'task.toml':
                    self.assertEqual((verifier / name).read_bytes(), content)
            self.assertEqual(runtime.tree_hash(frozen), manifest['task_digest'])
            effective = tomllib.loads((verifier / 'task.toml').read_text())
            self.assertEqual(effective['verifier']['env']['RL01_CRITERION_WORKERS'], '2')
            self.assertIn('bubblewrap', (verifier / 'tests/Dockerfile').read_text())
            self.assertIn('SYS_ADMIN', (verifier / 'tests/docker-compose.yaml').read_text())
            script = run / 'judge-runtime/vps_parallel_rewardkit.py'
            script.write_text(script.read_text() + '\n# changed after freeze\n')
            with self.assertRaisesRegex(ValueError, 'Frozen Judge runtime changed'):
                scheduler.run_manifest(run)

    def test_regrade_rejects_artifacts_generated_with_a_different_memory_limit(self):
        task = self.root / "input/FIN-QA-001"
        task.mkdir(parents=True)
        write_package_fixture(task)
        with mock.patch.object(runtime, "PREFIX", self.root), \
                mock.patch.object(runtime, "bridge_ip", return_value="127.0.0.1"), \
                mock.patch.object(runtime, "host_status", return_value={}):
            old_run = runtime.prepare(task, 4, memory_mb=8192)
            new_run = runtime.prepare(task, 4)
            old = json.loads((old_run / "manifest.json").read_text())
            new = json.loads((new_run / "manifest.json").read_text())
            source = self.root / "old-trial"
            source.mkdir()
            (source / "config.json").write_text(json.dumps({"task": {"path": old["task"]}, "agent": {"name": "oracle"}}))
            with self.assertRaisesRegex(ValueError, "different Agent-visible task"):
                scheduler.submit_regrade(source, Path(new["task"]), new_run, golden=True, start_worker=False)

    @unittest.skipUnless(importlib.util.find_spec("harbor"), "Installed Harbor defaults are verified on VPS")
    def test_saved_oracle_without_default_agent_fields_can_be_queued_for_regrade(self):
        task = self.root / "input/FIN-QA-001"
        task.mkdir(parents=True)
        write_package_fixture(task)
        with mock.patch.object(runtime, "PREFIX", self.root), \
                mock.patch.object(runtime, "bridge_ip", return_value="127.0.0.1"), \
                mock.patch.object(runtime, "host_status", return_value={}):
            run = runtime.prepare(task, 4)
            manifest = json.loads((run / "manifest.json").read_text())
            source = self.root / "oracle-trial"
            (source / "artifacts").mkdir(parents=True)
            config = {"task": {"path": manifest["task"]}}
            (source / "config.json").write_text(json.dumps(config))
            (source / "artifacts/manifest.json").write_text("[]")
            queued = scheduler.submit_regrade(source, Path(manifest["task"]), run,
                                               golden=True, start_worker=False)
            self.assertEqual(queued["status"], "QUEUED_ASYNCHRONOUSLY")
            config["agent"] = {"name": "claude-code"}
            (source / "config.json").write_text(json.dumps(config))
            with self.assertRaisesRegex(ValueError, "Oracle source"):
                scheduler.submit_regrade(source, Path(manifest["task"]), run,
                                         golden=True, start_worker=False)

    def test_reward_audit_never_mutates_frozen_task_even_with_bytecode_enabled(self):
        task = self.root / "audit-fixture"
        task.mkdir()
        write_package_fixture(task)
        before = runtime.tree_hash(task)
        with mock.patch.object(sys, "dont_write_bytecode", False):
            self.assertFalse(runtime.validate_scored_rewards(task, []))
        self.assertEqual(runtime.tree_hash(task), before)
        self.assertFalse(any(task.rglob("__pycache__")))


if __name__ == "__main__":
    unittest.main(verbosity=2)
