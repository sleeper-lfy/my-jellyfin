import pytest
from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox, QPushButton

from lumen import javinizer
from lumen.matching import apply_match, CandidatePicker, MatchConflictDialog
from lumen.plugins import Plugins
from lumen.ui import MainWindow
from test_core import add_work
from test_gallery_downloads import manager_for
from test_metadata_overwrite import setup, candidate, presentation
from test_matching import wait
from test_javinizer import raw


def test_historical_external_id_aliases_do_not_block_repeated_scraping(library):
    manager=manager_for(library)
    identifier=add_work(library,'IPX-535')
    with library.db:
        for value in ('ipx00535','ipx535'):
            library.db.execute('INSERT INTO external_ids VALUES (?,?,?,?)',('movie','dmm',value,identifier))
    record={'id':'same','title':'IPX-535','year':2024,'url':'http://localhost/same','external_ids':{'dmm':'ipx00535'}}
    for _ in range(2):
        assert apply_match(library,manager.installed()[0],'detail',record,identifier)==identifier
    assert len(library.work(identifier)['sources'])==1


@pytest.mark.parametrize('choice',['keep','replace'])
def test_changed_identifier_requires_choice_and_respects_it(library,qapp,tmp_path,monkeypatch,choice):
    identifier,_,_=setup(library,tmp_path,monkeypatch)
    with library.db:
        library.db.execute('INSERT INTO external_ids VALUES (?,?,?,?)',('vr','product_code','OLD-123',identifier))
    manifest=Plugins(library).installed()[0];before=presentation(library,identifier)
    pending=apply_match(library,manifest,'detail',candidate(),identifier,interactive=True)
    assert pending['conflict']['stored']['product_code']=='OLD-123'
    assert pending['conflict']['incoming']['product_code']=='ABC-123'
    assert presentation(library,identifier)==before
    # Cancelling the dialog does not mutate anything.
    dialog=MatchConflictDialog(pending['conflict']);dialog.reject()
    assert presentation(library,identifier)==before
    result=apply_match(library,manifest,'detail',pending['candidate'],identifier,interactive=True,
                       resolution=choice,snapshot=pending['snapshot'])
    assert not isinstance(result,dict) or 'conflict' not in result
    work=library.work(identifier)
    expected='OLD-123' if choice=='keep' else 'ABC-123'
    assert work['metadata']['external_ids']['product_code']==expected
    assert library.db.execute('SELECT value FROM external_ids WHERE work_id=?',(identifier,)).fetchone()[0]==expected
    assert work['rating']==9 and work['favorite']
    if choice=='replace':
        assert work['title']=='ABC-123 New title' and not work['locked']
        assert apply_match(library,manifest,'detail',candidate(),identifier,interactive=True)==identifier


def test_conflict_with_another_local_work_offers_preview_and_never_reassigns_ids(library,qapp,tmp_path,monkeypatch):
    identifier,_,_=setup(library,tmp_path,monkeypatch)
    other=add_work(library,'Another local film',kind='vr')
    with library.db:library.db.execute('INSERT INTO external_ids VALUES (?,?,?,?)',('vr','product_code','ABC-123',other))
    manifest=Plugins(library).installed()[0]
    pending=apply_match(library,manifest,'detail',candidate(),identifier,force=True,interactive=True)
    assert pending['conflict']['related'][0]['id']==other and pending['conflict']['can_merge']
    dialog=MatchConflictDialog(pending['conflict'])
    assert dialog.findChild(QPushButton,'matchConflict:merge') is not None
    assert dialog.findChild(QPushButton,'matchConflict:replace') is None
    with pytest.raises(ValueError,match='关联其他影片'):
        apply_match(library,manifest,'detail',candidate(),identifier,force=True,resolution='replace')
    assert library.db.execute('SELECT work_id FROM external_ids WHERE value=?',('ABC-123',)).fetchone()[0]==other
    assert library.work(other)['files']


def test_conflict_choice_rejects_edits_made_while_dialog_was_open(library,qapp,tmp_path,monkeypatch):
    identifier,_,_=setup(library,tmp_path,monkeypatch)
    with library.db:library.db.execute('INSERT INTO external_ids VALUES (?,?,?,?)',('vr','product_code','OLD-123',identifier))
    manifest=Plugins(library).installed()[0]
    pending=apply_match(library,manifest,'detail',candidate(),identifier,interactive=True)
    library.edit_metadata(identifier,{'overview':'New edit'},['overview'])
    with pytest.raises(ValueError,match='选择期间'):
        apply_match(library,manifest,'detail',candidate(),identifier,resolution='replace',snapshot=pending['snapshot'])
    assert library.work(identifier)['metadata']['overview']=='New edit'


@pytest.mark.parametrize('kind,expected',[('movie','javinizer-go'),('vr','javinizer-go'),('series','catalog-json')])
def test_manual_source_default_prefers_javinizer_only_for_movies(qapp,tmp_path,monkeypatch,kind,expected):
    window=MainWindow(tmp_path/'default-source')
    try:
        manager_for(window.library);javinizer.save_settings(window.library,{'enabled':True})
        # The generic plugin has the earlier priority, so the selected index matters.
        Plugins(window.library).configure('catalog-json',{'priority':1})
        identifier=add_work(window.library,'Title',kind=kind);window.open_details(identifier,fetch=False)
        chosen=[]
        def select(parent,title,label,names,index,editable):
            chosen.append(names[index]);return names[index],False
        monkeypatch.setattr(QInputDialog,'getItem',select)
        window.detail_page.scrape()
        assert chosen==[next(p['name'] for p in Plugins(window.library).installed() if p['id']==expected)]
    finally:window.close()


def test_gui_force_can_refresh_same_javinizer_work_twice(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'twice')
    try:
        javinizer.save_settings(window.library,{'enabled':True})
        identifier=add_work(window.library,'IPX-535',metadata={'overview':'Locked'},kind='movie')
        window.library.edit_metadata(identifier,{},['overview']);window.library.update_personal(identifier,rating=8,favorite=True)
        monkeypatch.setattr(javinizer,'verified_executable',lambda *a:tmp_path/'engine.exe')
        count=[]
        def query(*args):
            count.append(True)
            return javinizer.metadata(raw(title='Updated '+str(len(count)),poster_url='',cover_url='',screenshot_urls=[],actresses=[]),'r18dev','IPX-535')
        monkeypatch.setattr(javinizer,'query_source',query)
        monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**k:(a[3][a[4]],True))
        monkeypatch.setattr(QInputDialog,'getText',lambda *a,**k:('IPX-535',True))
        def pick(dialog):
            assert dialog.force is not None
            dialog.force.setChecked(True);dialog.items.setCurrentRow(0);return QDialog.DialogCode.Accepted
        monkeypatch.setattr(CandidatePicker,'exec',pick)
        errors=[];monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a))
        for index in (1,2):
            window.open_details(identifier,fetch=False);window.detail_page.scrape()
            wait(qapp,lambda:not window.jobs and not window.job_queue)
            assert window.library.work(identifier)['title']=='Updated '+str(index)
        assert len(count)==2 and not errors
        assert window.library.work(identifier)['rating']==8 and window.library.work(identifier)['favorite']
    finally:window.close()


@pytest.mark.parametrize('choice',['keep','replace',None])
def test_gui_conflict_choice_is_used_without_a_generic_error_popup(qapp,tmp_path,monkeypatch,choice):
    window=MainWindow(tmp_path/'conflict-choice')
    try:
        manager_for(window.library)
        identifier=add_work(window.library,'Old title',metadata={'external_ids':{'imdb':'old'}})
        with window.library.db:window.library.db.execute('INSERT INTO external_ids VALUES (?,?,?,?)',('movie','imdb','old',identifier))
        window.open_details(identifier,fetch=False)
        record={'id':'candidate','title':'Updated title','url':'http://localhost/candidate','external_ids':{'imdb':'new'}}
        monkeypatch.setattr(Plugins,'run',lambda *a,**kw:[record])
        monkeypatch.setattr(QInputDialog,'getItem',lambda *a,**kw:(a[3][a[4]],True))
        monkeypatch.setattr(QInputDialog,'getText',lambda *a,**kw:('Search',True))
        def pick(dialog):
            dialog.items.setCurrentRow(0);return QDialog.DialogCode.Accepted
        monkeypatch.setattr(CandidatePicker,'exec',pick)
        choices=[]
        def resolve(dialog):
            choices.append(True);dialog.choice=choice
            return QDialog.DialogCode.Rejected if choice is None else QDialog.DialogCode.Accepted
        monkeypatch.setattr(MatchConflictDialog,'exec',resolve)
        errors=[];monkeypatch.setattr(QMessageBox,'warning',lambda *a:errors.append(a))
        window.detail_page.scrape();wait(qapp,lambda:not window.jobs and not window.job_queue)
        assert choices==[True] and not errors
        work=window.library.work(identifier)
        assert work['metadata']['external_ids']['imdb']==('new' if choice=='replace' else 'old')
        assert work['title']==('Old title' if choice is None else 'Updated title')
    finally:window.close()
