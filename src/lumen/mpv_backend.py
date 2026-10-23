"""libmpv playback with a native GPU render target and Qt playback signals."""
import os
import sys
from pathlib import Path
from PySide6.QtCore import QObject, Signal, QTimer, Qt, QUrl
from PySide6.QtWidgets import QWidget
from PySide6.QtMultimedia import QMediaPlayer, QMediaMetaData


def load_mpv():
    if sys.platform == 'win32':
        directory = Path(getattr(sys, '_MEIPASS', Path(__file__).parent)) / 'lumen' / 'bin'
        if not directory.exists():
            directory = Path(__file__).resolve().parents[2] / '.local' / 'mpv-bundle'
        if directory.exists():
            os.environ['PATH'] = str(directory) + os.pathsep + os.environ.get('PATH', '')
    import mpv
    return mpv


class MpvAudio:
    def __init__(self, owner):
        self.owner=owner
        self.volume=.7
        self.muted=False
    @property
    def engine(self): return self.owner.engine if isinstance(self.owner,MpvMedia) else self.owner
    def setVolume(self, value):
        self.volume=max(0,min(1,value))
        if self.engine is not None:self.engine.volume=self.volume*100
    def setMuted(self, value):
        self.muted=value
        if self.engine is not None:self.engine.mute=value
    def isMuted(self): return self.muted


class Track:
    def __init__(self, data): self.data = data
    def stringValue(self, key):
        return self.data.get('title' if key == QMediaMetaData.Key.Title else 'lang', '')


class MpvMedia(QObject):
    keyPressed = Signal(str)
    tracksChanged = Signal()
    durationChanged = Signal(int)
    positionChanged = Signal(int)
    mediaStatusChanged = Signal(object)
    playbackStateChanged = Signal(object)
    errorOccurred = Signal(object, str)

    def __init__(self, parent=None, *, headless=False, window_id=None):
        super().__init__(parent)
        self.binding = load_mpv()
        self.headless=headless
        self.engine=self.create_engine(window_id)
        self._suspended=None
        self._seek_on_load=None
        self.enhanced=False
        self.subtitle_style={}
        self._state = QMediaPlayer.PlaybackState.StoppedState
        self._status = QMediaPlayer.MediaStatus.NoMedia
        self._duration = self._position = 0
        self._tracks = []
        self._loaded = False
        self._source = ''
        self._ended = False
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.poll)
        self.timer.start()

    def create_engine(self, window_id):
        headless=self.headless
        engine=self.binding.MPV(vo='null' if headless else ('gpu-next' if sys.platform == 'win32' else 'gpu'),
            hwdec='auto-safe', keep_open='yes', idle=True, config=False,
            input_default_bindings=False, input_vo_keyboard=True, osc=False,
            audio_channels='stereo', sub_auto='no', gpu_sw=os.environ.get('LUMEN_ALLOW_SOFTWARE_GPU')=='1', **({'ao': 'null'} if headless else {'wid':str(window_id)}))
        if not headless:
            for key in ('LEFT','RIGHT','SPACE','f','ESC'):
                engine.on_key_press(key)(lambda key=key:self.keyPressed.emit(key))
        return engine

    def detach_window(self, preserve=True):
        self.timer.stop()
        if self.engine is not None:
            if preserve and self._source:
                self._suspended=(self._source,int((self.engine.time_pos or self._position/1000)*1000),not self.engine.pause,
                                 self.engine.volume,self.engine.mute,self.engine.speed)
            else:
                self._suspended=None
                self._source=''
            self.engine.terminate()
            self.engine=None

    def attach_window(self, window_id):
        if self.engine is not None:return
        self.engine=self.create_engine(window_id)
        saved,self._suspended=self._suspended,None
        self.set_enhancement(self.enhanced)
        self.set_subtitle_style(**self.subtitle_style)
        if saved:
            source,position,playing,volume,muted,speed=saved
            self.setSource(QUrl.fromLocalFile(source))
            self._seek_on_load=position
            self.engine.volume=volume;self.engine.mute=muted;self.engine.speed=speed
            if playing:self.play()
        self.timer.start()

    def setSource(self, url):
        self.stop()
        self._source = url.toLocalFile()
        self._duration = self._position = 0
        self._loaded = self._ended = False
        self._seek_on_load=None
        self._tracks = []
        self.engine.pause = True
        self.engine.command('loadfile', self._source, 'replace')
        self._status = QMediaPlayer.MediaStatus.LoadingMedia
        self.mediaStatusChanged.emit(self._status)

    def play(self):
        if self.engine is not None:self.engine.pause = False
    def pause(self):
        if self.engine is not None:self.engine.pause = True
    def stop(self):
        if self.engine is not None:self.engine.command('stop')
        self._loaded = False
        self._source = ''
        self._status = QMediaPlayer.MediaStatus.NoMedia
        self._state = QMediaPlayer.PlaybackState.StoppedState
    def duration(self): return self._duration
    def position(self): return self._position
    def playbackState(self): return self._state
    def mediaStatus(self): return self._status
    def playbackRate(self): return float(self.engine.speed or 1) if self.engine is not None else 1.0
    def setPlaybackRate(self, rate): self.engine.speed = rate
    def setPosition(self, milliseconds):
        if self._loaded:
            self.engine.command('seek', max(0, milliseconds / 1000), 'absolute+exact')
            self._position = max(0, milliseconds)
    def audioTracks(self): return [Track(t) for t in self._tracks if t['type'] == 'audio']
    def subtitleTracks(self): return [Track(t) for t in self._tracks if t['type'] == 'sub']
    def active_track(self, kind):
        return next((i for i, t in enumerate(t for t in self._tracks if t['type'] == kind) if t.get('selected')), -1)
    def activeAudioTrack(self): return self.active_track('audio')
    def activeSubtitleTrack(self): return self.active_track('sub')
    def select_track(self, kind, index):
        tracks = [t for t in self._tracks if t['type'] == kind]
        self.engine[kind == 'sub' and 'sid' or 'aid'] = tracks[index]['id'] if 0 <= index < len(tracks) else 'no'
    def setActiveAudioTrack(self, index): self.select_track('audio', index)
    def setActiveSubtitleTrack(self, index): self.select_track('sub', index)
    def set_enhancement(self, enabled):
        self.enhanced=enabled
        if self.engine is None:return
        # Bundled, bounded sharpening only. Never execute arbitrary downloaded shaders.
        self.engine.scale = 'spline36' if enabled else 'bilinear'
        self.engine.dscale = 'mitchell' if enabled else 'bilinear'
        self.engine.cscale = 'spline36' if enabled else 'bilinear'
        self.engine.glsl_shaders = [str(Path(__file__).with_name('shaders') / 'gentle-sharpen.glsl')] if enabled else []

    def set_subtitle_style(self,delay=0,size=22,position=90):
        self.subtitle_style={'delay':delay,'size':size,'position':position}
        if self.engine is not None:
            self.engine.sub_delay=delay;self.engine.sub_font_size=size;self.engine.sub_pos=position

    def diagnostics(self):
        values={}
        if self.engine is not None:
            for key in ('video-codec','audio-codec','video-params','hwdec-current','decoder-frame-drop-count','frame-drop-count','avsync','demuxer-cache-duration','cache-speed'):
                try:values[key]=self.engine[key]
                except (RuntimeError,AttributeError,ValueError):values[key]=None
        return values

    def poll(self):
        if not self._source or self.engine is None: return
        try:
            position = self.engine.time_pos
            if position is None:
                if self.engine.idle_active:
                    self._source = ''
                    self._status = QMediaPlayer.MediaStatus.InvalidMedia
                    self.errorOccurred.emit(0, 'libmpv 无法打开视频，请检查文件或解码支持')
                return
            duration = int((self.engine.duration or 0) * 1000)
            if duration != self._duration:
                self._duration = duration
                self.durationChanged.emit(duration)
            self._position = int(position * 1000)
            if not self._loaded:
                self._loaded = True
                if self._seek_on_load is not None:
                    self.setPosition(self._seek_on_load)
                    self._seek_on_load=None
                self._status = QMediaPlayer.MediaStatus.LoadedMedia
                self.mediaStatusChanged.emit(self._status)
            tracks = self.engine.track_list or []
            if tracks != self._tracks:
                self._tracks = tracks
                self.tracksChanged.emit()
            state = QMediaPlayer.PlaybackState.PausedState if self.engine.pause else QMediaPlayer.PlaybackState.PlayingState
            if state != self._state:
                self._state = state
                self.playbackStateChanged.emit(state)
            self._status = QMediaPlayer.MediaStatus.StalledMedia if self.engine.paused_for_cache else QMediaPlayer.MediaStatus.BufferedMedia
            self.positionChanged.emit(self._position)
            if self.engine.eof_reached and not self._ended:
                self._ended = True
                self._status = QMediaPlayer.MediaStatus.EndOfMedia
                self.mediaStatusChanged.emit(self._status)
            elif not self.engine.eof_reached:
                self._ended = False
        except (RuntimeError, ValueError) as exc:
            self.errorOccurred.emit(0, str(exc))

    def shutdown(self):
        self.timer.stop()
        if self.engine is not None:
            self.engine.terminate()
            self.engine=None


class MpvCanvas(QWidget):
    """Native host: mpv owns GPU rendering; controls live in a masked sibling."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.setStyleSheet('background: black; border: none;')

    def viewport(self): return self

    def when_ready(self, callback):
        QTimer.singleShot(0, callback)
