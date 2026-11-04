"""Trusted, optional Javinizer-Go queries. No server, browser or second library DB."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlparse
import uuid

import httpx

from .core import check_cancelled, ImportCancelled


ENGINE_ID = 'javinizer-go'
CONFIG_KEY = 'plugin:' + ENGINE_ID
VERSION = '1.6.6'
ASSET = 'javinizer-windows-amd64.exe'
DOWNLOAD_URL = f'https://github.com/javinizer/javinizer-go/releases/download/v{VERSION}/{ASSET}'
SHA256 = '762a81d660438c4abd83fbd0bf7a31374803b8f4d0d09381127e6b65d12e3004'
BINARY_SIZE = 59_761_664
MAX_OUTPUT = 4 * 1024 * 1024
MAX_STDERR = 256 * 1024
CACHE_PREFIX = 'javinizer-cache:'
CACHE_VERSION = 1
MAX_CACHE_BYTES = 8 * 1024 * 1024
MAX_CACHE_ENTRIES = 256

SOURCES = {
    'r18dev': ('R18.dev', ('r18.dev',)),
    'libredmm': ('LibreDMM', ('www.libredmm.com', 'libredmm.com')),
    'javbus': ('JavBus', ('www.javbus.com', 'javbus.com')),
    'javdb': ('JavDB', ('javdb.com', 'www.javdb.com')),
    'jav321': ('Jav321', ('jp.jav321.com', 'www.jav321.com', 'jav321.com')),
    'fc2': ('FC2', ('adult.contents.fc2.com', 'contents.fc2.com')),
}
DEFAULT_SOURCES = ['r18dev', 'libredmm', 'javbus']
ALL_SCRAPERS = (*SOURCES, 'dmm', 'mgstage', 'javlibrary', 'tokyohot',
                'aventertainment', 'dlgetchu', 'caribbeancom', 'javstash')
IMAGE_HOSTS = ('pics.dmm.co.jp', 'awsimgsrc.dmm.com', 'awsimgsrc.dmm.co.jp', 'pics.r18.com',
               'pics.javbus.com', 'www.javbus.com', 'c0.jdbstatic.com',
               'c1.jdbstatic.com', 'c2.jdbstatic.com', 'c3.jdbstatic.com',
               'img.jav321.com', 'www.libredmm.com', 'contents-thumbnail2.fc2.com',
               'contents-thumbnail.fc2.com')
DOMAINS = sorted({host for _, hosts in SOURCES.values() for host in hosts} | set(IMAGE_HOSTS))
_query_lock = threading.Lock()
LICENSE_TEXT = '''MIT License

Copyright (c) 2026 Javinizer contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
'''


def settings(library):
    return {'enabled': False, 'configured': False, 'sources': DEFAULT_SOURCES.copy(),
            'timeout': 60, 'cache_hours': 168, 'proxy': 'inherit', 'priority': 50,
            **library.setting(CONFIG_KEY, {})}


def provider(library):
    config = settings(library)
    if not config['configured']:
        return None
    return {'id': ENGINE_ID, 'name': 'Javinizer-Go · 番号刮削（按需运行）',
            'version': VERSION, 'api_version': 1, 'engine': ENGINE_ID,
            'description': '按番号查询影片，失败时依次尝试来源；任务结束后退出。',
            'capabilities': ['search'], 'search_filters': ['name'],
            'media_kinds': ['movie', 'vr'],
            'input_hint': '输入影片番号，例如 IPX-535 或 FC2-PPV-1234567',
            'domains': DOMAINS.copy(), 'config': config}


def save_settings(library, values):
    config = {**settings(library), **values, 'configured': True}
    selected = config['sources']
    if not isinstance(selected, list) or not selected or len(set(selected)) != len(selected) or any(s not in SOURCES for s in selected):
        raise ValueError('请按顺序选择至少一个支持的刮削来源')
    for key, low, high in (('timeout', 15, 180), ('cache_hours', 0, 720), ('priority', 0, 999)):
        if type(config[key]) is not int or not low <= config[key] <= high:
            raise ValueError('无效引擎配置：' + key)
    resolve_proxy(library, config)
    library.set_setting(CONFIG_KEY, config)
    return config


def resolve_proxy(library, config):
    proxy = config.get('proxy', 'inherit')
    if proxy == 'inherit':
        proxy = library.setting('proxy', '')
    if not isinstance(proxy, str) or '\n' in proxy or '\r' in proxy:
        raise ValueError('无效代理地址')
    if proxy:
        parsed = urlparse(proxy)
        if parsed.scheme not in {'http', 'https', 'socks5', 'socks5h'} or not parsed.hostname:
            raise ValueError('代理须为完整的 HTTP、HTTPS 或 SOCKS5 地址')
    return proxy


def executable_path(library):
    return library.directory / 'engines' / ENGINE_ID / VERSION / 'javinizer.exe'


def _hash_file(path, cancelled=None):
    digest = hashlib.sha256()
    with Path(path).open('rb') as incoming:
        for block in iter(lambda: incoming.read(1024 * 1024), b''):
            check_cancelled(cancelled)
            digest.update(block)
    return digest.hexdigest()


def verified_executable(library, cancelled=None):
    path = executable_path(library)
    if not path.is_file():
        raise ValueError('尚未安装 Javinizer-Go，请在设置 → 按需刮削引擎中下载组件')
    if path.stat().st_size != BINARY_SIZE or _hash_file(path, cancelled) != SHA256:
        raise ValueError('Javinizer-Go 组件校验失败，请重新下载官方组件')
    return path


def _download_response(client):
    url = DOWNLOAD_URL
    allowed = {'github.com', 'release-assets.githubusercontent.com',
               'objects.githubusercontent.com', 'github-releases.githubusercontent.com'}
    for _ in range(6):
        parsed = httpx.URL(url)
        if parsed.scheme != 'https' or parsed.host not in allowed or parsed.username or parsed.password:
            raise ValueError('引擎下载只能来自 GitHub 官方 HTTPS 发布资产')
        response = client.send(client.build_request('GET', url, headers={
            'User-Agent': 'Lumen-Javinizer-Fetcher', 'Accept-Encoding': 'identity'}), stream=True)
        if response.is_redirect:
            location = response.headers.get('location')
            response.close()
            if not location:
                raise ValueError('引擎下载重定向缺少目标')
            url = str(parsed.join(location))
            continue
        try:
            response.raise_for_status()
        except BaseException:
            response.close()
            raise
        return response
    raise ValueError('引擎下载重定向次数过多')


def install(library, progress=None, cancelled=None, *, local_file=None):
    """Install the exact published binary; arbitrary local executables are rejected."""
    if sys.platform != 'win32':
        raise ValueError('当前按需引擎组件支持 Windows x64')
    check_cancelled(cancelled)
    target = executable_path(library)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    deadline = time.monotonic() + 1800
    try:
        with tempfile.NamedTemporaryFile(dir=target.parent, suffix='.part', delete=False) as output:
            temporary = Path(output.name)
            digest = hashlib.sha256()
            total = 0

            def copy(blocks):
                nonlocal total
                for block in blocks:
                    check_cancelled(cancelled)
                    if time.monotonic() > deadline:
                        raise TimeoutError('组件下载超过 30 分钟，请检查代理或选择已下载的官方组件')
                    total += len(block)
                    if total > BINARY_SIZE:
                        raise ValueError('引擎下载大小与官方资产不一致')
                    digest.update(block)
                    output.write(block)
                    if progress:
                        progress(total, BINARY_SIZE, '安装 Javinizer-Go ' + VERSION)

            if local_file is not None:
                with Path(local_file).open('rb') as incoming:
                    copy(iter(lambda: incoming.read(1024 * 1024), b''))
            else:
                proxy = resolve_proxy(library, settings(library))
                with httpx.Client(proxy=proxy or None, trust_env=False, timeout=httpx.Timeout(30, connect=10)) as client:
                    response = _download_response(client)
                    try:
                        copy(response.iter_bytes(16 * 1024))
                    finally:
                        response.close()
            output.flush()
            os.fsync(output.fileno())
        check_cancelled(cancelled)
        if total != BINARY_SIZE or digest.hexdigest() != SHA256:
            raise ValueError('Javinizer-Go SHA-256 校验失败，未替换现有组件')
        (target.parent / 'LICENSE.txt').write_text(LICENSE_TEXT, encoding='utf-8')
        temporary.replace(target)
        save_settings(library, {'enabled': True})
        return {'path': str(target), 'version': VERSION, 'sha256': SHA256}
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def movie_code(value):
    """Recognize one unambiguous identifier, including IDs embedded in filenames."""
    if not isinstance(value, str) or len(value) > 2000:
        raise ValueError('请输入一个影片番号')
    found = set()
    fc2 = re.compile(r'(?<![A-Za-z0-9])FC2[-_ ]*(?:PPV[-_ ]*)?(\d{5,9})(?!\d)', re.I)
    for match in fc2.finditer(value):
        found.add('FC2-PPV-' + str(int(match[1])))
    remainder = fc2.sub(' ', value)
    pattern = r'(?<![A-Za-z0-9])((?:\d{1,3})?[A-Za-z]{2,12}|[A-Za-z]\d{1,2})[-_ ](\d{2,8})(?!\d)'
    for match in re.finditer(pattern, remainder):
        found.add(match[1].upper() + '-' + str(int(match[2])).zfill(3))
    for match in re.finditer(r'(?<!\d)(\d{6})[-_](\d{2,4})(?!\d)', remainder):
        found.add(match[1] + '-' + match[2])
    if not found:
        match = re.fullmatch(r'\s*([A-Za-z]{2,12})(\d{3,8})\s*', value)
        if match:
            found.add(match[1].upper() + '-' + str(int(match[2])).zfill(3))
    if len(found) != 1:
        raise ValueError('未识别到唯一番号，请输入例如 IPX-535 或 FC2-PPV-1234567；不支持按片名搜索')
    return found.pop()


def work_query(work):
    for value in [work.get('metadata', {}).get('external_ids', {}).get('jav', ''),
                  work.get('title', ''), *[Path(f['path']).stem for f in work.get('files', [])]]:
        try:
            return movie_code(value)
        except ValueError:
            pass
    return work.get('title', '')


def _safe_url(value, hosts):
    if not isinstance(value, str) or len(value) > 4096:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {'https', 'http'} or parsed.hostname not in hosts or parsed.username or parsed.password:
        return None
    return value


def metadata(raw, source, code):
    if not isinstance(raw, dict) or raw.get('source') != source or not isinstance(raw.get('title'), str) or not raw['title'].strip():
        raise ValueError('引擎未返回有效的来源与标题')
    if movie_code(raw.get('id', '')) != code:
        raise ValueError('来源返回的番号与请求不一致，未采用该结果')
    url = _safe_url(raw.get('source_url'), SOURCES[source][1])
    if not url:
        raise ValueError('引擎返回的来源地址不属于所选站点')
    released = None
    try:
        released = date.fromisoformat(str(raw.get('release_date', ''))[:10]).isoformat()
    except ValueError:
        pass
    actors = []
    cast = raw.get('actresses') or []
    provenance = raw.get('cast_name_provenance') or []
    for index, actor in enumerate(cast[:100] if isinstance(cast, list) else []):
        if not isinstance(actor, dict):
            continue
        name = actor.get('japanese_name')
        evidence = provenance[index] if isinstance(provenance, list) and index < len(provenance) else {}
        if not name and isinstance(evidence, dict):
            name = evidence.get('display_name')
        roman = ' '.join(v.strip() for v in (actor.get('first_name'), actor.get('last_name')) if isinstance(v, str) and v.strip())
        name = name or roman
        if not isinstance(name, str) or not name.strip():
            continue
        actors.append({'name': name.strip()[:200], 'gender': 'unknown',
                       'aliases': [roman] if roman and roman != name else [],
                       'photo': _safe_url(actor.get('thumb_url'), IMAGE_HOSTS)})
    rating = raw.get('rating')
    score = rating.get('score') if isinstance(rating, dict) else None
    # LibreDMM passes its API's "review" through without declaring a scale.
    # Do not present an unverified five-point score as a ten-point rating.
    if source == 'libredmm':
        score = None
    if type(score) not in (int, float) or not 0 <= score <= 10:
        score = None
    original = raw.get('original_title')
    genres = raw.get('genres') or []
    screenshots = raw.get('screenshot_urls') or []
    content_id = raw.get('content_id')
    return {'id': code, 'title': raw['title'].strip()[:2000], 'kind': 'movie',
            'url': url, 'released': released, 'year': int(released[:4]) if released else None,
            'overview': raw.get('description', '')[:200000] if isinstance(raw.get('description'), str) else '',
            'aliases': list(dict.fromkeys([code] + ([original] if isinstance(original, str) and original else []))),
            'tags': list(dict.fromkeys(v[:200] for v in genres[:200] if isinstance(v, str))) if isinstance(genres, list) else [],
            'directors': [raw['director'][:200]] if isinstance(raw.get('director'), str) and raw['director'] else [],
            'actors': actors, 'poster': _safe_url(raw.get('poster_url'), IMAGE_HOSTS) or _safe_url(raw.get('cover_url'), IMAGE_HOSTS),
            'stills': [v for v in (_safe_url(v, IMAGE_HOSTS) for v in screenshots[:40]) if v] if isinstance(screenshots, list) else [],
            'rating': score, 'external_ids': {'jav': code, **({'dmm': content_id} if isinstance(content_id, str) and content_id else {})},
            'javinizer_source': source}


def engine_config(source, proxy, timeout):
    """JSON is valid YAML; use upstream defaults for unrelated required fields."""
    scrapers = {name: {'enabled': name == source, 'use_browser': False, 'use_flaresolverr': False,
                      'retry_count': 0, 'rate_limit': 1000,
                      'proxy': {'enabled': bool(proxy), 'profile': 'lumen'}} for name in ALL_SCRAPERS}
    scrapers[source]['language'] = 'ja'
    scrapers.update({'priority': [source], 'timeout_seconds': min(20, timeout),
                     'request_timeout_seconds': timeout, 'scrape_actress': False,
                     'browser': {'enabled': False}, 'flaresolverr': {'enabled': False},
                     'proxy': {'enabled': bool(proxy), 'default_profile': 'lumen',
                               'profiles': {'lumen': {'url': proxy}}}})
    return {'config_version': 3, 'scrapers': scrapers,
            'system': {'version_check_enabled': False, 'image_cache_enabled': False},
            'metadata': {'actress_database': {'enabled': False}, 'translation': {'enabled': False}},
            'logging': {'level': 'warn', 'output': 'stderr'}}


def _child_environment(directory):
    env = {k: v for k, v in os.environ.items()
           if not k.upper().startswith('JAVINIZER_') and k.upper() not in {'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'NO_PROXY'}}
    env.update({'JAVINIZER_HOME': str(directory), 'GOMEMLIMIT': '96MiB', 'GOMAXPROCS': '2'})
    return env


class _ProcessTree:
    """Kill descendants when the job ends, including on parent application exit."""
    def __init__(self, process):
        self.process = process
        self.handle = None
        if os.name != 'nt':
            return
        import ctypes
        from ctypes import wintypes
        class Basic(ctypes.Structure):
            _fields_ = [('user', ctypes.c_int64), ('job_user', ctypes.c_int64), ('flags', wintypes.DWORD),
                        ('minimum', ctypes.c_size_t), ('maximum', ctypes.c_size_t), ('active', wintypes.DWORD),
                        ('affinity', ctypes.c_size_t), ('priority', wintypes.DWORD), ('scheduling', wintypes.DWORD)]
        class IO(ctypes.Structure):
            _fields_ = [(n, ctypes.c_uint64) for n in ('read', 'write', 'other', 'read_bytes', 'write_bytes', 'other_bytes')]
        class Limits(ctypes.Structure):
            _fields_ = [('basic', Basic), ('io', IO), ('process_memory', ctypes.c_size_t),
                        ('job_memory', ctypes.c_size_t), ('peak_process', ctypes.c_size_t), ('peak_job', ctypes.c_size_t)]
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        self.kernel = kernel
        self.handle = kernel.CreateJobObjectW(None, None)
        limits = Limits()
        limits.basic.flags = 0x2000 | 0x200  # KILL_ON_JOB_CLOSE | JOB_MEMORY
        limits.job_memory = 256 * 1024 * 1024
        try:
            if not self.handle or not kernel.SetInformationJobObject(self.handle, 9, ctypes.byref(limits), ctypes.sizeof(limits)):
                raise ctypes.WinError(ctypes.get_last_error())
            if not kernel.AssignProcessToJobObject(self.handle, int(process._handle)):
                raise ctypes.WinError(ctypes.get_last_error())
        except BaseException:
            self.close()
            raise

    def close(self):
        if self.handle:
            self.kernel.CloseHandle(self.handle)
            self.handle = None
        elif os.name != 'nt':
            try:
                os.killpg(self.process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass


def run_process(command, directory, timeout, cancelled=None):
    check_cancelled(cancelled)
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(command, cwd=directory, env=_child_environment(directory),
                                   stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   creationflags=0x08000000 if os.name == 'nt' else 0,
                                   start_new_session=os.name != 'nt')
        tree = None
        try:
            tree = _ProcessTree(process)
            deadline = time.monotonic() + timeout
            while True:
                check_cancelled(cancelled)
                if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT or os.fstat(stderr.fileno()).st_size > MAX_STDERR:
                    raise ValueError('引擎输出超过大小上限')
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError(f'刮削超过 {timeout} 秒，已终止引擎进程')
                try:
                    process.wait(timeout=min(.1, remaining))
                    break
                except subprocess.TimeoutExpired:
                    pass
            if os.fstat(stdout.fileno()).st_size > MAX_OUTPUT or os.fstat(stderr.fileno()).st_size > MAX_STDERR:
                raise ValueError('引擎输出超过大小上限')
            stdout.seek(0)
            return process.returncode, stdout.read(MAX_OUTPUT).decode('utf-8-sig')
        finally:
            if tree is not None:
                tree.close()
            if process.poll() is None:
                process.kill()
            process.wait()


def _redact(message):
    return re.sub(r'(https?|socks5h?)://[^\s/@]+:[^\s/@]+@', r'\1://***@', str(message))[:800]


class SourceError(ValueError):
    def __init__(self, source, error):
        self.source = source
        self.kind = str(error.get('kind', 'unknown'))
        status = error.get('status_code')
        self.status = status if type(status) is int else 0
        host = SOURCES[source][1][0]
        hint = {401: '认证失效或站点要求登录', 403: '站点拒绝访问，请检查代理或更换来源',
                429: '站点限流，请稍后重试'}.get(self.status, _redact(error.get('message', '来源查询失败')))
        super().__init__(f'{SOURCES[source][0]}（{host}）' + (f' HTTP {self.status}' if self.status else '') + '：' + hint)


def query_source(library, executable, source, code, config, cancelled=None):
    with tempfile.TemporaryDirectory(prefix='query-', dir=executable.parent) as directory:
        path = Path(directory) / 'config.yaml'
        path.write_text(json.dumps(engine_config(source, resolve_proxy(library, config), config['timeout'])), encoding='utf-8')
        command = [str(executable), '--config', str(path), 'scrape', code, '--scrapers', source,
                   '--output', 'json', '--no-browser']
        returncode, output = run_process(command, directory, config['timeout'], cancelled)
    try:
        raw = json.loads(output)
    except (ValueError, TypeError):
        raise ValueError(f'{SOURCES[source][0]} 未返回有效 JSON（exit={returncode}）') from None
    if isinstance(raw, dict) and isinstance(raw.get('error'), dict):
        raise SourceError(source, raw['error'])
    if returncode:
        raise ValueError(f'{SOURCES[source][0]} 引擎异常退出（exit={returncode}）')
    return metadata(raw, source, code)


@contextmanager
def _single_query(cancelled):
    while not _query_lock.acquire(timeout=.1):
        check_cancelled(cancelled)
    try:
        check_cancelled(cancelled)
        yield
    finally:
        _query_lock.release()


def clear_cache(library):
    with library.db:
        count = library.db.execute('SELECT count(*) FROM settings WHERE key GLOB ?', (CACHE_PREFIX + '*',)).fetchone()[0]
        library.db.execute('DELETE FROM settings WHERE key GLOB ?', (CACHE_PREFIX + '*',))
        library.db.execute('DELETE FROM settings WHERE key GLOB ?', ('javinizer-cooldown:*',))
    return {'removed': count}


def _cache_result(library, source, code, record):
    key = CACHE_PREFIX + source + ':' + code
    with library.db:
        library.db.execute('INSERT OR REPLACE INTO settings VALUES (?,?)',
                           (key, json.dumps({'at': time.time(), 'version': CACHE_VERSION, 'record': record}, ensure_ascii=False)))
        rows = library.db.execute("SELECT key,length(CAST(value AS BLOB)),json_extract(value,'$.at') FROM settings WHERE key GLOB ? ORDER BY json_extract(value,'$.at') DESC,rowid DESC", (CACHE_PREFIX + '*',)).fetchall()
        used = 0
        for index, row in enumerate(rows):
            used += row[1]
            if index >= MAX_CACHE_ENTRIES or used > MAX_CACHE_BYTES or row[2] < time.time() - 30 * 86400:
                library.db.execute('DELETE FROM settings WHERE key=?', (row[0],))


def lookup(library, query, cancelled=None, progress=None):
    code = movie_code(query)
    config = settings(library)
    if not config['enabled']:
        raise ValueError('按需刮削引擎未启用')
    sources = config['sources']
    if not isinstance(sources, list) or not sources or any(source not in SOURCES for source in sources):
        raise ValueError('请在设置中重新选择刮削来源')
    errors = []
    with _single_query(cancelled):
        executable = None
        for index, source in enumerate(sources):
            check_cancelled(cancelled)
            if progress:
                progress(index, len(sources), '查询 ' + code + ' · ' + SOURCES[source][0])
            cached = library.setting(CACHE_PREFIX + source + ':' + code, {})
            if config['cache_hours'] and cached.get('version') == CACHE_VERSION and cached.get('at', 0) > time.time() - config['cache_hours'] * 3600:
                return [cached['record']]
            cooldown = library.setting('javinizer-cooldown:' + source, {})
            if cooldown.get('until', 0) > time.time():
                errors.append(cooldown['message'] + '（冷却中，可在设置中清除缓存后重试）')
                continue
            if executable is None:
                executable = verified_executable(library, cancelled)
            try:
                record = query_source(library, executable, source, code, config, cancelled)
                check_cancelled(cancelled)
                if config['cache_hours']:
                    _cache_result(library, source, code, record)
                return [record]
            except ImportCancelled:
                raise
            except Exception as error:
                if isinstance(error, SourceError) and error.kind == 'not_found':
                    continue
                message = _redact(error)
                if not isinstance(error, SourceError):
                    message = f'{SOURCES[source][0]}（{SOURCES[source][1][0]}）：' + message
                errors.append(message)
                if isinstance(error, SourceError) and error.status in {401, 403, 429}:
                    library.set_setting('javinizer-cooldown:' + source, {'until': time.time() + 300, 'message': message})
                library.task(uuid.uuid4().hex, 'scrape-source', 'failed',
                             {'plugin': ENGINE_ID, 'source': source, 'host': SOURCES[source][1][0], 'code': code}, error=message)
        if errors:
            raise ValueError('刮削来源未能完成查询：' + '；'.join(errors))
        return []


def cache_images(library, record, work_id, replace_nfo=False, cancelled=None):
    """Save metadata first, then fetch images without holding SQLite's writer lock."""
    from .plugins import Plugins
    from PySide6.QtCore import QByteArray, QBuffer, QIODevice, QSize, Qt, QSaveFile
    from PySide6.QtGui import QImageReader
    manager = Plugins(library)
    plugin = provider(library)
    work = library.work(work_id)
    jobs = [('poster', record.get('poster'), None)]
    jobs += [('actor', actor.get('photo'), actor.get('name')) for actor in work['metadata'].get('actors', [])]
    jobs += [('still', url, None) for url in record.get('stills', [])]
    deadline = time.monotonic() + 180
    for role, url, name in jobs:
        check_cancelled(cancelled)
        if not url:
            continue
        field = 'actors' if role == 'actor' else 'stills' if role == 'still' else 'poster'
        current = library.work(work_id)
        if field in current['locked'] or not replace_nfo and field in current['metadata'].get('nfo_fields', []):
            continue
        if role == 'poster':
            custom = library.setting(f'artwork_{work_id}', {}).get('poster')
            if custom and Path(custom).is_file() or not replace_nfo and current['metadata'].get('nfo_poster'):
                continue
        if time.monotonic() > deadline:
            library.task(uuid.uuid4().hex, 'image', 'partial', {'plugin': ENGINE_ID, 'work_id': work_id},
                         error='图片下载超过 180 秒，已保存影片资料；可再次刮削重试缺失图片')
            break
        try:
            path = library.directory / 'cache' / ('javinizer-' + hashlib.sha256(url.encode()).hexdigest() + '.jpg')
            if not path.is_file():
                data, content_type = manager.fetch(plugin, url, image=True)
                check_cancelled(cancelled)
                if not content_type.startswith('image/'):
                    raise ValueError('图片响应类型错误')
                buffer = QBuffer()
                buffer.setData(QByteArray(data))
                buffer.open(QIODevice.OpenModeFlag.ReadOnly)
                reader = QImageReader(buffer)
                reader.setAutoTransform(True)
                size = reader.size()
                if size.width() <= 0 or size.height() <= 0 or size.width() * size.height() > 40_000_000:
                    raise ValueError('图片无效或像素过大')
                reader.setScaledSize(size.scaled(QSize(1920, 1920), Qt.AspectRatioMode.KeepAspectRatio))
                picture = reader.read()
                output = QSaveFile(str(path))
                if picture.isNull() or not output.open(QIODevice.OpenModeFlag.WriteOnly) or not picture.save(output, 'JPG') or not output.commit():
                    raise ValueError('图片解码或保存失败')
            check_cancelled(cancelled)
            with library.db:
                library.db.execute('BEGIN IMMEDIATE')
                row = library.db.execute('SELECT metadata,locked FROM works WHERE id=?', (work_id,)).fetchone()
                if row is None or field in json.loads(row['locked']):
                    continue
                merged = json.loads(row['metadata'])
                if not replace_nfo and field in merged.get('nfo_fields', []):
                    continue
                if role == 'poster' and merged.get('poster') == url:
                    custom = library.setting(f'artwork_{work_id}', {}).get('poster')
                    if custom and Path(custom).is_file():
                        continue
                    if replace_nfo:
                        merged.pop('nfo_poster', None)
                    library.db.execute('UPDATE works SET thumbnail=? WHERE id=?', (str(path), work_id))
                elif role == 'actor':
                    for actor in merged.get('actors', []):
                        if actor.get('name') == name and actor.get('photo') == url:
                            actor['photo_cache'] = str(path)
                            actor['photo_revision'] = path.stem
                elif role == 'still' and url in merged.get('stills', []):
                    entries = {entry['url']: entry for entry in merged.get('stills_cache', []) if isinstance(entry, dict) and entry.get('url')}
                    entries[url] = {'url': url, 'path': str(path)}
                    merged['stills_cache'] = [entries[v] for v in merged['stills'] if v in entries]
                library.db.execute('UPDATE works SET metadata=? WHERE id=?', (json.dumps(merged, ensure_ascii=False), work_id))
        except ImportCancelled:
            raise
        except Exception as error:
            library.task(uuid.uuid4().hex, 'image', 'failed',
                         {'url': url, 'plugin': ENGINE_ID, 'role': role, 'work_id': work_id}, error=_redact(error))
