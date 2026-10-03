#!/usr/bin/env python3
"""File, PID and network isolation for direct Claude Code stages."""
from __future__ import annotations

import hashlib
import fcntl
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import socketserver
import stat
import struct
import subprocess
import threading
import time

from vps_request_proxy import ProxyConfig
from reliable_proxy import make_server

PREFIX = Path('/opt/rl01-direct')
_UID_LOCK = threading.Lock()


def hashes(root: Path) -> dict:
    result = {}
    for path in sorted(root.rglob('*')):
        if path.is_symlink():
            raise ValueError(f'symlink is not accepted: {path.name}')
        if path.is_file():
            with path.open('rb') as handle:
                result[str(path.relative_to(root))] = hashlib.file_digest(handle, 'sha256').hexdigest()
        elif not path.is_dir():
            raise ValueError('special files are not accepted')
    return result


def owned_tree(path: Path, uid: int):
    os.chown(path, uid, uid)
    path.chmod(0o700)
    for item in path.rglob('*'):
        if item.is_symlink():
            raise ValueError('stage source contains a symlink')
        os.chown(item, uid, uid)
        item.chmod(0o700 if item.is_dir() else 0o600)


class UnixHTTPServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    def verify_request(self, request, address):
        _, uid, _ = struct.unpack('3i', request.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        return uid == self.allowed_uid


class Stage:
    def __init__(self, label: str, app: Path, *, tests: Path | None = None,
                 writable_output: bool = False, model: str = 'qwen3.7-plus',
                 upstream: str | None = None, upstream_token: str | None = None,
                 effort: str | None = None, memory_mb: int = 2048):
        with _UID_LOCK:
            counter = PREFIX/'private/uid-counter'
            with counter.open('a+') as handle:
                fcntl.flock(handle, fcntl.LOCK_EX)
                handle.seek(0)
                self.uid = int(handle.read() or '22000')
                if self.uid > 60000:
                    raise RuntimeError('stage uid pool exhausted')
                handle.seek(0)
                handle.truncate()
                handle.write(str(self.uid + 1))
                handle.flush()
        self.label = label
        self.root = PREFIX / 'stages' / (label + '-' + secrets.token_hex(5))
        self.root.mkdir(mode=0o700)
        self.app = self.root / 'app'
        shutil.copytree(app, self.app)
        (self.app / 'output').mkdir(exist_ok=True)
        self.tests = None
        if tests is not None:
            self.tests = self.root / 'tests'
            shutil.copytree(tests, self.tests)
        self.home = self.root / 'home'
        self.home.mkdir()
        (self.home / '.claude').mkdir()
        (self.home / '.claude/settings.json').write_text(json.dumps({'permissions': {'defaultMode': 'bypassPermissions'}}))
        (self.home / '.claude.json').write_text(json.dumps({'hasCompletedOnboarding': True}))
        self.etc = self.root / 'etc'
        self.etc.mkdir()
        (self.etc/'ssl').mkdir()
        for public_config in ['fonts', 'libreoffice', 'alternatives']:
            (self.etc/public_config).mkdir()
        (self.etc / 'passwd').write_text('root:x:0:0:Sandbox:/home/runner:/bin/bash\n')
        (self.etc / 'group').write_text('root:x:0:\n')
        (self.etc / 'hosts').write_text('127.0.0.1 localhost\n')
        owned_tree(self.root, self.uid)
        self.writable_output = writable_output
        self.model = model
        self.memory_mb = memory_mb
        self.before = hashes(self.app)
        self.tests_before = hashes(self.tests) if self.tests is not None else None
        self.token = secrets.token_urlsafe(32)
        if upstream is None:
            settings = PREFIX / 'private/runtime-settings.json'
            if settings.stat().st_mode & 0o077:
                raise PermissionError('runtime credential file must be 0600')
            credential = json.loads(settings.read_text())['env']
            upstream = credential['ANTHROPIC_BASE_URL']
            upstream_token = credential['ANTHROPIC_AUTH_TOKEN']
        audit = PREFIX / 'receipts' / (self.root.name + '-requests.jsonl')
        config = ProxyConfig(upstream, upstream_token, self.token, audit, stage=label,
                             task_digest=hashlib.sha256(json.dumps(self.before, sort_keys=True).encode()).hexdigest(),
                             max_attempts=11, timeout=180, effort=effort,
                             shared_slot_dir=PREFIX/'private/api-slots')
        tcp = make_server('127.0.0.1', 0, config)
        original = tcp.RequestHandlerClass
        original_post = original.do_POST
        allowed_model = model
        class GuardedHandler(original):
            def do_POST(self):
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 32 * 1024 * 1024:
                    self.reply(400, b'{"error":"body_size"}')
                    return
                body = self.rfile.read(size)
                try:
                    value = json.loads(body)
                    if value.get('model') != allowed_model:
                        self.reply(403, b'{"error":"model_not_allowed_for_stage"}')
                        return
                except ValueError:
                    self.reply(400, b'{"error":"invalid_json"}')
                    return
                stream = self.rfile
                self.rfile = io.BytesIO(body)
                try:
                    original_post(self)
                finally:
                    self.rfile = stream
        tcp.server_close()
        self.socket_path = self.root / 'model.sock'
        self.server = UnixHTTPServer(str(self.socket_path), GuardedHandler)
        self.server.allowed_uid = self.uid
        os.chown(self.socket_path, self.uid, self.uid)
        self.socket_path.chmod(0o600)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.audit = audit
        self.process = None
        self.peak_pss_bytes = 0
        self.resource_error = None
        self._monitor_stop = threading.Event()

    def command(self, argv: list[str], *, aliases: tuple[Path, ...] = ()) -> list[str]:
        config = self.root / 'stage.json'
        config.write_text(json.dumps({'command': argv}))
        os.chown(config, self.uid, self.uid)
        config.chmod(0o400)
        args = [str(PREFIX/'bin/bwrap'), '--unshare-user', '--uid', '0', '--gid', '0',
                '--unshare-pid', '--unshare-net', '--unshare-ipc', '--unshare-uts',
                '--die-with-parent', '--new-session', '--clearenv',
                '--ro-bind', '/usr', '/usr', '--symlink', 'usr/bin', '/bin',
                '--symlink', 'usr/lib', '/lib', '--symlink', 'usr/lib64', '/lib64',
                '--dir', '/proc', '--dir', '/proc/self', '--dir', '/sys', '--dev', '/dev', '--tmpfs', '/tmp',
                '--tmpfs', '/run', '--ro-bind', str(self.etc), '/etc']
        for kernel_file in ['version', 'cpuinfo']:
            args += ['--ro-bind', '/proc/'+kernel_file, '/proc/'+kernel_file]
        if Path('/etc/ssl').exists():
            args += ['--ro-bind', '/etc/ssl', '/etc/ssl']
        for system_config in ['/etc/fonts', '/etc/libreoffice', '/etc/alternatives']:
            if Path(system_config).exists():
                args += ['--ro-bind', system_config, system_config]
        for part in ['bin', 'vendor', 'venv']:
            args += ['--ro-bind', str(PREFIX/part), str(PREFIX/part)]
        args += ['--ro-bind', str(PREFIX/'lib/sandbox_entry.py'), str(PREFIX/'lib/sandbox_entry.py')]
        args += ['--ro-bind', '/opt/mamba', '/opt/mamba',
                 '--ro-bind', str(self.app), '/app', '--bind', str(self.home), '/home/runner',
                 '--ro-bind', str(config), '/run/stage.json',
                 '--ro-bind', '/proc', '/run/setup-proc',
                 '--ro-bind', str(self.socket_path), '/run/model.sock']
        if self.writable_output:
            args += ['--bind', str(self.app/'output'), '/app/output']
        if self.tests is not None:
            args += ['--ro-bind', str(self.tests), '/tests']
        for alias in aliases:
            args += ['--ro-bind', str(self.app), str(alias)]
        variables = {
            'HOME': '/home/runner', 'USER': 'root', 'LOGNAME': 'root',
            'PATH': f'{PREFIX}/bin:{PREFIX}/venv/bin:/opt/mamba/bin:/usr/bin:/usr/sbin:/bin',
            'TMPDIR': '/tmp', 'LANG': 'C.UTF-8', 'PYTHONNOUSERSITE': '1',
            'LD_LIBRARY_PATH': '/usr/lib/libreoffice/program',
            'URE_BOOTSTRAP': 'vnd.sun.star.pathname:/usr/lib/libreoffice/program/fundamentalrc',
            'CLAUDE_CONFIG_DIR': '/home/runner/.claude',
            'ANTHROPIC_BASE_URL': 'http://127.0.0.1:18081',
            'ANTHROPIC_AUTH_TOKEN': self.token, 'ANTHROPIC_API_KEY': self.token,
            'CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC': '1', 'CLAUDE_CODE_MAX_RETRIES': '0',
            'DISABLE_PROMPT_CACHING': '0', 'IS_SANDBOX': '1',
        }
        for key, value in variables.items():
            args += ['--setenv', key, value]
        args += ['--remount-ro', '/', '--cap-drop', 'ALL', '--cap-add', 'CAP_NET_ADMIN',
                 '--cap-add', 'CAP_SETPCAP', '--cap-add', 'CAP_SYS_ADMIN',
                 '--chdir', '/app', '--', str(PREFIX/'venv/bin/python'), str(PREFIX/'lib/sandbox_entry.py')]
        return args

    def monitor(self, process):
        import psutil
        self.process = process
        def watch():
            while not self._monitor_stop.wait(0.25):
                try:
                    parent = psutil.Process(process.pid)
                    children = [parent, *parent.children(recursive=True)]
                    usage = 0
                    for child in children:
                        try:
                            info = child.memory_full_info()
                            usage += getattr(info, 'pss', info.rss)
                        except psutil.AccessDenied:
                            try:
                                usage += child.memory_info().rss
                            except psutil.NoSuchProcess:
                                pass
                            except psutil.AccessDenied:
                                self.resource_error = 'MEMORY_OBSERVATION_UNAVAILABLE'
                                process.kill()
                                return
                        except psutil.NoSuchProcess:
                            pass
                    self.peak_pss_bytes = max(self.peak_pss_bytes, usage)
                    if usage > self.memory_mb * 1024 * 1024:
                        self.resource_error = 'PSS_WATCHDOG_LIMIT_EXCEEDED'
                        process.kill()
                        return
                except psutil.NoSuchProcess:
                    return
        threading.Thread(target=watch, daemon=True).start()

    def run(self, argv: list[str], *, timeout: int = 300, aliases: tuple[Path, ...] = ()):
        process = subprocess.Popen(self.command(argv, aliases=aliases), stdin=subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   user=self.uid, group=self.uid, extra_groups=[], start_new_session=True,
                                   env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
        self.monitor(process)
        try:
            stdout, stderr = process.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            self.resource_error = 'STAGE_TIMEOUT'
            process.kill()
            stdout, stderr = process.communicate()
        (self.root/'stdout.txt').write_bytes(stdout)
        (self.root/'stderr.txt').write_bytes(stderr)
        return subprocess.CompletedProcess(argv, process.returncode, stdout.decode(errors='replace'), stderr.decode(errors='replace'))

    def close(self):
        self._monitor_stop.set()
        if self.process is not None and self.process.returncode is None:
            self.process.kill()
        self.server.shutdown()
        self.server.server_close()
        self.socket_path.unlink(missing_ok=True)
        after = hashes(self.app)
        immutable = {key: value for key, value in self.before.items() if not key.startswith('output/')}
        unchanged = all(after.get(key) == value for key, value in immutable.items())
        tests_unchanged = self.tests is None or hashes(self.tests) == self.tests_before
        receipt = {'stage': self.label, 'root': str(self.root), 'host_uid': self.uid,
                   'model': self.model, 'input_hashes': immutable, 'inputs_unchanged': unchanged,
                   'output_hashes': {key: value for key, value in after.items() if key.startswith('output/')},
                   'peak_observed_memory_bytes': self.peak_pss_bytes, 'resource_error': self.resource_error,
                   'memory_policy': {'kind': 'pss_with_rss_fallback_watchdog', 'limit_mb': self.memory_mb,
                                     'cgroup_hard_limit_available': False},
                   'tests_hashes': self.tests_before, 'tests_unchanged': tests_unchanged,
                   'exit_code': self.process.returncode if self.process is not None else None}
        isolation = self.home/'isolation.json'
        if isolation.is_file():
            receipt['isolation'] = json.loads(isolation.read_text())
        (PREFIX/'receipts'/f'{self.root.name}-stage.json').write_text(json.dumps(receipt, indent=2))
        if not unchanged or not tests_unchanged:
            raise RuntimeError('immutable input changed')
        if self.resource_error:
            raise RuntimeError(self.resource_error)
        return receipt
