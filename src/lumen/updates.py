"""Public Gitee Windows updates with bounded downloads and a normal Inno upgrade."""
from dataclasses import dataclass,field
import hashlib
import json
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit,urljoin
import httpx
from .core import check_cancelled

REPO='sleeper_lfy/my-jellyfin'
API=f'https://gitee.com/api/v5/repos/{REPO}/releases/latest'
RAW=f'https://gitee.com/{REPO}/raw/main/target/'
MAX_INSTALLER=1024*1024*1024
INSTALLER='Lumen-Setup-x64.exe'


def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,6}\.\d{1,6}\.\d{1,6}',value):raise ValueError('更新版本格式无效')
    return tuple(map(int,value.split('.')))


def release_url(name,tag):
    return f'https://gitee.com/{REPO}/releases/download/{tag}/{name}'


def validate_url(url):
    parsed=urlsplit(url)
    host=parsed.hostname or ''
    # Release attachments redirect to Gitee's own CDN (foruda.gitee.com).
    allowed=host=='gitee.com' or host.endswith('.gitee.com')
    if parsed.scheme!='https' or parsed.username is not None or parsed.password is not None or parsed.port not in (None,443) or parsed.fragment or not allowed:
        raise ValueError('更新地址必须来自 Gitee HTTPS')


@dataclass(frozen=True)
class Candidate:
    version:str
    url:str
    size:int
    sha256:str
    notes:str=''
    parts:tuple=field(default=())
    def __post_init__(self):
        version(self.version);validate_url(self.url) if self.url else None
        expected=release_url(INSTALLER,f'v{self.version}')
        if self.parts:
            if self.url or type(self.size) is not int or not 4096<=self.size<=MAX_INSTALLER or not re.fullmatch(r'[a-f0-9]{64}',self.sha256):raise ValueError('更新安装包信息无效或缺少 SHA-256')
            if len(self.parts)>64 or any(not isinstance(part,tuple) or len(part)!=2 for part in self.parts):raise ValueError('更新安装包信息无效或缺少 SHA-256')
            for index,part in enumerate(self.parts,1):
                part_url,part_size=part
                if part_url!=release_url(f'{INSTALLER}.part{index:03d}',f'v{self.version}') or type(part_size) is not int or part_size<=0:raise ValueError('更新安装包信息无效或缺少 SHA-256')
            if sum(part[1] for part in self.parts)!=self.size:raise ValueError('更新安装包分卷大小与总量不符')
        elif self.url!=expected or type(self.size) is not int or not 4096<=self.size<=MAX_INSTALLER or not re.fullmatch(r'[a-f0-9]{64}',self.sha256):raise ValueError('更新安装包信息无效或缺少 SHA-256')


def response(client,url):
    for _ in range(6):
        validate_url(url)
        request=client.build_request('GET',url,headers={'User-Agent':'Lumen-PC-Updater','Accept-Encoding':'identity'})
        result=client.send(request,stream=True)
        if result.is_redirect:
            location=result.headers.get('Location');result.close()
            if not location:raise ValueError('Gitee 重定向无效')
            url=urljoin(url,location);continue
        try:result.raise_for_status()
        except Exception:result.close();raise
        return result
    raise ValueError('Gitee 重定向次数过多')


def client_for(proxy=None):
    return httpx.Client(proxy=proxy or None,timeout=httpx.Timeout(10,connect=5),follow_redirects=False)


def fetch(url,limit,proxy=None,cancelled=None):
    with client_for(proxy) as client:
        result=response(client,url)
        try:
            output=bytearray()
            for block in result.iter_bytes(8192):
                check_cancelled(cancelled)
                if len(output)+len(block)>limit:raise ValueError('更新信息过大')
                output.extend(block)
            return bytes(output)
        finally:result.close()


def install_size(url,client=None,proxy=None):
    """Gitee's API omits attachment sizes, so ask the download itself."""
    owned=client is None;client=client or client_for(proxy)
    try:
        for _ in range(6):
            validate_url(url)
            request=client.build_request('HEAD',url,headers={'User-Agent':'Lumen-PC-Updater','Accept-Encoding':'identity'})
            result=client.send(request,stream=True)
            try:
                if result.is_redirect:
                    location=result.headers.get('Location')
                    if not location:raise ValueError('Gitee 重定向无效')
                    url=urljoin(url,location);continue
                result.raise_for_status()
                length=result.headers.get('Content-Length')
                if length is None:raise ValueError('无法确认安装包大小')
                return int(length)
            finally:result.close()
        raise ValueError('Gitee 重定向次数过多')
    finally:
        if owned:client.close()


def installer_candidate(new,assets,fetcher,notes,size_resolver=None):
    """Prefer a single installer attachment; Gitee's 100MB attachment limit otherwise requires split parts."""
    size_resolver=size_resolver or install_size
    def size_of(asset):
        value=asset.get('size')
        return value if type(value) is int and value>0 else size_resolver(asset['browser_download_url'])
    installer=assets.get(INSTALLER)
    if installer:
        checksum=(installer.get('digest') or '').removeprefix('sha256:')
        if not re.fullmatch('[a-f0-9]{64}',checksum):
            url=assets.get(INSTALLER+'.sha256',{}).get('browser_download_url','')
            if url!=release_url(INSTALLER+'.sha256',f'v{new}'):raise ValueError('缺少可信的安装包校验文件')
            checksum=fetcher(url,4096).decode('utf-8-sig').split()[0].lower()
        return Candidate(new,installer['browser_download_url'],size_of(installer),checksum,notes)
    numbered=[(name,asset) for name,asset in assets.items() if re.fullmatch(re.escape(INSTALLER)+r'\.part\d{3}',name)]
    if not numbered:return None
    ordered=[assets[f'{INSTALLER}.part{index:03d}'] for index in range(1,len(numbered)+1) if f'{INSTALLER}.part{index:03d}' in assets]
    if len(ordered)!=len(numbered):raise ValueError('安装包分卷编号不连续')
    url=assets.get(INSTALLER+'.sha256',{}).get('browser_download_url','')
    if url!=release_url(INSTALLER+'.sha256',f'v{new}'):raise ValueError('缺少可信的安装包校验文件')
    checksum=fetcher(url,4096).decode('utf-8-sig').split()[0].lower()
    parts=tuple((part['browser_download_url'],size_of(part)) for part in ordered)
    return Candidate(new,'',sum(part[1] for part in parts),checksum,notes,parts)


def check(current,fetcher=fetch,cancelled=None,size_resolver=None):
    best=None;successful=0;latest=None
    try:
        check_cancelled(cancelled)
        try:
            release=json.loads(fetcher(API,1024*1024))
        except httpx.HTTPStatusError as error:
            # A repository without any published release answers 404: a normal
            # state that must not surface as a network failure.
            if error.response.status_code==404:release=None;successful+=1
            else:raise
        else:successful+=1
        if release:
            new=release['tag_name'].removeprefix('v');version(new)
            if not release.get('draft') and not release.get('prerelease'):
                if version(new)>version(current):
                    assets={entry['name']:entry for entry in release.get('assets',[])}
                    best=installer_candidate(new,assets,fetcher,str(release.get('body') or '')[:3000],size_resolver)
            latest=new
    except (ValueError,TypeError,AttributeError,KeyError,IndexError,UnicodeError,httpx.HTTPError,OSError):pass
    try:
        check_cancelled(cancelled);status=json.loads(fetcher(RAW+'release-status.json',65536));manifest=json.loads(fetcher(RAW+'windows-installer.json',65536))
        new=status['tag'].removeprefix('v');version(new)
        if status.get('windows')!='success' or status.get('publish')!='success' or manifest['source_commit']!=status['source_commit'] or not re.fullmatch(r'[a-f0-9]{40}',status['source_commit']) or manifest.get('file')!=INSTALLER:raise ValueError('安装包尚未完成验证发布')
        candidate=Candidate(new,release_url(INSTALLER,f'v{new}'),manifest['bytes'],manifest['sha256'],'通过仓库 target 发布清单核对的 Windows 安装包。')
        successful+=1
        if version(new)>version(current) and (best is None or version(new)>version(best.version)):best=candidate
    except (ValueError,TypeError,AttributeError,KeyError,IndexError,httpx.HTTPError,OSError):pass
    check_cancelled(cancelled)
    if not successful:
        raise ValueError('无法读取 Gitee 更新信息：仓库还没有发布 Release，或网络暂时不可用')
    return best


def verify(path,candidate,cancelled=None):
    path=Path(path)
    if path.stat().st_size!=candidate.size:raise ValueError('安装包大小不匹配')
    digest=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(65536),b''):check_cancelled(cancelled);digest.update(block)
        stream.seek(0)
        if stream.read(2)!=b'MZ':raise ValueError('下载文件不是 Windows 安装程序')
        stream.seek(60);offset=struct.unpack('<I',stream.read(4))[0]
        if offset>candidate.size-4:raise ValueError('安装程序 PE 头无效')
        stream.seek(offset)
        if stream.read(4)!=b'PE\0\0':raise ValueError('安装程序 PE 头无效')
    if digest.hexdigest()!=candidate.sha256:raise ValueError('安装包 SHA-256 校验失败')
    return path


def download(candidate,directory,progress=None,cancelled=None,client=None,proxy=None):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    descriptor,temporary=tempfile.mkstemp(prefix='lumen-',suffix='.part',dir=directory);temporary=Path(temporary)
    owned=client is None;client=client or client_for(proxy)
    result=None;total=0;reported=0
    try:
        with os.fdopen(descriptor,'wb') as output:
            sources=candidate.parts or ((candidate.url,candidate.size),)
            for index,(url,size) in enumerate(sources):
                result=response(client,url)
                length=result.headers.get('Content-Length')
                if length is not None and int(length)!=size:raise ValueError('安装包大小与更新信息不符')
                part=0
                try:
                    for block in result.iter_bytes(65536):
                        check_cancelled(cancelled);total+=len(block);part+=len(block)
                        if total>candidate.size or part>size:raise ValueError('安装包超过声明大小')
                        output.write(block)
                        if progress and time.monotonic()-reported>=.1:progress(total,candidate.size);reported=time.monotonic()
                finally:result.close();result=None
                if part!=size:raise ValueError('安装包大小与更新信息不符')
            output.flush();os.fsync(output.fileno())
        verify(temporary,candidate,cancelled)
        check_cancelled(cancelled);destination=directory/f'Lumen-Setup-{candidate.version}-x64.exe';temporary.replace(destination)
        if progress:progress(total,candidate.size)
        return destination
    finally:
        temporary.unlink(missing_ok=True)
        if result is not None:result.close()
        if owned:client.close()


def can_install():
    return sys.platform=='win32' and bool(getattr(sys,'frozen',False))


HELPER=r'''$ErrorActionPreference = 'Stop'
$request = Get-Content -LiteralPath $args[0] -Raw -Encoding UTF8 | ConvertFrom-Json
$result = @{ version=$request.version; ok=$false }
try {
    Wait-Process -Id $request.pid -Timeout 120 -ErrorAction SilentlyContinue
    if (Get-Process -Id $request.pid -ErrorAction SilentlyContinue) { throw 'Lumen has not exited; update cancelled' }
    $installer = Get-Item -LiteralPath $request.installer
    if ($installer.Length -ne $request.bytes -or (Get-FileHash -LiteralPath $request.installer -Algorithm SHA256).Hash.ToLowerInvariant() -ne $request.sha256) { throw 'Installer integrity check failed' }
    $arguments = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART','/CLOSEAPPLICATIONS',('/DIR="'+$request.directory+'"'),('/LOG="'+$request.log+'"'))
    $setup = Start-Process -FilePath $request.installer -ArgumentList $arguments -Wait -PassThru
    if ($setup.ExitCode -ne 0) { throw ('Installer exit code '+$setup.ExitCode) }
    $result.ok=$true
} catch { $result.error=$_.Exception.Message }
$result | ConvertTo-Json | Set-Content -LiteralPath $request.result -Encoding UTF8
if (-not (Get-Process -Id $request.pid -ErrorAction SilentlyContinue) -and (Test-Path -LiteralPath $request.application)) {
    Start-Process -FilePath $request.application -ArgumentList ('--data-dir "'+$request.data_dir+'"') -WorkingDirectory $request.directory
}
'''


def prepare_installer(candidate,installer,data_dir,application=None):
    if not can_install():raise ValueError('自动安装仅支持已打包的 Windows 客户端；源码运行请更新 Git')
    installer=Path(installer).resolve();verify(installer,candidate)
    application=Path(application or sys.executable).resolve();directory=installer.parent
    request={'pid':os.getpid(),'version':candidate.version,'installer':str(installer),'bytes':candidate.size,'sha256':candidate.sha256,
             'application':str(application),'directory':str(application.parent),'data_dir':str(Path(data_dir).resolve()),
             'log':str(directory/'update-install.log'),'result':str(directory/'update-result.json')}
    configuration=directory/'update-request.json';script=directory/'Lumen-update.ps1'
    configuration.write_text(json.dumps(request,ensure_ascii=False),encoding='utf-8');script.write_text(HELPER,encoding='utf-8-sig')
    powershell=Path(os.environ.get('SystemRoot',r'C:\Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
    return {'command':[str(powershell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(script),str(configuration)],'directory':str(directory)}


def launch_installer(plan):
    return subprocess.Popen(plan['command'],cwd=plan['directory'],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
