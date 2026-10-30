import json
from pathlib import Path
import sqlite3
import time
import pytest
from PySide6.QtCore import Qt, QMimeData, QUrl, QPointF
from PySide6.QtGui import QImage, QColor, QDragEnterEvent, QDropEvent
from PySide6.QtTest import QTest
from lumen.actor_portrait import replace_local_portrait
from lumen.ui import MainWindow
from test_actor_plugins import credit


def picture(path):
    image=QImage(80,120,QImage.Format.Format_RGB32);image.fill(QColor('green'));assert image.save(str(path));return path


def test_local_replacement_copies_image_and_preserves_identity_locks_and_other_actors(library,qapp,tmp_path):
    first=credit(library,'First',locked=True);second=credit(library,'Second');other=credit(library,'Other',name='Other actor')
    actor=next(a for a in library.actresses() if a['name']=='Local actor')
    source=picture(tmp_path/'portrait.png');original=source.read_bytes()
    result=replace_local_portrait(library,actor,source)
    assert result['updated']==2 and source.read_bytes()==original
    assert library.work(first)['locked']==['actors']
    source.unlink()
    for identifier in (first,second):
        metadata=library.work(identifier)['metadata'];saved=metadata['actors'][0]
        assert Path(saved['photo_cache']).is_file()
        assert saved['photo_local'] and saved['photo_source']=='local'
        assert saved['name']=='Local actor' and saved['aliases']==['Local alias'] and metadata['overview']=='Keep this'
    assert not library.work(other)['metadata']['actors'][0].get('photo_cache')


def test_unreadable_image_and_late_database_error_preserve_original_metadata(library,qapp,tmp_path):
    first=credit(library,'First');second=credit(library,'Second')
    actor=library.actresses()[0];before=[library.work(i)['metadata'] for i in (first,second)]
    broken=tmp_path/'broken.png';broken.write_bytes(b'not an image')
    with pytest.raises(ValueError):replace_local_portrait(library,actor,broken)
    library.db.execute(f"CREATE TRIGGER refuse_second BEFORE UPDATE ON works WHEN NEW.id={second} BEGIN SELECT RAISE(ABORT,'injected'); END")
    library.db.commit()
    with pytest.raises(sqlite3.IntegrityError,match='injected'):
        replace_local_portrait(library,actor,picture(tmp_path/'valid.png'))
    assert [library.work(i)['metadata'] for i in (first,second)]==before


def test_drag_local_image_onto_actor_card_updates_in_background(qapp,tmp_path):
    window=MainWindow(tmp_path/'data');work=credit(window.library,'Drag target');source=picture(tmp_path/'drop.png')
    window.resize(1200,850);window.show();window.navigate('movie');window.tabs.setCurrentIndex(1);qapp.processEvents()
    for timer in (window.scheduler,window.media_scheduler,window.watch_scheduler,window.remote.timer):timer.stop()
    try:
        assert window.cards.count()==1
        position=window.cards.visualItemRect(window.cards.item(0)).center()
        mime=QMimeData();mime.setUrls([QUrl.fromLocalFile(str(source))])
        enter=QDragEnterEvent(position,Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(window.cards.viewport(),enter);assert enter.isAccepted()
        drop=QDropEvent(QPointF(position),Qt.DropAction.CopyAction,mime,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        qapp.sendEvent(window.cards.viewport(),drop);assert drop.isAccepted()
        deadline=time.monotonic()+6
        while (window.jobs or not window.library.work(work)['metadata']['actors'][0].get('photo_local')) and time.monotonic()<deadline:QTest.qWait(10)
        assert window.library.work(work)['metadata']['actors'][0]['photo_local']
        assert source.exists()
        assert '已替换 Local actor' in window.status.text()
        remote=QMimeData();remote.setUrls([QUrl('https://example.test/photo.png')])
        event=QDragEnterEvent(position,Qt.DropAction.CopyAction,remote,Qt.MouseButton.LeftButton,Qt.KeyboardModifier.NoModifier)
        assert window.cards.portrait_drop_path(event) is None
        window.navigate('movie');assert not window.cards.acceptDrops()
    finally:
        window.close()
        deadline=time.monotonic()+5
        while window.jobs and time.monotonic()<deadline:QTest.qWait(10)
