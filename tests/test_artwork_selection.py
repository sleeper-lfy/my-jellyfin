import time
from pathlib import Path
import pytest
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QImage, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QLabel, QDialog, QSpinBox, QDialogButtonBox
from lumen.artwork_ui import crop_image, save_artwork, artwork_paths, ArtworkDialog
from lumen.core import Library
from lumen.ui import MainWindow, poster_regions
from test_core import add_work


@pytest.fixture(autouse=True)
def finish_image_reads(qapp):
    yield
    from lumen.images import image_cache
    cache=image_cache()
    wait_for(lambda:not cache.active and not cache.waiting)
    qapp.processEvents()


def picture(path):
    image=QImage(900,300,QImage.Format.Format_RGB32)
    for x in range(900):
        color=QColor('red' if x<300 else 'green' if x<600 else 'blue')
        for y in range(300):image.setPixelColor(x,y,color)
    assert image.save(str(path))
    return image


def wait_for(predicate):
    deadline=time.monotonic()+5
    while not predicate() and time.monotonic()<deadline:QTest.qWait(10)
    assert predicate()


@pytest.mark.parametrize('anchor,color',[('left','red'),('center','green'),('right','blue')])
def test_crop_keeps_selected_region_and_original(anchor,color,tmp_path):
    image=picture(tmp_path/'source.png')
    result=crop_image(image,'poster',anchor)
    assert (result.width(),result.height())==(200,300)
    assert result.pixelColor(100,150)==QColor(color)
    assert (image.width(),image.height())==(900,300)


def test_artwork_roles_survive_reopen_and_failure_preserves_selection(qapp,tmp_path):
    library=Library(tmp_path/'data');work_id=add_work(library,'Artwork')
    source=tmp_path/'source.png';picture(source);original=source.read_bytes()
    save_artwork(library,work_id,source,'poster','right')
    save_artwork(library,work_id,source,'thumbnail','center')
    selected=library.setting(f'artwork_{work_id}')
    assert QImage(selected['poster']).size().width()==200
    assert QImage(selected['poster']).pixelColor(100,150).blue()>240
    thumb=QImage(selected['thumbnail']);assert abs(thumb.width()/thumb.height()-16/9)<.01
    with pytest.raises(ValueError):save_artwork(library,work_id,tmp_path/'missing.jpg','poster','left')
    assert library.setting(f'artwork_{work_id}')==selected and source.read_bytes()==original
    library.close();library=Library(tmp_path/'data')
    assert library.setting(f'artwork_{work_id}')==selected
    library.close()


def test_no_stills_can_use_thumbnail_and_cancel_does_not_save(qapp,tmp_path):
    window=MainWindow(tmp_path/'ui');work_id=add_work(window.library,'Copy <title> & 中文')
    source=tmp_path/'thumb.png';picture(source)
    with window.library.db:window.library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(source),work_id))
    work=window.library.work(work_id)
    assert artwork_paths(window.library,work)==[str(source)]
    dialog=ArtworkDialog(window,work);dialog.show()
    wait_for(lambda:dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled())
    dialog.anchor.setCurrentIndex(dialog.anchor.findData('right'))
    dialog.reject();assert not window.library.setting(f'artwork_{work_id}')
    dialog.deleteLater()
    window.show();window.open_details(work_id,fetch=False);qapp.processEvents()
    heading=window.detail_page.findChild(QLabel,'detailTitle')
    heading.setSelection(0,len(heading.text()));heading.setFocus()
    QTest.keyClick(heading,Qt.Key.Key_C,Qt.KeyboardModifier.ControlModifier)
    assert qapp.clipboard().text()=='Copy <title> & 中文'
    window.close()


def test_thumbnail_prefers_stills_over_frames_and_keeps_manual_selection(qapp,tmp_path):
    window=MainWindow(tmp_path/'thumbnail-priority')
    try:
        first=tmp_path/'first.png';second=tmp_path/'second.png';manual=tmp_path/'manual.png'
        local=tmp_path/'local.png';poster=tmp_path/'poster.png'
        for path in (first,second,manual,local,poster):
            image=QImage(32,18,QImage.Format.Format_RGB32);image.fill(QColor('blue'));assert image.save(str(path))
        identifier=add_work(window.library,'Thumbnail priority',metadata={'nfo_stills':[str(first),str(second)]})
        work=window.library.work(identifier);file=work['files'][0]
        frame=window.library.directory/'cache'/(file['digest']+'.jpg')
        assert QImage(str(first)).save(str(frame))
        work['thumbnail']=str(poster)
        work['metadata']['nfo_thumbnails']={str(file['id']):str(local)}
        assert window.card_data(work,True)['_cover']==str(first)
        assert window.card_data(work).get('_cover') is None
        window.library.set_setting(f'artwork_{identifier}',{'thumbnail':str(manual)})
        assert window.card_data(work,True)['_cover']==str(manual)
        manual.unlink()
        assert window.card_data(work,True)['_cover']==str(first)
        first.unlink()
        assert window.card_data(work,True)['_cover']==str(second)
        second.unlink()
        assert window.card_data(work,True)['_cover']==str(local)
        local.unlink()
        assert window.card_data(work,True)['_cover']==str(frame)
        frame.unlink()
        assert window.card_data(work,True)['_cover']==str(poster)
    finally:window.close()


def test_thumbnail_uses_ordered_plugin_stills_and_episode_stills(qapp,tmp_path):
    from lumen.artwork import thumbnail_path
    library=Library(tmp_path/'still-sources')
    try:
        first=tmp_path/'plugin.jpg';second=tmp_path/'episode.jpg'
        for path in (first,second):
            image=QImage(32,18,QImage.Format.Format_RGB32);image.fill(QColor('green'));assert image.save(str(path))
        work={'id':1,'metadata':{'stills':['https://example.test/first'],
            'stills_cache':[{'url':'https://example.test/stale','path':str(second)},
                            {'url':'https://example.test/first','path':str(first)}]}}
        assert thumbnail_path(library,work)==str(first)
        work['metadata']['episode_stills']={'1':[str(second)]}
        assert thumbnail_path(library,work)==str(second)
    finally:library.close()


def test_explicit_recapture_is_manual_thumbnail_until_reset(qapp,tmp_path,monkeypatch):
    from PySide6.QtWidgets import QInputDialog
    window=MainWindow(tmp_path/'manual-frame')
    try:
        still=tmp_path/'still.png'
        image=QImage(32,18,QImage.Format.Format_RGB32);image.fill(QColor('red'));assert image.save(str(still))
        identifier=add_work(window.library,'Manual frame',metadata={'nfo_stills':[str(still)]})
        window.open_details(identifier,fetch=False)
        monkeypatch.setattr(QInputDialog,'getDouble',lambda *args:(12.0,True))
        monkeypatch.setattr('lumen.ui.thumbnail',lambda source,target,*args: image.save(str(target)))
        monkeypatch.setattr(window,'run_job',lambda title,job,*args:job(window.library,None))
        window.detail_page.recapture()
        frame=window.library.setting(f'artwork_{identifier}')['thumbnail']
        work=window.library.work(identifier)
        assert window.card_data(work,True)['_cover']==frame
        window.library.set_setting(f'artwork_{identifier}',{})
        assert window.card_data(work,True)['_cover']==str(still)
    finally:window.close()


def test_cover_keyboard_and_custom_images_used_in_both_modes(qapp,tmp_path):
    window=MainWindow(tmp_path/'cover');work_id=add_work(window.library,'Cover keys')
    source=tmp_path/'source.png';picture(source)
    with window.library.db:window.library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(source),work_id))
    save_artwork(window.library,work_id,source,'poster','left');save_artwork(window.library,work_id,source,'thumbnail','right')
    selected=window.library.setting(f'artwork_{work_id}')
    work=window.library.work(work_id)
    assert window.card_data(work)['_cover']==selected['poster']
    assert window.card_data(work,True)['_cover']==selected['thumbnail']
    window.open_details(work_id,fetch=False);window.show();qapp.processEvents()
    page=window.detail_page;assert page.poster_path==selected['poster']
    QTest.keyClick(page.poster,Qt.Key.Key_Right);assert page.poster_path==selected['thumbnail']
    QTest.keyClick(page.poster,Qt.Key.Key_Left);assert page.poster_path==selected['poster']
    page.reset_artwork()
    assert window.detail_page.poster_path==str(source) and not window.library.setting(f'artwork_{work_id}')
    window.close()


def test_size_dialog_saves_independent_sizes_and_preserves_card_actions(qapp,tmp_path):
    window=MainWindow(tmp_path/'sizes');work_id=add_work(window.library,'Sized cards')
    window.navigate('movie');window.show();qapp.processEvents()
    def choose():
        dialog=qapp.activeModalWidget();assert isinstance(dialog,QDialog)
        spins=dialog.findChildren(QSpinBox);spins[0].setValue(240);spins[1].setValue(360)
        dialog.accept()
    QTimer.singleShot(30,choose);window.choose_artwork_sizes();qapp.processEvents()
    assert window.library.setting('poster_width')==240 and window.library.setting('thumbnail_width')==360
    item=window.cards.item(0);assert window.cards.visualItemRect(item).width()==240
    _,areas=poster_regions(window.cards.visualItemRect(item))
    QTest.mouseClick(window.cards.viewport(),Qt.MouseButton.LeftButton,pos=areas['favorite'].center())
    assert window.library.work(work_id)['favorite']==1
    window.view_mode.setCurrentIndex(1);qapp.processEvents()
    assert window.cards.visualItemRect(window.cards.item(0)).width()==360
    window.open_details(work_id,fetch=False);qapp.processEvents()
    assert window.detail_page.poster.width()==260
    assert window.detail_page.still_gallery.iconSize().width()==368
    window.close()


def test_save_from_detail_dialog_refreshes_page_and_gallery_is_browsable(qapp,tmp_path,monkeypatch):
    window=MainWindow(tmp_path/'save-ui');work_id=add_work(window.library,'Save artwork')
    source=tmp_path/'still.png';picture(source)
    with window.library.db:
        window.library.db.execute('UPDATE works SET thumbnail=? WHERE id=?',(str(source),work_id))
    window.open_details(work_id,fetch=False);window.show();qapp.processEvents()
    def choose():
        dialog=qapp.activeModalWidget();assert isinstance(dialog,ArtworkDialog)
        wait_for(lambda:dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled())
        dialog.anchor.setCurrentIndex(dialog.anchor.findData('right'))
        dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()
    QTimer.singleShot(30,choose);window.detail_page.choose_artwork()
    wait_for(lambda:not window.jobs and bool(window.library.setting(f'artwork_{work_id}')))
    selected=window.library.setting(f'artwork_{work_id}')
    assert window.detail_page.poster_path==selected['poster']
    opened=[]
    class Viewer:
        def __init__(self,paths,**kwargs):opened.extend(paths)
        def exec(self):return 0
        def deleteLater(self):pass
    monkeypatch.setattr('lumen.catalog_ui.StillViewer',Viewer)
    window.detail_page.view_cover()
    assert opened==[selected['poster'],str(source)]
    window.close()
