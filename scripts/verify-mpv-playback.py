"""Verify libmpv in its own process, isolated from Qt FFmpeg backend libraries."""
import os
from PySide6.QtCore import QUrl, QEventLoop, QTimer
from PySide6.QtMultimedia import QMediaPlayer
from lumen.mpv_backend import MpvMedia, MpvAudio


def wait(app, milliseconds=400):
    loop=QEventLoop();QTimer.singleShot(milliseconds,loop.quit);loop.exec();app.processEvents()


def check(qapp, source):
    try:
        media=MpvMedia(headless=True)
    except OSError:
        raise
    errors=[];ends=[]
    media.errorOccurred.connect(lambda _code,message:errors.append(message))
    media.mediaStatusChanged.connect(lambda status:ends.append(status))
    try:
        media.setSource(QUrl.fromLocalFile(str(source)));media.play();wait(qapp,900)
        assert not errors
        assert 5900<=media.duration()<=6200
        assert media.position()>0
        assert media.playbackState()==QMediaPlayer.PlaybackState.PlayingState
        media.pause();wait(qapp)
        assert media.playbackState()==QMediaPlayer.PlaybackState.PausedState
        media.setPosition(3500);wait(qapp)
        assert 3400<=media.position()<=3700
        audio=MpvAudio(media.engine);audio.setVolume(.25);audio.setMuted(True)
        assert audio.isMuted() and media.engine.volume==25
        media.set_enhancement(True)
        assert media.engine.scale=='spline36' and len(media.engine.glsl_shaders)==1
        media.set_enhancement(False)
        assert not media.engine.glsl_shaders
        media.setPosition(5400);media.play();wait(qapp,1200)
        assert ends.count(QMediaPlayer.MediaStatus.EndOfMedia)==1
        media.stop();wait(qapp)
        assert media.playbackState()==QMediaPlayer.PlaybackState.StoppedState
        # Reopening the same file must emit loaded/end events again.
        media.setSource(QUrl.fromLocalFile(str(source)));media.play();wait(qapp)
        assert media.position()<1500
        assert not errors
    finally:
        media.shutdown()

if __name__ == '__main__':
    import sys
    from PySide6.QtCore import QCoreApplication
    app=QCoreApplication([])
    check(app, sys.argv[1])
    print('libmpv decode, seek, audio, shader options, EOF and reopen passed')
