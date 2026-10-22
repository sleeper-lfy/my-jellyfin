"""Fetch this repository's selected CI logs and publish a bounded, redacted failure report."""
import io,json,os,re,subprocess,zipfile
from pathlib import Path
repository=os.environ['GITHUB_REPOSITORY']
configuration=json.loads(Path('scripts/ci-inspect.json').read_text())
secrets=[value for name,value in os.environ.items() if len(value)>8 and any(word in name for word in ('TOKEN','SECRET','PASSWORD','CREDENTIAL'))]
def redact(value):
    for secret in secrets:value=value.replace(secret,'[redacted]')
    return re.sub(r'(?:gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+)','[redacted]',value)
result=[]
for run in configuration['runs']:
    run=int(run);entry={'run':run}
    jobs=json.loads(subprocess.check_output(['gh','api',f'repos/{repository}/actions/runs/{run}/jobs']))
    entry['jobs']=[{'name':job['name'],'conclusion':job['conclusion'],'steps':[{'name':step['name'],'conclusion':step['conclusion']} for step in job.get('steps',[])]} for job in jobs['jobs']]
    logs=subprocess.run(['gh','api',f'repos/{repository}/actions/runs/{run}/logs'],capture_output=True)
    if logs.returncode:entry['log_error']=redact(logs.stderr.decode(errors='replace'))
    else:
        matches={}
        with zipfile.ZipFile(io.BytesIO(logs.stdout)) as archive:
            for item in archive.infolist():
                if item.file_size>20*1024*1024:continue
                lines=archive.read(item).decode(errors='replace').splitlines()
                errors=[index for index,line in enumerate(lines) if re.search(r'##\[error\]|FAILED|ERROR|FAILURES|What went wrong|Caused by:|AssertionError|Exception:',line)]
                selected=set()
                for index in errors:
                    selected.update(range(max(0,index-2),min(len(lines),index+9)))
                if selected:matches[item.filename]=redact('\n'.join(lines[index] for index in sorted(selected)))[-24000:]
        entry['logs']=matches
    result.append(entry)
for run in configuration.get('cancel',[]):
    subprocess.run(['gh','api','--method','POST',f'repos/{repository}/actions/runs/{int(run)}/cancel'],capture_output=True)
Path('target/ci-inspection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')

publish=configuration.get('publish')
if publish:
    import hashlib,sys
    run=int(publish['run']);source=publish['source'];tag=publish['tag']
    provenance=json.loads(subprocess.check_output(['gh','api',f'repos/{repository}/actions/runs/{run}']))
    assert provenance['head_sha']==source,'Installer source commit mismatch'
    jobs=json.loads(subprocess.check_output(['gh','api',f'repos/{repository}/actions/runs/{run}/jobs']))
    assert any(job['name']=='windows' and job['conclusion']=='success' for job in jobs['jobs']),'Windows verification did not pass'
    destination=Path('.local/release-retry');destination.mkdir(exist_ok=True,parents=True)
    subprocess.run(['gh','run','download',str(run),'--repo',repository,'--name','Lumen-windows-x64','--dir',str(destination)],check=True)
    installer=destination/'installer/Lumen-Setup-x64.exe'
    expected=installer.with_suffix('.exe.sha256').read_text().split()[0]
    assert hashlib.sha256(installer.read_bytes()).hexdigest()==expected,'Installer checksum mismatch'
    subprocess.run([sys.executable,'scripts/verify-android-target.py'],check=True)
    subprocess.run([sys.executable,'scripts/package-installer-target.py',str(installer),'target','--revision',source],check=True)
    files=[str(installer),str(installer)+'.sha256','target/Lumen-android-debug.apk','target/Lumen-android-debug.apk.sha256']
    exists=subprocess.run(['gh','release','view',tag,'--repo',repository],capture_output=True).returncode==0
    command=['gh','release','upload',tag,*files,'--clobber'] if exists else ['gh','release','create',tag,*files,'--verify-tag','--title','Lumen 0.4.1 · Windows + Android','--notes','Verified Windows x64 installer and Android 0.4.1 APK, with SHA-256 checksums. Playback controls, VR and Bluetooth mappings, local NFO artwork and discovery resources.']
    publication=subprocess.run(command,capture_output=True,text=True)
    Path('target/release-upload.json').write_text(json.dumps({'tag':tag,'source_commit':source,'installer_sha256':expected,
        'uploaded':publication.returncode==0,'output':redact(publication.stdout+publication.stderr)},ensure_ascii=False,indent=2)+'\n')
