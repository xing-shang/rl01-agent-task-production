#!/usr/bin/env python3
"""Private Messages proxy; no prompts, responses, or keys are logged."""
from __future__ import annotations

import argparse
import email.utils
import fcntl
import hashlib
import http.server
import json
import os
import queue
import random
import threading
import time
import urllib.error
import urllib.request
import uuid
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONCURRENCY = 8


class IncompleteResponse(Exception):
    pass


class DownstreamClosed(Exception):
    pass


SSE_KEEPALIVE = b": rl01-keepalive\n\n"


def error_detail(exc: Exception) -> str | None:
    if isinstance(exc, IncompleteResponse):
        return str(exc)
    if isinstance(exc, urllib.error.URLError):
        reason = exc.reason
        return f"{type(reason).__name__}: {str(reason)[:240]}"
    return str(exc)[:240] or None


def validate_response(body: bytes, content_type: str, path: str) -> dict:
    if not body.strip():
        raise IncompleteResponse("empty_body")
    if "text/event-stream" in content_type:
        events, usage, terminal = [], {}, False
        for block in body.replace(b"\r\n", b"\n").split(b"\n\n"):
            event = None
            data = []
            for line in block.splitlines():
                if line.startswith(b"event:"):
                    event = line[6:].strip().decode()
                elif line.startswith(b"data:"):
                    data.append(line[5:].strip())
            if not data:
                continue
            raw = b"\n".join(data)
            if raw == b"[DONE]":
                terminal |= "/messages" not in path
                continue
            try:
                value = json.loads(raw)
            except ValueError as exc:
                raise IncompleteResponse("invalid_sse_json") from exc
            if not isinstance(value, dict):
                raise IncompleteResponse("invalid_sse_object")
            kind = value.get("type", event)
            if kind == "error" or "error" in value:
                raise IncompleteResponse("sse_error")
            terminal |= kind in {"message_stop", "response.completed"}
            usage.update(value.get("usage") or {})
            usage.update((value.get("message") or {}).get("usage") or {})
            events.append(kind)
        if not terminal:
            raise IncompleteResponse("missing_terminal_event")
        return {"terminal_complete": True, "usage": numeric_usage(usage)}
    try:
        value = json.loads(body)
    except ValueError as exc:
        raise IncompleteResponse("invalid_json") from exc
    if not isinstance(value, dict) or value.get("type") == "error" or "error" in value:
        raise IncompleteResponse("json_error")
    if path.split("?")[0].endswith("/messages"):
        if value.get("type") != "message" or value.get("stop_reason") is None:
            raise IncompleteResponse("incomplete_message")
    return {"terminal_complete": True, "usage": numeric_usage(value.get("usage") or {})}


def numeric_usage(value: dict) -> dict:
    return {k: v for k, v in value.items() if isinstance(v, (int, float))}


@dataclass
class ProxyConfig:
    upstream: str
    token: str
    client_token: str
    audit: Path
    stage: str = "agent-and-judge"
    task_digest: str = "not-a-task-run"
    max_attempts: int = 11
    timeout: float = 900
    backoff_scale: float = 1
    effort: str | None = "low"
    max_in_flight: int = DEFAULT_CONCURRENCY
    sse_keepalive_interval: float = 5.0
    shared_slot_dir: Path | None = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    upstream_slots: threading.Semaphore = field(init=False)

    def __post_init__(self) -> None:
        if self.max_in_flight < 1:
            raise ValueError("max_in_flight must be positive")
        if self.sse_keepalive_interval <= 0:
            raise ValueError("sse_keepalive_interval must be positive")
        self.upstream_slots = threading.BoundedSemaphore(self.max_in_flight)

    def record(self, value: dict) -> None:
        with self.lock:
            self.audit.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with self.audit.open("a") as handle:
                handle.write(json.dumps(value, ensure_ascii=False) + "\n")
            self.audit.chmod(0o600)

    @contextmanager
    def request_slot(self):
        with self.upstream_slots:
            if self.shared_slot_dir is None:
                yield
                return
            self.shared_slot_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
            handle = None
            try:
                while handle is None:
                    for number in range(DEFAULT_CONCURRENCY):
                        candidate = (self.shared_slot_dir / str(number)).open('a')
                        try:
                            fcntl.flock(candidate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        except BlockingIOError:
                            candidate.close()
                        else:
                            handle = candidate
                            break
                    if handle is None:
                        time.sleep(0.1)
                yield
            finally:
                if handle is not None:
                    handle.close()


def make_server(bind: str, port: int, config: ProxyConfig) -> http.server.ThreadingHTTPServer:
    class ProxyServer(http.server.ThreadingHTTPServer):
        request_queue_size = 32

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args) -> None:
            pass

        def reply(self, status: int, body: bytes, content_type="application/json") -> tuple[bool, str | None]:
            try:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(body)
                self.wfile.flush()
            except OSError as exc:
                self.close_connection = True
                return False, type(exc).__name__
            self.close_connection = True
            return True, None

        def begin_chunked_sse(self, content_type: str, headers) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", headers.get("Cache-Control", "no-cache"))
            self.send_header("X-Accel-Buffering", headers.get("X-Accel-Buffering", "no"))
            for name in ("x-request-id", "request-id"):
                value = headers.get(name)
                if value:
                    self.send_header(name, value)
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Connection", "close")
            self.end_headers()
            self.wfile.flush()

        def write_chunk(self, body: bytes) -> None:
            try:
                self.wfile.write(f"{len(body):X}\r\n".encode("ascii"))
                self.wfile.write(body)
                self.wfile.write(b"\r\n")
                self.wfile.flush()
            except OSError as exc:
                raise DownstreamClosed(type(exc).__name__) from exc

        def finish_chunked(self) -> None:
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except OSError as exc:
                raise DownstreamClosed(type(exc).__name__) from exc
            finally:
                self.close_connection = True

        def read_stream_buffered(self, response) -> bytes:
            """Keep Claude's SSE connection alive while validating a full upstream body."""
            result = queue.Queue(maxsize=1)

            def reader() -> None:
                try:
                    chunks = []
                    while True:
                        chunk = response.read(64 * 1024)
                        if not chunk:
                            break
                        chunks.append(chunk)
                    result.put((True, b"".join(chunks)))
                except Exception as exc:
                    result.put((False, exc))

            threading.Thread(target=reader, daemon=True).start()
            while True:
                try:
                    complete, value = result.get(timeout=config.sse_keepalive_interval)
                except queue.Empty:
                    self.write_chunk(SSE_KEEPALIVE)
                    continue
                if complete:
                    return value
                raise value

        def wait_with_sse_keepalive(self, seconds: float) -> None:
            deadline = time.monotonic() + seconds
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                time.sleep(min(config.sse_keepalive_interval, remaining))
                if remaining > config.sse_keepalive_interval:
                    self.write_chunk(SSE_KEEPALIVE)

        def do_GET(self) -> None:
            if self.path == "/health":
                self.reply(200, json.dumps({"status": "ready", "max_attempts": config.max_attempts,
                                           "effort": config.effort, "max_in_flight": config.max_in_flight}).encode())
            else:
                self.reply(404, b'{"error":"unsupported_path"}')

        def do_POST(self) -> None:
            supplied = self.headers.get("x-api-key") or self.headers.get("Authorization", "").removeprefix("Bearer ")
            if supplied != config.client_token:
                self.reply(401, b'{"error":"proxy_auth_failed"}')
                return
            if self.path.split("?")[0] not in {"/v1/messages", "/v1/messages/count_tokens"}:
                self.reply(404, b'{"error":"unsupported_path"}')
                return
            try:
                size = int(self.headers.get("Content-Length", "0"))
                if not 0 < size <= 32 * 1024 * 1024:
                    raise ValueError("body_size")
                body = self.rfile.read(size)
                payload = json.loads(body)
                if self.path.split("?")[0] == "/v1/messages":
                    # Claude Code can omit effort for gateway model IDs it does
                    # not recognize. Force it only for stages that explicitly
                    # require low effort; Golden and Judge use provider default.
                    if config.effort is not None:
                        payload.setdefault("output_config", {})["effort"] = config.effort
                body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
            except (ValueError, TypeError, AttributeError):
                self.reply(400, b'{"error":"invalid_request"}')
                return
            request_id = str(uuid.uuid4())
            base = {"logical_request_id": request_id, "stage": config.stage,
                    "task_digest": config.task_digest, "model": payload.get("model"),
                    "payload_hash": hashlib.sha256(body).hexdigest(), "effort": config.effort,
                    "max_in_flight": config.max_in_flight}
            headers = {k: v for k, v in self.headers.items() if k.lower() not in
                       {"authorization", "x-api-key", "host", "content-length", "connection", "accept-encoding"}}
            headers.update({"Authorization": "Bearer " + config.token, "x-api-key": config.token,
                            "Content-Type": "application/json", "Accept-Encoding": "identity"})
            stream_request = payload.get("stream") is True and self.path.split("?")[0] == "/v1/messages"
            # Real model events remain buffered until validation completes. For
            # SSE only, comment keepalives keep the client connection open while
            # the upstream response is being collected.
            with config.request_slot():
                chunked_started = False
                for attempt in range(config.max_attempts):
                    start = time.time()
                    status, retry_after, error, detail = None, 0, None, None
                    try:
                        req = urllib.request.Request(config.upstream.rstrip("/") + self.path,
                                                     data=body, headers=headers, method="POST")
                        with urllib.request.urlopen(req, timeout=config.timeout) as response:
                            status = response.status
                            content_type = response.headers.get("Content-Type", "application/json")
                            if stream_request and "text/event-stream" in content_type:
                                if not chunked_started:
                                    self.begin_chunked_sse(content_type, response.headers)
                                    chunked_started = True
                                response_body = self.read_stream_buffered(response)
                            else:
                                response_body = response.read()
                        validation = validate_response(response_body, content_type, self.path)
                        record = {**base, "attempt_index": attempt, "retry_index": attempt,
                                  "http_status": status, "started_at": start, "ended_at": time.time(),
                                  "backoff_seconds": 0, "final_status": "SUCCESS", **validation}
                        if chunked_started:
                            try:
                                self.write_chunk(response_body)
                                self.finish_chunked()
                            except DownstreamClosed as exc:
                                record.update({"delivery_status": "FAILED", "delivery_error": str(exc)})
                                config.record(record)
                                return
                        else:
                            delivered, delivery_error = self.reply(status, response_body, content_type)
                            if not delivered:
                                record.update({"delivery_status": "FAILED", "delivery_error": delivery_error})
                        if "delivery_status" not in record:
                            record["delivery_status"] = "SUCCESS"
                        config.record(record)
                        return
                    except DownstreamClosed as exc:
                        config.record({**base, "attempt_index": attempt, "retry_index": attempt,
                                       "http_status": status, "error_type": "downstream_closed",
                                       "error_detail": str(exc), "started_at": start, "ended_at": time.time(),
                                       "terminal_complete": False, "backoff_seconds": 0,
                                       "final_status": "DELIVERY_FAILED"})
                        return
                    except urllib.error.HTTPError as exc:
                        status = exc.code
                        error = "http_error"
                        try:
                            raw = exc.read()
                            retry_value = exc.headers.get("Retry-After", "0")
                            try:
                                retry_after = float(retry_value)
                            except ValueError:
                                retry_after = max(0, email.utils.parsedate_to_datetime(retry_value).timestamp() - time.time())
                        except (ValueError, TypeError):
                            retry_after = 0
                        finally:
                            exc.close()
                        if status != 429 and not 500 <= status < 600:
                            record = {**base, "attempt_index": attempt, "retry_index": attempt,
                                      "http_status": status, "error_type": error,
                                      "started_at": start, "ended_at": time.time(),
                                      "terminal_complete": False, "backoff_seconds": 0,
                                      "final_status": "CONFIGURATION_ERROR"}
                            # Return a safe error envelope; upstream error bodies
                            # can echo credentials or other private information.
                            if chunked_started:
                                try:
                                    self.write_chunk(("event: error\ndata: " + json.dumps({
                                        "type": "error", "error": {"type": "api_error",
                                        "message": "upstream HTTP " + str(status)}}) + "\n\n").encode())
                                    self.finish_chunked()
                                except DownstreamClosed:
                                    record["delivery_status"] = "FAILED"
                                else:
                                    record["delivery_status"] = "SUCCESS"
                            else:
                                delivered, delivery_error = self.reply(status, json.dumps({"type": "error", "error": {
                                    "type": "invalid_request_error", "message": "upstream HTTP " + str(status)}}).encode())
                                record["delivery_status"] = "SUCCESS" if delivered else "FAILED"
                                if delivery_error:
                                    record["delivery_error"] = delivery_error
                            config.record(record)
                            return
                    except Exception as exc:
                        error = str(exc) if isinstance(exc, IncompleteResponse) else type(exc).__name__
                        detail = error_detail(exc)
                    exhausted = attempt + 1 == config.max_attempts
                    delay = 0 if exhausted else max(retry_after, min(60, 2 ** min(attempt, 6) + random.random())) * config.backoff_scale
                    record = {**base, "attempt_index": attempt, "retry_index": attempt,
                              "http_status": status, "error_type": error,
                              "started_at": start, "ended_at": time.time(),
                              "terminal_complete": False, "backoff_seconds": delay,
                              "final_status": "REQUEST_FAILED" if exhausted else "RETRY"}
                    if detail:
                        record["error_detail"] = detail
                    config.record(record)
                    if exhausted:
                        # 400 stops outer Claude SDK retries from multiplying
                        # this already exhausted eleven-attempt request budget.
                        if chunked_started:
                            try:
                                self.write_chunk(b'event: error\ndata: {"type":"error","error":{"type":"overloaded_error","message":"RL01_REQUEST_RETRY_BUDGET_EXHAUSTED; inspect private request audit"}}\n\n')
                                self.finish_chunked()
                            except DownstreamClosed:
                                pass
                        else:
                            self.reply(400, b'{"type":"error","error":{"type":"invalid_request_error","message":"RL01_REQUEST_RETRY_BUDGET_EXHAUSTED; inspect private request audit"}}')
                        return
                    try:
                        if chunked_started:
                            self.wait_with_sse_keepalive(delay)
                        else:
                            time.sleep(delay)
                    except DownstreamClosed as exc:
                        config.record({**base, "attempt_index": attempt, "retry_index": attempt,
                                       "http_status": status, "error_type": "downstream_closed",
                                       "error_detail": str(exc), "started_at": start, "ended_at": time.time(),
                                       "terminal_complete": False, "backoff_seconds": 0,
                                       "final_status": "DELIVERY_FAILED"})
                        return

    server = ProxyServer((bind, port), Handler)
    server.daemon_threads = True
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bind", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=18991)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--task-digest", default="not-a-task-run")
    parser.add_argument("--max-in-flight", type=int, default=DEFAULT_CONCURRENCY)
    args = parser.parse_args()
    config = ProxyConfig(os.environ["RL01_UPSTREAM_BASE"], os.environ["RL01_UPSTREAM_TOKEN"],
                         os.environ["RL01_PROXY_TOKEN"], args.audit, task_digest=args.task_digest,
                         max_in_flight=args.max_in_flight)
    make_server(args.bind, args.port, config).serve_forever()


if __name__ == "__main__":
    main()
