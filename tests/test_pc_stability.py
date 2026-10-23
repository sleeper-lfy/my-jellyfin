"""Regressions for live import layout, repeated import, bookmarks and image memory."""
import threading
import time
from pathlib import Path
import pytest
from PySide6.QtCore import QEventLoop,QTimer,Qt,QSize
from PySide6.QtGui import QImage,QColor
from PySide6.QtWidgets import QDialog,QLineEdit,QPlainTextEdit,QDoubleSpinBox,QDialogButtonBox,QPushButton,QListWidget,QFileDialog
from lumen.ui import MainWindow


def spin(app,seconds=.03):
    loop=QEventLoop();QTimer.singleShot(int(seconds*1000),loop.quit);loop.exec();app.processEvents()


def until(app,predicate,seconds=10):
    deadline=time.monotonic()+seconds
    while not predicate() and time.monotonic()<deadline:spin(app,.02)
    assert predicate()


@pytest.fixture
def window(qapp,tmp_path):
    value=MainWindow(tmp_path/'stability');value.show();spin(qapp)
    for timer in (value.scheduler,value.media_scheduler,value.watch_scheduler,value.remote.timer):timer.stop()
    yield value
    value.stop_jobs();value.close();until(qapp,lambda:not value.isVisible() and not value.jobs)


def test_progress_long_paths_and_chained_jobs_never_resize_content(qapp,window):
    baseline=window.pages.geometry();samples=[];timer=QTimer();timer.setInterval(10)
    timer.timeout.connect(lambda:samples.append(window.pages.geometry()));timer.start()
    def progress(lib,report):
        for number in range(12):
            report(number,12,('D:\\'+('目录很长\\'*70)+'video.mp4') if number%2 else '扫描中')
            time.sleep(.025)
        return {}
    window.run_job('快速导入布局检查',progress);window.run_job('后续处理',progress)
    until(qapp,lambda:not window.jobs and not window.job_queue);timer.stop()
    assert len(samples)>20 and all(rect==baseline for rect in samples)
    assert window.status.height()==28 and not window.status.wordWrap()
    assert not window.job_progress.isVisible() and window.pages.geometry()==baseline
    assert not window._job_functions  # Completed closures must not retain old pages.


def records(count):
    return [{'id':i,'kind':'movie','title':f'Fixture {i}','year':2024,'files':[], 'sources':[], 'metadata':{}} for i in range(count)]


def test_refresh_reuses_cards_selection_and_home_widgets(qapp,window):
    works=records(100);window.navigate('movie');window.refresh(_data={'items':works});spin(qapp)
    item=window.cards.item(18);window.cards.setCurrentItem(item);window.cards.verticalScrollBar().setValue(600);spin(qapp)
    position=window.cards.verticalScrollBar().value();count=window.display_count
    for _ in range(12):window.refresh(_data={'items':works})
    assert window.cards.currentItem() is item and window.display_count==count
    assert window.cards.updatesEnabled()
    assert window.cards.verticalScrollBar().value()==position
    window.navigate('home');data={'home':works,'recommendations':works[:12]};window.refresh(_data=data);spin(qapp)
    rows=list(window.home_page.rows);tiles=dict(window.home_page.tiles);widgets=len(window.findChildren(QListWidget))
    window.home_page.verticalScrollBar().setValue(150);position=window.home_page.verticalScrollBar().value()
    for _ in range(25):window.refresh(_data=data)
    assert window.home_page.rows==rows and window.home_page.tiles==tiles
    assert all(row.updatesEnabled() for row in rows)
    assert window.home_page.verticalScrollBar().value()==position and len(window.findChildren(QListWidget))==widgets


def test_import_form_reopens_and_queues_repeated_imports(qapp,window,video_factory):
    source=video_factory('Repeated import.mp4');source.with_suffix('.nfo').write_text('<movie><title>First title</title></movie>',encoding='utf-8')
    release=threading.Event();started=threading.Event()
    def busy(lib,p):
        started.set()
        while not release.wait(.01):
            if p.cancelled():return {'cancelled':True}
        return {}
    window.run_job('Existing task',busy);until(qapp,started.is_set)
    try:
        window.import_path(source.parent);form=window.import_form
        window.import_dialog();assert window.import_form is form and form.isVisible()
        form.submit();assert len(window.job_queue)==1
        window.import_path(source.parent);assert window.import_form is form;form.submit();assert len(window.job_queue)==2
        # Opening the reusable form and its Qt directory chooser is asynchronous.
        window.import_dialog();form.choose();assert form.browser.testOption(QFileDialog.Option.DontUseNativeDialog)
        fired=[];QTimer.singleShot(20,lambda:fired.append(True));spin(qapp,.06);assert fired
        form.browser.reject();form.reject()
    finally:release.set()
    until(qapp,lambda:not window.jobs and not window.job_queue)
    assert len(window.library.query())==1 and window.library.db.execute('SELECT COUNT(*) FROM files').fetchone()[0]==1
    source.with_suffix('.nfo').write_text('<movie><title>Updated title</title></movie>',encoding='utf-8')
    window.import_path(source.parent);form.submit();until(qapp,lambda:not window.jobs and not window.job_queue)
    assert window.library.query()[0]['title']=='Updated title'


def test_bookmark_visible_entry_saves_original_moment_and_actual_screenshot(qapp,window,video_factory):
    window.library.import_folder(video_factory('Bookmarks UI.mp4','blue',6).parent,'movie');work=window.library.query()[0];file=work['files'][0]
    window.open_details(work['id'],fetch=False);detail=window.detail_page
    assert detail.add_bookmark_action.isVisible() and detail.bookmark_empty.isVisible()
    player=window.player;player.open_file(file);until(qapp,lambda:player.media.duration()>0);player.media.pause();player.timeline.setValue(1000);player.seek()
    assert player.bookmark_control.isVisible()
    dialog=player.add_bookmark();assert dialog.findChild(QDoubleSpinBox,'bookmarkTime').value()==1
    player.timeline.setValue(3000);player.seek()
    dialog.findChild(QLineEdit,'bookmarkName').setText('First scene');dialog.findChild(QPlainTextEdit,'bookmarkNote').setPlainText('Saved while typing')
    dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Save).click()
    entry=dict(window.library.db.execute('SELECT * FROM bookmarks').fetchone())
    assert entry['position']==1 and entry['title']=='First scene' and detail.bookmark_list.count()==1
    until(qapp,lambda:not window.jobs)
    entry=dict(window.library.db.execute('SELECT * FROM bookmarks').fetchone());assert Path(entry['image']).read_bytes().startswith(b'\xff\xd8')
    listing=player.show_bookmarks();next(button for button in listing.findChildren(QPushButton) if button.text().startswith('跳转')).click()
    assert abs(player.media.position()-1000)<100
    listing=player.show_bookmarks();next(button for button in listing.findChildren(QPushButton) if button.text().startswith('删除')).click()
    assert not window.library.db.execute('SELECT 1 FROM bookmarks').fetchone() and detail.bookmark_empty.isVisible()
    listing.close();player.close();spin(qapp)
    baseline=len(player.findChildren(QDialog))
    for _ in range(12):player.add_bookmark(file=file,parent=detail).reject();spin(qapp,.01)
    assert len(player.findChildren(QDialog))==baseline and window.library.stats()['valid']==0


def test_image_refresh_keeps_previous_picture_until_ready(qapp,tmp_path,monkeypatch):
    from lumen import images
    cache=images.ImageCache(qapp);target=tmp_path/'poster.jpg';picture=QImage(160,240,QImage.Format.Format_RGB32);picture.fill(QColor('red'));picture.save(str(target));size=QSize(160,240)
    until(qapp,lambda:not cache.request(target,size).isNull());release=threading.Event();original=images.decode
    def delayed(path,size):
        if str(path)!=str(target):return original(path,size)
        release.wait(3);image=QImage(160,240,QImage.Format.Format_RGB32);image.fill(QColor('green'));return image
    monkeypatch.setattr(images,'decode',delayed)
    try:
        cache.invalidate();assert cache.request(target,size).toImage().pixelColor(1,1).red()>200
        spin(qapp,.05);assert cache.request(target,size).toImage().pixelColor(1,1).red()>200
    finally:release.set()
    until(qapp,lambda:not cache.pending)
    assert cache.request(target,size).toImage().pixelColor(1,1).green()>100
    cache.deleteLater()


def test_image_decode_queue_and_pixels_are_bounded(qapp,tmp_path,monkeypatch):
    from lumen import images
    cache=images.ImageCache(qapp);release=threading.Event();calls=[];original=images.decode
    def decode(path,size):
        if not str(path).startswith(str(tmp_path)):return original(path,size)
        calls.append(str(path));release.wait(3);picture=QImage(1400,900,QImage.Format.Format_RGB32);picture.fill(QColor('blue'));return picture
    monkeypatch.setattr(images,'decode',decode)
    try:
        for i in range(1000):cache.request(tmp_path/f'{i}.jpg',QSize(1400,900))
        until(qapp,lambda:len(calls)==2)
        assert len(cache.pending)<=cache.max_pending and cache.active==2
        release.set();time.sleep(.04)
        assert len(calls)==2  # New decodes wait until the GUI consumes finished images.
        until(qapp,lambda:not cache.pending)
        assert cache.bytes<=32*1024*1024 and len(cache.cache)<=256 and cache.active==0
    finally:release.set()
    cache.deleteLater()
