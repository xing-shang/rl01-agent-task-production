"""Keep the local connection alive across headers, bodies and all 11 attempts."""
from __future__ import annotations
import hashlib
import email.utils
import http.server
import json
import queue
import random
import threading
import time
import urllib.error
import urllib.request
import uuid

from vps_request_proxy import ProxyConfig, IncompleteResponse, validate_response, error_detail


def make_server(bind, port, config: ProxyConfig):
    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version='HTTP/1.1'
        def log_message(self,*args):pass
        def reply(self,status,body,content_type='application/json'):
            try:
                self.send_response(status);self.send_header('Content-Type',content_type)
                self.send_header('Content-Length',str(len(body)));self.send_header('Connection','close');self.end_headers()
                self.wfile.write(body);self.wfile.flush()
                return True,None
            except OSError as exc:return False,type(exc).__name__
            finally:self.close_connection=True
        def chunk(self,body):
            self.wfile.write(f'{len(body):X}\r\n'.encode());self.wfile.write(body);self.wfile.write(b'\r\n');self.wfile.flush()
        def do_GET(self):
            self.reply(200,json.dumps({'status':'ready','max_attempts':config.max_attempts}).encode()) if self.path=='/health' else self.reply(404,b'{"error":"unsupported_path"}')
        def do_POST(self):
            supplied=self.headers.get('x-api-key') or self.headers.get('Authorization','').removeprefix('Bearer ')
            if supplied!=config.client_token:self.reply(401,b'{"error":"proxy_auth_failed"}');return
            path=self.path.split('?')[0]
            if path not in {'/v1/messages','/v1/messages/count_tokens'}:self.reply(404,b'{"error":"unsupported_path"}');return
            try:
                n=int(self.headers.get('Content-Length','0'))
                if not 0<n<=32*1024**2:raise ValueError('body_size')
                payload=json.loads(self.rfile.read(n))
                if path=='/v1/messages' and config.effort is not None:payload.setdefault('output_config',{})['effort']=config.effort
                body=json.dumps(payload,ensure_ascii=False,separators=(',',':')).encode()
            except (ValueError,TypeError,AttributeError):self.reply(400,b'{"error":"invalid_request"}');return
            stream=payload.get('stream') is True and path=='/v1/messages'
            headers={k:v for k,v in self.headers.items() if k.lower() not in {'authorization','x-api-key','host','content-length','connection','accept-encoding'}}
            headers.update({'Authorization':'Bearer '+config.token,'x-api-key':config.token,'Content-Type':'application/json','Accept-Encoding':'identity'})
            base={'logical_request_id':str(uuid.uuid4()),'stage':config.stage,'task_digest':config.task_digest,'model':payload.get('model'),
                  'payload_hash':hashlib.sha256(body).hexdigest(),'effort':config.effort,'max_in_flight':config.max_in_flight}
            result=queue.Queue(maxsize=1);cancel=threading.Event()
            def worker():
                with config.request_slot():
                    for attempt in range(config.max_attempts):
                        if cancel.is_set():return
                        started=time.time();status=None;retry_after=0;error=detail=None;configuration_error=False
                        try:
                            request=urllib.request.Request(config.upstream.rstrip('/')+self.path,data=body,headers=headers,method='POST')
                            with urllib.request.urlopen(request,timeout=config.timeout) as response:
                                status=response.status;content_type=response.headers.get('Content-Type','application/json')
                                response_body=response.read()
                            validation=validate_response(response_body,content_type,self.path)
                            if stream and 'text/event-stream' not in content_type:
                                raise IncompleteResponse('unexpected_stream_content_type')
                            record={**base,'attempt_index':attempt,'retry_index':attempt,'http_status':status,'started_at':started,'ended_at':time.time(),
                                    'backoff_seconds':0,'final_status':'SUCCESS',**validation}
                            result.put({'body':response_body,'record':record});return
                        except urllib.error.HTTPError as exc:
                            status=exc.code;error='http_error';configuration_error=status!=429 and not 500<=status<600
                            try:retry_after=max(0,float(exc.headers.get('Retry-After','0')))
                            except (ValueError,TypeError):
                                try:retry_after=max(0,email.utils.parsedate_to_datetime(exc.headers.get('Retry-After','')).timestamp()-time.time())
                                except (ValueError,TypeError):retry_after=0
                            finally:exc.close()
                        except Exception as exc:
                            error=str(exc) if isinstance(exc,IncompleteResponse) else type(exc).__name__;detail=error_detail(exc)
                        exhausted=attempt+1==config.max_attempts
                        delay=0 if exhausted or configuration_error else max(retry_after,min(60,2**min(attempt,6)+random.random()))*config.backoff_scale
                        record={**base,'attempt_index':attempt,'retry_index':attempt,'http_status':status,'error_type':error,'started_at':started,'ended_at':time.time(),
                                'terminal_complete':False,'backoff_seconds':delay,'final_status':'CONFIGURATION_ERROR' if configuration_error else 'REQUEST_FAILED' if exhausted else 'RETRY'}
                        if detail:record['error_detail']=detail
                        config.record(record)
                        if exhausted or configuration_error:
                            message='upstream HTTP '+str(status) if configuration_error else 'RL01_REQUEST_RETRY_BUDGET_EXHAUSTED; inspect private request audit'
                            value={'type':'error','error':{'type':'invalid_request_error','message':message}}
                            error_body=('event: error\ndata: '+json.dumps(value)+'\n\n').encode() if stream else json.dumps(value).encode()
                            result.put({'body':error_body,'record':None});return
                        if cancel.wait(delay):return
            threading.Thread(target=worker,daemon=True).start()
            # Comments/whitespace contain no model output. The actual response
            # is released once, only after complete upstream validation.
            self.send_response(200);self.send_header('Content-Type','text/event-stream' if stream else 'application/json')
            self.send_header('Transfer-Encoding','chunked');self.send_header('Connection','close');self.end_headers()
            heartbeat=b': rl01-keepalive\n\n' if stream else b'\n'
            try:
                self.chunk(heartbeat)
                while True:
                    try:value=result.get(timeout=config.sse_keepalive_interval)
                    except queue.Empty:self.chunk(heartbeat);continue
                    try:
                        self.chunk(value['body']);self.wfile.write(b'0\r\n\r\n');self.wfile.flush()
                    except OSError as exc:
                        if value['record']:
                            value['record'].update(delivery_status='FAILED',delivery_error=type(exc).__name__);config.record(value['record'])
                        raise
                    else:
                        if value['record']:
                            value['record']['delivery_status']='SUCCESS';config.record(value['record'])
                    break
            except OSError:
                cancel.set()
                config.record({**base,'final_status':'DELIVERY_FAILED','error_type':'downstream_closed','terminal_complete':False,'ended_at':time.time()})
            finally:self.close_connection=True
    server=http.server.ThreadingHTTPServer((bind,port),Handler);server.daemon_threads=True
    return server
