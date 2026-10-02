#!/usr/bin/env python3
"""Offline HTTP fault injection. Does not contact a provider or start Harbor."""
from __future__ import annotations

import http.server
import io
import concurrent.futures
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest import mock
from pathlib import Path

from vps_request_proxy import ProxyConfig, make_server
import vps_harbor

GOOD = {"type": "message", "id": "local-message", "role": "assistant", "model": "local",
        "content": [{"type": "text", "text": "This content mentions error and stream normally."}],
        "stop_reason": "end_turn", "usage": {"input_tokens": 5, "output_tokens": 8,
        "cache_read_input_tokens": 20, "cache_creation_input_tokens": 10}}
GOOD_SSE = b'event: message_start\ndata: {"type":"message_start","message":{"usage":{"cache_read_input_tokens":20}}}\n\nevent: message_stop\ndata: {"type":"message_stop"}\n\n'


class RuntimeTests(unittest.TestCase):
    def test_default_plan_keeps_four_per_task_with_eight_global_slots(self):
        with mock.patch.object(sys, 'argv', ['rl01', 'plan', '/unused-task']), \
                mock.patch.object(sys, 'stdout', new_callable=io.StringIO), \
                mock.patch.object(vps_harbor, 'prepare', return_value=Path('/unused-run')) as prepare:
            vps_harbor.main()
        self.assertEqual(prepare.call_args.args[1], 4)

    def test_proxy_firewall_is_limited_to_docker_interfaces_private_ip_and_port(self):
        with mock.patch.object(vps_harbor.subprocess, "run", return_value=mock.Mock(returncode=0)) as run:
            rules = vps_harbor.install_proxy_firewall("172.17.0.1", 32001)
            self.assertEqual({rule[1] for rule in rules}, {"docker0", "br-+"})
            for rule in rules:
                self.assertEqual(rule[rule.index("-d") + 1], "172.17.0.1")
                self.assertEqual(rule[rule.index("--dport") + 1], "32001")
            self.assertEqual(run.call_count, 2)
            with self.assertRaisesRegex(ValueError, "private Docker"):
                vps_harbor.install_proxy_firewall("76.13.21.51", 32001)
            self.assertEqual(run.call_count, 2)
            self.assertEqual(vps_harbor.install_proxy_firewall("127.0.0.1", 32001), [])

    def test_partial_firewall_installation_rolls_back_only_its_own_rule(self):
        results = [mock.Mock(returncode=0), mock.Mock(returncode=1), mock.Mock(returncode=0)]
        with mock.patch.object(vps_harbor.subprocess, "run", side_effect=results) as run:
            with self.assertRaisesRegex(ValueError, "scoped Docker access"):
                vps_harbor.install_proxy_firewall("172.17.0.1", 32001)
            deleted = run.call_args_list[-1].args[0]
            self.assertEqual(deleted[:5], ["iptables", "-w", "5", "-D", "INPUT"])
            self.assertIn("rl01-private-proxy:", " ".join(deleted))

    def test_stale_firewall_cleanup_preserves_live_and_unrelated_rules(self):
        listing = ("-A INPUT -i br-+ -d 172.17.0.1 -p tcp --dport 32001 "
                   "-m comment --comment rl01-private-proxy:100:111:32001 -j ACCEPT\n"
                   "-A INPUT -i br-+ -d 172.17.0.1 -p tcp --dport 32002 "
                   "-m comment --comment rl01-private-proxy:200:222:32002 -j ACCEPT\n"
                   "-A INPUT -p tcp --dport 23450 -j ACCEPT\n")
        with mock.patch.object(vps_harbor, "process_stamp", side_effect=[None, "222"]), \
                mock.patch.object(vps_harbor.subprocess, "run",
                                  side_effect=[mock.Mock(returncode=0, stdout=listing), mock.Mock(returncode=0)]) as run:
            vps_harbor.cleanup_stale_proxy_firewall()
            self.assertEqual(run.call_count, 2)
            self.assertIn("rl01-private-proxy:100:111:32001", run.call_args.args[0])
            self.assertNotIn("23450", run.call_args.args[0])

    def test_selected_concurrency_reaches_upstream(self):
        models = ["qwen3.7-plus", "gpt-5.6-sol", "claude-opus-4-8", "qwen3.8-max0902"]
        for limit in [2, 3, 4, 8]:
            with self.subTest(limit=limit):
                requests = models * (2 if limit == 8 else 1)
                ready, release, lock = threading.Event(), threading.Event(), threading.Lock()
                stats = {"active": 0, "peak": 0, "received": 0}
                class Upstream(http.server.BaseHTTPRequestHandler):
                    def log_message(self, *args):
                        pass
                    def do_POST(self):
                        self.rfile.read(int(self.headers["Content-Length"]))
                        with lock:
                            stats["active"] += 1
                            stats["received"] += 1
                            stats["peak"] = max(stats["peak"], stats["active"])
                            if stats["active"] == limit:
                                ready.set()
                        release.wait(5)
                        body = json.dumps(GOOD).encode()
                        self.send_response(200)
                        self.send_header("Content-Type", "application/json")
                        self.send_header("Content-Length", str(len(body)))
                        self.end_headers()
                        self.wfile.write(body)
                        with lock:
                            stats["active"] -= 1
                class UpstreamServer(http.server.ThreadingHTTPServer):
                    request_queue_size = 32
                upstream = UpstreamServer(("127.0.0.1", 0), Upstream)
                upstream.daemon_threads = True
                threading.Thread(target=upstream.serve_forever, daemon=True).start()
                with tempfile.TemporaryDirectory(prefix="rl01-concurrency-test-") as tmp:
                    root = Path(tmp)
                    (root / "claude-config").mkdir()
                    settings = root / "claude-config/settings.json"
                    settings.write_text(json.dumps({"env": {"ANTHROPIC_BASE_URL": "http://127.0.0.1:" + str(upstream.server_address[1]),
                                                           "ANTHROPIC_AUTH_TOKEN": "test-upstream-only"}}))
                    settings.chmod(0o600)
                    client_env = {}
                    with mock.patch.object(vps_harbor, "PREFIX", root), mock.patch.object(vps_harbor, "bridge_ip", return_value="127.0.0.1"):
                        options = {} if limit == 8 else {"concurrency": limit}
                        proxy, endpoint = vps_harbor.start_proxy(root, client_env, "test-task-digest", **options)
                    try:
                        with urllib.request.urlopen(endpoint + "/health") as response:
                            self.assertEqual(json.load(response)["max_in_flight"], limit)
                        def request(model):
                            req = urllib.request.Request(endpoint + "/v1/messages",
                                data=json.dumps({"model": model, "max_tokens": 100,
                                                 "messages": [{"role": "user", "content": "local concurrency test"}]}).encode(),
                                headers={"x-api-key": client_env["RL01_PROXY_TOKEN"]})
                            with urllib.request.urlopen(req, timeout=10) as response:
                                response.read()
                                return response.status
                        with concurrent.futures.ThreadPoolExecutor(max_workers=len(requests)) as pool:
                            futures = [pool.submit(request, model) for model in requests]
                            reached = ready.wait(5)
                            release.set()
                            self.assertTrue(reached, f"Selected concurrency did not reach the upstream: {stats}")
                            self.assertEqual([future.result() for future in futures], [200] * len(requests))
                        self.assertEqual((stats["peak"], stats["received"]), (limit, len(requests)))
                    finally:
                        release.set()
                        proxy.shutdown(); proxy.server_close()
                        upstream.shutdown(); upstream.server_close()

    def exercise(self, outcomes, model="gpt-5.6-sol", timeout=0.1,
                 proxy_effort="low", incoming_effort="high"):
        received = []
        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                received.append(json.loads(body))
                action = outcomes[min(len(received) - 1, len(outcomes) - 1)]
                status, content_type, response = action
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(response)))
                self.end_headers()
                if content_type == "stall":
                    time.sleep(0.2)
                try:
                    self.wfile.write(response)
                except (BrokenPipeError, ConnectionResetError):
                    pass
        upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        upstream.daemon_threads = True
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory(prefix="rl01-proxy-test-") as tmp:
            audit = Path(tmp) / "audit.jsonl"
            config = ProxyConfig("http://127.0.0.1:" + str(upstream.server_address[1]),
                                 "test-upstream-only", "test-client-only", audit,
                                 timeout=timeout, backoff_scale=0, effort=proxy_effort)
            proxy = make_server("127.0.0.1", 0, config)
            threading.Thread(target=proxy.serve_forever, daemon=True).start()
            request = {"model": model, "max_tokens": 100,
                       "output_config": {"effort": incoming_effort},
                       "messages": [{"role": "user", "content": [{"type": "text", "text": "Private test prompt",
                                   "cache_control": {"type": "ephemeral"}}]}]}
            if incoming_effort is None:
                request.pop("output_config")
            req = urllib.request.Request("http://127.0.0.1:" + str(proxy.server_address[1]) + "/v1/messages",
                                         data=json.dumps(request).encode(), headers={"x-api-key": "test-client-only"})
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    status, body = response.status, response.read()
            except urllib.error.HTTPError as exc:
                status, body = exc.code, exc.read()
                exc.close()
            finally:
                proxy.shutdown()
                proxy.server_close()
                upstream.shutdown()
                upstream.server_close()
            records = [json.loads(x) for x in audit.read_text().splitlines()]
            text = audit.read_text()
            for secret in ["test-upstream-only", "test-client-only", "Private test prompt", "mentions error"]:
                self.assertNotIn(secret, text)
            for received_request in received:
                expected_effort = proxy_effort if proxy_effort is not None else incoming_effort
                self.assertEqual(received_request.get("output_config", {}).get("effort"), expected_effort)
                if proxy_effort is None and incoming_effort is None:
                    self.assertNotIn("output_config", received_request)
                self.assertEqual(received_request["messages"], request["messages"])
            self.assertEqual(len({x["payload_hash"] for x in records}), 1)
            return status, body, received, records

    def test_golden_and_scoring_preserve_explicit_or_default_effort(self):
        for incoming in ("high", None):
            with self.subTest(incoming_effort=incoming):
                status, _, calls, logs = self.exercise(
                    [(200, "application/json", json.dumps(GOOD).encode())],
                    model="qwen3.7-plus", proxy_effort=None, incoming_effort=incoming)
                self.assertEqual((status, len(calls)), (200, 1))
                self.assertIsNone(logs[0]["effort"])

    def test_candidate_and_golden_job_effort_are_separate(self):
        with tempfile.TemporaryDirectory(prefix="rl01-effort-job-") as tmp:
            job = vps_harbor.plans(Path(tmp) / "task", Path(tmp), 4, "http://127.0.0.1:1")
        for candidate in job["candidates"]["agents"]:
            self.assertEqual(candidate["kwargs"]["reasoning_effort"], "low")
            self.assertEqual(candidate["env"]["CLAUDE_CODE_EFFORT_LEVEL"], "low")
        self.assertNotIn("CLAUDE_CODE_EFFORT_LEVEL", job["golden"]["verifier"]["env"])

    def test_tenth_retry_success_then_stop(self):
        status, _, calls, logs = self.exercise([(503, "application/json", b'{"error":"busy"}')] * 10 +
                                             [(200, "application/json", json.dumps(GOOD).encode())])
        self.assertEqual((status, len(calls), len(logs)), (200, 11, 11))
        self.assertEqual(logs[-1]["final_status"], "SUCCESS")
        self.assertEqual(logs[-1]["usage"]["cache_read_input_tokens"], 20)

    def test_stream_response_sends_keepalive_before_full_body(self):
        body = GOOD_SSE

        class Upstream(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers["Content-Length"]))
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                time.sleep(0.25)
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        upstream = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Upstream)
        upstream.daemon_threads = True
        threading.Thread(target=upstream.serve_forever, daemon=True).start()
        with tempfile.TemporaryDirectory(prefix="rl01-sse-proxy-test-") as tmp:
            audit = Path(tmp) / "audit.jsonl"
            config = ProxyConfig("http://127.0.0.1:" + str(upstream.server_address[1]),
                                 "test-upstream-only", "test-client-only", audit,
                                 timeout=2, backoff_scale=0, effort=None,
                                 sse_keepalive_interval=0.05)
            proxy = make_server("127.0.0.1", 0, config)
            threading.Thread(target=proxy.serve_forever, daemon=True).start()
            request = {"model": "qwen3.7-plus", "max_tokens": 100, "stream": True,
                       "messages": [{"role": "user", "content": "local SSE test"}]}
            req = urllib.request.Request(
                "http://127.0.0.1:" + str(proxy.server_address[1]) + "/v1/messages",
                data=json.dumps(request).encode(),
                headers={"x-api-key": "test-client-only"})
            try:
                started = time.monotonic()
                with urllib.request.urlopen(req, timeout=5) as response:
                    first = response.read(1)
                    first_byte_delay = time.monotonic() - started
                    received = first + response.read()
                deadline = time.monotonic() + 1
                while not audit.is_file() and time.monotonic() < deadline:
                    time.sleep(0.01)
                records = [json.loads(x) for x in audit.read_text().splitlines()]
            finally:
                proxy.shutdown()
                proxy.server_close()
                upstream.shutdown()
                upstream.server_close()
            self.assertEqual(response.status, 200)
            self.assertLess(first_byte_delay, 0.2)
            self.assertIn(b"rl01-keepalive", received)
            self.assertIn(b"message_stop", received)
            self.assertEqual(records[-1]["delivery_status"], "SUCCESS")

    def test_exhaustion_stops_outer_sdk_retries(self):
        status, body, calls, logs = self.exercise([(429, "application/json", b'{"error":"busy"}')])
        self.assertEqual((status, len(calls)), (400, 11))
        self.assertIn(b"RETRY_BUDGET_EXHAUSTED", body)
        self.assertEqual(logs[-1]["final_status"], "REQUEST_FAILED")

    def test_body_and_stream_failures_share_budget(self):
        cases = [(200, "application/json", b'{"type":"error","error":{"type":"api_error"}}'),
                 (200, "text/event-stream", b'event: message_start\ndata: {"type":"message_start"}\n\n'),
                 (200, "text/event-stream", b'event: error\ndata: {"type":"error"}\n\n'),
                 (200, "application/json", b'{"type":"message"'),
                 (200, "stall", json.dumps(GOOD).encode())]
        for case in cases:
            with self.subTest(kind=case[1], body=case[2][:25]):
                status, _, calls, logs = self.exercise([case, (200, "text/event-stream", GOOD_SSE)])
                self.assertEqual((status, len(calls)), (200, 2))
                self.assertEqual(logs[0]["final_status"], "RETRY")

    def test_all_candidate_and_judge_model_names(self):
        for model in ["gpt-5.6-sol", "claude-opus-4-8", "qwen3.8-max0902", "qwen3.7-plus"]:
            with self.subTest(model=model):
                status, _, calls, _ = self.exercise([(200, "application/json", json.dumps(GOOD).encode())], model)
                self.assertEqual((status, len(calls)), (200, 1))
                self.assertEqual(calls[0]["model"], model)

    def test_auth_failure_is_not_retried(self):
        status, _, calls, logs = self.exercise([(401, "application/json", b'{"error":"bad credential"}')])
        self.assertEqual((status, len(calls), len(logs)), (401, 1, 1))


if __name__ == "__main__":
    unittest.main(verbosity=2)
