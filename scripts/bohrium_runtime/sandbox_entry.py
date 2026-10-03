#!/usr/bin/env python3
"""Trusted entry point: enable private loopback, drop capabilities, run one CLI."""
from __future__ import annotations

import ctypes
import errno
import fcntl
import http.client
import http.server
import json
import os
from pathlib import Path
import resource
import socket
import struct
import subprocess
import sys
import threading


def enable_loopback():
    interface = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    request = struct.pack('16sH22x', b'lo', 0)
    flags = struct.unpack('16sH22x', fcntl.ioctl(interface, 0x8913, request))[1]
    fcntl.ioctl(interface, 0x8914, struct.pack('16sH22x', b'lo', flags | 1))
    interface.close()


def mount_own_process():
    libc=ctypes.CDLL(None,use_errno=True)
    if libc.mount(b'/run/setup-proc/self',b'/proc/self',None,4096,None)!=0:
        raise OSError(ctypes.get_errno(),'bind own process directory')
    if libc.mount(None,b'/proc/self',None,4096|32|1|2|4|8,None)!=0:
        raise OSError(ctypes.get_errno(),'make own process directory read-only')
    # Mask the setup-only source before any untrusted code is executed.
    if libc.mount(b'tmpfs',b'/run/setup-proc',b'tmpfs',1|2|4|8,b'size=4k,mode=000')!=0:
        raise OSError(ctypes.get_errno(),'hide setup process tree')


def restrict_process() -> dict:
    libc = ctypes.CDLL(None, use_errno=True)
    # Lock NOROOT so exec cannot reconstruct capabilities for namespace uid 0.
    if libc.prctl(28, 0x0F, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_SECUREBITS')
    for capability in range(41):
        if libc.prctl(24, capability, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_CAPBSET_DROP')
    class Header(ctypes.Structure):
        _fields_ = [('version', ctypes.c_uint32), ('pid', ctypes.c_int)]
    class Data(ctypes.Structure):
        _fields_ = [('effective', ctypes.c_uint32), ('permitted', ctypes.c_uint32), ('inheritable', ctypes.c_uint32)]
    header = Header(0x20080522, 0)
    data = (Data * 2)()
    if libc.capset(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise OSError(ctypes.get_errno(), 'capset')
    if libc.prctl(38, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_NO_NEW_PRIVS')
    # x86_64 seccomp: prohibit namespace creation and mount operations.
    class Filter(ctypes.Structure):
        _fields_ = [('code', ctypes.c_ushort), ('jt', ctypes.c_ubyte), ('jf', ctypes.c_ubyte), ('k', ctypes.c_uint32)]
    class Program(ctypes.Structure):
        _fields_ = [('length', ctypes.c_ushort), ('filter', ctypes.POINTER(Filter))]
    rules = [(0x20, 0, 0, 4), (0x15, 1, 0, 0xC000003E), (0x06, 0, 0, 0x80000000),
             (0x20, 0, 0, 0), (0x35, 0, 1, 0x40000000), (0x06, 0, 0, 0x80000000)]
    for number in [155, 165, 166, 175, 176, 246, 272, 304, 308, 313, 428, 429, 430, 431, 432, 433, 442]:
        rules.extend([(0x15, 0, 1, number), (0x06, 0, 0, 0x50000 | errno.EPERM)])
    # clone3 falls back to clone, where namespace flags are rejected.
    rules.extend([(0x15, 0, 1, 435), (0x06, 0, 0, 0x50000 | errno.ENOSYS),
                  (0x15, 0, 3, 56), (0x20, 0, 0, 16),
                  (0x45, 0, 1, 0x7E020000), (0x06, 0, 0, 0x50000 | errno.EPERM),
                  (0x06, 0, 0, 0x7FFF0000)])
    filters = (Filter * len(rules))(*(Filter(*rule) for rule in rules))
    program = Program(len(rules), filters)
    if libc.prctl(22, 2, ctypes.byref(program), 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'PR_SET_SECCOMP')
    if libc.capget(ctypes.byref(header), ctypes.byref(data)) != 0:
        raise OSError(ctypes.get_errno(), 'capget')
    if any(item.effective or item.permitted or item.inheritable for item in data):
        raise RuntimeError('capabilities were not removed')
    if any(libc.prctl(23, capability, 0, 0, 0) != 0 for capability in range(41)):
        raise RuntimeError('capability bounding set is not empty')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    resource.setrlimit(resource.RLIMIT_NOFILE, (1024, 1024))
    resource.setrlimit(resource.RLIMIT_NPROC, (128, 128))
    resource.setrlimit(resource.RLIMIT_FSIZE, (128 * 1024 * 1024,) * 2)
    resource.setrlimit(resource.RLIMIT_CPU, (600, 600))
    return {'capabilities': 0, 'bounding_capabilities': 0, 'no_new_privileges': True,
            'seccomp': True, 'proc_view': 'only_this_cli_process_read_only'}


class UnixConnection(http.client.HTTPConnection):
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/run/model.sock')


class Relay(http.server.BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    def log_message(self, *args):
        pass
    def handle_request(self):
        connection = UnixConnection('broker', timeout=180)
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 32 * 1024 * 1024:
                raise ValueError('body too large')
            body = self.rfile.read(size) if size else None
            headers = {key: value for key, value in self.headers.items()
                       if key.lower() not in {'host', 'connection', 'transfer-encoding'}}
            connection.request(self.command, self.path, body=body, headers=headers)
            response = connection.getresponse()
            self.send_response(response.status)
            for key, value in response.getheaders():
                if key.lower() not in {'transfer-encoding', 'connection', 'content-length'}:
                    self.send_header(key, value)
            self.send_header('Connection', 'close')
            self.end_headers()
            while chunk := response.read1(65536):
                self.wfile.write(chunk)
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            self.close_connection = True
            connection.close()
    do_GET = handle_request
    do_POST = handle_request


def main():
    settings = json.loads(Path('/run/stage.json').read_text())
    enable_loopback()
    ready_read,ready_write=os.pipe()
    go_read,go_write=os.pipe()
    child=os.fork()
    if child==0:
        try:
            os.close(ready_read);os.close(go_write)
            mount_own_process()
            receipt=restrict_process()
            Path('/home/runner/isolation.json').write_text(json.dumps(receipt))
            os.write(ready_write,b'1');os.close(ready_write)
            if os.read(go_read,1)!=b'1':raise RuntimeError('trusted relay did not start')
            os.close(go_read)
            os.execvpe(settings['command'][0],settings['command'],{**os.environ,**settings.get('env',{})})
        except BaseException as exc:
            print('Trusted sandbox setup failed: '+type(exc).__name__+': '+str(exc),file=sys.stderr,flush=True)
            os._exit(125)
    os.close(ready_write);os.close(go_read)
    if os.read(ready_read,1)!=b'1':
        os.close(ready_read);os.close(go_write)
        os.waitpid(child,0)
        return 125
    os.close(ready_read)
    restrict_process()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 18081), Relay)
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        os.write(go_write,b'1');os.close(go_write)
        _,status=os.waitpid(child,0)
        return os.waitstatus_to_exitcode(status)
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    sys.exit(main())
