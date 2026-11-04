"""Delete only an explicitly requested, snapshotted set of GitHub Releases; never tags."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]
PLAN=ROOT/'.local/release-cleanup-plan.json'
RESULT=ROOT/'.local/release-cleanup-result.json'


def keeps(tag,version):
    return re.fullmatch(r'v?'+re.escape(version)+r'(?:[-+].+)?',tag,re.I) is not None


def select_releases(releases,version,allowed,required):
    assert re.fullmatch(r'\d+\.\d+\.\d+',version),'Invalid keep version'
    assert keeps(required,version),'Required release must belong to retained version'
    assert any(r['tag_name']==required for r in releases),'Required retained release is missing'
    kept=[r for r in releases if keeps(r['tag_name'],version)]
    deleting=[r for r in releases if not keeps(r['tag_name'],version)]
    assert all(r['tag_name'] in allowed for r in deleting),'Unexpected releases; refresh the explicit deletion request first'
    return kept,deleting


def gh(*args):return subprocess.check_output(['gh','api',*args],text=True)


def listing(repo):
    pages=json.loads(gh('--paginate','--slurp',f'repos/{repo}/releases?per_page=100'))
    return [release for page in pages for release in page]


def inputs():
    request=json.loads((ROOT/'scripts/release-cleanup-request.json').read_text())
    assert request['execute'] is True and request['repository']==os.environ['GITHUB_REPOSITORY']
    proof=json.loads((ROOT/'docs/validation/preview-0.4.14.json').read_text())
    assert request['required_tag']==proof['tag'] and request['keep_version']==proof['android']['version']
    return request,proof


def verify_retained(kept,request,proof,repo):
    release=next(r for r in kept if r['tag_name']==request['required_tag'])
    assert not release['draft'],'Required retained release must remain published'
    actual={a['name']:a for a in release['assets']}
    for expected in proof['assets']:
        assert expected['name'] in actual and actual[expected['name']]['size']==expected['bytes'],'Retained release asset mismatch'
        if actual[expected['name']].get('digest'):
            assert actual[expected['name']]['digest']=='sha256:'+expected['sha256'],'Retained asset digest mismatch'
    tag=json.loads(gh(f'repos/{repo}/git/ref/tags/'+request['required_tag']))
    assert tag['object']['sha']==proof['source_commit'],'Retained tag source changed'
    return release


def plan():
    request,proof=inputs();repo=request['repository'];releases=listing(repo)
    kept,deleting=select_releases(releases,request['keep_version'],request['delete_tags'],request['required_tag'])
    verify_retained(kept,request,proof,repo)
    result={'request':request,'before':releases,'delete_ids':[r['id'] for r in deleting],'keep_ids':[r['id'] for r in kept]}
    PLAN.parent.mkdir(exist_ok=True,parents=True);PLAN.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({'keep':[r['tag_name'] for r in kept],'delete':[r['tag_name'] for r in deleting]},indent=2))


def apply():
    request,proof=inputs();repo=request['repository'];saved=json.loads(PLAN.read_text())
    assert saved['request']==request,'Cleanup request changed after snapshot'
    current=listing(repo)
    assert {(r['id'],r['tag_name']) for r in current}=={(r['id'],r['tag_name']) for r in saved['before']},'Release list changed after snapshot'
    kept,deleting=select_releases(current,request['keep_version'],request['delete_tags'],request['required_tag'])
    assert {r['id'] for r in deleting}==set(saved['delete_ids'])
    retained=verify_retained(kept,request,proof,repo)
    identity=lambda release:sorted((a['id'],a['name'],a['size']) for a in release['assets'])
    asset_identity=identity(retained)
    result={'request_id':request['request_id'],'deleted':[],'remaining':[],'tags_deleted':False,'success':False}
    try:
        for release in deleting:
            fresh=json.loads(gh(f'repos/{repo}/releases/{release["id"]}'))
            assert fresh['tag_name']==release['tag_name'] and not keeps(fresh['tag_name'],request['keep_version'])
            gh('--method','DELETE',f'repos/{repo}/releases/{release["id"]}')
            result['deleted'].append({'id':release['id'],'tag':release['tag_name']})
            print('Deleted release (tag retained):',release['tag_name'],flush=True)
        remaining=listing(repo)
        kept,left=select_releases(remaining,request['keep_version'],[],request['required_tag'])
        assert not left
        final=verify_retained(kept,request,proof,repo)
        assert final['id']==retained['id'] and identity(final)==asset_identity,'Retained release or assets changed'
        result['remaining']=[{'id':r['id'],'tag':r['tag_name']} for r in remaining]
        result['retained_asset_count']=len(final['assets']);result['success']=True
        print(json.dumps(result,indent=2))
    finally:RESULT.write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':{'plan':plan,'apply':apply}[sys.argv[1]]()
