from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import struct
import threading
import httpx
import pytest
from lumen import updates
from lumen.core import ImportCancelled


def executable():
    data=bytearray(8192);data[:2]=b'MZ';struct.pack_into('<I',data,60,128);data[128:132]=b'PE\0\0';return bytes(data)


def candidate():
    data=executable();return updates.Candidate('0.4.6',f'https://github.com/{updates.REPO}/releases/download/v0.4.6/Lumen-Setup-x64.exe',len(data),hashlib.sha256(data).hexdigest())


def metadata(url,limit):
    value=candidate()
    if url==updates.API:raise httpx.HTTPError('API unavailable')
    if url.endswith('release-status.json'):return json.dumps({'tag':'v0.4.6','windows':'success','publish':'success','source_commit':'a'*40}).encode()
    return json.dumps({'file':'Lumen-Setup-x64.exe','bytes':value.size,'sha256':value.sha256,'source_commit':'a'*40}).encode()


def test_release_api_fallback_and_no_downgrades_or_unpublished_packages():
    assert updates.check('0.4.5',metadata)==candidate().__class__(**{**asdict(candidate()),'notes':'通过仓库 target 发布清单核对的 Windows 安装包。'})
    assert updates.check('0.4.6',metadata) is None
    def pending(url,limit):
        data=metadata(url,limit)
        return data.replace(b'"success"',b'"failure"') if url.endswith('release-status.json') else data
    with pytest.raises(ValueError):updates.check('0.4.5',pending)
    def mismatched(url,limit):
        data=metadata(url,limit)
        return data.replace(b'a'*40,b'b'*40) if url.endswith('windows-installer.json') else data
    with pytest.raises(ValueError):updates.check('0.4.5',mismatched)
    with pytest.raises(ImportCancelled):updates.check('0.4.5',metadata,lambda:True)


def test_release_checksums_and_newest_stable_asset():
    value=candidate()
    def read(url,limit):
        if url==updates.API:return json.dumps({'tag_name':'v0.4.7','assets':[{'name':'Lumen-Setup-x64.exe','browser_download_url':value.url.replace('0.4.6','0.4.7'),'size':value.size,'digest':'sha256:'+value.sha256}]}).encode()
        return metadata(url,limit)
    assert updates.check('0.4.5',read).version=='0.4.7'
    for url in ('http://github.com/a.exe','https://github.com.evil.test/a.exe','https://github.com@evil.test/a.exe','file:///tmp/a','https://github.com:444/a.exe'):
        with pytest.raises(ValueError):updates.validate_url(url)
    with pytest.raises(ValueError):updates.Candidate('0.4.6',value.url,True,value.sha256)
    with pytest.raises(ValueError):updates.Candidate('0.4.6',value.url.replace(updates.REPO,'someone/else'),value.size,value.sha256)


def test_streaming_download_checks_pe_hash_and_size_and_cleans_cancellation(tmp_path):
    value=candidate();data=executable();progress=[]
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=data))) as client:
        destination=updates.download(value,tmp_path,lambda done,total:progress.append((done,total)),client=client)
    assert destination.read_bytes()==data and progress[-1]==(len(data),len(data))
    for wrong in (data[:-1],b'x'*len(data),data+b'x'):
        with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=wrong))) as client,pytest.raises(ValueError):updates.download(value,tmp_path,client=client)
        assert destination.read_bytes()==data and not list(tmp_path.glob('*.part'))
    with httpx.Client(transport=httpx.MockTransport(lambda request:httpx.Response(200,content=data))) as client,pytest.raises(ImportCancelled):updates.download(value,tmp_path,cancelled=lambda:True,client=client)
    assert not list(tmp_path.glob('*.part'))
    calls=[]
    def redirect(request):
        calls.append(str(request.url));return httpx.Response(302,headers={'Location':'http://127.0.0.1/private'})
    with httpx.Client(transport=httpx.MockTransport(redirect)) as client,pytest.raises(ValueError):updates.download(value,tmp_path,client=client)
    assert calls==[value.url]


def test_upgrade_helper_waits_for_exit_preserves_install_and_data_paths_and_rechecks_integrity(tmp_path,monkeypatch):
    monkeypatch.setattr(updates,'can_install',lambda:True)
    value=candidate();installer=tmp_path/'updates with spaces'/"Lumen-Setup.exe";installer.parent.mkdir();installer.write_bytes(executable());application=tmp_path/'Program files'/'Lumen.exe';application.parent.mkdir();application.write_bytes(b'old')
    data=tmp_path/'My data';data.mkdir();plan=updates.prepare_installer(value,installer,data,application)
    configuration=json.loads((installer.parent/'update-request.json').read_text())
    assert configuration['directory']==str(application.parent) and configuration['data_dir']==str(data)
    assert configuration['sha256']==value.sha256 and plan['command'][-1].endswith('update-request.json')
    script=(installer.parent/'Lumen-update.ps1').read_text(encoding='utf-8-sig')
    assert 'Wait-Process' in script and 'Get-FileHash' in script and '/FORCECLOSEAPPLICATIONS' not in script
    assert '/DIR=' in script and '--data-dir' in script and 'Start-Process' in script
    calls=[];monkeypatch.setattr(updates.subprocess,'Popen',lambda command,**options:calls.append((command,options)))
    updates.launch_installer(plan);assert calls[0][0]==plan['command'] and not calls[0][1].get('shell')
    installer.write_bytes(b'changed')
    with pytest.raises(ValueError):updates.prepare_installer(value,installer,data,application)


def test_powershell_upgrade_helper_parses_without_executing_it(tmp_path):
    import base64
    import shutil
    import subprocess
    shell=shutil.which('pwsh') or shutil.which('powershell')
    if not shell:pytest.skip('Windows PowerShell parser is checked by Windows CI')
    script=tmp_path/'helper.ps1';script.write_text(updates.HELPER,encoding='utf-8-sig')
    literal=str(script).replace("'","''")
    source="$parseTokens=$null; $parseErrors=$null; [System.Management.Automation.Language.Parser]::ParseFile('"+literal+"',[ref]$parseTokens,[ref]$parseErrors) | Out-Null; if ($parseErrors.Count) { $parseErrors | ForEach-Object { $_.Message }; exit 1 }"
    subprocess.run([shell,'-NoProfile','-NonInteractive','-EncodedCommand',base64.b64encode(source.encode('utf-16le')).decode()],check=True,capture_output=True,timeout=30)
