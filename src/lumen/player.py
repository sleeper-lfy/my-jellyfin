from pathlib import Path
from PySide6.QtCore import Qt, QTimer, QUrl, Signal
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider, QComboBox, QFileDialog
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
from PySide6.QtMultimediaWidgets import QVideoWidget
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
        self.video = QVideoWidget()
        self.video.setMinimumSize(480, 270)
        self.media = QMediaPlayer(self)
        self.audio = QAudioOutput(self)
        self.audio.setVolume(.7)
        self.media.setAudioOutput(self.audio)
        self.media.setVideoOutput(self.video)
        layout = QVBoxLayout(self)
        self.title = QLabel()
        self.title.setObjectName('heading')
        layout.addWidget(self.title)
        layout.addWidget(self.video, 1)
        self.caption = QLabel()
        self.caption.setTextFormat(Qt.TextFormat.PlainText)
        self.caption.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.caption.setWordWrap(True)
        self.caption.setStyleSheet('font-size: 19px; color: #f7f8ff; padding: 6px;')
        layout.addWidget(self.caption)
        self.timeline = QSlider(Qt.Orientation.Horizontal)
        self.timeline.sliderReleased.connect(self.seek)
        layout.addWidget(self.timeline)
        row = QHBoxLayout()
        self.pause = QPushButton('暂停')
        self.pause.clicked.connect(self.toggle)
        row.addWidget(self.pause)
        previous = QPushButton('上一作品')
        previous.clicked.connect(self.queuePrevious.emit)
        row.addWidget(previous)
        next_episode = QPushButton('剧内下一集')
        next_episode.clicked.connect(self.next_episode)
        row.addWidget(next_episode)
        next_work = QPushButton('随机下一作品')
        next_work.clicked.connect(self.queueNext.emit)
        row.addWidget(next_work)
        self.time_label = QLabel('00:00 / 00:00')
        row.addWidget(self.time_label)
        row.addStretch()
        volume = QSlider(Qt.Orientation.Horizontal)
        volume.setRange(0, 100)
        volume.setValue(70)
        volume.setMaximumWidth(100)
        volume.valueChanged.connect(lambda v: self.audio.setVolume(v / 100))
        row.addWidget(QLabel('音量'))
        row.addWidget(volume)
        layout.addLayout(row)
        tracks = QHBoxLayout()
        self.subtitles = QComboBox()
        self.subtitles.currentIndexChanged.connect(lambda i: self.media.setActiveSubtitleTrack(self.subtitles.itemData(i)) if self.subtitles.itemData(i) is not None else None)
        self.audio_tracks = QComboBox()
        self.audio_tracks.currentIndexChanged.connect(lambda i: self.media.setActiveAudioTrack(self.audio_tracks.itemData(i)) if self.audio_tracks.itemData(i) is not None else None)
        tracks.addWidget(QLabel('字幕'))
        tracks.addWidget(self.subtitles)
        tracks.addWidget(QLabel('音轨'))
        tracks.addWidget(self.audio_tracks)
        full = QPushButton('全屏 / 退出')
        full.clicked.connect(self.toggle_fullscreen)
        tracks.addWidget(QPushButton('外挂字幕…', clicked=self.choose_subtitle))
        tracks.addWidget(QPushButton('开关外挂字幕', clicked=self.toggle_external_subtitle))
        tracks.addWidget(full)
        layout.addLayout(tracks)
        self.error = QLabel()
        self.error.setWordWrap(True)
        layout.addWidget(self.error)
        self.media.tracksChanged.connect(self.tracks_changed)
        self.media.durationChanged.connect(lambda value: self.timeline.setRange(0, value))
        self.media.positionChanged.connect(self.position_changed)
        self.media.mediaStatusChanged.connect(self.status_changed)
        self.media.playbackStateChanged.connect(self.state_changed)
        self.media.errorOccurred.connect(lambda _code, message: self.error.setText('播放错误：' + message))
        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.sample)
        self.timer.start()

    def open_file(self, file):
        self.finish()
        if not Path(file['path']).is_file():
            self.error.setText('文件不存在，请检查磁盘或重新导入：' + file['path'])
            self.show()
            return
        self.file = file
        work = self.library.work(file['work_id'])
        self.title.setText(work['title'] + (f" · S{file['season']:02}E{file['episode']:02}" if work['kind'] == 'series' else ''))
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

    def position_changed(self, position):
        if not self.timeline.isSliderDown():
            self.timeline.setValue(position)
        def stamp(ms):
            seconds = ms // 1000
            return f'{seconds // 3600:02}:{seconds // 60 % 60:02}:{seconds % 60:02}'
        self.time_label.setText(f'{stamp(position)} / {stamp(self.media.duration())}')
        text = '\n'.join(cue[2] for cue in self.cues if cue[0] <= position/1000 < cue[1]) if self.external_subtitle_enabled else ''
        self.caption.setText(text)

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
        self.pause.setText('暂停' if state == QMediaPlayer.PlaybackState.PlayingState else '继续')
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

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape and self.isFullScreen():
            self.showNormal()
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
        super().closeEvent(event)
