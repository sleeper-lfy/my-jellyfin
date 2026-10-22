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
    assert window.player.like.text()=='♥'
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
