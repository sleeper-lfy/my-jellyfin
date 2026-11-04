"""Explicit test prereleases: automatic evidence is required; manual checks stay unverified."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tomllib
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()


def version():
    value=tomllib.loads((ROOT/'pyproject.toml').read_text())['project']['version']
    assert re.fullmatch(r'v'+re.escape(value)+r'-preview\.[1-9][0-9]*',os.environ['GITHUB_REF_NAME']), 'Tag/version mismatch'
    return value


def gh(*args):
    return subprocess.check_output(['gh',*args],text=True)


def tests_passed(directory):
    suites=[ET.parse(path).getroot() for path in directory.glob('TEST-*.xml')]
    counts={key:sum(int(suite.get(key,0)) for suite in suites) for key in ('tests','failures','errors','skipped')}
    assert counts['tests'] and not any(counts[key] for key in ('failures','errors','skipped')),counts
    return counts


def android():
    value=version();sdk=ROOT/'.local/android-tools/sdk';tools=sdk/'build-tools/35.0.0'
    archive=ROOT/'android/app/build/outputs/apk/debug/app-debug.apk'
    output=ROOT/'.local/preview-android';output.mkdir(exist_ok=True,parents=True)
    verified=subprocess.check_output([str(tools/'apksigner'),'verify','--verbose','--print-certs',str(archive)],text=True)
    expected=json.loads((ROOT/'docs/validation/beauty-preview.json').read_text())['android_signature']['certificate_sha256']
    certificates=set(re.findall(r'(?im)^.*certificate SHA-256 digest:\s*([0-9a-f]{64})\s*$',verified))
    assert certificates=={expected},'Persistent APK certificate changed'
    subprocess.run([str(tools/'zipalign'),'-c','-p','4',str(archive)],check=True)
    package=subprocess.check_output([str(tools/'aapt'),'dump','badging',str(archive)],text=True)
    match=re.search(r"package: name='net.lumen.media' versionCode='(\d+)' versionName='([^']+)'",package)
    gradle=(ROOT/'android/app/build.gradle').read_text();code=int(re.search(r'versionCode (\d+)',gradle)[1])
    assert match and int(match[1])==code and match[2]==value,'APK version mismatch'
    tests=tests_passed(ROOT/'android/app/build/test-results/testDebugUnitTest')
    dest=output/'Lumen-android-debug.apk';shutil.copyfile(archive,dest)
    checksum=digest(dest);Path(str(dest)+'.sha256').write_text(checksum+'  '+dest.name+'\n')
    proof={'version':value,'version_code':code,'source_commit':os.environ['GITHUB_SHA'],
           'sha256':checksum,'bytes':dest.stat().st_size,'certificate_sha256':expected,
           'tests':tests,'signature_verified':True,'lint':'passed','manual_device_checks':'unverified'}
    (output/'android-verification.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(proof,indent=2))


def validate_artifacts(windows,android,acceptance,proof,source,value):
    sys.path.insert(0,str(ROOT/'src'))
    from lumen.release_acceptance import validate
    validate(acceptance,windows,require_release=False)
    assert acceptance['source']['commit']==proof['source_commit']==source,'Source mismatch'
    assert acceptance['version']==proof['version']==value,'Version mismatch'
    assert proof['signature_verified'] is True and proof['lint']=='passed'
    expected=json.loads((ROOT/'docs/validation/beauty-preview.json').read_text())['android_signature']['certificate_sha256']
    assert proof['certificate_sha256']==expected,'APK certificate mismatch'
    assert proof['tests']['tests'] and not any(proof['tests'][key] for key in ('failures','errors','skipped'))
    assert android.stat().st_size==proof['bytes'] and digest(android)==proof['sha256'],'APK mismatch'
    with zipfile.ZipFile(android) as package:
        assert package.testzip() is None
        assert {'AndroidManifest.xml','classes.dex'}<=set(package.namelist())
    for archive in (windows,android):
        assert archive.stat().st_size>1024*1024,'Installer is unexpectedly small'
        assert Path(str(archive)+'.sha256').read_text(encoding='utf-8-sig').split()[0].lower()==digest(archive),'Checksum mismatch'


def publish():
    value=version();tag=os.environ['GITHUB_REF_NAME'];source=os.environ['GITHUB_SHA']
    assert subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()==source
    remote_tag=subprocess.check_output(['git','ls-remote','origin','refs/tags/'+tag],text=True).split()
    assert remote_tag and remote_tag[0]==source,'Release tag changed during the build'
    windows=ROOT/'.local/preview-windows/Lumen-Setup-x64.exe';apk=ROOT/'.local/preview-android/Lumen-android-debug.apk'
    acceptance_path=windows.parent/'acceptance.json';proof_path=apk.parent/'android-verification.json'
    acceptance=json.loads(acceptance_path.read_text(encoding='utf-8-sig'));proof=json.loads(proof_path.read_text())
    validate_artifacts(windows,apk,acceptance,proof,source,value)
    # CI builds and tests the tagged checkout. Each platform's evidence names the
    # same commit; a Windows CRLF checkout intentionally has a different byte hash.
    notes=ROOT/'.local/preview-notes.md'
    notes.write_text((ROOT/f'docs/releases/{value}.md').read_text()+f'\n源码：`{source}`\n\nWindows 自动测试：{acceptance["automated"]["tests"]["tests"]} 项；Android：{proof["tests"]["tests"]} 项。安装包和验收记录随附件提供。\n')
    review=windows.parent/'windows-acceptance.json';shutil.copyfile(acceptance_path,review)
    assets=[windows,Path(str(windows)+'.sha256'),apk,Path(str(apk)+'.sha256'),review,proof_path]
    existing=subprocess.run(['gh','release','view',tag,'--json','isDraft,isPrerelease'],capture_output=True,text=True)
    if existing.returncode:
        gh('release','create',tag,'--verify-tag','--draft','--prerelease','--title',f'Lumen {value} Preview 1 · Windows + Android','--notes-file',str(notes))
    else:
        state=json.loads(existing.stdout);assert state['isDraft'] or state['isPrerelease'],'Refusing to replace a stable release'
    gh('release','upload',tag,*map(str,assets),'--clobber')
    metadata=json.loads(gh('release','view',tag,'--json','assets'))
    remote={asset['name']:asset for asset in metadata['assets']}
    for asset in assets:
        assert remote[asset.name]['size']==asset.stat().st_size
        if remote[asset.name].get('digest'):assert remote[asset.name]['digest']=='sha256:'+digest(asset)
    gh('release','edit',tag,'--draft=false','--prerelease','--latest=false','--notes-file',str(notes))
    final=json.loads(gh('release','view',tag,'--json','isDraft,isPrerelease,url'))
    assert not final['isDraft'] and final['isPrerelease'];print(final['url'])


if __name__=='__main__':
    {'version':version,'android':android,'publish':publish}[sys.argv[1]]()
