"""On-demand FFmpeg delivery: bundled and user installs win, missing tools are fetched once."""
import hashlib
import json
import os
import struct
import subprocess
import zipfile
from pathlib import Path
import httpx
from .core import data_directory, check_cancelled

# Pinned upstream essentials build; the rolling URL is a fallback checked by runtime smoke only.
SOURCES = (
    {'url': 'https://www.gyan.dev/ffmpeg/builds/packages/ffmpeg-9.0.2-essentials_build.zip',
     'sha256': '60f467265b1e312373dbcd92200c2618a74850f98d3d078e94296bb3fa2047ba'},
    {'url': 'https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip', 'sha256': None},
)
MEMBERS = ('ffmpeg.exe', 'ffprobe.exe')
MAX_ZIP = 512 * 1024 * 1024
MAX_MEMBER = 256 * 1024 * 1024
TOOLS = ('ffmpeg', 'ffprobe')


def install_directory():
    directory = data_directory() / 'ffmpeg'
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def needed():
    from .core import tool
    return any(tool(name) is None for name in TOOLS)


def missing_tools():
    from .core import tool
    return [name for name in TOOLS if tool(name) is None]


def client_for(proxy=None):
    return httpx.Client(proxy=proxy or None, timeout=httpx.Timeout(30, connect=10), follow_redirects=False)


def response(client, url):
    for _ in range(6):
        parsed = httpx.URL(url)
        if parsed.scheme != 'https' or parsed.host != 'www.gyan.dev':
            raise ValueError('FFmpeg 下载地址必须来自 www.gyan.dev HTTPS')
        request = client.build_request('GET', url, headers={'User-Agent': 'Lumen-FFmpeg-Fetcher', 'Accept-Encoding': 'identity'})
        result = client.send(request, stream=True)
        if result.is_redirect:
            location = result.headers.get('Location');result.close()
            if not location:raise ValueError('FFmpeg 下载重定向无效')
            url=str(parsed.join(location));continue
        try:result.raise_for_status()
        except Exception:result.close();raise
        return result
    raise ValueError('FFmpeg 下载重定向次数过多')


def extract(archive, destination, progress=None, cancelled=None):
    extracted = {}
    with zipfile.ZipFile(archive) as bundle:
        for member in bundle.infolist():
            name = Path(member.filename).name
            if name not in MEMBERS or member.is_dir():continue
            if member.file_size > MAX_MEMBER:raise ValueError('FFmpeg 组件体积异常')
            check_cancelled(cancelled)
            if progress:progress(0, member.file_size, name)
            target = destination / name
            partial = destination / (name + '.part')
            digest = hashlib.sha256();total = 0
            with bundle.open(member) as incoming, partial.open('wb') as output:
                for block in iter(lambda: incoming.read(1024 * 1024), b''):
                    check_cancelled(cancelled)
                    total += len(block)
                    if total > MAX_MEMBER:raise ValueError('FFmpeg 组件体积异常')
                    digest.update(block);output.write(block)
                    if progress and total % (8 * 1024 * 1024) < 1024 * 1024:progress(total, member.file_size, name)
                output.flush();os.fsync(output.fileno())
            with partial.open('rb') as check:
                if check.read(2) != b'MZ':raise ValueError('下载的组件不是 Windows 可执行文件')
            partial.replace(target)
            extracted[name] = {'path': str(target), 'size': total, 'sha256': digest.hexdigest()}
    missing = [name for name in MEMBERS if name not in extracted]
    if missing:raise ValueError('下载包中缺少组件：' + ', '.join(missing))
    return extracted


def verify_runtime(extracted):
    for name in MEMBERS:
        path = extracted[name]['path']
        result = subprocess.run([path, '-version'], capture_output=True, timeout=60,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if result.returncode != 0 or not result.stdout.startswith(name.encode() + b' version'):
            raise ValueError(name + ' 运行验证失败')


def ensure(progress=None, cancelled=None, proxy=None, fetcher=None):
    """Download, verify and unpack FFmpeg next to the library data; returns the component map."""
    if not needed():return {}
    destination = install_directory()
    archive = destination / 'ffmpeg-download.zip.part'
    failure = None
    for source in SOURCES:
        digest = hashlib.sha256();total = 0
        try:
            check_cancelled(cancelled)
            if progress:progress(0, 0, '下载 FFmpeg 组件')
            client = fetcher(source['url']) if fetcher else client_for(proxy)
            try:
                result = client if isinstance(client, httpx.Response) else response(client, source['url'])
                with archive.open('wb') as output:
                    for block in result.iter_bytes(1024 * 1024):
                        check_cancelled(cancelled)
                        total += len(block)
                        if total > MAX_ZIP:raise ValueError('FFmpeg 下载包超过大小上限')
                        digest.update(block);output.write(block)
                        if progress and total % (4 * 1024 * 1024) < 1024 * 1024:progress(total, 0, '下载 FFmpeg 组件')
                    output.flush();os.fsync(output.fileno())
            finally:
                if isinstance(client, httpx.Response):client.close()
                elif hasattr(client, 'close'):client.close()
            if source['sha256'] and digest.hexdigest() != source['sha256']:
                raise ValueError('FFmpeg 下载包 SHA-256 校验失败')
            extracted = extract(archive, destination, progress, cancelled)
            verify_runtime(extracted)
            (destination / 'source.json').write_text(json.dumps(
                {'url': source['url'], 'sha256': digest.hexdigest(), 'components': extracted}, ensure_ascii=False, indent=2), encoding='utf-8')
            archive.unlink(missing_ok=True)
            if progress:progress(1, 1, 'FFmpeg 组件已就绪')
            return {'ffmpeg': extracted['ffmpeg.exe']['path'], 'ffprobe': extracted['ffprobe.exe']['path']}
        except Exception as error:
            failure = error
            archive.unlink(missing_ok=True)
    raise ValueError(f'FFmpeg 组件下载失败：{failure}')
