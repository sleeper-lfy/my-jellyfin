"""An author's files form one playback group, just as episodes form a series."""
import time

import pytest
from PySide6.QtCore import QEventLoop,QTimer
from PySide6.QtMultimedia import QMediaPlayer
from PySide6.QtWidgets import QWidget

from lumen.player import Player
from test_core import add_work


def spin(app,ms=25):
    loop=QEventLoop();QTimer.singleShot(ms,loop.quit);loop.exec();app.processEvents()


def until(app,predicate,seconds=6):
    end=time.monotonic()+seconds
    while not predicate() and time.monotonic()<end:spin(app)
    assert predicate()


@pytest.fixture
def fans(qapp,library,video_factory):
    work=add_work(library,'Fans author',kind='fans',local=False)
    for index in range(1,4):
        source=video_factory(f'Fans clip {index:02}.mp4','blue',4)
        with library.db:
            library.db.execute('INSERT INTO files(work_id,path,digest,root,duration) VALUES (?,?,?,?,?)',
                               (work,str(source),f'fans-{index}',str(source.parent),4))
    files=library.work(work)['files']
    parent=QWidget();parent.random_active=False
    player=Player(library,parent)
    yield player,files,parent
    player.close();until(qapp,player.playback_journal.stop)
    parent.deleteLater();spin(qapp)


def test_previous_and_next_buttons_stay_inside_author_until_group_boundary(qapp,fans):
    player,files,parent=fans;next_authors=[];previous_authors=[]
    player.queueNext.connect(lambda:next_authors.append(1));player.queuePrevious.connect(lambda:previous_authors.append(1))
    player.open_file(files[0]);until(qapp,lambda:player.media.duration()>0)
    assert player.media.playbackState()==QMediaPlayer.PlaybackState.PlayingState
    assert player.next_control.toolTip()=='下一视频' and player.previous_control.toolTip()=='上一视频'
    assert 'Fans clip 01' in player.title.text()
    player.previous_control.click();assert previous_authors==[1] and player.file['id']==files[0]['id']
    player.next_control.click();assert player.file['id']==files[1]['id'] and not next_authors
    player.previous_control.click();assert player.file['id']==files[0]['id'] and previous_authors==[1]
    player.next_control.click();player.next_control.click();assert player.file['id']==files[2]['id'] and not next_authors
    player.next_control.click();assert next_authors==[1]


def test_end_of_media_uses_next_file_and_respects_auto_next_switch(library,fans):
    player,files,parent=fans;next_authors=[];player.queueNext.connect(lambda:next_authors.append(1))
    player.open_file(files[0]);player.status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    assert player.file['id']==files[1]['id'] and not next_authors
    library.set_setting('auto_next',False);player.status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    assert player.file['id']==files[1]['id'] and not next_authors
    library.set_setting('auto_next',True);player.open_file(files[-1]);player.status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    assert player.file['id']==files[-1]['id'] and next_authors==[1]


def test_repeat_one_restarts_entire_author_even_before_completion_is_flushed(library,fans):
    player,files,parent=fans;parent.random_active=True
    library.set_setting('queue',{'ids':[files[0]['work_id']],'index':0,'repeat':'one'})
    player.open_file(files[-1]);player.status_changed(QMediaPlayer.MediaStatus.EndOfMedia)
    assert player.file['id']==files[0]['id'] and player.resume==0
