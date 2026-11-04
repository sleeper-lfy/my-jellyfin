import importlib.util
import json
from pathlib import Path
import zipfile

import pytest

spec=importlib.util.spec_from_file_location('preview_release',Path(__file__).parents[1]/'scripts/preview-release.py')
preview=importlib.util.module_from_spec(spec);spec.loader.exec_module(preview)


def artifacts(tmp_path):
    windows=tmp_path/'Lumen-Setup-x64.exe';windows.write_bytes(b'MZ'+bytes(1024*1024))
    apk=tmp_path/'Lumen-android-debug.apk'
    with zipfile.ZipFile(apk,'w') as package:
        package.writestr('classes.dex',bytes(1024*1024+1));package.writestr('AndroidManifest.xml',b'manifest')
    for path in (windows,apk):Path(str(path)+'.sha256').write_text(preview.digest(path)+'  '+path.name+'\n')
    tests={'tests':10,'failures':0,'errors':0,'skipped':0}
    acceptance={'format_version':1,'version':'0.4.14','source':{'commit':'same'},
                'artifact':{'sha256':preview.digest(windows),'bytes':windows.stat().st_size},
                'automated':{'status':'passed','tests':tests,'installation':{'sha256':preview.digest(windows),
                    'installed_ui':True,'mpv_runtime':True,'plugin_worker':True,'uninstall':True}},
                'manual':{'audio':{'status':'unverified'}}}
    proof={'source_commit':'same','version':'0.4.14','signature_verified':True,'lint':'passed',
           'certificate_sha256':json.loads((preview.ROOT/'docs/validation/beauty-preview.json').read_text())['android_signature']['certificate_sha256'],
           'tests':tests.copy(),'bytes':apk.stat().st_size,'sha256':preview.digest(apk)}
    return windows,apk,acceptance,proof


def test_preview_preserves_unverified_manual_evidence(tmp_path):
    windows,apk,acceptance,proof=artifacts(tmp_path)
    original=json.dumps(acceptance,sort_keys=True)
    preview.validate_artifacts(windows,apk,acceptance,proof,'same','0.4.14')
    assert json.dumps(acceptance,sort_keys=True)==original


@pytest.mark.parametrize('fault',['source','version','signature','certificate','failed_tests','skipped_tests','installer','apk','checksum'])
def test_preview_rejects_mismatched_or_unverified_artifacts(tmp_path,fault):
    windows,apk,acceptance,proof=artifacts(tmp_path)
    if fault=='source':proof['source_commit']='other'
    if fault=='version':proof['version']='old'
    if fault=='signature':proof['signature_verified']=False
    if fault=='certificate':proof['certificate_sha256']='wrong'
    if fault=='failed_tests':proof['tests']['failures']=1
    if fault=='skipped_tests':proof['tests']['skipped']=1
    if fault=='installer':acceptance['automated']['installation']['mpv_runtime']=False
    if fault=='apk':apk.write_bytes(b'changed')
    if fault=='checksum':Path(str(windows)+'.sha256').write_text('wrong')
    with pytest.raises((AssertionError,ValueError)):preview.validate_artifacts(windows,apk,acceptance,proof,'same','0.4.14')


def test_only_matching_preview_tag_is_accepted(monkeypatch):
    monkeypatch.setenv('GITHUB_REF_NAME','v0.4.14-preview.1');assert preview.version()=='0.4.14'
    for tag in ('v0.4.14','v0.4.13-preview.1','v0.4.14-preview.0','other'):
        monkeypatch.setenv('GITHUB_REF_NAME',tag)
        with pytest.raises(AssertionError):preview.version()


def test_android_tests_must_be_present_and_successful(tmp_path):
    with pytest.raises(AssertionError):preview.tests_passed(tmp_path)
    report=tmp_path/'TEST-one.xml';report.write_text('<testsuite tests="3" failures="0" errors="0" skipped="0"/>')
    assert preview.tests_passed(tmp_path)['tests']==3
    report.write_text('<testsuite tests="3" failures="0" errors="0" skipped="1"/>')
    with pytest.raises(AssertionError):preview.tests_passed(tmp_path)
