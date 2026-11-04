import copy
import json
from pathlib import Path
from unittest.mock import Mock
import pytest
from PySide6.QtWidgets import QTableWidget,QPushButton
from lumen.plugins import Plugins
from lumen.metadata_health import scan_health,repair_many,retry_images
from lumen.metadata_health_ui import show_metadata_health
from lumen.ui import MainWindow
from test_actor_plugins import portrait
from test_gallery_downloads import manager_for, image_site


def work(library,tmp_path,title='ABC-123'):
    root=tmp_path/title;root.mkdir();(root/(title+'.mp4')).write_bytes(title.encode())
    library.import_folder(root,'vr',fast=True)
    identifier=library.query({'folder':str(root)})[0]['id']
    if not any(plugin['id']=='catalog-json' for plugin in Plugins(library).installed()):manager_for(library)
    library.set_setting('partition:vr',{'plugin':'catalog-json'})
    return identifier


def record(title='ABC-123'):
    return {'id':title,'title':title,'kind':'movie','url':'http://localhost/'+title,
        'overview':'From provider','tags':['Provider tag'],'actors':[{'name':'Performer','gender':'female','photo':'http://localhost/actor.png'}],
        'poster':'http://localhost/poster.png','stills':['http://localhost/still.png']}


def raw(library,identifier):return json.loads(library.db.execute('SELECT metadata FROM works WHERE id=?',(identifier,)).fetchone()[0])


def test_only_missing_fields_are_filled_and_successful_images_not_downloaded_twice(library,qapp,tmp_path,monkeypatch):
    identifier=work(library,tmp_path)
    library.edit_metadata(identifier,{'overview':'Manual overview','tags':['Local tag']},[])
    library.update_personal(identifier,favorite=True,rating=9)
    metadata_calls=[];image_calls=[];picture=portrait(qapp)
    def run(self,plugin,operation,**kw):metadata_calls.append(operation);return [record()]
    def fetch(self,plugin,url,image=False):image_calls.append(url);return picture,'image/png'
    monkeypatch.setattr(Plugins,'run',run);monkeypatch.setattr(Plugins,'fetch',fetch)
    first=repair_many(library,[identifier])
    assert first['updated']==1 and first['images']==3 and not first['failed']
    saved=library.work(identifier)
    assert saved['kind']=='vr' and saved['title']=='ABC-123' and saved['favorite'] and saved['rating']==9
    assert saved['metadata']['overview']=='Manual overview' and saved['metadata']['tags']==['Local tag']
    assert Path(saved['thumbnail']).is_file() and Path(saved['metadata']['actors'][0]['photo_cache']).is_file()
    assert len(image_calls)==3 and metadata_calls==['search','detail']
    second=repair_many(library,[identifier]);assert not second['updated'] and not second['images']
    assert len(image_calls)==3 and len(metadata_calls)==2
    assert scan_health(library)['items']==[]


def test_locked_empty_fields_nfo_and_custom_poster_are_protected(library,qapp,tmp_path,monkeypatch):
    identifier=work(library,tmp_path)
    local=tmp_path/'poster.jpg';local.write_bytes(portrait(qapp))
    library.edit_metadata(identifier,{'overview':'','tags':[],'actors':[], 'nfo_fields':['overview']},['tags','actors'])
    library.set_setting(f'artwork_{identifier}',{'poster':str(local)})
    before=raw(library,identifier)
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:pytest.fail('all missing fields are protected'))
    monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:pytest.fail('custom image must not download'))
    report=scan_health(library)['items'][0]
    assert set(report['locked'])=={'overview','tags','actors'}
    result=repair_many(library,[identifier])
    assert result['updated']==0 and raw(library,identifier)==before


def test_image_failure_is_independently_retryable_without_repeat_metadata_or_good_images(library,qapp,tmp_path,monkeypatch):
    identifier=work(library,tmp_path);picture=portrait(qapp);calls=[]
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:[record()])
    failed=[True]
    def fetch(self,plugin,url,image=False):
        calls.append(url)
        if '/actor.png' in url and failed[0]:raise OSError('network unavailable')
        return picture,'image/png'
    monkeypatch.setattr(Plugins,'fetch',fetch)
    first=repair_many(library,[identifier]);assert first['images']==2 and first['failed']==1
    assert library.db.execute("SELECT COUNT(*) FROM tasks WHERE kind='health-image' AND status='failed'").fetchone()[0]==1
    failed[0]=False
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:pytest.fail('image-only retry must not scrape metadata'))
    second=repair_many(library,[identifier],images_only=True)
    assert second['images']==1 and not second['failed']
    assert calls==['http://localhost/poster.png','http://localhost/actor.png','http://localhost/still.png','http://localhost/actor.png']
    assert library.db.execute("SELECT COUNT(*) FROM tasks WHERE kind='health-image' AND status='failed'").fetchone()[0]==0


def test_background_changes_during_download_are_not_overwritten(library,qapp,tmp_path,monkeypatch):
    identifier=work(library,tmp_path);picture=portrait(qapp)
    candidate=record();candidate.pop('actors');candidate.pop('stills')
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:[candidate])
    other=type(library)(library.directory)
    try:
        def fetch(self,plugin,url,image=False):
            # A separate connection can write because network I/O holds no write transaction.
            other.edit_metadata(identifier,{'overview':'Concurrent edit'},['poster'])
            return picture,'image/png'
        monkeypatch.setattr(Plugins,'fetch',fetch)
        repair_many(library,[identifier])
        saved=library.work(identifier)
        assert saved['metadata']['overview']=='Concurrent edit' and not saved['thumbnail']
        assert 'poster' in saved['locked']
    finally:other.close()


def test_wrong_detail_id_and_ambiguous_search_do_not_fill(library,tmp_path,monkeypatch):
    identifier=work(library,tmp_path)
    before=raw(library,identifier)
    def run(self,plugin,operation,**kwargs):return [record()] if operation=='search' else [record('XYZ-999')]
    monkeypatch.setattr(Plugins,'run',run)
    result=repair_many(library,[identifier]);assert result['failed']==1 and result['updated']==0
    assert raw(library,identifier)==before
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:[record(),dict(record(),id='another')])
    assert repair_many(library,[identifier])['updated']==0


def test_cancellation_keeps_already_completed_work(library,qapp,tmp_path,monkeypatch):
    one=work(library,tmp_path,'ABC-123');two=work(library,tmp_path,'XYZ-456')
    monkeypatch.setattr(Plugins,'run',lambda self,p,operation,**kw:[record('XYZ-456' if 'XYZ' in str(kw) else 'ABC-123')])
    picture=portrait(qapp);monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:(picture,'image/png'))
    stop=[False]
    def progress(*args):stop[0]=True
    result=repair_many(library,[one,two],progress=progress,cancelled=lambda:stop[0])
    assert result['stopped'] and result['updated']==1
    assert raw(library,one)['overview']=='From provider' and not raw(library,two).get('overview')


def test_panel_scans_and_image_only_action_uses_selected_work(qapp,tmp_path):
    window=MainWindow(tmp_path/'data');identifier=work(window.library,tmp_path)
    calls=[]
    try:
        def run_job(title,function,callback=None,**kw):
            calls.append((title,function,callback))
            if title=='检查缺失影片资料':callback(scan_health(window.library))
        window.run_job=run_job
        dialog=show_metadata_health(window);table=dialog.findChild(QTableWidget,'metadataHealthTable')
        assert table.rowCount()==1 and '简介' in table.item(0,1).text()
        table.selectRow(0);dialog.findChild(QPushButton,'retryMissingImages').click()
        assert calls[-1][0]=='重试缺失图片'
        result=calls[-1][1](window.library,type('Progress',(),{'__call__':lambda *a:None,'cancelled':lambda self:False})())
        assert result['items'][0]['id']==identifier
        dialog.close();qapp.processEvents()
    finally:window.close()


def test_image_retry_uses_real_host_fetch_and_cached_success(library,qapp,tmp_path,monkeypatch,image_site):
    base,counts=image_site
    identifier=work(library,tmp_path)
    library.edit_metadata(identifier,{'poster':base+'/image'},[])
    first=retry_images(library,identifier)
    assert first['updated']==1 and first['errors']==[] and counts['/image']==1
    assert Path(library.work(identifier)['thumbnail']).read_bytes().startswith(b'\xff\xd8')
    assert retry_images(library,identifier)['updated']==0 and counts['/image']==1


def test_protected_actor_photo_is_not_replaced_and_disabled_provider_is_reported(library,qapp,tmp_path,monkeypatch):
    identifier=work(library,tmp_path)
    library.edit_metadata(identifier,{'actors':[{'name':'Performer','photo':'http://localhost/photo'}]},['actors'])
    monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:pytest.fail('locked actor must not fetch'))
    assert retry_images(library,identifier)=={'updated':0,'skipped':1,'errors':[]}
    library.edit_metadata(identifier,{'poster':'http://localhost/poster'},['actors'])
    Plugins(library).configure('catalog-json',{'enabled':False})
    result=retry_images(library,identifier)
    assert len(result['errors'])==1 and '已启用' in result['errors'][0]['error']


def test_generated_video_frame_does_not_hide_missing_poster(library,qapp,tmp_path,monkeypatch):
    identifier=work(library,tmp_path);picture=portrait(qapp)
    file=library.work(identifier)['files'][0]
    frame=library.directory/'cache'/(file['digest']+'.jpg');frame.write_bytes(picture)
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(frame),identifier))
    assert 'poster' in scan_health(library)['items'][0]['missing']
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:[record()])
    monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:(picture,'image/png'))
    assert repair_many(library,[identifier])['images']==3
    assert library.work(identifier)['thumbnail']!=str(frame) and frame.is_file()
    assert scan_health(library)['items']==[]


def test_nfo_poster_marker_is_boolean_and_preserves_cached_nfo_image(library,qapp,tmp_path,monkeypatch):
    identifier=work(library,tmp_path);picture=portrait(qapp)
    cached=library.directory/'cache'/'nfo.jpg';cached.write_bytes(picture)
    library.edit_metadata(identifier,{'nfo_poster':True,'poster':'http://localhost/poster'},[])
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(cached),identifier))
    monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:pytest.fail('NFO poster must be retained'))
    assert retry_images(library,identifier)['updated']==0
    assert 'poster' not in scan_health(library)['items'][0]['missing']


def test_numbered_fallback_setting_is_used_when_primary_unavailable(library,qapp,tmp_path,monkeypatch):
    identifier=work(library,tmp_path)
    library.set_setting('partition:vr',{'plugin':'disabled'})
    library.set_setting('numbered_fallbacks:vr',['catalog-json'])
    monkeypatch.setattr(Plugins,'run',lambda *a,**k:[record()])
    picture=portrait(qapp);monkeypatch.setattr(Plugins,'fetch',lambda *a,**k:(picture,'image/png'))
    assert repair_many(library,[identifier])['updated']==1


def test_same_source_id_with_wrong_detail_product_code_is_rejected(library,tmp_path,monkeypatch):
    identifier=work(library,tmp_path);before=raw(library,identifier)
    def run(self,plugin,operation,**kw):
        value=record()
        if operation=='detail':value['external_ids']={'product_code':'ABC-124'}
        return [value]
    monkeypatch.setattr(Plugins,'run',run)
    result=repair_many(library,[identifier])
    assert result['failed']==1 and result['updated']==0 and raw(library,identifier)==before
