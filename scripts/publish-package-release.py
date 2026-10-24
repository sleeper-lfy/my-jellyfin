"""Publish an explicitly requested, already delivered package without rebuilding it."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tomllib

INPUTS=['src','android','assets','plugins','installer','requirements.lock','pyproject.toml',
        'scripts/build-windows.ps1','scripts/build-installer-windows.ps1','scripts/fetch-mpv-windows.ps1',
        'scripts/launcher.py','scripts/verify-package.py','scripts/verify-installer-windows.ps1']


def validate(request,package,windows,android,run,version):
    assert request['publish'] is True and request['tag']=='v'+version
    source=request['build_source_commit']
    assert len(source)==40 and all(c in '0123456789abcdef' for c in source)
    assert package['version']==android['version']==version
    assert package['source_commit']==windows['source_commit']==android['source_commit']==source
    assert package['windows']==package['delivery']=='success'
    assert package['tests']['failures']==package['tests']['errors']==package['tests']['skipped']==0
    assert run['head_sha']==package['workflow_commit'] and run['conclusion']=='success'
    assert run['path'].split('@')[0]=='.github/workflows/package-current.yml'
    assert package['run_url'].endswith('/'+str(request['package_run_id']))
    return source


def gh(*arguments):
    return subprocess.check_output(['gh',*arguments],text=True)


def main():
    root=Path('.');request=json.loads((root/'scripts/publish-package-release.json').read_text())
    package=json.loads((root/'target/package-status.json').read_text());windows=json.loads((root/'target/windows-installer.json').read_text());android=json.loads((root/'target/android-build.json').read_text())
    version=tomllib.loads((root/'pyproject.toml').read_text())['project']['version'];repository=os.environ['GH_REPO'];head=os.environ['GITHUB_SHA'];tag=request['tag'];run_id=int(request['package_run_id'])
    run=json.loads(gh('api',f'repos/{repository}/actions/runs/{run_id}'))
    source=validate(request,package,windows,android,run,version)
    subprocess.run(['git','fetch','--depth=1','origin',source],check=True)
    subprocess.run(['git','diff','--exit-code',source,'--',*INPUTS],check=True)
    jobs=json.loads(gh('api',f'repos/{repository}/actions/runs/{run_id}/jobs'))['jobs']
    assert all(any(job['name']==name and job['conclusion']=='success' for job in jobs) for name in ('windows','deliver'))
    report={'tag':tag,'source_commit':source,'workflow_commit':head,'windows':'success','publish':'failure',
            'package_run_id':run_id,'run_url':f"{os.environ['GITHUB_SERVER_URL']}/{repository}/actions/runs/{os.environ['GITHUB_RUN_ID']}",
            'release_url':f"https://github.com/{repository}/releases/tag/{tag}"}
    try:
        subprocess.run([sys.executable,'scripts/verify-android-target.py'],check=True)
        subprocess.run([sys.executable,'scripts/verify-android-signature.py'],check=True)
        directory=Path('.local/reused-package');directory.mkdir(parents=True,exist_ok=True)
        subprocess.run(['gh','run','download',str(run_id),'--name','Lumen-windows-x64','--dir',str(directory)],check=True)
        executable=directory/'installer/Lumen-Setup-x64.exe';checksum=Path(str(executable)+'.sha256')
        digest=hashlib.sha256(executable.read_bytes()).hexdigest()
        assert executable.stat().st_size==windows['bytes'] and digest==windows['sha256']
        assert digest==checksum.read_text(encoding='utf-8-sig').split()[0].lower()
        destination=Path('.local/release-windows');destination.mkdir(parents=True,exist_ok=True)
        for path in (executable,checksum):shutil.copyfile(path,destination/path.name)
        # GITHUB_TOKEN-created refs do not start another build workflow. Create
        # the release tag at this authorized publication commit; the complete
        # application/build inputs were compared with the actual build above.
        existing=subprocess.run(['gh','api',f'repos/{repository}/git/ref/tags/{tag}'],capture_output=True,text=True)
        if existing.returncode:
            gh('api','--method','POST',f'repos/{repository}/git/refs','-f',f'ref=refs/tags/{tag}','-f',f'sha={head}')
        subprocess.run(['git','fetch','--depth=1','origin',f'refs/tags/{tag}:refs/tags/{tag}'],check=True)
        release_commit=subprocess.check_output(['git','rev-parse',tag+'^{}'],text=True).strip()
        subprocess.run(['git','diff','--exit-code',source,release_commit,'--',*INPUTS],check=True)
        report['release_commit']=release_commit
        environment={**os.environ,'SOURCE_COMMIT':release_commit,'RELEASE_TAG':tag,'BUILD_SOURCE_COMMIT':source}
        subprocess.run([sys.executable,'scripts/publish-release.py'],env=environment,check=True)
        report['publish']='success'
        print('Published the original verified EXE and APK:',report['release_url'])
    except Exception as error:
        report['diagnostics']=str(error)[:3000]
        raise
    finally:
        Path('target/release-status.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')


if __name__=='__main__':main()
