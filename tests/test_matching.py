from pathlib import Path
import json
import time
import pytest
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QDialog, QInputDialog, QMessageBox, QComboBox
from lumen.matching import CandidatePicker, apply_match, preview_cover
from lumen.ui import MainWindow, FilterDialog
from lumen.plugins import Plugins
from test_core import add_work
from test_gallery_downloads import image_site, manager_for


def wait(qapp, predicate):
    deadline=time.monotonic()+8
    while not predicate() and time.monotonic()<deadline:
        qapp.processEvents()
        time.sleep(.01)
    assert predicate()


def test_candidate_grid_shows_title_and_loads_real_cover_without_merging(qapp,library,image_site):
    base,counts=image_site; manager_for(library)
    records=[{'id':'first','title':'First film','year':2024,'url':base+'/first','poster':base+'/image'},
             {'id':'second','title':'Second film','url':base+'/second'}]
    dialog=CandidatePicker(library.directory,'catalog-json',records)
    dialog.show()
    assert not dialog.confirm.isEnabled()
    assert 'First film' in dialog.items.item(0).text()
    assert '来源未提供封面' in dialog.items.item(1).toolTip()
    wait(qapp,lambda: counts.get('/image')==1 and '正在载入' not in dialog.items.item(0).toolTip())
    assert dialog.items.item(0).icon().pixmap(140,190).toImage().pixelColor(50,30).red()>200
    assert library.query({'local':False})==[]
    dialog.items.setCurrentRow(1)
    assert dialog.confirm.isEnabled() and dialog.selection()['id']=='second'
    rect = dialog.items.visualItemRect(dialog.items.item(1))
    QTest.mouseClick(dialog.items.viewport(),Qt.MouseButton.LeftButton,pos=rect.center())
    assert dialog.result()==QDialog.DialogCode.Accepted and not dialog.isVisible()
    with pytest.raises(ValueError):preview_cover(library,'catalog-json',{'poster':'https://unlisted.example/cover.jpg'})
    dialog.close()


def test_selected_candidate_fetches_exact_detail_once_and_honors_locks(qapp,library,monkeypatch):
    manager=manager_for(library)
    work_id=add_work(library,'Original',metadata={'title':'Original','overview':'Keep this',
                        'nfo_fields':['title','overview','actors'],'actors':[{'name':'Old'}]})
    library.edit_metadata(work_id,{},['overview'])
    candidate={'id':'selected','title':'Brief title','url':'http://localhost/selected'}
    detail={**candidate,'title':'Complete title','overview':'Replacement','actors':[{'name':'New'}]}
    calls=[]
    def run(self,plugin,operation,**kwargs):
        calls.append((operation,kwargs));return [detail]
    monkeypatch.setattr(Plugins,'run',run)
    manifest=manager.installed()[0]
    apply_match(library,manifest,'search',candidate,work_id)
    result=library.work(work_id)
    assert result['title']=='Complete title' and result['metadata']['actors'][0]['name']=='New'
    assert result['metadata']['overview']=='Keep this'
    assert calls==[('detail',{'url':candidate['url']})]
    monkeypatch.setattr(Plugins,'run',lambda *args,**kwargs:[{**detail,'id':'different'}])
    with pytest.raises(ValueError,match='不匹配'):apply_match(library,manifest,'search',candidate,work_id)
    assert library.work(work_id)['title']=='Complete title'


@pytest.mark.parametrize('accepted',[True,False])
def test_scrape_selection_updates_same_detail_without_second_confirmation(qapp,tmp_path,monkeypatch,accepted):
    window=MainWindow(tmp_path/'detail-match'); manager_for(window.library)
    work_id=add_work(window.library,'Before')
    window.open_details(work_id,fetch=False)
    original=window.detail_page
    candidate={'id':'chosen','title':'Candidate','url':'http://localhost/chosen'}
    calls=[]
    def run(self,plugin,operation,**kwargs):
        calls.append(operation)
        return [candidate if operation=='search' else {**candidate,'title':'Updated detail'}]
    monkeypatch.setattr(Plugins,'run',run)
    choices=[]
    def choose(*args,**kwargs):
        choices.append(args[1]);return manager_for_name(window.library),True
    def manager_for_name(library):return Plugins(library).installed()[0]['name']
    monkeypatch.setattr(QInputDialog,'getItem',choose)
    monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Query',True))
    pickers=[]
    def pick(dialog):
        assert window.detail_page is original
        assert dialog.records==[candidate]
        pickers.append(dialog);dialog.items.setCurrentRow(0);return QDialog.DialogCode.Accepted if accepted else QDialog.DialogCode.Rejected
    monkeypatch.setattr(CandidatePicker,'exec',pick)
    errors=[];monkeypatch.setattr(QMessageBox,'warning',lambda *args:errors.append(args))
    original.scrape()
    assert window.detail_page is original
    wait(qapp,lambda: not window.jobs)
    assert calls==(['search','detail'] if accepted else ['search']) and len(pickers)==1 and len(choices)==1 and not errors
    assert window.detail_page.work_id==work_id and window.detail_page.work['title']==('Updated detail' if accepted else 'Before')
    assert window.pages.currentWidget() is window.details_scroll
    window.close()


def test_editable_filter_dropdowns_preserve_combined_filter_semantics(qapp,library):
    one=add_work(library,'One',year=2024,metadata={'tags':['Drama','Travel'],'actors':[{'name':'Example actor'}]})
    add_work(library,'Two',year=2020,metadata={'tags':['Other']})
    dialog=FilterDialog({},options=library.filter_options())
    for field in [*dialog.fields.values(),dialog.actor,dialog.numbers['year_min'],dialog.numbers['year_max']]:
        assert isinstance(field,QComboBox) and field.isEditable()
    assert dialog.fields['tags_all'].findText('Drama')>=0
    assert dialog.actor.findText('Example actor')>=0
    dialog.fields['tags_all'].setEditText('Drama, Travel')
    dialog.actor.setEditText('Example actor')
    dialog.numbers['year_min'].setEditText('2024')
    dialog.numbers['year_max'].setEditText('2024')
    filters=dialog.filters()
    assert filters['tags_all']==['Drama','Travel']
    assert [work['id'] for work in library.query(filters)]==[one]
    dialog.show()
    tag = dialog.fields['tags_all']
    tag.lineEdit().clear();tag.lineEdit().setFocus()
    QTest.keyClicks(tag.lineEdit(),'Drama, Tr');qapp.processEvents()
    completer = tag.completer()
    assert completer.completionCount() == 1
    completer.popup().setCurrentIndex(completer.completionModel().index(0,0))
    QTest.keyClick(completer.popup(),Qt.Key.Key_Return);qapp.processEvents()
    assert tag.text() == 'Drama, Travel'
    dialog.close()


def test_manual_match_replaces_nfo_cover_but_preserves_explicit_cover_lock(qapp,library,image_site):
    base,_=image_site;manager=manager_for(library)
    old=library.directory/'cache'/'local-cover.jpg'
    from PySide6.QtGui import QImage,QColor
    picture=QImage(100,150,QImage.Format.Format_RGB32);picture.fill(QColor('blue'));picture.save(str(old))
    work_id=add_work(library,'Local cover',metadata={'nfo_poster':str(old),'nfo_fields':['poster']})
    with library.db:library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(old),work_id))
    record={'id':'cover','title':'Local cover','poster':base+'/image','url':base+'/detail'}
    manager.merge('catalog-json',record,work_id,replace_nfo=True)
    updated=library.work(work_id)
    assert updated['thumbnail']!=str(old) and 'nfo_poster' not in updated['metadata']
    with library.db:library.db.execute('UPDATE works SET thumbnail=?,locked=? WHERE id=?',(str(old),json.dumps(['poster']),work_id))
    manager.merge('catalog-json',record,work_id,replace_nfo=True)
    assert library.work(work_id)['thumbnail']==str(old)


def test_leaving_detail_during_search_does_not_reopen_picker(qapp,tmp_path,monkeypatch):
    import threading
    window=MainWindow(tmp_path/'leave-match');manager_for(window.library)
    work_id=add_work(window.library,'Leave unchanged');window.open_details(work_id,fetch=False)
    proceed=threading.Event()
    def run(*args,**kwargs):
        assert proceed.wait(3)
        return [{'id':'late','title':'Late result','url':'http://localhost/late'}]
    monkeypatch.setattr(Plugins,'run',run)
    monkeypatch.setattr(QInputDialog,'getItem',lambda *args,**kwargs:(Plugins(window.library).installed()[0]['name'],True))
    monkeypatch.setattr(QInputDialog,'getText',lambda *args,**kwargs:('Search',True))
    def unexpected(*args):pytest.fail('A closed detail page must not display search candidates')
    monkeypatch.setattr(CandidatePicker,'exec',unexpected)
    window.detail_page.scrape();window.back_details();proceed.set()
    wait(qapp,lambda:not window.jobs)
    assert window.detail_page is None and window.library.work(work_id)['title']=='Leave unchanged'
    window.close()
