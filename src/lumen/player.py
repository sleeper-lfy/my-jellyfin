from pathlib import Path
from datetime import datetime, timedelta
from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QEvent, QSizeF, QSize
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider, QComboBox, QFileDialog, QWidget, QGridLayout, QGraphicsView, QGraphicsScene, QFrame, QStyle, QCheckBox, QApplication, QDoubleSpinBox,QSpinBox,QFormLayout,QPlainTextEdit,QInputDialog,QListWidget,QListWidgetItem,QScrollArea,QMenu,QLineEdit,QDialogButtonBox,QGraphicsDropShadowEffect
from PySide6.QtGui import QShortcut, QKeySequence, QPainter, QIcon, QColor, QCursor, QRegion
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtMultimediaWidgets import QGraphicsVideoItem
from .playback_journal import PlaybackJournal, PlaybackSession
from .windows_fullscreen import set_fullscreen_window


class Player(QDialog):
    queueNext = Signal()
    queuePrevious = Signal()
    refreshed = Signal()
    bookmarksChanged = Signal()

    def __init__(self, library, parent=None):
        # A normal top-level window lets the Windows shell recognize fullscreen;
        # an owned dialog can leave Explorer's taskbar above the video.
        super().__init__(parent, Qt.WindowType.Window)
        self._windowed_geometry = None
        self._windowed_flags = None
        self.library = library
        self.playback_journal = PlaybackJournal(library.directory)
        self.setWindowTitle('Lumen · 播放器')
        self.resize(1100, 720)
        self.session = None
        self._open_generation = 0
        self.file = None
        self.resume = None
        self.subtitle_preferences={}
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
        self.mpv_backend = False
        self.backend_message = ''
        if QApplication.platformName() != 'offscreen' and not self.library.setting('player_compat', False):
            try:
                from .mpv_backend import MpvMedia, MpvAudio, MpvCanvas
                self.canvas = MpvCanvas(self)
                self.media = MpvMedia(self, window_id=int(self.canvas.winId()))
                self.audio = MpvAudio(self.media)
                self.mpv_backend = True
                self.media.keyPressed.connect(self.native_key,Qt.ConnectionType.QueuedConnection)
                QApplication.instance().aboutToQuit.connect(self.shutdown_mpv)
            except (ImportError, OSError, RuntimeError) as exc:
                self.backend_message = 'libmpv 不可用，已使用兼容播放：' + str(exc)
        if not self.mpv_backend:
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
            from .qt_audio import native_audio_output
            self.audio = native_audio_output(self)
            self.audio.setVolume(.7)
            self.media.setAudioOutput(self.audio)
            self.media.setVideoOutput(self.video)
        self.audio.setVolume(.7)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas, 0, 0)
        self.overlay = QWidget(self)
        if self.mpv_backend:
            self.overlay.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.overlay.setAutoFillBackground(False)
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
        self.caption = QLabel(self.overlay)
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet('font-size:22px; color:white; background:transparent; padding:6px;')
        subtitle_shadow=QGraphicsDropShadowEffect(self.caption)
        subtitle_shadow.setBlurRadius(3)
        subtitle_shadow.setOffset(0,1)
        subtitle_shadow.setColor(QColor(0,0,0,230))
        self.caption.setGraphicsEffect(subtitle_shadow)
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
        self.previous_control = control(QStyle.StandardPixmap.SP_MediaSkipBackward, '上一作品', self.previous_item)
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
        from .components import icon
        personal_row=QHBoxLayout()
        self.personal_rating=QPushButton();self.personal_rating.setObjectName('playerRating');self.personal_rating.setAccessibleName('我的评分');self.personal_rating.clicked.connect(self.choose_personal_rating)
        personal_row.addWidget(self.personal_rating)
        self.like=QPushButton();self.like.setObjectName('playerFavorite');self.like.setCheckable(True);self.like.setAccessibleName('喜欢 / 收藏');self.like.clicked.connect(self.toggle_like);personal_row.addWidget(self.like)
        self.negative=QPushButton();self.negative.setObjectName('playerDisliked');self.negative.setCheckable(True);self.negative.setAccessibleName('不喜欢');self.negative.clicked.connect(lambda:self.save_personal({'disliked':self.negative.isChecked()}));personal_row.addWidget(self.negative)
        personal_row.addStretch();bottom.insertLayout(0,personal_row)
        for action_button in [self.personal_rating,self.like,self.negative]:action_button.setEnabled(False)
        self.mute = control(QStyle.StandardPixmap.SP_MediaVolume, '静音 / 恢复音量', self.toggle_mute)
        volume = self.volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(70)
        volume.setMaximumWidth(110)
        volume.setToolTip('音量')
        volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        row.addWidget(volume)
        settings = QPushButton('⚙')
        from .components import icon
        self.bookmark_control=QPushButton(icon('bookmark'),'书签');self.bookmark_control.setAccessibleName('时间点书签');self.bookmark_control.setToolTip('添加当前时间点 / 查看书签（Ctrl+B 添加）')
        bookmark_menu=QMenu(self.bookmark_control);bookmark_menu.addAction('添加当前时间点…',self.add_bookmark);bookmark_menu.addAction('查看 / 跳转书签…',self.show_bookmarks);self.bookmark_control.setMenu(bookmark_menu);row.addWidget(self.bookmark_control)
        self.bookmark_shortcut=QShortcut(QKeySequence('Ctrl+B'),self,activated=self.add_bookmark)
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
        self.track_dialog.resize(620,650)
        track_outer=QVBoxLayout(self.track_dialog);track_scroll=QScrollArea();track_scroll.setWidgetResizable(True);track_outer.addWidget(track_scroll)
        track_content=QWidget();track_scroll.setWidget(track_content);tracks=QVBoxLayout(track_content)
        self.subtitles = QComboBox()
        self.subtitles.currentIndexChanged.connect(lambda i:self.select_subtitle(self.subtitles.itemData(i)) if self.subtitles.itemData(i) is not None else None)
        self.audio_tracks = QComboBox()
        self.audio_tracks.currentIndexChanged.connect(lambda i: self.media.setActiveAudioTrack(self.audio_tracks.itemData(i)) if self.audio_tracks.itemData(i) is not None else None)
        self.playback_speed=QComboBox()
        for rate in [.5,.75,1.,1.25,1.5,1.75,2.]:self.playback_speed.addItem(f'{rate:g}×',rate)
        self.playback_speed.setCurrentIndex(max(0,self.playback_speed.findData(self.library.setting('playback_speed',1.))))
        self.media.setPlaybackRate(self.playback_speed.currentData())
        self.playback_speed.currentIndexChanged.connect(lambda:(self.media.setPlaybackRate(self.playback_speed.currentData()),self.library.set_setting('playback_speed',self.playback_speed.currentData())))
        tracks.addWidget(QLabel('播放速度'));tracks.addWidget(self.playback_speed)
        self.auto_next=QCheckBox('自动播放下一集');self.auto_next.setChecked(self.library.setting('auto_next',True))
        self.auto_next.toggled.connect(lambda value:self.library.set_setting('auto_next',value));tracks.addWidget(self.auto_next)
        tracks.addWidget(QLabel('字幕'))
        tracks.addWidget(self.subtitles)
        tracks.addWidget(QLabel('音轨'))
        tracks.addWidget(self.audio_tracks)
        tracks.addWidget(QPushButton('外挂字幕…', clicked=self.choose_subtitle))
        tracks.addWidget(QPushButton('开关外挂字幕', clicked=self.toggle_external_subtitle))
        subtitle_form=QFormLayout()
        self.subtitle_delay=QDoubleSpinBox();self.subtitle_delay.setRange(-600,600);self.subtitle_delay.setSingleStep(.1);self.subtitle_delay.setDecimals(1);self.subtitle_delay.setSuffix(' 秒')
        self.subtitle_size=QSpinBox();self.subtitle_size.setRange(12,64);self.subtitle_size.setValue(22)
        self.subtitle_position=QSpinBox();self.subtitle_position.setRange(5,95);self.subtitle_position.setValue(90);self.subtitle_position.setSuffix(' %')
        subtitle_form.addRow('字幕延后（负数提前）',self.subtitle_delay);subtitle_form.addRow('字号',self.subtitle_size);subtitle_form.addRow('垂直位置',self.subtitle_position)
        tracks.addLayout(subtitle_form)
        tracks.addWidget(QLabel('按当前视频保存。Qt 兼容模式的字幕调节仅作用于外挂字幕。'))
        for control in (self.subtitle_delay,self.subtitle_size,self.subtitle_position):control.valueChanged.connect(self.save_subtitle_preferences)
        tracks.addWidget(QPushButton('添加当前时间书签…',clicked=self.add_bookmark))
        tracks.addWidget(QPushButton('时间点书签…',clicked=self.show_bookmarks))
        tracks.addWidget(QPushButton('播放诊断…',clicked=self.show_diagnostics))
        self.enhance = QCheckBox('GPU 画质增强（高质量缩放 + 轻度锐化）')
        self.enhance.setEnabled(self.mpv_backend)
        self.enhance.setToolTip('改善放大画面；不是 AI 超分辨率。卡顿时可关闭。')
        self.enhance.setChecked(self.mpv_backend and self.library.setting('player_enhance', False))
        if self.mpv_backend:
            self.media.set_enhancement(self.enhance.isChecked())
        self.enhance.toggled.connect(self.set_enhancement)
        tracks.addWidget(QLabel('播放内核：libmpv' if self.mpv_backend else '播放内核：Qt 兼容模式'))
        tracks.addWidget(self.enhance)
        self.beauty_enabled=QCheckBox('实时美颜（肤色区域磨皮 / 提亮）')
        self.beauty_enabled.setEnabled(self.mpv_backend)
        self.beauty_enabled.setToolTip('默认关闭，不修改视频。肤色估计可能影响相近颜色；不是人脸识别。Qt 兼容内核不支持。')
        tracks.addWidget(self.beauty_enabled)
        beauty_form=QFormLayout()
        self.beauty_smoothing=QSpinBox();self.beauty_smoothing.setRange(0,100);self.beauty_smoothing.setValue(35)
        self.beauty_brighten=QSpinBox();self.beauty_brighten.setRange(0,100);self.beauty_brighten.setValue(15)
        for label,control in [('磨皮强度',self.beauty_smoothing),('肤色提亮',self.beauty_brighten)]:
            control.setEnabled(self.mpv_backend);beauty_form.addRow(label,control)
        tracks.addLayout(beauty_form)
        tracks.addWidget(QLabel('按当前视频记忆。卡顿或色彩异常时关闭；不包含瘦脸、大眼。'))
        self.beauty_timer=QTimer(self);self.beauty_timer.setSingleShot(True);self.beauty_timer.setInterval(150)
        self.beauty_timer.timeout.connect(self.save_beauty)
        self.beauty_enabled.toggled.connect(lambda:self.save_beauty())
        for control in (self.beauty_smoothing,self.beauty_brighten):control.valueChanged.connect(lambda:self.beauty_timer.start())
        compatibility = QCheckBox('兼容播放模式（重启应用后生效）')
        compatibility.setChecked(self.library.setting('player_compat', False))
        compatibility.setToolTip('显卡或 OpenGL 不兼容时启用，使用原有播放方式。')
        compatibility.toggled.connect(lambda enabled: self.library.set_setting('player_compat', enabled))
        tracks.addWidget(compatibility)
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
        self.media.errorOccurred.connect(lambda _code, message: self.set_error('播放错误：' + message))
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

    def native_key(self, key):
        self.show_controls()
        if key=='LEFT':self.jump(-10000)
        elif key=='RIGHT':self.jump(10000)
        elif key=='SPACE':self.toggle()
        elif key=='f':self.toggle_fullscreen()
        elif key=='ESC':
            if self.isFullScreen():self.toggle_fullscreen()
            else:self.close()

    def set_error(self, message):
        self.error.setText(message)
        self.sync_overlay()

    def set_enhancement(self, enabled):
        if self.mpv_backend:
            try:
                self.media.set_enhancement(enabled)
                self.library.set_setting('player_enhance', enabled)
            except (ValueError, RuntimeError) as exc:
                self.set_error('画质增强未启用：' + str(exc))

    def load_beauty(self):
        self.beauty_timer.stop()
        from .beauty import validate
        value=validate(self.subtitle_preferences.get('beauty',{}))
        for control,key in ((self.beauty_enabled,'enabled'),(self.beauty_smoothing,'smoothing'),(self.beauty_brighten,'brighten')):
            control.blockSignals(True)
            control.setChecked(value[key]) if key=='enabled' else control.setValue(round(value[key]))
            control.blockSignals(False)
        if self.mpv_backend:self.media.set_beauty(value,self.library.directory/'cache'/'beauty')

    def save_beauty(self):
        self.beauty_timer.stop()
        if not self.file or not self.mpv_backend:return
        from .media_tools import preferences
        value={'enabled':self.beauty_enabled.isChecked(),'smoothing':self.beauty_smoothing.value(),'brighten':self.beauty_brighten.value()}
        try:
            self.media.set_beauty(value,self.library.directory/'cache'/'beauty')
            self.subtitle_preferences=preferences(self.library,self.file['id'],{'beauty':value})
        except (ValueError,RuntimeError,OSError) as exc:self.set_error('美颜设置未应用：'+str(exc))

    def shutdown_mpv(self):
        if self.mpv_backend:
            self.media.shutdown()
            self.mpv_backend = False

    def control_icon(self, standard):
        pixmap = self.style().standardIcon(standard).pixmap(24, 24)
        painter = QPainter(pixmap)
        painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceIn)
        painter.fillRect(pixmap.rect(), QColor('white'))
        painter.end()
        return QIcon(pixmap)

    def eventFilter(self, watched, event):
        if not self.mpv_backend and watched is self.canvas.viewport() and event.type() == QEvent.Type.Resize:
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
        self.overlay.setGeometry(area)
        width = area.width()
        self.ends_at.setVisible(width >= 1000)
        self.rating.setVisible(width >= 760)
        self.volume.setVisible(width >= 640)
        self.bookmark_control.setText('书签' if width>=760 else '')
        self.previous_control.setVisible(width >= 540)
        self.next_control.setVisible(width >= 540)
        self.overlay.layout().invalidate()
        self.overlay.layout().activate()
        self.position_caption()
        self.overlay.raise_()
        self.update_overlay_mask()

    def update_overlay_mask(self):
        if not self.mpv_backend:
            return
        region = QRegion()
        for widget in (self.header, self.footer, self.caption, self.error):
            if not widget.isHidden() and (widget in (self.header, self.footer) or widget.text()):
                region = region.united(QRegion(widget.geometry()))
        if region.isEmpty():
            self.overlay.hide()
        else:
            self.overlay.setMask(region)
            self.overlay.show()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.sync_overlay()

    def showEvent(self, event):
        super().showEvent(event)
        self.last_cursor = QCursor.pos()
        self.pointer_timer.start()
        self.show_controls()
        if self.isFullScreen():
            QTimer.singleShot(0, self.apply_native_fullscreen)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and hasattr(self, 'idle'):
            QTimer.singleShot(0, self.show_controls)
            if self.isFullScreen():
                QTimer.singleShot(0, self.apply_native_fullscreen)

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
        self.update_overlay_mask()
        self.overlay.unsetCursor()
        if self.auto_hide.isChecked():
            self.idle.start()
        else:
            self.idle.stop()

    def hide_controls(self):
        if not getattr(self,'_personal_menu',None) and self.auto_hide.isChecked() and self.media.playbackState() == QMediaPlayer.PlaybackState.PlayingState and not any(dialog.isVisible() for dialog in self.findChildren(QDialog)) and not self.timeline.isSliderDown() and not self.footer.underMouse():
            self.header.hide()
            self.footer.hide()
            self.overlay.setCursor(Qt.CursorShape.BlankCursor)
            self.update_overlay_mask()

    def show_settings(self):
        self.track_dialog.show()
        self.track_dialog.raise_()

    def update_like(self, work):
        from .components import icon
        for control,key,name,color in [(self.like,'favorite','heart','#f4779b'),(self.negative,'disliked','ban','#ef8b87')]:
            active=bool(work.get(key));control.setChecked(active);control.setEnabled(True)
            text={'favorite':('喜欢／收藏','喜欢／收藏'),'liked':('已喜欢','喜欢'),'disliked':('不喜欢','不喜欢')}[key][0 if active else 1]
            control.setText(text);control.setIcon(icon(name,color if active else '#dddddd',active and name=='heart'))
            control.setToolTip(('取消' if active else '确认')+{'favorite':'喜欢 / 收藏','liked':'喜欢','disliked':'不喜欢'}[key]);control.setStyleSheet('color: '+(color if active else '#eeeeee'))
        self.personal_rating.setEnabled(True);self.personal_rating.setText(f"我的 {work['rating']} 分" if work.get('rating') is not None else '评分')
        self.personal_rating.setIcon(icon('star','#e7c567',work.get('rating') is not None))
        source=next((s for s in work.get('sources',[]) if s.get('rating') is not None),None)
        self.rating.setText(f"来源 ★ {source['rating']:.1f}" if source else '来源暂无评分')

    def save_personal(self, fields, work_id=None):
        if not self.file:return
        target=work_id if work_id is not None else self.file['work_id']
        try:self.library.update_personal(target,**fields)
        except Exception as error:
            self.set_error('偏好未保存：'+str(error));self.update_like(self.library.work(self.file['work_id']));return
        if self.error.text().startswith('偏好未保存：'):self.set_error(self.backend_message)
        if self.file and self.file['work_id']==target:self.update_like(self.library.work(target))
        self.show_controls();self.refreshed.emit()

    def toggle_like(self):
        self.save_personal({'favorite':self.like.isChecked()})

    def choose_personal_rating(self):
        if not self.file:return
        work_id=self.file['work_id'];current=self.library.work(work_id)['rating'];menu=QMenu(self)
        for value in [None,*range(1,11)]:
            action=menu.addAction('清除评分' if value is None else f'{value} 分');action.setCheckable(True);action.setChecked(current==value)
            action.triggered.connect(lambda checked=False,value=value:self.save_personal({'rating':value},work_id))
        self._personal_menu=menu;self.show_controls();self.idle.stop()
        try:menu.exec(self.personal_rating.mapToGlobal(self.personal_rating.rect().bottomLeft()))
        finally:self._personal_menu=None;self.show_controls()

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

    def previous_item(self):
        if not self.previous_episode():
            self.queuePrevious.emit()

    def open_file(self, file):
        if self.beauty_timer.isActive():self.save_beauty()
        self.finish()
        if not Path(file['path']).is_file():
            self.file=None
            for action_button in [self.personal_rating,self.like,self.negative]:action_button.setEnabled(False)
            self.title.setText('视频文件离线');self.caption.clear();self.caption.hide()
            self.set_error('文件不存在，请检查磁盘或重新导入：' + file['path'])
            self.show()
            return
        self.file = file
        from .media_tools import preferences
        self.subtitle_preferences=preferences(self.library,file['id'])
        for control,key,default in ((self.subtitle_delay,'subtitle_delay',0),(self.subtitle_size,'subtitle_size',22),(self.subtitle_position,'subtitle_position',90)):
            control.blockSignals(True);control.setValue(self.subtitle_preferences.get(key,default));control.blockSignals(False)
        self.apply_subtitle_preferences()
        self.load_beauty()
        work = self.library.work(file['work_id'])
        self.title.setToolTip(work['title'])
        self.title.setText(work['title'] + (f" · S{file['season']:02}E{file['episode']:02}" if work['kind'] == 'series' and file['season'] is not None and file['episode'] is not None else ''))
        if work['kind']=='fans':self.title.setText(work['title']+' · '+Path(file['path']).stem)
        previous,next_item=(('上一视频','下一视频') if work['kind']=='fans' else
                            ('上一集','下一集') if work['kind']=='series' else ('上一作品','下一集 / 下一作品'))
        for control,text in ((self.previous_control,previous),(self.next_control,next_item)):
            control.setToolTip(text);control.setAccessibleName(text)
        self.update_like(work)
        self.show_controls()
        self.set_error(self.backend_message)
        self.cues = []
        self.caption.clear()
        source = Path(file['path'])
        candidates = [p for p in source.parent.iterdir() if p.suffix.lower() in {'.srt','.ass','.ssa','.vtt'} and (p.stem == source.stem or p.name.startswith(source.stem + '.'))]
        if candidates:
            self.load_subtitle(sorted(candidates)[0])
        self.resume = file['position'] if not file['completed'] else 0
        self.session = PlaybackSession(self.playback_journal, file['id'])
        # libmpv's render context must exist before opening its first video.
        self.show()
        if self.mpv_backend:
            self.media.attach_window(int(self.canvas.winId()))
            self.audio.setVolume(self.audio.volume)
            self.audio.setMuted(self.audio.muted)
        generation = self._open_generation
        def start_source():
            if generation != self._open_generation or not self.isVisible():
                return
            self.media.setSource(QUrl.fromLocalFile(file['path']))
            self.media.play()
        if self.mpv_backend:
            self.canvas.when_ready(start_source)
        else:
            start_source()
        self.show()
        self.raise_()

    def duration_changed(self, milliseconds):
        self.timeline.setRange(0, milliseconds)
        if self.file and milliseconds > 0:
            self.playback_journal.duration(self.file['id'],milliseconds/1000)

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
        subtitle_time=position/1000-self.subtitle_preferences.get('subtitle_delay',0)
        text = '\n'.join(cue[2] for cue in self.cues if cue[0] <= subtitle_time < cue[1]) if self.external_subtitle_enabled else ''
        self.caption.setText(text)
        self.caption.setVisible(bool(text))
        self.position_caption()
        if self.mpv_backend:
            self.overlay.layout().activate()
            self.update_overlay_mask()

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
            self.playback_journal.completed(self.file['id'])
            if self.library.work(self.file['work_id'])['kind'] in {'series','fans'}:
                if not self.library.setting('auto_next',True):return
                if self.next_episode():return
            if getattr(self.parent(),'random_active',False) and self.library.setting('queue',{}).get('repeat')=='one':
                work=self.library.work(self.file['work_id'])
                first=work['files'][0] if work['kind'] in {'series','fans'} else self.library.resume_file(work['id'])
                self.open_file({**first,'position':0});return
            self.finish()
            self.queueNext.emit()

    def next_episode(self):
        return self.step_group_file(1)

    def previous_episode(self):
        return self.step_group_file(-1)

    def step_group_file(self,direction):
        if not self.file:
            return False
        work = self.library.work(self.file['work_id'])
        if work['kind'] not in {'series','fans'}:
            return False
        files = work['files']
        index = next((i for i, f in enumerate(files) if f['id'] == self.file['id']),-1)
        target=index+direction
        if index>=0 and 0<=target<len(files):
            self.open_file(files[target])
            return True
        return False

    def tracks_changed(self):
        from PySide6.QtMultimedia import QMediaMetaData
        for box, tracks, off in [(self.subtitles, self.media.subtitleTracks(), True), (self.audio_tracks, self.media.audioTracks(), False)]:
            box.blockSignals(True)
            box.clear()
            if off:
                box.addItem('关闭字幕', -1)
                if self.cues:box.addItem('外挂字幕',-2)
            for i, track in enumerate(tracks):
                box.addItem(track.stringValue(QMediaMetaData.Key.Title) or track.stringValue(QMediaMetaData.Key.Language) or f'轨道 {i + 1}', i)
            active = (-2 if self.cues and self.external_subtitle_enabled else self.media.activeSubtitleTrack()) if off else self.media.activeAudioTrack()
            box.setCurrentIndex(box.findData(active))
            box.blockSignals(False)

    def select_subtitle(self,index):
        self.external_subtitle_enabled=index==-2
        self.media.setActiveSubtitleTrack(-1 if index==-2 else index)
        self.position_changed(self.media.position())

    def load_subtitle(self, path):
        from .subtitles import read_subtitles
        try:
            self.cues = read_subtitles(path)
            self.external_subtitle_enabled = True
        except Exception as exc:
            self.set_error('外挂字幕未载入：' + str(exc))

    def choose_subtitle(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择外挂字幕', '', '字幕 (*.srt *.ass *.ssa *.vtt)')
        if path:
            self.load_subtitle(path)

    def toggle_external_subtitle(self):
        self.external_subtitle_enabled = not self.external_subtitle_enabled
        self.position_changed(self.media.position())

    def position_caption(self):
        width=max(1,self.overlay.width()-32)
        height=self.caption.heightForWidth(width)
        if height<0:height=self.caption.sizeHint().height()
        y=int(self.overlay.height()*self.subtitle_preferences.get('subtitle_position',90)/100)-height
        if self.footer.isVisible():y=min(y,self.footer.y()-height-8)
        self.caption.setGeometry(16,max(0,min(self.overlay.height()-height,y)),width,height)
        self.caption.raise_()

    def apply_subtitle_preferences(self):
        value=self.subtitle_preferences
        self.caption.setStyleSheet(f"font-size: {value.get('subtitle_size',22)}px; color:white; background:transparent; padding:6px;")
        if self.mpv_backend:self.media.set_subtitle_style(value.get('subtitle_delay',0),value.get('subtitle_size',22),value.get('subtitle_position',90))
        self.position_changed(self.media.position())

    def save_subtitle_preferences(self):
        if not self.file:return
        from .media_tools import preferences
        self.subtitle_preferences=preferences(self.library,self.file['id'],{'subtitle_delay':self.subtitle_delay.value(),'subtitle_size':self.subtitle_size.value(),'subtitle_position':self.subtitle_position.value()})
        self.apply_subtitle_preferences()

    def add_bookmark(self,*,file=None,position=None,parent=None):
        file=file or self.file
        if not file:return
        existing=getattr(self,'_bookmark_dialog',None)
        if existing is not None and existing.isVisible():existing.raise_();existing.activateWindow();return existing
        active=self.file is not None and self.file['id']==file['id'] and self.isVisible()
        # Capture the position before the user starts typing, not after saving.
        moment=position if position is not None else self.media.position()/1000 if active else file.get('position',0)
        maximum=(self.media.duration()/1000 if active else file.get('duration',0)) or 864000
        dialog=QDialog(parent or self);self._bookmark_dialog=dialog;dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.setWindowTitle('添加时间点书签');dialog.resize(500,340)
        layout=QVBoxLayout(dialog);form=QFormLayout();layout.addLayout(form)
        time=QDoubleSpinBox();time.setObjectName('bookmarkTime');time.setRange(0,maximum);time.setDecimals(1);time.setSuffix(' 秒');time.setValue(min(maximum,max(0,moment)))
        name=QLineEdit();name.setObjectName('bookmarkName');name.setMaxLength(120);name.setPlaceholderText('可留空，默认使用时间点')
        note=QPlainTextEdit();note.setObjectName('bookmarkNote');note.setPlaceholderText('备注（最多 2000 字）');note.setMaximumHeight(100)
        filename=QLabel(Path(file['path']).name);filename.setWordWrap(True)
        form.addRow('视频',filename);form.addRow('时间点',time);form.addRow('名称',name);form.addRow('备注',note)
        screenshot=QCheckBox('后台生成此时间点截图');screenshot.setChecked(True);layout.addWidget(screenshot)
        message=QLabel('时间点已固定，可继续播放；也可以手动调整秒数。');message.setWordWrap(True);layout.addWidget(message)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel);layout.addWidget(buttons);buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.Save).setText('保存');buttons.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        def save():
            from .media_tools import add_bookmark,capture_bookmark
            try:item=add_bookmark(self.library,file['id'],time.value(),name.text(),note.toPlainText())
            except (ValueError,RuntimeError) as error:message.setText(str(error));return
            capture=screenshot.isChecked();dialog.accept();self.bookmarksChanged.emit()
            owner=self.parentWidget()
            if capture and hasattr(owner,'run_job'):owner.run_job('书签截图',lambda lib,p:capture_bookmark(lib,item['id'],p.cancelled),lambda _:self.bookmarksChanged.emit())
        buttons.accepted.connect(save);dialog.finished.connect(lambda _:setattr(self,'_bookmark_dialog',None));dialog.show();name.setFocus();return dialog

    def show_bookmarks(self):
        if not self.file:return
        from .media_tools import bookmarks,delete_bookmark
        existing=getattr(self,'_bookmarks_dialog',None)
        if existing is not None and existing.isVisible():existing.raise_();return existing
        file_id=self.file['id']
        dialog=QDialog(self);self._bookmarks_dialog=dialog;dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.setWindowTitle('时间点书签');dialog.resize(600,450)
        layout=QVBoxLayout(dialog);items=QListWidget();items.setIconSize(QSize(144,81));layout.addWidget(items)
        empty=QLabel('还没有书签。点击“添加当前时间点”保存位置与截图。');empty.setWordWrap(True);layout.addWidget(empty)
        def reload():
            items.clear()
            for entry in bookmarks(self.library,file_id):
                row=QListWidgetItem(f"{int(entry['position'])//60:02}:{int(entry['position'])%60:02} · {entry['title']}\n{entry['note']}")
                row.setData(Qt.ItemDataRole.UserRole,entry)
                if entry['image']:row.setIcon(QIcon(entry['image']))
                items.addItem(row)
            empty.setVisible(items.count()==0)
            if items.count():items.setCurrentRow(0)
        def jump():
            if not items.currentItem():return
            position=items.currentItem().data(Qt.ItemDataRole.UserRole)['position']
            if not self.file or self.file['id']!=file_id:
                file=dict(self.library.db.execute('SELECT * FROM files WHERE id=?',(file_id,)).fetchone());self.open_file({**file,'position':position,'completed':0})
            else:self.timeline.setValue(int(position*1000));self.seek()
            dialog.accept()
        def remove():
            if items.currentItem():delete_bookmark(self.library,items.currentItem().data(Qt.ItemDataRole.UserRole)['id']);self.bookmarksChanged.emit()
        def capture():
            if not items.currentItem():return
            from .media_tools import capture_bookmark
            identifier=items.currentItem().data(Qt.ItemDataRole.UserRole)['id'];parent=self.parentWidget()
            if hasattr(parent,'run_job'):parent.run_job('书签截图',lambda lib,p:capture_bookmark(lib,identifier,p.cancelled),lambda _:self.bookmarksChanged.emit())
        layout.addWidget(QPushButton('添加当前时间点…',clicked=lambda:self.add_bookmark(file=dict(self.library.db.execute('SELECT * FROM files WHERE id=?',(file_id,)).fetchone()),parent=dialog)))
        items.itemDoubleClicked.connect(lambda _:jump());layout.addWidget(QPushButton('跳转到选中书签',clicked=jump));layout.addWidget(QPushButton('生成 / 更新选中截图',clicked=capture));layout.addWidget(QPushButton('删除选中书签',clicked=remove))
        self.bookmarksChanged.connect(reload)
        def closed(_):
            self.bookmarksChanged.disconnect(reload);self._bookmarks_dialog=None
        dialog.finished.connect(closed);reload();dialog.show();return dialog

    def diagnostics(self):
        value={'backend':'libmpv' if self.mpv_backend else 'Qt Multimedia','position_seconds':self.media.position()/1000,
               'duration_seconds':self.media.duration()/1000,'rate':self.media.playbackRate(),'state':self.media.playbackState().name,
               'subtitle_delay':self.subtitle_preferences.get('subtitle_delay',0)}
        if self.mpv_backend:value.update(self.media.diagnostics())
        else:
            from PySide6.QtMultimedia import QMediaMetaData
            metadata=self.media.metaData();resolution=metadata.value(QMediaMetaData.Key.Resolution)
            value.update(video_codec=metadata.stringValue(QMediaMetaData.Key.VideoCodec),audio_codec=metadata.stringValue(QMediaMetaData.Key.AudioCodec),
                         resolution=f'{resolution.width()}×{resolution.height()}' if resolution else None,buffer_percent=round(self.media.bufferProgress()*100),
                         hardware_decoder='Qt 未提供实际硬解状态',dropped_frames=None)
        return value

    def show_diagnostics(self):
        import json
        dialog=QDialog(self);dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose);dialog.setWindowTitle('播放诊断');dialog.resize(650,500)
        layout=QVBoxLayout(dialog);text=QPlainTextEdit();text.setReadOnly(True);layout.addWidget(text)
        update=lambda:text.setPlainText(json.dumps(self.diagnostics(),ensure_ascii=False,indent=2,default=str))
        layout.addWidget(QPushButton('复制诊断（不含路径和访问密钥）',clicked=lambda:QApplication.clipboard().setText(text.toPlainText())))
        timer=QTimer(dialog);timer.setInterval(1000);timer.timeout.connect(update);timer.start();update();dialog.show()

    def toggle_fullscreen(self):
        entering = not self.isFullScreen()
        canvas_id=int(self.canvas.winId()) if self.mpv_backend else None
        if entering:
            self._windowed_geometry = self.saveGeometry()
            self._windowed_flags = self.windowFlags()
            # Qt removes native decorations in fullscreen itself. Changing flags
            # hides/recreates the window and used to force a decoder restart.
            self.showFullScreen()
        else:
            set_fullscreen_window(self.winId(), False)
            self.restore_windowed()
        self.raise_()
        self.activateWindow()
        if entering:
            self.apply_native_fullscreen()
        if self.mpv_backend and int(self.canvas.winId())!=canvas_id:
            # Recover only on platforms which actually replaced the native host.
            self.media.detach_window()
            self.media.attach_window(int(self.canvas.winId()))
        self.show_controls()

    def apply_native_fullscreen(self):
        # Queued state/resize events must not re-enter fullscreen after Esc or
        # after the player has closed. Do not promote it on Alt+Tab either.
        if self.isFullScreen() and self.isVisible() and not self.isMinimized():
            set_fullscreen_window(self.winId(), True)
            self.sync_overlay()

    def restore_windowed(self, show=True):
        self.setWindowState(self.windowState() & ~Qt.WindowState.WindowFullScreen)
        if self._windowed_geometry is not None:
            self.restoreGeometry(self._windowed_geometry)
        else:
            self.setWindowState(Qt.WindowState.WindowNoState)
        if show:
            self.show()
        self._windowed_geometry = self._windowed_flags = None

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.toggle_fullscreen()
        elif event.key() == Qt.Key.Key_F:
            self.toggle_fullscreen()
        elif event.key() in {Qt.Key.Key_Left, Qt.Key.Key_Right}:
            self.jump(-10000 if event.key() == Qt.Key.Key_Left else 10000)
        elif event.key() == Qt.Key.Key_Space:
            self.toggle()
        else:
            super().keyPressEvent(event)

    def finish(self):
        if hasattr(self,'beauty_timer') and self.beauty_timer.isActive():self.save_beauty()
        self._open_generation += 1
        if self.session:
            self.sample()
            self.session.finish()
            self.session = None
        self.media.stop()
        self.refreshed.emit()

    def closeEvent(self, event):
        self.finish()
        if self.mpv_backend:
            self.media.detach_window(False)
        if self.isFullScreen():
            set_fullscreen_window(self.winId(), False)
            self.restore_windowed(show=False)
        for dialog in self.findChildren(QDialog):dialog.close()
        self.idle.stop()
        self.pointer_timer.stop()
        super().closeEvent(event)
