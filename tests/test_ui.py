from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtTest import QTest
from lumen.ui import MainWindow, Details, FilterDialog
from lumen.settings import Settings
from lumen.player import Player


def spin(app, milliseconds):
    end=QEventLoop()
    QTimer.singleShot(milliseconds,end.quit)
    end.exec()
    app.processEvents()


def test_every_page_and_dialog_uses_real_import(qapp,tmp_path,video_factory):
    window=MainWindow(tmp_path/'ui')
    window.library.import_folder(video_factory().parent,'movie')
    window.show()
    for section in ['home','movie','series','other','discover','stats']:
        window.navigate(section)
        for index in range(window.tabs.count()):
            window.tabs.setCurrentIndex(index)
            qapp.processEvents()
    work=window.library.query()[0]
    for dialog in [Details(window,work['id']),FilterDialog({},window),Settings(window)]:
        dialog.show(); qapp.processEvents(); dialog.close()
    window.navigate('movie')
    assert window.cards.count()==1
    window.grab().save(str(tmp_path/'imported-library.png'))
    window.close()


def test_real_ffmpeg_playback_pause_seek_persistence(qapp,library,video_factory):
    source=video_factory('Playback.mp4','yellow',10)
    library.import_folder(source.parent,'movie')
    f=library.query()[0]['files'][0]
    player=Player(library)
    frames=[]
    player.video.videoSink().videoFrameChanged.connect(lambda frame: frames.append(frame.isValid()))
    player.open_file(f)
    spin(qapp,2600)
    assert player.media.error()==QMediaPlayer.Error.NoError, player.media.errorString()
    assert player.media.position()>500
    assert any(frames), 'A decoded video frame must arrive, not just a playing state'
    player.media.pause()
    before=library.stats()['seconds']
    spin(qapp,1200)
    assert library.stats()['seconds']==before
    player.timeline.setValue(7000);player.seek()
    spin(qapp,300)
    assert library.stats()['seconds']==before
    player.media.play();spin(qapp,1300)
    player.close()
    saved=library.work(f['work_id'])['files'][0]
    assert saved['position']>=7
    assert 0<library.stats()['seconds']<6
    assert library.stats()['valid']==0


def test_background_import_finishes_and_calls_callback(qapp,tmp_path,video_factory):
    import time
    window=MainWindow(tmp_path/'background')
    completed=[]
    source=video_factory('Background.mp4','purple')
    window.run_job('test import',lambda lib,p:lib.import_folder(source.parent,'movie',p),completed.append)
    deadline=time.monotonic()+10
    while window.jobs and time.monotonic()<deadline:
        spin(qapp,50)
    assert not window.jobs
    assert completed[0]['imported']==1
    assert window.library.query()[0]['title']=='Background'
    window.close()


def test_jellyfin_home_navigation_and_favorites(qapp,tmp_path,video_factory):
    from lumen.home import MediaTile
    from PySide6.QtCore import Qt
    window=MainWindow(tmp_path/'navigation')
    window.library.import_folder(video_factory('Navigation.mp4','orange').parent,'movie')
    work=window.library.query()[0]
    window.library.update_personal(work['id'],favorite=True)
    window.show();window.navigate('home');qapp.processEvents()
    assert window.home_page.isVisible() and not window.drawer.isVisible()
    assert len(window.home_page.rows)>=2
    tiles=window.home_page.findChildren(MediaTile)
    QTest.mouseClick(tiles[0],Qt.MouseButton.LeftButton)
    assert window.section=='movie' and window.cards.count()==1
    window.open_favorites()
    assert [w['id'] for w in window.current_items]==[work['id']]
    assert window.heading.text()=='收藏'
    window.close()


def test_poster_center_plays_and_edge_opens_details(qapp):
    from lumen.ui import PosterList,PosterDelegate
    from PySide6.QtWidgets import QListWidgetItem,QListWidget
    from PySide6.QtCore import Qt
    played=[];opened=[]
    cards=PosterList(played.append)
    cards.setViewMode(QListWidget.ViewMode.IconMode)
    cards.setItemDelegate(PosterDelegate(cards))
    cards.resize(400,400)
    item=QListWidgetItem()
    item.setData(Qt.ItemDataRole.UserRole,{'id':42,'title':'Hit target fixture','files':[{'id':1}]})
    cards.addItem(item)
    cards.itemClicked.connect(lambda item:opened.append(item.data(Qt.ItemDataRole.UserRole)['id']))
    cards.show();qapp.processEvents()
    image_rect=cards.visualItemRect(item).adjusted(8,8,-8,-58)
    QTest.mouseClick(cards.viewport(),Qt.MouseButton.LeftButton,pos=image_rect.center())
    assert played==[42] and opened==[]
    QTest.mouseClick(cards.viewport(),Qt.MouseButton.LeftButton,pos=image_rect.topLeft())
    assert opened==[42]
    cards.close()
