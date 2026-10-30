import json
from pathlib import Path
import pytest
from lumen.actor_batch import fetch_actor_portraits
from lumen.plugins import Plugins
from test_actor_plugins import credit, provider, candidate, portrait


def matching(name='Local actor', identifier='person:1'):
    return {**candidate(),'name':name,'id':identifier}


def test_batches_deduplicates_actors_and_preserves_existing_locked_and_other_fields(library,qapp,tmp_path,monkeypatch):
    manager=provider(library)
    first=credit(library,'First');second=credit(library,'Second')
    locked=credit(library,'Locked',locked=True)
    existing=tmp_path/'existing.jpg';existing.write_bytes(b'existing')
    present=credit(library,'Present',photo=existing)
    calls=[];images=[];picture=portrait(qapp)
    def run(self,plugin,operation,**kwargs):calls.append(kwargs['query']);return [matching()]
    def fetch(self,plugin,url,image=False):images.append(url);return picture,'image/png'
    monkeypatch.setattr(Plugins,'run',run);monkeypatch.setattr(Plugins,'fetch',fetch)
    result=fetch_actor_portraits(library,['tvmaze'],delay=0)
    assert result['updated']==1 and result['skipped']==0 and result['updated_works']==2
    assert calls==['Local actor'] and len(images)==1
    for identifier in (first,second):
        saved=library.work(identifier)['metadata']
        assert Path(saved['actors'][0]['photo_cache']).is_file()
        assert saved['overview']=='Keep this' and saved['actors'][0]['name']=='Local actor'
    assert not library.work(locked)['metadata']['actors'][0].get('photo_cache')
    assert library.work(present)['metadata']['actors'][0]['photo_cache']==str(existing)
    assert fetch_actor_portraits(library,['tvmaze'],delay=0)['skipped']==1
    assert calls==['Local actor']


def test_fallback_requires_unique_alias_match_and_does_not_touch_shared_alias_credit(library,qapp,monkeypatch):
    provider(library);provider(library,'wikimedia-actors')
    wanted=credit(library,'Wanted')
    other=credit(library,'Different',name='Other actor')
    library.edit_metadata(other,{'actors':[{'name':'Other actor','aliases':['Local actor'],'gender':'female'}]},[])
    calls=[]
    def run(self,plugin,operation,**kwargs):
        calls.append((plugin,kwargs['query']))
        return [matching('Wrong person')] if plugin=='tvmaze' else [matching('Provider spelling')|{'aliases':['Local alias']}]
    monkeypatch.setattr(Plugins,'run',run)
    picture=portrait(qapp);monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:(picture,'image/png'))
    result=fetch_actor_portraits(library,['tvmaze','wikimedia-actors'],names=['Local actor'],delay=0)
    assert result['updated']==1 and len(calls)==2
    assert library.work(wanted)['metadata']['actors'][0]['photo_source']=='wikimedia-actors'
    assert not library.work(other)['metadata']['actors'][0].get('photo_cache')


@pytest.mark.parametrize('rows,status',[
    ([matching(identifier='one'),matching(identifier='two')],'ambiguous'),
    ([matching('Partial Local actor')],'unmatched'),
    ([matching()|{'photo':None}],'unmatched'),
])
def test_never_picks_first_ambiguous_partial_or_no_photo_result(library,monkeypatch,rows,status):
    provider(library);work=credit(library,'Match')
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:rows)
    def no_download(*a,**k):raise AssertionError('must not fetch')
    monkeypatch.setattr(Plugins,'fetch',no_download)
    result=fetch_actor_portraits(library,['tvmaze'],delay=0)
    assert result[status]==1 and result['updated']==0
    assert not library.work(work)['metadata']['actors'][0].get('photo_cache')


def test_failure_isolated_and_cancellation_keeps_previous_actor(library,qapp,monkeypatch):
    provider(library);a=credit(library,'First',name='First');b=credit(library,'Second',name='Second')
    stopped=[False];picture=portrait(qapp)
    def run(self,plugin,operation,**kwargs):return [matching(kwargs['query'])]
    monkeypatch.setattr(Plugins,'run',run)
    monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:(picture,'image/png'))
    def progress(done,total,message):
        if done==1:stopped[0]=True
    result=fetch_actor_portraits(library,['tvmaze'],delay=0,progress=progress,cancelled=lambda:stopped[0])
    assert result['cancelled'] and result['updated']==1 and result['completed']==1
    assert library.work(a)['metadata']['actors'][0].get('photo_cache')
    assert not library.work(b)['metadata']['actors'][0].get('photo_cache')
    def failure(*a,**k):raise RuntimeError('offline')
    monkeypatch.setattr(Plugins,'run',failure)
    retry=fetch_actor_portraits(library,['tvmaze'],delay=0)
    assert retry['skipped']==1 and retry['failed']==1 and retry['items'][1]['attempts'][0]['error']=='offline'


def test_cancellation_during_download_does_not_apply_current_actor(library,qapp,monkeypatch):
    provider(library);work=credit(library,'Cancelled');stop=[False];picture=portrait(qapp)
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:[matching()])
    def fetch(*a,**k):stop[0]=True;return picture,'image/png'
    monkeypatch.setattr(Plugins,'fetch',fetch)
    result=fetch_actor_portraits(library,['tvmaze'],delay=0,cancelled=lambda:stop[0])
    assert result['cancelled'] and result['updated']==0
    assert not library.work(work)['metadata']['actors'][0].get('photo_cache')


def test_scopes_overwrite_and_disabled_source(library,qapp,tmp_path,monkeypatch):
    manager=provider(library);path=tmp_path/'old.jpg';path.write_bytes(b'old')
    credit(library,'Ready',photo=path);other=credit(library,'Other',name='Other')
    queries=[]
    def run(self,p,op,**kwargs):queries.append(kwargs['query']);return [matching()]
    monkeypatch.setattr(Plugins,'run',run)
    picture=portrait(qapp);monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:(picture,'image/png'))
    result=fetch_actor_portraits(library,['tvmaze'],replace=True,names=['Local actor'],delay=0)
    assert result['updated']==1 and queries==['Local actor']
    assert not library.work(other)['metadata']['actors'][0].get('photo_cache')
    manager.configure('tvmaze',{'enabled':False})
    with pytest.raises(ValueError,match='已启用'):fetch_actor_portraits(library,['tvmaze'])
