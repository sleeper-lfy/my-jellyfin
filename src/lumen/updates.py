"""Public GitHub Windows updates with bounded downloads and a normal Inno upgrade."""
from dataclasses import dataclass
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

REPO='sleeper-lfy/my-jellyfin'
API=f'https://api.github.com/repos/{REPO}/releases/latest'
RAW=f'https://raw.githubusercontent.com/{REPO}/main/target/'
MAX_INSTALLER=1024*1024*1024


def version(value):
    if not isinstance(value,str) or not re.fullmatch(r'\d{1,6}\.\d{1,6}\.\d{1,6}',value):raise ValueError('更新版本格式无效')
    return tuple(map(int,value.split('.')))


def validate_url(url):
    parsed=urlsplit(url)
    if parsed.scheme!='https' or parsed.username is not None or parsed.password is not None or parsed.port not in (None,443) or parsed.fragment or parsed.hostname not in {'github.com','api.github.com','raw.githubusercontent.com','release-assets.githubusercontent.com','objects.githubusercontent.com'}:
        raise ValueError('更新地址必须来自 GitHub HTTPS')


@dataclass(frozen=True)
class Candidate:
    version:str
    url:str
    size:int
    sha256:str
    notes:str=''
    def __post_init__(self):
        version(self.version);validate_url(self.url)
        expected=f'https://github.com/{REPO}/releases/download/v{self.version}/Lumen-Setup-x64.exe'
        if self.url!=expected or type(self.size) is not int or not 4096<=self.size<=MAX_INSTALLER or not re.fullmatch(r'[a-f0-9]{64}',self.sha256):raise ValueError('更新安装包信息无效或缺少 SHA-256')


def response(client,url):
    for _ in range(6):
        validate_url(url)
        request=client.build_request('GET',url,headers={'User-Agent':'Lumen-PC-Updater','Accept-Encoding':'identity'})
        result=client.send(request,stream=True)
        if result.is_redirect:
            location=result.headers.get('Location');result.close()
            if not location:raise ValueError('GitHub 重定向无效')
            url=urljoin(url,location);continue
        try:result.raise_for_status()
        except Exception:result.close();raise
        return result
    raise ValueError('GitHub 重定向次数过多')


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


def check(current,fetcher=fetch,cancelled=None):
    best=None;successful=0
    try:
        check_cancelled(cancelled);release=json.loads(fetcher(API,1024*1024));new=release['tag_name'].removeprefix('v');version(new)
        if not release.get('draft') and not release.get('prerelease'):
            if version(new)>version(current):
                assets={entry['name']:entry for entry in release.get('assets',[])};asset=assets.get('Lumen-Setup-x64.exe')
                if asset:
                    checksum=asset.get('digest','').removeprefix('sha256:')
                    if not re.fullmatch('[a-f0-9]{64}',checksum):
                        url=assets.get('Lumen-Setup-x64.exe.sha256',{}).get('browser_download_url','')
                        if url!=f'https://github.com/{REPO}/releases/download/v{new}/Lumen-Setup-x64.exe.sha256':raise ValueError('缺少可信的安装包校验文件')
                        checksum=fetcher(url,4096).decode('utf-8-sig').split()[0].lower()
                    best=Candidate(new,asset['browser_download_url'],asset['size'],checksum,str(release.get('body') or '')[:3000])
            successful+=1
    except (ValueError,TypeError,AttributeError,KeyError,IndexError,UnicodeError,httpx.HTTPError,OSError):pass
    try:
        check_cancelled(cancelled);status=json.loads(fetcher(RAW+'release-status.json',65536));manifest=json.loads(fetcher(RAW+'windows-installer.json',65536))
        new=status['tag'].removeprefix('v');version(new)
        if status.get('windows')!='success' or status.get('publish')!='success' or manifest['source_commit']!=status['source_commit'] or not re.fullmatch(r'[a-f0-9]{40}',status['source_commit']) or manifest.get('file')!='Lumen-Setup-x64.exe':raise ValueError('安装包尚未完成验证发布')
        candidate=Candidate(new,f'https://github.com/{REPO}/releases/download/v{new}/Lumen-Setup-x64.exe',manifest['bytes'],manifest['sha256'],'通过仓库 target 发布清单核对的 Windows 安装包。')
        successful+=1
        if version(new)>version(current) and (best is None or version(new)>version(best.version)):best=candidate
    except (ValueError,TypeError,AttributeError,KeyError,IndexError,httpx.HTTPError,OSError):pass
    check_cancelled(cancelled)
    if not successful:raise ValueError('无法读取 GitHub 更新信息，请检查网络或稍后重试')
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
            result=response(client,candidate.url)
            length=result.headers.get('Content-Length')
            if length is not None and int(length)!=candidate.size:raise ValueError('安装包大小与更新信息不符')
            for block in result.iter_bytes(65536):
                check_cancelled(cancelled);total+=len(block)
                if total>candidate.size:raise ValueError('安装包超过声明大小')
                output.write(block)
                if progress and time.monotonic()-reported>=.1:progress(total,candidate.size);reported=time.monotonic()
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
