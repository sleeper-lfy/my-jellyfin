from pathlib import Path
from datetime import datetime, timedelta
from .presentation import rating_text
from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QEvent, QSizeF, QSize, QRect
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider, QComboBox, QFileDialog, QWidget, QGridLayout, QGraphicsView, QGraphicsScene, QFrame, QStyle, QCheckBox
from PySide6.QtGui import QShortcut, QKeySequence, QPainter, QIcon, QColor, QCursor
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from .core import WatchSession


class Player(QDialog):
    queueNext = Signal()
    queuePrevious = Signal()
    refreshed = Signal()

    def __init__(self, library, parent=None):
        super().__init__(parent)
        self.library = library
        self.setWindowTitle('Lumen · 播放器')
        self.resize(1100, 720)
        self.session = None
        self.file = None
        self.resume = None
        self.seek_guard = 0
        self.cues = []
        self.external_subtitle_enabled = True
        self.setObjectName('cinema')
        self.setStyleSheet("""
            QDialog#cinema { background: black; }
            QLabel { color: #eeeeee; background: transparent; }
            QWidget#playerBar { background: rgba(8,8,8,225); }
            QPushButton { background: transparent; border: none; color: white; padding: 8px; }
            QPushButton:hover { background: #303030; border-radius: 4px; }
            QPushButton:checked { color: #00a4dc; }
            QSlider::groove:horizontal { height: 3px; background: #555555; }
            QSlider::sub-page:horizontal { background: #00a4dc; }
            QSlider::handle:horizontal { background: #00a4dc; width: 14px; margin: -6px 0; border-radius: 7px; }
        """)
        self.scene = QGraphicsScene(self)
        self.video = QGraphicsVideoItem()
        self.video.setAspectRatioMode(Qt.AspectRatioMode.KeepAspectRatio)
        self.scene.addItem(self.video)
        self.canvas = QGraphicsView(self.scene)
        self.canvas.setFrameShape(QFrame.Shape.NoFrame)
        self.canvas.setStyleSheet('background: black; border: none;')
        self.canvas.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.canvas.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.media = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.media.setAudioOutput(self.audio)
        self.media.setVideoOutput(self.video)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, 0, 0)
        self.overlay = QWidget(self)
        overlay_layout = QVBoxLayout(self.overlay)
        overlay_layout.setContentsMargins(0, 0, 0, 0)
        self.header = QWidget()
        self.header.setObjectName('playerBar')
        header = QHBoxLayout(self.header)
        header.setContentsMargins(16, 8, 16, 8)
        back = QPushButton('←')
        back.setToolTip('返回媒体库')
        back.clicked.connect(self.close)
        header.addWidget(back)
        self.title = QLabel()
        self.title.setTextFormat(Qt.TextFormat.PlainText)
        self.title.setMinimumWidth(0)
        self.title.setWordWrap(True)
        self.title.setMaximumHeight(48)
        header.addWidget(self.title, 1)
        overlay_layout.addWidget(self.header)
        overlay_layout.addStretch(1)
        self.caption = QLabel()
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet('font-size: 22px; color: white; background: rgba(0,0,0,120); padding: 6px;')
        overlay_layout.addWidget(self.caption)
        self.error = QLabel()
        self.error.setTextFormat(Qt.TextFormat.PlainText)
        self.error.setWordWrap(True)
        overlay_layout.addWidget(self.error)
        self.footer = QWidget()
        self.footer.setObjectName('playerBar')
        bottom = QVBoxLayout(self.footer)
        bottom.setContentsMargins(16, 12, 16, 24)
        timeline_row = QHBoxLayout()
        self.time_label = QLabel('00:00')
        timeline_row.addWidget(self.time_label)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.setToolTip('播放进度')
        self.timeline.sliderReleased.connect(self.seek)
        timeline_row.addWidget(self.timeline, 1)
        self.remaining = QLabel('-00:00')
        timeline_row.addWidget(self.remaining)
        bottom.addLayout(timeline_row)
        row = QHBoxLayout()
        def control(icon, tip, callback):
            button = QPushButton()
            button.setIcon(self.control_icon(icon))
            button.setIconSize(QSize(22, 22))
            button.setMinimumWidth(40)
            button.setToolTip(tip)
            button.setAccessibleName(tip)
            button.clicked.connect(callback)
            row.addWidget(button)
            return button
        self.previous_control = control(QStyle.StandardPixmap.SP_MediaSkipBackward, '上一作品', self.queuePrevious.emit)
        control(QStyle.StandardPixmap.SP_MediaSeekBackward, '后退 10 秒（←）', lambda: self.jump(-10000))
        self.pause = control(QStyle.StandardPixmap.SP_MediaPlay, '播放 / 暂停（空格）', self.toggle)
        control(QStyle.StandardPixmap.SP_MediaSeekForward, '前进 10 秒（→）', lambda: self.jump(10000))
        self.next_control = control(QStyle.StandardPixmap.SP_MediaSkipForward, '下一集 / 下一作品', self.next_item)
        self.ends_at = QLabel('')
        row.addWidget(self.ends_at)
        self.rating = QLabel('')
        self.rating.setStyleSheet('color: #efc84a;')
        row.addWidget(self.rating)
        row.addStretch()
        self.like = QPushButton('♡')
        self.like.setCheckable(True)
        self.like.setAccessibleName('喜欢')
        self.like.clicked.connect(self.toggle_like)
        row.addWidget(self.like)
        self.mute = control(QStyle.StandardPixmap.SP_MediaVolume, '静音 / 恢复音量', self.toggle_mute)
        volume = self.volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(70)
        volume.setMaximumWidth(110)
        volume.setToolTip('音量')
        volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        row.addWidget(volume)
        settings = QPushButton('⚙')
        settings.setToolTip('音轨和字幕设置')
        settings.setAccessibleName('音轨和字幕设置')
        settings.clicked.connect(self.show_settings)
        row.addWidget(settings)
        full = self.fullscreen_control = QPushButton('⛶')
        full.setToolTip('全屏 / 退出（F）')
        full.clicked.connect(self.toggle_fullscreen)
        row.addWidget(full)
        bottom.addLayout(row)
        overlay_layout.addWidget(self.footer)
        # The controls must follow the actual client rectangle, independently
        # of the video scene and its size hints when switching DPI/fullscreen.
        self.overlay.setGeometry(self.rect())
        self.overlay.raise_()
        self.track_dialog = QDialog(self)
        self.track_dialog.setWindowTitle('播放设置')
        tracks = QVBoxLayout(self.track_dialog)
        self.subtitles = QComboBox()
        self.subtitles.currentIndexChanged.connect(lambda i: self.media.setActiveSubtitleTrack(self.subtitles.itemData(i)) if self.subtitles.itemData(i) is not None else None)
        self.audio_tracks = QComboBox()
        self.audio_tracks.currentIndexChanged.connect(lambda i: self.media.setActiveAudioTrack(self.audio_tracks.itemData(i)) if self.audio_tracks.itemData(i) is not None else None)
        tracks.addWidget(QLabel('字幕'))
        tracks.addWidget(self.subtitles)
        tracks.addWidget(QLabel('音轨'))
        tracks.addWidget(self.audio_tracks)
        tracks.addWidget(QPushButton('外挂字幕…', clicked=self.choose_subtitle))
        tracks.addWidget(QPushButton('开关外挂字幕', clicked=self.toggle_external_subtitle))
        self.auto_hide = QCheckBox('播放时自动隐藏控制栏')
        self.auto_hide.setChecked(self.library.setting('player_auto_hide', True))
        self.auto_hide.toggled.connect(self.set_auto_hide)
        tracks.addWidget(self.auto_hide)
        self.idle = QTimer(self)
        self.idle.setSingleShot(True)
        self.idle.setInterval(3500)
        self.idle.timeout.connect(self.hide_controls)
        self.last_cursor = QCursor.pos()
        self.pointer_timer = QTimer(self)
        self.pointer_timer.setInterval(150)
        self.pointer_timer.timeout.connect(self.check_pointer)
        for widget in [self, self.canvas.viewport(), self.overlay, *self.overlay.findChildren(QWidget)]:
            widget.setMouseTracking(True)
            widget.installEventFilter(self)
        self.media.tracksChanged.connect(self.tracks_changed)
        self.media.durationChanged.connect(self.duration_changed)
        self.media.positionChanged.connect(self.position_changed)
        self.media.mediaStatusChanged.connect(self.status_changed)
        self.media.playbackStateChanged.connect(self.state_changed)
        self.media.errorOccurred.connect(lambda _code, message: self.error.setText('播放错误：' + message))
        self.seek_shortcuts = []
        for key, delta in [(Qt.Key.Key_Left, -10000), (Qt.Key.Key_Right, 10000)]:
            shortcut = QShortcut(QKeySequence(key), self)
            shortcut.setContext(Qt.ShortcutContext.WindowShortcut)
            shortcut.activated.connect(lambda delta=delta: self.jump(delta))
            self.seek_shortcuts.append(shortcut)
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.sample)
        self.timer.start()

    def control_icon(self, standard):
        pixmap = self.style().standardIcon(standard).pixmap(24, 24)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor('white'))
        painter.end()
        return QIcon(pixmap)

    def eventFilter(self, watched, event):
        if watched is self.canvas.viewport() and event.type() == QEvent.Type.Resize:
            size = QSizeF(self.canvas.viewport().size())
            self.video.setSize(size)
            self.scene.setSceneRect(0, 0, size.width(), size.height())
        if event.type() in {QEvent.Type.MouseMove, QEvent.Type.MouseButtonPress, QEvent.Type.KeyPress}:
            self.show_controls()
        return super().eventFilter(watched, event)

    def sync_overlay(self):
        if not hasattr(self, 'fullscreen_control'):
            return
        area = self.rect()
        screen = self.screen()
        if self.isFullScreen() and screen is not None:
            # Windows can keep the taskbar above a fullscreen dialog. Keep
            # controls inside the work area even then; video still fills the
            # entire screen. Map from global coordinates for secondary monitors.
            available = screen.availableGeometry()
            safe = QRect(self.mapFromGlobal(available.topLeft()), available.size())
            intersection = area.intersected(safe)
            if not intersection.isEmpty():
                area = intersection
        self.overlay.setGeometry(area)
        width = area.width()
        self.ends_at.setVisible(width >= 1000)
        self.rating.setVisible(width >= 760)
        self.volume.setVisible(width >= 640)
        self.previous_control.setVisible(width >= 540)
        self.next_control.setVisible(width >= 540)
        self.overlay.layout().invalidate()
        self.overlay.layout().activate()
        self.overlay.raise_()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sync_overlay()

    def showEvent(self, event):
        super().showEvent(event)
        self.last_cursor = QCursor.pos()
        self.pointer_timer.start()
        self.show_controls()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, 'idle'):
            QTimer.singleShot(0, self.show_controls)

    def check_pointer(self):
        # Some Windows video/fullscreen paths do not deliver unpressed mouse
        # movement to the overlay. Cursor position provides a second wake path.
        point = QCursor.pos()
        moved = point != self.last_cursor
        self.last_cursor = point
        if moved and self.isVisible() and self.isActiveWindow() and self.rect().contains(self.mapFromGlobal(point)):
            self.show_controls()

    def set_auto_hide(self, enabled):
        self.library.set_setting('player_auto_hide', enabled)
        self.show_controls()

    def show_controls(self):
        self.sync_overlay()
        self.header.show()
        self.footer.show()
        self.overlay.unsetCursor()
        if self.auto_hide.isChecked():
            self.idle.start()
        else:
            self.idle.stop()

    def hide_controls(self):
        if self.auto_hide.isChecked() and self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState and not self.track_dialog.isVisible() and not self.timeline.isSliderDown() and not self.footer.underMouse():
            self.header.hide()
            self.footer.hide()
            self.overlay.setCursor(Qt.CursorShape.BlankCursor)

    def show_settings(self):
        self.track_dialog.show()
        self.track_dialog.raise_()

    def update_like(self, work):
        self.like.setChecked(bool(work['favorite']))
        self.like.setText('♥' if work['favorite'] else '♡')
        self.like.setToolTip('取消喜欢' if work['favorite'] else '喜欢')

    def toggle_like(self):
        if self.file:
            self.library.update_personal(self.file['work_id'], favorite=self.like.isChecked())
            self.update_like(self.library.work(self.file['work_id']))
            self.refreshed.emit()

    def toggle_mute(self):
        self.audio.setMuted(not self.audio.isMuted())
        icon = QStyle.StandardPixmap.SP_MediaVolumeMuted if self.audio.isMuted() else QStyle.StandardPixmap.SP_MediaVolume
        self.mute.setIcon(self.control_icon(icon))

    def jump(self, milliseconds):
        self.timeline.setValue(max(0, min(self.media.duration(), self.media.position() + milliseconds)))
        self.seek()

    def next_item(self):
        if not self.next_episode():
            self.queueNext.emit()

    def open_file(self, file):
        self.finish()
        if not Path(file['path']).is_file():
            self.error.setText('文件不存在，请检查磁盘或重新导入：' + file['path'])
            self.show()
            return
        self.file = file
        work = self.library.work(file['work_id'])
        self.title.setToolTip(work['title'])
        self.title.setText(work['title'] + (f" · S{file['season']:02}E{file['episode']:02}" if work['kind'] == 'series' else ''))
        self.rating.setText(rating_text(work))
        self.update_like(work)
        self.show_controls()
        self.error.setText('')
        self.cues = []
        self.caption.clear()
        source = Path(file['path'])
        candidates = [p for p in source.parent.iterdir() if p.suffix.lower() in {'.srt','.ass','.ssa','.vtt'} and (p.stem == source.stem or p.name.startswith(source.stem + '.'))]
        if candidates:
            self.load_subtitle(sorted(candidates)[0])
        self.resume = file['position'] if not file['completed'] else 0
        self.session = WatchSession(self.library, file['id'])
        self.media.setSource(QUrl.fromLocalFile(file['path']))
        self.media.play()
        self.show()
        self.raise_()

    def duration_changed(self, milliseconds):
        self.timeline.setRange(0, milliseconds)
        if self.file and milliseconds > 0:
            with self.library.db:
                self.library.db.execute('UPDATE files SET duration=? WHERE id=?',(milliseconds/1000,self.file['id']))

    def position_changed(self, position):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(position)
        def stamp(ms):
            seconds = ms // 1000
            return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'
        self.time_label.setText(stamp(position))
        remaining = max(0, self.media.duration() - position)
        self.remaining.setText('-' + stamp(remaining))
        end = datetime.now() + timedelta(milliseconds=remaining / max(.01, self.media.playbackRate()))
        self.ends_at.setText('结束于 ' + end.strftime('%H:%M') if self.media.duration() else '')
        text = '\n'.join(cue[2] for cue in self.cues if cue[0] <= position/1000 < cue[1]) if self.external_subtitle_enabled else ''
        self.caption.setText(text)
        self.caption.setVisible(bool(text))

    def sample(self):
        if self.session:
            playing = (self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState and
                       self.media.mediaStatus() in {QMediaPlayer.MediaStatus.BufferedMedia, QMediaPlayer.MediaStatus.BufferingMedia})
            self.session.tick(self.media.position() / 1000, playing, self.media.playbackRate(), self.seek_guard > 0)
            self.seek_guard = max(0, self.seek_guard - 1)

    def seek(self):
        self.seek_guard = 2
        self.media.setPosition(self.timeline.value())
        self.sample()

    def state_changed(self, state):
        self.pause.setIcon(self.control_icon(QStyle.StandardPixmap.SP_MediaPause if state == QMediaPlayer.PlaybackState.PlayingState else QStyle.StandardPixmap.SP_MediaPlay))
        self.show_controls()
        self.sample()

    def toggle(self):
        self.media.pause() if self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState else self.media.play()

    def status_changed(self, status):
        if status in {QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia} and self.resume is not None:
            self.seek_guard = 2
            self.media.setPosition(int(self.resume * 1000))
            self.resume = None
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.file:
            self.finish()
            with self.library.db:
                self.library.db.execute('UPDATE files SET completed=1,position=0 WHERE id=?', (self.file['id'],))
            if self.library.work(self.file['work_id'])['kind'] == 'series' and self.next_episode():
                return
            self.finish()
            self.queueNext.emit()

    def next_episode(self):
        if not self.file:
            return False
        work = self.library.work(self.file['work_id'])
        if work['kind'] != 'series':
            return False
        files = work['files']
        index = next(i for i, f in enumerate(files) if f['id'] == self.file['id'])
        if index + 1 < len(files):
            self.open_file(files[index + 1])
            return True
        return False

    def tracks_changed(self):
        from PySide6.QtMultimedia import QMediaMetaData
        for box, tracks, off in [(self.subtitles, self.media.subtitleTracks(), True), (self.audio_tracks, self.media.audioTracks(), False)]:
            box.blockSignals(True)
            box.clear()
            if off:
                box.addItem('关闭字幕', -1)
            for i, track in enumerate(tracks):
                box.addItem(track.stringValue(QMediaMetaData.Key.Title) or track.stringValue(QMediaMetaData.Key.Language) or f'轨道 {i + 1}', i)
            active = self.media.activeSubtitleTrack() if off else self.media.activeAudioTrack()
            box.setCurrentIndex(box.findData(active))
            box.blockSignals(False)

    def load_subtitle(self, path):
        from .subtitles import read_subtitles
        try:
            self.cues = read_subtitles(path)
            self.external_subtitle_enabled = True
        except Exception as exc:
            self.error.setText('外挂字幕未载入：' + str(exc))

    def choose_subtitle(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择外挂字幕', '', '字幕 (*.srt *.ass *.ssa *.vtt)')
        if path:
            self.load_subtitle(path)

    def toggle_external_subtitle(self):
        self.external_subtitle_enabled = not self.external_subtitle_enabled
        self.position_changed(self.media.position())

    def toggle_fullscreen(self):
        self.showNormal() if self.isFullScreen() else self.showFullScreen()
        self.raise_()
        self.activateWindow()
        self.show_controls()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
        elif event.key() == Qt.Key.Key_F:
            self.toggle_fullscreen()
        elif event.key() in {Qt.Key.Key_Left, Qt.Key.Key_Right}:
            self.jump(-10000 if event.key() == Qt.Key.Key_Left else 10000)
        elif event.key() == Qt.Key.Key_Space:
            self.toggle()
        else:
            super().keyPressEvent(event)

    def finish(self):
        if self.session:
            self.sample()
            self.session.finish()
            self.session = None
        self.media.stop()
        self.refreshed.emit()

    def closeEvent(self, event):
        self.finish()
        self.track_dialog.close()
        self.idle.stop()
        self.pointer_timer.stop()
        super().closeEvent(event)
