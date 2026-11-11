"""Bounded, short-lived image jobs for the headless service; never imports Qt."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import stat
import subprocess
import sys
import tempfile
import threading
import time

MAX_MESSAGE = 131_072
_TIMEOUTS = {'dimensions': 15, 'cache_poster': 30, 'cache_discovery_cover': 90}
_FIELDS = {'dimensions': {'path', 'modified', 'size'},
           'cache_poster': {'path', 'directory'},
           'cache_discovery_cover': {'directory', 'work_id', 'poster_only'}}
_slots = threading.BoundedSemaphore(2)
_shutdown_event = None


def should_isolate():
    return os.environ.get('LUMEN_BACKGROUND_SERVICE') == '1' and os.environ.get('LUMEN_IMAGE_WORKER') != '1'


def register_shutdown_event(event):
    """The service registers its stop Event before accepting image requests."""
    if event is not None and not callable(getattr(event, 'is_set', None)):
        raise TypeError('Expected a shutdown Event')
    global _shutdown_event
    _shutdown_event = event


def _check_cancelled(cancelled):
    if (_shutdown_event is not None and _shutdown_event.is_set()) or (cancelled is not None and cancelled()):
        from .core import ImportCancelled
        raise ImportCancelled('图片任务已停止')


def validate_request(request):
    """A closed operation schema; no callable names, URLs, commands or work dicts."""
    if not isinstance(request, dict) or type(request.get('op')) is not str or request['op'] not in _FIELDS:
        raise ValueError('无效图片任务')
    op = request['op']
    if set(request) != {'op', *_FIELDS[op]}:
        raise ValueError('无效图片任务参数')
    for key in ('path', 'directory'):
        if key in request:
            value = request[key]
            if not isinstance(value, str) or not value or len(value) > 32768 or '\0' in value or not Path(value).is_absolute():
                raise ValueError('无效图片任务路径')
    if op == 'dimensions':
        if type(request['modified']) is not int or not -2**63 <= request['modified'] <= 2**63 - 1 or type(request['size']) is not int or not 0 <= request['size'] <= 2**63 - 1:
            raise ValueError('无效图片版本')
    elif op == 'cache_discovery_cover':
        if type(request['work_id']) is not int or not 0 < request['work_id'] <= 2**63 - 1 or type(request['poster_only']) is not bool:
            raise ValueError('无效封面任务')
    return request


def _command(request, response):
    command = [sys.executable, '--image-worker'] if getattr(sys, 'frozen', False) else [sys.executable, '-m', 'lumen.image_worker', '--image-worker']
    return [*command, '--request', str(request), '--response', str(response)]


def _environment():
    environment = os.environ.copy()
    environment.pop('LUMEN_BACKGROUND_SERVICE', None)
    environment['LUMEN_IMAGE_WORKER'] = '1'
    environment.setdefault('QT_QPA_PLATFORM', 'offscreen')
    if not getattr(sys, 'frozen', False):
        source = str(Path(__file__).resolve().parent.parent)
        environment['PYTHONPATH'] = source + (os.pathsep + environment['PYTHONPATH'] if environment.get('PYTHONPATH') else '')
    return environment


def _terminate(process):
    """Also stop a plugin's transient HTTP worker when its image job is cancelled."""
    if process.poll() is not None:
        return
    try:
        if os.name == 'nt':
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=2, creationflags=0x08000000, check=False)
        else:
            os.killpg(process.pid, signal.SIGTERM)
    except (OSError, subprocess.TimeoutExpired):
        process.terminate()
    try:
        process.wait(timeout=.5)
    except subprocess.TimeoutExpired:
        try:
            if os.name != 'nt': os.killpg(process.pid, signal.SIGKILL)
            else: process.kill()
        except ProcessLookupError:
            pass
        process.wait(timeout=2)


def _read_response(path, op):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_MESSAGE:
        raise RuntimeError('图片任务未返回有效结果')
    try:
        response = read_message(path)
    except (OSError, UnicodeError, ValueError):
        raise RuntimeError('图片任务未返回有效结果') from None
    if not isinstance(response, dict) or type(response.get('ok')) is not bool:
        raise RuntimeError('图片任务未返回有效结果')
    if not response['ok']:
        error = response.get('error')
        if not isinstance(error, dict):raise RuntimeError('图片任务未返回有效结果')
        # Messages are fixed on both sides; never echo a decoder/OS/URL exception.
        kind = error.get('type')
        if kind == 'PosterPathError':
            from .artwork import PosterPathError
            raise PosterPathError('海报路径无效')
        if kind == 'OSError':raise OSError('图片文件读取失败')
        if kind == 'ValueError':raise ValueError('图片资料无效或无法解码')
        raise RuntimeError('后台图片处理失败')
    value = response.get('result')
    if op == 'dimensions':
        if not isinstance(value, list) or len(value) != 2 or any(type(item) is not int or not -1 <= item <= 2**31 - 1 for item in value):
            raise RuntimeError('图片任务返回无效尺寸')
        return tuple(value)
    if value is not None and (not isinstance(value, str) or not value or len(value) > 32768 or not Path(value).is_absolute()):
        raise RuntimeError('图片任务返回无效缓存')
    return value


def read_message(path):
    descriptor=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    with os.fdopen(descriptor,'rb') as source:
        details=os.fstat(source.fileno())
        if not stat.S_ISREG(details.st_mode) or details.st_size>MAX_MESSAGE:
            raise ValueError('图片任务参数过大')
        raw=source.read(MAX_MESSAGE+1)
        if len(raw)>MAX_MESSAGE:raise ValueError('图片任务参数过大')
        return json.loads(raw.decode('utf-8'))


def run_image_operation(op, *, timeout=None, cancelled=None, **arguments):
    request = validate_request({'op': op, **arguments})
    limit = _TIMEOUTS[op] if timeout is None else timeout
    if type(limit) not in (int, float) or not 0 < limit <= 180:
        raise ValueError('无效图片任务时限')
    encoded = json.dumps(request, ensure_ascii=False).encode('utf-8')
    if len(encoded) > MAX_MESSAGE:raise ValueError('图片任务参数过大')
    deadline = time.monotonic() + limit
    _check_cancelled(cancelled)
    while not _slots.acquire(timeout=min(.05, max(0, deadline-time.monotonic()))):
        _check_cancelled(cancelled)
        if time.monotonic() >= deadline:raise TimeoutError('后台图片处理超时')
    try:
        _check_cancelled(cancelled)
        if time.monotonic() >= deadline:raise TimeoutError('后台图片处理超时')
        with tempfile.TemporaryDirectory(prefix='lumen-image-') as temporary:
            folder=Path(temporary);source=folder/'request.json';target=folder/'response.json'
            descriptor=os.open(source,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
            with os.fdopen(descriptor,'wb') as output:output.write(encoded)
            try:
                process=subprocess.Popen(_command(source,target), stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                         stderr=subprocess.DEVNULL, env=_environment(), start_new_session=os.name!='nt',
                                         creationflags=(0x08000000|0x00000200) if os.name=='nt' else 0)
            except OSError:
                raise RuntimeError('后台图片处理进程无法启动') from None
            try:
                while process.poll() is None:
                    _check_cancelled(cancelled)
                    if time.monotonic() >= deadline:raise TimeoutError('后台图片处理超时')
                    try:process.wait(timeout=min(.05,max(.001,deadline-time.monotonic())))
                    except subprocess.TimeoutExpired:pass
                _check_cancelled(cancelled)
                if process.returncode != 0:raise RuntimeError('后台图片处理进程异常退出')
                return _read_response(target,op)
            finally:
                _terminate(process)
    finally:
        _slots.release()
