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
    image_rect=cards.visualItemRect(item).adjusted(8,8,-8,-82)
    QTest.mouseClick(cards.viewport(),Qt.MouseButton.LeftButton,pos=image_rect.center())
    assert played==[42] and opened==[]
    QTest.mouseClick(cards.viewport(),Qt.MouseButton.LeftButton,pos=image_rect.topLeft())
    assert opened==[42]
    cards.close()


def test_cover_modes_ratings_and_player_like_persist(qapp,tmp_path,video_factory):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage,QColor
    from lumen.presentation import rating_text
    window=MainWindow(tmp_path/'modes')
    source=video_factory('Modes.mp4','blue',10)
    source.with_suffix('.nfo').write_text('<movie><title>Cover modes</title><rating>8.4</rating><userrating>7</userrating></movie>',encoding='utf-8')
    poster=QImage(100,150,QImage.Format.Format_RGB32);poster.fill(QColor('red'))
    poster.save(str(source.parent/'poster.png'))
    window.library.import_folder(source.parent,'movie')
    window.show();window.navigate('movie');qapp.processEvents()
    data=window.cards.item(0).data(Qt.ItemDataRole.UserRole)
    assert not data['_landscape']
    assert '8.4' in rating_text(data) and '我的 7' in rating_text(data)
    window.view_mode.setCurrentIndex(1);qapp.processEvents()
    data=window.cards.item(0).data(Qt.ItemDataRole.UserRole)
    assert data['_landscape'] and data['_cover']!=data['thumbnail']
    assert QImage(data['_cover']).pixelColor(10,10).blue()>200
    assert QImage(data['thumbnail']).pixelColor(10,10).red()>200
    assert window.library.setting('view_mode')=='thumbnail'
    window.player.open_file(data['files'][0]);spin(qapp,300)
    QTest.mouseClick(window.player.like,Qt.MouseButton.LeftButton)
    assert window.library.work(data['id'])['favorite']==1
    assert window.player.like.text()=='喜欢／收藏' and window.player.like.isChecked() and not window.player.like.icon().isNull()
    assert window.cards.item(0).data(Qt.ItemDataRole.UserRole)['favorite']==1
    window.player.show_settings();qapp.processEvents()
    assert window.player.track_dialog.isVisible()
    window.player.track_dialog.close()
    window.player.close();window.close()


def test_direction_buttons_and_keys_seek_ten_seconds(qapp,library,video_factory):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QPushButton
    library.import_folder(video_factory('Seek.mp4','green',30).parent,'movie')
    player=Player(library)
    player.open_file(library.query()[0]['files'][0]);spin(qapp,500)
    player.media.pause()
    player.timeline.setValue(15000);player.seek();spin(qapp,100)
    backward=next(b for b in player.findChildren(QPushButton) if b.toolTip().startswith('后退 10'))
    forward=next(b for b in player.findChildren(QPushButton) if b.toolTip().startswith('前进 10'))
    QTest.mouseClick(backward,Qt.MouseButton.LeftButton)
    assert player.media.position()==5000
    QTest.mouseClick(forward,Qt.MouseButton.LeftButton)
    assert player.media.position()==15000
    player.timeline.setFocus();qapp.processEvents()
    QTest.keyClick(player.timeline,Qt.Key.Key_Left)
    assert player.media.position()==5000
    QTest.keyClick(player.timeline,Qt.Key.Key_Left)
    assert player.media.position()==0
    QTest.keyClick(player.timeline,Qt.Key.Key_Right)
    assert player.media.position()==10000
    player.jump(999999)
    assert player.media.position()==player.media.duration()
    player.close()


def test_detail_artwork_preserves_ratio_and_background_does_not_leak(qapp,tmp_path,video_factory):
    from PySide6.QtGui import QImage,QColor
    window=MainWindow(tmp_path/'artwork')
    source=video_factory('Artwork.mp4','blue')
    poster=QImage(160,320,QImage.Format.Format_RGB32);poster.fill(QColor('red'))
    poster.save(str(source.parent/'poster.png'))
    fanart=QImage(640,360,QImage.Format.Format_RGB32);fanart.fill(QColor('green'))
    fanart.save(str(source.parent/'fanart.png'))
    window.library.import_folder(source.parent,'movie')
    work=window.library.query()[0]
    dialog=Details(window,work['id']);dialog.show();qapp.processEvents()
    spin(qapp,400)
    pixmap=dialog.poster.pixmap()
    assert abs(pixmap.width()/pixmap.height()-.5)<.01
    assert not dialog.poster.hasScaledContents()
    assert dialog.backdrop.toImage().pixelColor(10,10).green()>100
    # Deliberately force a portrait background to verify painting is clipped,
    # including the historical case where its excess height spilled below 500px.
    from PySide6.QtGui import QPixmap
    dialog.backdrop=QPixmap(str(source.parent/'poster.png'))
    dialog.update();qapp.processEvents()
    screenshot=dialog.grab().toImage()
    assert screenshot.pixelColor(2,600).name()=='#101010'
    dialog.close();window.close()


def test_home_media_tiles_stay_widescreen_and_card_footers_fit(qapp,tmp_path,video_factory):
    from lumen.home import MediaTile
    window=MainWindow(tmp_path/'home-sizing')
    window.library.import_folder(video_factory('Home sizing.mp4','blue').parent,'movie')
    window.show();window.navigate('home')
    for width in [1100,1600]:
        window.resize(width,1000);qapp.processEvents();qapp.processEvents()
        for tile in window.home_page.findChildren(MediaTile):
            assert abs(tile.height()-tile.width()*9/16)<3
        for cards in window.home_page.rows:
            assert cards.visualItemRect(cards.item(0)).bottom() < cards.viewport().height()
    window.view_mode.setCurrentIndex(1);qapp.processEvents();qapp.processEvents()
    for cards in window.home_page.rows:
        assert cards.visualItemRect(cards.item(0)).bottom() < cards.viewport().height()
    window.close()


def test_details_are_inline_and_metadata_links_filter_all_media(qapp,tmp_path,video_factory):
    from PySide6.QtWidgets import QApplication
    window=MainWindow(tmp_path/'inline-details')
    movie=video_factory('Linked movie.mp4','blue')
    movie.with_suffix('.nfo').write_text('<movie><title>Linked movie</title><genre>Adventure &amp; Mystery</genre><actor><name>Example actor</name></actor></movie>',encoding='utf-8')
    other=video_factory('Other movie.mp4','red')
    window.library.import_folder(movie.parent,'movie')
    window.library.import_folder(other.parent,'movie')
    window.show();window.navigate('movie');qapp.processEvents()
    window.filters={'tags_all':['Adventure & Mystery']};window.refresh()
    item=window.cards.item(0)
    window.cards.setCurrentItem(item)
    window.open_item(item);qapp.processEvents()
    detail=window.detail_page
    assert detail is not None and not detail.isWindow()
    assert QApplication.activeModalWidget() is None
    assert window.pages.currentWidget() is window.details_scroll
    detail.accept();qapp.processEvents()
    assert window.pages.currentWidget() is window.browse_page
    assert window.filters=={'tags_all':['Adventure & Mystery']}
    assert window.cards.currentItem() is item
    window.open_item(item)
    window.detail_page.tag_links.linkActivated.emit('0');qapp.processEvents()
    assert window.detail_page is None
    assert [w['title'] for w in window.current_items]==['Linked movie']
    assert window.heading.text()=='标签：Adventure & Mystery'
    window.open_item(window.cards.item(0))
    window.detail_page.actor_links.linkActivated.emit('0');qapp.processEvents()
    assert window.filters=={'actor':'Example actor'}
    assert [w['title'] for w in window.current_items]==['Linked movie']
    window.open_item(window.cards.item(0));window.navigate('home');qapp.processEvents()
    assert window.detail_page is None and window.home_page.isVisible()
    window.close()


def test_fullscreen_controls_restore_and_can_be_kept_visible(qapp,library,video_factory,monkeypatch):
    from PySide6.QtCore import Qt,QPoint
    from PySide6.QtGui import QCursor
    library.import_folder(video_factory('Fullscreen.mp4','blue',30).parent,'movie')
    player=Player(library)
    player.open_file(library.query()[0]['files'][0]);spin(qapp,400)
    player.activateWindow();qapp.processEvents()
    QCursor.setPos(player.mapToGlobal(QPoint(300,200)));spin(qapp,100)
    player.hide_controls()
    assert player.header.isHidden() and player.footer.isHidden()
    player.toggle_fullscreen();qapp.processEvents()
    assert player.isFullScreen() and player.header.isVisible() and player.footer.isVisible()
    player.hide_controls()
    QTest.mouseMove(player.overlay,QPoint(320,220));qapp.processEvents()
    assert player.footer.isVisible()
    player.hide_controls()
    # Exercise the polling fallback without depending on mouse event delivery.
    player.last_cursor=QCursor.pos()+QPoint(1,1)
    # Offscreen Qt has no window manager to reactivate a recreated window.
    with monkeypatch.context() as focus:
        focus.setattr(player, 'isActiveWindow', lambda: True)
        player.check_pointer()
    assert player.footer.isVisible()
    player.auto_hide.setChecked(False)
    player.hide_controls()
    assert player.header.isVisible() and player.footer.isVisible() and not player.idle.isActive()
    assert library.setting('player_auto_hide') is False
    player.auto_hide.setChecked(True)
    player.media.pause();player.hide_controls()
    assert player.footer.isVisible()
    QTest.keyClick(player,Qt.Key.Key_Escape);qapp.processEvents()
    assert not player.isFullScreen() and player.footer.isVisible()
    player.close()
    assert not player.pointer_timer.isActive()


def test_player_controls_fit_small_fullscreen_and_long_metadata(qapp,library,video_factory):
    from PySide6.QtWidgets import QPushButton
    from PySide6.QtCore import QPoint
    library.import_folder(video_factory('Layout.mp4','blue',20).parent,'movie')
    work=library.query()[0]
    library.edit_metadata(work['id'],{'title':'很长的影片标题用于检查全屏布局 ' * 12},[])
    player=Player(library);player.open_file(work['files'][0]);spin(qapp,300)
    player.media.pause()
    for size in [(3440,1440),(2560,1080),(1280,720),(960,540),(640,360),(480,320)]:
        player.resize(*size);qapp.processEvents()
        player.show_controls();qapp.processEvents()
        assert player.overlay.geometry()==player.rect()
        for button in player.footer.findChildren(QPushButton):
            if button.isVisible():
                assert player.rect().contains(button.mapTo(player,QPoint(0,0)))
                assert player.rect().contains(button.mapTo(player,button.rect().bottomRight()))
        assert player.pause.isVisible() and player.fullscreen_control.isVisible()
    player.toggle_fullscreen();qapp.processEvents()
    assert player.rect().contains(player.fullscreen_control.mapTo(player,player.fullscreen_control.rect().bottomRight()))
    player.close()


def test_fullscreen_uses_entire_monitor_instead_of_taskbar_work_area(qapp, library, monkeypatch):
    from PySide6.QtCore import QPoint, QRect
    from PySide6.QtWidgets import QPushButton
    player = Player(library)
    player.show()
    player.auto_hide.setChecked(False)
    # Simulate fullscreen client/work areas independently of the CI monitor.
    # Actual fullscreen transitions are covered by the tests above.
    monkeypatch.setattr(player, 'isFullScreen', lambda: True)
    class Screen:
        def availableGeometry(self):
            return QRect(player.mapToGlobal(safe.topLeft()), safe.size())
    monkeypatch.setattr(player, 'screen', lambda: Screen())
    for width, height in [(3440, 1440), (2560, 1080)]:
        safe = QRect(0, 0, width, height)
        player.resize(width, height)
        qapp.processEvents()
        for safe in [QRect(0, 0, width, height-64), QRect(0, 64, width, height-64),
                     QRect(80, 0, width-80, height), QRect(0, 0, width-80, height)]:
            player.show_controls()
            qapp.processEvents()
            # The taskbar must be behind fullscreen, not consume a reserved
            # strip of the video/control surface as in the old workaround.
            assert player.overlay.geometry() == player.rect()
            assert player.canvas.geometry() == player.rect()
            for button in player.footer.findChildren(QPushButton):
                if button.isVisible():
                    assert player.rect().contains(button.mapTo(player, QPoint(0, 0)))
                    assert player.rect().contains(button.mapTo(player, button.rect().bottomRight()))
        monkeypatch.setattr(player, 'isFullScreen', lambda: False)
        player.show_controls()
        assert player.overlay.geometry() == player.rect()
        monkeypatch.setattr(player, 'isFullScreen', lambda: True)
    player.close()


def test_fullscreen_restores_window_and_clears_shell_state_on_exit_and_close(qapp,library,monkeypatch):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget
    import lumen.player as module
    calls=[]
    monkeypatch.setattr(module,'set_fullscreen_window',lambda hwnd,enabled:calls.append((int(hwnd),enabled)))
    owner=QWidget();owner.show()
    player=Player(library,owner);player.resize(680,460);player.move(40,60);player.show();qapp.processEvents()
    geometry=player.geometry();flags=player.windowFlags()
    assert flags & Qt.WindowType.WindowType_Mask == Qt.WindowType.Window
    for _ in range(2):
        player.toggle_fullscreen();qapp.processEvents()
        assert player.isFullScreen() and player.windowFlags()==flags
        assert not player.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
        assert calls[-1][1] is True
        player.toggle_fullscreen();qapp.processEvents()
        assert not player.isFullScreen() and player.geometry()==geometry and player.windowFlags()==flags
        assert calls[-1][1] is False
    player.showMaximized();qapp.processEvents()
    player.toggle_fullscreen();qapp.processEvents()
    player.toggle_fullscreen();qapp.processEvents()
    assert player.isMaximized()
    player.toggle_fullscreen();qapp.processEvents()
    player.close();qapp.processEvents()
    assert calls[-1][1] is False and not player.isFullScreen() and not player.isVisible()
    # A queued callback may run after close / Esc; it must not re-mark or show it.
    previous=len(calls);player.apply_native_fullscreen();qapp.processEvents()
    assert len(calls)==previous and not player.isVisible()
    player.show();qapp.processEvents()
    assert not player.isFullScreen() and player.windowFlags()==flags
    player.close();owner.close()


def test_vertical_wheel_over_home_row_scrolls_page_not_row(qapp,tmp_path,video_factory):
    from PySide6.QtCore import Qt,QPoint,QPointF
    from PySide6.QtGui import QWheelEvent
    from PySide6.QtWidgets import QApplication
    window=MainWindow(tmp_path/'wheel')
    window.library.import_folder(video_factory('Wheel movie.mp4').parent,'movie',fast=True)
    window.show();window.resize(1100,700);window.navigate('home');qapp.processEvents();qapp.processEvents()
    row=window.home_page.rows[0];outer=window.home_page.verticalScrollBar();horizontal=row.horizontalScrollBar()
    assert outer.maximum()>0
    before=horizontal.value()
    event=QWheelEvent(QPointF(100,100),QPointF(row.viewport().mapToGlobal(QPoint(100,100))),QPoint(),QPoint(0,-120),
                      Qt.MouseButton.NoButton,Qt.KeyboardModifier.NoModifier,Qt.ScrollPhase.NoScrollPhase,False)
    QApplication.sendEvent(row.viewport(),event);qapp.processEvents()
    assert outer.value()>0 and horizontal.value()==before
    window.close()


def test_large_catalog_reads_do_not_block_gui_and_stale_navigation_is_discarded(qapp,tmp_path,monkeypatch):
    import threading,time
    from lumen import browse
    window=MainWindow(tmp_path/'responsive')
    with window.library.db:
        window.library.db.executemany('INSERT INTO works(identity,kind,title,added) VALUES (?,?,?,?)',
            [(f'large:{i}','movie' if i%2 else 'series',f'Title {i}','2026-01-01') for i in range(300)])
    original=browse.load_view;threads=[]
    def slow_read(library,request):
        threads.append(threading.current_thread().ident);time.sleep(.15);return original(library,request)
    monkeypatch.setattr(browse,'load_view',slow_read)
    ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(time.monotonic()));timer.start()
    start=time.monotonic();window.navigate('movie');window.navigate('discover')
    assert time.monotonic()-start<.1
    deadline=time.monotonic()+3
    while window._browse_job is not None and time.monotonic()<deadline:spin(qapp,20)
    timer.stop()
    assert len(ticks)>8 and all(thread!=threading.current_thread().ident for thread in threads)
    assert window.section=='discover' and window.cards.isEnabled() and not window.current_items
    window.close()


def test_slow_image_decode_runs_in_background_and_bounds_cached_size(qapp,tmp_path,monkeypatch):
    import threading,time
    from lumen import images
    from PySide6.QtGui import QImage,QColor
    from PySide6.QtCore import QSize
    release=threading.Event();threads=[]
    def slow(path,size):
        threads.append(threading.get_ident());release.wait(2)
        image=QImage(80,40,QImage.Format.Format_RGB32);image.fill(QColor('green'));return image
    monkeypatch.setattr(images,'decode',slow)
    cache=images.ImageCache(qapp)
    start=time.monotonic();assert cache.request(str(tmp_path/'image.jpg'),QSize(300,200)).isNull()
    assert time.monotonic()-start<.05
    fired=[];QTimer.singleShot(20,lambda:(fired.append(True),release.set()))
    spin(qapp,150)
    assert fired and threads and all(thread!=threading.get_ident() for thread in threads)
    result=cache.request(str(tmp_path/'image.jpg'),QSize(300,200))
    assert not result.isNull() and result.toImage().pixelColor(1,1).green()>80
    assert cache.bytes<64*1024*1024
    cache.deleteLater()
