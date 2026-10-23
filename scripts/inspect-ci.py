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
if configuration.get('release'):
    tag=configuration['release']
    assert re.fullmatch(r'v[0-9]+\.[0-9]+\.[0-9]+',tag)
    metadata=json.loads(subprocess.check_output(['gh','api',f'repos/{repository}/releases/tags/{tag}']))
    result.append({'release':{key:metadata.get(key) for key in ('id','tag_name','name','draft','prerelease','published_at','target_commitish','html_url')},
                   'assets':[{key:asset.get(key) for key in ('name','size','state','browser_download_url','digest')} for asset in metadata.get('assets',[])]})
Path('target/ci-inspection.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
