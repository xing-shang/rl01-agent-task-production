#!/usr/bin/env python3
"""Prepare and run isolated RL01 Harbor jobs. Run on the designated VPS."""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import secrets
import shlex
import shutil
import subprocess
import sys
import threading
import time
import tomllib
import re
from urllib.parse import urlsplit
from pathlib import Path

from vps_request_proxy import DEFAULT_CONCURRENCY, ProxyConfig, make_server
from check_pro_golden_review import validate as validate_pro_review

PREFIX = Path(os.environ.get("RL01_RUNTIME_PREFIX", "/opt/rl01-harbor"))
MODELS = ["gpt-5.6-sol", "claude-opus-4-8", "qwen3.8-max0902"]
DEFAULT_MEMORY_MB = 2048
DEFAULT_CRITERION_WORKERS = 2
DEFAULT_TASK_CONCURRENCY = 4
REGRADE_PROXY_CONCURRENCY = 2
JUDGE_ASSETS = ('vps_parallel_rewardkit.py', 'vps-judge-compose.yaml')


def freeze_judge_runtime(run_dir: Path, workers: int) -> dict:
    if workers not in (1, 2):
        raise ValueError('criterion_workers must be one or two for the 2 GiB default')
    destination = run_dir / 'judge-runtime'
    destination.mkdir(mode=0o700)
    hashes = {}
    for name in JUDGE_ASSETS:
        shutil.copy2(Path(__file__).parents[1] / 'assets' / name, destination / name)
        hashes[name] = hashlib.sha256((destination / name).read_bytes()).hexdigest()
    return {'criterion_workers': workers, 'runtime_assets': hashes,
            'authorization': 'User confirmed client approval offline on 2026-10-01'}


def verify_judge_runtime(run_dir: Path, policy: dict):
    for name, expected in policy.get('runtime_assets', {}).items():
        if name not in JUDGE_ASSETS or hashlib.sha256((run_dir / 'judge-runtime' / name).read_bytes()).hexdigest() != expected:
            raise ValueError('Frozen Judge runtime changed')


def tree_hash(path: Path, visible_only=False) -> str:
    selected = [path / "instruction.md", path / "environment"] if visible_only else [path]
    files = []
    for node in selected:
        if node.is_file():
            files.append(node)
        elif node.is_dir():
            files.extend(x for x in node.rglob("*") if x.is_file())
    digest = hashlib.sha256()
    if visible_only:
        task_config = tomllib.loads((path / "task.toml").read_text())
        # Verifier adapters can change without changing the candidate's task,
        # but agent limits, tools/network/resources and collection paths cannot.
        digest.update(json.dumps({key: task_config.get(key) for key in
                                  ["agent", "environment", "artifacts", "steps"]},
                                 sort_keys=True, ensure_ascii=False, default=str).encode())
    for file in sorted(files):
        if file.is_symlink():
            raise ValueError("symlinks are not supported: " + str(file))
        digest.update(file.relative_to(path).as_posix().encode() + b"\0")
        with file.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
        digest.update(str(file.stat().st_mode & 0o777).encode() + b"\0")
    return digest.hexdigest()


def host_status() -> dict:
    jobs = []
    for item in Path("/proc").iterdir():
        if not item.name.isdigit():
            continue
        try:
            if (item / "comm").read_text().strip() == "harbor":
                jobs.append(int(item.name))
        except OSError:
            pass
    available = next(int(x.split()[1]) for x in Path("/proc/meminfo").read_text().splitlines()
                     if x.startswith("MemAvailable:")) / 1024
    return {"cpu_count": os.cpu_count(), "load": os.getloadavg(),
            "memory_available_mb": round(available), "foreign_harbor_pids": jobs,
            "free_disk_gb": round(shutil.disk_usage(PREFIX).free / 2 ** 30, 2)}


def bridge_ip() -> str:
    data = json.loads(subprocess.check_output(["docker", "network", "inspect", "bridge"]))
    return data[0]["IPAM"]["Config"][0]["Gateway"]


def base_environment() -> dict:
    # Settings only apply to child processes. No shared shell profile is edited.
    return {**os.environ, "PATH": str(PREFIX / "bin") + ":" + os.environ["PATH"],
            "PIP_CACHE_DIR": str(PREFIX / "cache/pip"),
            "npm_config_cache": str(PREFIX / "cache/npm"), "DOCKER_BUILDKIT": "1",
            "CLAUDE_CONFIG_DIR": str(PREFIX / "claude-config"),
            "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
            "API_FORCE_IDLE_TIMEOUT": "0",
            "DISABLE_PROMPT_CACHING": "0",
            "CLAUDE_CODE_MAX_RETRIES": "0"}


def plans(task: Path, run_dir: Path, concurrency: int, endpoint: str) -> dict:
    agent_env = {"ANTHROPIC_BASE_URL": endpoint,
                 "ANTHROPIC_AUTH_TOKEN": "${RL01_PROXY_TOKEN}",
                 "ANTHROPIC_API_KEY": "${RL01_PROXY_TOKEN}",
                 "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                 "CLAUDE_CODE_EFFORT_LEVEL": "low", "DISABLE_PROMPT_CACHING": "0",
                 "CLAUDE_CODE_MAX_RETRIES": "0", "API_FORCE_IDLE_TIMEOUT": "0",
                 "DISABLE_PROMPT_CACHING_HAIKU": "0", "DISABLE_PROMPT_CACHING_SONNET": "0",
                 "DISABLE_PROMPT_CACHING_OPUS": "0", "API_TIMEOUT_MS": "14400000"}
    verifier_env = {"ANTHROPIC_BASE_URL": endpoint,
                    "ANTHROPIC_AUTH_TOKEN": "${RL01_PROXY_TOKEN}",
                    "ANTHROPIC_API_KEY": "${RL01_PROXY_TOKEN}",
                    "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
                    "DISABLE_PROMPT_CACHING": "0", "CLAUDE_CODE_MAX_RETRIES": "10",
                    "API_FORCE_IDLE_TIMEOUT": "0",
                    "DISABLE_PROMPT_CACHING_HAIKU": "0", "DISABLE_PROMPT_CACHING_SONNET": "0",
                    "DISABLE_PROMPT_CACHING_OPUS": "0", "API_TIMEOUT_MS": "14400000",
                    "JUDGE_BASE_URL": endpoint,
                    "JUDGE_API_KEY": "${RL01_PROXY_TOKEN}", "JUDGE_MODEL": "qwen3.7-plus",
                    "JUDGE_API_PROTOCOL": "anthropic", "JUDGE_PROVIDER": "anthropic"}
    common = {"jobs_dir": str(run_dir / "jobs"), "n_attempts": 1,
              "retry": {"max_retries": 0}, "tasks": [{"path": str(task)}],
              "environment": {"type": "docker", "force_build": False, "delete": True,
                              "extra_allowed_hosts": [urlsplit(endpoint).hostname],
                              "extra_docker_compose": [str(run_dir / "runtime-compose.yaml"
                                  if (run_dir / "runtime-compose.yaml").exists() else
                                  Path(__file__).parents[1] / "assets/vps-build-network.yaml")]},
              "quiet": True}
    candidate = {**common, "job_name": "candidates", "n_concurrent_trials": concurrency - 1,
                 "verifier": {"disable": True},
                 "agents": [{"name": "claude-code", "model_name": model,
                             "kwargs": {"version": "2.1.114", "reasoning_effort": "low"},
                             "env": agent_env} for model in MODELS]}
    golden = {**common, "job_name": "golden", "n_concurrent_trials": 1,
              "agents": [{"name": "oracle"}], "verifier": {"env": verifier_env}}
    return {"golden": golden, "candidates": candidate}


def freeze_memory_limits(task: Path, memory_mb: int) -> dict:
    """Apply the selected resource policy before freezing candidate evidence."""
    import toml
    config = tomllib.loads((task / "task.toml").read_text())
    environments = [("environment", config["environment"])]
    verifier_env = config.get("verifier", {}).get("environment")
    if verifier_env is not None:
        environments.append(("verifier.environment", verifier_env))
    for index, step in enumerate(config.get("steps", [])):
        verifier_env = step.get("verifier", {}).get("environment")
        if verifier_env is not None:
            environments.append((f"steps[{index}].verifier.environment", verifier_env))
    changes = {}
    for name, environment in environments:
        previous = environment.get("memory_mb")
        if previous != memory_mb:
            changes[name + ".memory_mb"] = {"source": previous, "runtime": memory_mb}
            environment["memory_mb"] = memory_mb
    if changes:
        (task / "task.toml").write_text(toml.dumps(config))
    return changes


def prepare(task: Path, concurrency: int, memory_mb: int = DEFAULT_MEMORY_MB,
            criterion_workers: int = DEFAULT_CRITERION_WORKERS,
            pro_review: Path | None = None, skip_formal_golden: bool = False) -> Path:
    if type(skip_formal_golden) is not bool or (skip_formal_golden and pro_review is None):
        raise ValueError("Skipping formal Golden requires an explicit flag and a complete Pro review")
    if type(memory_mb) is not int or memory_mb <= 0:
        raise ValueError("memory_mb must be a positive integer in MiB")
    task = task.resolve(strict=True)
    # The maintained static package checker runs before any billable inference.
    checker = Path(__file__).with_name("check_rl01_package.py")
    result = subprocess.run([sys.executable, str(checker), str(task)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Static preflight failed; inspect checker output:\n" + result.stdout + result.stderr)
    author_review = validate_pro_review(task, pro_review) if pro_review is not None else None
    run_dir = PREFIX / "runs" / (time.strftime("%Y%m%dT%H%M%S") + "-" + secrets.token_hex(4))
    run_dir.mkdir(parents=True, mode=0o700)
    judge_policy = freeze_judge_runtime(run_dir, criterion_workers)
    frozen = run_dir / "frozen" / task.name
    shutil.copytree(task, frozen)
    source_digest = tree_hash(frozen)
    shutil.copy2(frozen / "task.toml", run_dir / "source-task.toml")
    changes = freeze_memory_limits(frozen, memory_mb)
    source_preflight = result.stdout
    result = subprocess.run([sys.executable, str(checker), str(frozen)], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Runtime resource preflight failed; inspect checker output:\n" + result.stdout + result.stderr)
    manifest = {"source": str(task), "task": str(frozen), "task_digest": tree_hash(frozen),
                "source_task_digest": source_digest,
                "agent_visible_digest": tree_hash(frozen, True), "concurrency": concurrency,
                "status": "PREPARED_NOT_RUN", "host_snapshot": host_status(),
                "resource_policy": {"memory_mb": memory_mb, "source_task_config": "source-task.toml",
                                    "source_task_config_sha256": hashlib.sha256(
                                        (run_dir / "source-task.toml").read_bytes()).hexdigest(),
                                    "adjustments": changes},
                "effort_policy": {"candidate": "low", "golden": "provider_default",
                                   "judge": "provider_default"},
                "judge": "qwen3.7-plus", "models": MODELS,
                "formal_golden_required": not skip_formal_golden}
    manifest['judge_execution'] = judge_policy
    if author_review is not None:
        review_copy = run_dir / "pro-golden-review.json"
        shutil.copy2(pro_review, review_copy)
        review_copy.chmod(0o600)
        if hashlib.sha256(review_copy.read_bytes()).hexdigest() != author_review["review_sha256"]:
            raise ValueError("Pro review changed while preparing the frozen run")
        manifest.update(golden_review_mode="pro_self_review" if skip_formal_golden else "formal_golden", golden_valid=False,
                        local_golden_scoring_executed=False,
                        pro_golden_review={**author_review, "path": str(review_copy)})
        pro_review_accepted(manifest, frozen)
    policy = run_dir / "runtime-compose.yaml"
    shutil.copy2(Path(__file__).parents[1] / "assets/vps-build-network.yaml", policy)
    manifest["runtime_policy_digest"] = hashlib.sha256(policy.read_bytes()).hexdigest()
    (run_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    (run_dir / "source-static-preflight.json").write_text(source_preflight)
    (run_dir / "static-preflight.json").write_text(result.stdout)
    for name, config in plans(frozen, run_dir, concurrency, "http://" + bridge_ip() + ":PORT").items():
        if skip_formal_golden and name == "golden":
            continue
        (run_dir / (name + ".json")).write_text(json.dumps(config, indent=2))
    return run_dir


def prepare_batch(paths: list[Path], concurrency: int, memory_mb: int = DEFAULT_MEMORY_MB,
                  criterion_workers: int = DEFAULT_CRITERION_WORKERS,
                  pro_review_dir: Path | None = None, skip_formal_golden: bool = False) -> dict:
    if type(skip_formal_golden) is not bool or (skip_formal_golden and pro_review_dir is None):
        raise ValueError("Skipping formal Golden requires an explicit flag and a complete Pro review directory")
    tasks = []
    for path in paths:
        path = path.resolve(strict=True)
        if (path / 'task.toml').is_file():
            tasks.append(path)
        else:
            tasks.extend(sorted(p.parent for p in path.glob('*/task.toml')))
    if not tasks:
        raise ValueError('No task directories found')
    if len(set(tasks)) != len(tasks) or len({p.name for p in tasks}) != len(tasks):
        raise ValueError('Each batch needs distinct task directories and task IDs')
    reviews = [pro_review_dir / (task.name + ".json") if pro_review_dir is not None else None
               for task in tasks]
    for task, review in zip(tasks, reviews):
        if review is not None:
            validate_pro_review(task, review)
    runs = [str(prepare(task, concurrency, memory_mb, criterion_workers, review, skip_formal_golden))
            for task, review in zip(tasks, reviews)]
    batch = PREFIX / 'batches' / (time.strftime('%Y%m%dT%H%M%S') + '-' + secrets.token_hex(4))
    batch.mkdir(parents=True, mode=0o700)
    result = {'batch_dir': str(batch), 'runs': runs, 'models_executed': False}
    (batch / 'manifest.json').write_text(json.dumps(result, indent=2))
    return result


def cache_image(run_dir: Path) -> dict:
    run_dir = run_dir.resolve(strict=True)
    manifest = json.loads((run_dir / "manifest.json").read_text())
    task = Path(manifest["task"])
    if tree_hash(task) != manifest["task_digest"]:
        raise ValueError("Frozen task changed")
    config = tomllib.loads((task / "task.toml").read_text())
    tag = config.get("environment", {}).get("docker_image")
    if not tag:
        if not (task / "environment/Dockerfile").exists():
            raise ValueError("This cache helper requires a Dockerfile task or an explicit docker_image")
        tag = "rl01-agent-runtime:" + manifest["task_digest"][:16]
        cached = subprocess.run(['docker', 'image', 'inspect', tag], capture_output=True).returncode == 0
        if not cached:
            with (run_dir / "cache-build.log").open("a") as log:
                result = subprocess.run(["docker", "build", "--network=host", "-t", tag,
                                         str(task / "environment")], stdout=log, stderr=subprocess.STDOUT)
            if result.returncode:
                raise ValueError("Cache build failed; inspect cache-build.log. No model was started.")
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", tag]))[0]
    if manifest.get("cache_image_tag") == tag and manifest.get("cache_image_id") not in (None, image["Id"]):
        raise ValueError("Preserved Agent image changed; inspect the runtime cache")
    receipt = {"cache_image_tag": tag, "cache_image_id": image["Id"],
               "cache_source_task_digest": manifest["task_digest"]}
    from vps_queue import atomic_json, file_lock
    with file_lock(run_dir / ".manifest.lock"):
        manifest = json.loads((run_dir / "manifest.json").read_text())
        manifest.update(receipt)
        atomic_json(run_dir / "manifest.json", manifest)
    return receipt


def prepare_verifier(run_dir: Path, agent_image: str | None, task: Path | None = None) -> dict:
    import toml
    run_dir = run_dir.resolve(strict=True)
    if not run_dir.is_relative_to((PREFIX / "runs").resolve()):
        raise ValueError("run directory must be inside this runtime prefix")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    judge_policy = manifest.get('judge_execution', {'criterion_workers': 1})
    verify_judge_runtime(run_dir, judge_policy)
    workers = judge_policy['criterion_workers']
    task = (task or Path(manifest["task"])).resolve(strict=True)
    if tree_hash(task, True) != manifest["agent_visible_digest"]:
        raise ValueError("Agent-visible task changed; candidate generation must run again")
    agent_image = agent_image or manifest.get("cache_image_tag")
    if not agent_image:
        raise ValueError("No preserved image; build/cache the frozen Agent environment first")
    image = json.loads(subprocess.check_output(["docker", "image", "inspect", agent_image]))[0]
    if agent_image == manifest.get("cache_image_tag") and image["Id"] != manifest.get("cache_image_id"):
        raise ValueError("The preserved image tag changed")
    # Keep an immutable source image ID in the receipt and a private stable tag
    # for Docker FROM. A verifier image containing Golden is never used by Agent.
    tag = "rl01-agent-base:" + image["Id"].split(":")[-1][:16]
    subprocess.run(["docker", "image", "tag", image["Id"], tag], check=True)
    parent = run_dir / ("verifier-runtime-" + secrets.token_hex(4))
    verifier = parent / task.name
    shutil.copytree(task, verifier)
    config = toml.loads((verifier / "task.toml").read_text())
    config.setdefault("verifier", {})["environment_mode"] = "separate"
    config["verifier"].pop("environment", None)
    # Separate verifiers must build their own tests image even when the Agent
    # environment was supplied as a prebuilt image.
    if config.get('environment', {}).get('docker_image'):
        config['verifier']['environment'] = dict(config['environment'])
        config['verifier']['environment'].pop('docker_image')
    config['verifier'].setdefault('env', {})['RL01_CRITERION_WORKERS'] = str(workers)
    (verifier / "task.toml").write_text(toml.dumps(config))
    dockerfile = 'FROM ' + tag + '\n'
    if workers > 1:
        import yaml
        plugin = verifier / 'tests/.rl01-runtime'
        plugin.mkdir(mode=0o700)
        shutil.copy2(run_dir / 'judge-runtime/vps_parallel_rewardkit.py', plugin / 'parallel_rewardkit.py')
        compose_path = verifier / 'tests/docker-compose.yaml'
        compose = yaml.safe_load(compose_path.read_text()) if compose_path.exists() else {}
        overlay = yaml.safe_load((run_dir / 'judge-runtime/vps-judge-compose.yaml').read_text())
        main = compose.setdefault('services', {}).setdefault('main', {})
        if main.get('privileged'):
            raise ValueError('Parallel Judge does not support privileged task-authored services')
        for key, value in overlay['services']['main'].items():
            if key in ('cap_add', 'security_opt'):
                main[key] = list(dict.fromkeys(main.get(key, []) + value))
            elif key == 'build':
                build = main.get('build', {})
                if isinstance(build, str):
                    build = {'context': build}
                main[key] = {**build, **value}
            else:
                main[key] = value
        compose_path.write_text(yaml.safe_dump(compose, sort_keys=False))
        dockerfile += ('RUN command -v bwrap >/dev/null || '
                       '(if command -v apt-get >/dev/null; then apt-get update && '
                       'apt-get install -y --no-install-recommends bubblewrap && rm -rf /var/lib/apt/lists/*; '
                       'elif command -v apk >/dev/null; then apk add --no-cache bubblewrap; else exit 1; fi)\n')
    dockerfile += 'COPY . /tests\nRUN mkdir -p /app/output /logs/verifier /logs/artifacts\n'
    if workers > 1:
        dockerfile += ('RUN mkdir -p /opt/rl01-runtime && cp /tests/.rl01-runtime/parallel_rewardkit.py '
                       '/opt/rl01-runtime/parallel_rewardkit.py && '
                       "printf '#!/bin/sh\\nexec python3 /opt/rl01-runtime/parallel_rewardkit.py \"$@\"\\n' "
                       '> /usr/local/bin/rewardkit && chmod +x /usr/local/bin/rewardkit\n')
    (verifier / "tests/Dockerfile").write_text(dockerfile)
    if tree_hash(verifier, True) != manifest["agent_visible_digest"]:
        raise ValueError("Verifier adaptation altered Agent-visible content")
    author_review_accepted = pro_review_accepted(manifest, verifier)
    receipt = {"verifier_task": str(verifier), "source_task_digest": tree_hash(task),
               "verifier_task_digest": tree_hash(verifier), "agent_visible_digest": manifest["agent_visible_digest"],
               "agent_image_id": image["Id"], "status": "VERIFIER_READY_PRO_REVIEW_ACCEPTED"
               if author_review_accepted else "VERIFIER_READY_REQUIRES_GOLDEN_REGRADE"}
    receipt['judge_execution'] = judge_policy
    (parent / "receipt.json").write_text(json.dumps(receipt, indent=2))
    return receipt


def process_stamp(pid: int) -> str | None:
    try:
        return Path("/proc", str(pid), "stat").read_text().rsplit(")", 1)[1].split()[19]
    except OSError:
        return None


def install_proxy_firewall(bind: str, port: int) -> list[list[str]]:
    address = ipaddress.ip_address(bind)
    if address.is_loopback:
        return []
    if address.version != 4 or not address.is_private:
        raise ValueError("Runtime proxy must bind a private Docker IPv4 address")
    tag = f"rl01-private-proxy:{os.getpid()}:{process_stamp(os.getpid())}:{port}"
    rules = []
    try:
        for interface in ("docker0", "br-+"):
            rule = ["-i", interface, "-d", bind, "-p", "tcp", "--dport", str(port),
                    "-m", "comment", "--comment", tag, "-j", "ACCEPT"]
            result = subprocess.run(["iptables", "-w", "5", "-I", "INPUT", "1", *rule], capture_output=True)
            if result.returncode:
                raise ValueError("Cannot grant scoped Docker access to the runtime proxy")
            rules.append(rule)
        return rules
    except Exception:
        for rule in rules:
            subprocess.run(["iptables", "-w", "5", "-D", "INPUT", *rule], capture_output=True)
        raise


def cleanup_stale_proxy_firewall():
    result = subprocess.run(["iptables", "-w", "5", "-S", "INPUT"], capture_output=True, text=True)
    if result.returncode:
        raise ValueError("Cannot audit runtime proxy firewall rules")
    for line in result.stdout.splitlines():
        match = re.search(r"rl01-private-proxy:(\d+):(\d+):(\d+)", line)
        if match and process_stamp(int(match[1])) != match[2]:
            arguments = shlex.split(line)
            subprocess.run(["iptables", "-w", "5", "-D", *arguments[1:]], capture_output=True, check=True)


def start_proxy(run_dir: Path, env: dict, task_digest: str,
                concurrency: int = DEFAULT_CONCURRENCY, effort: str | None = "low",
                settings_path: Path | None = None, max_attempts: int = 11):
    secret_file = settings_path or (PREFIX / "claude-config/settings.json")
    if secret_file.stat().st_mode & 0o077:
        raise ValueError("settings.json must have mode 0600")
    secret = json.loads(secret_file.read_text())["env"]
    token = secrets.token_urlsafe(32)
    env["RL01_PROXY_TOKEN"] = token
    config = ProxyConfig(secret["ANTHROPIC_BASE_URL"], secret["ANTHROPIC_AUTH_TOKEN"], token,
                         run_dir / "private-request-audit.jsonl", task_digest=task_digest,
                         max_attempts=max_attempts,
                         max_in_flight=concurrency, shared_slot_dir=PREFIX / 'state/api-slots',
                         effort=effort)
    server = make_server(bridge_ip(), 0, config)
    try:
        firewall_rules = install_proxy_firewall(*server.server_address)
    except Exception:
        server.server_close()
        raise
    close = server.server_close
    def close_and_release():
        try:
            failed = []
            for rule in firewall_rules:
                if subprocess.run(["iptables", "-w", "5", "-D", "INPUT", *rule],
                                  capture_output=True).returncode:
                    failed.append(rule)
            if failed:
                (run_dir / "firewall-cleanup-failed.json").write_text(json.dumps(failed))
        finally:
            close()
    server.server_close = close_and_release
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://" + server.server_address[0] + ":" + str(server.server_address[1])


def validate_scored_rewards(task: Path, reward_paths, minimum=0.0) -> bool:
    expected = len(json.loads((task / "rubrics.json").read_text())["items"])
    # Loading with a file-backed importer can write __pycache__ into frozen
    # evidence. Execute the already checked template without creating a cache.
    script = task / "tests/finalize.py"
    namespace = {"__name__": "rl01_fixed_finalize", "__file__": str(script)}
    exec(compile(script.read_bytes(), str(script), "exec"), namespace)
    for path in reward_paths:
        value = json.loads(path.read_text())
        detail = path.with_name("reward-details.json")
        if not detail.exists():
            continue
        score, count, broken = namespace["pooled_score"](json.loads(detail.read_text()))
        if (value.get("verifier_error") == 0 and value.get("criteria_counted") == expected
                and count == expected and broken == 0 and score is not None
                and abs(round(score, 6) - value.get("reward", -1)) < 0.000001
                and value.get("reward", -1) >= minimum):
            return True
    return False


def validate_golden_rewards(task: Path, reward_paths) -> bool:
    return validate_scored_rewards(task, reward_paths, minimum=0.85)


def golden_valid(run_dir: Path) -> bool:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    return validate_golden_rewards(Path(manifest["task"]),
                                   (run_dir / "jobs/golden").glob("*/verifier/reward.json"))


def pro_review_accepted(manifest: dict, task: Path) -> bool:
    mode = manifest.get("golden_review_mode")
    if mode not in {"pro_self_review", "formal_golden"}:
        return False
    saved = manifest.get("pro_golden_review", {})
    if not saved.get("path"):
        if mode == "formal_golden":
            return False
        raise ValueError("Pro self-review mode needs its frozen author review")
    review = Path(saved["path"])
    receipt = validate_pro_review(task, review, review.parent / "source-task.toml")
    if any(receipt.get(key) != value for key, value in saved.items() if key != "path"):
        raise ValueError("Frozen Pro review receipt changed")
    return mode == "pro_self_review"


def candidate_grade_allowed(manifest: dict, task: Path) -> bool:
    if pro_review_accepted(manifest, task):
        return True
    return bool(manifest.get("golden_valid") and
                tree_hash(task) == manifest.get("golden_verifier_task_digest"))


def launch(run_dir: Path) -> dict:
    from vps_queue import submit_runs
    return submit_runs([run_dir])


def source_agent_name(config: dict) -> str:
    agent = config.get("agent", {})
    if "name" in agent:
        return agent["name"]
    # Harbor omits defaults from saved trial configs, including Oracle's agent.
    from harbor.models.trial.config import AgentConfig
    return AgentConfig.model_validate(agent).name


def execute_regrade(source: Path, task: Path, run_dir: Path, is_golden=False) -> dict:
    # Never re-run candidate generation just because its verifier failed.
    from harbor.trial.regrade import check_task_regradable
    reason = check_task_regradable(task)
    if reason:
        raise ValueError(reason + " Use an isolated separate-verifier runtime copy; see vps-harbor.md.")
    manifest = json.loads((run_dir / "manifest.json").read_text())
    if tree_hash(task, True) != manifest["agent_visible_digest"]:
        raise ValueError("Agent-visible task changed; candidate generation must run again")
    if is_golden:
        original = json.loads((source / "config.json").read_text())
        if source_agent_name(original) != "oracle":
            raise ValueError("--golden requires an Oracle source trial")
    elif not candidate_grade_allowed(manifest, task):
        raise ValueError("Candidate scoring needs the current Pro review or a valid same-version Golden")
    output = run_dir / ("regrade-" + secrets.token_hex(4))
    output.mkdir(mode=0o700)
    env = base_environment()
    # Regrades must retain the same request recovery budget as candidate and
    # Golden requests. Keep one saved candidate's Judge traffic at the two
    # authorized criterion workers while the dispatcher still owns eight slots.
    server, endpoint = start_proxy(
        output, env, tree_hash(task), concurrency=REGRADE_PROXY_CONCURRENCY,
        effort=None, max_attempts=11)
    args = [str(PREFIX / "bin/harbor"), "trials", "regrade", str(source.resolve(strict=True)),
            "--task-path", str(task.resolve(strict=True)), "--trials-dir", str(output / "trials")]
    for key, value in plans(task, run_dir, REGRADE_PROXY_CONCURRENCY, endpoint)["golden"]["verifier"]["env"].items():
        args += ["--ve", key + "=" + value]
    try:
        with (output / "regrade.log").open("w") as log:
            code = subprocess.run(args, stdout=log, stderr=subprocess.STDOUT, env=env).returncode
    finally:
        server.shutdown()
        server.server_close()
    receipt = {"source_trial": str(source), "verifier_task": str(task), "task_digest": tree_hash(task),
               "output": str(output), "exit_code": code, "status": "REGRADE_REQUIRES_REWARD_AUDIT"}
    if is_golden:
        valid = code == 0 and validate_golden_rewards(task, (output / "trials").glob("*/verifier/reward.json"))
        from vps_queue import file_lock, atomic_json
        with file_lock(run_dir / ".manifest.lock"):
            manifest = json.loads((run_dir / "manifest.json").read_text())
            manifest.update(golden_valid=valid, golden_verifier_task_digest=tree_hash(task) if valid else None,
                            golden_regrade_receipt=str(output / "receipt.json"))
            atomic_json(run_dir / "manifest.json", manifest)
        receipt["golden_valid"] = valid
    (output / "receipt.json").write_text(json.dumps(receipt, indent=2))
    return receipt


def main() -> None:
    parser = argparse.ArgumentParser()
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("doctor")
    plan = commands.add_parser("plan")
    plan.add_argument("task", type=Path)
    plan.add_argument("--concurrency", type=int, choices=[2, 3, 4], default=DEFAULT_TASK_CONCURRENCY)
    plan.add_argument("--memory-mb", type=int, default=DEFAULT_MEMORY_MB,
                      help="New Agent and Verifier memory limit in MiB (default: 2048)")
    plan.add_argument('--judge-workers', type=int, choices=(1, 2), default=DEFAULT_CRITERION_WORKERS)
    plan.add_argument('--pro-review', type=Path,
                      help='Import the complete web Pro author review; formal Golden remains enabled by default')
    plan.add_argument('--skip-formal-golden', action='store_true',
                      help='Explicit candidate-stage-only mode; requires --pro-review and does not satisfy final Golden preflight')
    batch_plan = commands.add_parser('plan-batch')
    batch_plan.add_argument('paths', nargs='+', type=Path)
    batch_plan.add_argument('--concurrency', type=int, choices=[2, 3, 4], default=DEFAULT_TASK_CONCURRENCY)
    batch_plan.add_argument('--memory-mb', type=int, default=DEFAULT_MEMORY_MB,
                            help='New Agent and Verifier memory limit in MiB (default: 2048)')
    batch_plan.add_argument('--judge-workers', type=int, choices=(1, 2), default=DEFAULT_CRITERION_WORKERS)
    batch_plan.add_argument('--pro-review-dir', type=Path,
                            help='Directory containing <task-directory-name>.json Pro reviews')
    batch_plan.add_argument('--skip-formal-golden', action='store_true',
                            help='Explicit candidate-stage-only mode; requires --pro-review-dir')
    run = commands.add_parser("run")
    run.add_argument("run_dir", type=Path)
    batch_run = commands.add_parser('run-batch')
    batch_run.add_argument('batch_dir', type=Path)
    status = commands.add_parser('status')
    status.add_argument('run_dir', type=Path, nargs='?')
    commands.add_parser('worker')
    batch_grade = commands.add_parser('grade-batch')
    batch_grade.add_argument('batch_dir', type=Path)
    adapter = commands.add_parser("prepare-verifier")
    adapter.add_argument("run_dir", type=Path)
    adapter.add_argument("--agent-image")
    adapter.add_argument("--task", type=Path)
    grade = commands.add_parser("regrade")
    grade.add_argument("source", type=Path)
    grade.add_argument("--task", type=Path, required=True)
    grade.add_argument("--run-dir", type=Path, required=True)
    grade.add_argument("--golden", action="store_true")
    args = parser.parse_args()
    if args.command == "doctor":
        result = host_status()
    elif args.command == 'plan-batch':
        result = prepare_batch(args.paths, args.concurrency, args.memory_mb, args.judge_workers,
                               args.pro_review_dir, args.skip_formal_golden)
    elif args.command in {'run-batch', 'grade-batch', 'status', 'worker'}:
        import vps_queue
        if args.command == 'worker':
            vps_queue.worker()
            return
        if args.command == 'status':
            result = vps_queue.queue_status(args.run_dir)
        else:
            runs = vps_queue.batch_runs(args.batch_dir)
            result = vps_queue.submit_runs(runs) if args.command == 'run-batch' else vps_queue.submit_grades(runs)
    elif args.command == "plan":
        result = {"prepared_run": str(prepare(args.task, args.concurrency, args.memory_mb,
                                             args.judge_workers, args.pro_review, args.skip_formal_golden)), "models_executed": False}
    elif args.command == "run":
        result = launch(args.run_dir)
    elif args.command == "prepare-verifier":
        result = prepare_verifier(args.run_dir, args.agent_image, args.task)
    else:
        from vps_queue import submit_regrade
        result = submit_regrade(args.source, args.task, args.run_dir, args.golden)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
