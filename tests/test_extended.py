import json
from pathlib import Path
import time
import pytest
from lumen.core import parse_name, now
from lumen.plugins import Plugins
from lumen.subtitles import read_subtitles
from test_core import add_work


def test_subtitle_real_conversion(tmp_path):
    path=tmp_path/'字幕.srt'
    path.write_text('1\n00:00:00,500 --> 00:00:02,000\n你好 <i>世界</i>\n\n2\n00:00:03,000 --> 00:00:04,000\n第二行\n',encoding='utf-8')
    result=read_subtitles(path)
    assert result==[(.5,2.0,'你好 世界'),(3.0,4.0,'第二行')]


def test_tv_filename_fallback_and_ambiguity():
    assert parse_name('/Shows/Our Show/Season 2/03 - title.mkv','series')['title']=='Our Show'
    assert parse_name('/Shows/Our Show/Season 2/03 - title.mkv','series')['episode']==3
    assert parse_name('Movie.1080p.WEB-DL.mp4','movie')['title']=='Movie'
    with pytest.raises(ValueError): parse_name('unknown.mp4','series')


def test_discovered_work_merge_preserves_history_and_queue(library):
    local=add_work(library,'Guessed title')
    discovered=add_work(library,'Canonical title',local=False)
    library.update_personal(discovered,rating=9,watchlist=True)
    library.set_setting('queue',{'ids':[discovered,local],'index':0})
    library.merge_works(discovered,local)
    assert library.work(local)['rating']==9
    assert library.work(local)['watchlist']==1
    assert library.setting('queue')=={'ids':[local],'index':0}
    assert len(library.query({'local':False}))==1


def test_tvmaze_followup_plan_and_gender_parser(library):
    manager=Plugins(library)
    manager.install(Path(__file__).parents[1]/'plugins/tvmaze')
    config={'base_url':'https://api.tvmaze.com'}
    request=manager.javascript('tvmaze','buildRequest',{'operation':'discover','config':config})
    assert request['url']=='https://api.tvmaze.com/updates/shows'
    plan=manager.javascript('tvmaze','parseResponse',{'operation':'discover','config':config,'url':request['url'],'body':json.dumps({'1':100,'5':200,'3':300})})
    assert plan['followups'][0]['url'].endswith('/5?embed=cast')
    show={'id':5,'name':'Protocol test fixture','url':'https://www.tvmaze.com/shows/5/test','premiered':'2024-01-02','genres':['Drama'],
          '_embedded':{'cast':[{'person':{'id':1,'name':'Female','gender':'Female'}},{'person':{'id':2,'name':'Unknown','gender':None}}]}}
    rows=manager.javascript('tvmaze','parseResponse',{'operation':'detail','config':config,'url':'https://api.tvmaze.com/shows/5','body':json.dumps(show)})
    assert rows[0]['actors'][0]['gender']=='female'
    assert rows[0]['actors'][1]['gender']=='unknown'
    assert rows[0]['site_added'] is None
    assert rows[0]['released']=='2024-01-02'


def test_10000_work_query_and_full_queue(library):
    with library.db:
        library.db.executemany('INSERT INTO works(identity,kind,title,year,metadata,added) VALUES (?,?,?,?,?,?)',
             ((f'movie:{i}:2024','movie',f'Title {i}',2024,'{"tags":["benchmark"]}',now()) for i in range(10000)))
        library.db.executemany('INSERT INTO files(work_id,path,digest,root,duration) VALUES (?,?,?,?,?)',
             ((i+1,f'/benchmark/{i}.mp4',str(i),'/benchmark',1000) for i in range(10000)))
    started=time.monotonic()
    works=library.query({'tags_all':['benchmark']})
    query_duration=time.monotonic()-started
    assert len(works)==10000
    ids=library.shuffle({'tags_all':['benchmark']})['ids']
    assert len(ids)==len(set(ids))==10000
    # Generous budget to flag accidental per-item network / pathological database behavior on CI.
    assert query_duration<5, f'10000 work query took {query_duration:.2f}s'
    print(f'10000-work query: {query_duration:.3f}s')


def test_continue_filter_and_negative_rating_exclusion(library):
    first=add_work(library,'First')
    second=add_work(library,'Second')
    with library.db: library.db.execute('UPDATE files SET position=12 WHERE work_id=?',(second,))
    assert [w['id'] for w in library.query({'continue':True})]==[second]
    assert library.shuffle({'continue':True})['ids']==[second]
    library.update_personal(first,rating=None)
    assert library.query({'rating_min':1})==[]


def test_discovery_arriving_after_import_keeps_one_entity(library):
    manager=Plugins(library)
    manager.install(Path(__file__).parents[1]/'plugins/example')
    first=add_work(library,'Same title')
    record={'id':'same','title':'Same title','year':2024,'kind':'movie','url':'https://example.org/same'}
    assert manager.merge('catalog-json',record)==first
    assert len(library.query({'local':False}))==1


def test_explicit_match_merges_discovered_entity(library):
    manager=Plugins(library)
    manager.install(Path(__file__).parents[1]/'plugins/example')
    record={'id':'same','title':'Canonical title','year':2024,'kind':'movie','url':'https://example.org/same'}
    discovered=manager.merge('catalog-json',record)
    local=add_work(library,'Filename guessed')
    library.update_personal(discovered,watchlist=True)
    assert manager.merge('catalog-json',record,local)==local
    assert len(library.query({'local':False}))==1
    assert library.work(local)['sources'][0]['source_id']=='same'
    assert library.work(local)['watchlist']==1


def test_annual_report_uses_real_activity_days(library):
    work_id=add_work(library,'Yearly',metadata={'tags':['Drama']})
    file_id=library.work(work_id)['files'][0]['id']
    with library.db:
        library.db.execute('INSERT INTO sessions VALUES (?,?,?,?,?)',('annual',file_id,'2024-12-31T23:55:00','2025-01-01T00:10:00',900))
        library.db.executemany('INSERT INTO activity VALUES (?,?,?)',[('annual','2024-12-31',300),('annual','2025-01-01',600)])
    assert library.annual_report(2024)['seconds']==300
    report=library.annual_report(2025)
    assert report['seconds']==600 and report['valid']==1 and report['distinct']==1
    assert report['tags']['Drama']==600
    assert library.annual_report(2026)['seconds']==0


def test_cross_language_sources_share_external_identity(library,tmp_path):
    manager=Plugins(library)
    original=Path(__file__).parents[1]/'plugins/example'
    manager.install(original)
    folder=tmp_path/'localized';folder.mkdir()
    manifest=json.loads((original/'manifest.json').read_text());manifest['id']='localized'
    (folder/'manifest.json').write_text(json.dumps(manifest));(folder/'plugin.js').write_text((original/'plugin.js').read_text())
    manager.install(folder)
    first={'id':'one','title':'English title','kind':'movie','year':2024,'url':'https://example.org/one','external_ids':{'imdb':'tt0001'}}
    second={**first,'id':'二','title':'中文片名','url':'https://example.org/two'}
    one=manager.merge('catalog-json',first)
    two=manager.merge('localized',second)
    assert one==two
    assert len(library.work(one)['sources'])==2
    assert library.query({'local':False,'query':'English title'})[0]['id']==one
    assert library.db.execute('SELECT work_id FROM name_keys WHERE key=?',('movie:englishtitle:2024',)).fetchone()[0]==one
    with pytest.raises(ValueError,match='冲突'):
        manager.merge('localized',{**second,'external_ids':{'imdb':'different'}})


def test_failed_merge_rolls_back_discovery_absorption(library,tmp_path):
    manager=Plugins(library);manager.install(Path(__file__).parents[1]/'plugins/example')
    source=manager.merge('catalog-json',{'id':'s','title':'Source','year':2024,'url':'https://example.org/s','external_ids':{'imdb':'source'}})
    target=add_work(library,'Target')
    with library.db:
        library.db.execute('INSERT INTO external_ids VALUES (?,?,?,?)',('movie','imdb','target',target))
    with pytest.raises(ValueError,match='冲突'):
        manager.merge('catalog-json',{'id':'s','title':'Source','year':2024,'url':'https://example.org/s','external_ids':{'imdb':'source'}},target)
    assert library.work(source)['sources'][0]['source_id']=='s'
    assert library.work(target)['files']
    assert len(library.query({'local':False}))==2
