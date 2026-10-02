#!/usr/bin/env python3
"""Durable, shared eight-slot queue for the isolated RL01 VPS runtime."""
from __future__ import annotations

import concurrent.futures
import fcntl
import hashlib
import json
import os
import signal
import sqlite3
import subprocess
import threading
import time
from contextlib import contextmanager
from pathlib import Path

import vps_harbor as runtime
from vps_request_proxy import DEFAULT_CONCURRENCY

ACTIVE = ("RUNNING", "ORPHANED")
TERMINAL = ("SUCCEEDED", "FAILED", "BLOCKED", "INTERRUPTED")
WORKER_SERVICE = "rl01-harbor-dispatcher.service"


@contextmanager
def file_lock(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        yield


def atomic_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = path.with_name(path.name + "." + str(threading.get_ident()) + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(path)


def run_manifest(run_dir: Path) -> dict:
    run_dir = run_dir.resolve(strict=True)
    if not run_dir.is_relative_to((runtime.PREFIX / "runs").resolve()):
        raise ValueError("Run directory must belong to this runtime")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    runtime.verify_judge_runtime(run_dir, manifest.get('judge_execution', {}))
    task = Path(manifest["task"]).resolve(strict=True)
    if runtime.tree_hash(task) != manifest["task_digest"]:
        raise ValueError("Frozen task changed")
    if manifest.get("runtime_policy_digest") and hashlib.sha256(
            (run_dir / "runtime-compose.yaml").read_bytes()).hexdigest() != manifest["runtime_policy_digest"]:
        raise ValueError("Frozen runtime policy changed")
    return manifest


class Queue:
    def __init__(self, prefix: Path | None = None):
        self.prefix = prefix or runtime.PREFIX
        self.state = self.prefix / "state"
        self.state.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = self.state / "queue.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS runs (
                    run_dir TEXT PRIMARY KEY, task_id TEXT NOT NULL,
                    cap INTEGER NOT NULL, last_claimed REAL NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS units (
                    id TEXT PRIMARY KEY, run_dir TEXT NOT NULL,
                    kind TEXT NOT NULL, model TEXT, payload TEXT NOT NULL,
                    dependency TEXT, state TEXT NOT NULL DEFAULT 'QUEUED',
                    created REAL NOT NULL, started REAL, ended REAL,
                    child_pid INTEGER, child_start TEXT, result TEXT
                );
                CREATE INDEX IF NOT EXISTS units_state ON units(state, run_dir);
            """)
            db.execute('BEGIN IMMEDIATE')
            columns = {r['name'] for r in db.execute('PRAGMA table_info(units)')}
            for name, field_type in (('owner_pid', 'INTEGER'), ('owner_start', 'TEXT')):
                if name not in columns:
                    db.execute(f'ALTER TABLE units ADD COLUMN {name} {field_type}')
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        try:
            with db:
                yield db
        finally:
            db.close()

    def add(self, run_dir: Path, task_id: str, cap: int, units: list[dict]):
        if cap not in (2, 3, 4):
            raise ValueError("Per-task concurrency must be 2, 3 or 4")
        identifiers = []
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("INSERT OR IGNORE INTO runs(run_dir,task_id,cap) VALUES(?,?,?)",
                       (str(run_dir), task_id, cap))
            for unit in units:
                key = unit["key"]
                identifier = hashlib.sha256((str(run_dir) + ":" + key).encode()).hexdigest()[:24]
                identifiers.append(identifier)
                existing = db.execute("SELECT payload FROM units WHERE id=?", (identifier,)).fetchone()
                if existing and json.loads(existing["payload"]) != unit:
                    raise ValueError("Queued unit identity already exists with different frozen inputs")
                dependency = unit.get("dependency")
                if dependency:
                    dependency = hashlib.sha256((str(run_dir) + ":" + dependency).encode()).hexdigest()[:24]
                state = "QUEUED"
                if dependency:
                    parent = db.execute("SELECT state,result FROM units WHERE id=?", (dependency,)).fetchone()
                    if parent and (parent["state"] in ("FAILED", "BLOCKED", "INTERRUPTED") or
                            (parent["state"] == "SUCCEEDED" and not json.loads(parent["result"] or "{}").get("golden_valid"))):
                        state = "BLOCKED"
                db.execute("""INSERT OR IGNORE INTO units
                    (id,run_dir,kind,model,payload,dependency,created,state) VALUES(?,?,?,?,?,?,?,?)""",
                    (identifier, str(run_dir), unit["kind"], unit.get("model"),
                     json.dumps(unit), dependency, time.time(), state))
        return identifiers

    def rows(self, run_dir: Path | None = None, active_only=False):
        conditions = []
        if run_dir:
            conditions.append("run_dir=?")
        if active_only:
            conditions.append("state IN ('RUNNING','ORPHANED')")
        with self.connect() as db:
            rows = db.execute("SELECT * FROM units" +
                              (" WHERE " + " AND ".join(conditions) if conditions else "") + " ORDER BY created,rowid",
                              (str(run_dir),) if run_dir else ()).fetchall()
        return [dict(row) for row in rows]

    def claim(self, capacity=DEFAULT_CONCURRENCY):
        capacity = min(DEFAULT_CONCURRENCY, max(0, capacity))
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT COUNT(*) FROM units WHERE state IN ('RUNNING','ORPHANED')").fetchone()[0]
            if active >= capacity:
                return None
            row = db.execute("""
                SELECT u.* FROM units u JOIN runs r USING(run_dir)
                WHERE u.state='QUEUED'
                  AND (SELECT COUNT(*) FROM units a WHERE a.run_dir=u.run_dir
                       AND a.state IN ('RUNNING','ORPHANED')) < r.cap
                  AND (u.dependency IS NULL OR EXISTS (
                       SELECT 1 FROM units d WHERE d.id=u.dependency
                       AND d.state='SUCCEEDED' AND json_extract(d.result,'$.golden_valid')=1))
                ORDER BY (SELECT COUNT(*) FROM units a WHERE a.run_dir=u.run_dir
                          AND a.state IN ('RUNNING','ORPHANED')),
                         CASE WHEN r.last_claimed=0 THEN 1 ELSE 0 END,
                         r.last_claimed, u.created, u.rowid
                LIMIT 1
            """).fetchone()
            if row is None:
                return None
            now = time.time()
            owner = os.getpid()
            stamp = process_start(owner)
            db.execute("UPDATE units SET state='RUNNING',started=?,owner_pid=?,owner_start=? WHERE id=?",
                       (now, owner, stamp, row["id"]))
            db.execute("UPDATE runs SET last_claimed=? WHERE run_dir=?", (now, row["run_dir"]))
            result = dict(row)
            result.update(state="RUNNING", started=now, owner_pid=owner, owner_start=stamp)
            return result

    def child(self, identifier, pid):
        with self.connect() as db:
            db.execute("UPDATE units SET child_pid=?,child_start=? WHERE id=?",
                       (pid, process_start(pid), identifier))

    def finish(self, identifier, success: bool, result: dict):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("UPDATE units SET state=?,ended=?,result=? WHERE id=?",
                       ("SUCCEEDED" if success else "FAILED", time.time(), json.dumps(result), identifier))
            if not success or result.get("golden_valid") is False:
                db.execute("UPDATE units SET state='BLOCKED',ended=?,result=? WHERE dependency=? AND state='QUEUED'",
                           (time.time(), json.dumps({"reason": "GOLDEN_GATE_NOT_PASSED"}), identifier))

    def recover(self):
        # Never rerun generation after a controller crash. Preserve the old job.
        with self.connect() as db:
            for row in db.execute("SELECT * FROM units WHERE state IN ('RUNNING','ORPHANED')").fetchall():
                # A draining controller keeps its proxies and trials alive.
                # Its active claims remain reserved through a live handoff.
                if row['state'] == 'RUNNING' and process_alive(row['owner_pid'], row['owner_start']):
                    continue
                alive = row["child_pid"] and process_alive(row["child_pid"], row["child_start"])
                state = "ORPHANED" if alive else "INTERRUPTED"
                db.execute("UPDATE units SET state=?,result=? WHERE id=?",
                           (state, json.dumps({"reason": "WORKER_RESTART_REQUIRES_REVIEW"}), row["id"]))
                if not alive:
                    db.execute("UPDATE units SET state='BLOCKED',result=? WHERE dependency=? AND state='QUEUED'",
                               (json.dumps({"reason": "DEPENDENCY_INTERRUPTED"}), row["id"]))

    def reap_orphans(self):
        with self.connect() as db:
            for row in db.execute("SELECT * FROM units WHERE state='ORPHANED'").fetchall():
                if not process_alive(row["child_pid"], row["child_start"]):
                    db.execute("UPDATE units SET state='INTERRUPTED',ended=? WHERE id=?", (time.time(), row["id"]))
                    db.execute("UPDATE units SET state='BLOCKED',result=? WHERE dependency=? AND state='QUEUED'",
                               (json.dumps({"reason": "DEPENDENCY_INTERRUPTED"}), row["id"]))


def process_start(pid):
    try:
        return Path("/proc", str(pid), "stat").read_text().rsplit(")", 1)[1].split()[19]
    except OSError:
        return None


def process_alive(pid, start):
    return start is not None and process_start(pid) == start


def capacity_snapshot(queue: Queue) -> dict:
    host = runtime.host_status()
    owned = set()
    for run_dir in {row["run_dir"] for row in queue.rows(active_only=True)}:
        owned.update(p.name.lower() for p in (Path(run_dir) / "jobs").glob("*/*") if p.is_dir())
        owned.update(p.name.lower() for p in Path(run_dir).glob("regrade-*/trials/*") if p.is_dir())
    try:
        lines = subprocess.check_output(
            ["docker", "ps", "--filter", "label=com.docker.compose.service=main",
             "--format", '{{.Label "com.docker.compose.project"}}'], timeout=10).decode().splitlines()
        external = sorted({p for p in lines if p and ("__env" in p or "__verifier" in p) and
                           not any(p.lower().startswith(name + "__") for name in owned)})
    except (subprocess.SubprocessError, OSError):
        return {**host, "capacity": 0, "waiting_reason": "CONTAINER_INVENTORY_UNAVAILABLE"}
    # The global cap covers the new managed queue. Existing unscheduled
    # sessions are observed through real resource pressure, not container count.
    capacity = DEFAULT_CONCURRENCY
    reason = None
    if host["memory_available_mb"] < 1536:
        capacity, reason = 0, "MEMORY_AVAILABLE_BELOW_1536_MB"
    elif host["free_disk_gb"] < 15:
        capacity, reason = 0, "FREE_DISK_BELOW_15_GB"
    return {**host, "capacity": capacity, "global_slots": DEFAULT_CONCURRENCY,
            "external_trial_projects": external, "waiting_reason": reason}


def refresh_run(queue: Queue, run_dir: Path):
    with file_lock(run_dir / ".manifest.lock"):
        manifest = json.loads((run_dir / "manifest.json").read_text())
        rows = queue.rows(run_dir)
        preliminary = [r for r in rows if r["kind"] in ("golden", "candidate")]
        results = {r["id"]: json.loads(r["result"] or "{}") for r in rows}
        manifest["queue_units"] = [{"id": r["id"], "kind": r["kind"], "model": r["model"], "state": r["state"]} for r in rows]
        if preliminary:
            manifest["trial_index"] = [
                {"unit": r["id"], "kind": r["kind"], "model": r["model"], "trial": trial}
                for r in preliminary for trial in results[r["id"]].get("trials", [])
            ]
        if any(r["state"] in ACTIVE for r in rows):
            manifest["status"] = "RUNNING_QUEUED_UNITS"
        elif any(r["state"] == "QUEUED" for r in rows):
            manifest["status"] = "QUEUED"
        elif any(r["state"] != "SUCCEEDED" for r in rows):
            manifest["status"] = "QUEUE_STAGE_INCOMPLETE"
        elif rows:
            grades = [r for r in rows if r["kind"].startswith("regrade")]
            if grades:
                manifest["status"] = "SCORES_READY_REQUIRES_REVIEW"
                manifest["grade_receipts"] = [results[r["id"]] for r in grades]
            else:
                golden = next((r for r in preliminary if r["kind"] == "golden"), None)
                valid = bool(golden and results[golden["id"]].get("golden_valid"))
                manifest["golden_valid"] = valid
                if valid:
                    manifest["golden_verifier_task_digest"] = manifest["task_digest"]
                manifest["status"] = "CANDIDATES_AWAITING_REGRADE" if valid else "GOLDEN_NOT_VALIDATED"
        atomic_json(run_dir / "manifest.json", manifest)


def execute_unit(queue: Queue, unit: dict) -> dict:
    run_dir = Path(unit["run_dir"])
    payload = json.loads(unit["payload"])
    manifest = run_manifest(run_dir)
    work = run_dir / "queue-units" / unit["id"]
    work.mkdir(parents=True, exist_ok=True, mode=0o700)
    if unit["kind"].startswith("regrade"):
        if runtime.tree_hash(Path(payload["source"]) / "artifacts") != payload["artifact_digest"]:
            raise ValueError("Saved candidate artifacts changed after queuing")
        receipt = runtime.execute_regrade(Path(payload["source"]), Path(payload["task"]), run_dir,
                                          unit["kind"] == "regrade_golden")
        valid = runtime.validate_scored_rewards(
            Path(payload["task"]), (Path(receipt["output"]) / "trials").glob("*/verifier/reward.json"))
        if receipt["exit_code"] or not valid:
            raise ValueError("Regrade lacks a valid complete reward; inspect its private receipt")
        return receipt
    # Warm jobs must not wait behind another task's dependency installation.
    with (queue.state / "build.lock").open("a") as build:
        while True:
            current = run_manifest(run_dir)
            if current.get("cache_image_tag"):
                runtime.cache_image(run_dir)
                break
            try:
                fcntl.flock(build, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                time.sleep(0.2)
                continue
            runtime.cache_image(run_dir)
            break
    manifest = run_manifest(run_dir)
    env = runtime.base_environment()
    candidate_stage = unit["kind"] == "candidate"
    candidate_settings = run_dir / "candidate-settings.json"
    server, endpoint = runtime.start_proxy(
        work, env, manifest["task_digest"], manifest["concurrency"],
        effort="low" if candidate_stage else None,
        max_attempts=11 if candidate_stage else 1,
        settings_path=candidate_settings if candidate_stage and
        candidate_settings.is_file() else None)
    try:
        options = runtime.plans(Path(manifest["task"]), run_dir, manifest["concurrency"], endpoint)
        if unit["kind"] == "golden":
            config = options["golden"]
        else:
            config = options["candidates"]
            config["agents"] = [agent for agent in config["agents"] if agent["model_name"] == unit["model"]]
            config["job_name"] = "candidate-" + str(runtime.MODELS.index(unit["model"]))
        config["n_concurrent_trials"] = 1
        path = work / "job.json"
        atomic_json(path, config)
        with (work / "harbor.log").open("a") as log:
            child = subprocess.Popen([str(runtime.PREFIX / "bin/harbor"), "run", "-c", str(path), "--yes"],
                                     stdout=log, stderr=subprocess.STDOUT, env=env)
            queue.child(unit["id"], child.pid)
            code = child.wait()
        trials = sorted((run_dir / "jobs" / config["job_name"]).glob("*/result.json"))
        failures = []
        for result in trials:
            if json.loads(result.read_text()).get("exception_info"):
                failures.append(str(result))
            exit_code = result.parent / "agent/exit-code.txt"
            if exit_code.is_file() and exit_code.read_text().strip() != "0":
                failures.append(str(exit_code))
            artifact_manifest = result.parent / "artifacts/manifest.json"
            if artifact_manifest.exists() and any(item.get("status") == "failed"
                    for item in json.loads(artifact_manifest.read_text())):
                failures.append(str(artifact_manifest))
        if code or len(trials) != 1 or failures:
            raise ValueError("Harbor trial or artifact collection incomplete; inspect queue unit log")
        receipt = {"exit_code": code, "trials": [str(p.parent) for p in trials]}
        if unit["kind"] == "golden":
            receipt["golden_valid"] = runtime.golden_valid(run_dir)
        atomic_json(work / "receipt.json", receipt)
        return receipt
    finally:
        server.shutdown()
        server.server_close()


def run_claimed(queue: Queue, unit: dict):
    try:
        # Keep slow manifest locks and filesystem work out of the heartbeat
        # loop, so another task's build cannot block global admission.
        refresh_run(queue, Path(unit["run_dir"]))
        result = execute_unit(queue, unit)
        success = True
    except Exception as error:
        result = {"error_type": type(error).__name__, "reason": str(error)}
        success = False
    queue.finish(unit["id"], success, result)
    refresh_run(queue, Path(unit["run_dir"]))


def ensure_worker():
    # Only this new service is started. Other sessions and services are untouched.
    result = subprocess.run(["systemctl", "start", WORKER_SERVICE], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Queue saved, but worker could not start; inspect " + WORKER_SERVICE)


def submit_runs(run_dirs: list[Path]) -> dict:
    queue = Queue()
    prepared = [(p.resolve(strict=True), run_manifest(p)) for p in run_dirs]
    for path, manifest in prepared:
        if manifest["status"] != "PREPARED_NOT_RUN" and not queue.rows(path):
            raise ValueError("Unregistered historical run must be reviewed, not automatically rerun")
    for path, manifest in prepared:
        queue.add(path, Path(manifest["task"]).name, manifest["concurrency"],
                  [{"key": "golden", "kind": "golden"}] +
                  [{"key": "candidate:" + model, "kind": "candidate", "model": model}
                   for model in runtime.MODELS])
        refresh_run(queue, path)
    ensure_worker()
    return {"submitted_runs": [str(p) for p, _ in prepared], "global_slots": DEFAULT_CONCURRENCY,
            "status": "QUEUED_ASYNCHRONOUSLY", "inspect_with": "rl01 status"}


def submit_regrade(source: Path, task: Path, run_dir: Path, golden=False, dependency=None, start_worker=True):
    queue = Queue()
    run_dir = run_dir.resolve(strict=True)
    manifest = run_manifest(run_dir)
    task, source = task.resolve(strict=True), source.resolve(strict=True)
    if runtime.tree_hash(task, True) != manifest["agent_visible_digest"]:
        raise ValueError("Agent-visible task changed; generate candidates again")
    source_config = json.loads((source / "config.json").read_text())
    original_task = Path(source_config["task"]["path"]).resolve(strict=True)
    if runtime.tree_hash(original_task, True) != manifest["agent_visible_digest"]:
        raise ValueError("Source trial belongs to a different Agent-visible task")
    if golden and runtime.source_agent_name(source_config) != "oracle":
        raise ValueError("Golden regrade requires an Oracle source")
    if not (source / "artifacts/manifest.json").is_file():
        raise ValueError("Source trial lacks its artifact manifest")
    artifact_digest = runtime.tree_hash(source / "artifacts")
    if not golden and dependency is None:
        if not manifest.get("golden_valid") or runtime.tree_hash(task) != manifest.get("golden_verifier_task_digest"):
            raise ValueError("First validate Golden on this verifier version")
    key = ("regrade-golden:" if golden else "regrade:") + str(source) + ":" + runtime.tree_hash(task)
    units = [{"key": key, "kind": "regrade_golden" if golden else "regrade_candidate",
              "source": str(source), "task": str(task), "dependency": dependency,
              "artifact_digest": artifact_digest}]
    identifiers = queue.add(run_dir, Path(manifest["task"]).name, manifest["concurrency"], units)
    refresh_run(queue, run_dir)
    if start_worker:
        ensure_worker()
    return {"units": identifiers, "key": key, "status": "QUEUED_ASYNCHRONOUSLY"}


def submit_grades(run_dirs: list[Path]) -> dict:
    queue = Queue()
    for path in run_dirs:
        manifest = run_manifest(path)
        if manifest["status"] != "CANDIDATES_AWAITING_REGRADE" and not any(
                r["kind"].startswith("regrade") for r in queue.rows(path.resolve(strict=True))):
            raise ValueError("All selected tasks need a valid Golden and three saved candidates first")
    submitted = []
    for path in run_dirs:
        path = path.resolve(strict=True)
        manifest = run_manifest(path)
        with file_lock(path / ".manifest.lock"):
            receipt_path = path / "queue-verifier.json"
            if receipt_path.exists():
                adapter = json.loads(receipt_path.read_text())
            else:
                adapter = runtime.prepare_verifier(path, None)
                atomic_json(receipt_path, adapter)
        task = Path(adapter["verifier_task"])
        golden = next(entry for entry in manifest["trial_index"] if entry["kind"] == "golden")
        result = submit_regrade(Path(golden["trial"]), task, path, True, start_worker=False)
        submitted.extend(result["units"])
        for entry in manifest["trial_index"]:
            if entry["kind"] == "candidate":
                result_candidate = submit_regrade(Path(entry["trial"]), task, path,
                                                  dependency=result["key"], start_worker=False)
                submitted.extend(result_candidate["units"])
    ensure_worker()
    return {"queued_regrades": submitted, "global_slots": DEFAULT_CONCURRENCY,
            "status": "GOLDEN_REGRADE_THEN_CANDIDATE_REGRADE"}


def batch_runs(batch_dir: Path):
    batch_dir = batch_dir.resolve(strict=True)
    if not batch_dir.is_relative_to((runtime.PREFIX / "batches").resolve()):
        raise ValueError("Batch directory must belong to this runtime")
    return [Path(p) for p in json.loads((batch_dir / "manifest.json").read_text())["runs"]]


def queue_status(run_dir: Path | None = None):
    queue = Queue()
    if run_dir:
        run_dir = run_dir.resolve(strict=True)
    rows = queue.rows(run_dir)
    worker_path = queue.state / "worker.json"
    controller = json.loads(worker_path.read_text()) if worker_path.exists() else {}
    return {"global_slots": DEFAULT_CONCURRENCY,
            "counts": {state: sum(r["state"] == state for r in rows)
                       for state in ("QUEUED", *ACTIVE, *TERMINAL)},
            "worker": {**controller, "alive": process_alive(controller.get("pid", 0), controller.get("start"))},
            "host": capacity_snapshot(queue),
            "units_total": len(rows),
            "units": [{key: r[key] for key in ("id", "run_dir", "kind", "model", "state")}
                      for r in (rows if run_dir else rows[:50])]}


def worker():
    queue = Queue()
    # The older controller retains worker.lock while its threads drain. Only
    # the new controller admits work, guarded by this independent mutex.
    handle = (queue.state / "dispatcher.lock").open("a")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return
    queue.recover()
    runtime.cleanup_stale_proxy_firewall()
    stopping = threading.Event()
    signal.signal(signal.SIGTERM, lambda *_: stopping.set())
    signal.signal(signal.SIGINT, lambda *_: stopping.set())
    futures = set()
    with concurrent.futures.ThreadPoolExecutor(max_workers=DEFAULT_CONCURRENCY) as pool:
        while not stopping.is_set():
            futures = {f for f in futures if not f.done()}
            queue.reap_orphans()
            snapshot = capacity_snapshot(queue)
            while len(futures) < DEFAULT_CONCURRENCY and not stopping.is_set():
                unit = queue.claim(snapshot["capacity"])
                if not unit:
                    break
                futures.add(pool.submit(run_claimed, queue, unit))
            atomic_json(queue.state / "worker.json", {"pid": os.getpid(), "start": process_start(os.getpid()),
                        "heartbeat": time.time(), "running": sum(row['state'] == 'RUNNING' for row in queue.rows(active_only=True)),
                        "local_running": len(futures), "capacity": snapshot["capacity"],
                        "global_slots": DEFAULT_CONCURRENCY, "service": WORKER_SERVICE,
                        "waiting_reason": snapshot.get("waiting_reason")})
            stopping.wait(1)
    handle.close()


if __name__ == "__main__":
    worker()
