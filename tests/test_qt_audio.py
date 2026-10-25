"""Compatibility audio must never acquire the GIL in native notify callbacks."""
import json
import os
from pathlib import Path
import subprocess
import sys

from PySide6.QtCore import QObject
from PySide6.QtMultimedia import QAudioOutput
import shiboken6

from lumen.qt_audio import native_audio_output


def test_native_audio_factory_ownership_lifetime_and_existing_api(qapp):
    owner=QObject()
    audio=native_audio_output(owner)
    engine=audio._lumen_qml_engine
    component=audio._lumen_qml_component
    assert isinstance(audio,QAudioOutput)
    assert not shiboken6.createdByPython(audio)
    assert not shiboken6.ownedByPython(audio)
    assert audio.parent() is owner and engine.parent() is audio
    assert component.parent() is engine and component.isReady()
    audio.setVolume(.4);audio.setMuted(True)
    assert abs(audio.volume()-.4)<.001 and audio.isMuted()
    shiboken6.delete(owner)
    assert not shiboken6.isValid(audio)
    assert not shiboken6.isValid(engine) and not shiboken6.isValid(component)


def test_real_source_switching_with_bookmark_and_text_widgets_does_not_deadlock(video_factory,tmp_path):
    # A timeout in a separate process turns a native mutex/GIL deadlock into a
    # test failure instead of hanging the entire suite. Both clips carry AAC
    # audio so FFmpeg actually builds and tears down the affected audio pipeline.
    first=video_factory('Native audio source one.mp4','blue',4)
    second=video_factory('Native audio source two.mp4','green',4)
    script=r'''
import json,sys,time
from pathlib import Path
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtWidgets import QApplication,QLineEdit,QPlainTextEdit
from PySide6.QtMultimedia import QMediaPlayer
import shiboken6
from lumen.core import Library
from lumen.player import Player
app=QApplication([])
library=Library(sys.argv[1])
for source in sys.argv[2:]:library.import_folder(Path(source).parent,'movie',fast=True)
files=[work['files'][0] for work in library.query()]
assert len(files)==2
player=Player(library)
assert not player.mpv_backend and not shiboken6.createdByPython(player.audio)
def spin(ms):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec();app.processEvents()
player.open_file(files[0])
deadline=time.monotonic()+5
while player.media.mediaStatus()!=QMediaPlayer.MediaStatus.BufferedMedia and time.monotonic()<deadline:spin(20)
assert player.media.duration()>0 and player.media.playbackState()==QMediaPlayer.PlaybackState.PlayingState
assert player.media.audioTracks()
decoded=player.video.videoSink().videoFrame().isValid()
for index in range(80):
    player.open_file(files[index%2])
    spin(10)
    dialog=player.add_bookmark(file=files[index%2])
    assert dialog.findChild(QPlainTextEdit) is not None
    assert dialog.findChild(QLineEdit) is not None
    dialog.reject()
    edit=QPlainTextEdit();line=QLineEdit();line.textChanged.connect(edit.setPlainText)
    line.setText('Native audio teardown stress '+str(index))
    edit.deleteLater();line.deleteLater()
    spin(5)
player.close()
deadline=time.monotonic()+5
while not player.playback_journal.stop() and time.monotonic()<deadline:spin(10)
assert player.playback_journal.stop()
library.close()
print(json.dumps({'switches':80,'native_audio':not shiboken6.createdByPython(player.audio),'decoded_video_frame':decoded,'audio_tracks':True}))
'''
    environment=dict(os.environ,QT_QPA_PLATFORM='offscreen',QT_MEDIA_BACKEND='ffmpeg')
    source=str(Path(__file__).resolve().parents[1]/'src')
    environment['PYTHONPATH']=source+os.pathsep+environment.get('PYTHONPATH','')
    result=subprocess.run([sys.executable,'-c',script,str(tmp_path/'audio-stress'),str(first),str(second)],
                          capture_output=True,text=True,timeout=35,env=environment)
    assert result.returncode==0,result.stdout+'\n'+result.stderr[-5000:]
    summary=json.loads(result.stdout.strip().splitlines()[-1])
    assert summary['switches']==80 and summary['native_audio'] and summary['audio_tracks']
    assert summary['decoded_video_frame']
