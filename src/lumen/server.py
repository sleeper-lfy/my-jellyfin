"""Authenticated LAN API and byte-range streaming for the companion Android client."""
from __future__ import annotations
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs
import hmac
import json
import logging
import math
import mimetypes
import random
import re
import secrets
import socket
import threading
import time
import uuid
from .core import Library, now


class ApiError(Exception):
    def __init__(self, status, message):
        self.status, self.message = status, message


def ensure_token(library):
    token = library.setting('lan_token')
    if not token:
        token = secrets.token_urlsafe(32)
        library.set_setting('lan_token', token)
    return token


def local_addresses():
    addresses = {'127.0.0.1'}
    try:
        addresses.update(row[4][0] for row in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET))
    except OSError:
        pass
    return sorted(addresses)


def parse_range(value, size):
    if not value:
        return 0, size-1, 200
    match = re.fullmatch(r'bytes=(\d*)-(\d*)', value.strip())
    if not match or not any(match.groups()) or size == 0:
        raise ApiError(416, '无效 Range 请求')
    left, right = match.groups()
    if not left:
        count = int(right)
        if count <= 0:
            raise ApiError(416, '无效后缀范围')
        return max(0, size-count), size-1, 206
    start, end = int(left), min(int(right) if right else size-1, size-1)
    if start >= size or end < start:
        raise ApiError(416, '请求范围超出文件')
    return start, end, 206


def public_work(work, detail=False):
    result = {key: work[key] for key in ['id','kind','title','year','rating','favorite','watchlist','disliked','added']}
    result.update(cover=f"/api/works/{work['id']}/cover" if work['thumbnail'] else None,
                  file_count=len(work['files']), tags=work['metadata'].get('tags', []),
                  position=max((f['position'] for f in work['files']),default=0))
    if detail:
        result.update(overview=work['metadata'].get('overview',''),
                      actors=[{k:a[k] for k in ['name','gender','aliases'] if k in a} for a in work['metadata'].get('actors',[])],
                      sources=[{k:s[k] for k in ['site','url','rating']} for s in work['sources']],
                      files=[{**{k:f[k] for k in ['id','season','episode','duration','position','completed']},
                              'name':f.get('title') or Path(f['path']).name,'stream':f"/api/files/{f['id']}/stream"} for f in work['files']])
    return result


class LanServer:
    def __init__(self, directory, host='0.0.0.0', port=8097, clock=time.monotonic):
        self.directory, self.host, self.port, self.clock = Path(directory), host, port, clock
        lib = Library(directory)
        self.token = ensure_token(lib)
        lib.close()
        self.lock = threading.RLock()
        self.sessions = {}
        self.http = None
        self.thread = None

    def start(self):
        if self.http:
            return
        service = self
        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'
            server_version = 'LumenLAN/1'
            sys_version = ''

            def setup(self):
                super().setup()
                self.connection.settimeout(25)

            def log_message(self, *_):
                pass  # Never log auth headers or URLs containing user search terms.

            def send_json(self, status, value):
                data = json.dumps(value, ensure_ascii=False, allow_nan=False).encode('utf-8')
                self.send_response(status)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Content-Length',str(len(data)))
                self.send_header('Cache-Control','no-store')
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Connection','close')
                self.end_headers()
                if self.command != 'HEAD':
                    self.wfile.write(data)
                self.close_connection = True

            def do_GET(self): self.dispatch()
            def do_HEAD(self): self.dispatch()
            def do_POST(self): self.dispatch()

            def dispatch(self):
                library = None
                try:
                    supplied = self.headers.get('Authorization','')
                    if not hmac.compare_digest(supplied.encode(), ('Bearer '+service.token).encode()):
                        raise ApiError(401,'访问密钥不正确，请在电脑端设置中查看')
                    parts = urlsplit(self.path)
                    query = parse_qs(parts.query)
                    path = parts.path
                    library = Library(service.directory)
                    body = {}
                    if self.command == 'POST':
                        length = int(self.headers.get('Content-Length','0'))
                        if not 0 < length <= 16384 or self.headers.get('Transfer-Encoding'):
                            raise ApiError(413,'请求内容大小无效')
                        body = json.loads(self.rfile.read(length))
                        if not isinstance(body,dict): raise ApiError(400,'请求内容须为对象')
                    if self.command in {'GET','HEAD'}:
                        if path == '/api/info':
                            return self.send_json(200,{'name':'Lumen','api_version':1,'streaming':'direct','server_time':now()})
                        if path in {'/api/works','/api/recommendations'}:
                            filters = self.filters(query)
                            items = library.query(filters) if path == '/api/works' else library.recommendations()
                            offset = max(0,int(query.get('offset',['0'])[0])); limit=max(1,min(100,int(query.get('limit',['40'])[0])))
                            return self.send_json(200,{'total':len(items),'items':[public_work(w) for w in items[offset:offset+limit]],'offset':offset,'limit':limit})
                        if path == '/api/stats':
                            return self.send_json(200,library.stats())
                        match = re.fullmatch(r'/api/works/(\d+)(/cover)?',path)
                        if match:
                            work = library.work(int(match[1]))
                            if match[2]:
                                if not work['thumbnail']:raise ApiError(404,'暂无封面')
                                target=Path(work['thumbnail']).resolve()
                                if not target.is_relative_to((service.directory/'cache').resolve()):raise ApiError(403,'封面路径不在缓存内')
                                return self.send_file(target,'image/jpeg')
                            result=public_work(work,True)
                            result['resume_file_id']=library.resume_file(work['id'])['id'] if work['files'] else None
                            return self.send_json(200,result)
                        match = re.fullmatch(r'/api/files/(\d+)/(stream|subtitles)(?:/(\d+))?',path)
                        if match:
                            file=self.file(library,int(match[1])); target=Path(file['path']).resolve()
                            if match[2]=='stream' and match[3] is None:
                                return self.send_file(target,mimetypes.guess_type(target.name)[0] or 'application/octet-stream')
                            subtitles=sorted(p for p in target.parent.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() in {'.srt','.vtt','.ass','.ssa'} and (p.stem==target.stem or p.name.startswith(target.stem+'.')))
                            types={'.srt':'application/x-subrip','.vtt':'text/vtt','.ass':'text/x-ssa','.ssa':'text/x-ssa'}
                            if match[3] is not None:
                                index=int(match[3])
                                if index>=len(subtitles):raise ApiError(404,'字幕不存在')
                                return self.send_file(subtitles[index],types[subtitles[index].suffix.lower()])
                            return self.send_json(200,{'items':[{'name':p.name,'mime':types[p.suffix.lower()],'url':f'/api/files/{file["id"]}/subtitles/{i}'} for i,p in enumerate(subtitles)]})
                    else:
                        if path == '/api/queue':
                            filters=self.filters({k:[str(v)] for k,v in body.items() if k in {'kind','q','favorite'}})
                            ids=[w['id'] for w in library.query(filters)]
                            random.SystemRandom().shuffle(ids)
                            return self.send_json(200,{'ids':ids})
                        match=re.fullmatch(r'/api/works/(\d+)/personal',path)
                        if match:
                            library.work(int(match[1]))
                            if not body or not body.keys()<={'rating','favorite','watchlist','disliked'}:raise ApiError(400,'无效个人字段')
                            for key in ['favorite','watchlist','disliked']:
                                if key in body and type(body[key]) is not bool:raise ApiError(400,'标记须为布尔值')
                            library.update_personal(int(match[1]),**body)
                            return self.send_json(200,{'ok':True})
                        if path == '/api/playback/start':
                            file=self.file(library,int(body.get('file_id',0)))
                            with service.lock:
                                service.expire(library)
                                if len(service.sessions)>=128:raise ApiError(429,'活动播放会话过多')
                                session=uuid.uuid4().hex
                                with library.db:library.db.execute('INSERT INTO sessions(id,file_id,started) VALUES (?,?,?)',(session,file['id'],now()))
                                service.sessions[session]={'file_id':file['id'],'time':service.clock(),'position':file['position'],'playing':False,'seq':-1,'duration':file['duration']}
                            return self.send_json(200,{'session_id':session})
                        match=re.fullmatch(r'/api/playback/([a-f0-9]{32})/(tick|stop)',path)
                        if match:
                            return self.send_json(200,service.tick(library,match[1],body,match[2]=='stop'))
                    raise ApiError(404,'接口不存在')
                except ApiError as exc:
                    self.send_json(exc.status,{'error':exc.message})
                except (ValueError,TypeError,KeyError,OverflowError):
                    self.send_json(400,{'error':'请求参数无效或媒体不存在'})
                except (BrokenPipeError,ConnectionResetError,TimeoutError):
                    pass
                except FileNotFoundError:
                    self.send_json(404,{'error':'文件离线或已移动'})
                except Exception:
                    logging.exception('LAN request failed')
                    self.send_json(500,{'error':'服务端处理失败，请查看电脑端日志'})
                finally:
                    if library: library.close()

            def filters(self,query):
                filters={'query':query.get('q',[''])[0]}
                kind=query.get('kind',[''])[0]
                if kind:
                    if kind not in {'movie','series','other'}:raise ApiError(400,'无效媒体类型')
                    filters['kinds']=[kind]
                if query.get('favorite',[''])[0].lower() in {'true','1'}:filters['favorite']=True
                return filters

            def file(self,library,file_id):
                row=library.db.execute('SELECT * FROM files WHERE id=?',(file_id,)).fetchone()
                if not row:raise ApiError(404,'媒体文件不存在')
                target=Path(row['path']).resolve()
                if not target.is_relative_to(Path(row['root']).resolve()):raise ApiError(403,'文件不在媒体目录内')
                if not target.is_file():raise ApiError(404,'媒体文件离线')
                return dict(row)

            def send_file(self,path,mime):
                with path.open('rb') as stream:
                    size=path.stat().st_size
                    try:
                        start,end,status=parse_range(self.headers.get('Range'),size)
                    except ApiError:
                        self.send_response(416)
                        self.send_header('Content-Range',f'bytes */{size}')
                        self.send_header('Content-Length','0')
                        self.send_header('Connection','close')
                        self.end_headers();self.close_connection=True
                        return
                    self.send_response(status)
                    self.send_header('Content-Type',mime)
                    self.send_header('Accept-Ranges','bytes')
                    self.send_header('Content-Length',str(max(0,end-start+1)))
                    self.send_header('X-Content-Type-Options','nosniff')
                    self.send_header('Cache-Control','private, max-age=300' if mime.startswith('image/') else 'no-store')
                    self.send_header('Connection','close')
                    if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
                    self.end_headers();self.close_connection=True
                    if self.command=='HEAD':return
                    stream.seek(start);remaining=end-start+1
                    while remaining>0:
                        data=stream.read(min(256*1024,remaining))
                        if not data:break
                        self.wfile.write(data);remaining-=len(data)

        self.http=ThreadingHTTPServer((self.host,self.port),Handler)
        self.http.daemon_threads=True
        self.port=self.http.server_port
        self.thread=threading.Thread(target=self.http.serve_forever,name='LumenLAN',daemon=True)
        self.thread.start()

    def expire(self,library):
        expired=[key for key,s in self.sessions.items() if self.clock()-s['time']>3600]
        for key in expired:
            with library.db:library.db.execute('UPDATE sessions SET ended=? WHERE id=?',(now(),key))
            self.sessions.pop(key)

    def tick(self,library,key,body,stop=False):
        with self.lock:
            self.expire(library)
            state=self.sessions.get(key)
            if state is None:raise ApiError(404,'播放会话已结束，请重新播放')
            position=float(body.get('position',0)); seq=int(body.get('seq',-1));rate=float(body.get('rate',1))
            if not math.isfinite(position) or not math.isfinite(rate) or not 0<=position<=state['duration']+10 or not .25<=rate<=4:
                raise ApiError(400,'播放位置或速度无效')
            if seq<=state['seq']:return {'ok':True,'duplicate':True}
            for field in ['playing','seeking','completed']:
                if field in body and type(body[field]) is not bool:raise ApiError(400,'播放状态须为布尔值')
            playing=body.get('playing',False)
            elapsed=self.clock()-state['time'];advance=position-state['position'];watched=0
            if state['playing'] and playing and not body.get('seeking') and 0<elapsed<=3 and 0<advance<=elapsed*rate+.6:
                watched=min(elapsed,advance/rate)
            with library.db:
                library.db.execute('UPDATE sessions SET watched=watched+? WHERE id=?',(watched,key))
                if watched:
                    library.db.execute('INSERT INTO activity VALUES (?,?,?) ON CONFLICT(session_id,day) DO UPDATE SET watched=watched+excluded.watched',(key,datetime.now().date().isoformat(),watched))
                completed=bool(body.get('completed') and state['duration']>0 and position>=state['duration']-3)
                library.db.execute('UPDATE files SET position=?,completed=? WHERE id=?',(0 if completed else position,int(completed),state['file_id']))
                if stop:library.db.execute('UPDATE sessions SET ended=? WHERE id=?',(now(),key))
            state.update(time=self.clock(),position=position,playing=playing,seq=seq)
            if stop:self.sessions.pop(key,None)
            return {'ok':True}

    def stop(self):
        if self.http:
            self.http.shutdown();self.http.server_close();self.thread.join(timeout=5)
            self.http=None
            library=Library(self.directory)
            with self.lock,library.db:
                for key in self.sessions:library.db.execute('UPDATE sessions SET ended=? WHERE id=?',(now(),key))
                self.sessions.clear()
            library.close()
