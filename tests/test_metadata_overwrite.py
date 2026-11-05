from pathlib import Path

import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QWidget, QLabel, QComboBox, QTableWidget, QPushButton, QMessageBox

from lumen.core import Library, now
from lumen.metadata_health import repair_many, scan_health
from lumen.metadata_health_ui import show_metadata_health
from lumen.plugins import Plugins
from lumen.artwork import thumbnail_path
from test_core import add_work
from test_gallery_downloads import manager_for
from test_javinizer_artwork import image_bytes


def candidate(**changes):
    return {'id':'ABC-123','kind':'movie','title':'ABC-123 New title','year':2025,
            'url':'https://example.test/detail','overview':'New overview','tags':['New tag'],
            'actors':[{'name':'New actor','gender':'female'}], 'directors':['New director'],
            'poster':'https://example.test/poster','cover':'https://example.test/cover',
            'stills':['https://example.test/still'], 'external_ids':{'product_code':'ABC-123'},
            'rating':8.3, **changes}


def setup(library, tmp_path, monkeypatch):
    manager_for(library)
    library.set_setting('partition:vr',{'plugin':'catalog-json'})
    old=library.directory/'cache/old.jpg';old.write_bytes(image_bytes(tmp_path,'old',(200,300),'blue'))
    identifier=add_work(library,'ABC-123',kind='vr',metadata={
        'overview':'Old overview','tags':['Old tag'],'actors':[{'name':'Old actor'}],
        'directors':['Old director'],'aliases':['Old alias'],'nfo_poster':True,
        'nfo_fields':['title','year','overview','actors','tags'],
        'nfo_stills':[str(old)],'nfo_thumbnails':{'1':str(old)},'nfo_backdrop':str(old),
        'episode_details':{'1':{'overview':'Old episode'}},'episode_stills':{'1':[str(old)]}})
    library.edit_metadata(identifier,{},['title','year','overview','tags','actors','poster'])
    with library.db:
        library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(old),identifier))
    library.set_setting(f'artwork_{identifier}',{'poster':str(old),'thumbnail':str(old)})
    library.update_personal(identifier,rating=9,favorite=True,watchlist=True)
    picture=image_bytes(tmp_path,'new',(640,360),'red')
    calls=[]
    def run(self,plugin,operation,**kw):
        calls.append((operation,kw));return [candidate()]
    monkeypatch.setattr(Plugins,'run',run)
    monkeypatch.setattr(Plugins,'fetch',lambda *a,**kw:(picture,'image/png'))
    return identifier,old,calls


def presentation(library,identifier):
    row=dict(library.db.execute('SELECT * FROM works WHERE id=?',(identifier,)).fetchone())
    return row,library.setting(f'artwork_{identifier}',{})


def test_force_replaces_locked_nfo_and_custom_ui_but_keeps_personal_and_playback(library,qapp,tmp_path,monkeypatch):
    identifier,old,calls=setup(library,tmp_path,monkeypatch)
    file=library.work(identifier)['files'][0]
    with library.db:
        library.db.execute('UPDATE files SET position=42 WHERE id=?',(file['id'],))
        library.db.execute('INSERT INTO sessions(id,file_id,started,watched) VALUES (?,?,?,?)',('session',file['id'],now(),700))
        library.db.execute('INSERT INTO bookmarks(id,file_id,position,title,created) VALUES (?,?,?,?,?)',('bookmark',file['id'],30,'Keep',now()))
    before={table:[tuple(row) for row in library.db.execute('SELECT * FROM '+table)] for table in ('files','sessions','bookmarks')}
    personal={key:library.work(identifier)[key] for key in ('rating','favorite','liked','disliked','watchlist')}
    # Ordinary missing-only repair must still respect every protection.
    assert repair_many(library,[identifier])['updated']==0
    assert not calls
    result=repair_many(library,[identifier],force=True)
    assert result['updated']==1 and not result['failed'] and result['images']==3
    work=library.work(identifier);metadata=work['metadata']
    assert work['kind']=='vr' and work['title']=='ABC-123 New title' and work['year']==2025
    assert metadata['tags']==['New tag'] and metadata['actors'][0]['name']=='New actor'
    assert metadata['overview']=='New overview' and metadata['directors']==['New director']
    assert not metadata.get('aliases') and not work['locked']
    assert all(not key.startswith('nfo_') and not key.startswith('episode_') for key in metadata)
    assert not library.setting(f'artwork_{identifier}') and work['thumbnail']!=str(old)
    assert QImage(work['thumbnail']).width()/QImage(work['thumbnail']).height()==pytest.approx(2/3,abs=.01)
    assert QImage(thumbnail_path(library,work)).width()==640
    assert old.is_file() and {key:work[key] for key in personal}==personal
    assert work['sources'][0]['rating']==8.3
    for table,rows in before.items():assert [tuple(row) for row in library.db.execute('SELECT * FROM '+table)]==rows
    assert all(parameters['refresh'] for _,parameters in calls)
    reopened=Library(library.directory)
    try:
        assert reopened.work(identifier)['title']==work['title']
        assert reopened.work(identifier)['rating']==9 and not reopened.setting(f'artwork_{identifier}')
    finally:reopened.close()


def test_force_clears_missing_source_fields_instead_of_merging_old_values(library,qapp,tmp_path,monkeypatch):
    identifier,old,_=setup(library,tmp_path,monkeypatch)
    minimal={'id':'ABC-123','title':'ABC-123','kind':'movie','url':'https://example.test/detail',
             'tags':[],'actors':[],'overview':''}
    monkeypatch.setattr(Plugins,'run',lambda *a,**kw:[minimal])
    result=repair_many(library,[identifier],force=True)
    work=library.work(identifier)
    assert result['updated']==1 and not result['failed']
    assert work['year'] is None and work['thumbnail'] is None
    assert work['metadata']['tags']==[] and work['metadata']['actors']==[] and work['metadata']['overview']==''
    assert not work['metadata'].get('directors') and not work['metadata'].get('nfo_poster')
    assert work['favorite'] and work['rating']==9 and old.is_file()


@pytest.mark.parametrize('failure',['network','ambiguous','wrong_code','linked_elsewhere'])
def test_failed_force_keeps_entire_presentation(library,qapp,tmp_path,monkeypatch,failure):
    identifier,_,_=setup(library,tmp_path,monkeypatch)
    if failure=='linked_elsewhere':
        other=add_work(library,'Other')
        with library.db:
            library.db.execute('INSERT INTO sources VALUES (?,?,?,?,?,?,?,?)',
                               (other,'catalog-json','Example','ABC-123','https://example.test/detail',now(),None,3))
    before=presentation(library,identifier)
    def run(*a,**kw):
        if failure=='network':raise OSError('Network unavailable')
        if failure=='ambiguous':return [candidate(),candidate(id='second')]
        if failure=='wrong_code':return [candidate(id='XYZ-999',title='XYZ-999',external_ids={'product_code':'XYZ-999'})]
        return [candidate()]
    monkeypatch.setattr(Plugins,'run',run)
    result=repair_many(library,[identifier],force=True)
    assert result['failed']==1 and not result['updated']
    assert presentation(library,identifier)==before


def test_partial_image_failure_is_reported_and_retryable(library,qapp,tmp_path,monkeypatch):
    identifier,_,_=setup(library,tmp_path,monkeypatch)
    def fetch(self,plugin,url,image=False):
        if url.endswith('/poster'):raise OSError('HTTP 403')
        return image_bytes(tmp_path,'new',(640,360),'red'),'image/png'
    monkeypatch.setattr(Plugins,'fetch',fetch)
    result=repair_many(library,[identifier],force=True)
    assert result['updated']==1 and result['failed']==1 and '403' in result['items'][0]['errors'][0]
    assert QImage(library.work(identifier)['thumbnail']).width()>0


@pytest.mark.parametrize('during',['metadata','artwork','cancel'])
def test_force_does_not_erase_concurrent_edits_or_commit_after_cancel(library,qapp,tmp_path,monkeypatch,during):
    identifier,old,_=setup(library,tmp_path,monkeypatch)
    before=presentation(library,identifier);stop=[False];done=[False]
    def fetch(self,plugin,url,image=False):
        assert not library.db.in_transaction
        if not done[0]:
            done[0]=True
            other=Library(library.directory)
            try:
                if during=='metadata':other.edit_metadata(identifier,{'overview':'Concurrent'},['poster'])
                elif during=='artwork':other.set_setting(f'artwork_{identifier}',{'poster':str(old)})
                else:stop[0]=True
            finally:other.close()
        return old.read_bytes(),'image/png'
    monkeypatch.setattr(Plugins,'fetch',fetch)
    result=repair_many(library,[identifier],force=True,cancelled=lambda:stop[0])
    assert not result['updated']
    if during=='cancel':
        assert result['stopped'] and presentation(library,identifier)==before
    else:
        assert result['failed']==1
        if during=='metadata':assert library.work(identifier)['metadata']['overview']=='Concurrent'
        else:assert library.setting(f'artwork_{identifier}')=={'poster':str(old)}


def test_same_image_url_is_fetched_again_in_force_mode(library,qapp,tmp_path,monkeypatch):
    identifier,_,_=setup(library,tmp_path,monkeypatch)
    assert repair_many(library,[identifier],force=True)['updated']==1
    old_cover=thumbnail_path(library,library.work(identifier));original=Path(old_cover).read_bytes()
    calls=[]
    def fetch(self,plugin,url,image=False):
        calls.append(url);return image_bytes(tmp_path,'updated',(640,360),'green'),'image/png'
    monkeypatch.setattr(Plugins,'fetch',fetch)
    assert repair_many(library,[identifier],force=True)['updated']==1
    new_cover=thumbnail_path(library,library.work(identifier))
    assert len(calls)==3 and new_cover!=old_cover and Path(old_cover).read_bytes()==original
    assert QImage(new_cover).pixelColor(20,20).green()>100


def test_force_keeps_personal_changes_made_during_image_download(library,qapp,tmp_path,monkeypatch):
    identifier,old,_=setup(library,tmp_path,monkeypatch)
    def fetch(self,plugin,url,image=False):
        other=Library(library.directory)
        try:other.update_personal(identifier,rating=7,favorite=False,disliked=True)
        finally:other.close()
        return old.read_bytes(),'image/png'
    monkeypatch.setattr(Plugins,'fetch',fetch)
    assert repair_many(library,[identifier],force=True)['updated']==1
    work=library.work(identifier)
    assert work['rating']==7 and work['disliked'] and not work['favorite']


def test_artwork_changed_during_source_query_is_preserved(library,qapp,tmp_path,monkeypatch):
    identifier,old,_=setup(library,tmp_path,monkeypatch)
    def run(*args,**kwargs):
        library.set_setting(f'artwork_{identifier}',{'poster':str(old)})
        return [candidate()]
    monkeypatch.setattr(Plugins,'run',run)
    result=repair_many(library,[identifier],force=True)
    assert result['failed']==1 and not result['updated']
    assert library.setting(f'artwork_{identifier}')=={'poster':str(old)}


def test_force_javinizer_refreshes_metadata_and_repairs_cover_only_artwork(library,qapp,tmp_path,monkeypatch):
    from lumen import javinizer as engine
    from test_javinizer import raw
    from test_javinizer_artwork import COVER
    engine.save_settings(library,{'enabled':True})
    library.set_setting('partition:vr',{'plugin':engine.ENGINE_ID})
    identifier=add_work(library,'IPX-535',kind='vr')
    engine._cache_result(library,'r18dev','IPX-535',engine.metadata(raw(title='Old title'),'r18dev','IPX-535'))
    monkeypatch.setattr(engine,'verified_executable',lambda *a:tmp_path/'engine.exe')
    calls=[]
    def query(*args):
        calls.append(args[2])
        return engine.metadata(raw(title='New title',poster_url='',cover_url=COVER,
                                   screenshot_urls=[],actresses=[]),'r18dev','IPX-535')
    monkeypatch.setattr(engine,'query_source',query)
    picture=image_bytes(tmp_path,'wide',(640,360),'red')
    downloads=[]
    def fetch(*args,**kwargs):
        assert not library.db.in_transaction
        downloads.append(args[2]);return picture,'image/png'
    monkeypatch.setattr(Plugins,'fetch',fetch)
    result=repair_many(library,[identifier],force=True)
    work=library.work(identifier)
    assert result['updated']==1 and not result['failed']
    assert calls==['r18dev'] and downloads==[COVER] and work['title']=='New title'
    assert work['kind']=='vr' and QImage(thumbnail_path(library,work)).width()==640
    assert QImage(work['thumbnail']).width()/QImage(work['thumbnail']).height()==pytest.approx(2/3,abs=.01)


def test_force_panel_lists_complete_films_and_requires_scope_confirmation(library,qapp,tmp_path,monkeypatch):
    identifier,_,_=setup(library,tmp_path,monkeypatch)
    # Make it complete even though its values remain protected.
    library.edit_metadata(identifier,{'poster':'https://example.test/poster'},['poster'])
    assert scan_health(library)['items']==[]
    assert [item['id'] for item in scan_health(library,include_complete=True)['items']]==[identifier]
    host=QWidget();host.library=library;host.section='vr';host.detail_page=None;host.status=QLabel(host)
    calls=[]
    class Progress:
        def __call__(self,*args):pass
        def cancelled(self):return False
    def run_job(title,job,callback):
        calls.append((title,job))
        if title=='检查缺失影片资料':callback(job(library,Progress()))
    host.run_job=run_job
    dialog=show_metadata_health(host)
    try:
        table=dialog.findChild(QTableWidget,'metadataHealthTable')
        assert table.rowCount()==0
        dialog.findChild(QComboBox,'metadataRepairMode').setCurrentIndex(1)
        assert table.rowCount()==1
        assert not dialog.findChild(QPushButton,'retryMissingImages').isEnabled()
        decisions=[QMessageBox.StandardButton.Cancel,QMessageBox.StandardButton.Yes]
        def confirm(box):
            assert '1 部' in box.text() and '个人评分' in box.informativeText()
            assert box.detailedText()=='ABC-123'
            return decisions.pop(0)
        monkeypatch.setattr(QMessageBox,'exec',confirm)
        button=dialog.findChild(QPushButton,'repairMissingMetadata')
        button.click();assert calls[-1][0]=='检查缺失影片资料'
        table.selectRow(0);button.click();assert calls[-1][0]=='强制更新影片资料'
        recorded=[]
        monkeypatch.setattr('lumen.metadata_health_ui.repair_many',lambda lib,ids,**kw:recorded.append((ids,kw)) or {})
        calls[-1][1](library,Progress())
        assert recorded[0][0]==[identifier] and recorded[0][1]['force']
    finally:
        dialog.close();qapp.processEvents();host.close()


def test_force_and_image_only_cannot_be_combined(library):
    with pytest.raises(ValueError):repair_many(library,[],force=True,images_only=True)
